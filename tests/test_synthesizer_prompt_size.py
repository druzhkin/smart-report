"""Regression test for the v4.5 synthesizer prompt-size double-injection bug.

Live Acceptance Tests Run 1 (apr 2026) discovered that
``synthesizer._build_user_message`` was carrying ``high_relevance_facts``
TWICE: once inside the full ``analysis.model_dump()`` blob, and again
in the dedicated ``_build_facts_section`` block. On a realistic
4-amenities-fixture run this inflated the prompt to ~723k chars
(~241k tokens), overflowing Haiku 4.5's 200k context window and
forcing the pipeline onto Sonnet/Opus only.

The fix excludes the duplicate fact lists from the analyzer dump so
``_build_facts_section`` becomes the single source of truth. This
test pins the post-fix size budget so a future change that re-adds
the duplication cannot land silently.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pytest

from smart_report.io import load_prompt
from smart_report.models import (
    AnalysisOutput,
    Conflict,
    ConsensusClaim,
    Gap,
    NumericFact,
    QualitativeFact,
    ResearchPrompt,
    SourceRef,
    UploadedMarkdown,
    V4Session,
)
from smart_report.synthesizer import _build_user_message


# ---------------------------------------------------------------------------
# Char-budget thresholds
# ---------------------------------------------------------------------------
# Anthropic models on OpenRouter return HTTP 400 with a precise
# "200000 tokens, you requested X" body. Mixed Russian/English content
# tokenizes at roughly 3 chars/token on Anthropic's tokenizer (Cyrillic
# is denser per token than English ASCII). 200k tokens × 3 chars/token =
# 600k chars cap; we add a safety margin and cap at 550k chars.

HAIKU_CONTEXT_CHAR_BUDGET = 550_000  # ~183k tokens, leaves room for
                                     # max_tokens=32000 output and slack

# Pre-fix baseline (recorded for reference): ~723k chars on this fixture.
# Post-fix expected: ~310k chars.

PRE_FIX_BASELINE_FOR_REFERENCE = 720_000


# ---------------------------------------------------------------------------
# Synthetic session builder — mirrors realistic 4-fixture shape
# ---------------------------------------------------------------------------


def _make_source_ref(idx: int) -> SourceRef:
    return SourceRef(
        url=f"https://example-source-{idx}.ru/page-{idx}",
        title=f"Источник {idx}: статистика рынка недвижимости",
        publisher="Тестовое издание",
        date="2025-06-15",
        confidence="primary",
    )


def _make_numeric_fact(idx: int) -> NumericFact:
    return NumericFact(
        fact_id=NumericFact.make_id(f"{idx}%", "доля рынка", f"сегмент {idx}"),
        value=f"{idx % 100}%",
        metric="доля рынка",
        subject=f"сегмент бизнес-класса Москвы, проект {idx}",
        timeframe="2025 H1",
        sources=[_make_source_ref(idx)],
        relevance_to_question="high" if idx < 200 else "medium",
        fact_category="share",
    )


def _make_qualitative_fact(idx: int) -> QualitativeFact:
    return QualitativeFact(
        fact_id=QualitativeFact.make_id(f"тезис {idx}", f"субъект {idx}"),
        statement=(
            f"Тезис {idx}: эксперты отмечают изменение поведения покупателей "
            f"в сегменте бизнес-класса под влиянием регуляторных факторов."
        ),
        subject=f"девелопер {idx}",
        sources=[_make_source_ref(idx)],
        relevance_to_question="medium",
        fact_category="trend",
    )


def _make_long_source_report(idx: int, target_chars: int = 50_000) -> UploadedMarkdown:
    """Synthesize a markdown blob of approximately *target_chars* in size."""
    paragraph = (
        f"### Раздел {idx}.x — анализ сегмента\n\n"
        "Доля бизнес-класса в Москве в первом полугодии 2025 года составила "
        "47% от первичного рынка по данным ЕРЗ. Knight Frank и JLL отмечают "
        "снижение ипотечных сделок до исторического минимума 16%. По оценке "
        "Метриум, средняя цена м² выросла на 12% год к году. Нюансы по "
        "конкретным проектам и амениtis раскрыты ниже.\n\n"
    )
    repeats = max(1, target_chars // len(paragraph))
    content = (
        f"# Test fixture report {idx}\n\n"
        + (paragraph * repeats)
    )
    return UploadedMarkdown(
        filename=f"test_report_{idx}.md",
        content=content,
        detected_tool="other",
        word_count=len(content.split()),
    )


def _build_realistic_session(
    *,
    n_source_reports: int = 4,
    n_numeric_facts: int = 339,
    n_qualitative_facts: int = 124,
    n_high_relevance: int = 330,
) -> V4Session:
    """Build a session whose shape mirrors Live Run 1 Test 1 measurements.

    The default counts come from the actual Run 1 checkpoint (4 amenities
    fixtures + intake on Haiku 4.5): 339 numeric, 124 qualitative, 330
    high-relevance. Reproducing those counts gives the test the same
    prompt-inflation pressure as the production scenario.
    """
    sources = [_make_source_ref(i) for i in range(20)]
    consensus = [
        ConsensusClaim(
            claim=f"Тезис консенсуса {i}: фактор X влияет на сегмент Y.",
            supporting_sources=[s.url for s in sources[:5]],
            confidence="high",
        )
        for i in range(5)
    ]
    conflicts = [
        Conflict(
            topic=f"Конфликт {i}: оценка размера рынка",
            source_a="perplexity_dr_1",
            claim_a="55%",
            source_b="openai_dr_1",
            claim_b="68%",
            resolution_hint="cross-check ERZ",
            importance="material",
        )
        for i in range(4)
    ]
    gaps = [
        Gap(
            topic=f"Gap {i}: данные по subтеме",
            why_critical="закрывает ключевую неопределённость",
            what_to_find="конкретные числа от первичного источника",
            candidate_sources=["erzrf.ru", "rosstat.gov.ru"],
        )
        for i in range(6)
    ]
    numeric_facts = [_make_numeric_fact(i) for i in range(n_numeric_facts)]
    qualitative_facts = [_make_qualitative_fact(i) for i in range(n_qualitative_facts)]

    analysis = AnalysisOutput(
        consensus=consensus,
        conflicts=conflicts,
        gaps=gaps,
        all_numeric_facts=numeric_facts,
        all_qualitative_facts=qualitative_facts,
        high_relevance_facts=numeric_facts[:n_high_relevance],
        fact_coverage_target=200,
    )

    return V4Session(
        session_id="prompt-size-regression",
        raw_question="Какие факторы повлияют на спрос на жильё бизнес-класса в Москве?",
        research_prompt=ResearchPrompt(
            full_prompt="Подробный research prompt на ~5000 символов: " + ("анализ " * 600),
            reasoning="r",
            expected_structure=["Section A", "Section B"],
            key_entities=["PIK", "Самолёт", "Эталон"],
            tips_for_search="ЕРЗ + Минстрой",
        ),
        source_reports=[_make_long_source_report(i) for i in range(n_source_reports)],
        analysis=analysis,
        status="analyzed",
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_synthesizer_prompt_fits_haiku_context_window():
    """Combined system + user prompt must stay under the Haiku 4.5 budget.

    Anchor for the regression: this exact assertion would have failed
    pre-fix on the same synthetic session (~720k chars vs 550k cap).
    """
    session = _build_realistic_session()
    user = _build_user_message(session)
    system = load_prompt("synthesizer") or ""
    total_chars = len(system) + len(user)

    assert total_chars <= HAIKU_CONTEXT_CHAR_BUDGET, (
        f"Synthesizer prompt is {total_chars:,} chars — exceeds the "
        f"{HAIKU_CONTEXT_CHAR_BUDGET:,}-char budget that targets Haiku 4.5's "
        f"200k-token context. The double-injection bug (Finding 1 from "
        f"Live Acceptance Run 1) has likely returned: check that "
        f"_build_user_message excludes all_numeric_facts and "
        f"high_relevance_facts from analysis.model_dump()."
    )


def test_facts_section_is_the_single_source_of_truth_for_high_relevance_facts():
    """The dedicated facts section must carry the high-relevance inventory;
    the analysis dump must NOT also carry it.

    This is a structural assertion — independent of size — that locks in
    the design intent so a refactor cannot accidentally re-introduce the
    duplication while staying under the size cap.
    """
    session = _build_realistic_session(n_high_relevance=50)
    user = _build_user_message(session)

    # Pick a fact_id from the high-relevance set and count its occurrences.
    fact_ids = [f.fact_id for f in session.analysis.high_relevance_facts[:10]]
    assert fact_ids, "test fixture must include at least 10 high-relevance facts"

    for fid in fact_ids:
        occurrences = user.count(fid)
        assert occurrences == 1, (
            f"high-relevance fact_id {fid!r} appears {occurrences}× in "
            f"the synthesizer prompt — should be exactly 1 (only inside "
            f"_build_facts_section). If >1, the analysis dump is "
            f"re-carrying the same fact list. If 0, _build_facts_section "
            f"is no longer firing."
        )


def test_analysis_consensus_and_conflicts_still_present_in_dump():
    """Sanity check: excluding fact lists must NOT also strip the
    structural fields (consensus, conflicts, gaps, followup_prompt) that
    the synthesizer needs to drive the conflicts_section / gaps_section.
    """
    session = _build_realistic_session()
    user = _build_user_message(session)

    # Each consensus / conflict / gap statement should still be in the prompt
    for c in session.analysis.consensus[:3]:
        assert c.claim in user, f"consensus claim missing from prompt: {c.claim[:50]!r}"
    for cf in session.analysis.conflicts[:2]:
        assert cf.topic in user, f"conflict topic missing from prompt: {cf.topic!r}"
    for g in session.analysis.gaps[:2]:
        assert g.topic in user, f"gap topic missing from prompt: {g.topic!r}"


def test_facts_section_still_caps_high_relevance_at_200():
    """Don't lose the 200-fact cap from _build_facts_section while
    fixing the duplication. The cap is what made even the post-fix
    prompt size predictable."""
    from smart_report.synthesizer import _build_facts_section

    session = _build_realistic_session(n_high_relevance=500)
    section = _build_facts_section(session.analysis)
    # The first 200 high-relevance fact_ids should appear; ones at
    # positions 200..499 should NOT.
    first_200_ids = [f.fact_id for f in session.analysis.high_relevance_facts[:200]]
    beyond_200_ids = [f.fact_id for f in session.analysis.high_relevance_facts[200:300]]

    for fid in first_200_ids[:5]:
        assert fid in section, f"fact {fid} from the first 200 should be in the section"
    for fid in beyond_200_ids[:5]:
        assert fid not in section, (
            f"fact {fid} beyond the 200-cap should NOT be in the section"
        )
