from __future__ import annotations

import argparse
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import httpx

from .config import load_config, merge_args
from .providers import flixhq, idlix, lk21
from .quality import select_quality


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nontonaja",
        description="A CLI media streaming and downloading tool",
    )
    p.add_argument("query", nargs="*", help="Search query")
    p.add_argument("-q", "--quality", type=int, choices=[360, 480, 720, 1080], help="Video quality")
    p.add_argument("-d", "--download", action="store_true", help="Download video mode")
    p.add_argument("-o", "--output", help="Output directory for download (default: current directory)")
    return p


def _fzf_menu(options: list[str], prompt: str = "Select: ") -> str | None:
    """Show an interactive fzf menu if available and running in a TTY."""
    if not shutil.which("fzf") or not sys.stdin.isatty():
        return None
    try:
        proc = subprocess.run(
            [
                "fzf",
                "--reverse",
                "--prompt",
                prompt,
                "--height",
                "40%",
                "--border",
                "--info=inline",
            ],
            input="\n".join(options),
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return None


def _pick(results):
    items = []
    for r in results:
        year = getattr(r, "year", "")
        mtype = getattr(r, "media_type", "?")
        title = r.title
        # Strip year from title if already present to avoid duplication
        if year and title.endswith(f" ({year})"):
            title = title[: -len(f" ({year})")]
        label = f" ({year})" if year else ""
        items.append(f"{title}{label} [{mtype}]")

    # Try fzf first (ani-cli style)
    selected_item = _fzf_menu(items, prompt="Select Movie: ")
    if selected_item and selected_item in items:
        return results[items.index(selected_item)]

    # Fallback numbered list
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    try:
        choice = int(input("Pilih: ")) - 1
        return results[choice]
    except (ValueError, IndexError):
        return None


def _pick_action() -> str:
    actions = [
        "1. Stream (Play via mpv)",
        "2. Download",
        "3. Stream & Download",
        "4. Change Quality / Source",
        "5. Exit",
    ]
    selected = _fzf_menu(actions, prompt="Select Action: ")
    if selected:
        if "Stream & Download" in selected:
            return "both"
        elif "Download" in selected and "Stream" not in selected:
            return "download"
        elif "Change Quality" in selected or "Change Source" in selected:
            return "change_quality"
        elif "Exit" in selected:
            return "exit"
        return "play"

    print("Action:")
    print("  1. Stream (Play via mpv)")
    print("  2. Download")
    print("  3. Stream & Download")
    print("  4. Change Quality / Source")
    print("  5. Exit")
    while True:
        try:
            choice = input("Pilih action (default: 1): ").strip()
            if not choice or choice == "1":
                return "play"
            elif choice == "2":
                return "download"
            elif choice == "3":
                return "both"
            elif choice == "4":
                return "change_quality"
            elif choice == "5":
                return "exit"
            print("Pilihan tidak valid. Silakan pilih 1-5.")
        except (ValueError, EOFError):
            return "play"


def _pick_source():
    sources = [
        "1. 480p",
        "2. 720p",
        "3. 1080p",
    ]
    selected = _fzf_menu(sources, prompt="Select Quality/Source: ")
    if selected:
        if selected.startswith("1") or "480p" in selected:
            return "lk21", None
        elif selected.startswith("2") or "720p" in selected:
            return "flixhq", 720
        elif selected.startswith("3") or "1080p" in selected:
            return "flixhq", 1080

    print("Quality / Source:")
    print("  1. 480p")
    print("  2. 720p")
    print("  3. 1080p")
    while True:
        try:
            choice = int(input("Source: "))
            if choice == 1:
                return "lk21", None
            elif choice == 2:
                return "flixhq", 720
            elif choice == 3:
                return "flixhq", 1080
            print("Pilihan tidak valid. Silakan pilih 1, 2, atau 3.")
        except ValueError:
            print("Input harus berupa angka (1, 2, atau 3).")


def _find_flixhq_match(title: str, year: str = "", media_type: str = "movie"):
    """Find matching item by testing progressive queries and verifying title/type."""
    clean = re.sub(r"\s*\(\d{4}\)$", "", title).strip()
    title_norm = clean.lower()
    title_words = [w for w in re.findall(r"\w+", title_norm) if w not in ("the", "a", "an")]
    title_nums = {w for w in re.findall(r"\w+", title_norm) if w.isdigit()}

    queries = []
    # If title has hyphen (e.g. Spider-Man), try hyphenated keyword first
    hyphen_match = re.match(r"^([\w]+-[\w]+)", clean)
    if hyphen_match:
        queries.append(hyphen_match.group(1))

    # All meaningful words from title
    q_words = [w for w in re.sub(r"[:\-]", " ", clean).split() if len(w) > 2 and w.lower() not in ("the", "a", "an")]
    if len(q_words) >= 2:
        queries.append(" ".join(q_words[:2]))
    for w in q_words:
        queries.append(w)
    queries.append(clean)

    seen = set()
    dedup_queries = []
    for q in queries:
        if q and q.lower() not in seen:
            seen.add(q.lower())
            dedup_queries.append(q)

    best_candidate = None
    best_score = 0

    for q in dedup_queries:
        try:
            results = flixhq.search(q)
        except Exception:
            continue

        for r in results:
            rt = re.sub(r"\s*\(\d{4}\)$", "", r.title).strip().lower()
            rt_words = [w for w in re.findall(r"\w+", rt) if w not in ("the", "a", "an")]
            rt_nums = {w for w in rt_words if w.isdigit()}
            r_type = getattr(r, "media_type", "movie")
            r_year = getattr(r, "year", "")

            # Exact title + same media type + matching year is an instant win
            if rt == title_norm and r_type == media_type:
                if not year or not r_year or year == r_year:
                    return r
                # Exact title but wrong year — weak candidate only
                if 1.5 > best_score:
                    best_score = 1.5
                    best_candidate = r
                continue
            if rt == title_norm:
                if not year or not r_year or year == r_year:
                    if 2.5 > best_score:
                        best_candidate = r
                        best_score = 2.5
                elif 1.0 > best_score:
                    best_candidate = r
                    best_score = 1.0
                continue

            # Sequels/numbers must strictly match
            if title_nums and not (title_nums <= rt_nums):
                continue
            if not title_nums and rt_nums:
                continue

            # Must share at least one meaningful word
            set_title_words = set(title_words)
            set_rt_words = set(rt_words)
            if not (set_title_words & set_rt_words):
                continue

            # Meaningful word overlap + sequence similarity
            overlap = len(set_title_words & set_rt_words) / max(len(set_title_words), 1)
            # Reverse overlap: penalize results with many extra words not in query
            reverse_overlap = len(set_title_words & set_rt_words) / max(len(set_rt_words), 1)
            sim = difflib.SequenceMatcher(None, title_norm, rt).ratio()

            score = overlap * 1.0 + reverse_overlap * 1.0 + sim
            if r_type == media_type:
                score += 0.3
            if year and r_year and year == r_year:
                score += 0.5
            elif year and r_year and year != r_year:
                score -= 1.0

            if score > best_score and score >= 2.0 and sim >= 0.65:
                best_score = score
                best_candidate = r

        if best_candidate and best_score >= 2.0:
            return best_candidate

    return best_candidate if best_score >= 2.0 else None


def _search(query: str) -> list:
    """Unified search across all sources."""
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

    q_norm = query.lower().strip()
    q_words = set(re.findall(r"\w+", q_norm))

    def _sort_key(r):
        title = r.title
        year_str = getattr(r, "year", "") or "0"
        try:
            year = int(re.sub(r"[^\d]", "", year_str) or "0")
        except ValueError:
            year = 0

        clean = re.sub(r"\s*\(\d{4}\)$", "", title).lower().strip()
        words = set(re.findall(r"\w+", clean))

        is_exact = 1 if clean == q_norm else 0
        overlap = len(q_words & words) / max(len(q_words), 1)
        sim = difflib.SequenceMatcher(None, q_norm, clean).ratio()

        relevance = is_exact * 2.0 + overlap * 1.5 + sim
        return (-round(relevance, 2), -year, clean)

    merged.sort(key=_sort_key)
    return merged


def _play(stream_url: str, title: str, subtitles: list[str], headers: dict | None = None, detach: bool = False) -> None:
    sub_dir = tempfile.mkdtemp(prefix="nontonaja-subs-")
    local_subs = []
    proxy_server = None
    client = httpx.Client(verify=False, follow_redirects=True, timeout=15)

    # Start local proxy for HLS streams (rewrites .jpg/.css/.pict extensions to .ts/.mp4)
    local_stream = stream_url
    try:
        from .proxy import start_proxy
        local_stream, proxy_server = start_proxy(stream_url, headers=headers)
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

    from .download import detect_subtitle_info

    sub_items: list[tuple[str, str, str]] = []  # (path, label, lang_code)
    for i, sub_url in enumerate(subtitles):
        try:
            resp = client.get(sub_url)
            if resp.status_code == 200:
                text_content = resp.text
                label, lang_code = detect_subtitle_info(sub_url, text_content)
                ext = ".vtt" if ".vtt" in sub_url else ".srt"
                path = os.path.join(sub_dir, f"{i}_{label}{ext}")
                with open(path, "wb") as f:
                    f.write(resp.content)
                sub_items.append((path, label, lang_code))
        except Exception:
            pass

    # Sort so Indonesian subtitles come first
    sub_items.sort(key=lambda s: 0 if s[2] == "ind" or "indonesia" in s[1].lower() else 1)
    local_subs = [s[0] for s in sub_items]

    def _cleanup():
        if proxy_server:
            proxy_server.shutdown()
        shutil.rmtree(sub_dir, ignore_errors=True)

    mpv_cmd = [
        "mpv", local_stream,
        f"--force-media-title={title}",
        "--no-ytdl",
        "--msg-level=vo=v",
        "--cache=yes",
        "--demuxer-max-bytes=50M",
        "--demuxer-readahead-secs=30",
        "--slang=id,ind,indonesian,en,eng",
    ]
    for sub in local_subs:
        mpv_cmd += ["--sub-file=" + sub]
    if headers:
        for k, v in headers.items():
            mpv_cmd += [f"--http-header-fields={k}: {v}"]
        if "User-Agent" in headers:
            mpv_cmd += [f"--user-agent={headers['User-Agent']}"]

    if detach:
        import threading
        def _run_bg():
            try:
                subprocess.run(mpv_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            finally:
                _cleanup()

        t = threading.Thread(target=_run_bg, daemon=True)
        t.start()
        print("Pemutaran dimulai di jendela MPV. Terminal tetap aktif.\n")
    else:
        try:
            subprocess.run(mpv_cmd)
        finally:
            _cleanup()


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
            try:
                url = select_quality(result.url, quality, headers=result.headers)
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError):
                url = result.url
            return (url, result.subtitles, result.headers)

        fallback = _get_stream(selected, quality or 720, "flixhq")
        if fallback:
            return fallback
        return _get_stream(selected, quality, "idlix")
    elif source_choice == "idlix":
        source = getattr(selected, "source", "")
        if source == "idlix":
            try:
                result = idlix.get_stream(selected.id, getattr(selected, "media_type", "movie"), selected.title)
            except Exception as e:
                print(f"get_stream error: {e}")
                result = None
        else:
            # Cross-source search by title
            clean_title = re.sub(r"\s*\(\d{4}\)$", "", selected.title).strip()
            try:
                results = idlix.search(clean_title)
            except Exception as e:
                print(f"search error: {e}")
                results = []
            matched = None
            title_norm = clean_title.lower()
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
                result = idlix.get_stream(selected.id, getattr(selected, "media_type", "movie"), selected.title)
            except Exception as e:
                print(f"get_stream error: {e}")
                result = None
        if result and result.url:
            # Pass master URL directly to proxy (proxy handles quality selection)
            url = result.url
            return (url, result.subtitles, {})
    else:
        # Try selected ID directly, then search by title
        media_id = getattr(selected, "id", None)
        source = getattr(selected, "source", "")

        result = None
        if source == "flixhq" and media_id:
            result = flixhq.get_stream(media_id)
        else:
            sel_type = getattr(selected, "media_type", "movie")
            sel_year = getattr(selected, "year", "")
            matched = _find_flixhq_match(selected.title, year=sel_year, media_type=sel_type)
            if matched:
                result = flixhq.get_stream(matched.id)

        if result and result.url:
            try:
                url = select_quality(result.url, quality)
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError):
                url = result.url
            # Merge additional subtitles
            subs = list(result.subtitles)
            try:
                clean_title2 = re.sub(r"\s*\(\d{4}\)$", "", selected.title).strip()
                idlix_results = idlix.search(clean_title2)
                title_norm2 = clean_title2.lower()
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

        # Fallback
        fallback = _get_stream(selected, quality, "idlix")
        if fallback:
            return fallback

    return None


def _prepare_stream(selected, quality, source_choice, title: str = ""):
    """Run _get_stream in background thread while showing progress bar."""
    bar_width = 22
    label = title or "stream"
    result_holder = [None]
    done = threading.Event()

    def _fetch():
        result_holder[0] = _get_stream(selected, quality, source_choice)
        done.set()

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()

    elapsed = 0.0
    interval = 0.25
    # Use asymptotic progress: approaches 95% but never reaches 100% until done
    while not done.is_set():
        pct = min(95.0, (1 - 1 / (1 + elapsed / 8)) * 100)
        filled = int(round(bar_width * (pct / 100.0)))
        bar = "█" * filled + "░" * (bar_width - filled)
        secs = int(elapsed)
        sys.stdout.write(f"\r  Menyiapkan stream: [{bar}] {pct:5.1f}% | {secs}s ({label})   ")
        sys.stdout.flush()
        done.wait(timeout=interval)
        elapsed += interval

    # Complete
    bar = "█" * bar_width
    sys.stdout.write(f"\r  Menyiapkan stream: [{bar}] 100.0% | Stream siap! ({label})                    \n")
    sys.stdout.flush()

    return result_holder[0]


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

    source_choice, quality_override = _pick_source()
    quality = quality_override or config.quality

    stream = _prepare_stream(selected, quality, source_choice, selected.title)
    if not stream:
        print("No stream found.")
        sys.exit(1)

    stream_url, subtitles, headers = stream

    if args.download or args.output:
        from .download import download
        download_dir = args.output or config.download_dir or os.getcwd()
        download(stream_url, download_dir, selected.title, subtitles, config.subs_language, headers=headers)
        return

    while True:
        action = _pick_action()
        if action == "exit":
            break
        elif action == "play":
            _play(stream_url, selected.title, subtitles, headers=headers, detach=True)
        elif action == "download":
            from .download import download
            download_dir = args.output or config.download_dir or os.getcwd()
            download(stream_url, download_dir, selected.title, subtitles, config.subs_language, headers=headers)
            break
        elif action == "both":
            from .download import download
            _play(stream_url, selected.title, subtitles, headers=headers, detach=True)
            download_dir = args.output or config.download_dir or os.getcwd()
            download(stream_url, download_dir, selected.title, subtitles, config.subs_language, headers=headers)
            break
        elif action == "change_quality":
            source_choice, quality_override = _pick_source()
            quality = quality_override or config.quality
            new_stream = _prepare_stream(selected, quality, source_choice, selected.title)
            if new_stream:
                stream_url, subtitles, headers = new_stream
                print("Quality / source berhasil diubah.\n")
            else:
                print("Stream tidak ditemukan untuk source yang dipilih. Stream sebelumnya tetap digunakan.\n")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)
