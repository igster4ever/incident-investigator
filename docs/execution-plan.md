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

## Phase 3 — Performance Advisor (Session 3)

**Goal:** Add a 4th analysis mode — Performance Advisor — enabling engineers to identify,
understand, and resolve performance bottlenecks from a stacktrace, code block, file+method
reference, git commit, or ClickUp ticket.

### New files
- [ ] `ii_bridge/fetcher.py` — auto-fetch utility: `fetch_file_method` + `fetch_commit_diff`
  (uses same known repo list as triage handlers; pure functions, no WS I/O)

### `ii_bridge/prompts.py` additions
- [ ] `_perf_depth_instructions(depth)` — private helper returning the format/depth block
  for `"quick"` | `"standard"` | `"full"`
- [ ] `perf_advisor_clickup_prompt(ticket_data, depth)`
- [ ] `perf_advisor_slack_prompt(thread_content, depth)`
- [ ] `perf_advisor_description_prompt(content, content_source, depth)`
  — `content_source` is one of: `"code_block"`, `"file_method:<path>#<method>"`,
    `"commit_diff:<hash>"`, `"free_text"`
- [ ] `perf_advisor_stacktrace_prompt(stacktrace, depth)`

### `ii_bridge/handlers.py` additions
- [ ] `performance_advisor_report` WS handler
  — detects content type from raw description input (commit hash regex, file path
    heuristic, multi-line code block, free text)
  — calls `fetcher.fetch_file_method` or `fetcher.fetch_commit_diff` as appropriate
  — on fetch failure emits `{"type": "fetch_required", "reason": "...", "message": "..."}`
    before returning (UI shows inline warning; user pastes and resubmits)
  — calls the appropriate prompt builder, streams report back

### `index.html` changes
- [ ] Add "Performance Advisor" as 4th option in the intent selector
- [ ] Add depth selector within Performance Advisor mode:
  — "Quick scan" (~1–2k tokens) / "Full report" (~2–4k tokens) / "Deep dive" (~4–8k tokens)
- [ ] Contextual placeholder + ℹ tooltip on Description input when mode = Performance Advisor:
  — placeholder: `Paste a code block  —OR—  enter a file path (e.g. src/Foo.java#myMethod)  —OR—  enter a git commit hash`
  — tooltip: worked examples for each input variant
- [ ] Handle `fetch_required` WS event: inline warning below Description input, input stays
  active for paste fallback

### Tests
- [ ] `tests/test_prompts.py` additions — prompt builder unit tests for all 4 input types
  × 3 depth levels (12 cases) + depth instructions helper
- [ ] `tests/test_fetcher.py` — unit tests for `fetch_file_method` and `fetch_commit_diff`
  (happy path + not-found + file-too-large + commit-not-found)
- [ ] `tests/test_handlers.py` additions — handler flow tests: content-type detection,
  fetch-success path, fetch-failure / `fetch_required` emission

### Report structure
Three depth tiers, user-selectable:

| Tier | Bottlenecks | Root cause | Effort/Risk | Alternatives | Approx tokens |
|------|-------------|------------|-------------|--------------|---------------|
| Quick | Top 3, 1-sentence fix | 1 sentence | No | No | ~1–2k |
| Standard | Top 5, 2–3 sentence fix | 2–3 sentences | Yes (badges) | No | ~2–4k |
| Full | Exhaustive | Detailed | Yes (badges) | Yes + caveats | ~4–8k |

All tiers end with `Confidence: N/10`.

### Known limitations / future work
- Method body extraction uses brace-walking regex — works for standard Java formatting;
  may misbehave on lambdas or unusual indentation. Upgrade to `javalang` AST parser
  in a later phase if extraction proves unreliable in practice.
- Commit diff truncated at 200 lines — large refactor commits will be clipped.
  Future: smart truncation (keep changed method bodies, drop boilerplate).

**Exit criteria:** All four input types × all three depth tiers produce a streamed
Performance Advisor report against real HKJC code. `fetch_required` fallback confirmed
working for an unknown file path.

---

## Phase 3.5 — PNG Stack Trace Input (Session 4 or 5)

**Goal:** Accept a screenshot of a Java stack trace (PNG/JPEG) as an alternative to pasting text.
Vision extraction runs via Claude; extracted text populates the stacktrace textarea for user review before analysis.

### Pipeline
Upload/paste image → client-side Canvas resize (max 1 400px, JPEG 0.88) → WS `extract_stacktrace_image`
→ Claude vision extraction → `stacktrace_extracted` → textarea populated → normal analysis flow.

### New files
- [ ] `ii_bridge/image_extractor.py` — `extract_stacktrace_from_image(image_b64, media_type) -> str`;
  raises `ExtractionError`. Pure function, no WS I/O.

### `ii_bridge/handlers.py` additions
- [ ] `extract_stacktrace_image` handler — call extractor, emit `stacktrace_extracted { text }`
  or `stacktrace_extract_failed { reason }` on `ExtractionError` / `NOT_A_STACKTRACE` response

### `ii_bridge/__init__.py` + bridge shim
- [ ] Export `extract_stacktrace_image` handler; register in `bridge_modules/incident_handlers.py`

### Tests
- [ ] `tests/test_image_extractor.py` — happy path, `ExtractionError`, `NOT_A_STACKTRACE` response
- [ ] `tests/test_handlers.py` additions — handler happy/fail paths (mock extractor)

### `index.html` changes
- [ ] File input (`accept="image/*"`) + `Cmd/Ctrl+V` clipboard paste detection in stacktrace panel
- [ ] Client-side Canvas resize pipeline: max 1 400px longest side → JPEG 0.88; retry at 0.72 if >1 MB;
  reject if source < 100px on either dimension
- [ ] Image thumbnail (max 120×60px) + × clear button shown after upload
- [ ] Extraction status: `"Extracting stack trace from image…"` while in-flight
- [ ] Handle `stacktrace_extracted` (populate textarea) and `stacktrace_extract_failed` (inline error)

### Claude extraction prompt
> "You are extracting text from a screenshot of a Java stack trace. Return only the raw stack trace
> exactly as shown — preserve all package names, class names, method names, line numbers, and exception
> messages verbatim. Do not summarise, annotate, or add commentary. If the image does not contain a
> stack trace, respond with exactly: NOT_A_STACKTRACE"

**Exit criteria:** Upload a PNG screenshot of a real HKJC stack trace → extracted text appears in
textarea → Fix Advisor / Minimal Fix produces a valid report from it.

---

## Phase 4 — Prompt quality + confidence display (Session 4)

**Goal:** Confidence score is surfaced visually; prompts tuned for HKJC monorepo specifics.

### Tasks
- [ ] Parse confidence score from markdown output (`Confidence: N/10`) and render as a
  coloured score badge (green ≥7, amber 4–6, red <4) in the footer after generation
- [ ] Add `--keywords` support to git_collector calls in the new handlers (currently using
  raw git log; the incident-report script produces richer structured JSON)
- [ ] Tune prompts with HKJC service names, package prefixes, and known anti-patterns
- [ ] Add "Regenerate" button that re-runs without clearing the previous output (side-by-side diff)

---

## Phase 5 — History + multi-ticket (Future)

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
