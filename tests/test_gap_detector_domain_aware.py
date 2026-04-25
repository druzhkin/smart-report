"""Tests for v4.5 Phase 3 Step 3.2 Task 2.2 — domain-aware gap detection.

After Task 2.1 introduced QueryDomain + per-domain registries, the
gap_detector now picks the right authoritative set per query. These
tests pin the three Run 1 acceptance cases brief Task 2.2 named.

Mock-only — no LLM, no network.
"""

from __future__ import annotations

import pytest

from smart_report.domain_detector import QueryDomain
from smart_report.gap_detector import detect_gaps
from smart_report.models import (
    AnalysisOutput,
    NumericFact,
    SourceRef,
    SubQuestion,
)


def _src(url: str, title: str) -> SourceRef:
    return SourceRef(url=url, title=title, confidence="primary")


def _analysis_with(*pairs: tuple[str, str]) -> AnalysisOutput:
    facts = [
        NumericFact(
            fact_id=NumericFact.make_id(f"v{i}", "m", "s"),
            value=f"v{i}",
            metric="m",
            subject="s",
            sources=[_src(u, t)],
        )
        for i, (u, t) in enumerate(pairs)
    ]
    return AnalysisOutput(all_numeric_facts=facts)


def _sq(sid: str, text: str, **kw) -> SubQuestion:
    return SubQuestion(id=sid, text=text, rationale="r", **kw)


# ---------------------------------------------------------------------------
# Spec acceptance cases from Task 2.2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_q1_ev_now_recognizes_autostat():
    """RU_AUTOMOTIVE query with 2 autostat.ru citations → no gap.
    Pre-Step-3.2 this would have flagged "moderate" (autostat not in
    RU_RE registry).
    """
    sq = _sq(
        "sq1",
        "Какова доля Москвича на электромобильном рынке России в 2026?",
        suggested_sources=["industry_report", "regulatory"],
    )
    analysis = _analysis_with(
        (
            "https://autostat.ru/news/55000/",
            "Доля Москвича на электромобильном рынке 2026",
        ),
        (
            "https://aebrus.ru/auto/electric-vehicles-statistics-2026",
            "Статистика рынка электромобилей АЕБ 2026 для Москвича",
        ),
    )
    gaps = await detect_gaps([sq], analysis, query_domain=QueryDomain.RU_AUTOMOTIVE)
    assert gaps == [], "AUTOMOTIVE registry should match autostat + aebrus → no gap"
    assert sq.evidence_status == "answered"
    assert sq.authoritative_source_count == 2


@pytest.mark.asyncio
async def test_q3_eu_dac_recognizes_europa_eu():
    """EU_REGULATORY query with 2+ europa.eu citations → no gap."""
    sq = _sq(
        "sq1",
        "What is the EU CRCF regulation framework for Direct Air Capture certification?",
        suggested_sources=["regulatory"],
    )
    analysis = _analysis_with(
        (
            "https://climate.ec.europa.eu/eu-action/eu-funding-climate-action/innovation-fund",
            "EU CRCF regulation framework Direct Air Capture certification 2026",
        ),
        (
            "https://eur-lex.europa.eu/eli/reg/2024/3012/oj",
            "EU Regulation 2024/3012 CRCF Direct Air Capture certification framework",
        ),
        (
            "https://carbongap.org/eu-carbon-removal-funding/",
            "EU CRCF carbon removal Direct Air Capture certification funding",
        ),
    )
    gaps = await detect_gaps([sq], analysis, query_domain=QueryDomain.EU_REGULATORY)
    assert gaps == [], "EU_REGULATORY registry should match europa.eu + carbongap → no gap"
    assert sq.evidence_status == "answered"
    assert sq.authoritative_source_count == 3


@pytest.mark.asyncio
async def test_ru_re_unaffected():
    """Existing RU_REAL_ESTATE behaviour must be unchanged — Q2-shape
    fixture continues to work as before Step 3.2.
    """
    sq = _sq(
        "sq1",
        "Какова доля ипотечных сделок жилья бизнес-класса Москвы 2024?",
        suggested_sources=["regulatory", "market_data"],
    )
    analysis = _analysis_with(
        (
            "https://rosstat.gov.ru/zhilyo-ipoteka-biznes-2024.pdf",
            "Доля ипотечных сделок жилья бизнес-класса Москва 2024",
        ),
        (
            "https://erzrf.ru/zhilyo-ipoteka-statistika-moskva-2024",
            "Статистика ипотечных сделок жилья бизнес-класса Москва 2024",
        ),
    )
    # Default query_domain = RU_REAL_ESTATE preserves Phase 2 behaviour
    gaps = await detect_gaps([sq], analysis)
    assert gaps == []
    assert sq.evidence_status == "answered"
    assert sq.authoritative_source_count == 2


# ---------------------------------------------------------------------------
# Cross-registry isolation — automotive sources don't count for RU_RE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autostat_does_not_count_for_ru_re_query():
    """The whole point of Step 3.2: autostat.ru is NOT a RU RE source,
    even though it's authoritative for AUTOMOTIVE. A real-estate
    sub-question that happens to retrieve autostat must NOT score
    it as authoritative.
    """
    sq = _sq(
        "sq1",
        "Какова цена жилья бизнес-класса в Москве 2026?",
    )
    analysis = _analysis_with(
        (
            "https://autostat.ru/foo",
            "Цена жилья бизнес-класса в Москве 2026 — спецотчёт",
        ),
    )
    gaps = await detect_gaps(
        [sq], analysis, query_domain=QueryDomain.RU_REAL_ESTATE
    )
    # autostat title matches sq tokens (жилья, бизнес-класса, Москве, 2026)
    # but autostat NOT in RU_RE registry → moderate gap, not "answered"
    assert len(gaps) == 1
    assert gaps[0].severity == "moderate"
    assert sq.authoritative_source_count == 0


# ---------------------------------------------------------------------------
# Domain-specific reason text appears in gap.reason
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderate_gap_reason_names_correct_domain_registry():
    """The gap reason should mention the right registry — analyst
    sees "Минпромторг, Автостат, АЕБ..." for an automotive gap, not
    the RU RE list.
    """
    sq = _sq("sq1", "Какие риски Москвича на электромобильном рынке 2026?")
    analysis = _analysis_with(
        (
            "https://random-blog.ru/moskvich-electromobile",
            "Риски Москвича на электромобильном рынке 2026",
        ),
    )
    gaps = await detect_gaps(
        [sq], analysis, query_domain=QueryDomain.RU_AUTOMOTIVE
    )
    assert len(gaps) == 1
    assert "Автостат" in gaps[0].reason or "АЕБ" in gaps[0].reason
    # Conversely, RU_RE-specific names should NOT appear
    assert "Росстат" not in gaps[0].reason
    assert "Минстрой" not in gaps[0].reason


@pytest.mark.asyncio
async def test_eu_regulatory_gap_reason_names_eu_institutions():
    sq = _sq(
        "sq1",
        "What is the EU CRCF regulation timeline for DAC certification?",
    )
    analysis = _analysis_with(
        (
            "https://medium.com/@blogger/eu-dac-overview",
            "EU CRCF regulation timeline DAC certification overview",
        ),
    )
    gaps = await detect_gaps(
        [sq], analysis, query_domain=QueryDomain.EU_REGULATORY
    )
    assert len(gaps) == 1
    # Reason should mention EU registry, not Russian one
    assert "europa.eu" in gaps[0].reason or "EU" in gaps[0].reason
    assert "Росстат" not in gaps[0].reason
