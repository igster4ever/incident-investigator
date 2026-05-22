# Wiki Incident Generation Flow

Covers the end-to-end journey from the user submitting an inquiry in the SPA to a
rendered wiki article appearing in the output panel.

---

## Overview

```
  Browser (index.html)
        │
        │  WebSocket frame  {"type": "fix_advisor" | "minimal_fix" | "perf_advisor", ...}
        ▼
  ii_bridge / handlers.py
        │
        │  streams LLM tokens back to browser via WS
        │
        │  on completion → parse confidence → decide wiki action
        │
        ├─── conf ≥ 8  ──────────────────────────────────────────► auto-save
        │
        ├─── conf 6–7  ──────────────────────────────────────────► prompt user
        │                                                            (chip in footer)
        │
        └─── conf ≤ 5 / WIKI_AVAILABLE=False ───────────────────► skip (no wiki UI)
```

---

## Detailed Flow

### 1. User submits inquiry

```
┌─────────────────────────────────────────────────────────────────────┐
│  index.html                                                         │
│                                                                     │
│   [Ticket ID input]  [Incident description textarea]                │
│   [Fix Advisor ▶]  [Minimal Fix ▶]  [Perf Advisor ▶]               │
│                                                                     │
│   onclick → iiRun('fix_advisor')                                    │
│           → _send('fix_advisor', { ticket_id, description, ... })  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                    WebSocket message
                    {
                      "type":        "fix_advisor",
                      "ticket_id":   "AOP-1234",
                      "description": "..."
                    }
                                │
                                ▼
```

### 2. Bridge receives and streams the investigation

```
┌─────────────────────────────────────────────────────────────────────┐
│  ii_bridge/handlers.py                                              │
│                                                                     │
│   HANDLERS["fix_advisor"] → _handle_fix_advisor()                  │
│       └─► _handle_incident_mode(ws, payload,                       │
│               analysis="fix_advisor",                               │
│               complete_event="fix_advisor_complete")                │
│                                                                     │
│   ① Calls Claude (Fix Advisor / Minimal Fix / Perf Advisor prompt)  │
│      Tokens streamed back as: {"type": "token", "text": "..."}      │
│                                                                     │
│   ② Full report assembled in memory                                 │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                     report string complete
                                │
                                ▼
```

### 3. Confidence gate

```
┌─────────────────────────────────────────────────────────────────────┐
│  ii_bridge/handlers.py  →  ii_bridge/wiki_integration.py           │
│                                                                     │
│   conf = parse_confidence_score(report)                             │
│       ↳ regex: "Confidence[: ]+(\d+)\s*/\s*10"                     │
│       ↳ returns int 1–10, or None if pattern absent                 │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │  WIKI_AVAILABLE?  (import guard in wiki_integration.py)     │  │
│   │  False → wiki_status = "skipped"  ──────────────────────►  │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│   if conf ≥ 8 ──────────────────────────────────────────────────►  │
│       await _save_incident_to_wiki(...)     [auto, silent]          │
│       wiki_status = "saved"                                         │
│       wiki_path   = "incidents/<slug>.md"                           │
│                                                                     │
│   elif conf ≥ 6 ────────────────────────────────────────────────►  │
│       wiki_status = "prompt"               [deferred to user]       │
│       wiki_path   = None                                            │
│                                                                     │
│   else conf ≤ 5 ────────────────────────────────────────────────►  │
│       wiki_status = "skipped"                                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
```

### 4. Article synthesis (auto-save path, or user-triggered save)

```
┌─────────────────────────────────────────────────────────────────────┐
│  ii_bridge/handlers.py  →  _save_incident_to_wiki()                │
│                                                                     │
│   slug = _build_incident_slug(ticket_id, analysis)                 │
│       ↳ ticket_id present  →  "aop-1234"                           │
│       ↳ ticket_id absent   →  "incident-fix_advisor-20260522T..."   │
│                                                                     │
│   existing_path = wiki_root / "incidents" / f"{slug}.md"           │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │  file exists?                                               │  │
│   │                                                             │  │
│   │  YES → merge_incident_article(existing, report, metadata)  │  │
│   │        Claude: preserve original findings,                  │  │
│   │                append "## Investigation History" section,   │  │
│   │                update confidence + synthesised_at           │  │
│   │                                                             │  │
│   │  NO  → synthesise_incident(report, metadata)               │  │
│   │        Claude: write fresh structured article               │  │
│   │                with YAML frontmatter                        │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│   write_incident_article(slug, markdown)                           │
│       ↳ writes to  wiki/incidents/<slug>.md                        │
│       ↳ slug overridden by Claude's frontmatter if different       │
│                                                                     │
│   returns "incidents/<slug>.md"                                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                wiki path returned to _handle_incident_mode
                                │
                                ▼
```

### 5. Complete event sent to browser

```
┌─────────────────────────────────────────────────────────────────────┐
│  ii_bridge/handlers.py                                              │
│                                                                     │
│   ws.send({                                                         │
│     "type":        "fix_advisor_complete",                          │
│     "report":      "<full markdown report>",                        │
│     "wiki_status": "saved" | "prompt" | "skipped",                  │
│     "wiki_path":   "incidents/aop-1234.md"  (or null),             │
│     "confidence":  8                        (or null)              │
│   })                                                                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                    WebSocket message
                                │
                                ▼
```

### 6. Browser reacts to wiki_status

```
┌─────────────────────────────────────────────────────────────────────┐
│  index.html  →  _onComplete(report, msg)                           │
│                                                                     │
│   wiki_status = "saved"                                             │
│   ├─ _showWikiActions(wikiPath)                                     │
│   │       shows [📖 View Wiki] button + external wiki link          │
│   └─ output tab bar becomes visible (Report / Wiki tabs)            │
│                                                                     │
│   wiki_status = "prompt"                                            │
│   ├─ _wikiPending = true                                            │
│   ├─ _showWikiChip("Confidence N/10 — save to wiki?")              │
│   │       chip shows [📚 Save to Wiki] and [✕ Dismiss]             │
│   └─ user can trigger manual save (see path B below)               │
│                                                                     │
│   wiki_status = "skipped"                                           │
│   └─ no wiki UI shown                                               │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                    (path A: saved)          (path B: user clicks save)
                     │                                │
                     ▼                                ▼
```

### Path A — User clicks "View Wiki" tab

```
┌─────────────────────────────────────────────────────────────────────┐
│  index.html  →  iiShowTab('wiki')                                  │
│                                                                     │
│   if _wikiPath && #wiki-content not yet loaded:                    │
│       htmx.ajax('GET',                                              │
│           'http://localhost:7432/wiki/article-html/' + _wikiPath,  │
│           { target: '#wiki-content', swap: 'innerHTML' })          │
│                                                                     │
│   (subsequent tab toggles do NOT re-fetch)                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                        HTTP GET
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  bridge_server/wiki_routes.py                                       │
│  GET /wiki/article-html/{path}                                      │
│                                                                     │
│   ① path traversal guard (rejects "../" sequences)                 │
│   ② get_article(path) from wiki/index.py                           │
│   ③ _render_markdown(body)                                          │
│       → python-markdown (fenced_code + tables extensions)          │
│       → fallback: html.escape() + <pre> if markdown not installed  │
│   ④ build HTML fragment:                                            │
│                                                                     │
│   <div class="wh-article">                                          │
│     <div class="wh-header">                                         │
│       <h1>{title}</h1>                                              │
│       <span class="wh-conf-hi/mid/lo">conf {N}/10</span>           │
│       <a href="{clickup_url}">ClickUp ↗</a>   (if present)        │
│       <span>{synthesised_at}</span>                                 │
│     </div>                                                          │
│     <div class="wh-body">{rendered HTML}</div>                      │
│   </div>                                                            │
│                                                                     │
│   returns HTMLResponse (text/html)                                  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                        HTML fragment
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  HTMX swaps fragment into #wiki-content                             │
│  User sees rendered article inside the Wiki tab                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Path B — User triggers manual save (confidence 6–7/10)

```
┌─────────────────────────────────────────────────────────────────────┐
│  index.html  →  iiSaveToWiki()                                     │
│                                                                     │
│   _send('save_to_wiki', {                                           │
│     report:    _lastReport,                                         │
│     ticket_id: ...,                                                 │
│     analysis:  ...,                                                 │
│     confidence: ...                                                 │
│   })                                                                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                    WebSocket message
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ii_bridge/handlers.py                                              │
│  HANDLERS["save_to_wiki"] → _handle_save_to_wiki(ws, payload)      │
│                                                                     │
│   → _save_incident_to_wiki(...)   (same synthesis path as auto)    │
│                                                                     │
│   on success:  ws.send({"type": "wiki_saved",      "wiki_path": …})│
│   on failure:  ws.send({"type": "wiki_save_failed","message":  …}) │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                    wiki_saved / wiki_save_failed
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  index.html  dispatch                                               │
│                                                                     │
│   wiki_saved      → _wikiPath set, _showWikiActions(), tab shows   │
│   wiki_save_failed → status bar error message                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module responsibilities

```
┌────────────────────────┬──────────────────────────────────────────────────────────┐
│ Module                 │ Responsibility                                           │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ index.html             │ UI state machine; WebSocket comms; HTMX wiki tab         │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ ii_bridge/handlers.py  │ Orchestrates investigation, confidence gate, auto-save   │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ ii_bridge/             │ sys.path adapter; WIKI_AVAILABLE flag; graceful stubs    │
│   wiki_integration.py  │ when squad-gps-radar scripts are not reachable           │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ wiki/                  │ Claude synthesis and merge prompts; filesystem write;     │
│   incident_synthesis.py│ slug derivation; confidence regex parser                 │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ bridge_server/         │ SSR endpoint; markdown → HTML; path traversal guard;     │
│   wiki_routes.py       │ returns HTMLResponse fragment consumed by HTMX           │
└────────────────────────┴──────────────────────────────────────────────────────────┘
```

---

## Confidence thresholds (decided 2026-05-22)

```
  Score    Action
  ──────   ──────────────────────────────────────────────────────
  ≥ 8/10   Auto-save silently; complete event carries wiki_path
  6–7/10   Return wiki_status:"prompt"; SPA shows save chip
  ≤ 5/10   Skip entirely; no wiki UI shown
  absent   Treated as skipped (regex found nothing)
```

---

## Merge vs create

```
  wiki/incidents/<slug>.md exists?
       │
       YES ──► merge_incident_article()
       │         Claude merges: preserves original findings,
       │         appends ## Investigation History section,
       │         updates confidence + synthesised_at frontmatter
       │
       NO  ──► synthesise_incident()
                 Claude writes: fresh article with YAML frontmatter
                 (slug, ticket_id, analysis, confidence, synthesised_at)
```
