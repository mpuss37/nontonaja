from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

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


def _proxy_reachable(proxy: str) -> bool:
    """TCP-check the proxy host:port so a dead proxy doesn't stall every request."""
    try:
        parsed = urlparse(proxy)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return False
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


_proxy_check_cache: dict[str, bool] = {}
_proxy_warned: set[str] = set()


def _validate_proxy(cfg: Config) -> Config:
    if not cfg.proxy:
        return cfg
    if cfg.proxy not in _proxy_check_cache:
        _proxy_check_cache[cfg.proxy] = _proxy_reachable(cfg.proxy)
    if not _proxy_check_cache[cfg.proxy]:
        if cfg.proxy not in _proxy_warned:
            _proxy_warned.add(cfg.proxy)
            print(
                f"Warning: proxy '{cfg.proxy}' tidak aktif, diabaikan. "
                f"Hapus 'proxy' di ~/.config/nontonaja/config.toml atau jalankan proxynya.",
                file=sys.stderr,
            )
        cfg.proxy = None
    return cfg


def load_config() -> Config:
    cfg = Config()
    path = _config_dir() / "config.toml"
    if not path.exists():
        return _validate_proxy(_cfg_with_env(cfg))
    with open(path, "rb") as f:
        data = tomllib.load(f)
    cfg.subs_language = data.get("subs_language", cfg.subs_language)
    cfg.download_dir = data.get("download", cfg.download_dir)
    cfg.proxy = data.get("proxy", cfg.proxy)
    cfg.mirrors = data.get("mirrors", cfg.mirrors)
    return _validate_proxy(_cfg_with_env(cfg))


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
