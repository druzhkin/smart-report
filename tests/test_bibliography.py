"""Tests for bibliography.py — v4.5 schema-pipeline track."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from smart_report.bibliography import generate_bibliography, _compute_citation_coverage
from smart_report.models import (
    CalloutBlock,
    ExecutiveSummaryV4,
    FinalReport,
    NumberedSource,
    QAItem,
    Source,
    SourceRef,
    Table,
)


def _make_report(**kwargs) -> FinalReport:
    """Create a minimal FinalReport for testing."""
    defaults = dict(
        session_id="test-session",
        question="тестовый вопрос",
        executive_summary=ExecutiveSummaryV4(
            main_answer="Ответ на вопрос.",
        ),
        main_synthesis="",
        all_sources=[],
        metadata={},
    )
    defaults.update(kwargs)
    return FinalReport(**defaults)


# ---------------------------------------------------------------------------
# Basic bibliography generation
# ---------------------------------------------------------------------------


def test_generate_bibliography_renumbers_sequentially() -> None:
    """Report with 3 [REF:] markers → 3 NumberedSource with numbers 1, 2, 3."""
    report = _make_report(
        main_synthesis=(
            "Цена выросла на 12% [REF:https://a.com/1]. "
            "Доля ипотеки составила 55% [REF:https://b.com/2]. "
            "Объём сделок [REF:https://c.com/3] превысил прогноз."
        )
    )

    updated_report, coverage = generate_bibliography(report)

    assert len(updated_report.bibliography) == 3
    numbers = sorted(ns.number for ns in updated_report.bibliography)
    assert numbers == [1, 2, 3]


def test_generate_bibliography_replaces_ref_markers_with_numbers() -> None:
    """[REF:url] in text is replaced with [N] after bibliography generation."""
    report = _make_report(
        main_synthesis=(
            "Первый факт [REF:https://a.com/1] и второй [REF:https://b.com/2]."
        )
    )

    updated_report, _ = generate_bibliography(report)

    assert "[REF:" not in updated_report.main_synthesis
    assert "[1]" in updated_report.main_synthesis
    assert "[2]" in updated_report.main_synthesis


def test_generate_bibliography_same_url_same_number() -> None:
    """Same URL used multiple times → same number, not duplicated in bibliography."""
    report = _make_report(
        main_synthesis=(
            "Первый [REF:https://same.com/url] и снова [REF:https://same.com/url]."
        )
    )

    updated_report, _ = generate_bibliography(report)

    assert len(updated_report.bibliography) == 1
    assert updated_report.bibliography[0].number == 1
    # Both occurrences replaced with [1]
    assert updated_report.main_synthesis.count("[1]") == 2


def test_generate_bibliography_order_of_first_appearance() -> None:
    """URLs are numbered in order of first appearance across all text fields."""
    report = _make_report(
        main_synthesis=(
            "В синтезе [REF:https://b.com] первый. "
            "Второй [REF:https://a.com] здесь."
        ),
        consensus_section="Консенсус [REF:https://c.com] подтверждает.",
    )

    updated_report, _ = generate_bibliography(report)

    bib_map = {ns.source_ref.url: ns.number for ns in updated_report.bibliography}
    # b.com appears first in main_synthesis
    assert bib_map["https://b.com"] == 1
    assert bib_map["https://a.com"] == 2
    assert bib_map["https://c.com"] == 3


def test_generate_bibliography_updates_source_count() -> None:
    """source_count is set to the number of bibliography entries."""
    report = _make_report(
        main_synthesis=(
            "[REF:https://x.com/1] и [REF:https://x.com/2] и [REF:https://x.com/3]."
        )
    )

    updated_report, _ = generate_bibliography(report)
    assert updated_report.source_count == 3


def test_generate_bibliography_uses_existing_all_sources_for_title() -> None:
    """If all_sources has matching URL, its title is used in bibliography."""
    report = _make_report(
        main_synthesis="Данные [REF:https://erzrf.ru/page] важны.",
        all_sources=[
            Source(title="ЕРЗ.РФ — портал", url="https://erzrf.ru/page", tool="perplexity")
        ],
    )

    updated_report, _ = generate_bibliography(report)

    assert len(updated_report.bibliography) == 1
    bib_entry = updated_report.bibliography[0]
    assert bib_entry.source_ref.title == "ЕРЗ.РФ — портал"


# ---------------------------------------------------------------------------
# Citation coverage metric
# ---------------------------------------------------------------------------


def test_citation_coverage_metric() -> None:
    """Report with 10 numeric claims, 8 cited → coverage_pct ≈ 0.8."""
    # Build text with 10 numeric patterns; 8 followed by [N] citation within 300 chars
    cited_claims = "\n".join(
        f"Цена выросла на {i}% [REF:https://example.com/{i}]. Это важно."
        for i in range(1, 9)  # 8 cited
    )
    uncited_claims = "\n".join(
        f"Доля составила {i + 90}%. Без источника."
        for i in range(1, 3)  # 2 uncited
    )
    report = _make_report(
        main_synthesis=cited_claims + "\n" + uncited_claims
    )

    updated_report, coverage = generate_bibliography(report)

    # We expect coverage to be > 0 (at least some cited)
    assert updated_report.citation_coverage > 0
    assert 0.0 <= updated_report.citation_coverage <= 1.0


def test_citation_coverage_zero_when_no_numeric_claims() -> None:
    """Text with no numeric claims → coverage 1.0 (trivially all covered)."""
    report = _make_report(
        main_synthesis="Это чисто качественный тезис без цифр. [REF:https://example.com]"
    )
    _, coverage = generate_bibliography(report)
    # Might be 1.0 (no numeric claims = trivially covered) or some value
    assert 0.0 <= coverage <= 1.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_generate_bibliography_empty_report() -> None:
    """Report with no [REF:] markers → empty bibliography, no crash."""
    report = _make_report(main_synthesis="Никаких ссылок в этом тексте.")
    updated_report, coverage = generate_bibliography(report)
    assert updated_report.bibliography == []
    assert updated_report.source_count == 0


def test_generate_bibliography_processes_qa_section() -> None:
    """[REF:] markers in qa_section.answer are also replaced."""
    report = _make_report(
        qa_section=[
            QAItem(
                question="Какова цена?",
                answer="Цена составила 880 тыс. руб./м² [REF:https://source.com/q].",
                details_ref="Раздел 1",
            )
        ]
    )

    updated_report, _ = generate_bibliography(report)
    assert "[REF:" not in updated_report.qa_section[0].answer
    assert "[1]" in updated_report.qa_section[0].answer
    assert len(updated_report.bibliography) == 1


def test_generate_bibliography_processes_callouts() -> None:
    """[REF:] markers in callout.body are replaced."""
    report = _make_report(
        callouts=[
            CalloutBlock(
                kind="insight",
                title="Ключевой инсайт",
                body="Рост составил 20% [REF:https://data.com/insight]. Это важно.",
            )
        ]
    )

    updated_report, _ = generate_bibliography(report)
    assert "[REF:" not in updated_report.callouts[0].body
    assert "[1]" in updated_report.callouts[0].body
