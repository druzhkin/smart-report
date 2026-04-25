"""Tests for the v4.5 Phase 2 Step 2.3 gap detector.

Mock-only — no LLM, no network. Live coverage runs through Step 2.4
acceptance fixture.
"""

from __future__ import annotations

import pytest

from smart_report.authoritative_sources import is_authoritative_url
from smart_report.gap_detector import (
    _match_sources_to_sub_question,
    _tokenize,
    detect_gaps,
    gap_count_by_severity,
)
from smart_report.models import (
    AnalysisOutput,
    EvidenceGap,
    NumericFact,
    QualitativeFact,
    SourceRef,
    SubQuestion,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _src(url: str, title: str = "") -> SourceRef:
    return SourceRef(url=url, title=title or url, confidence="primary")


def _numeric_fact(value: str, *sources: tuple[str, str] | str) -> NumericFact:
    """Each source is either (url, title) tuple or bare url string."""
    refs = []
    for s in sources:
        if isinstance(s, tuple):
            url, title = s
        else:
            url, title = s, ""
        refs.append(_src(url, title))
    return NumericFact(
        fact_id=NumericFact.make_id(value, "metric", "subj"),
        value=value,
        metric="metric",
        subject="subj",
        sources=refs,
    )


def _analysis_with_sources(*sources: tuple[str, str] | str) -> AnalysisOutput:
    """Build an AnalysisOutput where every (url, title) appears once on a numeric fact.

    Tests model production reality: RU RE sources usually have Latin URL
    slugs but Cyrillic titles. Match-by-tokens needs both to find the
    overlap with a Cyrillic sub_question.
    """
    facts = [_numeric_fact(f"v{i}", src) for i, src in enumerate(sources)]
    return AnalysisOutput(all_numeric_facts=facts)


def _sq(
    sid: str,
    text: str,
    *,
    suggested_sources: list[str] | None = None,
) -> SubQuestion:
    return SubQuestion(
        id=sid,
        text=text,
        rationale="r",
        suggested_sources=suggested_sources or [],
    )


# ---------------------------------------------------------------------------
# Severity-classification — the five spec acceptance cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critical_gap_when_no_sources_match_sub_question():
    """Sub-question with zero retrieved sources → severity='critical'."""
    sq = _sq("sq1", "Какие тренды влияют на спрос на жильё бизнес-класса в Москве?")
    # analysis carries sources on a totally unrelated topic — no token overlap
    analysis = _analysis_with_sources(
        ("https://github.com/langfuse/langfuse", "Langfuse observability platform overview"),
        ("https://www.helicone.ai/pricing", "Helicone pricing tiers"),
    )
    gaps = await detect_gaps([sq], analysis)
    assert len(gaps) == 1
    assert gaps[0].severity == "critical"
    assert gaps[0].sub_question_id == "sq1"
    assert sq.evidence_status == "unanswered"
    assert sq.bibliography_refs == []
    assert sq.authoritative_source_count == 0


@pytest.mark.asyncio
async def test_moderate_gap_when_sources_present_but_none_authoritative():
    """Sub-question matched some sources but none from the registry."""
    sq = _sq(
        "sq1",
        "Какие факторы определяют выбор девелопера бизнес-сегмента жилья?",
        suggested_sources=["industry_report"],
    )
    # Both sources overlap with sq tokens via Cyrillic titles, but
    # neither is on AUTHORITATIVE_RU_RE_DOMAINS.
    analysis = _analysis_with_sources(
        (
            "https://random-blog.ru/biznes-zhilyo-developer-2025",
            "Факторы выбора девелопера бизнес-сегмента жилья 2025",
        ),
        (
            "https://vc.ru/realty/biznes-zhilyo-tendencii-developera",
            "Тенденции выбора девелопера бизнес жилья",
        ),
    )
    gaps = await detect_gaps([sq], analysis)
    assert len(gaps) == 1
    assert gaps[0].severity == "moderate"
    assert sq.authoritative_source_count == 0
    assert len(sq.bibliography_refs) >= 1
    assert sq.evidence_status == "partial"


@pytest.mark.asyncio
async def test_minor_gap_when_one_authoritative_source():
    """Exactly one Rosstat source — meets recall but not the threshold of 2."""
    sq = _sq(
        "sq1",
        "Какова доля ипотечных сделок в сегменте жилья бизнес-класса Москвы 2024?",
        suggested_sources=["regulatory", "market_data"],
    )
    analysis = _analysis_with_sources(
        (
            "https://rosstat.gov.ru/storage/zhilyo-biznes-ipoteka-2024.pdf",
            "Доля ипотечных сделок в сегменте жилья бизнес-класса 2024",
        ),
        (
            "https://random-blog.ru/zhilyo-ipoteka-biznes-2024-obzor",
            "Обзор ипотечных сделок жилья бизнес 2024",
        ),
    )
    gaps = await detect_gaps([sq], analysis)
    assert len(gaps) == 1
    assert gaps[0].severity == "minor"
    assert sq.authoritative_source_count == 1
    assert sq.evidence_status == "partial"


@pytest.mark.asyncio
async def test_no_gap_when_two_or_more_authoritative_sources():
    """Two authoritative sources → meets the threshold; no gap emitted."""
    sq = _sq(
        "sq1",
        "Какова доля ипотечных сделок в сегменте жилья бизнес-класса Москвы 2024?",
    )
    analysis = _analysis_with_sources(
        (
            "https://rosstat.gov.ru/storage/zhilyo-biznes-ipoteka-2024.pdf",
            "Доля ипотечных сделок в сегменте жилья бизнес-класса Москва 2024",
        ),
        (
            "https://erzrf.ru/zhilyo-biznes-ipoteka-statistika-2024",
            "Статистика ипотечных сделок жилья бизнес-класс Москва 2024",
        ),
        (
            "https://random-blog.ru/biznes-zhilyo-2024",
            "Обзор бизнес жилья 2024",
        ),
    )
    gaps = await detect_gaps([sq], analysis)
    assert gaps == []
    assert sq.evidence_status == "answered"
    assert sq.authoritative_source_count == 2


@pytest.mark.asyncio
async def test_gap_severity_aggregation_sorts_critical_first():
    """Three sub_questions of mixed severity → all returned, critical first."""
    sq1 = _sq("sq1", "Какие риски рынка жилья при ставке ЦБ 16%?")  # critical
    sq2 = _sq("sq2", "Какие тренды цен на жильё бизнес-класса?")     # moderate
    sq3 = _sq("sq3", "Какова доля ипотеки 2024 в Москве?")           # minor

    analysis = _analysis_with_sources(
        # sq2 — moderate (matches "цены/жильё/бизнес" but no authoritative)
        (
            "https://realty-blog.ru/trendy-cen-zhilyo-biznes-klass-2024",
            "Цены жилья бизнес-класса 2024 — обзор",
        ),
        # sq3 — minor (one Rosstat) — title mentions "ипотека Москва доли"
        (
            "https://rosstat.gov.ru/ipoteka-doli-moskva-2024.pdf",
            "Ипотека доля Москва 2024 квартир",
        ),
        # sq1 — no sources match (CBR rate query, no overlap with these URLs/titles)
    )
    gaps = await detect_gaps([sq1, sq2, sq3], analysis)
    assert len(gaps) == 3
    assert [g.severity for g in gaps] == ["critical", "moderate", "minor"]
    assert [g.sub_question_id for g in gaps] == ["sq1", "sq2", "sq3"]


# ---------------------------------------------------------------------------
# Aggregation helper
# ---------------------------------------------------------------------------


def test_gap_count_by_severity_includes_all_keys():
    gaps = [
        EvidenceGap(sub_question_id="a", sub_question_text="x", severity="critical", reason="r"),
        EvidenceGap(sub_question_id="b", sub_question_text="x", severity="critical", reason="r"),
        EvidenceGap(sub_question_id="c", sub_question_text="x", severity="moderate", reason="r"),
    ]
    counts = gap_count_by_severity(gaps)
    assert counts == {"critical": 2, "moderate": 1, "minor": 0}


def test_gap_count_by_severity_empty():
    assert gap_count_by_severity([]) == {"critical": 0, "moderate": 0, "minor": 0}


# ---------------------------------------------------------------------------
# Edge cases — empty inputs, opaque URLs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_sub_questions_returns_empty_list():
    """Step 2.1 RU RE template path doesn't populate SubQuestion list —
    detect_gaps must short-circuit cleanly in that case.
    """
    analysis = _analysis_with_sources(("https://rosstat.gov.ru/x", "Заголовок"))
    gaps = await detect_gaps([], analysis)
    assert gaps == []


@pytest.mark.asyncio
async def test_opaque_urls_ignored():
    """Sources with URLs like 'opaque:perplexity_dr_1' are tool sentinels,
    not real sources; they must not count toward bibliography_refs.
    """
    sq = _sq("sq1", "Какие тренды на рынке жилья бизнес-класса Москвы?")
    fact = NumericFact(
        fact_id=NumericFact.make_id("v1", "m", "s"),
        value="v1",
        metric="m",
        subject="s",
        sources=[
            _src("opaque:perplexity_dr_1", "Тренды рынка жилья бизнес-класса Москвы"),
            _src(
                "https://erzrf.ru/biznes-zhilyo-trendy-moskva-2024",
                "Тренды рынка жилья бизнес-класса Москвы 2024",
            ),
        ],
    )
    analysis = AnalysisOutput(all_numeric_facts=[fact])
    gaps = await detect_gaps([sq], analysis)
    # Only the erzrf source should count; one authoritative is "minor"
    assert len(gaps) == 1
    assert gaps[0].severity == "minor"
    assert all(not url.startswith("opaque:") for url in sq.bibliography_refs)


@pytest.mark.asyncio
async def test_authoritative_threshold_is_configurable():
    """Step 2.3 caller can raise the bar (e.g. 3 sources for high-stakes)."""
    sq = _sq("sq1", "Какова доля ипотеки в сегменте жилья бизнес-класса Москвы 2024?")
    analysis = _analysis_with_sources(
        (
            "https://rosstat.gov.ru/zhilyo-ipoteka-biznes-moskva-2024.pdf",
            "Доля ипотечных сделок жилья бизнес-класс Москва 2024",
        ),
        (
            "https://erzrf.ru/biznes-zhilyo-ipoteka-statistika-moskva-2024",
            "Статистика ипотечных сделок жилья бизнес Москва 2024",
        ),
    )
    # Default threshold 2 → no gap
    gaps_at_2 = await detect_gaps([sq], analysis, authoritative_threshold=2)
    assert gaps_at_2 == []
    # Reset state for next call (detect_gaps mutates sq in place)
    sq2 = _sq("sq1", "Какова доля ипотеки в сегменте жилья бизнес-класса Москвы 2024?")
    gaps_at_3 = await detect_gaps([sq2], analysis, authoritative_threshold=3)
    assert len(gaps_at_3) == 1
    assert gaps_at_3[0].severity == "minor"  # 2 of 3 is still close


# ---------------------------------------------------------------------------
# Tokenizer + matcher — unit-level guards
# ---------------------------------------------------------------------------


def test_tokenizer_strips_stopwords_and_short_tokens():
    tokens = _tokenize("Какие тренды влияют на бизнес-сегмент жилья в Москве?")
    # "какие", "тренды", "влияют", "на", "в" are stopwords; should leave
    # "бизнес-сегмент", "жилья", "москве" or constituent tokens >=3 chars
    assert "москве" in tokens
    assert "жилья" in tokens
    assert "какие" not in tokens
    assert "на" not in tokens
    assert "в" not in tokens


def test_matcher_requires_at_least_two_overlapping_tokens():
    """A single common token is too noisy to count as a match.

    Realistic case: source title carries the Cyrillic terms (URL slugs
    are Latin transliteration, but title is Russian).
    """
    sq = _sq("sq1", "девелопер премиум сегмент жильё Москва")
    sources = [
        # 2-token overlap (девелопер + Москва via Cyrillic title) → match
        {
            "url": "https://example.ru/developer-moskva-2024",
            "title": "Развитие девелопера премиум-класса в Москве",
        },
        # 1-token overlap (только москва via title) → no match
        {
            "url": "https://example.ru/moskva-news",
            "title": "Москва: новости",
        },
    ]
    matched = _match_sources_to_sub_question(sq, sources)
    assert "https://example.ru/developer-moskva-2024" in matched
    assert "https://example.ru/moskva-news" not in matched


def test_matcher_uses_suggested_sources_hint():
    """Suggested-source tokens (e.g. 'regulatory', 'market_data') feed
    into the overlap check too, so a sub-question with an unmatched text
    can still pull in domain hints.
    """
    sq = _sq(
        "sq1",
        "Какие новые правила влияют на сегмент?",
        suggested_sources=["regulatory", "minstroy"],
    )
    sources = [
        {"url": "https://minstroyrf.gov.ru/regulatory-update-2025", "title": "пресс"},
    ]
    matched = _match_sources_to_sub_question(sq, sources)
    assert matched == ["https://minstroyrf.gov.ru/regulatory-update-2025"]


# ---------------------------------------------------------------------------
# Sentinel separation — gap reasoning must stay Cyrillic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gap_reason_text_contains_no_uppercase_latin_sentinels():
    """Same anti-lint-retry discipline as Step 1.2: gap.reason text will
    eventually be surfaced in confidence_note (Step 2.3 integration), so
    no Latin-script sentinels (e.g. EVIDENCE_GAP, CRITICAL_FAILURE)
    should leak into the visible string.
    """
    import re as _re

    sq = _sq("sq1", "Какие риски рынка?")
    analysis = _analysis_with_sources()  # empty
    gaps = await detect_gaps([sq], analysis)
    assert len(gaps) == 1
    forbidden = _re.findall(r"[A-Z]{4,}", gaps[0].reason)
    assert not forbidden, (
        f"gap.reason text leaks uppercase Latin tokens {forbidden!r}; "
        f"these would trip the language linter once the reason is "
        f"prefixed onto confidence_note in the orchestrator stage."
    )
