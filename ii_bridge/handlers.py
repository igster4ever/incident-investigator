"""
ii_bridge/handlers.py — Fix Advisor, Minimal Fix, Perf Advisor, and image extraction handlers.

Handles:
  type: 'fix_advisor_report'         — repo + root cause + high-level fix + effort/risk
  type: 'minimal_fix_report'         — smallest safe change + effort + tech debt callout
  type: 'perf_advisor_report'        — bottleneck ID, root cause, resolution
  type: 'extract_stacktrace_image'   — extract verbatim stack trace from a screenshot

Data-gathering helpers are imported from triage_handlers (not duplicated).
All four input modes are supported: clickup, slack_thread, description, stacktrace.

Emits:
  fix_advisor_progress        { text: str }
  fix_advisor_complete        { report: str }
  minimal_fix_progress        { text: str }
  minimal_fix_complete        { report: str }
  perf_advisor_progress       { text: str }
  perf_advisor_complete       { report: str }
  stacktrace_extracted        { stacktrace: str }
  stacktrace_extract_failed   { message: str }
  error                       { message: str }

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
    perf_advisor_clickup_prompt,
    perf_advisor_slack_prompt,
    perf_advisor_description_prompt,
    perf_advisor_stacktrace_prompt,
)
from ii_bridge.fetcher import ContentType, FetchError, detect_content_type, fetch_file_method, fetch_commit_diff
from ii_bridge.clickup_fetcher import fetch_clickup_task
from ii_bridge.wiki_integration import (
    WIKI_AVAILABLE,
    parse_confidence_score,
    synthesise_incident,
    merge_incident_article,
    write_incident_article,
    _build_incident_slug,
)


# ── Wiki save helper ─────────────────────────────────────────────────────────

async def _save_incident_to_wiki(
    payload: dict,
    report: str,
    confidence_int: int,
    analysis: str,
) -> str:
    """
    Synthesise (or merge) a wiki article from the investigation report.
    Returns a relative path string like "incidents/aop-1234.md".
    """
    mode      = (payload.get("mode") or "description").strip()
    input_val = (payload.get("input") or "").strip()
    ticket_id = input_val.upper() if mode == "clickup" else None

    metadata = {
        "analysis":   analysis,
        "mode":       mode,
        "ticket_id":  ticket_id,
        "confidence": confidence_int,
    }

    slug = _build_incident_slug(ticket_id, analysis)

    # Import wiki root lazily so import errors surface only at call time
    try:
        from wiki.index import _WIKI_DIR
        wiki_root = _WIKI_DIR
    except ImportError:
        from pathlib import Path as _P
        wiki_root = _P.home() / ".cache" / "squad-gps-radar" / "wiki"

    existing_path = wiki_root / "incidents" / f"{slug}.md"

    if existing_path.exists():
        existing = existing_path.read_text(encoding="utf-8")
        markdown = await merge_incident_article(existing, report, metadata)
    else:
        markdown = await synthesise_incident(report, metadata)

    written = write_incident_article(slug, markdown)

    # Semantic index — fire-and-forget; does not block the WS response
    try:
        import asyncio as _asyncio
        from wiki.semantic import index_article_async as _idx
        _asyncio.create_task(_idx(written))
    except Exception:
        pass  # semantic index is optional

    return f"incidents/{written.name}"


# ── Shared data-gathering pipeline ───────────────────────────────────────────

async def _gather_clickup(
    ws,
    ticket_id: str,
    token: str | None,
    *,
    slack_enabled: bool = True,
) -> tuple[str, str, str]:
    """Returns (task_content, slack_text, git_text). Any source may be empty on failure."""
    from bridge_modules.shared import _run_in_executor
    from bridge_modules.triage_handlers import _git_log_for_keyword

    # ── ClickUp task content ────────────────────────────────────────────────
    await ws.send(json.dumps({"type": "status", "text": f"Fetching ClickUp task {ticket_id}…"}))
    task_content = await _run_in_executor(fetch_clickup_task, ticket_id) or ""
    if not task_content:
        await ws.send(json.dumps({"type": "status", "text": f"No ClickUp content for {ticket_id} — continuing with Slack + git"}))

    # ── Slack search (optional, degrades gracefully) ────────────────────────
    slack_text = ""
    if slack_enabled and token:
        from bridge_slack import _slack_search_channels
        try:
            await ws.send(json.dumps({"type": "status", "text": f"Searching Slack for {ticket_id}…"}))
            results = await _run_in_executor(_slack_search_channels, token, ticket_id)
            if results:
                slack_text = "\n".join(
                    f"[{r.get('channel','?')}] {r.get('text','')[:200]}"
                    for r in results[:10]
                )
        except Exception:
            await ws.send(json.dumps({"type": "status", "text": "Slack search failed — continuing without it"}))
    elif not slack_enabled:
        await ws.send(json.dumps({"type": "status", "text": "Slack search skipped (disabled)"}))

    # ── Git log ─────────────────────────────────────────────────────────────
    await ws.send(json.dumps({"type": "status", "text": f"Running git log for {ticket_id}…"}))
    git_text = await _run_in_executor(_git_log_for_keyword, ticket_id)

    return task_content, slack_text, git_text


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

    token        = _read_slack_token()
    slack_enabled = bool(payload.get("slack_enabled", True))
    prompt = ""

    try:
        if mode == "clickup":
            task_content, slack_text, git_text = await _gather_clickup(
                ws, input_val.upper(), token, slack_enabled=slack_enabled
            )
            prompt = prompt_fns["clickup"](input_val.upper(), slack_text, git_text, task_content)

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

    # ── Wiki save (confidence-gated) ──────────────────────────────────────────
    analysis    = complete_event.replace("_complete", "")
    conf        = parse_confidence_score(report) if WIKI_AVAILABLE else None
    wiki_status = "skipped"
    wiki_path   = None

    if WIKI_AVAILABLE and conf is not None:
        if conf >= 8:
            await ws.send(json.dumps({"type": "status", "text": "Saving to wiki…"}))
            try:
                wiki_path   = await _save_incident_to_wiki(payload, report, conf, analysis)
                wiki_status = "saved"
            except Exception:
                wiki_status = "skipped"
        elif conf >= 6:
            wiki_status = "prompt"

    await ws.send(json.dumps({
        "type":        complete_event,
        "report":      report,
        "wiki_status": wiki_status,
        "wiki_path":   wiki_path,
        "confidence":  conf,
    }))


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


async def _handle_perf_advisor(ws, payload: dict) -> None:
    from bridge_modules.shared import _stream_claude_to_ws, _read_slack_token
    from bridge_modules.triage_handlers import _REPO_PATH

    mode      = (payload.get("mode")  or "description").strip()
    input_val = (payload.get("input") or "").strip()
    depth     = (payload.get("depth") or "standard").strip()

    if not input_val:
        await ws.send(json.dumps({"type": "error", "message": "No input provided"}))
        return

    token         = _read_slack_token()
    slack_enabled = bool(payload.get("slack_enabled", True))
    repo_roots    = [str(_REPO_PATH)]
    prompt        = ""

    try:
        if mode == "clickup":
            task_content, slack_text, git_text = await _gather_clickup(
                ws, input_val.upper(), token, slack_enabled=slack_enabled
            )
            prompt = perf_advisor_clickup_prompt(input_val.upper(), slack_text, git_text, depth, task_content)

        elif mode == "slack_thread":
            thread_text = await _gather_slack_thread(ws, input_val, token)
            prompt = perf_advisor_slack_prompt(thread_text, depth)

        elif mode == "stacktrace":
            parsed, code_ctx, git_ctx = await _gather_stacktrace(ws, input_val)
            prompt = perf_advisor_stacktrace_prompt(input_val, parsed, code_ctx, git_ctx, depth)

        else:
            # description — detect content type and auto-fetch if needed
            content_type = detect_content_type(input_val)

            if content_type == ContentType.COMMIT_HASH:
                await ws.send(json.dumps({"type": "status", "text": "Fetching commit diff…"}))
                try:
                    content = fetch_commit_diff(input_val, repo_roots)
                    content_source = f"commit_diff:{input_val}"
                except FetchError as exc:
                    await ws.send(json.dumps({
                        "type": "fetch_required",
                        "reason": "commit_not_found",
                        "message": str(exc),
                    }))
                    return

            elif content_type == ContentType.FILE_METHOD:
                await ws.send(json.dumps({"type": "status", "text": "Fetching file/method…"}))
                parts      = input_val.split("#", 1)
                file_path  = parts[0]
                method     = parts[1] if len(parts) > 1 else None
                try:
                    content = fetch_file_method(file_path, method, repo_roots)
                    content_source = f"file_method:{input_val}"
                except FetchError as exc:
                    await ws.send(json.dumps({
                        "type": "fetch_required",
                        "reason": "file_not_found",
                        "message": str(exc),
                    }))
                    return

            elif content_type == ContentType.CODE_BLOCK:
                content        = input_val
                content_source = "code_block"

            else:
                content        = input_val
                content_source = "free_text"

            prompt = perf_advisor_description_prompt(content, content_source, depth)

    except Exception as exc:
        await ws.send(json.dumps({"type": "error", "message": f"Data gathering failed: {exc}"}))
        return

    await ws.send(json.dumps({"type": "status", "text": "Analysing with Claude…"}))
    report = await _stream_claude_to_ws(ws, prompt, progress_event="perf_advisor_progress")
    await ws.send(json.dumps({"type": "perf_advisor_complete", "report": report}))


async def _handle_save_to_wiki(ws, payload: dict) -> None:
    """
    User-triggered wiki save for borderline-confidence reports (6–7/10).
    Payload: { report, analysis, mode, input, confidence }
    Emits: wiki_saved { wiki_path } or wiki_save_failed { message }
    """
    if not WIKI_AVAILABLE:
        await ws.send(json.dumps({"type": "wiki_save_failed", "message": "Wiki module not available"}))
        return

    report = (payload.get("report") or "").strip()
    if not report:
        await ws.send(json.dumps({"type": "wiki_save_failed", "message": "No report in payload"}))
        return

    analysis   = (payload.get("analysis") or "fix_advisor").strip()
    conf_int   = int(payload.get("confidence") or 7)

    await ws.send(json.dumps({"type": "status", "text": "Saving to wiki…"}))
    try:
        wiki_path = await _save_incident_to_wiki(payload, report, conf_int, analysis)
        await ws.send(json.dumps({"type": "wiki_saved", "wiki_path": wiki_path}))
    except Exception as exc:
        await ws.send(json.dumps({"type": "wiki_save_failed", "message": str(exc)}))


async def _handle_extract_stacktrace_image(ws, payload: dict) -> None:
    from bridge_modules.shared import _run_in_executor
    from ii_bridge.image_extractor import ExtractionError, extract_stacktrace_from_image

    image_b64  = (payload.get("image_b64")  or "").strip()
    media_type = (payload.get("media_type") or "image/jpeg").strip()

    if not image_b64:
        await ws.send(json.dumps({"type": "stacktrace_extract_failed", "message": "No image data provided"}))
        return

    await ws.send(json.dumps({"type": "status", "text": "Extracting stack trace from image…"}))

    try:
        stacktrace = await _run_in_executor(extract_stacktrace_from_image, image_b64, media_type)
    except ExtractionError as exc:
        await ws.send(json.dumps({"type": "stacktrace_extract_failed", "message": str(exc)}))
        return

    await ws.send(json.dumps({"type": "stacktrace_extracted", "stacktrace": stacktrace}))


HANDLERS = {
    "fix_advisor_report":        _handle_fix_advisor,
    "minimal_fix_report":        _handle_minimal_fix,
    "perf_advisor_report":       _handle_perf_advisor,
    "extract_stacktrace_image":  _handle_extract_stacktrace_image,
    "save_to_wiki":              _handle_save_to_wiki,
}
