"""
tests/test_token_utils.py — Unit tests for ii_bridge/token_utils.py.

All file I/O and env vars are mocked — no real filesystem access.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from ii_bridge.token_utils import read_token_file, read_clickup_token, read_slack_token


class TestReadTokenFile:
    def test_returns_none_if_file_missing(self, tmp_path):
        assert read_token_file(tmp_path / "nonexistent") is None

    def test_returns_none_if_file_empty(self, tmp_path):
        f = tmp_path / "tok"
        f.write_text("")
        assert read_token_file(f) is None

    def test_returns_none_if_whitespace_only(self, tmp_path):
        f = tmp_path / "tok"
        f.write_text("   \n")
        assert read_token_file(f) is None

    def test_returns_stripped_content(self, tmp_path):
        f = tmp_path / "tok"
        f.write_text("  my-token\n")
        assert read_token_file(f) == "my-token"

    def test_returns_content_no_whitespace(self, tmp_path):
        f = tmp_path / "tok"
        f.write_text("abc123")
        assert read_token_file(f) == "abc123"


class TestReadClickupToken:
    def test_env_var_takes_precedence(self, tmp_path):
        with patch.dict("os.environ", {"CLICKUP_TOKEN": "env-tok"}):
            with patch("ii_bridge.token_utils.CLICKUP_TOKEN_PATH", tmp_path / "missing"):
                assert read_clickup_token() == "env-tok"

    def test_falls_back_to_file(self, tmp_path):
        f = tmp_path / ".clickup_token"
        f.write_text("file-tok")
        with patch.dict("os.environ", {}, clear=True):
            with patch("ii_bridge.token_utils.CLICKUP_TOKEN_PATH", f):
                assert read_clickup_token() == "file-tok"

    def test_env_var_whitespace_ignored(self, tmp_path):
        f = tmp_path / ".clickup_token"
        f.write_text("file-tok")
        with patch.dict("os.environ", {"CLICKUP_TOKEN": "   "}):
            with patch("ii_bridge.token_utils.CLICKUP_TOKEN_PATH", f):
                assert read_clickup_token() == "file-tok"

    def test_returns_none_if_neither_set(self, tmp_path):
        with patch.dict("os.environ", {}, clear=True):
            with patch("ii_bridge.token_utils.CLICKUP_TOKEN_PATH", tmp_path / "missing"):
                assert read_clickup_token() is None

    def test_returns_none_if_file_empty_and_no_env(self, tmp_path):
        f = tmp_path / ".clickup_token"
        f.write_text("")
        with patch.dict("os.environ", {}, clear=True):
            with patch("ii_bridge.token_utils.CLICKUP_TOKEN_PATH", f):
                assert read_clickup_token() is None


class TestReadSlackToken:
    def test_returns_token_from_file(self, tmp_path):
        f = tmp_path / ".slack_token"
        f.write_text("xoxb-slack")
        with patch("ii_bridge.token_utils.SLACK_TOKEN_PATH", f):
            assert read_slack_token() == "xoxb-slack"

    def test_returns_none_if_missing(self, tmp_path):
        with patch("ii_bridge.token_utils.SLACK_TOKEN_PATH", tmp_path / "missing"):
            assert read_slack_token() is None

    def test_returns_none_if_empty(self, tmp_path):
        f = tmp_path / ".slack_token"
        f.write_text("")
        with patch("ii_bridge.token_utils.SLACK_TOKEN_PATH", f):
            assert read_slack_token() is None
