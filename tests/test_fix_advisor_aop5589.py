"""
tests/test_fix_advisor_aop5589.py — Regression tests for Fix Advisor using AOP-5589.

AOP-5589: High error rate in ats-sportsbook due to ConcurrentModificationException
during Account persistence (OCA mismatch, 815 errors/hour).

Unit tests (class TestFixAdvisorAOP5589Unit):
  - Fully offline; ClickUp content injected via fixture.
  - Verify correct event sequence, prompt contains ticket-specific terms.

Integration tests (class TestFixAdvisorAOP5589Integration):
  - Marked @pytest.mark.integration — skipped unless CLICKUP_TOKEN is set.
  - Live ClickUp fetch; Claude stream is still mocked.
  - Verify the real ticket is fetchable and its content reaches the prompt.

Run unit tests only (default):
    pytest tests/test_fix_advisor_aop5589.py

Run including integration tests:
    pytest tests/test_fix_advisor_aop5589.py -m integration
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from ii_bridge.handlers import _handle_fix_advisor


# ── Fixtures ──────────────────────────────────────────────────────────────────

# Representative content matching what ClickUp returns for AOP-5589.
# Kept to the essential identifiers so the fixture doesn't rot as the ticket
# description evolves, but is specific enough to validate prompt construction.
AOP5589_FIXTURE = (
    "**AOP-5589: HKJC-QA and DEV – High error rate in ats-sportsbook due to "
    "ConcurrentModificationException during Account persistence**\n"
    "Status: in progress\n\n"
    "The ats-sportsbook service is generating repeated errors while attempting to persist "
    "Account entities. The failures occur during account updates and are caused by a "
    "ConcurrentModificationException triggered by an OCA (Optimistic Concurrency Attribute) "
    "mismatch.\n\n"
    "ats.core.InvalidDataException – Failed to persist entity of type AccountJdbcDao\n"
    "Caused by: java.util.ConcurrentModificationException\n"
    "entityName: Account, id: 795, expected oca: 310, encountered oca: 311\n\n"
    "ats-sportsbook - 815 times within 1h"
)

# Key domain terms that must appear in any prompt built from this ticket.
# These validate that data-gathering output is actually injected into the prompt.
_REQUIRED_PROMPT_TERMS = [
    "AOP-5589",
    "ConcurrentModificationException",
    "AccountJdbcDao",
    "oca",
]


def _make_stream_patch(return_value="mocked fix advisor report"):
    """Patch _stream_claude_to_ws and capture the prompt argument."""
    return patch(
        "bridge_modules.shared._stream_claude_to_ws",
        new_callable=AsyncMock,
        return_value=return_value,
    )


def _make_executor_side_effects(clickup_content: str):
    """
    Return a side_effect callable for _run_in_executor that injects clickup_content
    for the fetch_clickup_task call and returns "" for all other calls (e.g. git log).
    """
    from ii_bridge.clickup_fetcher import fetch_clickup_task as _real_cu

    async def _side_effect(fn, *args, **kwargs):
        if fn is _real_cu:
            return clickup_content
        return ""

    return _side_effect


# ── Unit tests ────────────────────────────────────────────────────────────────

class TestFixAdvisorAOP5589Unit:
    """Offline tests — ClickUp content injected via fixture; no network calls."""

    @pytest.mark.asyncio
    async def test_emits_fix_advisor_complete(self, mock_ws):
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.shared._run_in_executor",
                  side_effect=_make_executor_side_effects(AOP5589_FIXTURE)),
            _make_stream_patch(),
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert complete is not None, "fix_advisor_complete event not emitted"

    @pytest.mark.asyncio
    async def test_complete_carries_report(self, mock_ws):
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.shared._run_in_executor",
                  side_effect=_make_executor_side_effects(AOP5589_FIXTURE)),
            _make_stream_patch("## Fix Advisor — AOP-5589\n\nOCA mismatch…"),
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert "Fix Advisor" in complete["report"]

    @pytest.mark.asyncio
    async def test_prompt_contains_ticket_id(self, mock_ws):
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.shared._run_in_executor",
                  side_effect=_make_executor_side_effects(AOP5589_FIXTURE)),
            _make_stream_patch() as mock_stream,
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        prompt = mock_stream.call_args[0][1]  # positional: ws, prompt, …
        assert "AOP-5589" in prompt, "Ticket ID missing from prompt"

    @pytest.mark.asyncio
    async def test_prompt_contains_domain_terms(self, mock_ws):
        """Key OCA / exception terms from the fixture must reach the prompt."""
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.shared._run_in_executor",
                  side_effect=_make_executor_side_effects(AOP5589_FIXTURE)),
            _make_stream_patch() as mock_stream,
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        prompt = mock_stream.call_args[0][1]
        missing = [t for t in _REQUIRED_PROMPT_TERMS if t.lower() not in prompt.lower()]
        assert not missing, f"Prompt missing expected terms: {missing}"

    @pytest.mark.asyncio
    async def test_status_events_precede_complete(self, mock_ws):
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.shared._run_in_executor",
                  side_effect=_make_executor_side_effects(AOP5589_FIXTURE)),
            _make_stream_patch(),
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        types = [m["type"] for m in mock_ws.sent]
        complete_idx = types.index("fix_advisor_complete")
        assert any(t == "status" for t in types[:complete_idx]), \
            "Expected at least one status event before fix_advisor_complete"

    @pytest.mark.asyncio
    async def test_clickup_status_message_emitted(self, mock_ws):
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.shared._run_in_executor",
                  side_effect=_make_executor_side_effects(AOP5589_FIXTURE)),
            _make_stream_patch(),
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        status_texts = [m["text"] for m in mock_ws.messages_of_type("status")]
        assert any("AOP-5589" in t for t in status_texts), \
            "Expected a status message referencing the ticket ID"

    @pytest.mark.asyncio
    async def test_clickup_fetch_failure_still_produces_report(self, mock_ws):
        """If ClickUp returns None (e.g. token expired), the handler degrades gracefully."""
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.shared._run_in_executor",
                  side_effect=_make_executor_side_effects(None)),  # fetch returns None
            _make_stream_patch("degraded report"),
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert complete is not None, \
            "Handler should still complete when ClickUp fetch returns None"
        assert mock_ws.last_of_type("error") is None, \
            "Handler must not emit an error event for a missing ClickUp ticket"

    @pytest.mark.asyncio
    async def test_no_unexpected_events_emitted(self, mock_ws):
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.shared._run_in_executor",
                  side_effect=_make_executor_side_effects(AOP5589_FIXTURE)),
            _make_stream_patch(),
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        allowed = {"status", "fix_advisor_progress", "fix_advisor_complete"}
        unexpected = {m["type"] for m in mock_ws.sent} - allowed
        assert not unexpected, f"Unexpected event types emitted: {unexpected}"


# ── Integration tests ─────────────────────────────────────────────────────────

def _clickup_token_available() -> bool:
    from pathlib import Path
    token_file = Path.home() / ".claude" / "skills" / "shared" / ".clickup_token"
    env_token  = os.environ.get("CLICKUP_TOKEN", "").strip()
    return bool(env_token or (token_file.exists() and token_file.read_text().strip()))


@pytest.mark.integration
@pytest.mark.skipif(
    not _clickup_token_available(),
    reason="CLICKUP_TOKEN not set and ~/.claude/skills/shared/.clickup_token not present",
)
class TestFixAdvisorAOP5589Integration:
    """
    Live ClickUp fetch; Claude stream is mocked.

    These tests verify that the real AOP-5589 ticket is fetchable and that its
    content reaches the Fix Advisor prompt correctly. Run with:

        pytest tests/test_fix_advisor_aop5589.py -m integration
    """

    def test_clickup_fetch_returns_content(self):
        """Confirm AOP-5589 is fetchable and returns the expected identifiers."""
        from ii_bridge.clickup_fetcher import fetch_clickup_task
        result = fetch_clickup_task("AOP-5589")
        assert result is not None, \
            "fetch_clickup_task returned None — check ClickUp token and ticket ID"
        assert "AOP-5589" in result or "ats-sportsbook" in result.lower(), \
            "Fetched content does not look like the expected ticket"

    def test_clickup_fetch_contains_oca_terms(self):
        """The ticket description must include OCA-related terms."""
        from ii_bridge.clickup_fetcher import fetch_clickup_task
        result = fetch_clickup_task("AOP-5589")
        assert result is not None
        content_lower = result.lower()
        assert "oca" in content_lower or "concurrentmodificationexception" in content_lower, \
            "Expected OCA / ConcurrentModificationException content in live ticket"

    @pytest.mark.asyncio
    async def test_handler_with_live_clickup_emits_complete(self, mock_ws):
        """Full handler run with live ClickUp data; only Claude is mocked."""
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.triage_handlers._git_log_for_keyword", return_value=""),
            _make_stream_patch("## Fix Advisor — AOP-5589 (integration)"),
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        complete = mock_ws.last_of_type("fix_advisor_complete")
        assert complete is not None, "fix_advisor_complete not emitted with live ClickUp data"

    @pytest.mark.asyncio
    async def test_live_clickup_content_reaches_prompt(self, mock_ws):
        """OCA terms from the live ticket must appear in the prompt sent to Claude."""
        with (
            patch("bridge_modules.shared._read_slack_token", return_value=None),
            patch("bridge_modules.triage_handlers._git_log_for_keyword", return_value=""),
            _make_stream_patch() as mock_stream,
        ):
            await _handle_fix_advisor(mock_ws, {
                "mode":          "clickup",
                "input":         "AOP-5589",
                "slack_enabled": False,
            })

        prompt = mock_stream.call_args[0][1]
        missing = [t for t in _REQUIRED_PROMPT_TERMS if t.lower() not in prompt.lower()]
        assert not missing, (
            f"Live ClickUp content did not inject expected terms into prompt: {missing}\n"
            f"Prompt snippet: {prompt[:500]}"
        )
