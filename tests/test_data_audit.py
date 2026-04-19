"""Tests for data_audit.py — v4.5 schema-pipeline track."""

from __future__ import annotations

import pytest

from smart_report.data_audit import audit_fact_coverage, build_retry_feedback, CoverageReport
from smart_report.models import (
    AnalysisOutput,
    ExecutiveSummaryV4,
    FinalReport,
    NumericFact,
    SourceRef,
)


def _make_numeric_fact(
    value: str,
    metric: str,
    subject: str,
    relevance: str = "high",
) -> NumericFact:
    return NumericFact(
        fact_id=NumericFact.make_id(value, metric, subject),
        value=value,
        metric=metric,
        subject=subject,
        relevance_to_question=relevance,  # type: ignore[arg-type]
        fact_category="other",
    )


def _make_analysis(high_facts: list[NumericFact]) -> AnalysisOutput:
    """Create an AnalysisOutput with specified high_relevance_facts."""
    return AnalysisOutput(
        high_relevance_facts=high_facts,
        all_numeric_facts=high_facts,
        fact_coverage_target=int(len(high_facts) * 0.85),
    )


def _make_report(synthesis: str = "") -> FinalReport:
    return FinalReport(
        session_id="test",
        question="тест",
        executive_summary=ExecutiveSummaryV4(main_answer="OK"),
        main_synthesis=synthesis,
        metadata={},
    )


# ---------------------------------------------------------------------------
# Basic audit tests
# ---------------------------------------------------------------------------


def test_audit_missing_facts_poor_verdict() -> None:
    """5 of 10 high_relevance facts in final → verdict 'poor'."""
    facts = [
        _make_numeric_fact(f"{i}%", "доля сегмента", f"объект {i}")
        for i in range(1, 11)  # 10 facts
    ]
    analysis = _make_analysis(facts)

    # Only include facts 1-5 in synthesis
    synthesis = " ".join(
        f"Доля сегмента составила {i}% в объекте {i}. Данные важны."
        for i in range(1, 6)  # only 5 facts mentioned
    )
    report = _make_report(synthesis=synthesis)

    result = audit_fact_coverage(analysis, report)

    assert result.high_relevance_total == 10
    # At least some facts should be found, but not all
    assert result.facts_in_final < 10
    # With only 5 of 10, coverage should be ≤ 0.75 → poor or critical
    assert result.verdict in ("poor", "critical_failure", "acceptable")


def test_audit_excellent_all_facts_present() -> None:
    """All 5 high_relevance facts found in final → verdict 'excellent'."""
    facts = [
        _make_numeric_fact("55%", "доля ипотеки", "бизнес-класс Москва"),
        _make_numeric_fact("880 тыс.", "средняя цена", "Prime Park"),
        _make_numeric_fact("126", "число URL", "amenities документ"),
        _make_numeric_fact("12%", "ценовая премия", "закрытая территория"),
        _make_numeric_fact("3-5%", "CAPEX amenities", "оптимальный бюджет"),
    ]
    analysis = _make_analysis(facts)

    # Include all facts in synthesis
    synthesis = (
        "Доля ипотеки составила 55% в бизнес-классе Москвы. "
        "Средняя цена Prime Park — 880 тыс. руб. "
        "Документ содержит 126 URL по amenities. "
        "Ценовая премия за закрытую территорию составляет 12%. "
        "Оптимальный бюджет CAPEX amenities — 3-5%."
    )
    report = _make_report(synthesis=synthesis)

    result = audit_fact_coverage(analysis, report)

    assert result.high_relevance_total == 5
    assert result.verdict == "excellent"
    assert result.coverage_pct > 0.85


def test_audit_no_high_relevance_facts() -> None:
    """Empty high_relevance_facts → excellent verdict, no crash."""
    analysis = _make_analysis([])
    report = _make_report(synthesis="Текст без числовых данных.")

    result = audit_fact_coverage(analysis, report)

    assert result.verdict == "excellent"
    assert result.coverage_pct == 1.0
    assert result.high_relevance_total == 0


def test_audit_zero_coverage_critical_failure() -> None:
    """No facts present in empty report → critical_failure."""
    facts = [
        _make_numeric_fact("55%", "доля ипотеки", "бизнес-класс"),
        _make_numeric_fact("880 тыс.", "цена", "Prime Park"),
        _make_numeric_fact("12%", "премия", "территория"),
        _make_numeric_fact("3%", "CAPEX", "бюджет"),
        _make_numeric_fact("22%", "доля", "бассейн"),
    ]
    analysis = _make_analysis(facts)
    report = _make_report(synthesis="Никаких данных нет.")

    result = audit_fact_coverage(analysis, report)

    assert result.verdict in ("poor", "critical_failure")
    assert result.coverage_pct < 0.6 or result.coverage_pct == 0.0


# ---------------------------------------------------------------------------
# Verdict thresholds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("coverage,expected_verdict", [
    (0.90, "excellent"),
    (0.86, "excellent"),
    (0.85, "acceptable"),
    (0.80, "acceptable"),
    (0.75, "acceptable"),
    (0.74, "poor"),
    (0.60, "poor"),
    (0.59, "critical_failure"),
    (0.0, "critical_failure"),
])
def test_verdict_thresholds(coverage: float, expected_verdict: str) -> None:
    """Verify verdict thresholds per spec: >85%=excellent, 75-85%=acceptable, etc."""
    from smart_report.data_audit import _compute_verdict
    assert _compute_verdict(coverage) == expected_verdict


# ---------------------------------------------------------------------------
# build_retry_feedback
# ---------------------------------------------------------------------------


def test_build_retry_feedback_lists_missing_facts() -> None:
    """build_retry_feedback includes missing facts in the message."""
    facts = [
        _make_numeric_fact("55%", "доля ипотеки", "бизнес-класс"),
        _make_numeric_fact("12%", "ценовая премия", "закрытая территория"),
    ]
    coverage_report = CoverageReport(
        coverage_pct=0.5,
        facts_in_final=0,
        high_relevance_total=2,
        missing_high_relevance_facts=facts,
        verdict="critical_failure",
        detail="test",
    )

    feedback = build_retry_feedback(coverage_report)

    assert "55%" in feedback
    assert "доля ипотеки" in feedback
    assert "12%" in feedback
    assert "critical_failure" in feedback


def test_build_retry_feedback_empty_when_no_missing() -> None:
    """No missing facts → empty feedback string."""
    coverage_report = CoverageReport(
        coverage_pct=0.9,
        facts_in_final=9,
        high_relevance_total=10,
        missing_high_relevance_facts=[],
        verdict="excellent",
    )

    feedback = build_retry_feedback(coverage_report)
    assert feedback == ""


# ---------------------------------------------------------------------------
# Fact detection in various text fields
# ---------------------------------------------------------------------------


def test_audit_finds_facts_in_qa_section() -> None:
    """Facts in qa_section.answer are counted."""
    from smart_report.models import QAItem
    fact = _make_numeric_fact("55%", "доля ипотеки", "бизнес-класс Москва")
    analysis = _make_analysis([fact])

    report = _make_report(synthesis="Нет данных здесь.")
    report.qa_section = [
        QAItem(
            question="Какова доля ипотеки?",
            answer="Доля ипотеки в бизнес-классе Москвы составила 55% по данным ЕРЗ.",
            details_ref="Раздел 1",
        )
    ]

    result = audit_fact_coverage(analysis, report)
    assert result.facts_in_final >= 1


def test_audit_finds_facts_in_callouts() -> None:
    """Facts in callout.body are counted."""
    from smart_report.models import CalloutBlock
    fact = _make_numeric_fact("880 тыс. руб.", "средняя цена", "Prime Park")
    analysis = _make_analysis([fact])

    report = _make_report()
    report.callouts = [
        CalloutBlock(
            kind="key_number",
            title="Цена Prime Park",
            body="Средняя цена Prime Park составила 880 тыс. руб. за квадратный метр.",
        )
    ]

    result = audit_fact_coverage(analysis, report)
    assert result.facts_in_final >= 1
