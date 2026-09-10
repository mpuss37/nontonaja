from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from .http import get_client, request_with_retry


@dataclass
class StreamQuality:
    url: str
    height: int
    bandwidth: int


def _estimate_height(bandwidth: int) -> int:
    # ponytail: coarse H.264 bitrate->height mapping; accurate enough for variant picking,
    # replace by probing media playlists if wrong picks show up
    if bandwidth >= 2_000_000:
        return 1080
    if bandwidth >= 900_000:
        return 720
    if bandwidth >= 500_000:
        return 480
    if bandwidth >= 300_000:
        return 360
    return 240


def parse_m3u8(content: str, base_url: str = "") -> list[StreamQuality]:
    qualities = []
    lines = content.strip().splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"#EXT-X-STREAM-INF:(.*)", line)
        if match:
            attrs = match.group(1)
            bw_match = re.search(r"BANDWIDTH=(\d+)", attrs)
            res_match = re.search(r"RESOLUTION=\d+x(\d+)", attrs)
            bandwidth = int(bw_match.group(1)) if bw_match else 0
            if res_match:
                height = int(res_match.group(1))
            elif bandwidth > 0:
                height = _estimate_height(bandwidth)
            else:
                height = 0
            if i + 1 < len(lines):
                url = lines[i + 1].strip()
                if base_url and not url.startswith("http"):
                    url = urljoin(base_url, url)
                qualities.append(StreamQuality(url=url, height=height, bandwidth=bandwidth))

    if qualities and qualities[0].height > 0:
        qualities.sort(key=lambda q: q.height, reverse=True)
    else:
        qualities.sort(key=lambda q: q.bandwidth, reverse=True)
    return qualities


def pick_variant(qualities: list[StreamQuality], preferred: int | None = None) -> StreamQuality:
    """Pick variant for preferred height: exact match, else closest (tie -> higher)."""
    if preferred:
        for q in qualities:
            if q.height == preferred:
                return q
        # closest by absolute diff; tie -> higher bandwidth/height
        best = min(qualities, key=lambda q: (abs(q.height - preferred), -q.bandwidth))
        return best
    return qualities[0]


def select_quality(url: str, preferred: int | None = None, headers: dict | None = None) -> str:
    resp = request_with_retry("GET", url, headers=headers or {})
    if not resp:
        return url
    qualities = parse_m3u8(resp.text, base_url=url)

    if not qualities:
        return url

    return pick_variant(qualities, preferred).url
