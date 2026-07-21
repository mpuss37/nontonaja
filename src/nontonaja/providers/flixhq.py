from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://flixhq.ws"


@dataclass
class SearchResult:
    id: str
    title: str
    year: str
    image: str
    media_type: str
    duration: str = ""
    source: str = "flixhq"


@dataclass
class StreamResult:
    url: str
    subtitles: list[str] = field(default_factory=list)


_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(verify=False, follow_redirects=True, timeout=30)
    return _client


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _extract_id(href: str) -> str:
    href = href.rstrip("/")
    if href.startswith("http"):
        from urllib.parse import urlparse
        return urlparse(href).path.strip("/")
    return href


def search(query: str) -> list[SearchResult]:
    client = _get_client()
    resp = client.get(f"{BASE_URL}/search/{query.replace(' ', '-')}")
    soup = _soup(resp.text)

    results = []
    for item in soup.select("div.film-poster"):
        a = item.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        media_id = _extract_id(href)
        img = item.find("img")
        image = img.get("data-src") or img.get("src", "") if img else ""
        results.append(
            SearchResult(
                id=media_id,
                title=a.get("title", ""),
                year="",
                image=image,
                media_type="tv" if "/series/" in href else "movie",
            )
        )

    detail_items = soup.select("div.film-detail")
    for i, item in enumerate(detail_items):
        if i >= len(results):
            break
        heading = item.find("h3", class_="film-name") or item.find("h2", class_="film-name")
        if heading:
            a_tag = heading.find("a")
            if a_tag:
                results[i].title = a_tag.get("title", a_tag.text.strip())
        spans = item.select("div.fd-infor > span.fdi-item")
        if spans:
            results[i].year = spans[0].text.strip()
        if len(spans) >= 3:
            results[i].duration = spans[2].text.strip()

    return results


def get_stream(media_id: str) -> StreamResult | None:
    """Get stream URL from a movie page."""
    client = _get_client()
    resp = client.get(f"{BASE_URL}/{media_id}")

    pl_match = re.search(r"const pl_url = '([^']+)'", resp.text)
    if not pl_match:
        return None

    pl_url = pl_match.group(1)
    resp = client.get(pl_url)
    soup = _soup(resp.text)

    server_links = soup.select("ul > li > a[data-id]")
    if not server_links:
        return None

    chosen = None
    for a in server_links:
        data_id = a.get("data-id", "")
        if "subdrc" in data_id:
            chosen = a
            break

    if not chosen:
        chosen = server_links[0]

    embed_url = chosen.get("data-id", "")
    if not embed_url:
        return None

    resp = client.get(embed_url)
    m3u8_match = re.search(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*", resp.text)
    if not m3u8_match:
        return None

    subtitles = list(set(
        re.findall(r"https?://srt\.[^\s\"'<>]+\.vtt[^\s\"'<>]*", resp.text)
    ))

    return StreamResult(url=m3u8_match.group(0), subtitles=subtitles)
