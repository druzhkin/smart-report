"""Integration tests for the v4.5 Phase 2 Step 2.2 three-way routing.

Locks in the precedence and outputs of the Prompt Master decomposition
router:
  1. Russian RE strategic     → domain template (no extra LLM)
  2. Other strategic queries  → LLM planner (one extra LLM call)
  3. Factual / short queries  → no decomposition

Each path must populate ``ResearchPrompt.decomposition_method`` and
``sub_questions`` correctly so downstream observability (trace
events, frontend UI) and future C6 gap-detection can branch on the
decomposition signal.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from smart_report import prompt_master as pm_module
from smart_report.llm import LLMResult
from smart_report.models import SubQuestion


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


_PM_STUB_PAYLOAD = {
    "full_prompt": "Базовый research-промт от LLM длиной 50+ символов.",
    "reasoning": "rationale stub",
    "expected_structure": ["Section A"],
    "key_entities": ["PIK"],
    "tips_for_search": "use perplexity",
}


def _pm_stub():
    async def _s(*a, **kw):
        return LLMResult(text=json.dumps(_PM_STUB_PAYLOAD, ensure_ascii=False), cost_rub=0.0)
    return _s


def _planner_stub_returning(sub_qs: list[dict]):
    async def _s(*a, **kw):
        # Mimics what the orchestrator passes through generate_sub_questions:
        # raw JSON text via call_json that gets parsed inside the planner.
        return LLMResult(
            text=json.dumps({"sub_questions": sub_qs}, ensure_ascii=False),
            cost_rub=0.5,
        )
    return _s


# ---------------------------------------------------------------------------
# Path 1: Russian RE strategic → domain template
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_russian_re_strategic_uses_domain_template_skips_planner():
    """RU RE strategic query → template path; planner LLM must NOT be called.

    Domain-template-first precedence saves the planner cost on every
    RU RE run (the most common production case for Smart Report).
    """
    planner_call_count = 0

    async def planner_should_not_run(*a, **kw):
        nonlocal planner_call_count
        planner_call_count += 1
        return LLMResult(text='{"sub_questions": []}', cost_rub=0.0)

    with patch.object(pm_module, "call_json", _pm_stub()), \
         patch(
            "smart_report.decomposition_templates.call_json",
            new=planner_should_not_run,
        ):
        prompt, _ = await pm_module.generate_research_prompt(
            "Какие тренды повлияют на девелоперов бизнес-сегмента жилья в Москве?"
        )

    assert prompt.decomposition_method == "domain_template_ru_re"
    assert planner_call_count == 0, (
        "Domain-template path must short-circuit before invoking the planner LLM"
    )
    # Template guidance addendum present
    assert "Декомпозиция запроса (template Russian-RE-strategic)" in prompt.full_prompt
    assert "macro_context" in prompt.full_prompt
    # SubQuestion list stays empty for this path — template uses the
    # SubQuery TypedDict format inline in full_prompt, not the
    # Step 2.2 structured schema. The two paths intentionally share
    # only the guidance shape, not the data model.
    assert prompt.sub_questions == []


# ---------------------------------------------------------------------------
# Path 2: Other strategic → LLM planner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_re_strategic_uses_llm_planner():
    """English strategic query → LLM planner; populates sub_questions."""
    planner_payload = [
        {
            "id": "sq1",
            "text": "What are the feature differences between Langfuse, LangSmith, Helicone?",
            "depends_on": [],
            "rationale": "Establishes the competitive baseline.",
            "suggested_sources": ["vendor_docs"],
        },
        {
            "id": "sq2",
            "text": "How do their pricing models scale to enterprise volumes?",
            "depends_on": ["sq1"],
            "rationale": "Translates features into TCO at target scale.",
            "suggested_sources": ["vendor_docs", "market_data"],
        },
        {
            "id": "sq3",
            "text": "What real-world adoption signals exist (case studies, public ARR mentions)?",
            "depends_on": [],
            "rationale": "Grounds the comparison in production deployments.",
            "suggested_sources": ["case_study", "news"],
        },
    ]

    with patch.object(pm_module, "call_json", _pm_stub()), \
         patch(
            "smart_report.decomposition_templates.call_json",
            new=_planner_stub_returning(planner_payload),
        ):
        prompt, _ = await pm_module.generate_research_prompt(
            "Compare LLM observability platforms (Langfuse, LangSmith, Helicone) for enterprise scale"
        )

    assert prompt.decomposition_method == "llm_planner"
    assert len(prompt.sub_questions) == 3
    assert all(isinstance(sq, SubQuestion) for sq in prompt.sub_questions)
    # Dependency tracking made it through end-to-end
    assert prompt.sub_questions[1].depends_on == ["sq1"]
    # Planner guidance addendum in full_prompt
    assert "planner LLM" in prompt.full_prompt
    assert "sq1" in prompt.full_prompt


@pytest.mark.asyncio
async def test_planner_failure_falls_back_to_llm_planner_failed():
    """When the planner returns no usable sub-questions, the
    decomposition_method must record the failure rather than masquerading
    as 'none' (which would hide that we tried and failed).
    """
    with patch.object(pm_module, "call_json", _pm_stub()), \
         patch(
            "smart_report.decomposition_templates.call_json",
            new=_planner_stub_returning([]),  # empty sub_questions
        ):
        prompt, _ = await pm_module.generate_research_prompt(
            "Compare LLM observability platforms (Langfuse, LangSmith, Helicone) for enterprise scale"
        )

    assert prompt.decomposition_method == "llm_planner_failed"
    assert prompt.sub_questions == []
    # full_prompt remains the LLM-generated body (no addendum)
    assert prompt.full_prompt == _PM_STUB_PAYLOAD["full_prompt"]


# ---------------------------------------------------------------------------
# Path 3: Factual / short → no decomposition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_factual_short_query_skips_decomposition():
    """Short factual lookup → neither template nor planner; method='none'."""
    planner_call_count = 0

    async def planner_should_not_run(*a, **kw):
        nonlocal planner_call_count
        planner_call_count += 1
        return LLMResult(text='{"sub_questions": []}', cost_rub=0.0)

    with patch.object(pm_module, "call_json", _pm_stub()), \
         patch(
            "smart_report.decomposition_templates.call_json",
            new=planner_should_not_run,
        ):
        prompt, _ = await pm_module.generate_research_prompt(
            "Какая сейчас ставка ЦБ?"
        )

    assert prompt.decomposition_method == "none"
    assert prompt.sub_questions == []
    assert planner_call_count == 0
    # full_prompt is exactly what the LLM returned, no addendum
    assert prompt.full_prompt == _PM_STUB_PAYLOAD["full_prompt"]


# ---------------------------------------------------------------------------
# Backward-compat: legacy callers ignore the new fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_call_path_still_works_without_new_kwargs():
    """No planner_model kwarg, no consumers of decomposition_method
    in tests/cost_accumulation should break — defaults preserve old
    contract.
    """
    with patch.object(pm_module, "call_json", _pm_stub()):
        prompt, cost = await pm_module.generate_research_prompt(
            "Какая сейчас ставка ЦБ?"
        )
    assert prompt.full_prompt
    assert cost == 0.0  # stub
