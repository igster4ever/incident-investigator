"""
ii_bridge/handlers.py — Fix Advisor and Minimal Fix bridge handlers.

Handles:
  type: 'fix_advisor_report'   — repo + root cause + high-level fix + effort/risk
  type: 'minimal_fix_report'   — smallest safe change + effort + tech debt callout

Data-gathering helpers are imported from triage_handlers (not duplicated).
All four input modes are supported: clickup, slack_thread, description, stacktrace.

Emits:
  fix_advisor_progress    { text: str }
  fix_advisor_complete    { report: str }
  minimal_fix_progress    { text: str }
  minimal_fix_complete    { report: str }
  error                   { message: str }

Note: bridge_modules imports are deferred inside functions to break the circular
import that arises when bridge_modules/__init__ imports this module via the shim.
Python's module cache means there is no runtime cost after the first call.
"""

from __future__ import annotations

import json
import re

from ii_bridge.prompts import (
    fix_advisor_clickup,
    fix_advisor_slack_thread,
    fix_advisor_description,
    fix_advisor_stacktrace,
    minimal_fix_clickup,
    minimal_fix_slack_thread,
    minimal_fix_description,
    minimal_fix_stacktrace,
)


# ── Shared data-gathering pipeline ───────────────────────────────────────────

async def _gather_clickup(ws, ticket_id: str, token: str | None) -> tuple[str, str]:
    from bridge_modules.shared import _run_in_executor
    from bridge_modules.triage_handlers import _git_log_for_keyword
    from bridge_slack import _slack_search_channels

    slack_text = ""
    if token:
        await ws.send(json.dumps({"type": "status", "text": f"Searching Slack for {ticket_id}…"}))
        results = await _run_in_executor(_slack_search_channels, token, ticket_id)
        if results:
            slack_text = "\n".join(
                f"[{r.get('channel','?')}] {r.get('text','')[:200]}"
                for r in results[:10]
            )
    await ws.send(json.dumps({"type": "status", "text": f"Running git log for {ticket_id}…"}))
    git_text = await _run_in_executor(_git_log_for_keyword, ticket_id)
    return slack_text, git_text


async def _gather_slack_thread(ws, url: str, token: str | None) -> str:
    from bridge_modules.shared import _run_in_executor
    from bridge_modules.triage_handlers import _parse_slack_thread_url
    from bridge_slack import _slack_fetch_messages_by_id

    await ws.send(json.dumps({"type": "status", "text": "Fetching Slack thread…"}))
    parsed = _parse_slack_thread_url(url)
    if parsed and token:
        channel_id, msg_ts = parsed
        from_ts = float(msg_ts) - 1
        to_ts   = float(msg_ts) + 86400
        text = await _run_in_executor(
            _slack_fetch_messages_by_id, token, channel_id, channel_id, from_ts, to_ts
        )
        return text or f"(Could not fetch thread from URL: {url})"
    return f"(Could not parse or fetch thread: {url})"


async def _gather_description(ws, description: str, token: str | None) -> tuple[str, str]:
    from bridge_modules.shared import _run_in_executor
    from bridge_modules.triage_handlers import _git_log_for_keyword
    from bridge_slack import _slack_search_channels

    words = [
        w for w in re.findall(r"[a-zA-Z]{4,}", description)
        if w.lower() not in {"that", "this", "with", "from", "have", "been", "when", "there", "after"}
    ]
    keywords = list(dict.fromkeys(words))[:3]

    slack_text = ""
    if token and keywords:
        await ws.send(json.dumps({"type": "status", "text": "Searching Slack for keywords…"}))
        for kw in keywords[:2]:
            results = await _run_in_executor(_slack_search_channels, token, kw)
            if results:
                slack_text += "\n".join(
                    f"[{r.get('channel','?')}] {r.get('text','')[:150]}"
                    for r in results[:5]
                ) + "\n"

    git_text = ""
    if keywords:
        await ws.send(json.dumps({"type": "status", "text": "Searching git history…"}))
        for kw in keywords[:2]:
            git_text += await _run_in_executor(_git_log_for_keyword, kw) + "\n"

    return slack_text, git_text


async def _gather_stacktrace(ws, stacktrace: str) -> tuple[dict, str, str]:
    from bridge_modules.shared import _run_in_executor
    from bridge_modules.triage_handlers import _run_stacktrace_parser, _run_code_context, _run_git_context

    await ws.send(json.dumps({"type": "status", "text": "Parsing stacktrace…"}))
    parsed = await _run_in_executor(_run_stacktrace_parser, stacktrace)

    await ws.send(json.dumps({"type": "status", "text": "Fetching code context…"}))
    code_ctx = await _run_in_executor(_run_code_context, parsed)

    await ws.send(json.dumps({"type": "status", "text": "Fetching git history for affected files…"}))
    git_ctx = await _run_in_executor(_run_git_context, parsed)

    return parsed, code_ctx, git_ctx


# ── Generic handler factory ───────────────────────────────────────────────────

async def _handle_incident_mode(
    ws,
    payload: dict,
    *,
    progress_event: str,
    complete_event: str,
    prompt_fns: dict,
) -> None:
    """
    Shared handler skeleton for fix_advisor and minimal_fix.

    prompt_fns must have keys: clickup, slack_thread, description, stacktrace.
    Each value is a callable that returns the prompt string.
    """
    from bridge_modules.shared import _stream_claude_to_ws, _read_slack_token

    mode      = (payload.get("mode")  or "description").strip()
    input_val = (payload.get("input") or "").strip()

    if not input_val:
        await ws.send(json.dumps({"type": "error", "message": "No input provided"}))
        return

    token  = _read_slack_token()
    prompt = ""

    try:
        if mode == "clickup":
            slack_text, git_text = await _gather_clickup(ws, input_val.upper(), token)
            prompt = prompt_fns["clickup"](input_val.upper(), slack_text, git_text)

        elif mode == "slack_thread":
            thread_text = await _gather_slack_thread(ws, input_val, token)
            prompt = prompt_fns["slack_thread"](thread_text)

        elif mode == "description":
            slack_text, git_text = await _gather_description(ws, input_val, token)
            prompt = prompt_fns["description"](input_val, slack_text, git_text)

        elif mode == "stacktrace":
            parsed, code_ctx, git_ctx = await _gather_stacktrace(ws, input_val)
            prompt = prompt_fns["stacktrace"](input_val, parsed, code_ctx, git_ctx)

        else:
            slack_text, git_text = await _gather_description(ws, input_val, token)
            prompt = prompt_fns["description"](input_val, slack_text, git_text)

    except Exception as exc:
        await ws.send(json.dumps({"type": "error", "message": f"Data gathering failed: {exc}"}))
        return

    await ws.send(json.dumps({"type": "status", "text": "Analysing with Claude…"}))
    report = await _stream_claude_to_ws(ws, prompt, progress_event=progress_event)
    await ws.send(json.dumps({"type": complete_event, "report": report}))


# ── Public handlers ───────────────────────────────────────────────────────────

async def _handle_fix_advisor(ws, payload: dict) -> None:
    await _handle_incident_mode(
        ws,
        payload,
        progress_event="fix_advisor_progress",
        complete_event="fix_advisor_complete",
        prompt_fns={
            "clickup":      fix_advisor_clickup,
            "slack_thread": fix_advisor_slack_thread,
            "description":  fix_advisor_description,
            "stacktrace":   fix_advisor_stacktrace,
        },
    )


async def _handle_minimal_fix(ws, payload: dict) -> None:
    await _handle_incident_mode(
        ws,
        payload,
        progress_event="minimal_fix_progress",
        complete_event="minimal_fix_complete",
        prompt_fns={
            "clickup":      minimal_fix_clickup,
            "slack_thread": minimal_fix_slack_thread,
            "description":  minimal_fix_description,
            "stacktrace":   minimal_fix_stacktrace,
        },
    )


HANDLERS = {
    "fix_advisor_report": _handle_fix_advisor,
    "minimal_fix_report": _handle_minimal_fix,
}
