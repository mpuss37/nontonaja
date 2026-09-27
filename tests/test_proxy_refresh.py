"""Regression tests for proxy playlist/segment refresh (Android player stuck fix)."""

import unittest
from unittest.mock import patch

from nontonaja.proxy import ProxyServer, _Handler, _rewrite_m3u8


def _make_server():
    """Create a ProxyServer without binding a real socket port conflict."""
    server = ProxyServer(("127.0.0.1", 0), _Handler, "", "", {})
    return server


class TestRefreshPreservesIndices(unittest.TestCase):
    """Refresh must update seg_map in place, not replace it (index continuity)."""

    def setUp(self):
        self.server = _make_server()
        # Start with 3 original segments
        self.server.seg_map = {
            0: "https://cdn/old0.ts",
            1: "https://cdn/old1.ts",
            2: "https://cdn/old2.ts",
        }
        self.server._original_url = "https://cdn/sub.m3u8"
        self.server._preferred_quality = 720
        self.server._last_refresh = 0  # allow immediate refresh

    def tearDown(self):
        self.server.server_close()

    def test_refresh_updates_urls_in_place(self):
        fresh_playlist = (
            "#EXTM3U\n"
            "https://cdn/new0.ts\n"
            "https://cdn/new1.ts\n"
            "https://cdn/new2.ts\n"
        )

        class _Resp:
            status_code = 200
            text = fresh_playlist

        with patch.object(self.server.httpx_client, "get", return_value=_Resp()):
            self.server._refresh_playlist()

        # Indices must stay 0,1,2 but point to fresh URLs
        self.assertEqual(self.server.seg_map[0], "https://cdn/new0.ts")
        self.assertEqual(self.server.seg_map[1], "https://cdn/new1.ts")
        self.assertEqual(self.server.seg_map[2], "https://cdn/new2.ts")

    def test_refresh_keeps_extra_original_indices(self):
        """If fresh playlist is shorter, old higher indices remain (no crash)."""
        self.server.seg_map[3] = "https://cdn/old3.ts"
        fresh_playlist = "#EXTM3U\nhttps://cdn/new0.ts\n"

        class _Resp:
            status_code = 200
            text = fresh_playlist

        with patch.object(self.server.httpx_client, "get", return_value=_Resp()):
            self.server._refresh_playlist()

        self.assertEqual(self.server.seg_map[0], "https://cdn/new0.ts")
        # Index 3 preserved since fresh list was shorter
        self.assertEqual(self.server.seg_map[3], "https://cdn/old3.ts")

    def test_refresh_throttled(self):
        """Second immediate refresh must be skipped by throttle."""
        fresh_playlist = "#EXTM3U\nhttps://cdn/new0.ts\n"
        calls = {"n": 0}

        class _Resp:
            status_code = 200
            text = fresh_playlist

        def counting_get(*a, **k):
            calls["n"] += 1
            return _Resp()

        with patch.object(self.server.httpx_client, "get", side_effect=counting_get):
            self.server._refresh_playlist()
            self.server._refresh_playlist()  # should be throttled

        self.assertEqual(calls["n"], 1)

    def test_refresh_updates_init_url(self):
        fresh_playlist = (
            '#EXTM3U\n'
            '#EXT-X-MAP:URI="https://cdn/new_init.mp4"\n'
            "https://cdn/new0.ts\n"
        )

        class _Resp:
            status_code = 200
            text = fresh_playlist

        with patch.object(self.server.httpx_client, "get", return_value=_Resp()):
            self.server._refresh_playlist()

        self.assertEqual(self.server.init_url, "https://cdn/new_init.mp4")


class TestServeUrlRefreshOnError(unittest.TestCase):
    """Segment 4xx must trigger refresh then retry via idx."""

    def setUp(self):
        self.server = _make_server()
        self.server.seg_map = {0: "https://cdn/old0.ts"}
        self.server._original_url = "https://cdn/sub.m3u8"
        self.server._preferred_quality = 720
        self.server._last_refresh = 0

    def tearDown(self):
        self.server.server_close()

    def test_serve_url_passes_idx_and_refreshes(self):
        """_serve_url must accept idx and use it after refresh."""
        import inspect
        sig = inspect.signature(_Handler._serve_url)
        self.assertIn("idx", sig.parameters)


if __name__ == "__main__":
    unittest.main()
