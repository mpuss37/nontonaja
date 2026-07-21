from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class CelluloidArgs:
    url: str
    mpv_sub_files: list[str] | None = None
    mpv_force_media_title: str | None = None


def play(args: CelluloidArgs) -> None:
    cmd = ["celluloid"]

    if args.mpv_sub_files:
        for sub in args.mpv_sub_files:
            cmd += [f"--mpv-sub-files={sub}"]

    if args.mpv_force_media_title:
        cmd += [f"--mpv-force-media-title={args.mpv_force_media_title}"]

    cmd += [args.url]
    subprocess.run(cmd, check=True)
