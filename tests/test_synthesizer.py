"""Synthesizer schema/IO test — LLM mocked."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from smart_report import synthesizer as synth_module
from smart_report.models import (
    AnalysisOutput,
    ConsensusClaim,
    Conflict,
    FinalReport,
    FollowupPrompt,
    Gap,
    ResearchPrompt,
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
        return json.dumps(_MOCK_FINAL_JSON, ensure_ascii=False)

    monkeypatch.setattr(synth_module, "chat", _stub)


@pytest.mark.asyncio
async def test_synthesizer_returns_final_report(mock_llm):
    session = _session_with_analysis()
    final = await synthesize_final_report(session)
    assert isinstance(final, FinalReport)
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
async def test_synthesizer_rejects_missing_analysis():
    session = _session_with_analysis()
    session.analysis = None
    with pytest.raises(ValueError):
        await synthesize_final_report(session)


@pytest.mark.asyncio
async def test_synthesizer_rejects_empty_sources():
    session = _session_with_analysis()
    session.source_reports = []
    with pytest.raises(ValueError):
        await synthesize_final_report(session)
