"""
bridge/prompts.py — Pure prompt builder functions for Fix Advisor and Minimal Fix modes.

All functions are side-effect-free and take only plain Python values — no WS, no I/O.
This makes them straightforwardly unit-testable.

Effort scale:  XS < 2h  |  S 2–8h  |  M 1–3d  |  L 3–10d  |  XL >10d
Risk scale:    Low  |  Medium  |  High  |  Critical
"""

from __future__ import annotations

# ── Fix Advisor prompts ───────────────────────────────────────────────────────

_FIX_ADVISOR_TASK = """\
## Your task

Produce a **Fix Advisor** report with the following sections:

### Identified Repository
State which repo (and service/module within it) owns this issue, and why you are confident.

### Root Cause
Concise diagnosis. Reference actual class names, method names, commit hashes, or Slack
quotes from the evidence. Assign a confidence score (1–10) with one-line reasoning.

### Proposed Fix
Describe the fix at the level of: which file(s) to change, which method/block, and what
the change should do. Be concrete — approximate code is welcome where it helps.

### Affected Files
List the files most likely to require changes (with paths where identifiable).

### Effort Estimate
State: XS / S / M / L / XL and a one-line reasoning.
  XS = < 2 hours | S = 2–8 hours | M = 1–3 days | L = 3–10 days | XL = > 10 days

### Risk Assessment
State: Low / Medium / High / Critical and explain the main risk vector.

### Tech Debt Note
Call out any underlying issue that this fix does not address and should be tracked separately.
"""


def fix_advisor_clickup(ticket_id: str, slack_text: str, git_text: str) -> str:
    return (
        f"You are a senior engineering lead advising on how to fix a reported incident.\n\n"
        f"## Ticket: {ticket_id}\n\n"
        f"## Slack context (mentions of {ticket_id}):\n"
        f"{slack_text or '(no Slack mentions found)'}\n\n"
        f"## Git history (commits referencing {ticket_id}):\n"
        f"{git_text or '(no matching commits)'}\n\n"
        + _FIX_ADVISOR_TASK
    )


def fix_advisor_slack_thread(thread_text: str) -> str:
    return (
        f"You are a senior engineering lead advising on how to fix a reported incident.\n\n"
        f"## Slack thread content:\n{thread_text}\n\n"
        + _FIX_ADVISOR_TASK
    )


def fix_advisor_description(description: str, slack_text: str, git_text: str) -> str:
    return (
        f"You are a senior engineering lead advising on how to fix a reported incident.\n\n"
        f"## Incident description:\n{description}\n\n"
        f"## Related Slack context:\n"
        f"{slack_text or '(no relevant Slack activity found)'}\n\n"
        f"## Related git history:\n"
        f"{git_text or '(no matching commits found)'}\n\n"
        + _FIX_ADVISOR_TASK
    )


def fix_advisor_stacktrace(
    stacktrace: str,
    parsed: dict,
    code_ctx: str,
    git_ctx: str,
) -> str:
    exception_type = (parsed.get("primary_exception") or {}).get("type", "Unknown")
    exception_msg  = (parsed.get("primary_exception") or {}).get("message", "")
    services       = parsed.get("affected_services") or []
    frames         = [
        f.get("class_method", "")
        for f in (parsed.get("all_project_frames") or [])[:5]
    ]
    return (
        f"You are a senior engineering lead advising on how to fix a Java exception.\n\n"
        f"## Exception: {exception_type}\n"
        f"Message: {exception_msg}\n"
        f"Affected services: {', '.join(services) or 'unknown'}\n"
        f"Top project frames: {', '.join(f for f in frames if f) or 'none'}\n\n"
        f"## Code context at crash site:\n{code_ctx or '(unavailable)'}\n\n"
        f"## Recent git history for affected files:\n{git_ctx or '(unavailable)'}\n\n"
        f"## Raw stack trace (first 40 lines):\n"
        f"{chr(10).join(stacktrace.splitlines()[:40])}\n\n"
        + _FIX_ADVISOR_TASK
    )


# ── Minimal Fix prompts ───────────────────────────────────────────────────────

_MINIMAL_FIX_TASK = """\
## Your task

Produce a **Minimal Fix** report. Focus on the smallest safe change — not the ideal
long-term fix. Assume the engineer wants to unblock production with minimum blast radius.

### Identified Repository
State which repo (and service/module) owns this issue, and why.

### Root Cause (brief)
One paragraph. Reference specific classes/methods/commits where available.
Confidence score (1–10) with one-line reasoning.

### Minimal Fix
Describe the single smallest change that resolves the immediate issue safely.
Be specific: file path, method, line-level description, and approximate code change.

### Affected Files
List only the files the minimal fix touches — no speculative scope creep.

### Effort Estimate
XS / S / M / L / XL with one-line reasoning.

### Risk Assessment
Low / Medium / High / Critical — focus on the risk of *this specific minimal change*,
not the risk of leaving the underlying issue.

### Tech Debt Left Behind
Be explicit about what the minimal fix deliberately does NOT address.
List 2–4 concrete follow-up items that should be tracked separately.
"""


def minimal_fix_clickup(ticket_id: str, slack_text: str, git_text: str) -> str:
    return (
        f"You are a senior engineering lead advising on the smallest safe fix for a reported incident.\n\n"
        f"## Ticket: {ticket_id}\n\n"
        f"## Slack context (mentions of {ticket_id}):\n"
        f"{slack_text or '(no Slack mentions found)'}\n\n"
        f"## Git history (commits referencing {ticket_id}):\n"
        f"{git_text or '(no matching commits)'}\n\n"
        + _MINIMAL_FIX_TASK
    )


def minimal_fix_slack_thread(thread_text: str) -> str:
    return (
        f"You are a senior engineering lead advising on the smallest safe fix for a reported incident.\n\n"
        f"## Slack thread content:\n{thread_text}\n\n"
        + _MINIMAL_FIX_TASK
    )


def minimal_fix_description(description: str, slack_text: str, git_text: str) -> str:
    return (
        f"You are a senior engineering lead advising on the smallest safe fix for a reported incident.\n\n"
        f"## Incident description:\n{description}\n\n"
        f"## Related Slack context:\n"
        f"{slack_text or '(no relevant Slack activity found)'}\n\n"
        f"## Related git history:\n"
        f"{git_text or '(no matching commits found)'}\n\n"
        + _MINIMAL_FIX_TASK
    )


def minimal_fix_stacktrace(
    stacktrace: str,
    parsed: dict,
    code_ctx: str,
    git_ctx: str,
) -> str:
    exception_type = (parsed.get("primary_exception") or {}).get("type", "Unknown")
    exception_msg  = (parsed.get("primary_exception") or {}).get("message", "")
    services       = parsed.get("affected_services") or []
    frames         = [
        f.get("class_method", "")
        for f in (parsed.get("all_project_frames") or [])[:5]
    ]
    return (
        f"You are a senior engineering lead advising on the smallest safe fix for a Java exception.\n\n"
        f"## Exception: {exception_type}\n"
        f"Message: {exception_msg}\n"
        f"Affected services: {', '.join(services) or 'unknown'}\n"
        f"Top project frames: {', '.join(f for f in frames if f) or 'none'}\n\n"
        f"## Code context at crash site:\n{code_ctx or '(unavailable)'}\n\n"
        f"## Recent git history for affected files:\n{git_ctx or '(unavailable)'}\n\n"
        f"## Raw stack trace (first 40 lines):\n"
        f"{chr(10).join(stacktrace.splitlines()[:40])}\n\n"
        + _MINIMAL_FIX_TASK
    )
