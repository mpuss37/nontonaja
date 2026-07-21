from __future__ import annotations

import os
from pathlib import Path

from .config import PlayerConfig


def _history_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "~"))
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "~/.local/share")
        base = Path(xdg)
    return base / "nontonaja" / "history.txt"


def save_history(
    title: str,
    position: str,
    media_id: str,
    image: str,
    *,
    season: str | None = None,
    episode_title: str | None = None,
) -> None:
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    parts = [title, position, media_id, image]
    if season and episode_title:
        parts = [title, position, media_id, season, episode_title, image]

    with open(path, "a") as f:
        f.write("\t".join(parts) + "\n")


def clear_history() -> None:
    path = _history_path()
    if path.exists():
        path.unlink()


def load_history() -> list[dict]:
    path = _history_path()
    if not path.exists():
        return []

    entries = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 4:
            entry = {
                "title": parts[0],
                "position": parts[1],
                "media_id": parts[2],
                "image": parts[3],
            }
            if len(parts) >= 6:
                entry["season"] = parts[4]
                entry["episode_title"] = parts[5]
            entries.append(entry)
    return entries


def remove_history_entry(media_id: str) -> None:
    path = _history_path()
    if not path.exists():
        return

    lines = path.read_text().splitlines()
    filtered = [l for l in lines if media_id not in l]
    path.write_text("\n".join(filtered) + "\n")
