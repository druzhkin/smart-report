"""Tests for the deterministic "Сводная таблица данных" table parser (Track 4).

Covers:
- Russian / English heading detection
- Column mapping and cell normalisation
- URL extraction from markdown links
- Quote stripping (Russian guillemet / ASCII)
- Category inference from metric keywords
- Author-synthesis detection
- Large table handling (50 rows, unique fact_ids)
- Malformed table rejection (missing value column)
- Integration with normalize_report:
    · fast path (table present, LLM skipped)
    · fallback path (no table, LLM called)
- Real-world fixture: 30-row sample_with_data_table.md
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from textwrap import dedent
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from smart_report.intake import parse_data_table, normalize_report
from smart_report.models import NumericFact, NormalizedReport, UploadedMarkdown

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_md(content: str, filename: str = "test.md") -> UploadedMarkdown:
    return UploadedMarkdown(
        filename=filename,
        content=content,
        detected_tool=None,
        word_count=len(content.split()),
    )


def _simple_table(rows: list[list[str]]) -> str:
    """Build a minimal markdown table with standard data-table columns."""
    header = "| № | Метрика | Значение | Субъект | Период | Источник | Цитата |"
    sep = "|---|---------|----------|---------|--------|----------|--------|"
    lines = [header, sep]
    for i, row in enumerate(rows, start=1):
        metric, value, subject, period, source, quote = (row + [""] * 6)[:6]
        lines.append(f"| {i} | {metric} | {value} | {subject} | {period} | {source} | {quote} |")
    return "\n".join(lines)


def _doc_with_table(table_markdown: str, heading: str = "## Сводная таблица данных") -> str:
    return f"# Отчёт\n\nТекст.\n\n{heading}\n\n{table_markdown}\n"


# ---------------------------------------------------------------------------
# 1. test_parser_finds_russian_header
# ---------------------------------------------------------------------------


def test_parser_finds_russian_header() -> None:
    """Markdown with '## Сводная таблица данных' → parser returns a list."""
    table = _simple_table([["средняя цена", "500 тыс.", "ЖК Тест", "2024", "https://example.com", ""]])
    doc = _doc_with_table(table)
    result = parse_data_table(doc)
    assert result is not None
    assert isinstance(result, list)
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# 2. test_parser_finds_english_header
# ---------------------------------------------------------------------------


def test_parser_finds_english_header() -> None:
    """Markdown with '## Data Summary Table' → parser returns a list."""
    header_row = "| Metric | Value | Subject | Timeframe | Source | Quote |"
    sep = "|--------|-------|---------|-----------|--------|-------|"
    data_row = "| price | 500k | Test | 2024 | https://x.com | some quote |"
    table = f"{header_row}\n{sep}\n{data_row}"
    doc = f"# Report\n\n## Data Summary Table\n\n{table}\n"
    result = parse_data_table(doc)
    assert result is not None
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# 3. test_parser_returns_none_when_no_table
# ---------------------------------------------------------------------------


def test_parser_returns_none_when_no_table() -> None:
    """Plain prose without any data table heading → returns None."""
    doc = dedent("""\
        # Аналитика

        Рынок вырос на 15%. Цена составила 480 тыс. руб./м².
        Доля ипотеки — 55%.
    """)
    result = parse_data_table(doc)
    assert result is None


# ---------------------------------------------------------------------------
# 4. test_parser_strips_markdown_link_in_url_column
# ---------------------------------------------------------------------------


def test_parser_strips_markdown_link_in_url_column() -> None:
    """[text](https://example.com) in source column → source_url = raw URL."""
    table = _simple_table([
        ["доля ипотеки", "55%", "бизнес-класс", "2024", "[РБК](https://realty.rbc.ru/news/abc)", ""],
    ])
    doc = _doc_with_table(table)
    result = parse_data_table(doc)
    assert result is not None and len(result) == 1
    fact = result[0]
    # The source_url on the SourceRef should be the bare URL, not the markdown link
    assert fact.sources
    assert fact.sources[0].url == "https://realty.rbc.ru/news/abc"


# ---------------------------------------------------------------------------
# 5. test_parser_strips_russian_quotes_around_quote
# ---------------------------------------------------------------------------


def test_parser_strips_russian_quotes_around_quote() -> None:
    """«текст цитаты» in quote column → source_quote = 'текст цитаты' (no guillemets)."""
    table = _simple_table([
        ["средняя цена", "880 тыс.", "Prime Park", "H1 2025", "https://rbc.ru", "«средняя цена в Prime Park»"],
    ])
    doc = _doc_with_table(table)
    result = parse_data_table(doc)
    assert result is not None and len(result) == 1
    assert result[0].source_quote == "средняя цена в Prime Park"


# ---------------------------------------------------------------------------
# 6. test_parser_infers_fact_category_from_price_keyword
# ---------------------------------------------------------------------------


def test_parser_infers_fact_category_from_price_keyword() -> None:
    """Metric 'средняя цена предложения' → fact_category == 'price'."""
    table = _simple_table([
        ["средняя цена предложения", "483 тыс.", "бизнес-класс", "2024", "", ""],
    ])
    doc = _doc_with_table(table)
    result = parse_data_table(doc)
    assert result is not None and len(result) == 1
    assert result[0].fact_category == "price"


# ---------------------------------------------------------------------------
# 7. test_parser_marks_author_synthesis
# ---------------------------------------------------------------------------


def test_parser_marks_author_synthesis() -> None:
    """Quote column containing 'авторский синтез' → is_author_synthesis=True."""
    table = _simple_table([
        ["CAPEX строительства", "200 тыс.", "бизнес-класс типовой", "2024", "авторский синтез", "авторский синтез"],
    ])
    doc = _doc_with_table(table)
    result = parse_data_table(doc)
    assert result is not None and len(result) == 1
    assert result[0].is_author_synthesis is True
    assert result[0].source_quote is None


# ---------------------------------------------------------------------------
# 8. test_parser_handles_50_row_table
# ---------------------------------------------------------------------------


def test_parser_handles_50_row_table() -> None:
    """Synthetic 50-row table → returns 50 facts with unique fact_ids."""
    rows = [
        [f"метрика {i}", f"{i * 10} тыс.", f"ЖК Тест {i}", f"202{i % 5}", "", ""]
        for i in range(1, 51)
    ]
    table = _simple_table(rows)
    doc = _doc_with_table(table)
    result = parse_data_table(doc)
    assert result is not None
    assert len(result) == 50
    ids = [f.fact_id for f in result]
    assert len(ids) == len(set(ids)), "All fact_ids must be unique"


# ---------------------------------------------------------------------------
# 9. test_parser_skipped_when_table_has_no_value_column
# ---------------------------------------------------------------------------


def test_parser_skipped_when_table_has_no_value_column() -> None:
    """Table without a 'Значение'/'Value' column → returns None (not a data table)."""
    # This could be a table of contents or a comparison table without values
    doc = dedent("""\
        # Отчёт

        ## Сводная таблица данных

        | Параметр | Описание | Источник |
        |----------|----------|----------|
        | Рынок | Бизнес-класс Москва | ЕРЗ |
        | Метод | ЦИАН API | ЦИАН |
    """)
    result = parse_data_table(doc)
    assert result is None


# ---------------------------------------------------------------------------
# 10. test_normalize_report_uses_parser_when_table_present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_report_uses_parser_when_table_present() -> None:
    """When content has a data table, normalize_report uses parser; LLM is never called."""
    table = _simple_table([
        ["доля ипотеки", "55%", "бизнес-класс Москва", "2024", "https://domrf.ru", ""],
        ["средняя цена", "483 тыс.", "бизнес-класс Москва", "2024", "https://cian.ru", "«цена»"],
    ])
    content = f"# Отчёт\n\n## Сводная таблица данных\n\n{table}\n"
    report = _make_md(content, "report_with_table.md")

    # Patch call_json to raise if ever called — it must NOT be called
    with patch("smart_report.intake.call_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = AssertionError("LLM should not be called when table is present")
        nr: NormalizedReport = await normalize_report(report, research_prompt="тест")

    assert nr.facts_table_found is True
    assert nr.facts_table_row_count == 2
    assert nr.fallback_used is False
    assert len(nr.extracted_numeric_facts) == 2
    mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# 11. test_normalize_report_falls_back_to_llm_when_no_table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_report_falls_back_to_llm_when_no_table() -> None:
    """Plain prose (no table) → normalize_report falls back to LLM; facts_table_found=False."""
    content = (
        "# Обзор рынка\n\n"
        "Цена составила 480 тыс. руб./м² [[1]](https://erzrf.ru/test).\n"
        "Доля ипотеки — 55%.\n"
    )
    report = _make_md(content, "prose_report.md")

    stub_llm_response = {
        "numeric_facts": [
            {
                "value": "480 тыс. руб./м²",
                "metric": "средняя цена",
                "subject": "рынок",
                "timeframe": "2024",
                "fact_category": "price",
                "relevance_to_question": "high",
                "source_urls": ["https://erzrf.ru/test"],
            }
        ],
        "qualitative_facts": [],
        "claims": [],
    }
    from smart_report.llm import LLMResult

    mock_result = LLMResult(text=json.dumps(stub_llm_response), cost_rub=0.1)

    with patch("smart_report.intake.call_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_result
        nr: NormalizedReport = await normalize_report(report, research_prompt="цены Москва")

    assert nr.facts_table_found is False
    assert nr.fallback_used is True
    assert nr.facts_table_row_count == 0
    assert len(nr.extracted_numeric_facts) >= 1
    mock_llm.assert_called_once()


# ---------------------------------------------------------------------------
# 12. test_parser_fixture_30_rows (real-world fixture)
# ---------------------------------------------------------------------------


def test_parser_fixture_30_rows() -> None:
    """sample_with_data_table.md fixture → 30 facts with all required fields populated."""
    fixture = FIXTURES_DIR / "sample_with_data_table.md"
    assert fixture.exists(), f"Fixture not found: {fixture}"

    content = fixture.read_text(encoding="utf-8")
    result = parse_data_table(content, research_prompt="аменити бизнес премиум новостройки Москва")

    assert result is not None, "Parser should find the table in the fixture"
    assert len(result) == 30, f"Expected 30 facts, got {len(result)}"

    # All facts must have non-empty value and fact_id
    for fact in result:
        assert fact.value, f"Empty value in fact {fact.fact_id}"
        assert len(fact.fact_id) == 12, f"Invalid fact_id length: {fact.fact_id}"

    # Unique fact_ids
    ids = [f.fact_id for f in result]
    assert len(ids) == len(set(ids)), "All fact_ids must be unique"

    # Author synthesis rows (rows 11, 12, 26, 28) should be marked
    synthesis_facts = [f for f in result if f.is_author_synthesis]
    assert len(synthesis_facts) >= 3, (
        f"Expected at least 3 author-synthesis facts, got {len(synthesis_facts)}"
    )

    # Facts with URLs should have SourceRef populated
    facts_with_url = [f for f in result if f.sources]
    assert len(facts_with_url) >= 20, (
        f"Expected at least 20 facts with source URLs, got {len(facts_with_url)}"
    )

    # At least some facts should have source_quote set (from guillemet-wrapped cells)
    facts_with_quote = [f for f in result if f.source_quote]
    assert len(facts_with_quote) >= 15, (
        f"Expected at least 15 facts with source_quote, got {len(facts_with_quote)}"
    )

    # Category inference: rows with "цена" metrics → fact_category == "price"
    price_facts = [f for f in result if f.fact_category == "price"]
    assert len(price_facts) >= 3, f"Expected ≥3 price facts, got {len(price_facts)}"


# ---------------------------------------------------------------------------
# 13. test_parser_handles_heading_variations
# ---------------------------------------------------------------------------


def test_parser_handles_heading_variations() -> None:
    """Various heading formats (different levels, 'фактов') are all recognised."""
    table = _simple_table([["рост цен", "18%", "бизнес-класс", "2024", "", ""]])

    for heading in [
        "# Сводная таблица данных",
        "### Сводная таблица фактов",
        "## таблица данных",
        "## таблица фактов",
        "## Data Summary Table",
        "## Reference Table",
    ]:
        doc = _doc_with_table(table, heading=heading)
        result = parse_data_table(doc)
        assert result is not None, f"Parser should recognise heading: {heading!r}"
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 14. test_parser_deduplicates_identical_rows
# ---------------------------------------------------------------------------


def test_parser_deduplicates_identical_rows() -> None:
    """Two rows with identical value+metric+subject produce only one fact."""
    table = _simple_table([
        ["средняя цена", "500 тыс.", "бизнес-класс", "2024", "", ""],
        ["средняя цена", "500 тыс.", "бизнес-класс", "2024", "", ""],  # exact duplicate
    ])
    doc = _doc_with_table(table)
    result = parse_data_table(doc)
    assert result is not None
    assert len(result) == 1, "Duplicate rows must be deduplicated"


# ---------------------------------------------------------------------------
# 15. test_parser_category_inference_variety
# ---------------------------------------------------------------------------


def test_parser_category_inference_variety() -> None:
    """Various metric keywords → correct fact_category assigned."""
    cases = [
        ("рост год к году", "growth_rate"),
        ("доля ипотеки в %", "share"),
        ("CAPEX строительства", "capex"),
        ("OPEX управление", "opex"),
        ("ценовая премия за бассейн", "premium_pct"),
        ("площадь паркинга м²", "area"),
        ("число лотов в экспозиции", "count"),
        ("рейтинг девелопера", "ranking_position"),
        ("неизвестная метрика xyz", "other"),
    ]
    for metric, expected_cat in cases:
        table = _simple_table([[metric, "100", "тест", "2024", "", ""]])
        doc = _doc_with_table(table)
        result = parse_data_table(doc)
        assert result is not None and len(result) == 1, f"Parser failed for metric={metric!r}"
        actual = result[0].fact_category
        assert actual == expected_cat, (
            f"metric={metric!r}: expected category={expected_cat!r}, got {actual!r}"
        )
