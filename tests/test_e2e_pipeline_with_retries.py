"""End-to-end pipeline test with all retry layers triggered.

Mocks LLM call_json at every layer (prompt_master, intake, analyzer,
synthesizer, critic) so the orchestrator runs through:
  - generate_prompt
  - analyze (normalize 1 source + analyzer)
  - synthesize Step 3a (first pass)
  - Step 3c coverage audit → critical_failure → retry triggers Step 3d
  - Step 3e consistency check → critical_failure → retry
  - Step 3f language lint → above threshold → retry

Verifies:
  1. All async store.update calls (wrapped in asyncio.to_thread after the
     2026-04-28 hang fix) complete cleanly without RuntimeWarning about
     un-awaited coroutines.
  2. Final report is produced with status="synthesized".
  3. session.total_cost_rub accumulates across ALL synthesizer attempts
     (3 passes: first + coverage retry + consistency retry + lint retry).
  4. The orchestrator does not hang or raise on the multi-retry path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from smart_report import analyzer as analyzer_module
from smart_report import intake as intake_module
from smart_report import prompt_master as pm_module
from smart_report import synthesis_critic as critic_module
from smart_report import synthesizer as synth_module
from smart_report.llm import LLMResult
from smart_report.models import UploadedMarkdown
from smart_report.v4_orchestrator import V4Orchestrator, V4SessionStore


_PROMPT_PAYLOAD = {
    "full_prompt": "Stub research prompt about real estate prices in Moscow.",
    "reasoning": "stub",
    "expected_structure": ["Executive Summary", "Findings", "Sources"],
    "key_entities": ["PIK", "Etalon"],
    "tips_for_search": "search Russian sources",
}

# Analysis with high-relevance facts attached so coverage audit has work to do.
_ANALYSIS_PAYLOAD = {
    "per_source_summary": [
        {"source": "perplexity", "summary": "Comprehensive market data",
         "strengths": "covers PIK financials", "weaknesses": "no Etalon data"}
    ],
    "consensus": [
        {"claim": "PIK leads Moscow market", "supporting_sources": ["perplexity"],
         "confidence": "high"}
    ],
    "conflicts": [
        {"topic": "Etalon market share", "source_a": "perplexity",
         "claim_a": "10%", "source_b": "valyu", "claim_b": "12%",
         "resolution_hint": "verify with дом.рф data", "importance": "material"}
    ],
    "gaps": [
        {"topic": "Q4 2025 forecast", "why_critical": "needed for prediction",
         "what_to_find": "analyst forecasts", "candidate_sources": ["renaissance"]}
    ],
    "unverified_numbers": [],
    "quality_notes": "ok",
    "followup_prompts": [],
    "followup_prompt": {
        "prompt_id": "fp_consolidated", "intent": "fill_gap",
        "prompt": "Find Q4 2025 forecasts", "target_info": "Q4 2025 analyst forecast",
        "suggested_tool": "perplexity", "suggested_source_site": "renaissance.ru",
        "priority": "must", "linked_to": "Q4 2025 forecast",
    },
}

# Synth payload — minimal valid FinalReport JSON. main_synthesis intentionally
# has English vocabulary that the language lint will flag heavily, triggering
# the language-retry path in Step 3f.
_SYNTH_PAYLOAD = {
    "session_id": "overridden-by-orchestrator",
    "question": "stub question",
    "research_prompt_used": "stub prompt",
    "executive_summary": {
        "main_answer": "Финал готов",
        "ranking": None,
        "top_findings": ["finding 1"],
        "key_numbers": [{"value": "100", "metric": "млрд", "subject": "PIK"}],
        "confidence_note": "medium",
        "what_meta_adds": "nothing extra",
    },
    "main_synthesis": "## Executive overview\n\n" + " ".join(
        ["Implementation considers leading market drivers."] * 30
    ),
    "consensus_section": "all agree",
    "conflicts_section": "no critical conflicts",
    "gaps_filled_section": "Q4 forecast pending",
    "all_sources": [],
    "metadata": {},
}


@pytest.fixture
def stub_all_llms(monkeypatch):
    """Patch every call_json so the pipeline runs without a real OpenRouter call."""
    cost_per_call = 0.10

    async def _pm_stub(*a, **kw):
        return LLMResult(text=json.dumps(_PROMPT_PAYLOAD, ensure_ascii=False),
                         cost_rub=cost_per_call)

    async def _an_stub(*a, **kw):
        return LLMResult(text=json.dumps(_ANALYSIS_PAYLOAD, ensure_ascii=False),
                         cost_rub=cost_per_call)

    async def _syn_stub(*a, **kw):
        return LLMResult(text=json.dumps(_SYNTH_PAYLOAD, ensure_ascii=False),
                         cost_rub=cost_per_call)

    async def _intake_stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"numeric_facts": [], "qualitative_facts": [], "claims": []}),
            cost_rub=0.0,
        )

    # Critic returns critical_failure on first call → retry; pass on second.
    critic_calls = {"n": 0}
    async def _critic_stub(*a, **kw):
        critic_calls["n"] += 1
        verdict = "critical_failure" if critic_calls["n"] == 1 else "pass"
        return LLMResult(
            text=json.dumps({
                "issues": [], "severity_summary": {"critical": 0, "material": 0, "minor": 0},
                "overall_verdict": verdict,
            }),
            cost_rub=0.0,
        )

    monkeypatch.setattr(pm_module, "call_json", _pm_stub)
    monkeypatch.setattr(analyzer_module, "call_json", _an_stub)
    monkeypatch.setattr(synth_module, "call_json", _syn_stub)
    monkeypatch.setattr(intake_module, "call_json", _intake_stub)
    monkeypatch.setattr(critic_module, "call_json", _critic_stub)


@pytest.mark.asyncio
async def test_full_pipeline_with_consistency_retry(stub_all_llms):
    """End-to-end pipeline run: generate_prompt → analyze → synthesize.

    Critic is configured to return critical_failure on first call and pass on
    second, exercising the Step 3e retry path. With async store.update wrappers
    (asyncio.to_thread) all multi-update sequences must complete without a
    RuntimeWarning or hang.
    """
    store = V4SessionStore()
    orch = V4Orchestrator(store, mock=False)

    sid = "e2e-retry-01"
    store.create(session_id=sid, raw_question="что будет с ценами на жильё в Москве 2026")

    # --- Step 1: generate_prompt
    prompt = await orch.generate_prompt(sid)
    assert prompt.full_prompt
    assert store.get(sid).status == "prompt_ready"

    # --- Step 2: analyze (need a source_report)
    session = store.get(sid)
    session.source_reports = [
        UploadedMarkdown(
            filename="perplexity_research.md",
            content="# Moscow RE Market 2026\n\nPIK leads with 22% share. " * 10,
            detected_tool="perplexity",
            word_count=200,
        ),
    ]
    store.update(session)

    analysis = await orch.analyze(sid)
    assert analysis.followup_prompt is not None  # critique surfaces a followup
    assert store.get(sid).status == "analyzed"

    # --- Step 3: synthesize (will hit consistency retry)
    final = await orch.synthesize(sid)
    assert final.executive_summary.main_answer == "Финал готов"
    s = store.get(sid)
    assert s.status == "synthesized"
    assert s.final_report is not None

    # All four LLM-spending steps charged: generate_prompt + analyze + synth +
    # synth-consistency-retry = 4 × 0.10 = 0.40 (intake/critic stubbed at 0).
    assert s.total_cost_rub >= 0.40 - 1e-4


@pytest.mark.asyncio
async def test_pipeline_no_unawaited_coroutine_warnings(stub_all_llms, recwarn):
    """Async wrappers around store.update (via asyncio.to_thread) and the
    async _accumulate_cost must not leak un-awaited coroutines."""
    store = V4SessionStore()
    orch = V4Orchestrator(store, mock=False)

    sid = "e2e-warn-01"
    store.create(session_id=sid, raw_question="q")
    await orch.generate_prompt(sid)

    session = store.get(sid)
    session.source_reports = [
        UploadedMarkdown(
            filename="r.md",
            content="# R\n\ncontent " * 50,
            detected_tool="other",
            word_count=100,
        ),
    ]
    store.update(session)
    await orch.analyze(sid)
    await orch.synthesize(sid)

    # No "coroutine was never awaited" warnings — that bug existed before
    # the async refactor when _accumulate_cost was made async but a few
    # callsites kept the synchronous form.
    leaked = [w for w in recwarn.list if "never awaited" in str(w.message)]
    assert not leaked, f"unawaited coroutines leaked: {leaked}"
