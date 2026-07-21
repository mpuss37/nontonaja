from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

API_BASE = "https://z2.idlixku.com/api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
_CACHE_FILE = Path.home() / ".config" / "nontonaja" / "idlix_tokens.json"

_client: httpx.Client | None = None
_renewal_tokens: dict[str, str] = {}


def _load_tokens() -> dict[str, str]:
    global _renewal_tokens
    if _renewal_tokens:
        return _renewal_tokens
    try:
        if _CACHE_FILE.exists():
            _renewal_tokens = json.loads(_CACHE_FILE.read_text())
    except Exception:
        _renewal_tokens = {}
    return _renewal_tokens


def _save_tokens() -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_renewal_tokens))
    except Exception:
        pass


@dataclass
class SearchResult:
    id: str
    title: str
    year: str
    image: str
    media_type: str
    source: str = "idlix"


@dataclass
class StreamResult:
    url: str
    subtitles: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(verify=False, follow_redirects=True, timeout=30)
    return _client


def _headers() -> dict:
    return {"User-Agent": UA, "Content-Type": "application/json"}


def _countdown(seconds: int) -> None:
    for remaining in range(seconds, 0, -1):
        sys.stdout.write(f"\rwaiting {remaining}s for ad... ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\rstream ready!              \n")


def search(query: str) -> list[SearchResult]:
    client = _get_client()
    resp = client.get(f"{API_BASE}/search", params={"q": query}, headers={"User-Agent": UA})
    if resp.status_code != 200:
        return []

    results = []
    for item in resp.json().get("results", []):
        release = item.get("releaseDate", "")
        year = release[:4] if release else ""
        poster = item.get("posterPath", "")
        if poster and not poster.startswith("http"):
            poster = f"https://image.tmdb.org/t/p/w500{poster}"
        results.append(SearchResult(
            id=item["id"], title=item.get("title", ""), year=year,
            image=poster, media_type=item.get("contentType", "movie"),
        ))
    return results


def _claim(content_id: str, content_type: str) -> dict | None:
    client = _get_client()
    h = _headers()

    r = client.get(f"{API_BASE}/watch/play-info/{content_type}/{content_id}", headers=h)
    if r.status_code != 200:
        return None
    gate_token = r.json().get("gateToken")
    if not gate_token:
        return None

    r = client.post(f"{API_BASE}/watch/session/claim", json={"gateToken": gate_token}, headers=h)
    if r.status_code != 200:
        return None
    claim = r.json()

    if claim.get("kind") == "pentos":
        return claim

    wait_s = (claim.get("unlockAt", 0) - claim.get("serverNow", 0)) / 1000
    _countdown(int(max(wait_s, 0)) + 1)

    r = client.post(f"{API_BASE}/watch/session/claim", json={"gateToken": gate_token}, headers=h)
    return r.json() if r.status_code == 200 else None


def _redeem(pentos: dict) -> StreamResult | None:
    client = _get_client()
    r = client.post(
        pentos["redeemUrl"],
        json={"claim": pentos["claim"]},
        headers={**_headers(), "Origin": "https://z2.idlixku.com", "Referer": "https://z2.idlixku.com/"},
    )
    if r.status_code != 200:
        return None
    redeem = r.json()
    m3u8_url = redeem.get("url")
    if not m3u8_url:
        return None
    subtitles = [s["path"] for s in redeem.get("subtitles", []) if s.get("path")]
    return StreamResult(url=m3u8_url, subtitles=subtitles)


def get_stream(content_id: str, content_type: str = "movie") -> StreamResult | None:
    _load_tokens()

    cached = _renewal_tokens.get(content_id)
    if cached:
        r = _get_client().post(f"{API_BASE}/watch/session/refresh-claim", json={"renewalToken": cached}, headers=_headers())
        if r.status_code == 200 and r.json().get("kind") == "pentos":
            pentos = r.json()
            _renewal_tokens[content_id] = pentos.get("renewalToken", cached)
            _save_tokens()
            return _redeem(pentos)

    pentos = _claim(content_id, content_type)
    if not pentos or pentos.get("kind") != "pentos":
        return None

    renewal = pentos.get("renewalToken")
    if renewal:
        _renewal_tokens[content_id] = renewal
        _save_tokens()

    return _redeem(pentos)
