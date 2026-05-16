"""
tests/test_prompts.py — Unit tests for pure prompt builder functions.

All functions in bridge/prompts.py are side-effect-free so these tests need
no mocking — just call and assert on the returned string.
"""

import pytest
from ii_bridge.prompts import (
    fix_advisor_clickup,
    fix_advisor_slack_thread,
    fix_advisor_description,
    fix_advisor_stacktrace,
    minimal_fix_clickup,
    minimal_fix_slack_thread,
    minimal_fix_description,
    minimal_fix_stacktrace,
)


# ── Fix Advisor ───────────────────────────────────────────────────────────────

class TestFixAdvisorClickup:
    def test_contains_ticket_id(self):
        prompt = fix_advisor_clickup("AOP-1234", "", "")
        assert "AOP-1234" in prompt

    def test_contains_slack_text(self):
        prompt = fix_advisor_clickup("AOP-1234", "some slack content", "")
        assert "some slack content" in prompt

    def test_fallback_when_no_slack(self):
        prompt = fix_advisor_clickup("AOP-1234", "", "")
        assert "no Slack mentions found" in prompt

    def test_contains_git_text(self):
        prompt = fix_advisor_clickup("AOP-1234", "", "commit abc123")
        assert "commit abc123" in prompt

    def test_fallback_when_no_git(self):
        prompt = fix_advisor_clickup("AOP-1234", "", "")
        assert "no matching commits" in prompt

    def test_contains_required_sections(self):
        prompt = fix_advisor_clickup("AOP-1234", "", "")
        for section in [
            "Identified Repository",
            "Root Cause",
            "Proposed Fix",
            "Affected Files",
            "Effort Estimate",
            "Risk Assessment",
            "Tech Debt Note",
        ]:
            assert section in prompt, f"Missing section: {section}"

    def test_contains_effort_scale(self):
        prompt = fix_advisor_clickup("AOP-1234", "", "")
        assert "XS" in prompt and "XL" in prompt


class TestFixAdvisorSlackThread:
    def test_contains_thread_text(self):
        prompt = fix_advisor_slack_thread("alice: the payment service is down")
        assert "alice: the payment service is down" in prompt

    def test_contains_required_sections(self):
        prompt = fix_advisor_slack_thread("some thread")
        assert "Identified Repository" in prompt
        assert "Proposed Fix" in prompt


class TestFixAdvisorDescription:
    def test_contains_description(self):
        prompt = fix_advisor_description("deposit service crashes at midnight", "", "")
        assert "deposit service crashes at midnight" in prompt

    def test_fallbacks_for_empty_context(self):
        prompt = fix_advisor_description("something broke", "", "")
        assert "no relevant Slack activity found" in prompt
        assert "no matching commits found" in prompt

    def test_slack_and_git_included(self):
        prompt = fix_advisor_description("bug", "slack result here", "git commit here")
        assert "slack result here" in prompt
        assert "git commit here" in prompt


class TestFixAdvisorStacktrace:
    _parsed = {
        "primary_exception": {"type": "NullPointerException", "message": "null at line 42"},
        "affected_services": ["ats-payments"],
        "all_project_frames": [
            {"class_method": "DepositLimitService.calculate", "line": 42, "likely_paths": ["src/DepositLimitService.java"]},
        ],
    }

    def test_contains_exception_type(self):
        prompt = fix_advisor_stacktrace("stack...", self._parsed, "", "")
        assert "NullPointerException" in prompt

    def test_contains_affected_service(self):
        prompt = fix_advisor_stacktrace("stack...", self._parsed, "", "")
        assert "ats-payments" in prompt

    def test_contains_frame(self):
        prompt = fix_advisor_stacktrace("stack...", self._parsed, "", "")
        assert "DepositLimitService.calculate" in prompt

    def test_code_context_included(self):
        prompt = fix_advisor_stacktrace("stack...", self._parsed, "code context here", "")
        assert "code context here" in prompt

    def test_fallback_when_no_code_context(self):
        prompt = fix_advisor_stacktrace("stack...", self._parsed, "", "")
        assert "(unavailable)" in prompt

    def test_stacktrace_truncated_to_40_lines(self):
        long_trace = "\n".join(f"line {i}" for i in range(100))
        prompt = fix_advisor_stacktrace(long_trace, {}, "", "")
        assert "line 39" in prompt
        assert "line 40" not in prompt

    def test_empty_parsed_does_not_raise(self):
        prompt = fix_advisor_stacktrace("stack...", {}, "", "")
        assert "Unknown" in prompt  # default exception type


# ── Minimal Fix ───────────────────────────────────────────────────────────────

class TestMinimalFixClickup:
    def test_contains_ticket_id(self):
        prompt = minimal_fix_clickup("DEV-9999", "", "")
        assert "DEV-9999" in prompt

    def test_contains_required_sections(self):
        prompt = minimal_fix_clickup("DEV-9999", "", "")
        for section in [
            "Identified Repository",
            "Root Cause",
            "Minimal Fix",
            "Affected Files",
            "Effort Estimate",
            "Risk Assessment",
            "Tech Debt Left Behind",
        ]:
            assert section in prompt, f"Missing section: {section}"

    def test_minimal_fix_framing(self):
        # Prompt should emphasise smallest safe change, not full fix
        prompt = minimal_fix_clickup("DEV-9999", "", "")
        assert "smallest" in prompt.lower() or "minimal" in prompt.lower()

    def test_tech_debt_callout(self):
        prompt = minimal_fix_clickup("DEV-9999", "", "")
        assert "Tech Debt Left Behind" in prompt


class TestMinimalFixSlackThread:
    def test_contains_thread_text(self):
        prompt = minimal_fix_slack_thread("bob: hotfix needed urgently")
        assert "bob: hotfix needed urgently" in prompt

    def test_minimal_framing_present(self):
        prompt = minimal_fix_slack_thread("some thread")
        assert "Minimal Fix" in prompt


class TestMinimalFixDescription:
    def test_contains_description(self):
        prompt = minimal_fix_description("the bet settlement service is stuck", "", "")
        assert "the bet settlement service is stuck" in prompt

    def test_fallbacks_present(self):
        prompt = minimal_fix_description("broke", "", "")
        assert "no relevant Slack activity found" in prompt


class TestMinimalFixStacktrace:
    _parsed = {
        "primary_exception": {"type": "IllegalStateException", "message": "session expired"},
        "affected_services": ["ats-sportsbook"],
        "all_project_frames": [],
    }

    def test_contains_exception_type(self):
        prompt = minimal_fix_stacktrace("stack...", self._parsed, "", "")
        assert "IllegalStateException" in prompt

    def test_contains_service(self):
        prompt = minimal_fix_stacktrace("stack...", self._parsed, "", "")
        assert "ats-sportsbook" in prompt

    def test_no_frames_shows_none(self):
        prompt = minimal_fix_stacktrace("stack...", self._parsed, "", "")
        assert "none" in prompt

    def test_contains_required_sections(self):
        prompt = minimal_fix_stacktrace("stack...", self._parsed, "", "")
        assert "Minimal Fix" in prompt
        assert "Tech Debt Left Behind" in prompt


# ── Cross-cutting ─────────────────────────────────────────────────────────────

class TestPromptDifferentiation:
    """Fix Advisor and Minimal Fix prompts for the same input should differ."""

    def test_clickup_prompts_differ(self):
        fa = fix_advisor_clickup("AOP-1", "slack", "git")
        mf = minimal_fix_clickup("AOP-1", "slack", "git")
        assert fa != mf

    def test_stacktrace_prompts_differ(self):
        parsed = {"primary_exception": {"type": "NPE", "message": ""}, "affected_services": []}
        fa = fix_advisor_stacktrace("st", parsed, "", "")
        mf = minimal_fix_stacktrace("st", parsed, "", "")
        assert fa != mf

    def test_fix_advisor_mentions_risk_assessment(self):
        prompt = fix_advisor_clickup("X-1", "", "")
        assert "Risk Assessment" in prompt

    def test_minimal_fix_mentions_tech_debt_left_behind(self):
        prompt = minimal_fix_clickup("X-1", "", "")
        assert "Tech Debt Left Behind" in prompt
