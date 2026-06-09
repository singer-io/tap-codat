"""Unit tests for tap_codat.http — Client initialization, request handling, and URL building."""

import unittest
from base64 import b64encode
from unittest.mock import MagicMock, patch

import requests

from tap_codat.http import Client, RateLimitException, _join, BASE_URL, UAT_URL


default_config = {
    "api_key": "test_api_key_12345",
    "start_date": "2023-01-01T00:00:00Z",
    "uat_urls": "false",
}


class TestJoin(unittest.TestCase):
    """Tests for _join URL helper."""

    def test_simple_join(self):
        self.assertEqual(_join("https://api.codat.io", "/companies"), "https://api.codat.io/companies")

    def test_strips_trailing_slash(self):
        self.assertEqual(_join("https://api.codat.io/", "/companies"), "https://api.codat.io/companies")

    def test_strips_leading_slash(self):
        self.assertEqual(_join("https://api.codat.io", "companies"), "https://api.codat.io/companies")

    def test_both_slashes(self):
        self.assertEqual(_join("https://api.codat.io/", "companies/"), "https://api.codat.io/companies/")

    def test_nested_path(self):
        self.assertEqual(
            _join("https://api.codat.io", "/companies/123/data/accounts"),
            "https://api.codat.io/companies/123/data/accounts",
        )


class TestClientInit(unittest.TestCase):
    """Tests for Client initialization."""

    def test_production_base_url(self):
        client = Client({"api_key": "key", "uat_urls": "false"})
        self.assertEqual(client.base_url, BASE_URL)

    def test_uat_base_url(self):
        client = Client({"api_key": "key", "uat_urls": "true"})
        self.assertEqual(client.base_url, UAT_URL)

    def test_uat_base_url_case_insensitive(self):
        client = Client({"api_key": "key", "uat_urls": "True"})
        self.assertEqual(client.base_url, UAT_URL)

    def test_encodes_api_key_to_base64(self):
        client = Client({"api_key": "my_secret", "uat_urls": "false"})
        expected = b64encode(b"my_secret").decode("utf-8")
        self.assertEqual(client.b64key, expected)

    def test_session_is_requests_session(self):
        client = Client(default_config)
        self.assertIsInstance(client.session, requests.Session)

    def test_logs_initially_empty(self):
        client = Client(default_config)
        self.assertEqual(client.logs, [])

    def test_user_agent_set(self):
        config = {**default_config, "user_agent": "test-agent/1.0"}
        client = Client(config)
        self.assertEqual(client.user_agent, "test-agent/1.0")

    def test_user_agent_none_when_missing(self):
        client = Client(default_config)
        self.assertIsNone(client.user_agent)


class TestClientUrl(unittest.TestCase):
    """Tests for Client.url method."""

    def test_url_builds_full_url(self):
        client = Client(default_config)
        self.assertEqual(client.url("/companies"), "https://api.codat.io/companies")

    def test_url_with_nested_path(self):
        client = Client(default_config)
        self.assertEqual(
            client.url("/companies/123/data/accounts"),
            "https://api.codat.io/companies/123/data/accounts",
        )


class TestClientCreateGetRequest(unittest.TestCase):
    """Tests for Client.create_get_request."""

    def test_creates_get_request(self):
        client = Client(default_config)
        req = client.create_get_request(path="/companies")
        self.assertEqual(req.method, "GET")
        self.assertEqual(req.url, "https://api.codat.io/companies")

    def test_request_with_params(self):
        client = Client(default_config)
        req = client.create_get_request(path="/companies", params={"page": 1})
        self.assertEqual(req.params, {"page": 1})


class TestClientPrepareAndSend(unittest.TestCase):
    """Tests for Client.prepare_and_send — header injection."""

    def test_sets_authorization_header(self):
        client = Client(default_config)
        req = requests.Request(method="GET", url="https://api.codat.io/companies")
        client.session = MagicMock()
        client.session.send.return_value = MagicMock(status_code=200)

        client.prepare_and_send(req)

        self.assertIn("Authorization", req.headers)
        self.assertTrue(req.headers["Authorization"].startswith("Basic "))

    def test_sets_user_agent_when_configured(self):
        config = {**default_config, "user_agent": "my-agent/2.0"}
        client = Client(config)
        req = requests.Request(method="GET", url="https://api.codat.io/companies")
        client.session = MagicMock()
        client.session.send.return_value = MagicMock(status_code=200)

        client.prepare_and_send(req)

        self.assertEqual(req.headers["User-Agent"], "my-agent/2.0")

    def test_no_user_agent_when_not_configured(self):
        client = Client(default_config)
        req = requests.Request(method="GET", url="https://api.codat.io/companies")
        client.session = MagicMock()
        client.session.send.return_value = MagicMock(status_code=200)

        client.prepare_and_send(req)

        self.assertNotIn("User-Agent", req.headers)


class TestClientRequestWithHandling(unittest.TestCase):
    """Tests for Client.request_with_handling — status code handling."""

    def _make_client(self):
        return Client(default_config)

    def _make_response(self, status_code, json_data=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.url = "https://api.codat.io/test"
        resp.raise_for_status = MagicMock()
        return resp

    @patch.object(Client, "prepare_and_send")
    def test_returns_json_on_200(self, mock_send):
        client = self._make_client()
        mock_send.return_value = self._make_response(200, {"results": [1, 2]})
        result = client.request_with_handling(MagicMock(), "companies")
        self.assertEqual(result, {"results": [1, 2]})

    @patch.object(Client, "prepare_and_send")
    def test_returns_empty_results_on_404(self, mock_send):
        client = self._make_client()
        mock_send.return_value = self._make_response(404)
        result = client.request_with_handling(MagicMock(), "companies")
        self.assertEqual(result, {"results": []})

    @patch.object(Client, "prepare_and_send")
    def test_404_appends_to_logs(self, mock_send):
        client = self._make_client()
        mock_send.return_value = self._make_response(404)
        client.request_with_handling(MagicMock(), "companies")
        self.assertEqual(len(client.logs), 1)
        self.assertEqual(client.logs[0]["status_code"], 404)

    @patch.object(Client, "prepare_and_send")
    def test_returns_none_on_409(self, mock_send):
        client = self._make_client()
        mock_send.return_value = self._make_response(409)
        result = client.request_with_handling(MagicMock(), "accounts")
        self.assertIsNone(result)

    @patch.object(Client, "prepare_and_send")
    def test_409_appends_to_logs_with_msg(self, mock_send):
        client = self._make_client()
        mock_send.return_value = self._make_response(409)
        client.request_with_handling(MagicMock(), "accounts")
        self.assertEqual(len(client.logs), 1)
        self.assertIn("msg", client.logs[0])

    @patch.object(Client, "prepare_and_send")
    def test_retries_on_429_then_succeeds(self, mock_send):
        """429 triggers backoff retry; second call succeeds."""
        client = self._make_client()
        mock_send.side_effect = [
            self._make_response(429),
            self._make_response(200, {"ok": True}),
        ]
        result = client.request_with_handling(MagicMock(), "companies")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_send.call_count, 2)

    @patch.object(Client, "prepare_and_send")
    def test_retries_on_500_then_succeeds(self, mock_send):
        """500 triggers backoff retry; second call succeeds."""
        client = self._make_client()
        mock_send.side_effect = [
            self._make_response(500),
            self._make_response(200, {"recovered": True}),
        ]
        result = client.request_with_handling(MagicMock(), "companies")
        self.assertEqual(result, {"recovered": True})

    @patch.object(Client, "prepare_and_send")
    def test_retries_on_502_then_succeeds(self, mock_send):
        client = self._make_client()
        mock_send.side_effect = [
            self._make_response(502),
            self._make_response(200, {"data": []}),
        ]
        result = client.request_with_handling(MagicMock(), "invoices")
        self.assertEqual(result, {"data": []})

    @patch.object(Client, "prepare_and_send")
    def test_retries_on_503_then_succeeds(self, mock_send):
        client = self._make_client()
        mock_send.side_effect = [
            self._make_response(503),
            self._make_response(200, {"data": []}),
        ]
        result = client.request_with_handling(MagicMock(), "bills")
        self.assertEqual(result, {"data": []})

    @patch.object(Client, "prepare_and_send")
    def test_calls_raise_for_status_on_other_4xx(self, mock_send):
        """Status codes like 400 or 403 call raise_for_status."""
        client = self._make_client()
        resp = self._make_response(400)
        mock_send.return_value = resp
        client.request_with_handling(MagicMock(), "companies")
        resp.raise_for_status.assert_called_once()

    @patch.object(Client, "prepare_and_send")
    def test_multiple_404s_accumulate_logs(self, mock_send):
        client = self._make_client()
        mock_send.return_value = self._make_response(404)
        client.request_with_handling(MagicMock(), "accounts")
        client.request_with_handling(MagicMock(), "bills")
        self.assertEqual(len(client.logs), 2)


class TestClientGET(unittest.TestCase):
    """Tests for Client.GET convenience method."""

    @patch.object(Client, "request_with_handling")
    def test_get_calls_request_with_handling(self, mock_handling):
        client = Client(default_config)
        mock_handling.return_value = {"results": []}
        result = client.GET({"path": "/companies"}, "companies")
        mock_handling.assert_called_once()
        self.assertEqual(result, {"results": []})

    @patch.object(Client, "request_with_handling")
    def test_get_passes_params(self, mock_handling):
        client = Client(default_config)
        mock_handling.return_value = {"results": []}
        client.GET({"path": "/companies", "params": {"page": 2}}, "companies")
        mock_handling.assert_called_once()

    @patch.object(Client, "request_with_handling")
    def test_get_returns_none_when_handling_returns_none(self, mock_handling):
        client = Client(default_config)
        mock_handling.return_value = None
        result = client.GET({"path": "/companies/123"}, "company_info")
        self.assertIsNone(result)


class TestClientWriteAndClearLogs(unittest.TestCase):
    """Tests for Client.write_and_clear_accumulated_logs."""

    def test_clears_logs_after_writing(self):
        client = Client(default_config)
        client.logs = [{"tap_stream_id": "test", "status_code": 404, "url": "/x"}]
        client.write_and_clear_accumulated_logs()
        self.assertEqual(client.logs, [])

    def test_clears_empty_logs(self):
        client = Client(default_config)
        client.write_and_clear_accumulated_logs()
        self.assertEqual(client.logs, [])


if __name__ == "__main__":
    unittest.main()
