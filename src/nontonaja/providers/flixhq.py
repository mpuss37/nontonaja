from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..config import load_config
from ..http import get_client, request_with_retry

_BASE_URL = "https://flixhq.ws"


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


def _base_url() -> str:
    cfg = load_config()
    return cfg.mirrors.get("flixhq", _BASE_URL)


def _client():
    cfg = load_config()
    return get_client(proxy=cfg.proxy, name="flixhq")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _extract_id(href: str) -> str:
    href = href.rstrip("/")
    if href.startswith("http"):
        return urlparse(href).path.strip("/")
    return href


def search(query: str, max_pages: int = 3) -> list[SearchResult]:
    client = _client()
    base_slug = query.strip().replace(" ", "-")
    base = _base_url()
    results = []

    for page in range(1, max_pages + 1):
        url = f"{base}/search/{base_slug}/page/{page}/" if page > 1 else f"{base}/search/{base_slug}"
        resp = request_with_retry("GET", url)
        if not resp or resp.status_code != 200:
            break
        soup = _soup(resp.text)
        posters = soup.select("div.film-poster")
        if not posters:
            break

        page_results = []
        for item in posters:
            a = item.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            media_id = _extract_id(href)
            img = item.find("img")
            image = img.get("data-src") or img.get("src", "") if img else ""
            page_results.append(
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
            if i >= len(page_results):
                break
            heading = item.find("h3", class_="film-name") or item.find("h2", class_="film-name")
            if heading:
                a_tag = heading.find("a")
                if a_tag:
                    page_results[i].title = a_tag.get("title", a_tag.text.strip())
            spans = item.select("div.fd-infor > span.fdi-item")
            if spans:
                page_results[i].year = spans[0].text.strip()
            if len(spans) >= 3:
                page_results[i].duration = spans[2].text.strip()

        results.extend(page_results)
        pagination = soup.select("ul.pagination li")
        if not pagination or page >= len(pagination):
            break

    return results


def get_stream(media_id: str) -> StreamResult | None:
    base = _base_url()
    resp = request_with_retry("GET", f"{base}/{media_id}")
    if not resp:
        return None

    pl_match = re.search(r"const pl_url = '([^']+)'", resp.text)
    if not pl_match:
        return None

    pl_url = pl_match.group(1)
    resp = request_with_retry("GET", pl_url)
    if not resp:
        return None
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

    resp = request_with_retry("GET", embed_url)
    if not resp:
        return None
    m3u8_match = re.search(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*", resp.text)
    if not m3u8_match:
        return None

    subtitles = list(set(
        re.findall(r"https?://srt\.[^\s\"'<>]+\.vtt[^\s\"'<>]*", resp.text)
    ))

    return StreamResult(url=m3u8_match.group(0), subtitles=subtitles)
