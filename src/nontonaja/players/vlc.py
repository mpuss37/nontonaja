from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class VlcArgs:
    url: str
    input_slave: list[str] | None = None
    meta_title: str | None = None


def play(args: VlcArgs) -> None:
    cmd = ["vlc", args.url]

    if args.input_slave:
        slaves = "#".join(args.input_slave)
        cmd += [f"--input-slave={slaves}"]

    if args.meta_title:
        cmd += [f"--meta-title={args.meta_title}"]

    cmd += ["--play-and-exit"]
    subprocess.run(cmd, check=True)
