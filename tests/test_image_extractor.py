"""
tests/test_image_extractor.py — Unit tests for ii_bridge/image_extractor.py.

Covers:
  - Happy path: returns verbatim stack trace text
  - NOT_A_STACKTRACE sentinel: raises ExtractionError with clear message
  - API error: raises ExtractionError wrapping the original exception
  - Whitespace is stripped from the response
  - media_type is passed through to the API correctly
"""

from unittest.mock import MagicMock, patch

import anthropic
import pytest

from ii_bridge.image_extractor import (
    ExtractionError,
    _NOT_STACKTRACE_SENTINEL,
    extract_stacktrace_from_image,
)

_FAKE_STACKTRACE = (
    "java.lang.NullPointerException\n"
    "\tat com.example.Foo.bar(Foo.java:42)\n"
    "\tat com.example.Main.main(Main.java:10)\n"
)

_FAKE_B64 = "aW1hZ2VkYXRh"  # base64 for "imagedata"
_FAKE_MEDIA_TYPE = "image/jpeg"


def _mock_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _mock_client(text: str) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = _mock_response(text)
    return client


# ── Happy path ────────────────────────────────────────────────────────────────

class TestExtractStacktraceFromImage:

    def test_returns_stack_trace_on_success(self):
        with patch("ii_bridge.image_extractor.anthropic.Anthropic", return_value=_mock_client(_FAKE_STACKTRACE)):
            result = extract_stacktrace_from_image(_FAKE_B64, _FAKE_MEDIA_TYPE)
        assert result == _FAKE_STACKTRACE.strip()

    def test_strips_surrounding_whitespace(self):
        padded = f"\n\n  {_FAKE_STACKTRACE}  \n"
        with patch("ii_bridge.image_extractor.anthropic.Anthropic", return_value=_mock_client(padded)):
            result = extract_stacktrace_from_image(_FAKE_B64, _FAKE_MEDIA_TYPE)
        assert not result.startswith("\n")
        assert not result.endswith("\n\n")

    def test_passes_media_type_to_api(self):
        client = _mock_client(_FAKE_STACKTRACE)
        with patch("ii_bridge.image_extractor.anthropic.Anthropic", return_value=client):
            extract_stacktrace_from_image(_FAKE_B64, "image/png")
        call_kwargs = client.messages.create.call_args
        image_block = call_kwargs[1]["messages"][0]["content"][0]
        assert image_block["source"]["media_type"] == "image/png"

    def test_passes_image_data_to_api(self):
        client = _mock_client(_FAKE_STACKTRACE)
        with patch("ii_bridge.image_extractor.anthropic.Anthropic", return_value=client):
            extract_stacktrace_from_image("mybase64data", _FAKE_MEDIA_TYPE)
        call_kwargs = client.messages.create.call_args
        image_block = call_kwargs[1]["messages"][0]["content"][0]
        assert image_block["source"]["data"] == "mybase64data"


# ── Sentinel response ─────────────────────────────────────────────────────────

class TestNotStacktraceSentinel:

    def test_raises_extraction_error_on_sentinel(self):
        with patch("ii_bridge.image_extractor.anthropic.Anthropic",
                   return_value=_mock_client(_NOT_STACKTRACE_SENTINEL)):
            with pytest.raises(ExtractionError, match="does not appear to contain"):
                extract_stacktrace_from_image(_FAKE_B64, _FAKE_MEDIA_TYPE)

    def test_sentinel_with_surrounding_whitespace_still_raises(self):
        # Sentinel must match exactly after strip — whitespace should not fool the check
        with patch("ii_bridge.image_extractor.anthropic.Anthropic",
                   return_value=_mock_client(f"  {_NOT_STACKTRACE_SENTINEL}  ")):
            with pytest.raises(ExtractionError):
                extract_stacktrace_from_image(_FAKE_B64, _FAKE_MEDIA_TYPE)


# ── API errors ────────────────────────────────────────────────────────────────

class TestApiErrors:

    def test_api_error_raises_extraction_error(self):
        client = MagicMock()
        client.messages.create.side_effect = anthropic.APIStatusError(
            message="rate limit",
            response=MagicMock(status_code=429, headers={}),
            body={},
        )
        with patch("ii_bridge.image_extractor.anthropic.Anthropic", return_value=client):
            with pytest.raises(ExtractionError, match="Claude API error"):
                extract_stacktrace_from_image(_FAKE_B64, _FAKE_MEDIA_TYPE)

    def test_extraction_error_wraps_original(self):
        original = anthropic.APIConnectionError(request=MagicMock())
        client = MagicMock()
        client.messages.create.side_effect = original
        with patch("ii_bridge.image_extractor.anthropic.Anthropic", return_value=client):
            with pytest.raises(ExtractionError) as exc_info:
                extract_stacktrace_from_image(_FAKE_B64, _FAKE_MEDIA_TYPE)
        assert exc_info.value.__cause__ is original
