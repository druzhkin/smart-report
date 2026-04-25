"""Tests for v4.5 Phase 1 Step 1.1 — evidence-grade tag injection.

Covers:
  * Tag-parsing helper (``count_evidence_grades``)
  * Variance check (``has_grade_variance``)
  * Distribution across a fully-built ``FinalReport``
  * Synthesizer prompt regression: all four grade names must remain
    documented in the system prompt
  * Language-lint regression: grade tags must NOT be flagged as anglicisms
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from smart_report.evidence_grades import (
    EVIDENCE_GRADES,
    count_evidence_grades,
    evidence_grade_distribution,
    has_grade_variance,
    total_grades,
)
from smart_report.i18n.language_lint import lint_output_language
from smart_report.models import (
    CalloutBlock,
    ExecutiveSummaryV4,
    FinalReport,
    KeyNumberHighlight,
    QAItem,
)


# ---------------------------------------------------------------------------
# count_evidence_grades
# ---------------------------------------------------------------------------


def test_count_evidence_grades_all_zero_for_untagged_text():
    text = "Просто абзац без тегов и со ссылкой [REF:https://example.com/report]."
    counts = count_evidence_grades(text)
    assert counts == {grade: 0 for grade in EVIDENCE_GRADES}


def test_count_evidence_grades_returns_all_four_keys_even_when_zero():
    counts = count_evidence_grades("[STRONG] только один тег.")
    # Schema contract: callers can read counts[g] without try/except.
    assert set(counts.keys()) == set(EVIDENCE_GRADES)
    assert counts["STRONG"] == 1
    assert counts["MODERATE"] == 0


def test_count_evidence_grades_handles_repeats_and_mixed():
    text = (
        "[STRONG] Росстат: 47%. [MODERATE] Knight Frank ожидает 52%. "
        "[STRONG] Минстрой: коридор 45–50%. [WEAK] РБК со ссылкой на источник. "
        "[SPECULATIVE] Авторская оценка — диапазон 46–49%."
    )
    counts = count_evidence_grades(text)
    assert counts["STRONG"] == 2
    assert counts["MODERATE"] == 1
    assert counts["WEAK"] == 1
    assert counts["SPECULATIVE"] == 1
    assert total_grades(counts) == 5


def test_count_evidence_grades_ignores_lowercase_or_partial_tags():
    # The synthesizer must use the documented uppercase form. Variants
    # are deliberately not counted so we surface non-conformance.
    text = "[strong] нижний регистр, [STRONGLY] почти, [Strong] не считается."
    counts = count_evidence_grades(text)
    assert counts == {grade: 0 for grade in EVIDENCE_GRADES}


# ---------------------------------------------------------------------------
# has_grade_variance — Step 1.1 acceptance signal
# ---------------------------------------------------------------------------


def test_has_grade_variance_passes_with_two_distinct():
    text = "[STRONG] факт. [MODERATE] другой факт."
    assert has_grade_variance(text) is True


def test_has_grade_variance_fails_when_uniform():
    text = "[STRONG] один. [STRONG] два. [STRONG] три. [STRONG] четыре."
    assert has_grade_variance(text) is False


def test_has_grade_variance_fails_on_empty_text():
    assert has_grade_variance("") is False
    assert has_grade_variance("Текст без единого тега.") is False


def test_has_grade_variance_respects_custom_threshold():
    text = "[STRONG] a. [MODERATE] b."
    assert has_grade_variance(text, min_distinct=2) is True
    assert has_grade_variance(text, min_distinct=3) is False


# ---------------------------------------------------------------------------
# evidence_grade_distribution — full FinalReport
# ---------------------------------------------------------------------------


def _build_minimal_report(*, top_findings: list[str], main_synthesis: str = "") -> FinalReport:
    return FinalReport(
        session_id="t-1",
        question="Тестовый вопрос",
        executive_summary=ExecutiveSummaryV4(
            main_answer="ответ",
            top_findings=top_findings,
        ),
        main_synthesis=main_synthesis,
        callouts=[
            CalloutBlock(
                kind="insight",
                title="Закон убывающей отдачи",
                body="[WEAK] After 7 amenities each new one adds <1%.",
            )
        ],
        qa_section=[
            QAItem(
                question="Что лидирует?",
                answer="[MODERATE] По JLL — фитнес и МОПы.",
                details_ref="Раздел 3",
            )
        ],
        key_numbers_highlight=[
            KeyNumberHighlight(
                value="47%",
                label="[STRONG] доля бизнес-класса по ЕРЗ 2024",
                source_ref="ЕРЗ",
                importance="headline",
            )
        ],
    )


def test_evidence_grade_distribution_aggregates_across_fields():
    report = _build_minimal_report(
        top_findings=[
            "[STRONG] Росстат подтверждает 47%.",
            "[MODERATE] JLL ожидает 52%.",
            "[SPECULATIVE] Авторская оценка диапазона.",
        ],
        main_synthesis="[STRONG] Сводный показатель — 49%.",
    )
    dist = evidence_grade_distribution(report)
    # main_synthesis(1) + top_findings STRONG(1) + key_numbers_highlight(1) = 3
    assert dist["STRONG"] == 3
    # top_findings(1) + qa_section(1) = 2
    assert dist["MODERATE"] == 2
    # callouts(1)
    assert dist["WEAK"] == 1
    # top_findings(1)
    assert dist["SPECULATIVE"] == 1


def test_evidence_grade_distribution_passes_variance_check_for_realistic_report():
    report = _build_minimal_report(
        top_findings=[
            "[STRONG] Росстат: 47%.",
            "[MODERATE] JLL: 52%.",
        ],
    )
    dist = evidence_grade_distribution(report)
    distinct = sum(1 for v in dist.values() if v > 0)
    assert distinct >= 2  # the Step 1.1 acceptance signal


# ---------------------------------------------------------------------------
# Synthesizer prompt regression
# ---------------------------------------------------------------------------


def test_synthesizer_prompt_documents_all_four_grades():
    """Regression guard: removing the EVIDENCE GRADING section silently
    would make the LLM stop emitting tags — and the variance test would
    keep passing on stale fixtures. Pin the prompt-side contract here.
    """
    prompt_path = Path(__file__).parent.parent / "prompts" / "synthesizer.md"
    text = prompt_path.read_text(encoding="utf-8")
    assert "ПРАВИЛО EVIDENCE GRADING" in text
    for grade in EVIDENCE_GRADES:
        assert f"[{grade}]" in text, f"Grade tag [{grade}] missing from synthesizer prompt"


# ---------------------------------------------------------------------------
# Language lint regression — tags must not be flagged as anglicisms
# ---------------------------------------------------------------------------


def test_language_lint_does_not_flag_evidence_grade_tags():
    """If lint flagged [STRONG] etc., every Synthesizer output would
    trigger Track 3 retry until exhausted. Verify all four tags pass.
    """
    text = (
        "[STRONG] По Росстату 47%. "
        "[MODERATE] По JLL 52%. "
        "[WEAK] По РБК со ссылкой на брокера 50%. "
        "[SPECULATIVE] Авторский диапазон 46–49%."
    )
    warnings = lint_output_language(text)
    flagged_tokens = {w.token for w in warnings}
    for grade in EVIDENCE_GRADES:
        assert grade not in flagged_tokens, (
            f"Language lint flagged grade tag '{grade}' as an anglicism — "
            "this would trigger an infinite Track 3 retry loop. Ensure "
            "_RE_EVIDENCE_GRADE in language_lint.py strips them before scanning."
        )


def test_language_lint_does_not_flag_grade_tags_inside_real_paragraph():
    """Same guard, but in context — surrounded by real Russian prose
    with [REF:...] markers, anglicism whitelist tokens, and punctuation.
    """
    text = (
        "## Доли по сегменту жилья 2024\n\n"
        "[STRONG] По данным ЕРЗ доля бизнес-класса в Москве — 47% [REF:https://erzrf.ru]. "
        "[MODERATE] JLL даёт оценку 52% (vendor-биас premium-сегмента). "
        "[WEAK] РБК Недвижимость со ссылкой на брокера — 50%. "
        "[SPECULATIVE] Корректный коридор по совокупности — 46–49% (авторский синтез).\n\n"
        "CAPEX на amenities в этом сегменте — 3–5% (см. таблицу)."
    )
    warnings = lint_output_language(text)
    flagged_tokens = {w.token for w in warnings}
    # No grade tag should appear in flags.
    for grade in EVIDENCE_GRADES:
        assert grade not in flagged_tokens
    # CAPEX (whitelist) also must not appear.
    assert "CAPEX" not in flagged_tokens


# ---------------------------------------------------------------------------
# Live LLM acceptance check — gated behind -m expensive
# ---------------------------------------------------------------------------


@pytest.mark.expensive
def test_synthesizer_emits_grade_variance_on_real_call():
    """End-to-end acceptance for Step 1.1.

    Skipped by default. Requires OPENROUTER_API_KEY and a stubbed session
    fixture; marked ``expensive`` so the CI-light path stays free.

    NOTE: This test is intentionally a placeholder — wiring up a full
    V4Session fixture and hitting Sonnet 4.6 belongs in the live
    acceptance run, not in unit-test scope. The Step 1.1 plan calls for
    running this manually on a reference query when OpenRouter credits
    are available. Until then, the plain-text variance test above is
    the contract.
    """
    pytest.skip(
        "Live acceptance pending — see autonomous brief Day 2-3 final "
        "verification step. Run manually after OpenRouter top-up."
    )
