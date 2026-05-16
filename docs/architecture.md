# Incident Investigator — Logical Architecture

## Overview

Incident Investigator is a standalone single-page web application for structured incident
analysis. It connects to the GPS·ADR Radar bridge server (shared infrastructure) and exposes
three analysis modes, each mapping to a distinct investigative intent.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER (browser)                               │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │              index.html  (standalone SPA)                    │  │
│   │                                                              │  │
│   │  ┌──────────────────────────────────────────────────────┐   │  │
│   │  │  Analysis mode selector                              │   │  │
│   │  │  [ Triage / RCA ]  [ Fix Advisor ]  [ Minimal Fix ]  │   │  │
│   │  └──────────────────────────────────────────────────────┘   │  │
│   │                                                              │  │
│   │  ┌──────────────────────────────────────────────────────┐   │  │
│   │  │  Input type selector + input field/textarea          │   │  │
│   │  │  [ ClickUp ]  [ Slack Thread ]  [ Description ]      │   │  │
│   │  │  [ Stacktrace ]                                       │   │  │
│   │  └──────────────────────────────────────────────────────┘   │  │
│   │                                                              │  │
│   │  ┌──────────────────────────────────────────────────────┐   │  │
│   │  │  Streaming output canvas (monospace, themeable)      │   │  │
│   │  │  + Thinking panel (collapsible)                      │   │  │
│   │  └──────────────────────────────────────────────────────┘   │  │
│   │                                                              │  │
│   │  ┌──────────────────────────────────────────────────────┐   │  │
│   │  │  Footer: [Code Changes] [Save .md]  (mode-sensitive) │   │  │
│   │  └──────────────────────────────────────────────────────┘   │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                         │  WebSocket ws://localhost:7432/ws         │
└─────────────────────────┼───────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────────┐
│              GPS·ADR Bridge Server  (port 7432)                     │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  bridge_modules/incident_handlers.py  (shim)               │    │
│  │   └── delegates to incident-investigator/bridge/            │    │
│  │         handlers.py                                         │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  bridge_modules/triage_handlers.py  (existing)             │    │
│  │   ├── triage_report handler                                 │    │
│  │   └── triage_followup handler                              │    │
│  └────────────────────────────────────────────────────────────┘    │
└──────────────┬──────────────────┬──────────────────────────────────┘
               │                  │
    ┌──────────▼──┐      ┌────────▼──────────────────────────────┐
    │  Claude API │      │  Local data sources                   │
    │  (streaming)│      │  ├── git log  (be-hkjc-mono)          │
    └─────────────┘      │  ├── Slack search  (bridge_slack)     │
                         │  ├── ClickUp  (MCP)                   │
                         │  ├── java-stacktrace-analyser scripts │
                         │  └── incident-report scripts          │
                         └───────────────────────────────────────┘
```

---

## Analysis Modes

| Mode | Bridge event | Prompt target | Footer actions |
|---|---|---|---|
| **Triage / RCA** | `triage_report` / `triage_followup` | Full forensic analysis: timeline, root cause, remediation | Code Change Suggestions, Save .md |
| **Fix Advisor** | `fix_advisor_report` | Repo identification, high-level fix, effort (XS–XL), risk (Low–Critical) | Save .md |
| **Minimal Fix** | `minimal_fix_report` | Smallest safe change, affected files, effort, tech debt callout | Save .md |

## Input Types

All four input types are available for all three analysis modes:

| Input type | Data gathered |
|---|---|
| **ClickUp Ticket** | Slack mentions + git log by ticket ID |
| **Slack Thread** | Full thread fetched via bridge_slack |
| **Description** | Keywords extracted → Slack search + git log |
| **Stacktrace** | Parse → code context → git history for affected files |

---

## WebSocket Event Protocol

### Fix Advisor
```
FE → bridge:  { type: "fix_advisor_report", mode: "clickup|slack_thread|description|stacktrace", input: "..." }
bridge → FE:  { type: "status", text: "..." }            (progress status messages)
bridge → FE:  { type: "thinking", text: "..." }          (Claude reasoning, optional)
bridge → FE:  { type: "fix_advisor_progress", text: "..." }
bridge → FE:  { type: "fix_advisor_complete", report: "..." }
```

### Minimal Fix
```
FE → bridge:  { type: "minimal_fix_report", mode: "...", input: "..." }
bridge → FE:  { type: "status", text: "..." }
bridge → FE:  { type: "minimal_fix_progress", text: "..." }
bridge → FE:  { type: "minimal_fix_complete", report: "..." }
```

### Triage / RCA (existing, unchanged)
```
FE → bridge:  { type: "triage_report", mode: "...", input: "..." }
bridge → FE:  { type: "triage_progress", text: "...", lines: N }
bridge → FE:  { type: "triage_complete", report: "..." }

FE → bridge:  { type: "triage_followup", triage_report: "...", mode: "...", input: "..." }
bridge → FE:  { type: "triage_followup_progress", text: "..." }
bridge → FE:  { type: "triage_followup_complete", suggestions: "..." }
```

---

## Module Ownership

| Concern | Owner |
|---|---|
| Frontend SPA | `incident-investigator/index.html` |
| Fix Advisor + Minimal Fix prompts | `incident-investigator/bridge/prompts.py` |
| Fix Advisor + Minimal Fix handlers | `incident-investigator/bridge/handlers.py` |
| Bridge shim (routes WS events to handlers) | `squad-gps-radar/scripts/bridge_modules/incident_handlers.py` |
| Triage / RCA handlers | `squad-gps-radar/scripts/bridge_modules/triage_handlers.py` (unchanged) |
| Data-gathering helpers (git, Slack, stacktrace) | `triage_handlers.py` (imported, not duplicated) |
| Unit tests | `incident-investigator/tests/` |

---

## Bridge Token

The frontend reads the bridge auth token from `~/.cache/claude-bridge/state.json`:
```json
{ "pid": 12345, "port": 7432, "token": "abc123..." }
```

The token is passed as a query parameter on the WebSocket connection:
```
ws://localhost:7432/ws?token=abc123
```

---

## Key Constraints

- **No build step** — `index.html` is self-contained; open directly in a browser
- **Bridge dependency** — the app is inoperable without the bridge running on port 7432
- **Read-only** — no ClickUp comments posted, no Slack channel messages, no code changes
- **Slack DM** — the incident-report skill sends a DM to the authenticated user only; the
  bridge handlers do not replicate this behaviour (report is surfaced in the UI instead)
- **Git scope** — 30-day rolling window via `git_collector.py`; adjustable via handler config
