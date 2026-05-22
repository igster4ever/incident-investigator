"""
ii_bridge/wiki_integration.py — Bridge between ii_bridge and the wiki synthesis layer.

When running under the GPS·ADR bridge server (port 7432), squad-gps-radar/scripts/
is already on sys.path, making wiki.incident_synthesis importable directly.

When running ii_bridge standalone (tests, dev), this module adds the scripts/
directory to sys.path as a best-effort fallback using Path.home().

Either way, callers import from this module — never directly from wiki.*  —
so that WIKI_AVAILABLE guards correctly and import errors are localised.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── Ensure wiki/ is importable ────────────────────────────────────────────────

_SCRIPTS_DIR = Path.home() / ".claude" / "skills" / "squad-gps-radar" / "scripts"

if _SCRIPTS_DIR.is_dir():
    _s = str(_SCRIPTS_DIR.resolve())
    if _s not in sys.path:
        sys.path.insert(0, _s)

# ── Conditional imports with graceful fallback ────────────────────────────────

try:
    from wiki.incident_synthesis import (  # type: ignore[import]
        parse_confidence_score,
        synthesise_incident,
        merge_incident_article,
        write_incident_article,
        _build_incident_slug,
    )
    WIKI_AVAILABLE = True

except ImportError:
    WIKI_AVAILABLE = False

    def parse_confidence_score(report: str):  # type: ignore[misc]
        return None

    async def synthesise_incident(report, metadata):  # type: ignore[misc]
        raise RuntimeError("wiki.incident_synthesis not available — bridge not running?")

    async def merge_incident_article(existing, new_report, metadata):  # type: ignore[misc]
        raise RuntimeError("wiki.incident_synthesis not available — bridge not running?")

    def write_incident_article(slug, markdown, wiki_dir=None):  # type: ignore[misc]
        raise RuntimeError("wiki.incident_synthesis not available — bridge not running?")

    def _build_incident_slug(ticket_id, analysis):  # type: ignore[misc]
        return f"incident-{analysis}"


__all__ = [
    "WIKI_AVAILABLE",
    "parse_confidence_score",
    "synthesise_incident",
    "merge_incident_article",
    "write_incident_article",
    "_build_incident_slug",
]
