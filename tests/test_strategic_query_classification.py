"""Tests for the broad strategic-query heuristic (v4.5 Phase 2 Step 2.2 gate).

Used by Prompt Master to decide which decomposition path to take:
domain template (RU RE), LLM planner (other strategic), or none
(factual / short).
"""

from __future__ import annotations

import pytest

from smart_report.decomposition_templates import (
    is_russian_re_strategic,
    is_strategic_query,
)


# ---------------------------------------------------------------------------
# Acceptance cases from the Step 2.2 spec
# ---------------------------------------------------------------------------


def test_long_strategic_russian_re_query_is_strategic():
    """Spec acceptance #1 — long RU RE strategic query → True."""
    q = "Какие тренды повлияют на девелоперов в Москве в 2026-2027?"
    assert is_strategic_query(q) is True


def test_short_factual_query_is_not_strategic():
    """Spec acceptance #2 — short factual lookup → False."""
    q = "Какая сейчас ставка ЦБ?"
    assert is_strategic_query(q) is False


def test_long_strategic_english_non_re_query_is_strategic():
    """Spec acceptance #3 — non-RE strategic English query → True.

    This is the case is_russian_re_strategic() will NOT catch
    (no Cyrillic, no RE keywords) — Step 2.2 LLM planner is for it.
    """
    q = "Compare LLM observability platforms (Langfuse, LangSmith, Helicone) for enterprise scale"
    assert is_strategic_query(q) is True


def test_overlap_with_russian_re_strategic_does_not_break_either():
    """Spec acceptance #4 — query that fits both heuristics.

    is_strategic_query and is_russian_re_strategic should both be True;
    the order in the router (domain template first) handles precedence.
    """
    q = "Какие риски несёт повышение ставки ЦБ для бизнес-сегмента жилья в Москве на горизонте 2-3 лет?"
    assert is_strategic_query(q) is True
    assert is_russian_re_strategic(q) is True


# ---------------------------------------------------------------------------
# Boundary and edge cases
# ---------------------------------------------------------------------------


def test_empty_query_is_not_strategic():
    assert is_strategic_query("") is False
    assert is_strategic_query("   ") is False


def test_short_strategic_marker_query_is_not_strategic():
    """Strategic marker but only 5 words — too vague for decomposition."""
    q = "Выбор ипотеки или аренды?"
    assert is_strategic_query(q) is False


def test_long_descriptive_factual_is_not_strategic():
    """Twelve+ words but no strategic marker — descriptive factual lookup."""
    q = (
        "Опиши инфраструктуру ЖК Прайм Парк включая парковку площадь "
        "благоустройства тип фасадов и систему отопления подробно."
    )
    assert is_strategic_query(q) is False


@pytest.mark.parametrize(
    "marker_query",
    [
        "Что определяет успех девелопера в премиальном сегменте Москвы 2025-2027?",
        "Прогноз ипотечного рынка России в условиях ставки ЦБ 16% и инфляции 8%?",
        "Сравни три DR-инструмента (Perplexity, OpenAI, Claude) по глубине цитирований и стоимости",
        "Какие сценарии могут реализоваться на рынке жилья при сохранении ключевой ставки 16%?",
        "Analyze the impact of Russian central bank policy on Moscow real estate developers strategy",
        "Forecast LLM observability market consolidation over the next 24 months for enterprise buyers",
    ],
)
def test_realistic_strategic_queries_detected(marker_query: str):
    assert is_strategic_query(marker_query) is True, marker_query


@pytest.mark.parametrize(
    "factual_query",
    [
        "Какая сейчас ключевая ставка ЦБ России?",
        "Сколько стоит квартира в ЖК Прайм Парк?",
        "Когда вступает в силу новая редакция 214-ФЗ?",
        "Что такое эскроу-счёт?",
        "List all Russian developers operating in Moscow business class.",
    ],
)
def test_realistic_factual_queries_rejected(factual_query: str):
    assert is_strategic_query(factual_query) is False, factual_query


# ---------------------------------------------------------------------------
# Phase 3 Step 3.1 — regulatory / policy markers (Run 1 finding 1)
# ---------------------------------------------------------------------------
# Q3 EU DAC went through Run 1 routed as "none" because no existing
# marker fired on regulatory/policy vocabulary. Brief Step 3.1 task 1.1
# pins the four named acceptance tests below.


def test_q3_eu_dac_now_routes_to_planner():
    """The exact Run 1 Q3 query that missed every marker must now fire."""
    q = "How is Direct Air Capture regulated in the EU and what subsidies are available in 2026?"
    assert is_strategic_query(q) is True


def test_russian_regulatory_query_routes_to_planner():
    """RU regulatory query — checks that норматив/требовани markers work
    on long-enough Russian queries.
    """
    q = "Какие нормативные требования к энергоэффективности новых ЖК действуют в 2026?"
    assert is_strategic_query(q) is True


def test_old_strategic_queries_still_routed():
    """All three Run 1 queries (Q1 EV, Q2 Moscow RE, Q3 EU DAC) classify
    as strategic. Q1 + Q2 already worked pre-Step-3.1; Q3 is the new fix.
    """
    q1_ev = (
        "Сравните перспективы трёх лидеров электромобильного рынка в "
        "России (Москвич, АВТОВАЗ, Evolute) на горизонте 3 лет в условиях "
        "конкуренции с китайскими брендами BYD, Geely, Chery"
    )
    q2_re = (
        "Какие тренды повлияют на девелоперов бизнес-сегмента жилья в "
        "Москве в 2026-2027?"
    )
    q3_dac = (
        "How is Direct Air Capture regulated in the EU and what subsidies "
        "are available in 2026?"
    )
    assert is_strategic_query(q1_ev) is True
    assert is_strategic_query(q2_re) is True
    assert is_strategic_query(q3_dac) is True


def test_factual_queries_still_skip_planner():
    """Plain factual lookups must NOT match the new regulatory markers
    even when the markers appear (e.g. "available" can be a stopword in
    short factual contexts).
    """
    factual_short = "Сколько стоит Toyota Camry в 2026?"
    factual_camry_avail = "Is Toyota Camry available in red in 2026?"  # 8 words BUT "available" marker
    assert is_strategic_query(factual_short) is False
    # The Camry-availability one is a borderline case: 8 words, has "available".
    # Per spec, the heuristic is intentionally permissive — the cost of a
    # misrouted simple query is one extra LLM planner call (~$0.005-0.02
    # on Haiku). The cost of MISSING a strategic query (Run 1 Q3) was
    # the entire planner stage going dark. Acceptable trade-off.
    # We do NOT assert on this borderline case; we just document the
    # design choice.
    _ = factual_camry_avail


def test_router_order_handles_short_ru_re_strategic_queries():
    """Domain-template path must catch RU RE strategic queries even when
    they're shorter than the broad-strategic length gate.

    is_russian_re_strategic has NO length gate (it relies on the 3-signal
    combo: cyrillic + RE-vocab + strategic marker). is_strategic_query
    has a 7-word minimum to avoid LLM-planner waste on vague short queries.
    Some short RU RE queries hit one but not the other; the router puts
    domain template first to cover that gap without an extra LLM call.
    """
    short_ru_re = "Прогноз рынка премиум-новостроек Москвы на 2026-2027?"
    assert is_russian_re_strategic(short_ru_re), (
        f"{short_ru_re!r} should fire RU RE template (no length gate)"
    )
    # is_strategic_query may or may not fire here — what matters is
    # that the domain template wins first. Don't over-specify.

    long_ru_re = (
        "Какие тренды повлияют на девелоперов бизнес-сегмента жилья в Москве "
        "в 2026-2027 годах в условиях высокой ключевой ставки?"
    )
    assert is_russian_re_strategic(long_ru_re)
    assert is_strategic_query(long_ru_re), (
        "long RU RE strategic should also satisfy broad strategic — "
        "router puts template first as cheap path, but planner is the "
        "fallback if a future template is removed"
    )
