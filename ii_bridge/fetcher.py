"""
ii_bridge/fetcher.py — Auto-fetch utilities for Performance Advisor.

Pure functions — no WS I/O. All fetch functions raise FetchError on failure so the
calling handler can decide whether to emit a fetch_required event or surface the error.

Public API:
  detect_content_type(raw)                              -> ContentType
  fetch_file_method(file_path, method, repo_roots)      -> str
  fetch_commit_diff(commit_hash, repo_roots)            -> str
"""

from __future__ import annotations

import re
import subprocess
from enum import Enum
from pathlib import Path


# ── Content type classification ───────────────────────────────────────────────

class ContentType(str, Enum):
    COMMIT_HASH = "commit_diff"    # 7–40 hex chars (short or full SHA)
    FILE_METHOD = "file_method"    # src/Foo.java  or  src/Foo.java#methodName
    CODE_BLOCK  = "code_block"     # multi-line input containing Java-like syntax
    FREE_TEXT   = "free_text"      # anything else


_COMMIT_RE = re.compile(r'^[0-9a-f]{7,40}$', re.IGNORECASE)
_FILE_RE   = re.compile(r'^[\w/\-\.]+\.java(?:#\w+)?$')
_JAVA_KEYWORDS = ('{', 'void ', 'public ', 'private ', 'protected ', 'return ', '@', 'class ')


def detect_content_type(raw: str) -> ContentType:
    """Classify the raw description input without touching the filesystem."""
    stripped = raw.strip()
    if _COMMIT_RE.match(stripped):
        return ContentType.COMMIT_HASH
    if _FILE_RE.match(stripped):
        return ContentType.FILE_METHOD
    if '\n' in stripped and any(kw in stripped for kw in _JAVA_KEYWORDS):
        return ContentType.CODE_BLOCK
    return ContentType.FREE_TEXT


# ── Errors ────────────────────────────────────────────────────────────────────

class FetchError(Exception):
    """Raised when auto-fetch fails; message is shown to the user as-is."""


# ── File + method fetch ───────────────────────────────────────────────────────

_MAX_FILE_BYTES = 200_000  # refuse to embed files larger than ~200 KB


def fetch_file_method(file_path: str, method: str | None, repo_roots: list[str]) -> str:
    """
    Locate file_path under any of repo_roots and return its content.
    If method is given, extract only that method body via brace-walking regex.

    Raises FetchError if the file is not found, is too large, or the method
    is not found within the file.
    """
    relative = file_path.lstrip('/')

    for root in repo_roots:
        candidate = Path(root) / relative
        if not candidate.exists():
            continue
        size = candidate.stat().st_size
        if size > _MAX_FILE_BYTES:
            raise FetchError(
                f"File too large ({size // 1024} KB): {candidate}. "
                "Paste the relevant method body directly instead."
            )
        source = candidate.read_text(errors='replace')
        if not method:
            return source
        extracted = _extract_method(source, method)
        if extracted:
            return extracted
        raise FetchError(
            f"Method `{method}` not found in {candidate}. "
            "Paste the method body directly."
        )

    raise FetchError(
        f"File `{file_path}` not found in any known repo. "
        "Check the path or paste the code block directly."
    )


def _extract_method(source: str, method: str) -> str | None:
    """
    Brace-walking method extractor.  Finds the first method signature containing
    `method` and returns the full body including its surrounding braces.

    Works for standard Java formatting. Known limitation: may misbehave on lambda
    expressions or unusual indentation (javalang AST upgrade deferred to a later phase).
    """
    lines = source.splitlines()
    sig_re = re.compile(
        r'\b(?:public|private|protected|static|final|synchronized|default)\b[^(]*\b'
        + re.escape(method)
        + r'\s*\('
    )

    start = next((i for i, line in enumerate(lines) if sig_re.search(line)), None)
    if start is None:
        return None

    depth = 0
    in_body = False
    body_lines: list[str] = []

    for line in lines[start:]:
        body_lines.append(line)
        for ch in line:
            if ch == '{':
                depth += 1
                in_body = True
            elif ch == '}':
                depth -= 1
        if in_body and depth == 0:
            break

    return '\n'.join(body_lines) if body_lines else None


# ── Commit diff fetch ─────────────────────────────────────────────────────────

_MAX_DIFF_LINES = 200


def fetch_commit_diff(commit_hash: str, repo_roots: list[str]) -> str:
    """
    Run `git show` for commit_hash in each repo root until one succeeds.
    Returns at most _MAX_DIFF_LINES lines; appends a truncation notice if clipped.

    Raises FetchError if the commit is not found in any repo.
    """
    for root in repo_roots:
        try:
            result = subprocess.run(
                ['git', 'show', '--stat', '--patch', commit_hash],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
        if result.returncode != 0:
            continue
        lines = result.stdout.splitlines()
        if len(lines) > _MAX_DIFF_LINES:
            return (
                '\n'.join(lines[:_MAX_DIFF_LINES])
                + f'\n\n[...diff truncated at {_MAX_DIFF_LINES} lines...]'
            )
        return '\n'.join(lines)

    raise FetchError(
        f"Commit `{commit_hash}` not found in any known repo. "
        "Verify the hash and ensure the repo is cloned locally."
    )
