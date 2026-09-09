from __future__ import annotations

import socket
import httpx

_DOH_SERVERS = [
    ("https://1.1.1.1/dns-query", "cloudflare-dns.com"),
    ("https://1.0.0.1/dns-query", "cloudflare-dns.com"),
    ("https://8.8.8.8/dns-query", "dns.google"),
    ("https://8.8.4.4/dns-query", "dns.google"),
]

_bypass_hosts = {"1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4"}
_original_getaddrinfo = socket.getaddrinfo
_cache: dict[str, str] = {}


def _doh_resolve(domain: str) -> str | None:
    if domain in _cache:
        return _cache[domain]
    for url, host in _DOH_SERVERS:
        try:
            resp = httpx.get(
                f"{url}?name={domain}&type=A",
                headers={"Accept": "application/dns-json"},
                timeout=5,
                verify=False,
            )
            if resp.status_code == 200:
                data = resp.json()
                for answer in data.get("Answer", []):
                    if answer.get("type") == 1:
                        ip = answer.get("data")
                        if ip:
                            _cache[domain] = ip
                            return ip
        except Exception:
            continue
    return None


def _patched_getaddrinfo(host, port=0, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and host not in _bypass_hosts:
        try:
            import ipaddress
            ipaddress.ip_address(host)
            return _original_getaddrinfo(host, port, family, type, proto, flags)
        except ValueError:
            pass
        ip = _doh_resolve(host)
        if ip:
            return _original_getaddrinfo(ip, port, family, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)


def install() -> None:
    socket.getaddrinfo = _patched_getaddrinfo


def uninstall() -> None:
    socket.getaddrinfo = _original_getaddrinfo
