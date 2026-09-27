"""Regression tests for proxy playlist/segment refresh (Android player stuck fix)."""

import unittest
from unittest.mock import patch

from nontonaja.proxy import ProxyServer, _Handler, _rewrite_m3u8


def _make_server():
    """Create a ProxyServer without binding a real socket port conflict."""
    server = ProxyServer(("127.0.0.1", 0), _Handler, "", "", {})
    return server


class TestRewriteMediaSequence(unittest.TestCase):
    """Indices must be absolute (media-sequence offset), not list position."""

    def test_indices_offset_by_media_sequence(self):
        text = (
            "#EXTM3U\n"
            "#EXT-X-MEDIA-SEQUENCE:100\n"
            "https://cdn/a.ts\n"
            "https://cdn/b.ts\n"
        )
        _, _, seg_map = _rewrite_m3u8(text, 8080)
        # Absolute indices: 100, 101
        self.assertIn(100, seg_map)
        self.assertIn(101, seg_map)
        self.assertEqual(seg_map[100], "https://cdn/a.ts")
        self.assertEqual(seg_map[101], "https://cdn/b.ts")

    def test_no_media_sequence_starts_at_zero(self):
        text = "#EXTM3U\nhttps://cdn/a.ts\nhttps://cdn/b.ts\n"
        _, _, seg_map = _rewrite_m3u8(text, 8080)
        self.assertEqual(seg_map[0], "https://cdn/a.ts")
        self.assertEqual(seg_map[1], "https://cdn/b.ts")

    def test_playlist_urls_point_to_local_proxy(self):
        text = "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:5\nhttps://cdn/a.ts\n"
        rewritten, _, _ = _rewrite_m3u8(text, 8080)
        self.assertIn("http://127.0.0.1:8080/seg/5.ts", rewritten)
        self.assertNotIn("https://cdn/a.ts", rewritten)


class TestRefreshPreservesIndices(unittest.TestCase):
    """Refresh must merge seg_map (keep old indices), never drop them."""

    def setUp(self):
        self.server = _make_server()
        self.server.seg_map = {0: "https://cdn/old0.ts"}
        self.server._original_url = "https://cdn/sub.m3u8"
        self.server._sub_url = "https://cdn/sub.m3u8"
        self.server._preferred_quality = 720
        self.server._last_refresh = 0  # allow immediate refresh

    def tearDown(self):
        self.server.server_close()

    def test_refresh_merges_new_segments(self):
        fresh = (
            "#EXTM3U\n"
            "#EXT-X-MEDIA-SEQUENCE:10\n"
            "https://cdn/new10.ts\n"
            "https://cdn/new11.ts\n"
        )

        class _Resp:
            status_code = 200
            text = fresh

        with patch.object(self.server.httpx_client, "get", return_value=_Resp()):
            self.server._refresh_playlist()

        # New absolute indices present
        self.assertEqual(self.server.seg_map[10], "https://cdn/new10.ts")
        self.assertEqual(self.server.seg_map[11], "https://cdn/new11.ts")
        # Old index preserved (player may still request it)
        self.assertEqual(self.server.seg_map[0], "https://cdn/old0.ts")

    def test_refresh_throttled(self):
        """Second immediate refresh must be skipped by throttle."""
        fresh = "#EXTM3U\nhttps://cdn/new0.ts\n"
        calls = {"n": 0}

        class _Resp:
            status_code = 200
            text = fresh

        def counting_get(*a, **k):
            calls["n"] += 1
            return _Resp()

        with patch.object(self.server.httpx_client, "get", side_effect=counting_get):
            self.server._refresh_playlist()
            self.server._refresh_playlist()  # should be throttled

        self.assertEqual(calls["n"], 1)

    def test_refresh_updates_init_url(self):
        fresh = (
            '#EXTM3U\n'
            '#EXT-X-MAP:URI="https://cdn/new_init.mp4"\n'
            "#EXT-X-MEDIA-SEQUENCE:0\n"
            "https://cdn/new0.ts\n"
        )

        class _Resp:
            status_code = 200
            text = fresh

        with patch.object(self.server.httpx_client, "get", return_value=_Resp()):
            self.server._refresh_playlist()

        self.assertEqual(self.server.init_url, "https://cdn/new_init.mp4")


class TestBuildFreshPlaylist(unittest.TestCase):
    """Serving a FRESH playlist each request keeps sliding windows advancing."""

    def setUp(self):
        self.server = _make_server()
        self.server.seg_map = {0: "https://cdn/old0.ts"}
        self.server._original_url = "https://cdn/sub.m3u8"
        self.server._sub_url = "https://cdn/sub.m3u8"

    def tearDown(self):
        self.server.server_close()

    def test_build_fresh_returns_new_segments(self):
        fresh = (
            "#EXTM3U\n"
            "#EXT-X-MEDIA-SEQUENCE:20\n"
            "https://cdn/new20.ts\n"
        )

        class _Resp:
            status_code = 200
            text = fresh

        with patch.object(self.server.httpx_client, "get", return_value=_Resp()):
            data = self.server._build_fresh_playlist()

        self.assertIn(b"seg/20.ts", data)
        self.assertEqual(self.server.seg_map[20], "https://cdn/new20.ts")

    def test_build_fresh_falls_back_on_failure(self):
        """Upstream failure must return last good playlist, not crash."""
        self.server.playlist_data = "#EXTM3U\nfallback\n"

        with patch.object(
            self.server.httpx_client, "get", side_effect=Exception("network down")
        ):
            data = self.server._build_fresh_playlist()

        self.assertEqual(data, b"#EXTM3U\nfallback\n")


class TestServeUrlSignature(unittest.TestCase):
    """_serve_url must accept idx so refresh retry works."""

    def test_serve_url_has_idx_param(self):
        import inspect
        sig = inspect.signature(_Handler._serve_url)
        self.assertIn("idx", sig.parameters)


class TestHandlerServesPlaylistEndToEnd(unittest.TestCase):
    """Regression: _serve_playlist must call the SERVER's builder, not the
    handler (AttributeError: '_Handler' object has no attribute ...)."""

    def setUp(self):
        self.server = _make_server()
        self.server._original_url = "https://cdn/sub.m3u8"
        self.server._sub_url = "https://cdn/sub.m3u8"
        self.server.playlist_data = "#EXTM3U\nhttps://cdn/a.ts\n"

    def tearDown(self):
        self.server.server_close()

    def test_serve_playlist_uses_server_builder(self):
        """Handler._serve_playlist must not reference a handler-level builder."""
        fresh = "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:0\nhttps://cdn/a.ts\n"

        class _Resp:
            status_code = 200
            text = fresh

        # Point handler at our server, capture written bytes
        handler = object.__new__(_Handler)
        handler.server = self.server
        written = {"data": b""}
        sent = {"status": None}

        def fake_send_response(code, *a, **k):
            sent["status"] = code

        class _W:
            def write(self, b):
                written["data"] += b

        handler.send_response = fake_send_response
        handler.send_header = lambda *a, **k: None
        handler.end_headers = lambda *a, **k: None
        handler.wfile = _W()

        with patch.object(self.server.httpx_client, "get", return_value=_Resp()):
            handler._serve_playlist()  # must NOT raise AttributeError

        self.assertEqual(sent["status"], 200)
        self.assertIn(b"seg/0.ts", written["data"])


class TestFarSeekBehavior(unittest.TestCase):
    """Far seeking must not hammer upstream and must resolve missing indices."""

    def _handler_with(self, server):
        handler = object.__new__(_Handler)
        handler.server = server
        handler._resp_status = None
        handler._headers = []
        handler.send_response = lambda c, *a, **k: setattr(handler, "_resp_status", c)
        handler.send_header = lambda *a, **k: handler._headers.append(a)
        handler.end_headers = lambda *a, **k: None
        handler.send_error = lambda c, *a, **k: setattr(handler, "_resp_status", c)
        return handler

    def test_vod_playlist_not_refetched(self):
        """For VOD (cached playlist_data), serving playlist must not hit upstream."""
        server = _make_server()
        server._is_vod = True
        server.playlist_data = "#EXTM3U\nhttp://127.0.0.1:1/seg/0.ts\n"
        handler = self._handler_with(server)
        handler.wfile = type("W", (), {"write": lambda self, b: None})()

        calls = {"n": 0}

        def counting_get(*a, **k):
            calls["n"] += 1
            raise AssertionError("upstream must not be called for VOD")

        with patch.object(server.httpx_client, "get", side_effect=counting_get):
            handler._serve_playlist()

        self.assertEqual(calls["n"], 0)
        self.assertEqual(handler._resp_status, 200)
        server.server_close()

    def test_missing_index_triggers_refresh(self):
        """do_GET for an unknown seg index must refresh before serving."""
        server = _make_server()
        server._is_vod = False
        server._last_refresh = 0
        server.seg_map = {}
        server._original_url = "https://cdn/sub.m3u8"
        server._sub_url = "https://cdn/sub.m3u8"
        server.playlist_data = ""

        fresh = (
            "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:0\n"
            + "".join(f"https://cdn/s{i}.ts\n" for i in range(50))
        )

        class _Resp:
            status_code = 200
            text = fresh
            headers = {"content-type": "video/mp2t"}
            content = b"\x47" * 10

        handler = self._handler_with(server)
        handler.path = "/seg/40.ts"
        handler.wfile = type("W", (), {"write": lambda self, b: None})()

        with patch.object(server.httpx_client, "get", return_value=_Resp()):
            handler.do_GET()

        # After refresh, index 40 must be known
        self.assertIn(40, server.seg_map)
        server.server_close()


if __name__ == "__main__":
    unittest.main()
