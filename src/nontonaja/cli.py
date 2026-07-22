from __future__ import annotations

import argparse
import os
import re
import sys
import subprocess
import tempfile
import shutil

import httpx

from .config import load_config, merge_args
from .providers import flixhq, lk21, idlix
from .quality import select_quality


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nontonaja",
        description="A CLI media streaming tool",
    )
    p.add_argument("query", nargs="*", help="Search query")
    p.add_argument("-q", "--quality", type=int, choices=[360, 720, 1080], help="Video quality")
    p.add_argument("-d", "--download", nargs="?", const=".", help="Download to directory")
    return p


def _pick(results):
    for i, r in enumerate(results, 1):
        year = getattr(r, "year", "")
        mtype = getattr(r, "media_type", "?")
        title = r.title
        # Strip year from title if already present to avoid duplication
        if year and title.endswith(f" ({year})"):
            title = title[: -len(f" ({year})")]
        label = f" ({year})" if year else ""
        print(f"  {i}. {title}{label} [{mtype}]")
    try:
        choice = int(input("Pilih: ")) - 1
        return results[choice]
    except (ValueError, IndexError):
        return None


def _pick_source():
    print("  1. 480p (sub-indo)")
    print("  2. 720p+ (nonsub)")
    print("  3. 1080p (subtitle)")
    try:
        choice = int(input("Source: "))
        if choice == 1:
            return "lk21"
        elif choice == 3:
            return "idlix"
        return "flixhq"
    except (ValueError):
        return "flixhq"


def _flixhq_query(title: str) -> str:
    """Extract core search keyword from a movie title for FlixHQ search.

    FlixHQ search only works well with simple 1-2 word queries.
    Extract the most important franchise/character keyword.
    """
    q = re.sub(r"\([^)]*\)", "", title)
    q = re.sub(r"\d{4}", "", q)
    q = re.sub(r"[:\-]", " ", q)
    for prefix in ["The ", "A ", "An "]:
        if q.startswith(prefix):
            q = q[len(prefix):]
    words = [w for w in q.split() if len(w) > 2]
    # Use first word if it's a franchise keyword (Spider, Avengers, Batman, etc.)
    # Otherwise use first 2 words
    return words[0] if words else title.split()[0]


def _search(query: str) -> list:
    """Unified search: LK21 + FlixHQ + IDLIX."""
    try:
        lk21_results = lk21.search(query)
    except Exception:
        lk21_results = []

    seen = set()
    lk21_dedup = []
    for r in lk21_results:
        key = re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip()
        if key not in seen:
            seen.add(key)
            lk21_dedup.append(r)

    try:
        flixhq_results = flixhq.search(query)
    except Exception:
        flixhq_results = []

    try:
        idlix_results = idlix.search(query)
    except Exception:
        idlix_results = []

    merged = list(lk21_dedup)
    lk21_titles = {re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip() for r in lk21_dedup}
    for r in flixhq_results:
        key = re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip()
        if key not in lk21_titles:
            merged.append(r)

    existing_titles = {re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip() for r in merged}
    for r in idlix_results:
        key = re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip()
        if key not in existing_titles:
            merged.append(r)

    def _sort_key(r):
        year_str = getattr(r, "year", "") or "0"
        try:
            year = int(re.sub(r"[^\d]", "", year_str) or "0")
        except ValueError:
            year = 0
        return (-year, r.title.lower())

    merged.sort(key=_sort_key)
    return merged


def _play(stream_url: str, title: str, subtitles: list[str], headers: dict | None = None) -> None:
    sub_dir = tempfile.mkdtemp(prefix="nontonaja-subs-")
    local_subs = []
    client = httpx.Client(verify=False, follow_redirects=True, timeout=15)
    for sub_url in subtitles:
        try:
            resp = client.get(sub_url)
            ext = ".vtt" if ".vtt" in sub_url else ".srt"
            lang = sub_url.rsplit("_", 1)[-1].split(".")[0] if "_" in sub_url else "sub"
            path = os.path.join(sub_dir, f"sub_{lang}{ext}")
            with open(path, "wb") as f:
                f.write(resp.content)
            local_subs.append(path)
        except Exception:
            pass

    try:
        mpv_cmd = [
            "mpv", stream_url,
            "--profile=high-quality",
            "--msg-level=vo=v",
            f"--force-media-title={title}",
        ]
        for sub in local_subs:
            mpv_cmd += ["--sub-file=" + sub]
        if headers:
            for k, v in headers.items():
                mpv_cmd += [f"--http-header-fields={k}: {v}"]
            if "User-Agent" in headers:
                mpv_cmd += [f"--user-agent={headers['User-Agent']}"]
        subprocess.run(mpv_cmd)
    finally:
        shutil.rmtree(sub_dir, ignore_errors=True)


def _get_stream(selected, quality, source_choice) -> tuple[str, list[str], dict] | None:
    """Get stream from chosen source."""
    if source_choice == "lk21":
        source = getattr(selected, "source", "")
        if source == "lk21":
            result = lk21.get_p2p_stream(selected.id)
        else:
            # Cross-source: search LK21 by title
            try:
                results = lk21.search(selected.title)
            except Exception:
                results = []
            matched = None
            title_norm = re.sub(r"\s*\(\d{4}\)$", "", selected.title).lower().strip()
            title_words = set(title_norm.split())
            best_score = 0
            for r in results:
                rt = re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip()
                if rt == title_norm:
                    matched = r
                    break
                rt_words = set(rt.split())
                score = len(title_words & rt_words) / max(len(title_words), 1)
                if score > best_score and score >= 0.5:
                    best_score = score
                    matched = r
            if not matched:
                return None
            result = lk21.get_p2p_stream(matched.id)
        if result and result.url:
            url = select_quality(result.url, quality, headers=result.headers)
            return (url, result.subtitles, result.headers)
    elif source_choice == "idlix":
        source = getattr(selected, "source", "")
        if source == "idlix":
            try:
                result = idlix.get_stream(selected.id, getattr(selected, "media_type", "movie"), selected.title)
            except Exception as e:
                print(f"get_stream error: {e}")
                result = None
        else:
            # Cross-source: search IDLIX by title
            try:
                results = idlix.search(selected.title)
            except Exception as e:
                print(f"search error: {e}")
                results = []
            matched = None
            title_norm = re.sub(r"\s*\(\d{4}\)$", "", selected.title).lower().strip()
            title_words = set(title_norm.split())
            best_score = 0
            for r in results:
                rt = re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip()
                if rt == title_norm:
                    matched = r
                    break
                rt_words = set(rt.split())
                score = len(title_words & rt_words) / max(len(title_words), 1)
                if score > best_score and score >= 0.5:
                    best_score = score
                    matched = r
            if not matched:
                print(f"no match for '{selected.title}'")
                return None
            try:
                result = idlix.get_stream(matched.id, matched.media_type, selected.title)
            except Exception as e:
                print(f"get_stream error: {e}")
                result = None
        if result and result.url:
            url = select_quality(result.url, quality)
            return (url, result.subtitles, {})
    else:
        # FlixHQ: try selected ID directly, then search by title
        media_id = getattr(selected, "id", None)
        source = getattr(selected, "source", "")

        if source == "flixhq" and media_id:
            result = flixhq.get_stream(media_id)
        else:
            # FlixHQ search needs simple queries — extract core keywords
            search_query = _flixhq_query(selected.title)
            try:
                results = flixhq.search(search_query)
            except Exception:
                results = []

            matched = None
            title_norm = re.sub(r"\s*\(\d{4}\)$", "", selected.title).lower().strip()
            title_words = set(title_norm.split())
            best_score = 0
            for r in results:
                rt = re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip()
                if rt == title_norm:
                    matched = r
                    break
                rt_words = set(rt.split())
                score = len(title_words & rt_words) / max(len(title_words), 1)
                if score > best_score and score >= 0.5:
                    best_score = score
                    matched = r
            if not matched:
                return None

            result = flixhq.get_stream(matched.id)

        if result and result.url:
            url = select_quality(result.url, quality)
            return (url, result.subtitles, {})

    return None


def run(args: argparse.Namespace) -> None:
    config = load_config()
    config = merge_args(config, args)

    query = " ".join(args.query) if args.query else ""
    if not query:
        query = input("Search: ").strip()
    if not query:
        print("No query.")
        sys.exit(1)

    results = _search(query)
    if not results:
        print(f"No results for '{query}'.")
        sys.exit(1)

    selected = _pick(results) if len(results) > 1 else results[0]
    if not selected:
        print("Invalid choice.")
        sys.exit(1)

    source_choice = _pick_source()

    stream = _get_stream(selected, config.quality, source_choice)
    if not stream:
        print(f"No stream found.")
        sys.exit(1)

    stream_url, subtitles, headers = stream

    if args.download is not None:
        from .download import download
        download_dir = args.download or os.getcwd()
        download(stream_url, download_dir, selected.title, subtitles, config.subs_language)
        return

    _play(stream_url, selected.title, subtitles, headers=headers)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)
