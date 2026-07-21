from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://tv12.lk21official.cc"
P2P_API = "https://cloud.hownetwork.xyz/api2.php"


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
    """Search LK21 via browse pages, filter by query."""
    return _search_browse(query)


def _search_browse(query: str) -> list[LK21Result]:
    """Fallback search: browse populer + latest, filter by query."""
    query_lower = query.lower()
    all_results = browse("populer") + browse("latest")

    seen = set()
    results = []
    for r in all_results:
        if query_lower in r.title.lower() and r.id not in seen:
            seen.add(r.id)
            results.append(r)
    return results


def get_p2p_stream(slug: str) -> StreamResult | None:
    """Get P2P stream from LK21 movie."""
    client = _get_client()
    resp = client.get(f"{BASE_URL}/{slug}")

    if resp.status_code != 200:
        return None

    html = resp.text
    if '<title>Lk21 - Nonton Film' in html and "main-player" not in html:
        return None

    player_urls = re.findall(r'data-url="([^"]+)"', html)
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
            return _call_p2p_api(vid)

    return None


def _call_p2p_api(vid: str) -> StreamResult | None:
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
