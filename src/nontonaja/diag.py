from __future__ import annotations

import socket

import httpx

from .config import load_config
from .hosts import _DOMAIN_IPS, _doh_resolve, _original_getaddrinfo

_DOMAINS = [
    ("flixhq.ws", "https://flixhq.ws", "FlixHQ"),
    ("tv12.lk21official.cc", "https://tv12.lk21official.cc", "LK21"),
    ("z2.idlixku.com", "https://z2.idlixku.com/api/search?q=naruto", "IDLIX API"),
]


def _resolve_doh(domain: str) -> str | None:
    """Resolve domain using DNS-over-HTTPS."""
    return _doh_resolve(domain)


_BLOCKED_STATUSES = {401, 403, 407, 429, 451, 503}


def _test_http(url: str, timeout: float = 8.0, proxy: str | None = None) -> tuple[str, str]:
    """Test HTTP connectivity. Returns (status, detail).

    HTTP 4xx/5xx is reported as BLOCKED (not OK): the host responded but
    refused the request, which is what an ISP/Cloudflare block looks like.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    }
    kwargs: dict = {"timeout": timeout, "verify": False, "follow_redirects": True, "headers": headers}
    if proxy:
        kwargs["proxy"] = proxy
    try:
        resp = httpx.get(url, **kwargs)
        if resp.status_code in _BLOCKED_STATUSES:
            return (
                f"HTTP {resp.status_code}",
                f"BLOCKED ({len(resp.text)} bytes) - server menolak request",
            )
        if resp.status_code >= 400:
            return f"HTTP {resp.status_code}", f"ERROR ({len(resp.text)} bytes)"
        return f"HTTP {resp.status_code}", f"OK ({len(resp.text)} bytes)"
    except httpx.ConnectTimeout:
        return "TIMEOUT", "Connection timed out"
    except httpx.ConnectError as e:
        return "CONN_ERR", str(e)[:80]
    except httpx.SSLError as e:
        return "SSL_ERR", str(e)[:80]
    except Exception as e:
        return "ERROR", f"{type(e).__name__}: {str(e)[:60]}"


def _test_proxy(proxy: str) -> tuple[str, str]:
    """Test proxy connectivity. Returns (status, detail)."""
    try:
        resp = httpx.get(
            "https://httpbin.org/ip",
            proxy=proxy,
            timeout=10,
            verify=False,
        )
        if resp.status_code == 200:
            ip = resp.json().get("origin", "unknown")
            return "OK", f"Your IP via proxy: {ip}"
        return f"HTTP {resp.status_code}", "Unexpected response"
    except Exception as e:
        return "FAIL", str(e)[:80]


def run_diagnostics() -> None:
    """Run full connectivity diagnostics."""
    config = load_config()

    print("=" * 70)
    print("  NONTONAJA CONNECTIVITY DIAGNOSTICS")
    print("=" * 70)

    # --- Section 1: IP Resolution ---
    print("\n1. DNS RESOLUTION")
    print("-" * 70)
    print(f"  {'Domain':<30} {'Hardcoded IP':<18} {'DoH IP':<18} {'Match'}")
    print(f"  {'─' * 30} {'─' * 18} {'─' * 18} {'─' * 8}")

    for domain, _, _ in _DOMAINS:
        hardcoded = _DOMAIN_IPS.get(domain, ["?"])[0]
        doh_ip = _resolve_doh(domain)
        doh_str = doh_ip or "(failed)"
        if doh_ip:
            match = "OK" if doh_ip == hardcoded else "STALE"
        else:
            match = "FAIL"
        print(f"  {domain:<30} {hardcoded:<18} {doh_str:<18} {match}")

    # --- Section 2: HTTP Connectivity ---
    print("\n2. HTTP CONNECTIVITY")
    print("-" * 70)
    if config.proxy:
        print(f"  (via proxy: {config.proxy})")
    print(f"  {'Site':<20} {'Status':<12} {'Detail'}")
    print(f"  {'─' * 20} {'─' * 12} {'─' * 35}")

    http_results: list[tuple[str, str, str, str]] = []
    for domain, url, label in _DOMAINS:
        status, detail = _test_http(url, proxy=config.proxy)
        http_results.append((domain, status, detail, label))
        print(f"  {label:<20} {status:<12} {detail}")

    # --- Section 3: Proxy ---
    print("\n3. PROXY CONFIGURATION")
    print("-" * 70)
    if config.proxy:
        print(f"  Proxy: {config.proxy}")
        status, detail = _test_proxy(config.proxy)
        print(f"  Status: {status} - {detail}")
    else:
        print("  No proxy configured.")
        print("  To set proxy, edit ~/.config/nontonaja/config.toml:")
        print('    proxy = "socks5://127.0.0.1:1080"')

    # --- Section 4: Mirrors ---
    if config.mirrors:
        print("\n4. MIRROR OVERRIDES")
        print("-" * 70)
        for provider, url in config.mirrors.items():
            print(f"  {provider}: {url}")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    issues = []
    blocked = False
    unreachable = False
    for domain, status, detail, label in http_results:
        if detail.startswith("BLOCKED"):
            blocked = True
            issues.append(f"{label} ({domain}) - {status} (request ditolak server)")
        elif status.startswith(("TIMEOUT", "CONN_ERR")):
            unreachable = True
            issues.append(f"{label} ({domain}) - {status}")
        doh_ip = _resolve_doh(domain)
        if doh_ip and doh_ip != _DOMAIN_IPS.get(domain, ["?"])[0]:
            issues.append(
                f"{label} ({domain}) - IP changed: {_DOMAIN_IPS.get(domain, ['?'])[0]} -> {doh_ip}"
            )

    if issues:
        print("  Issues found:")
        for issue in issues:
            print(f"    - {issue}")
        print("\n  Suggestions:")
        if blocked:
            if config.proxy:
                print("    - Situs menjawab 403/blocked lewat proxy. Coba proxy lain / VPN penuh.")
            else:
                print("    - Situs menjawab 403 (diblokir ISP/Cloudflare).")
                print("      Set a proxy in ~/.config/nontonaja/config.toml:")
                print('      proxy = "socks5://127.0.0.1:1080"')
                print("      lalu jalankan ulang 'nontonaja --diag' untuk verifikasi.")
        if unreachable:
            print("    - Sites are unreachable. Try setting up a proxy:")
            print('      Edit ~/.config/nontonaja/config.toml: proxy = "socks5://127.0.0.1:1080"')
        if any("IP changed" in i for i in issues):
            print("    - Hardcoded IPs are stale. Restart nontonaja to auto-refresh.")
    else:
        print("  All checks passed. If search still fails, try:")
        print("    - Setting up a proxy")
        print("    - Adding [mirrors] in config.toml")

    print()
