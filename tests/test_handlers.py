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

from ii_bridge.handlers import (
    _handle_fix_advisor,
    _handle_minimal_fix,
    _handle_perf_advisor,
    _handle_extract_stacktrace_image,
    HANDLERS,
)


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


# ── Performance Advisor ───────────────────────────────────────────────────────

def _make_repo_path_patch():
    from pathlib import Path
    return patch(
        "bridge_modules.triage_handlers._REPO_PATH",
        new=Path("/fake/repo"),
    )


class TestPerfAdvisorHandler:

    @pytest.mark.asyncio
    async def test_empty_input_sends_error(self, mock_ws):
        await _handle_perf_advisor(mock_ws, {"mode": "description", "input": ""})
        errors = mock_ws.messages_of_type("error")
        assert errors
        assert "No input provided" in errors[0]["message"]

    @pytest.mark.asyncio
    async def test_clickup_mode_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch("perf report"), _make_repo_path_patch():
            await _handle_perf_advisor(mock_ws, {"mode": "clickup", "input": "AOP-7777", "depth": "standard"})

        complete = mock_ws.last_of_type("perf_advisor_complete")
        assert complete is not None
        assert complete["report"] == "perf report"

    @pytest.mark.asyncio
    async def test_slack_thread_mode_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch(), _make_repo_path_patch():
            await _handle_perf_advisor(mock_ws, {
                "mode": "slack_thread",
                "input": "https://amelco.slack.com/archives/C123/p111",
                "depth": "quick",
            })
        assert mock_ws.last_of_type("perf_advisor_complete") is not None

    @pytest.mark.asyncio
    async def test_stacktrace_mode_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(return_value={}), _make_stream_patch(), _make_repo_path_patch():
            await _handle_perf_advisor(mock_ws, {"mode": "stacktrace", "input": "NPE at X", "depth": "full"})
        assert mock_ws.last_of_type("perf_advisor_complete") is not None

    @pytest.mark.asyncio
    async def test_description_free_text_emits_complete(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch("result"), _make_repo_path_patch():
            await _handle_perf_advisor(mock_ws, {"mode": "description", "input": "the service is slow", "depth": "quick"})
        assert mock_ws.last_of_type("perf_advisor_complete") is not None

    @pytest.mark.asyncio
    async def test_description_commit_hash_fetches_diff(self, mock_ws):
        with (
            _make_no_token_patch(),
            _make_repo_path_patch(),
            _make_stream_patch("result"),
            patch("ii_bridge.handlers.fetch_commit_diff", return_value="diff content"),
        ):
            await _handle_perf_advisor(mock_ws, {"mode": "description", "input": "abc1234", "depth": "standard"})

        assert mock_ws.last_of_type("perf_advisor_complete") is not None

    @pytest.mark.asyncio
    async def test_description_commit_fetch_failure_emits_fetch_required(self, mock_ws):
        from ii_bridge.fetcher import FetchError
        with (
            _make_no_token_patch(),
            _make_repo_path_patch(),
            patch("ii_bridge.handlers.fetch_commit_diff", side_effect=FetchError("not found")),
        ):
            await _handle_perf_advisor(mock_ws, {"mode": "description", "input": "abc1234", "depth": "quick"})

        fetch_req = mock_ws.last_of_type("fetch_required")
        assert fetch_req is not None
        assert fetch_req["reason"] == "commit_not_found"

    @pytest.mark.asyncio
    async def test_description_file_path_emits_fetch_required_on_error(self, mock_ws):
        from ii_bridge.fetcher import FetchError
        with (
            _make_no_token_patch(),
            _make_repo_path_patch(),
            patch("ii_bridge.handlers.fetch_file_method", side_effect=FetchError("missing")),
        ):
            await _handle_perf_advisor(mock_ws, {"mode": "description", "input": "src/Foo.java#doThing", "depth": "standard"})

        fetch_req = mock_ws.last_of_type("fetch_required")
        assert fetch_req is not None
        assert fetch_req["reason"] == "file_not_found"

    @pytest.mark.asyncio
    async def test_description_file_path_success_emits_complete(self, mock_ws):
        with (
            _make_no_token_patch(),
            _make_repo_path_patch(),
            _make_stream_patch("perf result"),
            patch("ii_bridge.handlers.fetch_file_method", return_value="method body here"),
        ):
            await _handle_perf_advisor(mock_ws, {"mode": "description", "input": "src/Foo.java#doThing", "depth": "full"})

        assert mock_ws.last_of_type("perf_advisor_complete") is not None

    @pytest.mark.asyncio
    async def test_does_not_emit_fix_advisor_events(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch(), _make_repo_path_patch():
            await _handle_perf_advisor(mock_ws, {"mode": "clickup", "input": "AOP-1", "depth": "quick"})

        assert mock_ws.last_of_type("fix_advisor_complete") is None
        assert mock_ws.last_of_type("minimal_fix_complete") is None

    @pytest.mark.asyncio
    async def test_depth_defaults_to_standard(self, mock_ws):
        with _make_no_token_patch(), _make_executor_patch(), _make_stream_patch(), _make_repo_path_patch():
            await _handle_perf_advisor(mock_ws, {"mode": "description", "input": "slow service"})
        assert mock_ws.last_of_type("perf_advisor_complete") is not None


# ── Image extraction ──────────────────────────────────────────────────────────

class TestExtractStacktraceImageHandler:

    @pytest.mark.asyncio
    async def test_empty_image_sends_failed_event(self, mock_ws):
        await _handle_extract_stacktrace_image(mock_ws, {"image_b64": "", "media_type": "image/jpeg"})
        failed = mock_ws.last_of_type("stacktrace_extract_failed")
        assert failed is not None
        assert "No image data" in failed["message"]

    @pytest.mark.asyncio
    async def test_missing_image_key_sends_failed_event(self, mock_ws):
        await _handle_extract_stacktrace_image(mock_ws, {})
        assert mock_ws.last_of_type("stacktrace_extract_failed") is not None

    @pytest.mark.asyncio
    async def test_success_emits_stacktrace_extracted(self, mock_ws):
        extracted = "java.lang.NPE\n\tat com.example.Foo.bar(Foo.java:42)"
        with patch(
            "bridge_modules.shared._run_in_executor",
            new_callable=AsyncMock,
            return_value=extracted,
        ):
            await _handle_extract_stacktrace_image(mock_ws, {
                "image_b64": "abc123",
                "media_type": "image/png",
            })
        event = mock_ws.last_of_type("stacktrace_extracted")
        assert event is not None
        assert event["stacktrace"] == extracted

    @pytest.mark.asyncio
    async def test_extraction_error_emits_failed_event(self, mock_ws):
        from ii_bridge.image_extractor import ExtractionError
        with patch(
            "bridge_modules.shared._run_in_executor",
            new_callable=AsyncMock,
            side_effect=ExtractionError("Not a stack trace"),
        ):
            await _handle_extract_stacktrace_image(mock_ws, {
                "image_b64": "abc123",
                "media_type": "image/jpeg",
            })
        failed = mock_ws.last_of_type("stacktrace_extract_failed")
        assert failed is not None
        assert "Not a stack trace" in failed["message"]

    @pytest.mark.asyncio
    async def test_status_emitted_before_result(self, mock_ws):
        with patch(
            "bridge_modules.shared._run_in_executor",
            new_callable=AsyncMock,
            return_value="NPE trace",
        ):
            await _handle_extract_stacktrace_image(mock_ws, {
                "image_b64": "abc123",
                "media_type": "image/jpeg",
            })
        types = [m["type"] for m in mock_ws.sent]
        assert "status" in types
        assert types.index("status") < types.index("stacktrace_extracted")

    @pytest.mark.asyncio
    async def test_defaults_media_type_to_jpeg(self, mock_ws):
        captured = {}
        async def fake_executor(fn, *args):
            captured["args"] = args
            return "trace"
        with patch("bridge_modules.shared._run_in_executor", side_effect=fake_executor):
            await _handle_extract_stacktrace_image(mock_ws, {"image_b64": "abc123"})
        assert captured["args"][1] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_no_stacktrace_extracted_on_failure(self, mock_ws):
        from ii_bridge.image_extractor import ExtractionError
        with patch(
            "bridge_modules.shared._run_in_executor",
            new_callable=AsyncMock,
            side_effect=ExtractionError("bad image"),
        ):
            await _handle_extract_stacktrace_image(mock_ws, {
                "image_b64": "abc123",
                "media_type": "image/jpeg",
            })
        assert mock_ws.last_of_type("stacktrace_extracted") is None


# ── Wiki save handler ────────────────────────────────────────────────────────

class TestWikiSaveHandler:
    """Tests for _handle_save_to_wiki (user-triggered, borderline confidence path)."""

    @pytest.mark.asyncio
    async def test_wiki_unavailable_emits_save_failed(self, mock_ws):
        with patch("ii_bridge.handlers.WIKI_AVAILABLE", False):
            from ii_bridge.handlers import _handle_save_to_wiki
            await _handle_save_to_wiki(mock_ws, {"report": "some report"})
        msg = mock_ws.last_of_type("wiki_save_failed")
        assert msg is not None
        assert "not available" in msg["message"].lower()

    @pytest.mark.asyncio
    async def test_missing_report_emits_save_failed(self, mock_ws):
        with patch("ii_bridge.handlers.WIKI_AVAILABLE", True):
            from ii_bridge.handlers import _handle_save_to_wiki
            await _handle_save_to_wiki(mock_ws, {"report": ""})
        msg = mock_ws.last_of_type("wiki_save_failed")
        assert msg is not None
        assert "No report" in msg["message"]

    @pytest.mark.asyncio
    async def test_successful_save_emits_wiki_saved(self, mock_ws):
        with (
            patch("ii_bridge.handlers.WIKI_AVAILABLE", True),
            patch(
                "ii_bridge.handlers._save_incident_to_wiki",
                new_callable=AsyncMock,
                return_value="incidents/aop-1234.md",
            ),
        ):
            from ii_bridge.handlers import _handle_save_to_wiki
            await _handle_save_to_wiki(mock_ws, {
                "report": "Confidence: 7/10\nRoot cause: cache miss",
                "analysis": "fix_advisor",
                "confidence": 7,
            })
        msg = mock_ws.last_of_type("wiki_saved")
        assert msg is not None
        assert msg["wiki_path"] == "incidents/aop-1234.md"

    @pytest.mark.asyncio
    async def test_save_exception_emits_save_failed(self, mock_ws):
        with (
            patch("ii_bridge.handlers.WIKI_AVAILABLE", True),
            patch(
                "ii_bridge.handlers._save_incident_to_wiki",
                new_callable=AsyncMock,
                side_effect=RuntimeError("disk full"),
            ),
        ):
            from ii_bridge.handlers import _handle_save_to_wiki
            await _handle_save_to_wiki(mock_ws, {
                "report": "some report",
                "confidence": 7,
            })
        msg = mock_ws.last_of_type("wiki_save_failed")
        assert msg is not None
        assert "disk full" in msg["message"]

    @pytest.mark.asyncio
    async def test_defaults_analysis_to_fix_advisor(self, mock_ws):
        save_mock = AsyncMock(return_value="incidents/anon.md")
        with (
            patch("ii_bridge.handlers.WIKI_AVAILABLE", True),
            patch("ii_bridge.handlers._save_incident_to_wiki", save_mock),
        ):
            from ii_bridge.handlers import _handle_save_to_wiki
            await _handle_save_to_wiki(mock_ws, {"report": "report text"})
        _, _, _, analysis = save_mock.call_args.args
        assert analysis == "fix_advisor"


class TestConfidenceGatedWikiSave:
    """Tests for the wiki save path embedded in _handle_incident_mode."""

    @pytest.mark.asyncio
    async def test_high_confidence_auto_saves(self, mock_ws):
        report = "Confidence: 9/10\nRoot cause determined."
        save_mock = AsyncMock(return_value="incidents/auto.md")
        with (
            _make_no_token_patch(),
            _make_executor_patch(),
            _make_stream_patch(return_value=report),
            patch("ii_bridge.handlers.WIKI_AVAILABLE", True),
            patch("ii_bridge.handlers.parse_confidence_score", return_value=9),
            patch("ii_bridge.handlers._save_incident_to_wiki", save_mock),
        ):
            await _handle_fix_advisor(mock_ws, {"mode": "description", "input": "crash in prod"})

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert complete is not None
        assert complete["wiki_status"] == "saved"
        assert complete["wiki_path"] == "incidents/auto.md"
        save_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_borderline_confidence_returns_prompt_status(self, mock_ws):
        report = "Confidence: 7/10\nPartial analysis."
        with (
            _make_no_token_patch(),
            _make_executor_patch(),
            _make_stream_patch(return_value=report),
            patch("ii_bridge.handlers.WIKI_AVAILABLE", True),
            patch("ii_bridge.handlers.parse_confidence_score", return_value=7),
        ):
            await _handle_fix_advisor(mock_ws, {"mode": "description", "input": "slow query"})

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert complete is not None
        assert complete["wiki_status"] == "prompt"
        assert complete["wiki_path"] is None

    @pytest.mark.asyncio
    async def test_low_confidence_skips_wiki(self, mock_ws):
        report = "Confidence: 4/10\nInsufficient evidence."
        with (
            _make_no_token_patch(),
            _make_executor_patch(),
            _make_stream_patch(return_value=report),
            patch("ii_bridge.handlers.WIKI_AVAILABLE", True),
            patch("ii_bridge.handlers.parse_confidence_score", return_value=4),
        ):
            await _handle_fix_advisor(mock_ws, {"mode": "description", "input": "vague issue"})

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert complete is not None
        assert complete["wiki_status"] == "skipped"
        assert complete["wiki_path"] is None

    @pytest.mark.asyncio
    async def test_wiki_unavailable_skips_silently(self, mock_ws):
        with (
            _make_no_token_patch(),
            _make_executor_patch(),
            _make_stream_patch(),
            patch("ii_bridge.handlers.WIKI_AVAILABLE", False),
        ):
            await _handle_fix_advisor(mock_ws, {"mode": "description", "input": "some issue"})

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert complete is not None
        assert complete["wiki_status"] == "skipped"
        assert complete["confidence"] is None

    @pytest.mark.asyncio
    async def test_perf_advisor_complete_has_no_wiki_fields(self, mock_ws):
        with (
            _make_no_token_patch(),
            _make_executor_patch(),
            _make_stream_patch(),
        ):
            await _handle_perf_advisor(mock_ws, {"mode": "description", "input": "slow query"})

        complete = mock_ws.last_of_type("perf_advisor_complete")
        assert complete is not None
        assert "wiki_status" not in complete
        assert "wiki_path" not in complete
        assert "confidence" not in complete


# ── HANDLERS dict ─────────────────────────────────────────────────────────────

class TestHandlersDict:
    def test_fix_advisor_registered(self):
        assert "fix_advisor_report" in HANDLERS

    def test_minimal_fix_registered(self):
        assert "minimal_fix_report" in HANDLERS

    def test_perf_advisor_registered(self):
        assert "perf_advisor_report" in HANDLERS

    def test_extract_stacktrace_image_registered(self):
        assert "extract_stacktrace_image" in HANDLERS

    def test_handlers_are_callable(self):
        assert callable(HANDLERS["fix_advisor_report"])
        assert callable(HANDLERS["minimal_fix_report"])
        assert callable(HANDLERS["perf_advisor_report"])
        assert callable(HANDLERS["extract_stacktrace_image"])
