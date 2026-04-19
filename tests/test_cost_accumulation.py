"""Test that V4Session.total_cost_rub accumulates correctly across all three steps.

Each LLM step (generate_prompt, analyze, synthesize) must add its cost to the
session total via _accumulate_cost.  This test patches call_json in each module
to return LLMResult(..., cost_rub=0.12) and asserts that after all three steps
session.total_cost_rub == 0.36.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from smart_report import analyzer as analyzer_module
from smart_report import prompt_master as pm_module
from smart_report import synthesizer as synth_module
from smart_report.llm import LLMResult
from smart_report.models import (
    AnalysisOutput,
    ConsensusClaim,
    Conflict,
    Gap,
    ResearchPrompt,
    UploadedMarkdown,
    V4Session,
)
from smart_report.v4_orchestrator import V4Orchestrator, V4SessionStore


# ---------------------------------------------------------------------------
# Stub payloads — minimal valid JSON that each module will accept.
# ---------------------------------------------------------------------------

_PROMPT_PAYLOAD = {
    "full_prompt": "X" * 200,
    "reasoning": "stub reasoning",
    "expected_structure": ["Section A"],
    "key_entities": ["PIK"],
    "tips_for_search": "use perplexity",
}

_ANALYSIS_PAYLOAD = {
    "per_source_summary": [
        {"source": "perplexity", "summary": "stub", "strengths": "", "weaknesses": ""}
    ],
    "consensus": [
        {"claim": "PIK leads", "supporting_sources": ["perplexity"], "confidence": "high"}
    ],
    "conflicts": [],
    "gaps": [],
    "unverified_numbers": [],
    "quality_notes": "ok",
    "followup_prompts": [],
}

_SYNTH_PAYLOAD = {
    "session_id": "overridden-by-orchestrator",
    "question": "stub question",
    "research_prompt_used": "stub prompt",
    "executive_summary": {
        "main_answer": "stub answer",
        "ranking": None,
        "top_findings": ["finding 1"],
        "key_numbers": [],
        "confidence_note": "medium",
        "what_meta_adds": "nothing extra",
    },
    "main_synthesis": "## stub\n\ncontent",
    "consensus_section": "all agree",
    "conflicts_section": "no conflicts",
    "gaps_filled_section": "no gaps filled",
    "all_sources": [],
    "metadata": {},
}

_COST_PER_CALL = 0.12


@pytest.fixture
def mock_all_llm_calls(monkeypatch):
    """Patch call_json in all three v4 modules to return cost_rub=0.12."""

    async def _pm_stub(*a, **kw):
        return LLMResult(
            text=json.dumps(_PROMPT_PAYLOAD, ensure_ascii=False),
            cost_rub=_COST_PER_CALL,
        )

    async def _an_stub(*a, **kw):
        return LLMResult(
            text=json.dumps(_ANALYSIS_PAYLOAD, ensure_ascii=False),
            cost_rub=_COST_PER_CALL,
        )

    async def _syn_stub(*a, **kw):
        return LLMResult(
            text=json.dumps(_SYNTH_PAYLOAD, ensure_ascii=False),
            cost_rub=_COST_PER_CALL,
        )

    # Stub Intake call_json — it's invoked by normalize_all_reports during analyze step (v4.5)
    async def _intake_stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"numeric_facts": [], "qualitative_facts": [], "claims": []}),
            cost_rub=0.0,  # deterministic path contributes nothing
        )

    # Stub critic call_json — it's invoked by validate_consistency in synthesize step (v4.5)
    async def _critic_stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"issues": [], "severity_summary": {"critical": 0, "material": 0, "minor": 0}, "overall_verdict": "pass"}),
            cost_rub=0.0,
        )

    monkeypatch.setattr(pm_module, "call_json", _pm_stub)
    monkeypatch.setattr(analyzer_module, "call_json", _an_stub)
    monkeypatch.setattr(synth_module, "call_json", _syn_stub)
    from smart_report import intake as intake_module
    from smart_report import synthesis_critic as critic_module
    monkeypatch.setattr(intake_module, "call_json", _intake_stub)
    monkeypatch.setattr(critic_module, "call_json", _critic_stub)


@pytest.mark.asyncio
async def test_total_cost_accumulates_across_all_three_steps(mock_all_llm_calls):
    """After all three steps each costing 0.12 RUB, total_cost_rub must equal 0.36."""
    store = V4SessionStore()
    orch = V4Orchestrator(store, mock=False)  # mock=False; LLM calls are patched

    session_id = "test-cost-01"
    store.create(session_id=session_id, raw_question="stub question")

    # Step 1: generate_prompt
    await orch.generate_prompt(session_id)
    after_step1 = store.get(session_id).total_cost_rub
    assert after_step1 == pytest.approx(0.12, abs=1e-4), (
        f"Expected 0.12 after step 1, got {after_step1}"
    )

    # Step 2: analyze (needs at least one source report uploaded)
    session = store.get(session_id)
    session.source_reports = [
        UploadedMarkdown(filename="stub.md", content="# Stub report\nContent.", detected_tool="other")
    ]
    store.update(session)
    await orch.analyze(session_id)
    after_step2 = store.get(session_id).total_cost_rub
    assert after_step2 == pytest.approx(0.24, abs=1e-4), (
        f"Expected 0.24 after step 2, got {after_step2}"
    )

    # Step 3: synthesize
    await orch.synthesize(session_id)
    after_step3 = store.get(session_id).total_cost_rub
    assert after_step3 == pytest.approx(0.36, abs=1e-4), (
        f"Expected 0.36 after step 3, got {after_step3}"
    )


@pytest.mark.asyncio
async def test_cost_is_zero_when_mocked(monkeypatch):
    """When mock=True, no real cost is incurred and total_cost_rub stays 0."""
    store = V4SessionStore()
    orch = V4Orchestrator(store, mock=True)

    session_id = "test-cost-02"
    store.create(session_id=session_id, raw_question="stub question")

    await orch.generate_prompt(session_id)
    assert store.get(session_id).total_cost_rub == 0.0


@pytest.mark.asyncio
async def test_accumulate_cost_helper_rounds_to_4dp():
    """_accumulate_cost must round to 4 decimal places."""
    store = V4SessionStore()
    orch = V4Orchestrator(store)

    store.create(session_id="rounding-test", raw_question="q")
    session = store.get("rounding-test")

    # Add a third that doesn't round cleanly
    session = orch._accumulate_cost(session, 0.12345)
    session = orch._accumulate_cost(session, 0.12345)
    session = orch._accumulate_cost(session, 0.12345)

    # 3 * 0.12345 = 0.37035; rounded to 4dp at each step
    assert session.total_cost_rub == pytest.approx(0.3704, abs=1e-4)


@pytest.mark.asyncio
async def test_accumulate_cost_ignores_zero_and_negative():
    """_accumulate_cost must not add zero or negative values."""
    store = V4SessionStore()
    orch = V4Orchestrator(store)

    store.create(session_id="zero-test", raw_question="q")
    session = store.get("zero-test")

    session = orch._accumulate_cost(session, 0.0)
    assert session.total_cost_rub == 0.0

    session = orch._accumulate_cost(session, -1.0)
    assert session.total_cost_rub == 0.0

    session = orch._accumulate_cost(session, 0.5)
    assert session.total_cost_rub == pytest.approx(0.5, abs=1e-4)
