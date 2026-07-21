from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx


@dataclass
class StreamQuality:
    url: str
    height: int
    bandwidth: int


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
            height = int(res_match.group(1)) if res_match else 0
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


def select_quality(url: str, preferred: int | None = None, headers: dict | None = None) -> str:
    client = httpx.Client(verify=False, follow_redirects=True)
    resp = client.get(url, headers=headers or {})
    qualities = parse_m3u8(resp.text, base_url=url)

    if not qualities:
        return url

    if preferred:
        for q in qualities:
            if q.height == preferred:
                return q.url

    return qualities[0].url
