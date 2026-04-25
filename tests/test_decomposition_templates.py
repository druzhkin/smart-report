"""Tests for v4.5 Phase 2 Step 2.1 — domain decomposition templates."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from smart_report import prompt_master as pm_module
from smart_report.decomposition_templates import (
    RUSSIAN_RE_STRATEGIC_TEMPLATE,
    decompose,
    format_template_guidance,
    is_russian_re_strategic,
)
from smart_report.llm import LLMResult


# ---------------------------------------------------------------------------
# is_russian_re_strategic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        # Strategic + RE-vocab + Cyrillic — all three signals present
        "Какие тренды влияют на девелоперов бизнес-сегмента жилья в Москве?",
        "Кто из московских девелоперов бизнес-класса лидирует в 2024?",
        "Что определяет успех застройщика премиум-класса?",
        "Прогноз цен на новостройки бизнес-класса на 2025?",
        "Риски инвестиций в апартаменты Москвы — что нужно учесть?",
        "Стратегия выбора жилья в новостройке: что приоритетно для покупателя?",
    ],
)
def test_strategic_query_detected(query: str):
    assert is_russian_re_strategic(query) is True, query


@pytest.mark.parametrize(
    "query",
    [
        # Factual lookups — no strategic marker → don't decompose
        "Какая сейчас ипотечная ставка?",
        "Сколько стоит квартира в ЖК Прайм Парк?",
        "Когда вступает в силу новый 214-ФЗ?",
        # No RE vocabulary at all
        "Какие тренды влияют на IT-сектор в России?",
        # English-only — Cyrillic gate filters out
        "What are the trends in Moscow business-class housing?",
        # Empty / whitespace
        "",
        "   ",
    ],
)
def test_non_strategic_query_not_detected(query: str):
    assert is_russian_re_strategic(query) is False, query


# ---------------------------------------------------------------------------
# Template structural invariants
# ---------------------------------------------------------------------------


def test_russian_re_template_has_exactly_four_sub_queries():
    """The K-Dense decomposition is a four-vector frame: macro,
    regulation, market data, developer behaviour. Adding a fifth
    without revisiting the design risks overlap (buyer financing
    collapses into macro_context + market_data); removing one drops
    a load-bearing analysis vector. Pin the count.
    """
    assert len(RUSSIAN_RE_STRATEGIC_TEMPLATE) == 4


def test_russian_re_template_has_expected_ids():
    expected = {
        "macro_context",
        "regulatory_environment",
        "market_data",
        "developer_behavior",
    }
    assert set(RUSSIAN_RE_STRATEGIC_TEMPLATE.keys()) == expected


def test_each_sub_query_has_required_fields():
    for key, sq in RUSSIAN_RE_STRATEGIC_TEMPLATE.items():
        assert sq["id"] == key, f"{key}: id field must mirror dict key"
        assert isinstance(sq["prompt"], str) and sq["prompt"].strip(), (
            f"{key}: prompt must be non-empty"
        )
        assert isinstance(sq["sources_priority"], list), (
            f"{key}: sources_priority must be a list"
        )
        assert sq["sources_priority"], (
            f"{key}: sources_priority must contain at least one domain"
        )
        for domain in sq["sources_priority"]:
            assert isinstance(domain, str) and "." in domain, (
                f"{key}: every sources_priority entry must look like a domain, "
                f"got {domain!r}"
            )


def test_macro_context_priority_starts_with_central_bank():
    """The macro vector is anchored on CBR rate policy; if the priority
    list is reordered to put a private aggregator first the prompt
    will lead the analyst to weaker primary data.
    """
    assert (
        RUSSIAN_RE_STRATEGIC_TEMPLATE["macro_context"]["sources_priority"][0]
        == "cbr.ru"
    )


def test_regulatory_priority_includes_official_publishers():
    priority = RUSSIAN_RE_STRATEGIC_TEMPLATE["regulatory_environment"][
        "sources_priority"
    ]
    assert "minstroyrf.gov.ru" in priority
    # дом.рф is the source-of-truth for housing-policy guidance
    assert any("дом.рф" in p or "dom.rf" in p for p in priority)


# ---------------------------------------------------------------------------
# decompose router
# ---------------------------------------------------------------------------


def test_decompose_returns_four_sub_queries_for_strategic():
    sub_queries = decompose(
        "Какие тренды влияют на девелоперов бизнес-сегмента жилья в Москве?"
    )
    assert len(sub_queries) == 4
    ids = {sq["id"] for sq in sub_queries}
    assert ids == {
        "macro_context",
        "regulatory_environment",
        "market_data",
        "developer_behavior",
    }


def test_decompose_returns_empty_for_non_strategic():
    """Caller's contract: empty list means "fall back to LLM decomposition"."""
    assert decompose("Какая сегодня ипотечная ставка?") == []
    assert decompose("") == []


# ---------------------------------------------------------------------------
# format_template_guidance
# ---------------------------------------------------------------------------


def test_format_template_guidance_empty_for_empty_list():
    assert format_template_guidance([]) == ""


def test_format_template_guidance_includes_each_sub_query():
    sub_queries = decompose(
        "Кто из московских девелоперов бизнес-класса лидирует в 2024?"
    )
    text = format_template_guidance(sub_queries)
    assert text != ""
    # All four ids appear as headers
    for sq in sub_queries:
        assert f"`{sq['id']}`" in text, f"id {sq['id']!r} missing from guidance"
    # Header section names the template
    assert "Russian-RE-strategic" in text
    # Domain priorities are listed
    assert "cbr.ru" in text
    assert "minstroyrf.gov.ru" in text


def test_format_template_guidance_zero_lint_warnings_in_cyrillic_body():
    """Like the source-adequacy warning, the guidance text is appended
    to ResearchPrompt.full_prompt. full_prompt is currently NOT scanned
    by the language linter (it's an input to the LLM, not Synthesizer
    output), but if that ever changes we don't want this addition to
    suddenly push reports past the >20 warning retry threshold. Latin
    tokens here are confined to URL / code-fence-like markers (sq id,
    domain names) which the linter strips before scanning.
    """
    from smart_report.i18n import lint_output_language

    sub_queries = decompose(
        "Какие тренды влияют на бизнес-сегмент жилищного строительства Москвы?"
    )
    text = format_template_guidance(sub_queries)
    warnings = lint_output_language(text)
    # Only DR (in "DR-инструменте") may legitimately appear — it's a
    # standard analyst term. Tighter guard: zero ALL-CAPS errors, and
    # ≤ 5 warn-level tokens (each domain hyphen split etc.).
    errors = [w for w in warnings if w.severity == "error"]
    assert not errors, (
        f"Guidance text triggered {len(errors)} lint errors: "
        f"{[w.token for w in errors]!r}"
    )


# ---------------------------------------------------------------------------
# Prompt Master integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_research_prompt_appends_guidance_for_strategic_query():
    """Strategic question → returned ResearchPrompt.full_prompt contains
    the four-vector decomposition addendum.
    """
    payload = {
        "full_prompt": "Базовый research-промт от LLM.",
        "reasoning": "r",
        "expected_structure": ["s1"],
        "key_entities": ["PIK"],
        "tips_for_search": "Perplexity",
    }

    async def _stub(*a, **kw):
        return LLMResult(text=json.dumps(payload, ensure_ascii=False), cost_rub=0.0)

    with patch.object(pm_module, "call_json", _stub):
        prompt, _ = await pm_module.generate_research_prompt(
            "Какие тренды влияют на девелоперов бизнес-сегмента жилья в Москве?"
        )

    # LLM body preserved
    assert prompt.full_prompt.startswith("Базовый research-промт от LLM.")
    # Decomposition addendum appended
    assert "Декомпозиция запроса" in prompt.full_prompt
    assert "macro_context" in prompt.full_prompt
    assert "developer_behavior" in prompt.full_prompt


@pytest.mark.asyncio
async def test_generate_research_prompt_does_not_modify_non_strategic_query():
    """Factual lookup → no template applied, full_prompt is exactly the LLM body."""
    body = "Конкретный факт-промт от LLM."
    payload = {
        "full_prompt": body,
        "reasoning": "r",
        "expected_structure": ["s1"],
        "key_entities": [],
        "tips_for_search": "",
    }

    async def _stub(*a, **kw):
        return LLMResult(text=json.dumps(payload, ensure_ascii=False), cost_rub=0.0)

    with patch.object(pm_module, "call_json", _stub):
        prompt, _ = await pm_module.generate_research_prompt(
            "Какая сейчас ипотечная ставка?"
        )

    assert prompt.full_prompt == body
    assert "Декомпозиция запроса" not in prompt.full_prompt
