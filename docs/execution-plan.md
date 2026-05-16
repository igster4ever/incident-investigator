# Execution Plan — Incident Investigator

## Phase 1 — Foundation (Session 1, 2026-05-16) ✅ in progress

**Goal:** Working end-to-end for all three analysis modes with a single ClickUp ticket input.

### Tasks
- [x] Project structure: `docs/`, `bridge/`, `tests/`
- [x] `docs/architecture.md` — logical architecture
- [x] `docs/design-spikes.md` — key decisions with rationale
- [x] `docs/execution-plan.md` — this file
- [ ] `bridge/prompts.py` — prompt builder functions for fix-advisor + minimal-fix
- [ ] `bridge/handlers.py` — `fix_advisor_report` + `minimal_fix_report` handlers
- [ ] `bridge/__init__.py` — exports `HANDLERS`
- [ ] `squad-gps-radar/scripts/bridge_modules/incident_handlers.py` — bridge shim
- [ ] Register shim in `bridge_modules/__init__.py`
- [ ] `tests/conftest.py` — mock WS fixture + sys.path setup
- [ ] `tests/test_prompts.py` — pure prompt builder unit tests
- [ ] `tests/test_handlers.py` — handler flow tests with mock WS
- [ ] `pytest.ini`
- [ ] `index.html` — standalone SPA, all 3 modes, all 4 input types
- [ ] Smoke test: bridge restart → ClickUp ticket → all three modes produce output

**Exit criteria:** All three modes return a streamed report for a real ClickUp ticket.

---

## Phase 2 — Polish + Stacktrace UX (Session 2)

**Goal:** Stacktrace mode is first-class; output is structured and scannable.

### Tasks
- [ ] Validate stacktrace mode across all three analysis modes with a real Java exception
- [ ] Tune fix-advisor and minimal-fix prompts based on first real-world outputs
- [ ] Add effort/risk badge rendering — parse `Effort: S` / `Risk: Low` from the markdown
  output and render as coloured inline badges below the output canvas
- [ ] Add "Copy to clipboard" button alongside "Save .md"
- [ ] Keyboard shortcut: `Cmd+Enter` triggers Generate

---

## Phase 3 — Prompt quality + confidence display (Session 3)

**Goal:** Confidence score is surfaced visually; prompts tuned for HKJC monorepo specifics.

### Tasks
- [ ] Parse confidence score from markdown output (`Confidence: N/10`) and render as a
  coloured score badge (green ≥7, amber 4–6, red <4) in the footer after generation
- [ ] Add `--keywords` support to git_collector calls in the new handlers (currently using
  raw git log; the incident-report script produces richer structured JSON)
- [ ] Tune prompts with HKJC service names, package prefixes, and known anti-patterns
- [ ] Add "Regenerate" button that re-runs without clearing the previous output (side-by-side diff)

---

## Phase 4 — History + multi-ticket (Future)

**Goal:** Analyst can review prior investigations and compare across tickets.

### Tasks
- [ ] Investigation history panel — last 10 investigations stored in `localStorage`, clickable to reload
- [ ] Multi-ticket comparison — run fix-advisor across two tickets, render side-by-side
- [ ] Export to ClickUp comment — post the minimal-fix summary as a comment on the ticket
  (requires ClickUp MCP write permission)

---

## Non-goals (deliberately excluded)

- Multi-user / shared state — this is a single-analyst tool
- Authentication beyond bridge token — the bridge is local only
- CI/CD integration — not a pipeline tool
- Code change application — read-only; never writes to the repo
