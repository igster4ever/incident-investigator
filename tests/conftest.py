"""
tests/conftest.py — Shared fixtures for incident-investigator tests.

Adds squad-gps-radar/scripts to sys.path so ii_bridge/ can import triage_handlers
and shared bridge utilities. Uses the same HeadlessWs shim pattern as the GPS dashboard.
"""

import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make squad-gps-radar scripts importable (same path the bridge shim adds at runtime)
_BRIDGE_SCRIPTS = Path.home() / ".claude" / "skills" / "squad-gps-radar" / "scripts"
if str(_BRIDGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_SCRIPTS))

# Make the incident-investigator root importable so ii_bridge/ resolves correctly
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Make shared bridge_slack importable
_SHARED = Path.home() / ".claude" / "skills" / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))


class MockWs:
    """Minimal WebSocket double that records outbound messages."""

    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    def messages_of_type(self, event_type: str) -> list[dict]:
        return [m for m in self.sent if m.get("type") == event_type]

    def last_of_type(self, event_type: str) -> dict | None:
        msgs = self.messages_of_type(event_type)
        return msgs[-1] if msgs else None


@pytest.fixture
def mock_ws():
    return MockWs()


@pytest.fixture
def patch_claude_stream():
    """Patch _stream_claude_to_ws to return a fixed string without calling Claude."""
    with patch(
        "bridge_modules.shared._stream_claude_to_ws",
        new_callable=AsyncMock,
        return_value="**mocked report output**",
    ) as mock:
        yield mock


@pytest.fixture
def patch_data_gathering():
    """
    Patch all external data-gathering calls (Slack, git, stacktrace scripts)
    so handler tests run offline with predictable inputs.
    """
    with (
        patch("bridge_modules.shared._read_slack_token", return_value=None),
        patch("bridge_modules.shared._run_in_executor", new_callable=AsyncMock, return_value=""),
    ):
        yield
