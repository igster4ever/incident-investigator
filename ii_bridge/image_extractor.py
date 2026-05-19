"""
ii_bridge/image_extractor.py — Extract stack trace text from a screenshot.

Pure function — no WS I/O. Raises ExtractionError on failure so the calling
handler can emit the appropriate WS event.

Public API:
  extract_stacktrace_from_image(image_b64, media_type) -> str
"""

from __future__ import annotations

import anthropic

_MODEL = "claude-haiku-4-5-20251001"
_NOT_STACKTRACE_SENTINEL = "NOT_A_STACKTRACE"

_SYSTEM = (
    "You are a tool that extracts stack trace text from screenshots. "
    "Output ONLY the verbatim stack trace text you see — no commentary, "
    "no formatting changes, no added line numbers. "
    f"If the image does not contain a stack trace, output exactly: {_NOT_STACKTRACE_SENTINEL}"
)


class ExtractionError(Exception):
    """Raised when image extraction fails; message is shown to the user as-is."""


def extract_stacktrace_from_image(image_b64: str, media_type: str) -> str:
    """
    Call Claude vision to extract a stack trace from a base64-encoded screenshot.

    Returns verbatim stack trace text on success.
    Raises ExtractionError if the image contains no stack trace or the API call fails.
    """
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract the stack trace from this screenshot.",
                        },
                    ],
                }
            ],
        )
    except anthropic.APIError as exc:
        raise ExtractionError(f"Claude API error during image extraction: {exc}") from exc

    text = response.content[0].text.strip()
    if text == _NOT_STACKTRACE_SENTINEL:
        raise ExtractionError(
            "The image does not appear to contain a stack trace. "
            "Paste the stack trace as text instead."
        )
    return text
