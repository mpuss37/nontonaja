from __future__ import annotations

import shutil


def _has_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def check_dependencies() -> None:
    required = ["mpv", "fzf", "ffmpeg"]
    optional = ["rofi", "chafa"]

    for cmd in required:
        if not _has_command(cmd):
            raise SystemExit(f"Error: '{cmd}' is required but not installed.")

    for cmd in optional:
        if not _has_command(cmd):
            import warnings

            warnings.warn(f"'{cmd}' not found. Some features may be unavailable.")
