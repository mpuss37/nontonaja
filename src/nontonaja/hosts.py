from __future__ import annotations

import socket
import ipaddress
from typing import Optional

import httpx

_original_getaddrinfo = socket.getaddrinfo

_DOMAIN_IPS: dict[str, list[str]] = {
    "flixhq.ws": ["104.21.81.199", "172.67.146.64"],
    "tv12.lk21official.cc": ["172.67.185.109", "104.21.89.176"],
    "z2.idlixku.com": ["104.26.5.185", "172.67.73.54"],
    "playcdn.de": ["104.26.5.185", "172.67.73.54"],
    "cloud.hownetwork.xyz": ["104.26.5.185", "172.67.73.54"],
}

_DOH_SERVERS = [
    ("https://1.1.1.1/dns-query", "cloudflare-dns.com"),
    ("https://8.8.8.8/dns-query", "dns.google"),
]

_bypass_hosts = {"1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4"}
_doh_cache: dict[str, str] = {}


def set_ip(domain: str, ips: list[str]) -> None:
    _DOMAIN_IPS[domain] = ips


def get_ips(domain: str) -> Optional[list[str]]:
    return _DOMAIN_IPS.get(domain)


def _doh_resolve(domain: str) -> Optional[str]:
    if domain in _doh_cache:
        return _doh_cache[domain]
    for url, host in _DOH_SERVERS:
        try:
            resp = httpx.get(
                f"{url}?name={domain}&type=A",
                headers={"Accept": "application/dns-json"},
                timeout=5,
                verify=False,
            )
            if resp.status_code == 200:
                for answer in resp.json().get("Answer", []):
                    if answer.get("type") == 1:
                        ip = answer.get("data")
                        if ip:
                            _doh_cache[domain] = ip
                            return ip
        except Exception:
            continue
    return None


def _patched_getaddrinfo(host, port=0, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and host not in _bypass_hosts:
        # 1. Check hardcoded IPs first
        if host in _DOMAIN_IPS:
            for ip in _DOMAIN_IPS[host]:
                try:
                    ipaddress.ip_address(ip)
                    return _original_getaddrinfo(ip, port, family, type, proto, flags)
                except ValueError:
                    continue
        # 2. Fallback to DoH
        try:
            ipaddress.ip_address(host)
            return _original_getaddrinfo(host, port, family, type, proto, flags)
        except ValueError:
            ip = _doh_resolve(host)
            if ip:
                return _original_getaddrinfo(ip, port, family, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)


def _refresh_ips() -> None:
    """Resolve current IPs via DoH, keep hardcoded as fallback."""
    for domain in list(_DOMAIN_IPS):
        ip = _doh_resolve(domain)
        if ip:
            _DOMAIN_IPS[domain] = [ip]


def install() -> None:
    from .config import load_hosts

    custom_hosts = load_hosts()
    _DOMAIN_IPS.update(custom_hosts)
    _refresh_ips()
    socket.getaddrinfo = _patched_getaddrinfo


def uninstall() -> None:
    socket.getaddrinfo = _original_getaddrinfo
