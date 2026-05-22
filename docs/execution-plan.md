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

## Session H — Incident Wiki Integration (2026-05-22) ✅

**Goal:** At the end of a successful investigation, auto-save (or prompt to save) a wiki
article to the GPS Wiki `incidents` axis. View the article inline via an HTMX-powered panel.

### Completed
- [x] `wiki/incident_synthesis.py` — `parse_confidence_score`, `synthesise_incident`,
  `merge_incident_article`, `write_incident_article`; existing article → merge, new → create
- [x] `ii_bridge/wiki_integration.py` — sys.path adapter; `WIKI_AVAILABLE` flag + graceful stubs
- [x] `wiki/index.py` — `"incidents"` added to `_AXES`
- [x] `bridge_server/wiki_routes.py` — `"incidents"` in activity AXES;
  new `GET /wiki/article-html/{path}` SSR endpoint (markdown → HTML fragment for HTMX)
- [x] `ii_bridge/handlers.py` — confidence parsing after report complete:
  ≥8/10 auto-save → `wiki_status:"saved"`, 6–7/10 → `wiki_status:"prompt"`, ≤5 → `"skipped"`;
  new `_handle_save_to_wiki` handler registered as `"save_to_wiki"` in HANDLERS
- [x] `index.html` — HTMX 2.0 CDN; Report / Wiki tab bar; wiki panel (`htmx.ajax` on tab open);
  borderline confidence save chip; "View Wiki" + "↗ GPS Wiki" footer buttons

**Confidence thresholds (non-negotiable, do not change without discussion):**
- ≥ 8/10 → auto-save silently
- 6–7/10 → prompt user with "Confidence N/10 — save to wiki?" chip
- ≤ 5/10 → skip entirely

**HTMX Phase 1 note:** This session introduced HTMX to the SPA. The wiki panel is the
first HTMX interaction. Phases 3.6 and 3.7 (below) build on this foundation.

---

## Phase 3.6 — Integration Connectivity & Token Refresh

**Goal:** Surface the health of Slack and ClickUp integrations in the UI, and allow a user
to submit a fresh API token without restarting the bridge or touching the terminal.

**Motivation:** Token expiry for both integrations has caused repeated silent failures and
friction (Slack search silently degraded; ClickUp fetch returned `None` with no visible
feedback). This phase makes integration status visible and self-serviceable from the UI.

---

### WS event contract

| Direction | Event | Payload |
|-----------|-------|---------|
| client → bridge | `check_connectivity` | `{}` (no data needed) |
| bridge → client | `connectivity_status` | `{ slack: ConnStatus, clickup: ConnStatus }` |
| client → bridge | `update_token` | `{ integration: "slack" \| "clickup", token: "<new token>" }` |
| bridge → client | `token_updated` | `{ integration: str, ok: bool, error?: str }` |

```
ConnStatus = {
  ok:        bool,          # API ping succeeded
  token_set: bool,          # token file exists and is non-empty
  error?:    str            # human-readable error if ok=false
}
```

`check_connectivity` and `update_token` follow the same `{ type, token, payload }` envelope
as all other bridge messages.

---

### Bridge handler design

**New file:** `ii_bridge/connectivity_handler.py`

Two handlers — `_handle_check_connectivity` and `_handle_update_token` — both
delegated to from a single entry in `HANDLERS`:

```
"check_connectivity": _handle_check_connectivity
"update_token":       _handle_update_token
```

#### `_handle_check_connectivity`

For each integration, attempt a lightweight read API call:

| Integration | Endpoint | Success condition |
|-------------|----------|-------------------|
| ClickUp | `GET /api/v2/user` (with stored token) | HTTP 200 |
| Slack | `GET https://slack.com/api/auth.test` (with stored token, `Authorization: Bearer <tok>`) | `{"ok": true}` in JSON body |

Both calls run via `_run_in_executor` to avoid blocking the async loop.
`token_set` is true if the respective token file exists and is non-empty, regardless of
whether the API call succeeds. This lets the UI distinguish "no token at all" from
"token set but expired".

Emit `connectivity_status` once both checks complete (parallel is fine).

#### `_handle_update_token`

1. Validate `integration` is one of `"slack"` or `"clickup"`.
2. Validate `token` is non-empty.
3. Write token to the relevant file:
   - Slack → `~/.claude/skills/shared/.slack_token`
   - ClickUp → `~/.claude/skills/shared/.clickup_token`
4. Do a quick API ping (same as connectivity check) to confirm the new token works.
5. Emit `token_updated { integration, ok, error? }`.
6. Also emit an updated `connectivity_status` after a successful write, so the UI
   reflects the new state without requiring a second check.

**Note:** `clickup_fetcher.py` caches `_CACHE_TEAM_ID` at module level. On token update,
this cache must be invalidated so the next ClickUp call fetches a fresh team ID with the
new token. Export a `reset_clickup_cache()` function from `clickup_fetcher.py` for this.

---

### Token file paths

| Integration | File | Fallback |
|-------------|------|---------|
| ClickUp | `~/.claude/skills/shared/.clickup_token` | `CLICKUP_TOKEN` env var |
| Slack | `~/.claude/skills/shared/.slack_token` | — (no env var fallback currently) |

Both files should be `chmod 600` after write. Use `Path.chmod(0o600)` after `write_text`.

---

### UI spec

**Location:** a small "Connections" section appended to the settings/utility area, below
the existing Slack toggle. It should be always-visible when the bridge is connected (not
hidden behind any mode selector).

**Components:**

```
[ ⚡ Connections ]  ← collapsible section header, collapsed by default

  Slack     [●] Connected      ← green dot
  ClickUp   [●] Token missing  ← amber dot (token_set=false)
            [─────────────────────] [Update]  ← token input + submit

            [↻ Check]  ← re-runs check_connectivity
```

**Status dot colours:**
- `ok=true`  → green (`#22c55e`)
- `ok=false, token_set=true` → red (`#ef4444`) with short error message
- `ok=false, token_set=false` → amber (`#f59e0b`) — "No token"

**Behaviour:**
- On bridge connect, `check_connectivity` is sent automatically (on WS `open` event).
- The token input is always visible when `ok=false` for that integration; hidden when
  `ok=true` (no need to replace a working token).
- Submitting an empty token field is a no-op (disabled button state).
- After `token_updated { ok: true }`, the input collapses and the dot goes green.
- After `token_updated { ok: false }`, show `error` inline beneath the input.
- The connections section is collapsed by default; the dot in the header reflects the
  worst status (`red > amber > green`) so a problem is visible without expanding.

**WS message shape (client → bridge):**

```js
_send('check_connectivity', {});

_send('update_token', {
  integration: 'slack',   // or 'clickup'
  token: inputValue.trim()
});
```

---

### New files

- `ii_bridge/connectivity_handler.py` — `_handle_check_connectivity`, `_handle_update_token`
- `tests/test_connectivity_handler.py` — unit tests (mock HTTP calls, mock file writes)

### Changes to existing files

- `ii_bridge/handlers.py` — import and add two new keys to `HANDLERS`
- `ii_bridge/__init__.py` — no change (already exports `HANDLERS`)
- `ii_bridge/clickup_fetcher.py` — add `reset_clickup_cache()` to clear `_CACHE_TEAM_ID`
- `bridge_modules/incident_handlers.py` — no change (re-exports `HANDLERS` automatically)
- `index.html` — Connections section in settings area; `check_connectivity` on WS open

### Tests

- Mock HTTP calls for ClickUp `/user` and Slack `auth.test`
- Verify correct file is written for each integration, with `chmod 600`
- Verify `_CACHE_TEAM_ID` is cleared on token update
- Verify `token_updated` is emitted followed by a fresh `connectivity_status`
- Verify `ok=false` + `error` is emitted when the new token fails the ping

**Exit criteria:** Bridge connected → Connections section shows status automatically →
user pastes a fresh Slack token → dot goes green → subsequent Slack-mode analysis
uses the new token without bridge restart.

**⚠ HTMX implementation note (decided 2026-05-22):** The Connections strip is an ideal
HTMX Phase 2 target. Rather than hand-rolling fetch + DOM manipulation, implement with:
- `hx-post="/bridge/check-connectivity"` + `hx-trigger="load, every 60s"` on the strip div
- Bridge returns a pre-rendered HTML fragment (status dots + labels)
- Token update input: `hx-post="/bridge/update-token"`, server returns updated strip HTML
This removes ~30 lines of JS and keeps the SPA declarative. The SSR endpoint pattern is
already established by `GET /wiki/article-html/{path}` from Session H.

---

## Phase 3.7 — HTMX WebSocket Streaming (Future)

**Goal:** Replace the hand-rolled WS event loop with HTMX's WebSocket extension. The server
emits HTML fragments rather than JSON; HTMX injects them via out-of-band (OOB) swaps.

**Why:** Removes ~200 lines of JS dispatch/DOM manipulation. Server owns all rendering logic.
The SPA becomes a thin hypermedia shell — closer to zero custom JS.

### Architecture change

Current (JSON over WS):
```
server → { type: "fix_advisor_progress", text: "..." }
JS     → document.getElementById('output').textContent += msg.text
```

Target (HTML over WS via HTMX OOB):
```
server → <pre id="output" hx-swap-oob="beforeend">...next chunk...</pre>
          <span id="wiki-status" hx-swap-oob="outerHTML"><a href="...">Saved ✓</a></span>
HTMX   → injects both fragments in one message, no JS needed
```

### Prerequisites
- Phase 3.6 complete (HTMX already active in SPA)
- Bridge handlers refactored to emit HTML strings instead of JSON progress events
- `hx-ext="ws"` on the WS connect div; `ws-connect` attribute replaces `_connect()` JS

### Scope
This is a full rewrite of the streaming output model. Treat as its own dedicated session.
Not a prerequisite for any other phase.

---

## Phase 4 — Prompt quality + confidence display (Session 4)

**Goal:** Confidence score is surfaced visually; prompts tuned for HKJC monorepo specifics.

### Tasks
- [x] Parse confidence score from markdown output (`Confidence: N/10`) — done in Session H
  (`wiki/incident_synthesis.py::parse_confidence_score`); used for wiki-save gating
- [ ] Render confidence as a coloured score badge in the footer after generation
  (green ≥8, amber 6–7, red ≤5) — parsing exists, badge UI still pending
- [ ] Add `--keywords` support to git_collector calls in the new handlers (currently using
  raw git log; the incident-report script produces richer structured JSON)
- [ ] Tune prompts with HKJC service names, package prefixes, and known anti-patterns
- [ ] Add "Regenerate" button that re-runs without clearing the previous output (side-by-side diff)

---

## Session I — Semantic Search Core (squad-gps-radar)

**Goal:** LanceDB + Voyage AI index live; `GET /wiki/search` serving hybrid (vector + BM25)
results across all wiki axes; existing articles backfilled; on-demand indexing wired into
the article write paths.

**Tech decisions (2026-05-22):**
- **Store:** LanceDB (file-backed, in-process, native hybrid search via Tantivy + HNSW)
- **Embedder:** Voyage AI `voyage-3-lite` (512-dim, async client, same API key as Claude)
- **Hybrid mode:** RRF re-ranking (vector + FTS in a single LanceDB query)
- **Existing FTS5 (`wiki/fts.db`) unchanged** — keyword `POST /wiki/search` stays as-is;
  semantic layer is strictly additive

**LanceDB table schema:**
```
wiki_articles (
    id          TEXT PRIMARY KEY   -- sha256(path), upsert key
    path        TEXT               -- e.g. "incidents/aop-1234.md"
    axis        TEXT               -- squads | customers | … | incidents
    slug        TEXT
    title       TEXT
    body        TEXT               -- full markdown (for FTS sub-index)
    risk        TEXT
    confidence  FLOAT
    indexed_at  TEXT               -- ISO timestamp
    vector      ARRAY(FLOAT, 512)  -- voyage-3-lite
)
```

### New files
- [ ] `wiki/semantic.py` — `index_article_async(path)`, `search_semantic(q, axes, limit, mode)`,
  `build_semantic_index(wiki_dir)`; LanceDB table init; Voyage AI async embed client;
  model version stored in table metadata (rebuild required on model change)

### Changes to existing files
- [ ] `requirements.txt` (bridge server) — add `lancedb`, `voyageai`
- [ ] `bridge_server/wiki_routes.py` — `GET /wiki/search?q&axes&limit&mode=hybrid`;
  graceful FTS5 fallback when semantic index absent;
  `POST /wiki/rebuild-index?type=semantic` one-off management endpoint
- [ ] `wiki_routes.py` article write call sites — fire-and-forget
  `asyncio.create_task(index_article_async(path))` after `write_ticket_article`
  and `write_incident_article`
- [ ] `build_wiki.py` — call `build_semantic_index()` after `build_fts_index()`

### Response shape (`GET /wiki/search`)
```json
{
  "ok": true,
  "query": "bet-placement latency",
  "axes": ["incidents", "tickets"],
  "mode": "hybrid",
  "results": [
    {
      "path": "incidents/aop-1234.md",
      "axis": "incidents",
      "title": "Bet Placement Latency Spike 2026-04-12",
      "snippet": "…p99 latency spiked to 4.2s…",
      "score": 0.87,
      "confidence": 0.9,
      "match_type": "hybrid"
    }
  ],
  "count": 7
}
```

### Risks / constraints
- Embedding model version drift: document model version in LanceDB table metadata;
  full rebuild required if model changes — do not change model silently
- LanceDB FTS sub-index is rebuilt explicitly (`create_fts_index(replace=True)`) on
  full rebuild cycles; on-demand path is vector-only for the just-indexed article
- `pyarrow` (~70 MB) is a hard dep of `lancedb` — one-off install cost only

**Exit criteria:**
- `POST /wiki/rebuild-index` backfills all existing articles without error
- `GET /wiki/search?q=bet-placement+latency&axes=incidents,tickets` returns ranked results
- A new incident synthesis auto-triggers indexing (fire-and-forget; does not delay WS response)
- `mode=keyword` falls back to FTS5; `mode=semantic` or `mode=hybrid` uses LanceDB

---

## Session J — wiki-frontend Search Panel (wiki-frontend)

**Goal:** Cross-axis semantic search available from the wiki SPA; related articles visible
in axis detail views. Depends on Session I endpoint being live.

### New files
- [ ] `src/components/SearchPanel.tsx` — search input, axis filter chips (multi-select),
  results list grouped by axis; confidence badge + match_type pill per result;
  debounced input (300 ms); empty-safe (no results state)

### Changes to existing files
- [ ] `src/api/types.ts` — `WikiSearchResult`, `WikiSearchResponse` interfaces
- [ ] `src/api/client.ts` — `wiki.search(q, axes?, limit?, mode?)` → `GET /wiki/search`
- [ ] `src/App.tsx` — `{ type: "search" }` view + nav entry (`🔍 Search`); SearchPanel
  wired in centre column
- [ ] Axis detail panels (starting with `TicketsPanel`, `IncidentsPanel`) — "Related"
  section: on article open, call `wiki.search(title, neighbourAxes, 5)` and render
  compact result list beneath article body

**Exit criteria:**
- Search box returns hybrid results across all axes
- Axis filter chips narrow results correctly; clearing filter returns all axes
- Opening a ticket article shows ≤5 semantically related incidents/themes

---

## Session K — incident-investigator Related Incidents (incident-investigator)

**Goal:** Every investigation report surfaces semantically similar past incidents via HTMX,
with no new JS required. Depends on Session I endpoint being live.

### New endpoint (squad-gps-radar)
- [ ] `bridge_server/wiki_routes.py` — `GET /wiki/related-html?q=...&axes=incidents&limit=5`
  SSR HTML fragment (extends `article-html` pattern); empty-safe (`<p class="wh-none">`)

### Changes to existing files (incident-investigator)
- [ ] `index.html` — `<div id="related-incidents" hx-get="/wiki/related-html?q=..."
  hx-trigger="revealed" hx-swap="innerHTML">` injected after report renders;
  query string built from `ticket_id` — no extra LLM call;
  `hx-trigger="revealed"` defers fetch until section scrolls into view

**Notes:**
- Empty-safe: if semantic index absent or no results, fragment renders a single
  "No related incidents found" line — never an error state in the UI
- HTMX pattern already established by Session H `article-html` endpoint

**Exit criteria:**
- Fix Advisor report for AOP-XXXX renders a populated "Related incidents" section
- Section appears empty (not errored) when index is absent or query returns nothing
- No new JS added to `index.html`

---

## Future — RAG injection + GPS dashboard semantic enrichment

Deferred until Session K search quality is validated in practice.

- **RAG:** replace `POST /wiki/ask`'s FTS5 context selection with `search_semantic()` —
  same call shape, improved context relevance for Fix/Perf Advisor prompts
- **GPS dashboard:** "Related articles" in `EventDetailPanel` for `wiki.*` / `incidents.*`
  stream events; driven by same `GET /wiki/search` endpoint

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
