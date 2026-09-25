import unittest
from unittest.mock import patch

from nontonaja.config import Config
from nontonaja.diag import _test_http
from nontonaja.providers import flixhq, idlix, lk21


class _FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        return self._json


def _cfg_with_proxy(proxy="socks5://127.0.0.1:1080"):
    cfg = Config()
    cfg.proxy = proxy
    return cfg


class TestProxyIsUsedInSearch(unittest.TestCase):
    """Regression: search() must forward the configured proxy."""

    def test_flixhq_search_passes_proxy(self):
        captured = {}

        def fake_request(method, url, **kwargs):
            captured["proxy"] = kwargs.get("proxy")
            return _FakeResponse(status_code=200, text="")

        with patch.object(flixhq, "load_config", return_value=_cfg_with_proxy()), patch.object(
            flixhq, "request_with_retry", side_effect=fake_request
        ):
            flixhq.search("spider man")

        self.assertEqual(captured["proxy"], "socks5://127.0.0.1:1080")

    def test_lk21_search_passes_proxy(self):
        captured = {}

        def fake_request(method, url, **kwargs):
            captured["proxy"] = kwargs.get("proxy")
            return _FakeResponse(status_code=200, text="<body></body>")

        with patch.object(lk21, "load_config", return_value=_cfg_with_proxy()), patch.object(
            lk21, "request_with_retry", side_effect=fake_request
        ):
            lk21.search("spider man")

        self.assertEqual(captured["proxy"], "socks5://127.0.0.1:1080")

    def test_idlix_search_passes_proxy(self):
        captured = {}

        def fake_request(method, url, **kwargs):
            captured["proxy"] = kwargs.get("proxy")
            return _FakeResponse(status_code=200, json_data={"results": []})

        with patch.object(idlix, "load_config", return_value=_cfg_with_proxy()), patch.object(
            idlix, "request_with_retry", side_effect=fake_request
        ):
            idlix.search("spider man")

        self.assertEqual(captured["proxy"], "socks5://127.0.0.1:1080")

    def test_proxy_none_when_not_configured(self):
        captured = {}

        def fake_request(method, url, **kwargs):
            captured["proxy"] = kwargs.get("proxy", "MISSING")
            return _FakeResponse(status_code=200, json_data={"results": []})

        with patch.object(idlix, "load_config", return_value=Config()), patch.object(
            idlix, "request_with_retry", side_effect=fake_request
        ):
            idlix.search("spider man")

        self.assertIsNone(captured["proxy"])


class TestDiagDetectsBlocking(unittest.TestCase):
    """Regression: diag must treat HTTP 403 as BLOCKED, not OK."""

    def test_403_reported_as_blocked(self):
        def fake_get(url, **kwargs):
            return _FakeResponse(status_code=403, text="blocked")

        with patch("nontonaja.diag.httpx.get", side_effect=fake_get):
            status, detail = _test_http("https://flixhq.ws")

        self.assertEqual(status, "HTTP 403")
        self.assertIn("BLOCKED", detail)

    def test_200_reported_as_ok(self):
        def fake_get(url, **kwargs):
            return _FakeResponse(status_code=200, text="hello")

        with patch("nontonaja.diag.httpx.get", side_effect=fake_get):
            status, detail = _test_http("https://flixhq.ws")

        self.assertEqual(status, "HTTP 200")
        self.assertIn("OK", detail)

    def test_proxy_forwarded_to_httpx(self):
        captured = {}

        def fake_get(url, **kwargs):
            captured["proxy"] = kwargs.get("proxy")
            return _FakeResponse(status_code=200, text="ok")

        with patch("nontonaja.diag.httpx.get", side_effect=fake_get):
            _test_http("https://flixhq.ws", proxy="socks5://127.0.0.1:1080")

        self.assertEqual(captured["proxy"], "socks5://127.0.0.1:1080")


if __name__ == "__main__":
    unittest.main()
