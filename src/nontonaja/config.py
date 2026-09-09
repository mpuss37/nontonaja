from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import tomllib


@dataclass
class Config:
    quality: int | None = None
    subs_language: str = "English"
    download_dir: str | None = None
    proxy: str | None = None
    mirrors: dict[str, str] = field(default_factory=dict)


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(xdg).expanduser() / "nontonaja"


def load_config() -> Config:
    cfg = Config()
    path = _config_dir() / "config.toml"
    if not path.exists():
        return _cfg_with_env(cfg)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    cfg.subs_language = data.get("subs_language", cfg.subs_language)
    cfg.download_dir = data.get("download", cfg.download_dir)
    cfg.proxy = data.get("proxy", cfg.proxy)
    cfg.mirrors = data.get("mirrors", cfg.mirrors)
    return _cfg_with_env(cfg)


def _cfg_with_env(cfg: Config) -> Config:
    if not cfg.proxy:
        cfg.proxy = os.environ.get("NONTONAJA_PROXY") or os.environ.get("ALL_PROXY")
    return cfg


def load_hosts() -> dict[str, list[str]]:
    path = _config_dir() / "hosts.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def merge_args(cfg: Config, args) -> Config:
    if getattr(args, "quality", None) is not None:
        cfg.quality = args.quality
    return cfg
