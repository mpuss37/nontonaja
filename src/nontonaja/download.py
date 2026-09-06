from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

import httpx

from .proxy import start_proxy


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filesystem filename."""
    # Replace illegal filename characters
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "video"


def detect_subtitle_info(url: str, text: str = "") -> tuple[str, str]:
    """Detect subtitle label and 3-letter language code (e.g., ('Indonesian', 'ind'))."""
    url_lower = url.lower()
    if any(k in url_lower for k in ("indonesia", "_id", "/id/", "sub_id")):
        return "Indonesian", "ind"
    if any(k in url_lower for k in ("english", "_en", "/en/", "sub_en")):
        return "English", "eng"
    if any(k in url_lower for k in ("romanian", "_ro", "/ro/")):
        return "Romanian", "ron"

    # Content-based detection
    if text:
        sample = text[:3000].lower()
        indo_words = {
            "yang", "dan", "aku", "kau", "kamu", "tidak", "di", "ini", "itu",
            "untuk", "dengan", "ada", "dari", "dia", "mereka", "sudah", "bisa",
            "akan", "tapi", "pada", "saya"
        }
        words = set(re.findall(r"\w+", sample))
        if len(indo_words & words) >= 2:
            return "Indonesian", "ind"

        eng_words = {
            "the", "and", "you", "that", "with", "this", "have", "what",
            "know", "from", "they", "will", "would", "about"
        }
        if len(eng_words & words) >= 3:
            return "English", "eng"

    return "Subtitle", "und"


def _get_stream_duration(url: str, headers: dict | None = None) -> float | None:
    """Attempt to probe stream duration in seconds via ffprobe or m3u8 playlist."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
    ]
    if headers:
        header_strs = [f"{k}: {v}" for k, v in headers.items()]
        cmd += ["-headers", "\r\n".join(header_strs) + "\r\n"]
    cmd += [url]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        val = res.stdout.strip()
        if val and val != "N/A":
            dur = float(val)
            if dur > 0:
                return dur
    except Exception:
        pass
    return None


def _format_time_sec(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _parse_time_str(time_str: str) -> float:
    """Parse HH:MM:SS or HH:MM:SS.xx into seconds."""
    parts = time_str.split(":")
    if len(parts) == 3:
        try:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        except ValueError:
            pass
    elif len(parts) == 2:
        try:
            return float(parts[0]) * 60 + float(parts[1])
        except ValueError:
            pass
    return 0.0


def _format_bytes(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def _render_progress_bar(percent: float, width: int = 25) -> str:
    clamped = max(0.0, min(100.0, percent))
    filled = int(round(width * clamped / 100))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {clamped:5.1f}%"


def download(
    url: str,
    output_path: str,
    title: str,
    subtitles: list[str] | None = None,
    subtitle_language: str = "Indonesian",
    headers: dict | None = None,
) -> None:
    os.makedirs(output_path, exist_ok=True)
    safe_title = sanitize_filename(title)
    output = os.path.join(output_path, f"{safe_title}.mkv")

    proxy_server = None
    sub_dir = tempfile.mkdtemp(prefix="nontonaja-dl-")
    local_subs: list[tuple[str, str, str]] = []  # (path, label, lang_code)
    client = httpx.Client(verify=False, follow_redirects=True, timeout=15)

    stream_url = url
    try:
        if any(keyword in url for keyword in ("idlix", "majorplay", "config-", "pentos", "playcdn", "qornexia", "blaytoro")):
            try:
                stream_url, proxy_server = start_proxy(url, headers=headers)
            except Exception as e:
                print(f"Proxy start warning: {e}")

        print(f"\nMenyiapkan unduhan: {safe_title}")
        for i, sub_url in enumerate(subtitles or []):
            if sub_url.startswith(("http://", "https://")):
                try:
                    resp = client.get(sub_url)
                    if resp.status_code == 200:
                        text_content = resp.text
                        label, lang_code = detect_subtitle_info(sub_url, text_content)
                        ext = ".vtt" if ".vtt" in sub_url else ".srt"
                        sub_file = os.path.join(sub_dir, f"{i}_{label}{ext}")
                        with open(sub_file, "wb") as f:
                            f.write(resp.content)
                        local_subs.append((sub_file, label, lang_code))
                except Exception:
                    pass
            elif os.path.exists(sub_url):
                try:
                    with open(sub_url, "r", encoding="utf-8", errors="ignore") as f:
                        text_content = f.read(3000)
                except Exception:
                    text_content = ""
                label, lang_code = detect_subtitle_info(sub_url, text_content)
                local_subs.append((sub_url, label, lang_code))

        # Sort subtitles so preferred subtitle language is placed first
        local_subs.sort(key=lambda s: 0 if s[1].lower() == subtitle_language.lower() or s[2] == "ind" else 1)

        cmd = ["ffmpeg", "-y"]
        if headers:
            header_strs = [f"{k}: {v}" for k, v in headers.items()]
            cmd += ["-headers", "\r\n".join(header_strs) + "\r\n"]

        cmd += ["-i", stream_url]

        for sub_file, _, _ in local_subs:
            cmd += ["-i", sub_file]

        cmd += ["-map", "0:v?", "-map", "0:a?"]
        for i, (_, label, lang_code) in enumerate(local_subs):
            cmd += ["-map", f"{i + 1}:s?"]
            cmd += [f"-metadata:s:s:{i}", f"language={lang_code}", f"-metadata:s:s:{i}", f"title={label}"]

        cmd += [
            "-c:v", "copy",
            "-c:a", "copy",
            "-c:s", "srt",
            "-progress", "pipe:1",
            "-nostats",
            "-loglevel", "quiet",
            output,
        ]

        print(f"Lokasi file: {output}")
        if local_subs:
            sub_names = ", ".join([f"{label} ({code})" for _, label, code in local_subs])
            print(f"Subtitle disertakan: {sub_names}")

        # Probe total duration
        total_duration = _get_stream_duration(stream_url, headers=headers)
        total_dur_str = _format_time_sec(total_duration) if total_duration else "N/A"

        print("\nMengunduh... (Tekan Ctrl+C untuk membatalkan)")

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

        current_size = 0
        current_time_str = "00:00:00"
        current_speed_str = "0x"

        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            line = line.strip()
            if "=" in line:
                key, val = line.split("=", 1)
                if key == "total_size" and val.isdigit():
                    current_size = int(val)
                elif key == "out_time":
                    current_time_str = val.split(".")[0]
                elif key == "speed":
                    current_speed_str = val
                elif key == "progress":
                    cur_sec = _parse_time_str(current_time_str)
                    size_formatted = _format_bytes(current_size)

                    # Extract speed float multiplier
                    speed_match = re.search(r"([\d\.]+)", current_speed_str)
                    speed_val = float(speed_match.group(1)) if speed_match else 1.0

                    if total_duration and total_duration > 0:
                        pct = (cur_sec / total_duration) * 100.0
                        bar_str = _render_progress_bar(pct, width=22)
                        rem_sec = max(0.0, total_duration - cur_sec) / max(speed_val, 0.1)
                        rem_str = _format_time_sec(rem_sec)
                        line_out = f"\r  {bar_str} | {size_formatted} | Durasi: {current_time_str}/{total_dur_str} | Sisa: ~{rem_str} ({current_speed_str})   "
                    else:
                        line_out = f"\r  Terunduh: {size_formatted} | Durasi: {current_time_str} | Kecepatan: {current_speed_str}   "

                    sys.stdout.write(line_out)
                    sys.stdout.flush()

        proc.stdout.close()
        ret = proc.wait()
        if ret == 0:
            print(f"\n\nUnduhan selesai! Disimpan di: {output}\n")
        else:
            print(f"\n\nGagal mengunduh video. (Kode keluar ffmpeg: {ret})\n")
    except KeyboardInterrupt:
        print("\n\nUnduhan dibatalkan oleh pengguna.\n")
    finally:
        if proxy_server:
            proxy_server.shutdown()
        shutil.rmtree(sub_dir, ignore_errors=True)


