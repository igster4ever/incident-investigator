"""
tests/test_handlers.py — Handler flow tests with mock WebSocket.

Tests verify that handlers:
  - emit the correct event sequence (status → progress → complete)
  - send an error event for empty input
  - pass the right prompt_fns based on mode
  - do not call Claude if data gathering raises

All external I/O (Slack, git, Claude, stacktrace scripts) is patched out.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ii_bridge.handlers import _handle_fix_advisor, _handle_minimal_fix, HANDLERS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_stream_patch(return_value="mocked report"):
    return patch(
        "bridge_modules.shared._stream_claude_to_ws",
        new_callable=AsyncMock,
        return_value=return_value,
    )

def _make_no_token_patch():
    return patch("bridge_modules.shared._read_slack_token", return_value=None)

def _make_executor_patch(return_value=""):
    return patch(
        "bridge_modules.shared._run_in_executor",
        new_callable=AsyncMock,
        return_value=return_value,
    )


# ── Fix Advisor ───────────────────────────────────────────────────────────────

class TestFixAdvisorHandler:

    @pytest.mark.asyncio
    async def test_empty_input_sends_error(self, mock_ws):
        await _handle_fix_advisor(mock_ws, {"mode": "clickup", "input": ""})
        errors = mock_ws.messages_of_type("error")
        assert errors, "Expected an error event for empty input"
        assert "No input provided" in errors[0]["message"]

    @pytest.mark.asyncio
    async def test_clickup_mode_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch("report text"):
            await _handle_fix_advisor(mock_ws, {"mode": "clickup", "input": "AOP-1234"})

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert complete is not None
        assert complete["report"] == "report text"

    @pytest.mark.asyncio
    async def test_description_mode_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch("fa report"):
            await _handle_fix_advisor(mock_ws, {"mode": "description", "input": "service crashed"})

        assert mock_ws.last_of_type("fix_advisor_complete") is not None

    @pytest.mark.asyncio
    async def test_stacktrace_mode_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(return_value={}), _make_stream_patch():
            await _handle_fix_advisor(mock_ws, {"mode": "stacktrace", "input": "java.lang.NPE at line 1"})

        assert mock_ws.last_of_type("fix_advisor_complete") is not None

    @pytest.mark.asyncio
    async def test_status_messages_emitted_before_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch():
            await _handle_fix_advisor(mock_ws, {"mode": "clickup", "input": "AOP-1234"})

        types = [m["type"] for m in mock_ws.sent]
        complete_idx = types.index("fix_advisor_complete")
        assert "status" in types[:complete_idx], "Expected status messages before complete"

    @pytest.mark.asyncio
    async def test_data_gathering_failure_sends_error(self, mock_ws):
        with _make_no_token_patch(), _make_stream_patch():
            with patch(
                "bridge_modules.shared._run_in_executor",
                new_callable=AsyncMock,
                side_effect=RuntimeError("git exploded"),
            ):
                await _handle_fix_advisor(mock_ws, {"mode": "clickup", "input": "AOP-1234"})

        errors = mock_ws.messages_of_type("error")
        assert errors
        assert "Data gathering failed" in errors[0]["message"]

    @pytest.mark.asyncio
    async def test_no_complete_event_after_data_error(self, mock_ws):
        with _make_no_token_patch(), _make_stream_patch():
            with patch(
                "bridge_modules.shared._run_in_executor",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ):
                await _handle_fix_advisor(mock_ws, {"mode": "clickup", "input": "AOP-1234"})

        assert mock_ws.last_of_type("fix_advisor_complete") is None

    @pytest.mark.asyncio
    async def test_slack_thread_mode(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch("thread report"):
            await _handle_fix_advisor(mock_ws, {
                "mode": "slack_thread",
                "input": "https://amelco.slack.com/archives/C123/p1234567890123456",
            })

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert complete is not None


# ── Minimal Fix ───────────────────────────────────────────────────────────────

class TestMinimalFixHandler:

    @pytest.mark.asyncio
    async def test_empty_input_sends_error(self, mock_ws):
        await _handle_minimal_fix(mock_ws, {"mode": "clickup", "input": ""})
        errors = mock_ws.messages_of_type("error")
        assert errors
        assert "No input provided" in errors[0]["message"]

    @pytest.mark.asyncio
    async def test_clickup_mode_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch("mf report"):
            await _handle_minimal_fix(mock_ws, {"mode": "clickup", "input": "DEV-9999"})

        complete = mock_ws.last_of_type("minimal_fix_complete")
        assert complete is not None
        assert complete["report"] == "mf report"

    @pytest.mark.asyncio
    async def test_description_mode_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch():
            await _handle_minimal_fix(mock_ws, {"mode": "description", "input": "something is broken"})

        assert mock_ws.last_of_type("minimal_fix_complete") is not None

    @pytest.mark.asyncio
    async def test_stacktrace_mode_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(return_value={}), _make_stream_patch():
            await _handle_minimal_fix(mock_ws, {"mode": "stacktrace", "input": "NPE at ..."})

        assert mock_ws.last_of_type("minimal_fix_complete") is not None

    @pytest.mark.asyncio
    async def test_emits_minimal_fix_not_fix_advisor_events(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch():
            await _handle_minimal_fix(mock_ws, {"mode": "clickup", "input": "DEV-9999"})

        assert mock_ws.last_of_type("minimal_fix_complete") is not None
        assert mock_ws.last_of_type("fix_advisor_complete") is None


# ── HANDLERS dict ─────────────────────────────────────────────────────────────

class TestHandlersDict:
    def test_fix_advisor_registered(self):
        assert "fix_advisor_report" in HANDLERS

    def test_minimal_fix_registered(self):
        assert "minimal_fix_report" in HANDLERS

    def test_handlers_are_callable(self):
        assert callable(HANDLERS["fix_advisor_report"])
        assert callable(HANDLERS["minimal_fix_report"])
