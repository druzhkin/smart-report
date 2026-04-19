"""Analyzer schema/IO test — LLM is mocked to return deterministic JSON.

This is NOT a quality test. It verifies that given a well-formed JSON response
from the Analyzer LLM, the module shapes it into a valid AnalysisOutput with
all expected fields populated. Real quality is covered by the smoke run.
"""

from __future__ import annotations

import json

import pytest

from smart_report import analyzer as analyzer_module
from smart_report.analyzer import analyze_reports, _coerce_analysis
from smart_report.llm import LLMResult
from smart_report.models import AnalysisOutput, FollowupPrompt, ResearchPrompt, UploadedMarkdown


_REPORT_A = UploadedMarkdown(
    filename="perplexity.md",
    content=(
        "# Moscow developers 2024\n\n"
        "Top-5 developers account for 47% of business-class launches in 2024 "
        "per ERZ. PIK leads with 18% share, Donstroy 12%, Etalon 9%. "
        "Mortgage take-up in business class fell from 78% (2023) to 55% (2024)."
    ),
    detected_tool="perplexity",
    word_count=40,
)

_REPORT_B = UploadedMarkdown(
    filename="openai_dr.md",
    content=(
        "# Moscow business-class brief\n\n"
        "Knight Frank reports mortgage penetration in business-class Moscow at "
        "68% in 2024. Top developers include PIK, Donstroy, MR Group."
    ),
    detected_tool="openai_dr",
    word_count=30,
)


_MOCK_ANALYSIS_JSON = {
    "per_source_summary": [
        {
            "source": "perplexity",
            "summary": "Hard numbers on developer concentration and mortgage mix.",
            "strengths": "ERZ-sourced shares",
            "weaknesses": "No time-series beyond 2023-2024",
        },
        {
            "source": "openai_dr",
            "summary": "Narrative overview with Knight Frank benchmarks.",
            "strengths": "Names players",
            "weaknesses": "Vendor-biased mortgage figure",
        },
    ],
    "consensus": [
        {
            "claim": "PIK leads Moscow business-class by market share in 2024.",
            "supporting_sources": ["perplexity", "openai_dr"],
            "confidence": "high",
        },
        {
            "claim": "Donstroy is in the top three developers.",
            "supporting_sources": ["perplexity", "openai_dr"],
            "confidence": "medium",
        },
    ],
    "conflicts": [
        {
            "topic": "mortgage penetration in business-class 2024",
            "source_a": "perplexity",
            "claim_a": "55%",
            "source_b": "openai_dr",
            "claim_b": "68% per Knight Frank",
            "resolution_hint": "Cross-check ERZ aggregate vs Knight Frank premium slice",
            "importance": "critical",
        }
    ],
    "gaps": [
        {
            "topic": "per-project delivery delays",
            "why_critical": "Speed claims need measurable delivery slippage per developer",
            "what_to_find": "% delay for PIK, Donstroy, MR Group, Etalon, Sminex",
            "candidate_sources": ["erzrf.ru", "mos.ru"],
        }
    ],
    "unverified_numbers": [
        {
            "value": "68%",
            "metric": "mortgage penetration",
            "subject": "business-class Moscow 2024",
            "source_tool": "openai_dr",
            "why_unverified": "Knight Frank vendor report, premium slice bias",
        }
    ],
    "quality_notes": (
        "Perplexity gave ERZ-grounded numbers; OpenAI DR used vendor reports. "
        "Neither provided developer-level delivery metrics."
    ),
    "followup_prompts": [
        {
            "prompt_id": "fp_01",
            "intent": "verify_number",
            "prompt": (
                "Find on erzrf.ru the 2024 mortgage-share breakdown for Moscow "
                "business-class new builds, with URL to the underlying page."
            ),
            "target_info": "mortgage share 2024 business-class",
            "suggested_tool": "perplexity",
            "suggested_source_site": "erzrf.ru",
            "priority": "must",
            "linked_to": "conflict:mortgage_share",
        },
        {
            "prompt_id": "fp_02",
            "intent": "fill_gap",
            "prompt": (
                "Fetch per-developer deadline-slip percentage for 2025 projects "
                "from erzrf.ru for Donstroy, MR Group, Level Group, PIK, Etalon, Sminex."
            ),
            "target_info": "deadline slippage 2025",
            "suggested_tool": "perplexity",
            "suggested_source_site": "erzrf.ru",
            "priority": "must",
            "linked_to": "gap:delivery_delays",
        },
    ],
}


@pytest.fixture
def mock_llm(monkeypatch):
    async def _stub(*args, **kwargs):
        return LLMResult(text=json.dumps(_MOCK_ANALYSIS_JSON, ensure_ascii=False), cost_rub=0.0)

    monkeypatch.setattr(analyzer_module, "call_json", _stub)


@pytest.mark.asyncio
async def test_analyzer_returns_shaped_output(mock_llm):
    research_prompt = ResearchPrompt(
        full_prompt="Analyse Moscow developers for 2024.", reasoning="frame"
    )
    out, cost_rub = await analyze_reports(
        question="What defines developer success in Moscow business real estate?",
        research_prompt=research_prompt,
        source_reports=[_REPORT_A, _REPORT_B],
    )
    assert isinstance(out, AnalysisOutput)
    assert cost_rub == 0.0  # mocked
    assert len(out.per_source_summary) == 2
    assert len(out.consensus) >= 1
    assert len(out.conflicts) == 1
    assert out.conflicts[0].importance == "critical"
    assert len(out.gaps) >= 1
    assert len(out.unverified_numbers) == 1
    assert len(out.followup_prompts) == 2
    assert out.followup_prompts[0].suggested_source_site == "erzrf.ru"
    assert out.quality_notes


@pytest.mark.asyncio
async def test_analyzer_caps_followups_at_8(monkeypatch):
    """If the LLM returns more than 8 followups we cap."""
    many = dict(_MOCK_ANALYSIS_JSON)
    many["followup_prompts"] = [
        {
            "prompt_id": f"fp_{i:02d}",
            "intent": "fill_gap",
            "prompt": f"Sample prompt {i}",
            "target_info": "x",
            "suggested_tool": "perplexity",
            "suggested_source_site": "",
            "priority": "nice",
            "linked_to": "",
        }
        for i in range(1, 15)
    ]

    async def _stub(*args, **kwargs):
        return LLMResult(text=json.dumps(many, ensure_ascii=False), cost_rub=0.0)

    monkeypatch.setattr(analyzer_module, "call_json", _stub)

    out, _ = await analyze_reports(
        question="Q", research_prompt=None, source_reports=[_REPORT_A]
    )
    assert len(out.followup_prompts) == 8


@pytest.mark.asyncio
async def test_analyzer_rejects_empty_source_reports():
    with pytest.raises(ValueError):
        await analyze_reports(
            question="Q", research_prompt=None, source_reports=[]
        )


@pytest.mark.asyncio
async def test_analyzer_recovers_from_fenced_json(monkeypatch):
    """Claude on OpenRouter often wraps JSON in ```json fences even when asked not to."""

    async def _stub(*args, **kwargs):
        return LLMResult(
            text="```json\n" + json.dumps(_MOCK_ANALYSIS_JSON, ensure_ascii=False) + "\n```",
            cost_rub=0.0,
        )

    monkeypatch.setattr(analyzer_module, "call_json", _stub)
    out, _ = await analyze_reports(
        question="Q", research_prompt=None, source_reports=[_REPORT_A]
    )
    assert len(out.consensus) >= 1


# ---------------------------------------------------------------------------
# v4.1 single-prompt tests
# ---------------------------------------------------------------------------

_MOCK_SINGLE_PROMPT_JSON = {
    **_MOCK_ANALYSIS_JSON,
    "followup_prompt": {
        "prompt_id": "fp_consolidated",
        "intent": "fill_gap",
        "prompt": (
            "## Gap: Per-developer delivery delays\n"
            "Fetch per-developer deadline-slip percentage for 2025 projects "
            "from erzrf.ru for Donstroy, MR Group, Level Group, PIK, Etalon, Sminex.\n\n"
            "## Conflict: Mortgage penetration 2024\n"
            "Find on erzrf.ru the 2024 mortgage-share breakdown for Moscow "
            "business-class new builds (full segment vs premium tier), with URL "
            "to the underlying page. Goal: resolve ERZ 55% vs Knight Frank 68%."
        ),
        "target_info": "1 gap + 1 conflict",
        "suggested_tool": "perplexity",
        "suggested_source_site": "erzrf.ru",
        "priority": "must",
        "linked_to": "gap:delivery-delays | conflict:mortgage-penetration",
    },
    "followup_prompts": [],
}


@pytest.fixture
def mock_llm_single(monkeypatch):
    async def _stub(*args, **kwargs):
        return LLMResult(
            text=json.dumps(_MOCK_SINGLE_PROMPT_JSON, ensure_ascii=False), cost_rub=0.0
        )

    monkeypatch.setattr(analyzer_module, "call_json", _stub)


@pytest.mark.asyncio
async def test_analyzer_single_prompt_populated(mock_llm_single):
    """Path A: followup_prompt dict returned by LLM is parsed into the new field."""
    out, _ = await analyze_reports(
        question="Q?",
        research_prompt=None,
        source_reports=[_REPORT_A, _REPORT_B],
    )
    assert out.followup_prompt is not None
    assert isinstance(out.followup_prompt, FollowupPrompt)
    assert out.followup_prompt.prompt_id == "fp_consolidated"
    assert out.followup_prompt.priority == "must"
    assert len(out.followup_prompt.prompt) >= 100
    # Shim: legacy list gets the single prompt
    assert len(out.followup_prompts) >= 1
    assert out.followup_prompts[0].prompt_id == "fp_consolidated"


@pytest.mark.asyncio
async def test_analyzer_legacy_promotes_first_must(mock_llm):
    """Path B: when only followup_prompts array is present, first MUST is promoted."""
    out, _ = await analyze_reports(
        question="Q",
        research_prompt=None,
        source_reports=[_REPORT_A],
    )
    # _MOCK_ANALYSIS_JSON has no followup_prompt key, so Path B kicks in
    assert out.followup_prompt is not None
    assert out.followup_prompt.priority == "must"
    assert out.followup_prompt.prompt_id == "fp_01"


# ---------------------------------------------------------------------------
# Unit tests for _coerce_analysis directly (no async, no LLM)
# ---------------------------------------------------------------------------


def test_coerce_single_prompt_path_a():
    """Path A: followup_prompt dict is parsed; shim list is populated."""
    data = {
        "followup_prompt": {
            "prompt_id": "fp_consolidated",
            "intent": "fill_gap",
            "prompt": "## Gap: something\nFind this on erzrf.ru.",
            "target_info": "1 gap",
            "suggested_tool": "perplexity",
            "suggested_source_site": "erzrf.ru",
            "priority": "must",
            "linked_to": "gap:something",
        },
        "followup_prompts": [],
    }
    out = _coerce_analysis(data)
    assert out.followup_prompt is not None
    assert out.followup_prompt.prompt_id == "fp_consolidated"
    assert out.followup_prompt.priority == "must"
    assert len(out.followup_prompts) == 1
    assert out.followup_prompts[0].prompt_id == "fp_consolidated"


def test_coerce_single_prompt_path_b_promotes():
    """Path B: legacy array only — first MUST item is promoted."""
    data = {
        "followup_prompts": [
            {
                "prompt_id": "fp_01",
                "intent": "verify_number",
                "prompt": "Check erzrf.ru for Etalon delay 2025.",
                "target_info": "delay check",
                "suggested_tool": "perplexity",
                "suggested_source_site": "erzrf.ru",
                "priority": "must",
                "linked_to": "unverified:etalon",
            },
            {
                "prompt_id": "fp_02",
                "intent": "fill_gap",
                "prompt": "Find marketing budgets on spark-interfax.ru.",
                "target_info": "marketing budgets",
                "suggested_tool": "perplexity",
                "suggested_source_site": "spark-interfax.ru",
                "priority": "nice",
                "linked_to": "gap:marketing",
            },
        ],
    }
    out = _coerce_analysis(data)
    assert out.followup_prompt is not None
    assert out.followup_prompt.prompt_id == "fp_01"
    assert len(out.followup_prompts) == 2


def test_coerce_no_followup_yields_none():
    """Empty data -> followup_prompt is None, followup_prompts is empty."""
    out = _coerce_analysis({})
    assert out.followup_prompt is None
    assert out.followup_prompts == []


def test_coerce_path_a_null_falls_to_path_b():
    """followup_prompt: null falls through to Path B."""
    data = {
        "followup_prompt": None,
        "followup_prompts": [
            {
                "prompt_id": "fp_01",
                "intent": "fill_gap",
                "prompt": "Find something on cbr.ru.",
                "target_info": "x",
                "suggested_tool": "perplexity",
                "suggested_source_site": "cbr.ru",
                "priority": "must",
                "linked_to": "",
            }
        ],
    }
    out = _coerce_analysis(data)
    assert out.followup_prompt is not None
    assert out.followup_prompt.prompt_id == "fp_01"


def test_coerce_path_a_priority_forced_to_must():
    """Even if LLM puts priority=nice in the single dict, coercer forces must."""
    data = {
        "followup_prompt": {
            "prompt_id": "fp_consolidated",
            "intent": "fill_gap",
            "prompt": "Some consolidated prompt text here.",
            "target_info": "x",
            "suggested_tool": "perplexity",
            "suggested_source_site": "",
            "priority": "nice",
            "linked_to": "",
        },
    }
    out = _coerce_analysis(data)
    assert out.followup_prompt is not None
    assert out.followup_prompt.priority == "must"
