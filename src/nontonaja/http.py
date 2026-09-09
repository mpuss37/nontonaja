from __future__ import annotations

import time
import httpx

_clients: dict[str, httpx.Client] = {}

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
}


def get_client(proxy: str | None = None, name: str = "default") -> httpx.Client:
    key = f"{name}:{proxy or ''}"
    if key not in _clients:
        kwargs: dict = {
            "verify": False,
            "follow_redirects": True,
            "timeout": 30,
            "headers": _DEFAULT_HEADERS,
        }
        if proxy:
            kwargs["proxy"] = proxy
        _clients[key] = httpx.Client(**kwargs)
    return _clients[key]


def request_with_retry(
    method: str,
    url: str,
    *,
    proxy: str | None = None,
    max_retries: int = 3,
    timeout: float = 30,
    min_delay: float = 1.0,
    **kwargs,
) -> httpx.Response | None:
    client = get_client(proxy)
    for attempt in range(max_retries):
        try:
            resp = client.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code < 500:
                return resp
            if attempt < max_retries - 1:
                time.sleep(min_delay * (attempt + 1))
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RequestError):
            if attempt < max_retries - 1:
                time.sleep(min_delay * (attempt + 1))
    return None


def close_all() -> None:
    for c in _clients.values():
        c.close()
    _clients.clear()
