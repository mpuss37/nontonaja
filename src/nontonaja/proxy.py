"""Local HTTP proxy to rewrite HLS segments with .mp4 extensions.

CDN serves CMAF segments with obfuscated extensions (.jpg, .css, .js).
ffmpeg rejects these extensions. This proxy rewrites the m3u8 to point to
localhost with .mp4 extensions, then proxies the actual CDN content.
"""

from __future__ import annotations

import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from .config import load_config

_PORT = 0  # auto-assign


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.lstrip("/")
        if path == "playlist.m3u8":
            self._serve_playlist()
        elif path in ("init.mp4", "init.ts"):
            self._serve_url(self.server.init_url)
        elif path.startswith("seg/"):
            try:
                idx = int(path.split("/")[1].split(".")[0])
                url = self.server.seg_map.get(idx)
            except (ValueError, IndexError):
                url = None
                idx = None
            self._serve_url(url, idx)
        else:
            self.send_error(404)

    def _serve_playlist(self):
        # Re-fetch a FRESH playlist on every request so sliding-window HLS
        # playlists continue to advance (prevents player stalling once the
        # initial snapshot runs out).
        data = self.server._build_fresh_playlist()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        # Force no cache for Android players  
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache") 
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_url(self, url: str | None, idx: int | None = None):
        debug = os.environ.get("NONTONAJA_DEBUG_PROXY")
        if not url:
            if debug:
                print(f"[proxy] seg idx={idx} MISSING (no url)", flush=True)
            try:
                self.send_error(404)
            except Exception:
                pass
            return
        try:
            r = self.server.httpx_client.get(url, timeout=30)
            if debug:
                print(
                    f"[proxy] seg idx={idx} upstream={r.status_code} len={len(r.content)}",
                    flush=True,
                )
            # More aggressive refresh on any error
            if r.status_code >= 400 and hasattr(self.server, '_refresh_playlist'):
                self.server._refresh_playlist()
                # Retry with new URL
                if idx is not None:
                    url = self.server.seg_map.get(idx)
                    if url:
                        r = self.server.httpx_client.get(url, timeout=30)
                        if debug:
                            print(
                                f"[proxy] seg idx={idx} retry={r.status_code} len={len(r.content)}",
                                flush=True,
                            )
            
            self.send_response(r.status_code)
            ct = r.headers.get("content-type", "video/mp4")
            if "video" not in ct:
                ct = "video/mp4"
            self.send_header("Content-Type", ct)
            # Add no-cache headers for segments too
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(r.content)))
            self.end_headers()
            self.wfile.write(r.content)
        except Exception as e:
            if debug:
                print(f"[proxy] seg idx={idx} EXC {type(e).__name__}: {e}", flush=True)
            try:
                self.send_error(502)
            except Exception:
                pass

    def log_message(self, *args):
        pass


def _rewrite_m3u8(text: str, port: int) -> tuple[str, str, dict[int, str]]:
    """Rewrite m3u8: CDN URLs -> localhost proxy with .mp4 extensions.

    Segment indices are offset by EXT-X-MEDIA-SEQUENCE so that indices are
    absolute and monotonic across sliding-window refreshes. This lets a player
    that fetched an earlier playlist still resolve seg/N.ts correctly.
    """
    init_url = ""
    seg_map: dict[int, str] = {}
    new_lines: list[str] = []

    # Absolute starting index = media sequence number
    base = 0
    for line in text.split("\n"):
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                base = int(line.split(":")[1].strip())
            except (ValueError, IndexError):
                base = 0
            break

    pos = 0
    for line in text.split("\n"):
        if "#EXT-X-MAP:" in line and "URI=" in line:
            m = re.search(r'URI="([^"]+)"', line)
            if m:
                init_url = m.group(1)
                new_lines.append(f'#EXT-X-MAP:URI="http://127.0.0.1:{port}/init.mp4"')
            else:
                new_lines.append(line)
        elif line.startswith("http"):
            idx = base + pos
            pos += 1
            seg_map[idx] = line.strip()
            new_lines.append(f"http://127.0.0.1:{port}/seg/{idx}.ts")
        else:
            new_lines.append(line)

    return "\n".join(new_lines), init_url, seg_map


class ProxyServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address, handler, playlist: str, init_url: str, seg_map: dict):
        super().__init__(address, handler)
        self.playlist_data = playlist
        self.init_url = init_url
        self.seg_map = seg_map
        self._original_url = None  # Store for refresh
        self._sub_url = None       # Resolved variant (sub) playlist URL
        self._preferred_quality = None
        self._last_refresh = 0  # Timestamp
        cfg = load_config()
        self.httpx_client = httpx.Client(
            verify=False, follow_redirects=True, timeout=30,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            **({"proxy": cfg.proxy} if cfg.proxy else {}),
        )

    def _fetch_sub_text(self) -> str | None:
        """Fetch the current sub-playlist text (resolving master if needed)."""
        if not self._original_url:
            return None
        try:
            # Prefer the already-resolved sub playlist URL (avoids re-parsing
            # the master each time and keeps the same quality).
            if self._sub_url:
                return self.httpx_client.get(self._sub_url).text

            resp = self.httpx_client.get(self._original_url)
            text = resp.text
            if "#EXT-X-STREAM-INF" in text:
                from .quality import parse_m3u8, pick_variant
                qualities = parse_m3u8(text, base_url=self._original_url)
                if qualities:
                    self._sub_url = pick_variant(
                        qualities, self._preferred_quality or 720
                    ).url
                    return self.httpx_client.get(self._sub_url).text
            return text
        except Exception as e:
            if os.environ.get("NONTONAJA_DEBUG_PROXY"):
                print(f"[proxy] _fetch_sub_text FAILED: {type(e).__name__}: {e}", flush=True)
            return None

    def _build_fresh_playlist(self) -> bytes:
        """Re-fetch upstream and rebuild the served playlist with absolute
        (media-sequence based) indices. Falls back to the last known good
        playlist if the upstream fetch fails."""
        sub_text = self._fetch_sub_text()
        if not sub_text:
            return self.playlist_data.encode()

        try:
            rewritten, init_url, seg_map = _rewrite_m3u8(
                sub_text, self.server_address[1]
            )
        except Exception:
            return self.playlist_data.encode()

        # Merge new segments into seg_map (never drop old ones — the player may
        # still request an earlier index). Absolute indices make this safe.
        self.seg_map.update(seg_map)
        if init_url:
            self.init_url = init_url
        self.playlist_data = rewritten
        if os.environ.get("NONTONAJA_DEBUG_PROXY"):
            seqs = sorted(seg_map.keys())
            print(
                f"[proxy] playlist refreshed: {len(seg_map)} segs "
                f"range={seqs[0] if seqs else '-'}..{seqs[-1] if seqs else '-'} "
                f"total_map={len(self.seg_map)}",
                flush=True,
            )
        return rewritten.encode()

    def _refresh_playlist(self):
        """Refresh expired playlist URLs while preserving segment indices."""
        import time
        now = time.time()
        # Throttle refresh to max once per 10 seconds
        if now - self._last_refresh < 10:
            return

        if not self._original_url:
            return
        self._last_refresh = now
        # Delegate to the fresh builder; it merges absolute indices safely.
        self._build_fresh_playlist()


def start_proxy(
    master_url: str, headers: dict | None = None, preferred: int | None = None
) -> tuple[str, ProxyServer]:
    """Start proxy for an HLS stream. preferred = desired height (480/720/1080)."""
    req_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    }
    if headers:
        req_headers.update(headers)
    elif "playcdn.de" in master_url:
        req_headers["Referer"] = "https://playcdn.de/"

    cfg = load_config()
    client = httpx.Client(
        verify=False, follow_redirects=True, timeout=15,
        headers=req_headers,
        **({"proxy": cfg.proxy} if cfg.proxy else {}),
    )

    resp = client.get(master_url)
    playlist_text = resp.text

    sub_url_hint = None
    if "#EXT-X-STREAM-INF" in playlist_text:
        from .quality import parse_m3u8, pick_variant

        qualities = parse_m3u8(playlist_text, base_url=master_url)
        if not qualities:
            raise ValueError("No sub-playlist found in master m3u8")
        sub_url = pick_variant(qualities, preferred).url
        sub_url_hint = sub_url

        resp2 = client.get(sub_url)
        sub_text = resp2.text
    else:
        sub_text = playlist_text

    server = ProxyServer(("127.0.0.1", _PORT), _Handler, "", "", {})
    port = server.server_address[1]
    
    # Store for refresh capability
    server._original_url = master_url
    server._sub_url = sub_url_hint
    server._preferred_quality = preferred

    rewritten, init_url, seg_map = _rewrite_m3u8(sub_text, port)
    server.playlist_data = rewritten
    server.init_url = init_url
    server.seg_map = seg_map

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    proxy_url = f"http://127.0.0.1:{port}/playlist.m3u8"
    return proxy_url, server
