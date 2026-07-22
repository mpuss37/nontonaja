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
    print("  1. 480p")
    print("  2. 720p")
    print("  3. 1080p")
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
    proxy_server = None
    client = httpx.Client(verify=False, follow_redirects=True, timeout=15)

    # Start local proxy for IDLIX streams (rewrites .jpg/.css extensions to .mp4)
    local_stream = stream_url
    try:
        from .proxy import start_proxy
        local_stream, proxy_server = start_proxy(stream_url)
        print(f"proxy ready: {local_stream}")
    except Exception as e:
        print(f"proxy failed: {e}")
        # Fallback: save m3u8 locally
        try:
            resp = client.get(stream_url)
            if resp.status_code == 200 and "#EXTM3U" in resp.text[:100]:
                m3u8_path = os.path.join(sub_dir, "stream.m3u8")
                with open(m3u8_path, "w") as f:
                    f.write(resp.text)
                local_stream = m3u8_path
        except Exception:
            pass

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
            "mpv", local_stream,
            f"--force-media-title={title}",
            "--no-ytdl",
            "--msg-level=vo=v",
            "--cache=yes",
            "--demuxer-max-bytes=50M",
            "--demuxer-readahead-secs=30",
        ]
        for sub in local_subs:
            mpv_cmd += ["--sub-file=" + sub]
        if headers:
            for k, v in headers.items():
                mpv_cmd += [f"--http-header-fields={k}: {v}"]
            if "User-Agent" in headers:
                mpv_cmd += [f"--user-agent={headers['User-Agent']}"]
        # Show stream ready message for non-IDLIX sources (IDLIX shows its own after countdown)
        if not local_stream.startswith("http://127.0.0.1:"):
            print(f"{title} stream ready, wait :)")
        subprocess.run(mpv_cmd)
    finally:
        if proxy_server:
            proxy_server.shutdown()
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
            sel_type = getattr(selected, "media_type", "movie")
            best_score = 0
            for r in results:
                rt = re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip()
                rt_words = set(rt.split())
                score = len(title_words & rt_words) / max(len(title_words), 1)
                if rt == title_norm and r.media_type == sel_type:
                    matched = r
                    break
                if rt == title_norm and not matched:
                    matched = r
                if score > best_score and score >= 0.5 and r.media_type == sel_type:
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
            sel_type = getattr(selected, "media_type", "movie")
            best_score = 0
            for r in results:
                rt = re.sub(r"\s*\(\d{4}\)$", "", r.title).lower().strip()
                rt_words = set(rt.split())
                score = len(title_words & rt_words) / max(len(title_words), 1)
                # Prefer exact title + same media_type
                if rt == title_norm and r.media_type == sel_type:
                    matched = r
                    break
                if rt == title_norm and not matched:
                    matched = r
                if score > best_score and score >= 0.5 and r.media_type == sel_type:
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
            # IDLIX: pass master URL directly to proxy (proxy handles quality selection)
            url = result.url
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
            # Add IDLIX subtitles (sub Indo) to FlixHQ
            subs = list(result.subtitles)
            try:
                idlix_results = idlix.search(selected.title)
                title_norm2 = re.sub(r"\s*\(\d{4}\)$", "", selected.title).lower().strip()
                for ir in idlix_results:
                    rt2 = re.sub(r"\s*\(\d{4}\)$", "", ir.title).lower().strip()
                    if rt2 == title_norm2 or title_norm2 in rt2 or rt2 in title_norm2:
                        idlix_stream = idlix.get_stream(ir.id, ir.media_type, selected.title)
                        if idlix_stream and idlix_stream.subtitles:
                            subs.extend(idlix_stream.subtitles)
                            break
            except Exception:
                pass
            return (url, subs, {})

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
