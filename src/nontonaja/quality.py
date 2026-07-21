from __future__ import annotations

import re
from dataclasses import dataclass

import httpx


@dataclass
class StreamQuality:
    url: str
    height: int
    bandwidth: int


def parse_m3u8(content: str) -> list[StreamQuality]:
    qualities = []
    lines = content.strip().splitlines()
    for i, line in enumerate(lines):
        match = re.match(
            r"#EXT-X-STREAM-INF:.*BANDWIDTH=(\d+).*RESOLUTION=\d+x(\d+)", line
        )
        if match:
            bandwidth = int(match.group(1))
            height = int(match.group(2))
            if i + 1 < len(lines):
                url = lines[i + 1].strip()
                qualities.append(StreamQuality(url=url, height=height, bandwidth=bandwidth))

    qualities.sort(key=lambda q: q.height, reverse=True)
    return qualities


def select_quality(url: str, preferred: int | None = None, headers: dict | None = None) -> str:
    client = httpx.Client(verify=False, follow_redirects=True)
    resp = client.get(url, headers=headers or {})
    qualities = parse_m3u8(resp.text)

    if not qualities:
        return url

    if preferred:
        for q in qualities:
            if q.height == preferred:
                return q.url

    return qualities[0].url
