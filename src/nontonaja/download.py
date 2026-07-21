from __future__ import annotations

import subprocess


def download(
    url: str,
    output_path: str,
    title: str,
    subtitles: list[str] | None = None,
    subtitle_language: str = "English",
) -> None:
    output = f"{output_path}/{title}.mkv"

    cmd = ["ffmpeg", "-i", url, "-stats", "-loglevel", "error"]

    for sub in subtitles or []:
        cmd += ["-i", sub]

    cmd += ["-c:v", "copy", "-c:a", "copy"]

    if subtitles:
        for i, _ in enumerate(subtitles):
            cmd += ["-map", f"{i + 1}"]
            cmd += ["-metadata:s:s:0", f"language={subtitle_language}"]

    cmd += [output]

    print(f"Downloading to: {output}")
    subprocess.run(cmd, check=True)
    print("Download complete.")
