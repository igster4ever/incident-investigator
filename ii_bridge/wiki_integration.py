"""
ii_bridge/wiki_integration.py — Bridge between ii_bridge and the wiki synthesis layer.

When running under the GPS·ADR bridge server (port 7432), squad-gps-radar/scripts/
is already on sys.path, making wiki.incident_synthesis importable directly.

When running ii_bridge standalone (tests, dev), _ensure_wiki_importable() adds the
scripts/ directory to sys.path as a best-effort fallback using Path.home().

Either way, callers import from this module — never directly from wiki.*  —
so that WIKI_AVAILABLE guards correctly and import errors are localised.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


# ── Lazy sys.path patch (called only inside the try block below) ──────────────

def _ensure_wiki_importable() -> None:
    """Best-effort sys.path patch for standalone / test usage. No-op in bridge context."""
    scripts_dir = Path.home() / ".claude" / "skills" / "squad-gps-radar" / "scripts"
    if scripts_dir.is_dir():
        s = str(scripts_dir.resolve())
        if s not in sys.path:
            sys.path.insert(0, s)


# ── Conditional imports with graceful fallback ────────────────────────────────

try:
    _ensure_wiki_importable()
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


# ── Filesystem helpers (own the wiki I/O boundary) ───────────────────────────

def load_existing_article(slug: str) -> Optional[str]:
    """
    Return the existing markdown for the given incident slug, or None if absent.
    Owns the wiki-root resolution so handlers.py stays free of Path logic.
    """
    try:
        from wiki.index import _WIKI_DIR as _WD  # type: ignore[import]
        wiki_root = _WD
    except ImportError:
        wiki_root = Path.home() / ".cache" / "squad-gps-radar" / "wiki"

    path = wiki_root / "incidents" / f"{slug}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


__all__ = [
    "WIKI_AVAILABLE",
    "parse_confidence_score",
    "synthesise_incident",
    "merge_incident_article",
    "write_incident_article",
    "load_existing_article",
    "_build_incident_slug",
]
