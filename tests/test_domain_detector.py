"""Tests for v4.5 Phase 3 Step 3.2 — heuristic query-domain detector
plus the multi-domain authoritative registry built on top of it.

Mock-only — no LLM, no network.
"""

from __future__ import annotations

import pytest

from smart_report.authoritative_sources import (
    AUTHORITATIVE_DOMAINS_BY_QUERY_DOMAIN,
    AUTHORITATIVE_EU_REGULATORY_DOMAINS,
    AUTHORITATIVE_RU_AUTOMOTIVE_DOMAINS,
    AUTHORITATIVE_RU_RE_DOMAINS,
    get_authoritative_domains,
    is_authoritative_url,
    is_authoritative_url_for_domain,
)
from smart_report.domain_detector import QueryDomain, detect_query_domain


# ---------------------------------------------------------------------------
# QueryDomain detection — per-domain positive examples
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Какие тренды повлияют на девелоперов бизнес-сегмента жилья в Москве в 2026-2027?",
        "Прогноз цен новостроек премиум-класса Москвы 2026",
        "Что определяет успех застройщика элитного жилья на горизонте 3 лет?",
    ],
)
def test_detects_ru_real_estate(query: str):
    assert detect_query_domain(query) == QueryDomain.RU_REAL_ESTATE


@pytest.mark.parametrize(
    "query",
    [
        "Сравните перспективы российских производителей электромобилей Москвич, АВТОВАЗ, Evolute против BYD, Geely, Chery",
        "Как локализация автопрома повлияет на конкуренцию с китайскими брендами в 2026?",
        "Какие риски для Lada у Минпромторга в условиях электромобильного перехода?",
    ],
)
def test_detects_ru_automotive(query: str):
    assert detect_query_domain(query) == QueryDomain.RU_AUTOMOTIVE


@pytest.mark.parametrize(
    "query",
    [
        "Какие ниши открываются для российских SaaS стартапов после ухода western vendors?",
        "Перспективы российского финтех-сектора на горизонте 2 лет в условиях санкций",
    ],
)
def test_detects_ru_tech_saas(query: str):
    assert detect_query_domain(query) == QueryDomain.RU_TECH_SAAS


@pytest.mark.parametrize(
    "query",
    [
        "How is Direct Air Capture regulated in the EU and what subsidies are available in 2026?",
        "European Commission directive on AI act enforcement timeline 2026",
        "How does the EU CRCF framework for carbon removal certification work?",
    ],
)
def test_detects_eu_regulatory(query: str):
    assert detect_query_domain(query) == QueryDomain.EU_REGULATORY


@pytest.mark.parametrize(
    "query",
    [
        "Compare LLM observability platforms (Langfuse, LangSmith, Helicone) for enterprise scale",
        "What are the pricing models for vector database SaaS platforms at enterprise scale?",
        "Open source machine learning libraries comparison for production deployments",
    ],
)
def test_detects_global_tech(query: str):
    assert detect_query_domain(query) == QueryDomain.GLOBAL_TECH


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_query_is_generic():
    assert detect_query_domain("") == QueryDomain.GENERIC
    assert detect_query_domain("   ") == QueryDomain.GENERIC


def test_completely_off_topic_query_is_generic():
    """No marker hits → GENERIC fallback."""
    assert detect_query_domain("Какой рецепт у бабушкиного борща?") == QueryDomain.GENERIC
    assert detect_query_domain("Best hiking trails in Patagonia") == QueryDomain.GENERIC


def test_ru_re_wins_when_both_re_and_strategic_markers_fire():
    """RU RE is the flagship domain. If a query mentions RE keywords
    plus also generic strategic markers, RU_REAL_ESTATE must win
    over RU_AUTOMOTIVE / RU_TECH_SAAS / others.
    """
    q = "Какие риски для девелопера бизнес-класса при переходе на электромобили в служебном автопарке?"
    # Contains "девелопер", "бизнес-класс" (RE) AND "электромобил", "автопарк" (auto)
    # RU_REAL_ESTATE is checked first → wins
    assert detect_query_domain(q) == QueryDomain.RU_REAL_ESTATE


def test_english_query_with_no_eu_marker_falls_through_to_generic():
    """English query without EU/regulation/tech markers → GENERIC,
    NOT one of the RU domains (which gate on cyrillic).
    """
    q = "What is the best strategy for selecting commercial real estate in Moscow?"
    # Has "commercial real estate" + "Moscow" but no EU/tech markers
    # AND no Cyrillic → can't be RU_REAL_ESTATE
    assert detect_query_domain(q) == QueryDomain.GENERIC


# ---------------------------------------------------------------------------
# get_authoritative_domains — registry coverage
# ---------------------------------------------------------------------------


def test_each_registered_domain_has_non_empty_set_except_generic():
    for qd in QueryDomain:
        registry = get_authoritative_domains(qd)
        if qd == QueryDomain.GENERIC:
            assert registry == frozenset(), "GENERIC must be empty by design"
        else:
            assert len(registry) >= 5, (
                f"{qd.value} registry has only {len(registry)} entries — "
                f"need at least 5 for adequacy threshold of 2 to be meaningful"
            )


def test_ru_re_registry_unchanged_by_step_3_2():
    """Backwards compat: existing RU RE registry contents must not have
    been accidentally edited during the Step 3.2 split.
    """
    assert (
        get_authoritative_domains(QueryDomain.RU_REAL_ESTATE)
        == AUTHORITATIVE_RU_RE_DOMAINS
    )


def test_eu_regulatory_registry_matches_step_3_1_set():
    assert (
        get_authoritative_domains(QueryDomain.EU_REGULATORY)
        == AUTHORITATIVE_EU_REGULATORY_DOMAINS
    )


def test_ru_automotive_registry_includes_run_1_finding_3_domains():
    """Run 1 Q1 EV finding called out autostat / aebrus / minpromtorg
    as missing — Step 3.2 must add them.
    """
    auto = get_authoritative_domains(QueryDomain.RU_AUTOMOTIVE)
    assert "autostat.ru" in auto
    assert "aebrus.ru" in auto
    assert "minpromtorg.gov.ru" in auto


# ---------------------------------------------------------------------------
# is_authoritative_url_for_domain — domain-aware lookup
# ---------------------------------------------------------------------------


def test_domain_aware_lookup_uses_per_domain_registry():
    """autostat.ru is authoritative for RU_AUTOMOTIVE, NOT for RU_REAL_ESTATE
    (it's auto-industry data, not real estate).
    """
    assert is_authoritative_url_for_domain(
        "https://autostat.ru/news/55000/", QueryDomain.RU_AUTOMOTIVE
    ) is True
    assert is_authoritative_url_for_domain(
        "https://autostat.ru/news/55000/", QueryDomain.RU_REAL_ESTATE
    ) is False


def test_domain_aware_lookup_does_not_cross_match():
    """europa.eu is EU_REGULATORY only — must NOT count as authoritative
    for an unrelated RU_AUTOMOTIVE query.
    """
    assert is_authoritative_url_for_domain(
        "https://europa.eu/policy/x", QueryDomain.EU_REGULATORY
    ) is True
    assert is_authoritative_url_for_domain(
        "https://europa.eu/policy/x", QueryDomain.RU_AUTOMOTIVE
    ) is False


def test_domain_aware_lookup_falls_back_to_global_for_generic():
    """GENERIC has no per-domain registry — must fall back to the
    global union (defence in depth on cross-domain queries).
    """
    assert is_authoritative_url_for_domain(
        "https://rosstat.gov.ru/foo", QueryDomain.GENERIC
    ) is True
    assert is_authoritative_url_for_domain(
        "https://europa.eu/foo", QueryDomain.GENERIC
    ) is True
    assert is_authoritative_url_for_domain(
        "https://random-blog.ru/foo", QueryDomain.GENERIC
    ) is False


def test_legacy_is_authoritative_url_still_works():
    """The pre-Step-3.2 single-set check remains as a safety net for
    callers that haven't been migrated to the domain-aware variant.
    """
    assert is_authoritative_url("https://rosstat.gov.ru/foo") is True
    assert is_authoritative_url("https://europa.eu/policy") is True
    assert is_authoritative_url("https://random-blog.ru") is False
