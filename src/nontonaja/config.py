from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    quality: int | None = None
    subs_language: str = "English"
    download_dir: str | None = None


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(xdg).expanduser() / "nontonaja"


def load_config() -> Config:
    cfg = Config()
    path = _config_dir() / "config.toml"
    if not path.exists():
        return cfg
    import tomllib
    with open(path, "rb") as f:
        data = tomllib.load(f)
    cfg.subs_language = data.get("subs_language", cfg.subs_language)
    cfg.download_dir = data.get("download", cfg.download_dir)
    return cfg


def merge_args(cfg: Config, args) -> Config:
    if getattr(args, "quality", None) is not None:
        cfg.quality = args.quality
    return cfg
