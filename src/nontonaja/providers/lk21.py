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
    """Search via JSON API, fallback to browse pages."""
    client = _get_client()
    try:
        # Get API base URL from search page
        resp = client.get(f"{BASE_URL}/search", params={"s": query})
        if resp.status_code != 200:
            return _search_browse(query)
        soup = _soup(resp.text)
        body = soup.select_one("body")
        api_base = body.get("data-search_url", "") if body else ""
        if not api_base:
            return _search_browse(query)

        # Call JSON API
        api_resp = client.get(
            f"{api_base.rstrip('/')}/search.php",
            params={"s": query, "page": 1},
            headers={
                "Referer": f"{BASE_URL}/search?s={query.replace(' ', '+')}",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
        if api_resp.status_code != 200:
            return _search_browse(query)

        data = api_resp.json()
        items = data.get("data", [])
        return [
            LK21Result(
                id=item["slug"],
                title=item["title"],
                year=str(item.get("year", "")),
                image="",
                media_type="tv" if item.get("type") == "series" else "movie",
            )
            for item in items
            if item.get("slug")
        ]
    except Exception:
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
    """Get P2P stream."""
    client = _get_client()
    resp = client.get(
        f"{BASE_URL}/{slug}",
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"}
    )

    if resp.status_code != 200:
        return None

    html = resp.text
    if '<title>Lk21 - Nonton Film' in html and "main-player" not in html:
        return None

    player_urls = re.findall(r'data-url="([^"]+)"', html)
    if not player_urls:
        return None

    # Try new videonode -> playcdn -> verify.php flow first
    for purl in player_urls:
        if "videonode" in purl or "p2p" in purl:
            try:
                stream_res = _call_playcdn_api(purl, f"{BASE_URL}/{slug}")
                if stream_res:
                    return stream_res
            except Exception:
                pass

    # Legacy fallback for older links
    for purl in player_urls:
        vid = None
        match = re.search(r"hownetwork\.xyz/video\.php\?id=([^&\s]+)", purl)
        if match:
            vid = match.group(1)
        match2 = re.search(r"playeriframe\.sbs/iframe/p2p/([^/\s]+)", purl)
        if match2:
            vid = match2.group(1)
        if vid:
            res = _call_p2p_api(vid)
            if res:
                return res

    return None


def _call_playcdn_api(purl: str, referer: str) -> StreamResult | None:
    client = _get_client()
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    vnode_resp = client.get(purl, headers={"Referer": referer, "User-Agent": ua})
    if vnode_resp.status_code != 200:
        return None

    playcdn_urls = re.findall(r'<iframe[^>]+src="([^"]+playcdn[^"]+)"', vnode_resp.text)
    if not playcdn_urls:
        playcdn_urls = re.findall(r'https?://playcdn\.de/[^\s"\'<>]+', vnode_resp.text)
    if not playcdn_urls:
        return None

    import json
    playcdn_url = playcdn_urls[0].replace("&amp;", "&")
    pcdn_resp = client.get(playcdn_url, headers={"Referer": purl, "User-Agent": ua})
    if pcdn_resp.status_code != 200:
        return None

    token_match = re.search(r'var\s+data\s*=\s*(\{.*?\});', pcdn_resp.text)
    if not token_match:
        return None

    try:
        data = json.loads(token_match.group(1))
        verify_resp = client.post(
            "https://playcdn.de/verify.php",
            json={"token": data["token"], "is_ios": False},
            headers={
                "Referer": playcdn_url,
                "Origin": "https://playcdn.de",
                "Content-Type": "application/json",
                "User-Agent": ua,
            },
        )
        if verify_resp.status_code == 200:
            res_json = verify_resp.json()
            if res_json.get("status") == "success" and res_json.get("fileUrl"):
                return StreamResult(
                    url=res_json["fileUrl"],
                    headers={"Referer": "https://playcdn.de/", "User-Agent": ua},
                    source="lk21",
                )
    except Exception:
        pass

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
