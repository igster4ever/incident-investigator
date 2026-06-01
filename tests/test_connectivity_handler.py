"""
tests/test_connectivity_handler.py — Unit tests for connectivity_handler.py.

Tests run fully offline — all HTTP calls and file I/O are mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock, call

import pytest

from tests.conftest import MockWs
from ii_bridge.connectivity_handler import (
    _ping_clickup,
    _ping_slack,
    _check_slack,
    _check_clickup,
    _handle_check_connectivity,
    _handle_update_token,
    _SLACK_TOKEN_PATH,
    _CLICKUP_TOKEN_PATH,
)


# ── _ping_* unit tests ────────────────────────────────────────────────────────

class TestPingClickup:
    def test_returns_true_on_200(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.status = 200
        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok, err = _ping_clickup("tok")
        assert ok is True
        assert err is None

    def test_returns_false_on_http_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            None, 401, "Unauthorized", {}, None
        )):
            ok, err = _ping_clickup("bad-tok")
        assert ok is False
        assert "401" in err

    def test_returns_false_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            ok, err = _ping_clickup("tok")
        assert ok is False
        assert err is not None


class TestPingSlack:
    def _make_resp(self, body: dict):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(body).encode()
        return mock_resp

    def test_returns_true_when_ok_true(self):
        with patch("urllib.request.urlopen", return_value=self._make_resp({"ok": True})):
            ok, err = _ping_slack("xoxb-tok")
        assert ok is True
        assert err is None

    def test_returns_false_with_error_field(self):
        with patch("urllib.request.urlopen", return_value=self._make_resp({"ok": False, "error": "invalid_auth"})):
            ok, err = _ping_slack("bad-tok")
        assert ok is False
        assert err == "invalid_auth"

    def test_returns_false_on_http_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            None, 403, "Forbidden", {}, None
        )):
            ok, err = _ping_slack("tok")
        assert ok is False
        assert "403" in err


# ── _check_* unit tests ───────────────────────────────────────────────────────

class TestCheckSlack:
    def test_token_set_and_ok(self, tmp_path):
        tok_file = tmp_path / ".slack_token"
        tok_file.write_text("xoxb-valid")
        with (
            patch("ii_bridge.token_utils.SLACK_TOKEN_PATH", tok_file),
            patch("ii_bridge.connectivity_handler._ping_slack", return_value=(True, None)),
        ):
            result = _check_slack()
        assert result == {"ok": True, "token_set": True}

    def test_token_set_but_expired(self, tmp_path):
        tok_file = tmp_path / ".slack_token"
        tok_file.write_text("xoxb-expired")
        with (
            patch("ii_bridge.token_utils.SLACK_TOKEN_PATH", tok_file),
            patch("ii_bridge.connectivity_handler._ping_slack", return_value=(False, "token_revoked")),
        ):
            result = _check_slack()
        assert result["ok"] is False
        assert result["token_set"] is True
        assert result["error"] == "token_revoked"

    def test_no_token_file(self, tmp_path):
        missing = tmp_path / ".slack_token"
        with patch("ii_bridge.token_utils.SLACK_TOKEN_PATH", missing):
            result = _check_slack()
        assert result["ok"] is False
        assert result["token_set"] is False
        assert "error" in result


class TestCheckClickup:
    def test_token_set_and_ok(self, tmp_path):
        tok_file = tmp_path / ".clickup_token"
        tok_file.write_text("pk_valid")
        with (
            patch("ii_bridge.token_utils.CLICKUP_TOKEN_PATH", tok_file),
            patch("ii_bridge.connectivity_handler._CLICKUP_TOKEN_PATH", tok_file),
            patch("os.environ.get", return_value=""),
            patch("ii_bridge.connectivity_handler._ping_clickup", return_value=(True, None)),
        ):
            result = _check_clickup()
        assert result["ok"] is True
        assert result["token_set"] is True

    def test_no_token(self, tmp_path):
        missing = tmp_path / ".clickup_token"
        with (
            patch("ii_bridge.token_utils.CLICKUP_TOKEN_PATH", missing),
            patch("ii_bridge.connectivity_handler._CLICKUP_TOKEN_PATH", missing),
            patch("os.environ.get", return_value=""),
        ):
            result = _check_clickup()
        assert result["ok"] is False
        assert result["token_set"] is False


# ── _handle_check_connectivity ────────────────────────────────────────────────

class TestHandleCheckConnectivity:

    @pytest.mark.asyncio
    async def test_emits_connectivity_status(self):
        ws = MockWs()
        slack_status   = {"ok": True,  "token_set": True}
        clickup_status = {"ok": False, "token_set": False, "error": "No token configured"}

        async def fake_run_in_executor(fn, *args):
            if fn == _check_slack:
                return slack_status
            return clickup_status

        with patch("bridge_modules.shared._run_in_executor", side_effect=fake_run_in_executor):
            await _handle_check_connectivity(ws, {})

        msg = ws.last_of_type("connectivity_status")
        assert msg is not None
        assert msg["slack"]   == slack_status
        assert msg["clickup"] == clickup_status

    @pytest.mark.asyncio
    async def test_emits_status_message_first(self):
        ws = MockWs()

        async def fake_run_in_executor(fn, *args):
            return {"ok": True, "token_set": True}

        with patch("bridge_modules.shared._run_in_executor", side_effect=fake_run_in_executor):
            await _handle_check_connectivity(ws, {})

        assert ws.sent[0]["type"] == "status"
        assert ws.sent[-1]["type"] == "connectivity_status"

    @pytest.mark.asyncio
    async def test_both_checks_run(self):
        ws = MockWs()
        calls: list = []

        async def fake_run_in_executor(fn, *args):
            calls.append(fn.__name__)
            return {"ok": True, "token_set": True}

        with patch("bridge_modules.shared._run_in_executor", side_effect=fake_run_in_executor):
            await _handle_check_connectivity(ws, {})

        assert "_check_slack" in calls
        assert "_check_clickup" in calls


# ── _handle_update_token ──────────────────────────────────────────────────────

class TestHandleUpdateToken:

    def _make_executor(self, ping_ok: bool = True, ping_err: str | None = None):
        async def fake_run_in_executor(fn, *args):
            name = fn.__name__
            if name in ("_ping_slack", "_ping_clickup"):
                return ping_ok, ping_err
            return {"ok": ping_ok, "token_set": True}
        return fake_run_in_executor

    @pytest.mark.asyncio
    async def test_rejects_unknown_integration(self):
        ws = MockWs()
        await _handle_update_token(ws, {"integration": "github", "token": "tok"})
        msg = ws.last_of_type("token_updated")
        assert msg["ok"] is False
        assert "Unknown" in msg["error"]

    @pytest.mark.asyncio
    async def test_rejects_empty_token(self):
        ws = MockWs()
        await _handle_update_token(ws, {"integration": "slack", "token": ""})
        msg = ws.last_of_type("token_updated")
        assert msg["ok"] is False
        assert "empty" in msg["error"]

    @pytest.mark.asyncio
    async def test_slack_token_written_to_correct_file(self, tmp_path):
        ws = MockWs()
        tok_file = tmp_path / ".slack_token"
        with (
            patch("ii_bridge.connectivity_handler._SLACK_TOKEN_PATH", tok_file),
            patch("bridge_modules.shared._run_in_executor", side_effect=self._make_executor()),
        ):
            await _handle_update_token(ws, {"integration": "slack", "token": "xoxb-new"})
        assert tok_file.exists()
        assert tok_file.read_text() == "xoxb-new"
        assert oct(tok_file.stat().st_mode)[-3:] == "600"

    @pytest.mark.asyncio
    async def test_clickup_token_written_and_cache_cleared(self, tmp_path):
        ws = MockWs()
        tok_file = tmp_path / ".clickup_token"
        with (
            patch("ii_bridge.connectivity_handler._CLICKUP_TOKEN_PATH", tok_file),
            patch("bridge_modules.shared._run_in_executor", side_effect=self._make_executor()),
            patch("ii_bridge.clickup_fetcher.reset_clickup_cache") as mock_reset,
        ):
            await _handle_update_token(ws, {"integration": "clickup", "token": "pk_new"})
        assert tok_file.read_text() == "pk_new"
        mock_reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_emits_token_updated_ok_true_on_success(self, tmp_path):
        ws = MockWs()
        tok_file = tmp_path / ".slack_token"
        with (
            patch("ii_bridge.connectivity_handler._SLACK_TOKEN_PATH", tok_file),
            patch("bridge_modules.shared._run_in_executor", side_effect=self._make_executor(ping_ok=True)),
        ):
            await _handle_update_token(ws, {"integration": "slack", "token": "xoxb-ok"})
        msg = ws.last_of_type("token_updated")
        assert msg["ok"] is True
        assert "error" not in msg

    @pytest.mark.asyncio
    async def test_emits_token_updated_ok_false_on_bad_token(self, tmp_path):
        ws = MockWs()
        tok_file = tmp_path / ".slack_token"
        with (
            patch("ii_bridge.connectivity_handler._SLACK_TOKEN_PATH", tok_file),
            patch("bridge_modules.shared._run_in_executor", side_effect=self._make_executor(
                ping_ok=False, ping_err="token_revoked"
            )),
        ):
            await _handle_update_token(ws, {"integration": "slack", "token": "xoxb-bad"})
        msg = ws.last_of_type("token_updated")
        assert msg["ok"] is False
        assert msg["error"] == "token_revoked"

    @pytest.mark.asyncio
    async def test_emits_connectivity_status_after_successful_update(self, tmp_path):
        ws = MockWs()
        tok_file = tmp_path / ".slack_token"
        with (
            patch("ii_bridge.connectivity_handler._SLACK_TOKEN_PATH", tok_file),
            patch("bridge_modules.shared._run_in_executor", side_effect=self._make_executor(ping_ok=True)),
        ):
            await _handle_update_token(ws, {"integration": "slack", "token": "xoxb-ok"})
        assert ws.last_of_type("connectivity_status") is not None

    @pytest.mark.asyncio
    async def test_does_not_emit_connectivity_status_after_failed_update(self, tmp_path):
        ws = MockWs()
        tok_file = tmp_path / ".slack_token"
        with (
            patch("ii_bridge.connectivity_handler._SLACK_TOKEN_PATH", tok_file),
            patch("bridge_modules.shared._run_in_executor", side_effect=self._make_executor(ping_ok=False)),
        ):
            await _handle_update_token(ws, {"integration": "slack", "token": "bad"})
        assert ws.last_of_type("connectivity_status") is None
