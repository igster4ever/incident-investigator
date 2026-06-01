"""
ii_bridge/connectivity_handler.py — Integration health check and token refresh handlers.

Handles:
  type: 'check_connectivity'  — ping Slack + ClickUp APIs, emit status
  type: 'update_token'        — write new token file + re-ping + emit updated status

Token files:
  Slack   → ~/.claude/skills/shared/.slack_token   (chmod 600)
  ClickUp → ~/.claude/skills/shared/.clickup_token (chmod 600)

Emits:
  connectivity_status  { slack: ConnStatus, clickup: ConnStatus }
  token_updated        { integration: str, ok: bool, error?: str }
  error                { message: str }

ConnStatus = { ok: bool, token_set: bool, error?: str }

Note: bridge_modules imports are deferred inside async functions — same pattern as
handlers.py — to avoid circular imports at module load.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
import urllib.error

from ii_bridge.token_utils import (
    CLICKUP_TOKEN_PATH  as _CLICKUP_TOKEN_PATH,
    SLACK_TOKEN_PATH    as _SLACK_TOKEN_PATH,
    read_token_file     as _read_token_file,
    read_clickup_token,
    read_slack_token,
)

_CLICKUP_API_BASE = "https://api.clickup.com/api/v2"
_SLACK_API_BASE   = "https://slack.com/api"


# ── API pings (synchronous — run via _run_in_executor) ───────────────────────

def _ping_clickup(token: str) -> tuple[bool, str | None]:
    url = f"{_CLICKUP_API_BASE}/user"
    req = urllib.request.Request(url, headers={"Authorization": token})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200, None
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return False, str(exc)


def _ping_slack(token: str) -> tuple[bool, str | None]:
    url = f"{_SLACK_API_BASE}/auth.test"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return True, None
            return False, data.get("error", "Unknown error")
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return False, str(exc)


# ── Status builders (synchronous) ────────────────────────────────────────────

def _check_slack() -> dict:
    token = read_slack_token()
    token_set = token is not None
    if token:
        ok, error = _ping_slack(token)
    else:
        ok, error = False, "No token configured"
    result: dict = {"ok": ok, "token_set": token_set}
    if error:
        result["error"] = error
    return result


def _check_clickup() -> dict:
    token = read_clickup_token()
    token_set = bool(_read_token_file(_CLICKUP_TOKEN_PATH))
    if token:
        ok, error = _ping_clickup(token)
    else:
        ok, error = False, "No token configured"
    result: dict = {"ok": ok, "token_set": token_set}
    if error:
        result["error"] = error
    return result


# ── Async handlers ───────────────────────────────────────────────────────────

async def _handle_check_connectivity(ws, payload: dict) -> None:
    from bridge_modules.shared import _run_in_executor

    await ws.send(json.dumps({"type": "status", "text": "Checking integrations…"}))

    slack_status, clickup_status = await asyncio.gather(
        _run_in_executor(_check_slack),
        _run_in_executor(_check_clickup),
    )

    await ws.send(json.dumps({
        "type":    "connectivity_status",
        "slack":   slack_status,
        "clickup": clickup_status,
    }))


async def _handle_update_token(ws, payload: dict) -> None:
    from bridge_modules.shared import _run_in_executor

    integration = (payload.get("integration") or "").strip()
    token       = (payload.get("token")       or "").strip()

    if integration not in ("slack", "clickup"):
        await ws.send(json.dumps({
            "type":        "token_updated",
            "integration": integration,
            "ok":          False,
            "error":       f"Unknown integration: {integration!r}",
        }))
        return

    if not token:
        await ws.send(json.dumps({
            "type":        "token_updated",
            "integration": integration,
            "ok":          False,
            "error":       "Token must not be empty",
        }))
        return

    token_path = _SLACK_TOKEN_PATH if integration == "slack" else _CLICKUP_TOKEN_PATH
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token)
    token_path.chmod(0o600)

    if integration == "clickup":
        from ii_bridge.clickup_fetcher import reset_clickup_cache
        reset_clickup_cache()

    ping = _ping_slack if integration == "slack" else _ping_clickup
    ok, error = await _run_in_executor(ping, token)

    msg: dict = {"type": "token_updated", "integration": integration, "ok": ok}
    if error:
        msg["error"] = error
    await ws.send(json.dumps(msg))

    if ok:
        slack_status, clickup_status = await asyncio.gather(
            _run_in_executor(_check_slack),
            _run_in_executor(_check_clickup),
        )
        await ws.send(json.dumps({
            "type":    "connectivity_status",
            "slack":   slack_status,
            "clickup": clickup_status,
        }))
