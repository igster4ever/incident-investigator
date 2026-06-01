"""
ii_bridge/token_utils.py — Shared token-reading helpers.

Token resolution:
  ClickUp — CLICKUP_TOKEN env var → ~/.claude/skills/shared/.clickup_token
  Slack   — ~/.claude/skills/shared/.slack_token
"""

from __future__ import annotations

import os
from pathlib import Path

_SHARED_DIR = Path.home() / ".claude" / "skills" / "shared"

CLICKUP_TOKEN_PATH = _SHARED_DIR / ".clickup_token"
SLACK_TOKEN_PATH   = _SHARED_DIR / ".slack_token"


def read_token_file(path: Path) -> str | None:
    if path.exists():
        tok = path.read_text().strip()
        return tok or None
    return None


def read_clickup_token() -> str | None:
    tok = os.environ.get("CLICKUP_TOKEN", "").strip()
    if tok:
        return tok
    return read_token_file(CLICKUP_TOKEN_PATH)


def read_slack_token() -> str | None:
    return read_token_file(SLACK_TOKEN_PATH)
