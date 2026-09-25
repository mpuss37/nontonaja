from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import load_config
from ..http import get_client, request_with_retry

_BASE_URL = "https://tv12.lk21official.cc"
_P2P_API = "https://cloud.hownetwork.xyz/api2.php"


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
    slug: str = ""
    seasons: int = 0


@dataclass
class StreamResult:
    url: str
    subtitles: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    source: str = ""


def _base_url() -> str:
    cfg = load_config()
    return cfg.mirrors.get("lk21", _BASE_URL)


def _client():
    cfg = load_config()
    return get_client(proxy=cfg.proxy, name="lk21")


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
        id=slug,
        title=title,
        year=year,
        image=image,
        media_type=media_type,
        rating=rating,
        genre=genre,
    )


def browse(page: str = "populer") -> list[LK21Result]:
    cfg = load_config()
    try:
        resp = request_with_retry("GET", f"{_base_url()}/{page}", proxy=cfg.proxy)
    except httpx.ConnectError:
        return []
    if not resp:
        return []
    soup = _soup(resp.text)

    results = []
    for article in soup.select("article"):
        result = _parse_article(article)
        if result:
            results.append(result)
    return results


def search(query: str) -> list[LK21Result]:
    cfg = load_config()
    base = _base_url()
    client = _client()
    try:
        resp = request_with_retry(
            "GET",
            f"{base}/search",
            params={"s": query},
            proxy=cfg.proxy,
            timeout=10,
            min_delay=0.5,
            max_retries=2,
        )
        if not resp or resp.status_code != 200:
            return _search_browse(query)
        soup = _soup(resp.text)
        body = soup.select_one("body")
        api_base = body.get("data-search_url", "") if body else ""
        if not api_base:
            return _search_browse(query)

        api_resp = client.get(
            f"{api_base.rstrip('/')}/search.php",
            params={"s": query, "page": 1},
            headers={
                "Referer": f"{base}/search?s={query.replace(' ', '+')}",
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
                slug=item["slug"],
            )
            for item in items
            if item.get("slug")
        ]
    except httpx.ConnectError:
        return []
    except Exception:
        return _search_browse(query)


def _search_browse(query: str) -> list[LK21Result]:
    query_words = set(query.lower().split())
    all_results = browse("populer") + browse("latest")

    seen = set()
    results = []
    for r in all_results:
        title_lower = r.title.lower()
        title_words = set(title_lower.split())
        # Match if any query word appears in title, or substring match
        if (query_words & title_words) or query.lower() in title_lower:
            if r.id not in seen:
                seen.add(r.id)
                results.append(r)
    return results


def episode_counts(slug: str) -> dict[int, int]:
    """Return {season_number: max_episode} for a drama slug by scraping its page."""
    cfg = load_config()
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    m = re.match(r"^(.*)-(\d{4})$", slug)
    base_slug = m.group(1) if m else slug
    year = m.group(2) if m else ""
    url = f"https://dramamu.lk21.de/{base_slug}" + (f"-{year}" if year else "")
    r = request_with_retry("GET", url, headers={"User-Agent": ua}, proxy=cfg.proxy)
    if not r or r.status_code != 200:
        return {}
    counts: dict[int, int] = {}
    # episode links look like .../the-100-season-3-episode-16-2014
    for s, e in re.findall(r"season-(\d+)-episode-(\d+)", r.text):
        si, ei = int(s), int(e)
        counts[si] = max(counts.get(si, 0), ei)
    return counts


def get_p2p_stream(
    slug: str,
    media_type: str = "movie",
    season: int = 1,
    episode: int = 1,
) -> StreamResult | None:
    cfg = load_config()
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

    # TV series live on the drama subdomain with a season/episode slug
    # (e.g. dramamu.lk21.de/the-100-season-1-episode-1-2014). The year suffix
    # from the base slug moves to the end of the episode slug.
    if media_type and media_type != "movie":
        m = re.match(r"^(.*)-(\d{4})$", slug)
        base_slug = m.group(1) if m else slug
        year = f"-{m.group(2)}" if m else ""
        ep_slug = f"{base_slug}-season-{season}-episode-{episode}{year}"
        candidates = [f"https://dramamu.lk21.de/{ep_slug}"]
    else:
        candidates = [f"{_base_url()}/{slug}"]

    resp = None
    page_url = candidates[0]
    for url in candidates:
        r = request_with_retry("GET", url, headers={"User-Agent": ua}, proxy=cfg.proxy)
        if r and r.status_code == 200 and "main-player" in r.text:
            resp = r
            page_url = url
            break

    if not resp:
        return None

    html = resp.text
    player_urls = re.findall(r'data-url="([^"]+)"', html)
    if not player_urls:
        return None

    client = _client()
    for purl in player_urls:
        if "videonode" in purl or "p2p" in purl:
            try:
                stream_res = _call_playcdn_api(client, purl, page_url, ua)
                if stream_res:
                    return stream_res
            except Exception:
                pass

    for purl in player_urls:
        vid = None
        match = re.search(r"hownetwork\.xyz/video\.php\?id=([^&\s]+)", purl)
        if match:
            vid = match.group(1)
        match2 = re.search(r"playeriframe\.sbs/iframe/p2p/([^/\s]+)", purl)
        if match2:
            vid = match2.group(1)
        if vid:
            res = _call_p2p_api(client, vid)
            if res:
                return res

    return None


def _call_playcdn_api(client, purl: str, referer: str, ua: str) -> StreamResult | None:
    # videonode exposes /api.php to resolve an iframe URL into a playcdn embed
    vnode_resp = client.get(purl, headers={"Referer": referer, "User-Agent": ua})
    if vnode_resp.status_code != 200:
        return None

    # Extract host + id from purl (e.g. https://videonode.de/iframe3/p2p/X1mjaSZ9...)
    host_match = re.search(r"videonode\.de/iframe3/([^/]+)/([^/?\s]+)", purl)
    if not host_match:
        return None
    host = host_match.group(1)
    vid = host_match.group(2)

    api_resp = client.post(
        "https://videonode.de/api.php",
        data={"host": host, "id": vid},
        headers={
            "Referer": purl,
            "User-Agent": ua,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    if api_resp.status_code != 200:
        return None

    try:
        embed_url = api_resp.json().get("embedUrl")
    except Exception:
        return None
    if not embed_url:
        return None

    # playcdn embed URL is https://playcdn.de/<SLUG>; the stream JSON comes from
    # GET https://playcdn.de/verify/<SLUG> (the old POST verify.php is gone)
    slug = urlparse(embed_url).path.strip("/").split("/")[-1]
    if not slug:
        return None

    verify_resp = client.get(
        f"https://playcdn.de/verify/{slug}",
        headers={"Referer": embed_url, "User-Agent": ua},
    )
    if verify_resp.status_code == 200:
        try:
            res_json = verify_resp.json()
        except Exception:
            return None
        if res_json.get("status") == "success" and res_json.get("fileUrl"):
            return StreamResult(
                url=res_json["fileUrl"],
                headers={"Referer": "https://playcdn.de/", "User-Agent": ua},
                source="lk21",
            )

    return None


def _call_p2p_api(client, vid: str) -> StreamResult | None:
    referer = f"{_base_url()}/"
    try:
        resp = client.post(
            _P2P_API,
            params={"id": vid},
            data={"r": referer, "d": "tv12.lk21official.cc"},
            headers={"Referer": referer, "Origin": _base_url()},
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
