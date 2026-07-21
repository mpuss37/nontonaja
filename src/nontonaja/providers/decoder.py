from __future__ import annotations

import re
import json
from dataclasses import dataclass, field

import httpx


PROXY_URL = "https://dec.eatmynerds.live"


@dataclass
class StreamSource:
    file: str
    label: str = ""
    kind: str = ""
    default: bool = False


@dataclass
class DecodeResult:
    sources: list[str] = field(default_factory=list)
    subtitles: list[StreamSource] = field(default_factory=list)


def decode_via_proxy(url: str) -> DecodeResult | None:
    """Use the external decoder proxy (default method)."""
    client = httpx.Client(verify=False, follow_redirects=True, timeout=30)
    try:
        resp = client.get(f"{PROXY_URL}?url={url}")
        data = resp.json()
    except Exception:
        return None

    sources = [s.get("file", "") for s in data.get("sources", []) if s.get("file")]
    subtitles = [
        StreamSource(
            file=t.get("file", ""),
            label=t.get("label", ""),
            kind=t.get("kind", ""),
            default=t.get("default", False),
        )
        for t in data.get("tracks", [])
    ]

    return DecodeResult(sources=sources, subtitles=subtitles)


def decode_custom(url: str) -> DecodeResult | None:
    """Fallback: try to extract m3u8/mp4 from embed page JS."""
    client = httpx.Client(verify=False, follow_redirects=True, timeout=30)
    try:
        resp = client.get(url)
    except Exception:
        return None

    text = resp.text
    sources = []

    for match in re.finditer(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', text):
        src = match.group(0)
        if src not in sources:
            sources.append(src)

    for match in re.finditer(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', text):
        src = match.group(0)
        if src not in sources:
            sources.append(src)

    if not sources:
        return None

    return DecodeResult(sources=sources)


def decode(url: str) -> DecodeResult | None:
    """Try proxy first, fallback to custom extraction."""
    result = decode_via_proxy(url)
    if result and result.sources:
        return result

    return decode_custom(url)
