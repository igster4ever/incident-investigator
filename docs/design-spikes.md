# Design Spikes — Incident Investigator

## Spike 1: Standalone SPA vs React app

**Question:** Should the frontend be a React/Vite app or a self-contained single HTML file?

**Decision:** Single HTML file.

**Rationale:**
- The GPS·ADR Radar dashboard (source of the Triage/RCA UI) is generated as a single HTML file with all CSS and JS inlined. The Triage/RCA tab (`triage_rca.py`) is already written in this form — adapting it is a straight extraction, not a rewrite.
- No build step means the app can be opened directly from the filesystem (`file://`) or served trivially via any static server. Zero friction to run.
- The UI complexity does not warrant a component framework: three modes, four input types, one output canvas. React would add ~300KB of overhead and a build pipeline for no observable gain.
- If the app grows beyond a single analyst tool into a multi-user dashboard, revisit.

---

## Spike 2: Where should the bridge handlers live?

**Question:** Should `fix_advisor_report` and `minimal_fix_report` handlers live in:
- (A) `squad-gps-radar/scripts/bridge_modules/` directly, or
- (B) `incident-investigator/bridge/` (owned by this project), with a thin shim in squad-gps-radar

**Decision:** Option B — handlers live in `incident-investigator/bridge/`; squad-gps-radar has a thin shim.

**Rationale:**
- The incident-investigator project should own its logic. Burying handlers in the squad-gps-radar skill directory makes this project hard to understand in isolation and complicates future extraction (e.g., if the bridge is replaced by a different backend).
- The shim pattern is established in the codebase: `bridge_handlers_gps.py` is itself a thin re-export. Adding one more is zero ceremony.
- Keeping prompts and handlers in `incident-investigator/bridge/` means the unit tests can import them directly without path hacks.

**Trade-off:** The bridge does have to import from `~/projects/` which is a slightly unusual path. Mitigated by an explicit `sys.path.insert` in the shim with a clear comment.

---

## Spike 3: Re-implement data gathering or import from triage_handlers?

**Question:** The fix-advisor and minimal-fix handlers need the same data-gathering pipeline as `triage_handlers.py` (git log, Slack search, stacktrace parsing). Should we:
- (A) Duplicate the helper functions into `incident-investigator/bridge/handlers.py`, or
- (B) Import them from `triage_handlers.py`

**Decision:** Option B — import helpers from `triage_handlers`.

**Rationale:**
- `_git_log_for_keyword`, `_parse_slack_thread_url`, `_run_stacktrace_parser`, `_run_code_context`, `_run_git_context` are stable, well-tested at runtime, and have no GPS-specific coupling. Duplicating them would be pure redundancy.
- The shim already adds squad-gps-radar/scripts to `sys.path`, so the import is available.
- If this import ever becomes a problem (e.g., squad-gps-radar moves), the helpers can be extracted to `bridge_modules/shared.py` at that point — not before.

---

## Spike 4: Prompt strategy for fix-advisor and minimal-fix

**Question:** Should fix-advisor and minimal-fix prompts use the incident-report skill's `generate_report.py` script (which produces structured JSON + HTML files), or should they produce plain markdown streamed directly to the UI?

**Decision:** Plain markdown streamed to UI; no intermediate JSON or file output.

**Rationale:**
- The Triage/RCA handler streams markdown directly via `_stream_claude_to_ws` and the UI renders it in a monospace pre. This is proven and gives a live streaming experience.
- The incident-report skill's `generate_report.py` is designed for the CLI skill — it writes files to `~/Downloads` and is not wired to a WebSocket. Wiring it into a streaming handler would require buffering the entire response before generating the file, losing the live output.
- The "Save .md" footer button handles persistence: the final report string is offered as a browser download. HTML file generation can be added later if needed.
- Prompt output shape mirrors the skill's structured sections (Repo, Root Cause, Fix Plan, Effort, Risk, Tech Debt) but rendered as markdown headers, not JSON.

---

## Spike 5: Auth — how does the frontend get the bridge token?

**Question:** The bridge requires `Authorization: Bearer <token>` (HTTP) or `?token=<token>` (WebSocket). How does the standalone app obtain the token without a backend?

**Decision:** Read `~/.cache/claude-bridge/state.json` at startup via a `fetch()` call to `http://localhost:7432/health` — the health endpoint returns the token in its response, or fall back to prompting the user to paste it.

**Rationale:**
- `state.json` is written by `bridge_restart.sh` and readable by any local process, but a browser cannot access the filesystem directly.
- The bridge's `/health` endpoint returns `{"ok":true}` — it does not expose the token.
- Simplest viable approach: on first load, if no token is stored in `localStorage`, show a one-time token input. The user pastes the token from `state.json` (or the bridge restart output). Stored in `localStorage["ii_bridge_token"]` and reused thereafter.
- A `Clear token` link in the UI header allows re-entry if the token rotates.
