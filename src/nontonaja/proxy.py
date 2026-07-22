"""Local HTTP proxy to rewrite IDLIX HLS segments with .mp4 extensions.

IDLIX CDN serves CMAF segments with obfuscated extensions (.jpg, .css, .js).
ffmpeg rejects these extensions. This proxy rewrites the m3u8 to point to
localhost with .mp4 extensions, then proxies the actual CDN content.
"""

from __future__ import annotations

import re
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import httpx

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
            self._serve_url(url)
        else:
            self.send_error(404)

    def _serve_playlist(self):
        data = self.server.playlist_data.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_url(self, url: str | None):
        if not url:
            self.send_error(404)
            return
        try:
            r = self.server.httpx_client.get(url, timeout=30)
            self.send_response(r.status_code)
            ct = r.headers.get("content-type", "video/mp4")
            if "video" not in ct:
                ct = "video/mp4"
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(r.content)))
            self.end_headers()
            self.wfile.write(r.content)
        except Exception:
            self.send_error(502)

    def log_message(self, *args):
        pass


def _rewrite_m3u8(text: str, port: int) -> tuple[str, str, dict[int, str]]:
    """Rewrite m3u8: CDN URLs -> localhost proxy with .mp4 extensions.

    Returns (rewritten_m3u8, init_url, {index: segment_url}).
    """
    init_url = ""
    seg_map: dict[int, str] = {}
    new_lines: list[str] = []

    for line in text.split("\n"):
        if "#EXT-X-MAP:" in line and "URI=" in line:
            m = re.search(r'URI="([^"]+)"', line)
            if m:
                init_url = m.group(1)
                new_lines.append(f'#EXT-X-MAP:URI="http://127.0.0.1:{port}/init.mp4"')
            else:
                new_lines.append(line)
        elif line.startswith("http"):
            idx = len(seg_map)
            seg_map[idx] = line.strip()
            new_lines.append(f"http://127.0.0.1:{port}/seg/{idx}.ts")
        else:
            new_lines.append(line)

    return "\n".join(new_lines), init_url, seg_map


class ProxyServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, address, handler, playlist: str, init_url: str, seg_map: dict):
        super().__init__(address, handler)
        self.playlist_data = playlist
        self.init_url = init_url
        self.seg_map = seg_map
        self.httpx_client = httpx.Client(verify=False, follow_redirects=True, timeout=30)


def start_proxy(master_url: str) -> tuple[str, ProxyServer]:
    """Start proxy for an IDLIX HLS stream.

    Returns (proxy_playlist_url, server_instance).
    """
    client = httpx.Client(verify=False, follow_redirects=True, timeout=15)

    # Fetch playlist
    resp = client.get(master_url)
    playlist_text = resp.text

    # Check if this is a master playlist (has #EXT-X-STREAM-INF) or sub-playlist
    if "#EXT-X-STREAM-INF" in playlist_text:
        # Master playlist — find highest quality sub-playlist
        from urllib.parse import urljoin
        import re as _re
        lines = playlist_text.split("\n")
        best_bw = 0
        sub_url = ""
        for i, line in enumerate(lines):
            match = _re.match(r"#EXT-X-STREAM-INF:(.*)", line)
            if match and i + 1 < len(lines):
                bw_match = _re.search(r"BANDWIDTH=(\d+)", match.group(1))
                bw = int(bw_match.group(1)) if bw_match else 0
                candidate = lines[i + 1].strip()
                if candidate and not candidate.startswith("#") and bw > best_bw:
                    best_bw = bw
                    sub_url = urljoin(master_url, candidate)

        if not sub_url:
            raise ValueError("No sub-playlist found in master m3u8")

        # Fetch sub-playlist
        resp2 = client.get(sub_url)
        sub_text = resp2.text
    else:
        # Already a sub-playlist
        sub_text = playlist_text

    # Rewrite
    server = ProxyServer(("127.0.0.1", _PORT), _Handler, "", "", {})
    port = server.server_address[1]

    rewritten, init_url, seg_map = _rewrite_m3u8(sub_text, port)
    server.playlist_data = rewritten
    server.init_url = init_url
    server.seg_map = seg_map

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    proxy_url = f"http://127.0.0.1:{port}/playlist.m3u8"
    return proxy_url, server
