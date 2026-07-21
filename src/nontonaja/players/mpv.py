from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class MpvArgs:
    url: str
    sub_files: list[str] | None = None
    force_media_title: str | None = None
    save_position_on_quit: bool = True
    watch_later_dir: str | None = None


def play(args: MpvArgs) -> subprocess.Popen:
    cmd = ["mpv", args.url]

    if args.sub_files:
        for sub in args.sub_files:
            cmd += ["--sub-files=" + sub]

    if args.force_media_title:
        cmd += [f"--force-media-title={args.force_media_title}"]

    if args.save_position_on_quit:
        cmd += ["--save-position-on-quit"]

    if args.watch_later_dir:
        cmd += [f"--watch-later-dir={args.watch_later_dir}"]

    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
