# Incident Investigator — Claude Context

## What this is

Standalone single-file SPA (`index.html`) for structured incident analysis. No build step —
open directly in a browser. Analysis is delegated to the GPS·ADR Radar bridge server
(port 7432) via WebSocket. The bridge must be running; the app is inoperable without it.

## Module map

| Path | Role |
|------|------|
| `index.html` | Self-contained SPA — all modes, all input types, token gate, themes |
| `ii_bridge/prompts.py` | Pure prompt builder functions — no I/O, fully unit-testable |
| `ii_bridge/handlers.py` | WS handlers — data gathering + streaming to Claude API |
| `ii_bridge/image_extractor.py` | Claude Haiku vision extraction of stack traces from images; `ExtractionError` |
| `ii_bridge/clickup_fetcher.py` | ClickUp REST API client — fetches task name + description by custom task ID; `reset_clickup_cache()` |
| `ii_bridge/connectivity_handler.py` | `_handle_check_connectivity` (ping Slack + ClickUp), `_handle_update_token` (write token file, re-ping, emit status) |
| `ii_bridge/fetcher.py` | Content-type detection; file/method + commit diff auto-fetch for Perf Advisor |
| `ii_bridge/__init__.py` | Exports `HANDLERS` dict |
| `tests/conftest.py` | Mock WS fixture + sys.path wiring |
| `tests/test_prompts.py` | Prompt builder unit tests |
| `tests/test_handlers.py` | Handler flow tests (mock WS); includes TestWikiSaveHandler + TestConfidenceGatedWikiSave |
| `tests/test_connectivity_handler.py` | Connectivity handler unit tests — ping functions, status builders, async handlers |
| `tests/test_image_extractor.py` | Image extractor unit tests |
| `tests/test_fetcher.py` | Fetcher unit tests |
| `tests/test_fix_advisor_aop5589.py` | Regression tests for Fix Advisor — AOP-5589 (OCA/ats-sportsbook); unit + integration |
| `docs/architecture.md` | System diagram, WS event protocol, module ownership |
| `docs/design-spikes.md` | Key design decisions with rationale |
| `docs/execution-plan.md` | Phased delivery plan — current phase and backlog |

The bridge shim lives **outside this repo**:
`squad-gps-radar/scripts/bridge_modules/incident_handlers.py` — routes incoming WS events
to `ii_bridge/handlers.py`. Registered in `bridge_modules/__init__.py`.

## Running

```bash
# No install needed — open the SPA
open index.html

# Bridge must already be running (from the squad-gps-radar project)
# python scripts/bridge_server.py

# Tests
pytest
```

## Key gotchas

**Package name is `ii_bridge/`, not `bridge/`** — avoids a namespace collision with
the GPS dashboard's `bridge` module on `sys.path`. Do not rename it.

**`bridge_modules` imports are deferred inside handler functions** — never at module
level. This breaks the circular import: `bridge_modules/__init__` → `incident_handlers`
→ `ii_bridge`. Python's module cache means there is no runtime cost.

**`prompts.py` must stay pure** — no I/O, no imports from `bridge_modules`. All data
gathering happens in `handlers.py` before the prompt builder is called.

**WS event naming convention** — progress and complete events are prefixed by mode:
`fix_advisor_progress` / `fix_advisor_complete`, `minimal_fix_progress` / `minimal_fix_complete`,
`perf_advisor_progress` / `perf_advisor_complete`. Status messages use the generic
`{"type": "status", "text": "..."}` shape.

**Triage / RCA handler is not in this repo** — it lives in
`squad-gps-radar/scripts/bridge_modules/triage_handlers.py`. Data-gathering helpers
(`_git_log_for_keyword`, etc.) are imported from there rather than duplicated.

**WS message format is `{ type, token, payload }`** — the bridge validates `token` in
every message body (not just the WS connection URL). Handler data must be nested under
`payload`; the bridge does `payload = msg.get("payload", {})` before calling the handler.
Missing either causes a silent `{"type": "error", "message": "Unauthorised"}` response.
The `_send` function in `index.html` handles this — do not flatten payload into the
top-level message object.

**Bridge `state.json` token can be stale** — if the bridge was restarted, `~/.cache/claude-bridge/state.json`
may hold a different token than the running process. When auth fails, verify with
`ps aux | grep bridge` to get the live token from the process args.

**Claude subprocess must not call MCP tools** — `_stream_claude_to_ws` in `shared.py` spawns
`claude -p` with `--allowedTools none`. All prompt builders also prepend `_NO_TOOLS_PREAMBLE`
as a belt-and-braces instruction. Both layers are required: `--allowedTools ""` (empty string)
is silently ignored by the CLI.

**ClickUp token** — store at `~/.claude/skills/shared/.clickup_token` (chmod 600) or set
`CLICKUP_TOKEN` env var. `clickup_fetcher.py` degrades to `None` on any failure — missing
token is not an error. Custom task IDs (e.g. `AOP-5035`) require `?custom_task_ids=true&team_id=`.

**Image extraction** — `image_extractor.py` uses Claude Haiku (`claude-haiku-4-5-20251001`)
via the Anthropic SDK (not the bridge subprocess). The `NOT_A_STACKTRACE` sentinel response
is converted to a user-facing `ExtractionError`. Images are resized client-side to max 1400px
/ JPEG 0.88 before sending; retry at 0.72 quality if still > 1 MB.

## Analysis modes

| Mode | Bridge event | Intent |
|------|-------------|--------|
| Triage / RCA | `triage_report` | Timeline, root cause, remediation (existing handler, not here) |
| Fix Advisor | `fix_advisor_report` | Repo ID, high-level fix, effort/risk |
| Minimal Fix | `minimal_fix_report` | Smallest safe change, effort, tech debt callout |
| Performance Advisor | `perf_advisor_report` | Bottleneck ID, root cause, resolution; depth: Quick / Standard / Full |

## Input types (all modes)

`clickup` · `slack_thread` · `description` · `stacktrace`

Performance Advisor's `description` input also accepts a file path (`src/Foo.java#method`),
a git commit hash, or a raw code block — auto-fetched via `ii_bridge/fetcher.py` (Phase 3).

## Adding a new mode

1. Add prompt builder functions to `ii_bridge/prompts.py` — pure, one function per input type
2. Add a handler to `ii_bridge/handlers.py` — data gathering + prompt call + stream
3. Export the new handler key from `ii_bridge/__init__.py` in `HANDLERS`
4. Add the mode to the bridge shim's dispatch in `bridge_modules/incident_handlers.py`
5. Wire up the new mode in `index.html`
6. Add tests to `tests/test_prompts.py` and `tests/test_handlers.py`
