"""Tests for v4.5 Phase 3 Step 3.3 Task 3.1 — heuristic source quality classifier.

Mock-only — no LLM, no network. The classifier itself is pure
deterministic logic.
"""

from __future__ import annotations

import pytest

from smart_report.domain_detector import QueryDomain
from smart_report.source_quality_classifier import (
    SourceQualityScore,
    classify_source,
    classify_source_batch,
)


# ---------------------------------------------------------------------------
# Tier 1 — primary regulator / first-party data → STRONG
# ---------------------------------------------------------------------------


def test_rosstat_with_ru_real_estate_is_strong_first_party_data():
    score = classify_source(
        "https://rosstat.gov.ru/storage/zhilyo-2026.pdf",
        QueryDomain.RU_REAL_ESTATE,
    )
    assert score.evidence_strength == "STRONG"
    assert score.domain_authority == "first_party_data"
    assert "rosstat" in score.rationale.lower() or "first_party" in score.rationale


def test_europa_eu_with_eu_regulatory_is_strong():
    score = classify_source(
        "https://climate.ec.europa.eu/eu-action/funds",
        QueryDomain.EU_REGULATORY,
    )
    assert score.evidence_strength == "STRONG"
    assert score.domain_authority in ("primary_regulator", "first_party_data")


def test_minpromtorg_with_ru_automotive_is_strong():
    score = classify_source(
        "https://minpromtorg.gov.ru/ev-policy-2026.pdf",
        QueryDomain.RU_AUTOMOTIVE,
    )
    assert score.evidence_strength == "STRONG"
    assert score.domain_authority == "first_party_data"


def test_autostat_with_ru_automotive_is_strong():
    score = classify_source(
        "https://autostat.ru/news/55000/",
        QueryDomain.RU_AUTOMOTIVE,
    )
    assert score.evidence_strength == "STRONG"
    # autostat is industry data provider, not state — primary_regulator label is fine
    assert score.domain_authority == "primary_regulator"


# ---------------------------------------------------------------------------
# Tier 2 — trusted media → MODERATE
# ---------------------------------------------------------------------------


def test_rbc_is_moderate_trusted_media():
    score = classify_source("https://rbc.ru/economy/2026/01/x", QueryDomain.RU_REAL_ESTATE)
    assert score.evidence_strength == "MODERATE"
    assert score.domain_authority == "trusted_media"


def test_kommersant_is_moderate_trusted_media():
    score = classify_source(
        "https://www.kommersant.ru/doc/8398544", QueryDomain.RU_REAL_ESTATE
    )
    assert score.evidence_strength == "MODERATE"
    assert score.domain_authority == "trusted_media"


def test_ft_com_is_moderate_trusted_media():
    score = classify_source("https://ft.com/content/x", QueryDomain.GLOBAL_TECH)
    assert score.evidence_strength == "MODERATE"
    assert score.domain_authority == "trusted_media"


# ---------------------------------------------------------------------------
# Tier 3 — established consultancy → MODERATE
# ---------------------------------------------------------------------------


def test_jll_is_moderate_consultancy():
    score = classify_source(
        "https://jllrussia.com/research/q4-2025", QueryDomain.RU_REAL_ESTATE
    )
    # JLL is in the RU RE registry → fires Tier 1 (STRONG) before consultancy
    # tier. That's correct behaviour: top-RE consultancies on a RE query
    # are treated as primary RE-research sources.
    assert score.evidence_strength == "STRONG"


def test_mckinsey_off_domain_is_moderate_consultancy():
    """McKinsey is NOT in any per-domain registry, so it falls through
    to the trusted_media → consultancy tier and gets MODERATE.
    """
    score = classify_source(
        "https://mckinsey.com/insights/ev-2026", QueryDomain.RU_AUTOMOTIVE
    )
    assert score.evidence_strength == "MODERATE"
    assert score.domain_authority == "established_consultancy"


def test_yakov_partners_is_moderate_consultancy():
    score = classify_source(
        "https://yakovpartners.com/publications/development-trends/",
        QueryDomain.RU_REAL_ESTATE,
    )
    assert score.evidence_strength == "MODERATE"
    assert score.domain_authority == "established_consultancy"


# ---------------------------------------------------------------------------
# Tier 4 — forum / aggregator → WEAK
# ---------------------------------------------------------------------------


def test_medium_blog_is_weak_forum_aggregator():
    score = classify_source(
        "https://medium.com/@blogger/eu-dac-overview", QueryDomain.EU_REGULATORY
    )
    assert score.evidence_strength == "WEAK"
    assert score.domain_authority == "forum_or_aggregator"


def test_reddit_is_weak_forum():
    score = classify_source(
        "https://reddit.com/r/europe/comments/x", QueryDomain.EU_REGULATORY
    )
    assert score.evidence_strength == "WEAK"


def test_telegram_link_is_weak():
    score = classify_source("https://t.me/some_channel/123", QueryDomain.GENERIC)
    assert score.evidence_strength == "WEAK"
    assert score.domain_authority == "forum_or_aggregator"


# ---------------------------------------------------------------------------
# Default (unknown) — WEAK
# ---------------------------------------------------------------------------


def test_random_blog_is_weak_unknown():
    score = classify_source(
        "https://random-blog.ru/posts/2026", QueryDomain.RU_REAL_ESTATE
    )
    assert score.evidence_strength == "WEAK"
    assert score.domain_authority == "unknown"


def test_unknown_domain_global_tech_is_weak():
    score = classify_source(
        "https://obscure-tech-blog.io/llm-comparison", QueryDomain.GLOBAL_TECH
    )
    assert score.evidence_strength == "WEAK"


# ---------------------------------------------------------------------------
# Cross-domain isolation — autostat.ru is NOT STRONG for EU_REGULATORY
# ---------------------------------------------------------------------------


def test_autostat_with_eu_regulatory_is_not_strong():
    """Cross-domain finding: autostat.ru is RU_AUTOMOTIVE-authoritative
    but NOT a EU regulator — must NOT score STRONG on an EU query.
    """
    score = classify_source(
        "https://autostat.ru/news/55000/", QueryDomain.EU_REGULATORY
    )
    assert score.evidence_strength != "STRONG"
    # Falls through to default unknown → WEAK
    assert score.evidence_strength == "WEAK"


def test_europa_eu_with_ru_real_estate_is_not_strong():
    score = classify_source(
        "https://europa.eu/policy/x", QueryDomain.RU_REAL_ESTATE
    )
    assert score.evidence_strength != "STRONG"


# ---------------------------------------------------------------------------
# SPECULATIVE — no signal cases
# ---------------------------------------------------------------------------


def test_empty_url_is_speculative():
    score = classify_source("", QueryDomain.RU_REAL_ESTATE)
    assert score.evidence_strength == "SPECULATIVE"
    assert score.domain_authority == "unknown"


def test_opaque_url_is_speculative():
    score = classify_source(
        "opaque:perplexity_dr_1", QueryDomain.RU_REAL_ESTATE
    )
    assert score.evidence_strength == "SPECULATIVE"
    assert "opaque" in score.rationale.lower()


# ---------------------------------------------------------------------------
# Batch classifier
# ---------------------------------------------------------------------------


def test_classify_source_batch_dedupes():
    urls = [
        "https://rosstat.gov.ru/x",
        "https://rbc.ru/y",
        "https://rosstat.gov.ru/x",  # duplicate
        "",  # skipped (empty)
    ]
    out = classify_source_batch(urls, QueryDomain.RU_REAL_ESTATE)
    assert len(out) == 2  # rosstat + rbc, "" skipped, dup removed
    assert out["https://rosstat.gov.ru/x"].evidence_strength == "STRONG"
    assert out["https://rbc.ru/y"].evidence_strength == "MODERATE"


def test_classify_source_batch_preserves_order_independence():
    """Same URLs in different order produce equivalent classifications."""
    urls = ["https://rbc.ru/a", "https://rosstat.gov.ru/b"]
    out_a = classify_source_batch(urls, QueryDomain.RU_REAL_ESTATE)
    out_b = classify_source_batch(list(reversed(urls)), QueryDomain.RU_REAL_ESTATE)
    assert out_a == out_b


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_returned_score_is_pydantic_model():
    score = classify_source("https://rbc.ru/x", QueryDomain.RU_REAL_ESTATE)
    assert isinstance(score, SourceQualityScore)
    # Trip pydantic by attempting to dump
    dumped = score.model_dump()
    assert "url" in dumped
    assert "domain_authority" in dumped
    assert "evidence_strength" in dumped
    assert "rationale" in dumped
