from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlayerConfig:
    name: str = "mpv"
    download_dir: str | None = None
    provider: str = "Vidcloud"
    subs_language: str = "English"
    history: bool = False
    no_subs: bool = False
    quality: int | None = None
    debug: bool = False
    use_rofi: bool = False


def _config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "~"))
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "~/.config")
        base = Path(xdg)
    return base / "nontonaja"


def load_config() -> PlayerConfig:
    cfg = PlayerConfig()
    path = _config_dir() / "config.toml"
    if not path.exists():
        return cfg

    import tomllib

    with open(path, "rb") as f:
        data = tomllib.load(f)

    cfg.name = data.get("player", cfg.name)
    cfg.download_dir = data.get("download", cfg.download_dir)
    cfg.provider = data.get("provider", cfg.provider)
    cfg.subs_language = data.get("subs_language", cfg.subs_language)
    cfg.history = data.get("history", cfg.history)
    cfg.no_subs = data.get("no_subs", cfg.no_subs)
    cfg.debug = data.get("debug", cfg.debug)
    cfg.use_rofi = data.get("use_external_menu", cfg.use_rofi)
    return cfg


def merge_args(cfg: PlayerConfig, args) -> PlayerConfig:
    if getattr(args, "player", None):
        cfg.name = args.player
    if getattr(args, "provider", None):
        cfg.provider = args.provider
    if getattr(args, "quality", None) is not None:
        cfg.quality = args.quality
    if getattr(args, "language", None):
        cfg.subs_language = args.language
    if getattr(args, "no_subs", False):
        cfg.no_subs = True
    if getattr(args, "download", None) is not None:
        cfg.download_dir = args.download
    if getattr(args, "debug", False):
        cfg.debug = True
    if getattr(args, "rofi", False):
        cfg.use_rofi = True
    if getattr(args, "continue_watching", False):
        cfg.history = True
    return cfg
