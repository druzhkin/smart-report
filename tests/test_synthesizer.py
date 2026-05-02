"""Synthesizer schema/IO test — LLM mocked."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from smart_report import synthesizer as synth_module
from smart_report.llm import LLMResult
from smart_report.models import (
    AnalysisOutput,
    ConsensusClaim,
    Conflict,
    FinalReport,
    FollowupPrompt,
    Gap,
    NumericFact,
    ResearchPrompt,
    SourceRef,
    UploadedMarkdown,
    V4Session,
)
from smart_report.synthesizer import synthesize_final_report


_MOCK_FINAL_JSON = {
    "session_id": "will-be-overridden",
    "question": "What defines developer success in Moscow business real estate?",
    "research_prompt_used": "Analyse Moscow developers for 2024.",
    "executive_summary": {
        "main_answer": (
            "Product quality explains more of commercial success than brand or speed in "
            "Moscow business-class 2024. PIK's scale gives brand and speed advantages yet "
            "mid-tier developers with stronger product specs (Donstroy, Sminex) outperform "
            "on price per m² and resale velocity."
        ),
        "ranking": "Продукт > скорость > бренд",
        "top_findings": [
            "Top-5 developers hold 47% of business-class launches (ERZ).",
            "Mortgage share fell from 78% (2023) to 55% (2024) per ERZ.",
            "Donstroy leads on price per m² in the 120k+ RUB segment.",
        ],
        "key_numbers": [
            {
                "value": "47%",
                "metric": "Top-5 share",
                "subject": "business-class launches 2024",
                "source_url": "https://erzrf.ru/...",
            },
            {
                "value": "55%",
                "metric": "mortgage share",
                "subject": "business-class 2024",
                "source_url": "https://erzrf.ru/...",
            },
        ],
        "confidence_note": "Medium — concentrated on 2024 data, delivery-delay metrics absent.",
        "what_meta_adds": (
            "Reconciled conflicting mortgage-share numbers (55% ERZ vs 68% Knight Frank) "
            "in favour of ERZ, eliminating vendor skew."
        ),
    },
    "main_synthesis": "## Позиция\n\nПродукт > скорость > бренд. Ниже разбор.\n\n## Brand\n\nPIK leads by volume; NPS data unavailable.",
    "consensus_section": "All three reports agree on top-3 developers (PIK, Donstroy, MR Group).",
    "conflicts_section": "Mortgage share: 55% (ERZ) vs 68% (Knight Frank). We pick ERZ — broader base.",
    "gaps_filled_section": "Dobor not uploaded; per-developer delivery delays remain open.",
    "all_sources": [
        {
            "title": "ERZ 2024 Moscow business-class report",
            "url": "https://erzrf.ru/...",
            "tool": "perplexity",
            "reliability": "high",
        },
        {
            "title": "Knight Frank 2024",
            "url": "https://knightfrank.ru/...",
            "tool": "openai_dr",
            "reliability": "low",
        },
    ],
    "metadata": {"source_reports_count": 2},
}


def _session_with_analysis() -> V4Session:
    return V4Session(
        session_id="sess01",
        raw_question="What defines developer success in Moscow business real estate?",
        research_prompt=ResearchPrompt(
            full_prompt="Analyse Moscow developers for 2024.", reasoning="frame"
        ),
        source_reports=[
            UploadedMarkdown(filename="a.md", content="report A", detected_tool="perplexity"),
            UploadedMarkdown(filename="b.md", content="report B", detected_tool="openai_dr"),
        ],
        analysis=AnalysisOutput(
            consensus=[
                ConsensusClaim(
                    claim="PIK leads share", supporting_sources=["perplexity", "openai_dr"]
                )
            ],
            conflicts=[
                Conflict(
                    topic="mortgage share 2024",
                    source_a="perplexity",
                    claim_a="55%",
                    source_b="openai_dr",
                    claim_b="68%",
                    resolution_hint="cross-check ERZ",
                    importance="critical",
                )
            ],
            gaps=[
                Gap(
                    topic="delivery delays",
                    why_critical="speed ranking hinges on it",
                    what_to_find="% delay per developer",
                    candidate_sources=["erzrf.ru"],
                )
            ],
            followup_prompts=[
                FollowupPrompt(
                    prompt_id="fp_01",
                    intent="fill_gap",
                    prompt="Find delay % on erzrf.ru for PIK, Donstroy, MR Group.",
                    target_info="delay",
                    suggested_tool="perplexity",
                    suggested_source_site="erzrf.ru",
                    priority="must",
                    linked_to="gap:delivery_delays",
                )
            ],
        ),
        status="analyzed",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_llm(monkeypatch):
    async def _stub(*args, **kwargs):
        return LLMResult(text=json.dumps(_MOCK_FINAL_JSON, ensure_ascii=False), cost_rub=0.0)

    monkeypatch.setattr(synth_module, "call_json", _stub)


@pytest.mark.asyncio
async def test_synthesizer_returns_final_report(mock_llm):
    session = _session_with_analysis()
    final, cost_rub = await synthesize_final_report(session)
    assert isinstance(final, FinalReport)
    assert cost_rub == 0.0  # mocked
    assert final.session_id == "sess01"  # session id wins over LLM echo
    assert final.executive_summary.main_answer
    assert final.executive_summary.ranking and "Продукт" in final.executive_summary.ranking
    assert len(final.executive_summary.top_findings) == 3
    assert len(final.executive_summary.key_numbers) == 2
    assert len(final.all_sources) == 2
    assert final.metadata.get("source_reports_count") == 2
    assert final.metadata.get("consensus_count") == 1
    assert final.metadata.get("conflicts_count") == 1
    assert final.metadata.get("gaps_count") == 1


@pytest.mark.asyncio
async def test_synthesizer_includes_followup_reports_in_prompt_and_metadata(monkeypatch):
    captured: dict[str, object] = {}

    async def _stub(*args, **kwargs):
        captured["messages"] = kwargs["messages"]
        return LLMResult(text=json.dumps(_MOCK_FINAL_JSON, ensure_ascii=False), cost_rub=0.0)

    monkeypatch.setattr(synth_module, "call_json", _stub)

    session = _session_with_analysis()
    session.followup_reports = [
        UploadedMarkdown(
            filename="auto_followup_paper_search_required_source_families.md",
            content=(
                "Smart Report analytic-depth lead: required_source_families\n"
                "Paper-search evidence: Central Bank policy pass-through narrows the "
                "mortgage-sensitive buyer pool; https://example.org/paper"
            ),
            detected_tool="paper_search_mcp",
        ),
        UploadedMarkdown(
            filename="auto_followup_openai_gap_1.md",
            content="Gap evidence: delivery delays are concentrated in two developers.",
            detected_tool="openai_dr",
        ),
    ]

    final, _ = await synthesize_final_report(session)

    messages = captured["messages"]
    assert isinstance(messages, list)
    user_prompt = messages[1]["content"]
    assert "## Follow-up reports (round 2, dobor, n=2)" in user_prompt
    assert "auto_followup_paper_search_required_source_families.md" in user_prompt
    assert "Smart Report analytic-depth lead: required_source_families" in user_prompt
    assert "Gap evidence: delivery delays" in user_prompt
    assert final.metadata["followup_reports_count"] == 2
    assert final.metadata["followup_evidence_present"] is True
    assert final.metadata["followup_report_filenames"] == [
        "auto_followup_paper_search_required_source_families.md",
        "auto_followup_openai_gap_1.md",
    ]
    assert final.metadata["followup_report_tools"] == ["paper_search_mcp", "openai_dr"]


@pytest.mark.asyncio
async def test_synthesizer_rejects_missing_analysis():
    session = _session_with_analysis()
    session.analysis = None
    with pytest.raises(ValueError):
        await synthesize_final_report(session)  # raises before LLM call


@pytest.mark.asyncio
async def test_synthesizer_rejects_empty_sources():
    session = _session_with_analysis()
    session.source_reports = []
    with pytest.raises(ValueError):
        await synthesize_final_report(session)  # raises before LLM call


@pytest.mark.asyncio
async def test_synthesizer_remediates_thin_llm_output(monkeypatch):
    thin = {
        "session_id": "ignored",
        "question": "Will the market rise?",
        "executive_summary": {
            "main_answer": "The market is likely to rise, but uncertainty remains.",
            "top_findings": [
                "Demand is stronger than supply.",
                "Rates remain the main risk.",
                "Source quality is mixed.",
            ],
            "key_numbers": [
                {
                    "value": "12%",
                    "metric": "price growth",
                    "subject": "baseline scenario",
                    "source_url": "https://example.com/source",
                }
            ],
        },
        "main_synthesis": "Short output.",
        "all_sources": [
            {
                "title": "Primary source",
                "url": "https://example.com/source",
                "tool": "paper_search_mcp:arxiv",
                "reliability": "high",
            }
        ],
        "tables": [],
        "charts": [],
        "callouts": [],
        "key_numbers_highlight": [],
    }

    async def _stub(*args, **kwargs):
        return LLMResult(text=json.dumps(thin, ensure_ascii=False), cost_rub=0.0)

    monkeypatch.setattr(synth_module, "call_json", _stub)
    session = _session_with_analysis()
    session.analysis.all_numeric_facts = [
        NumericFact(
            fact_id="f1",
            value="12%",
            metric="price growth",
            subject="baseline scenario",
            timeframe="2026",
            relevance_to_question="high",
            sources=[
                SourceRef(
                    title="Primary source",
                    url="https://example.com/source",
                    confidence="primary",
                )
            ],
        )
    ]
    session.analysis.high_relevance_facts = list(session.analysis.all_numeric_facts)

    final, _ = await synthesize_final_report(session)

    assert len(final.main_synthesis) >= 1000
    assert len(final.tables) >= 3
    assert len(final.charts) >= 3
    assert len(final.callouts) >= 3
    assert len(final.key_numbers_highlight) >= 1
    assert "[REF:https://example.com/source]" in final.executive_summary.main_answer
    assert final.metadata["synthesis_remediation_applied"] is True
