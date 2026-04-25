"""Regression for v4_orchestrator's Track 3 lint-retry threshold (Finding 2).

Live Acceptance Run 1 measured 100-310 language-lint warnings on every
realistic Russian RE Synthesizer output (driven by mentions of Knight
Frank, JLL, CBRE, Cushman & Wakefield, etc. — international consultancy
brands that appear in the source DR reports). The previous threshold
of >20 fired Track 3 retry on every such run, paying 3× Synthesizer
cost (initial + Coverage retry + Lint retry) for zero quality gain.

The threshold is now 100. This test pins the constant so a future
revert cannot land silently and re-introduce the cost trap, plus
verifies the retry decision logic at both sides of the boundary.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from smart_report.i18n.language_lint import LanguageWarning
from smart_report.llm import LLMResult
from smart_report.models import (
    AnalysisOutput,
    ConsensusClaim,
    ExecutiveSummaryV4,
    FinalReport,
    Source,
    UploadedMarkdown,
    V4Session,
)
from smart_report.v4_orchestrator import (
    LINT_WARNING_RETRY_THRESHOLD,
    V4Orchestrator,
    V4SessionStore,
)


# ---------------------------------------------------------------------------
# Threshold constant pin
# ---------------------------------------------------------------------------


def test_lint_threshold_constant_pinned_at_100():
    """The threshold lives as a module-level constant. Lowering it back to
    20 (or any value < 50) reintroduces the cost trap from Run 1 — fail
    loudly so a regression PR cannot slip past code review.
    """
    assert LINT_WARNING_RETRY_THRESHOLD == 100, (
        f"LINT_WARNING_RETRY_THRESHOLD changed to {LINT_WARNING_RETRY_THRESHOLD}. "
        f"If you intentionally tuned it, also update Run 2 evidence and the "
        f"feedback memory at memory/feedback_lint_retry_cost_trap.md."
    )


def test_lint_threshold_above_realistic_brand_count():
    """Independent calibration check: realistic Russian RE reports cite
    5-20 international consultancies. Each brand mention can trigger 3-5
    Latin-token warnings (the brand name itself plus surrounding
    article fragments that didn't whitelist). Threshold should be above
    20 brands × 5 warnings = 100 to absorb that noise without retry.
    """
    expected_realistic_high_water = 100
    assert LINT_WARNING_RETRY_THRESHOLD >= expected_realistic_high_water, (
        f"Threshold {LINT_WARNING_RETRY_THRESHOLD} is below the empirical "
        f"realistic-content noise floor of {expected_realistic_high_water}. "
        f"Track 3 will retry on every production run."
    )


# ---------------------------------------------------------------------------
# Boundary-condition tests — full orchestrator decision path
# ---------------------------------------------------------------------------


def _fake_warnings(n: int) -> list[LanguageWarning]:
    return [
        LanguageWarning(
            token=f"brand{i}", location_context=f"...контекст {i}...", severity="warn"
        )
        for i in range(n)
    ]


def _make_session_with_final() -> V4Session:
    """Minimal V4Session whose synthesize step is poised to enter Step 3f."""
    return V4Session(
        session_id="lint-threshold-test",
        raw_question="stub question",
        source_reports=[UploadedMarkdown(filename="r.md", content="x", word_count=1)],
        analysis=AnalysisOutput(
            consensus=[ConsensusClaim(claim="c", supporting_sources=["s"], confidence="high")],
        ),
        status="analyzed",
        created_at=datetime.now(timezone.utc),
    )


def _make_final_report() -> FinalReport:
    return FinalReport(
        session_id="lint-threshold-test",
        question="Q",
        executive_summary=ExecutiveSummaryV4(main_answer="ans"),
        main_synthesis="body",
        all_sources=[Source(title="ERZ", url="https://erzrf.ru/x", reliability="high")],
    )


@pytest.mark.asyncio
async def test_50_warnings_does_not_trigger_retry():
    """At 50 warnings (well below the 100 threshold) the Synthesizer is
    called exactly once. Retry path must NOT fire.
    """
    syn_calls = 0

    async def syn_stub(session, **kw):
        nonlocal syn_calls
        syn_calls += 1
        # On the retry path the orchestrator passes language_feedback;
        # if that ever happens here, the test should fail loudly.
        assert kw.get("language_feedback") is None, (
            "language_feedback should not be passed on the first call"
        )
        return _make_final_report(), 0.12

    async def critic_stub(report, **kw):
        from smart_report.synthesis_critic import ConsistencyReport
        return ConsistencyReport(
            issues=[],
            severity_summary={"critical": 0, "material": 0, "minor": 0},
            overall_verdict="pass",
        )

    store = V4SessionStore()
    sess = _make_session_with_final()
    store._sessions[sess.session_id] = sess
    orch = V4Orchestrator(store, mock=False)

    with patch("smart_report.v4_orchestrator.synthesize_final_report", new=syn_stub), \
         patch("smart_report.v4_orchestrator.validate_consistency", new=critic_stub), \
         patch(
            "smart_report.v4_orchestrator.lint_output_language",
            return_value=_fake_warnings(50),
        ):
        await orch.synthesize(sess.session_id)

    assert syn_calls == 1, (
        f"With 50 warnings (< {LINT_WARNING_RETRY_THRESHOLD}), Synthesizer "
        f"must run exactly once. Got {syn_calls} call(s) — retry incorrectly "
        f"triggered."
    )


@pytest.mark.asyncio
async def test_150_warnings_triggers_retry():
    """At 150 warnings (above the 100 threshold) the Synthesizer is
    called twice (initial + Track 3 retry with language_feedback).
    """
    syn_calls = 0
    second_call_had_feedback = False

    async def syn_stub(session, **kw):
        nonlocal syn_calls, second_call_had_feedback
        syn_calls += 1
        if syn_calls == 2:
            second_call_had_feedback = kw.get("language_feedback") is not None
        return _make_final_report(), 0.12

    async def critic_stub(report, **kw):
        from smart_report.synthesis_critic import ConsistencyReport
        return ConsistencyReport(
            issues=[],
            severity_summary={"critical": 0, "material": 0, "minor": 0},
            overall_verdict="pass",
        )

    store = V4SessionStore()
    sess = _make_session_with_final()
    store._sessions[sess.session_id] = sess
    orch = V4Orchestrator(store, mock=False)

    with patch("smart_report.v4_orchestrator.synthesize_final_report", new=syn_stub), \
         patch("smart_report.v4_orchestrator.validate_consistency", new=critic_stub), \
         patch(
            "smart_report.v4_orchestrator.lint_output_language",
            return_value=_fake_warnings(150),
        ):
        await orch.synthesize(sess.session_id)

    assert syn_calls == 2, (
        f"With 150 warnings (> {LINT_WARNING_RETRY_THRESHOLD}), Synthesizer "
        f"must run twice (initial + Track 3 retry). Got {syn_calls} call(s)."
    )
    assert second_call_had_feedback, (
        "On retry, language_feedback must be passed to synthesize_final_report"
    )


@pytest.mark.asyncio
async def test_exactly_threshold_does_not_trigger_retry():
    """Boundary: exactly LINT_WARNING_RETRY_THRESHOLD (100) warnings must NOT
    trigger retry. The condition is strict greater-than; off-by-one would
    pay one extra Synthesizer invocation on every threshold-edge run.
    """
    syn_calls = 0

    async def syn_stub(session, **kw):
        nonlocal syn_calls
        syn_calls += 1
        return _make_final_report(), 0.12

    async def critic_stub(report, **kw):
        from smart_report.synthesis_critic import ConsistencyReport
        return ConsistencyReport(
            issues=[],
            severity_summary={"critical": 0, "material": 0, "minor": 0},
            overall_verdict="pass",
        )

    store = V4SessionStore()
    sess = _make_session_with_final()
    store._sessions[sess.session_id] = sess
    orch = V4Orchestrator(store, mock=False)

    with patch("smart_report.v4_orchestrator.synthesize_final_report", new=syn_stub), \
         patch("smart_report.v4_orchestrator.validate_consistency", new=critic_stub), \
         patch(
            "smart_report.v4_orchestrator.lint_output_language",
            return_value=_fake_warnings(LINT_WARNING_RETRY_THRESHOLD),
        ):
        await orch.synthesize(sess.session_id)

    assert syn_calls == 1, (
        f"Exactly {LINT_WARNING_RETRY_THRESHOLD} warnings must NOT trigger "
        f"retry (strict > comparison). Got {syn_calls} call(s)."
    )
