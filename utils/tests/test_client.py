"""Tests for utils.client: QLeverClient instantiation, QLeverError, _build_url, HTTP mocking."""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from utils.client import QLeverClient, QLeverError


# ---------------------------------------------------------------------------
# QLeverError
# ---------------------------------------------------------------------------

class TestQLeverError:
    def test_is_exception(self):
        err = QLeverError("something went wrong")
        assert isinstance(err, Exception)

    def test_message_attribute(self):
        err = QLeverError("oops", status_code=404)
        assert err.message == "oops"

    def test_status_code_attribute(self):
        err = QLeverError("not found", status_code=404)
        assert err.status_code == 404

    def test_default_status_code_zero(self):
        err = QLeverError("connection failed")
        assert err.status_code == 0

    def test_str_representation(self):
        err = QLeverError("bad request", status_code=400)
        assert "bad request" in str(err)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(QLeverError) as exc_info:
            raise QLeverError("test error", status_code=500)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# QLeverClient instantiation
# ---------------------------------------------------------------------------

class TestQLeverClientInstantiation:
    def test_basic_instantiation(self):
        client = QLeverClient("http://localhost:7001")
        assert client.endpoint == "http://localhost:7001"

    def test_trailing_slash_stripped(self):
        client = QLeverClient("http://localhost:7001/")
        assert client.endpoint == "http://localhost:7001"

    def test_multiple_trailing_slashes_stripped(self):
        client = QLeverClient("http://localhost:7001///")
        assert client.endpoint == "http://localhost:7001"

    def test_default_max_send(self):
        client = QLeverClient("http://localhost:7001")
        assert client.max_send == 5000

    def test_custom_max_send(self):
        client = QLeverClient("http://localhost:7001", max_send=100)
        assert client.max_send == 100

    def test_default_timeout(self):
        client = QLeverClient("http://localhost:7001")
        assert client.timeout == 300.0

    def test_custom_timeout(self):
        client = QLeverClient("http://localhost:7001", timeout=60.0)
        assert client.timeout == 60.0

    def test_repr_contains_endpoint(self):
        client = QLeverClient("http://localhost:7001")
        r = repr(client)
        assert "http://localhost:7001" in r

    def test_repr_format(self):
        client = QLeverClient("http://localhost:7001")
        assert repr(client) == "QLeverClient('http://localhost:7001')"


# ---------------------------------------------------------------------------
# _build_url() — internal URL construction
# ---------------------------------------------------------------------------

class TestBuildUrl:
    """Tests that verify the URL built for requests contains the right params."""

    def _make_fake_response(self, data: dict) -> MagicMock:
        body = json.dumps(data).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.side_effect = None
        # make json.load work by backing with a BytesIO
        mock_resp.__iter__ = lambda s: iter(body)
        return io.BytesIO(body)

    def test_query_url_contains_endpoint(self):
        client = QLeverClient("http://localhost:7001")
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return io.BytesIO(json.dumps({}).encode())

        with patch("utils.client.urllib.request.urlopen", side_effect=fake_urlopen):
            try:
                client.query("SELECT * WHERE { ?s ?p ?o }")
            except Exception:
                pass
        assert "http://localhost:7001/?" in captured.get('url', '')

    def test_query_url_contains_action_param(self):
        client = QLeverClient("http://localhost:7001")
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return io.BytesIO(json.dumps({}).encode())

        with patch("utils.client.urllib.request.urlopen", side_effect=fake_urlopen):
            try:
                client.query("SELECT * WHERE { ?s ?p ?o }", action="qlever_json_export")
            except Exception:
                pass
        assert "action=qlever_json_export" in captured.get('url', '')

    def test_query_url_contains_send_param(self):
        client = QLeverClient("http://localhost:7001", max_send=42)
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return io.BytesIO(json.dumps({}).encode())

        with patch("utils.client.urllib.request.urlopen", side_effect=fake_urlopen):
            try:
                client.query("SELECT * WHERE { ?s ?p ?o }")
            except Exception:
                pass
        assert "send=42" in captured.get('url', '')

    def test_query_custom_max_send_overrides(self):
        client = QLeverClient("http://localhost:7001", max_send=100)
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return io.BytesIO(json.dumps({}).encode())

        with patch("utils.client.urllib.request.urlopen", side_effect=fake_urlopen):
            try:
                client.query("SELECT * WHERE { ?s ?p ?o }", max_send=7)
            except Exception:
                pass
        assert "send=7" in captured.get('url', '')


# ---------------------------------------------------------------------------
# HTTP mocking — query()
# ---------------------------------------------------------------------------

class TestQueryMocked:
    def _json_response(self, data: dict) -> io.BytesIO:
        return io.BytesIO(json.dumps(data).encode())

    def test_query_returns_dict_for_json_action(self):
        client = QLeverClient("http://localhost:7001")
        payload = {"results": {"bindings": []}}

        with patch("utils.client.urllib.request.urlopen",
                   return_value=self._json_response(payload)):
            result = client.query("SELECT * WHERE { ?s ?p ?o }")
        assert result == payload

    def test_query_returns_string_for_tsv_action(self):
        client = QLeverClient("http://localhost:7001")
        tsv_data = b"?s\t?p\t?o\n"
        mock_resp = MagicMock()
        mock_resp.read.return_value = tsv_data

        with patch("utils.client.urllib.request.urlopen", return_value=mock_resp):
            result = client.query("SELECT * WHERE { ?s ?p ?o }", action="tsv_export")
        assert isinstance(result, str)
        assert "?s" in result

    def test_query_raises_qlever_error_on_http_error(self):
        client = QLeverClient("http://localhost:7001")
        http_err = urllib.error.HTTPError(
            url="http://localhost:7001/?query=...",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b"server exploded"),
        )
        with patch("utils.client.urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(QLeverError) as exc_info:
                client.query("SELECT * WHERE { ?s ?p ?o }")
        assert exc_info.value.status_code == 500

    def test_query_raises_qlever_error_on_url_error(self):
        client = QLeverClient("http://localhost:7001")
        url_err = urllib.error.URLError(reason="Connection refused")
        with patch("utils.client.urllib.request.urlopen", side_effect=url_err):
            with pytest.raises(QLeverError) as exc_info:
                client.query("SELECT * WHERE { ?s ?p ?o }")
        assert exc_info.value.status_code == 0

    def test_query_http_error_message_contains_code(self):
        client = QLeverClient("http://localhost:7001")
        http_err = urllib.error.HTTPError(
            url="http://localhost:7001/?query=...",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b"not found"),
        )
        with patch("utils.client.urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(QLeverError) as exc_info:
                client.query("SELECT * WHERE { ?s ?p ?o }")
        assert "404" in exc_info.value.message


# ---------------------------------------------------------------------------
# HTTP mocking — query_df()
# ---------------------------------------------------------------------------

class TestQueryDfMocked:
    def _json_response(self, data: dict) -> io.BytesIO:
        return io.BytesIO(json.dumps(data).encode())

    def test_query_df_returns_list_of_dicts(self):
        client = QLeverClient("http://localhost:7001")
        payload = {
            "results": {
                "bindings": [
                    {"s": {"value": "http://a.org/1"}, "p": {"value": "http://a.org/p"}},
                    {"s": {"value": "http://a.org/2"}, "p": {"value": "http://a.org/q"}},
                ]
            }
        }
        with patch("utils.client.urllib.request.urlopen",
                   return_value=self._json_response(payload)):
            rows = client.query_df("SELECT ?s ?p WHERE { ?s ?p ?o }")
        assert len(rows) == 2
        assert rows[0]["s"] == "http://a.org/1"
        assert rows[1]["p"] == "http://a.org/q"

    def test_query_df_empty_bindings(self):
        client = QLeverClient("http://localhost:7001")
        payload = {"results": {"bindings": []}}
        with patch("utils.client.urllib.request.urlopen",
                   return_value=self._json_response(payload)):
            rows = client.query_df("SELECT * WHERE { ?s ?p ?o }")
        assert rows == []

    def test_query_df_missing_results_key(self):
        client = QLeverClient("http://localhost:7001")
        payload = {}
        with patch("utils.client.urllib.request.urlopen",
                   return_value=self._json_response(payload)):
            rows = client.query_df("SELECT * WHERE { ?s ?p ?o }")
        assert rows == []


# ---------------------------------------------------------------------------
# HTTP mocking — _get_json() via stats() / cache_stats()
# ---------------------------------------------------------------------------

class TestGetJsonMocked:
    def _json_response(self, data: dict) -> io.BytesIO:
        return io.BytesIO(json.dumps(data).encode())

    def test_stats_returns_dict(self):
        client = QLeverClient("http://localhost:7001")
        payload = {"index-name": "my-index", "num-triples": 1000}
        with patch("utils.client.urllib.request.urlopen",
                   return_value=self._json_response(payload)):
            result = client.stats()
        assert result == payload

    def test_cache_stats_returns_dict(self):
        client = QLeverClient("http://localhost:7001")
        payload = {"num-cached-results": 5}
        with patch("utils.client.urllib.request.urlopen",
                   return_value=self._json_response(payload)):
            result = client.cache_stats()
        assert result == payload

    def test_stats_raises_qlever_error_on_http_error(self):
        client = QLeverClient("http://localhost:7001")
        http_err = urllib.error.HTTPError(
            url="http://localhost:7001/?cmd=stats",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=io.BytesIO(b"unavailable"),
        )
        with patch("utils.client.urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(QLeverError) as exc_info:
                client.stats()
        assert exc_info.value.status_code == 503

    def test_clear_cache_with_access_token(self):
        client = QLeverClient("http://localhost:7001")
        payload = {"result": "cache cleared"}
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return io.BytesIO(json.dumps(payload).encode())

        with patch("utils.client.urllib.request.urlopen", side_effect=fake_urlopen):
            result = client.clear_cache(access_token="secret-token")
        assert result == payload
        assert "access-token=secret-token" in captured['url']

    def test_clear_cache_without_token(self):
        client = QLeverClient("http://localhost:7001")
        payload = {"result": "cache cleared"}
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            return io.BytesIO(json.dumps(payload).encode())

        with patch("utils.client.urllib.request.urlopen", side_effect=fake_urlopen):
            client.clear_cache()
        assert "access-token" not in captured['url']
