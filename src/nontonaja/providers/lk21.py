from __future__ import annotations

import re
import asyncio
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://tv12.lk21official.cc"
P2P_API = "https://cloud.hownetwork.xyz/api2.php"
HYDRAX_FAKE_ID = "81347747"


@dataclass
class LK21Result:
    id: str
    title: str
    year: str
    image: str
    media_type: str
    rating: str = ""
    genre: str = ""
    source: str = "lk21"


@dataclass
class StreamResult:
    url: str
    subtitles: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    source: str = ""


_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(verify=False, follow_redirects=True, timeout=30)
    return _client


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _parse_article(article) -> LK21Result | None:
    a = article.find("a", href=True)
    if not a:
        return None

    slug = a["href"].strip("/")
    title_tag = article.select_one("h3.poster-title") or article.select_one("[itemprop='name']")
    title = title_tag.text.strip() if title_tag else ""

    year_tag = article.select_one("span.year")
    year = year_tag.text.strip() if year_tag else ""

    img_tag = article.select_one("img[itemprop='image']") or article.select_one("img")
    image = ""
    if img_tag:
        image = img_tag.get("data-src") or img_tag.get("src", "")

    rating_tag = article.select_one("span.rating")
    rating = rating_tag.text.strip() if rating_tag else ""

    genre_tag = article.select_one("div.genre") or article.select_one("meta[itemprop='genre']")
    genre = ""
    if genre_tag:
        genre = genre_tag.text.strip() if genre_tag.name != "meta" else genre_tag.get("content", "")

    is_series = bool(article.select_one("span.episode"))
    media_type = "tv" if is_series else "movie"

    return LK21Result(
        id=slug, title=title, year=year, image=image,
        media_type=media_type, rating=rating, genre=genre,
    )


def browse(page: str = "populer") -> list[LK21Result]:
    client = _get_client()
    resp = client.get(f"{BASE_URL}/{page}")
    soup = _soup(resp.text)

    results = []
    for article in soup.select("article"):
        result = _parse_article(article)
        if result:
            results.append(result)
    return results


def search(query: str) -> list[LK21Result]:
    """Search LK21 via playwright (JS-rendered search page)."""
    from .browser import run_async, _get_browser

    async def _search():
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            url = f"{BASE_URL}/search?s={query.replace(' ', '+')}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            try:
                await page.wait_for_selector("#results article", timeout=10000)
            except Exception:
                pass
            await asyncio.sleep(1)

            html = await page.content()
            soup = _soup(html)

            results = []
            for article in soup.select("#results article"):
                result = _parse_article(article)
                if result:
                    results.append(result)
            return results
        finally:
            await page.close()

    return run_async(_search())


def _extract_player_urls(slug: str) -> list[str] | None:
    """Fetch detail page and return all player embed URLs."""
    client = _get_client()
    resp = client.get(f"{BASE_URL}/{slug}")

    if resp.status_code != 200:
        return None

    html = resp.text
    if '<title>Lk21 - Nonton Film' in html and "main-player" not in html:
        return None

    player_urls = re.findall(r'data-url="([^"]+)"', html)
    return player_urls if player_urls else None


def get_p2p_stream(slug: str) -> StreamResult | None:
    """Get P2P stream from LK21 movie."""
    player_urls = _extract_player_urls(slug)
    if not player_urls:
        return None

    for purl in player_urls:
        vid = None
        match = re.search(r"hownetwork\.xyz/video\.php\?id=([^&\s]+)", purl)
        if match:
            vid = match.group(1)
        match2 = re.search(r"playeriframe\.sbs/iframe/p2p/([^/\s]+)", purl)
        if match2:
            vid = match2.group(1)
        if vid:
            return _get_p2p_stream(vid)

    return None


def get_hydrax_stream(slug: str) -> StreamResult | None:
    """Get hydrax stream from LK21 movie by slug.

    1. Fetch detail page → extract hydrax vid
    2. Open abyssplayer.com → wait for JWPlayer
    3. Download via frame fetch → return local file
    """
    player_urls = _extract_player_urls(slug)
    if not player_urls:
        return None

    for purl in player_urls:
        match = re.search(r"hydrax/([^/\s]+)", purl)
        if match:
            result = _get_hydrax_stream_vid(match.group(1))
            if result:
                return result

    return None


def _get_p2p_stream(vid: str) -> StreamResult | None:
    """Call hownetwork API to get HLS stream URL."""
    client = _get_client()

    referer = f"{BASE_URL}/"
    try:
        resp = client.post(
            P2P_API,
            params={"id": vid},
            data={"r": referer, "d": "tv12.lk21official.cc"},
            headers={"Referer": referer, "Origin": BASE_URL},
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        if isinstance(data, dict) and data.get("file"):
            return StreamResult(
                url=data["file"],
                headers={"Referer": "https://cloud.hownetwork.xyz/"},
                source="p2p",
            )
    except Exception:
        pass

    return None


def _get_hydrax_stream_vid(vid: str) -> StreamResult | None:
    """Get stream from hydrax via playwright frame fetch.

    Returns None if hydrax serves fake content (Big Buck Bunny).
    """
    try:
        from .browser import (
            run_async, _get_browser,
            download_via_frame, find_player_frame, get_video_url_from_frame,
        )
    except ImportError:
        return None

    async def _extract():
        browser = await _get_browser()
        page = await browser.new_page()

        try:
            embed_url = f"https://abyssplayer.com/{vid}"
            await page.goto(embed_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(10)

            frame = await find_player_frame(page)
            if not frame:
                return None

            video_url = await get_video_url_from_frame(frame)
            if not video_url:
                return None

            # Check for fake content
            if HYDRAX_FAKE_ID in video_url:
                return None

            # Download to local file via frame fetch
            import tempfile
            import os
            local_path = tempfile.mktemp(suffix=".mp4", prefix="nontonaja-lk21-")
            await download_via_frame(video_url, frame, local_path)

            if os.path.getsize(local_path) < 1024 * 1024:
                os.unlink(local_path)
                return None

            return StreamResult(url=local_path, source="hydrax")

        except Exception:
            return None
        finally:
            await page.close()

    return run_async(_extract())
