"""
ii_bridge/clickup_fetcher.py — Fetch ClickUp task content via REST API.

Pure function — no WS I/O. Returns None on any failure so callers degrade
gracefully rather than erroring.

Token resolution order:
  1. CLICKUP_TOKEN env var
  2. ~/.claude/skills/shared/.clickup_token file

To set up: paste your ClickUp personal API token into that file, or set the
env var before starting the bridge.
"""

from __future__ import annotations

import os
import urllib.request
import urllib.error
import json
from pathlib import Path

_TOKEN_PATH = Path.home() / ".claude" / "skills" / "shared" / ".clickup_token"
_API_BASE   = "https://api.clickup.com/api/v2"

_CACHE_TEAM_ID: str | None = None


class ClickUpError(Exception):
    pass


def _read_token() -> str | None:
    tok = os.environ.get("CLICKUP_TOKEN", "").strip()
    if tok:
        return tok
    if _TOKEN_PATH.exists():
        tok = _TOKEN_PATH.read_text().strip()
        return tok or None
    return None


def _get(path: str, token: str) -> dict:
    url = f"{_API_BASE}{path}"
    req = urllib.request.Request(url, headers={"Authorization": token})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise ClickUpError(f"ClickUp API {exc.code}: {exc.reason}") from exc
    except Exception as exc:
        raise ClickUpError(str(exc)) from exc


def _get_team_id(token: str) -> str:
    global _CACHE_TEAM_ID
    if _CACHE_TEAM_ID:
        return _CACHE_TEAM_ID
    data = _get("/team", token)
    teams = data.get("teams", [])
    if not teams:
        raise ClickUpError("No ClickUp workspaces found for this token")
    _CACHE_TEAM_ID = str(teams[0]["id"])
    return _CACHE_TEAM_ID


def reset_clickup_cache() -> None:
    """Clear the cached team ID — call after writing a new ClickUp token."""
    global _CACHE_TEAM_ID
    _CACHE_TEAM_ID = None


def fetch_clickup_task(ticket_id: str) -> str | None:
    """
    Fetch task name + description for a custom task ID (e.g. "AOP-5035").

    Returns a formatted string on success, None on any failure (missing token,
    network error, task not found).
    """
    token = _read_token()
    if not token:
        return None

    try:
        team_id = _get_team_id(token)
        data = _get(
            f"/task/{ticket_id}?custom_task_ids=true&team_id={team_id}",
            token,
        )
    except ClickUpError:
        return None

    name   = data.get("name", "").strip()
    desc   = (data.get("text_content") or data.get("description") or "").strip()
    status = (data.get("status") or {}).get("status", "").strip()

    if not name:
        return None

    parts = [f"**{ticket_id}: {name}**"]
    if status:
        parts.append(f"Status: {status}")
    if desc:
        parts.append(f"\n{desc[:2000]}")  # cap at 2000 chars to avoid bloating the prompt

    return "\n".join(parts)
