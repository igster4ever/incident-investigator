"""
tests/test_fetcher.py — Unit tests for ii_bridge/fetcher.py.

Covers:
  - detect_content_type: all four variants
  - fetch_file_method: happy path, not-found, file-too-large, method-not-found
  - fetch_commit_diff: happy path, truncation, not-found, git timeout
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ii_bridge.fetcher import (
    ContentType,
    FetchError,
    _MAX_DIFF_LINES,
    _MAX_FILE_BYTES,
    _extract_method,
    detect_content_type,
    fetch_commit_diff,
    fetch_file_method,
)


# ── detect_content_type ───────────────────────────────────────────────────────

class TestDetectContentType:

    def test_short_sha_is_commit(self):
        assert detect_content_type("a1b2c3d") == ContentType.COMMIT_HASH

    def test_full_sha_is_commit(self):
        assert detect_content_type("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2") == ContentType.COMMIT_HASH

    def test_uppercase_sha_is_commit(self):
        assert detect_content_type("DEADBEEF123") == ContentType.COMMIT_HASH

    def test_java_file_path_is_file_method(self):
        assert detect_content_type("src/main/java/com/example/Foo.java") == ContentType.FILE_METHOD

    def test_file_with_method_anchor_is_file_method(self):
        assert detect_content_type("src/Foo.java#processEvent") == ContentType.FILE_METHOD

    def test_multiline_java_code_is_code_block(self):
        code = "public void doThing() {\n    return;\n}"
        assert detect_content_type(code) == ContentType.CODE_BLOCK

    def test_multiline_no_java_keywords_is_free_text(self):
        text = "the service crashed\nbecause of a timeout\nin the payment handler"
        assert detect_content_type(text) == ContentType.FREE_TEXT

    def test_single_line_prose_is_free_text(self):
        assert detect_content_type("service is throwing 500s") == ContentType.FREE_TEXT

    def test_whitespace_stripped_before_check(self):
        assert detect_content_type("  a1b2c3d  ") == ContentType.COMMIT_HASH


# ── fetch_file_method ─────────────────────────────────────────────────────────

class TestFetchFileMethod:

    def test_returns_full_file_when_no_method(self, tmp_path):
        f = tmp_path / "Foo.java"
        f.write_text("public class Foo {}")
        result = fetch_file_method("Foo.java", None, [str(tmp_path)])
        assert result == "public class Foo {}"

    def test_extracts_named_method(self, tmp_path):
        source = (
            "public class Foo {\n"
            "    public void doThing() {\n"
            "        return;\n"
            "    }\n"
            "}\n"
        )
        f = tmp_path / "Foo.java"
        f.write_text(source)
        result = fetch_file_method("Foo.java", "doThing", [str(tmp_path)])
        assert "doThing" in result
        assert "return;" in result

    def test_file_not_found_raises_fetch_error(self, tmp_path):
        with pytest.raises(FetchError, match="not found in any known repo"):
            fetch_file_method("Missing.java", None, [str(tmp_path)])

    def test_file_too_large_raises_fetch_error(self, tmp_path):
        f = tmp_path / "Big.java"
        f.write_bytes(b"x" * (_MAX_FILE_BYTES + 1))
        with pytest.raises(FetchError, match="too large"):
            fetch_file_method("Big.java", None, [str(tmp_path)])

    def test_method_not_found_raises_fetch_error(self, tmp_path):
        f = tmp_path / "Foo.java"
        f.write_text("public class Foo { public void other() {} }")
        with pytest.raises(FetchError, match="not found in"):
            fetch_file_method("Foo.java", "missing", [str(tmp_path)])

    def test_searches_multiple_repo_roots(self, tmp_path):
        root_a = tmp_path / "repo_a"
        root_b = tmp_path / "repo_b"
        root_a.mkdir()
        root_b.mkdir()
        (root_b / "Bar.java").write_text("public class Bar {}")
        result = fetch_file_method("Bar.java", None, [str(root_a), str(root_b)])
        assert "Bar" in result

    def test_strips_leading_slash_from_path(self, tmp_path):
        f = tmp_path / "Foo.java"
        f.write_text("class Foo {}")
        result = fetch_file_method("/Foo.java", None, [str(tmp_path)])
        assert "Foo" in result


# ── _extract_method ───────────────────────────────────────────────────────────

class TestExtractMethod:

    def test_extracts_simple_method(self):
        source = (
            "public class X {\n"
            "    public int add(int a, int b) {\n"
            "        return a + b;\n"
            "    }\n"
            "}\n"
        )
        result = _extract_method(source, "add")
        assert result is not None
        assert "return a + b" in result

    def test_returns_none_for_missing_method(self):
        source = "public class X { public void other() {} }"
        assert _extract_method(source, "missing") is None

    def test_handles_nested_braces(self):
        source = (
            "public class X {\n"
            "    public void process() {\n"
            "        if (true) {\n"
            "            doThing();\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        result = _extract_method(source, "process")
        assert result is not None
        assert "doThing" in result


# ── fetch_commit_diff ─────────────────────────────────────────────────────────

class TestFetchCommitDiff:

    def _mock_run(self, stdout="diff output", returncode=0):
        mock = MagicMock()
        mock.returncode = returncode
        mock.stdout = stdout
        return mock

    def test_returns_diff_on_success(self, tmp_path):
        with patch("subprocess.run", return_value=self._mock_run("line1\nline2")) as m:
            result = fetch_commit_diff("abc1234", [str(tmp_path)])
        assert result == "line1\nline2"

    def test_truncates_long_diff(self, tmp_path):
        long_output = "\n".join(f"line {i}" for i in range(_MAX_DIFF_LINES + 50))
        with patch("subprocess.run", return_value=self._mock_run(long_output)):
            result = fetch_commit_diff("abc1234", [str(tmp_path)])
        assert "truncated" in result
        assert f"line {_MAX_DIFF_LINES}" not in result.split("truncated")[0]

    def test_raises_fetch_error_when_not_found(self, tmp_path):
        with patch("subprocess.run", return_value=self._mock_run("", returncode=128)):
            with pytest.raises(FetchError, match="not found in any known repo"):
                fetch_commit_diff("deadbeef", [str(tmp_path)])

    def test_skips_repo_on_timeout(self, tmp_path):
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()

        def side_effect(*args, cwd, **kwargs):
            if str(root_a) == str(cwd):
                raise subprocess.TimeoutExpired(cmd="git", timeout=10)
            return self._mock_run("found it")

        with patch("subprocess.run", side_effect=side_effect):
            result = fetch_commit_diff("abc1234", [str(root_a), str(root_b)])
        assert result == "found it"

    def test_raises_fetch_error_when_all_repos_fail(self, tmp_path):
        with patch("subprocess.run", return_value=self._mock_run("", returncode=1)):
            with pytest.raises(FetchError):
                fetch_commit_diff("abc1234", [str(tmp_path)])
