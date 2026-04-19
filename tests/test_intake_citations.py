"""Tests for intake citation extraction — v4.5 schema-pipeline track.

Covers:
- Format 1: [[N]](url) — amenities bracket-paren format
- Format 2: citeturnXviewY — OpenAI DR opaque tokens
- Format 3: [N] + bibliography at document end
- Format 4: plain markdown links [text](url)
- Numeric fact extraction (mocked LLM)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from smart_report.intake import (
    extract_sources_from_markdown,
    normalize_report,
    _parse_end_bibliography,
)
from smart_report.models import UploadedMarkdown

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_md(content: str, filename: str = "test.md") -> UploadedMarkdown:
    return UploadedMarkdown(
        filename=filename,
        content=content,
        detected_tool=None,
        word_count=len(content.split()),
    )


# ---------------------------------------------------------------------------
# Format 1: [[N]](url) — amenities bracket-paren format
# ---------------------------------------------------------------------------


def test_intake_format_bracket_parens() -> None:
    """[[N]](url) extracts correct url as SourceRef."""
    text = "Данные о ценах [[5]](https://example.com/price-data) показывают рост."
    sources = extract_sources_from_markdown(text, "test.md")
    urls = [s.url for s in sources]
    assert "https://example.com/price-data" in urls


def test_intake_format_bracket_parens_multiple() -> None:
    """Multiple [[N]](url) in text all extracted, no duplicates."""
    text = (
        "Источник [[1]](https://a.com/1) и [[2]](https://b.com/2) "
        "и снова [[1]](https://a.com/1) для подтверждения."
    )
    sources = extract_sources_from_markdown(text, "test.md")
    urls = [s.url for s in sources]
    assert "https://a.com/1" in urls
    assert "https://b.com/2" in urls
    assert len(urls) == len(set(urls)), "Duplicates must be removed"


def test_intake_format_bracket_parens_confidence_primary() -> None:
    """[[N]](url) format yields confidence='primary'."""
    text = "Цена [[1]](https://erzrf.ru/data) составила 800 тыс."
    sources = extract_sources_from_markdown(text, "test.md")
    assert sources
    src = next(s for s in sources if "erzrf.ru" in s.url)
    assert src.confidence == "primary"


# ---------------------------------------------------------------------------
# Format 2: citeturnXviewY — OpenAI DR opaque tokens
# ---------------------------------------------------------------------------


def test_intake_format_citeturn_preserved() -> None:
    """citeturnXviewY tokens are preserved as opaque SourceRef."""
    text = "По данным анализа citeturn0search3 рынок вырос на 15%."
    sources = extract_sources_from_markdown(text, "openai-dr.md")
    opaque = [s for s in sources if s.url.startswith("opaque:")]
    assert opaque, "Opaque citeturn token should be extracted"
    assert opaque[0].confidence == "secondary"


def test_intake_format_citeturn_multiple() -> None:
    """Multiple opaque tokens extracted independently."""
    text = (
        "Первый факт citeturn0search1 и второй факт citeturn1view2 подтверждают тренд."
    )
    sources = extract_sources_from_markdown(text, "openai-dr.md")
    opaque_urls = [s.url for s in sources if s.url.startswith("opaque:")]
    assert len(opaque_urls) == 2
    assert "opaque:citeturn0search1" in opaque_urls
    assert "opaque:citeturn1view2" in opaque_urls


# ---------------------------------------------------------------------------
# Format 3: [N] + bibliography at end of document
# ---------------------------------------------------------------------------


def test_intake_format_numbered_ref_with_bibliography() -> None:
    """[N] refs resolved via end-of-document numbered bibliography."""
    text = (
        "Цена выросла на 12% [1] по данным рынка [2].\n\n"
        "## Источники\n"
        "1. Название статьи — https://erzrf.ru/article-123\n"
        "2. Другой источник — https://metrium.ru/report\n"
    )
    bib = _parse_end_bibliography(text)
    assert 1 in bib
    assert "erzrf.ru" in bib[1][0]
    assert 2 in bib
    assert "metrium.ru" in bib[2][0]


def test_intake_format_numbered_ref_square_bracket_style() -> None:
    """[N]. style bibliography entries parsed correctly."""
    text = (
        "По данным [3] и [4] ситуация ясна.\n\n"
        "[3]. Аналитика bnmap.pro — https://bnmap.pro/analytics\n"
        "[4]. РБК Недвижимость — https://realty.rbc.ru/news/abc\n"
    )
    bib = _parse_end_bibliography(text)
    assert 3 in bib
    assert "bnmap.pro" in bib[3][0]
    assert 4 in bib
    assert "realty.rbc.ru" in bib[4][0]


# ---------------------------------------------------------------------------
# Format 4: plain markdown links [text](url)
# ---------------------------------------------------------------------------


def test_intake_format_plain_md_link() -> None:
    """[text](url) format extracted with title."""
    text = "Смотри [отчёт Метриум](https://metrium.ru/research/2024) для деталей."
    sources = extract_sources_from_markdown(text, "test.md")
    metrium = next((s for s in sources if "metrium.ru" in s.url), None)
    assert metrium is not None
    assert metrium.title == "отчёт Метриум"


def test_intake_format_plain_md_link_no_duplicate_with_bracket_paren() -> None:
    """Plain links don't duplicate [[N]](url) entries already captured."""
    text = "Данные [[3]](https://erzrf.ru/page) и [ЕРЗ](https://erzrf.ru/page) там же."
    sources = extract_sources_from_markdown(text, "test.md")
    erzrf_sources = [s for s in sources if "erzrf.ru/page" in s.url]
    assert len(erzrf_sources) == 1, "Should deduplicate identical URLs"


# ---------------------------------------------------------------------------
# accessed_via detection
# ---------------------------------------------------------------------------


def test_intake_accessed_via_perplexity() -> None:
    text = "Данные [[1]](https://erzrf.ru/x) из отчёта."
    sources = extract_sources_from_markdown(text, "deep-research-report-1.md")
    assert sources[0].accessed_via == "perplexity_dr_1"


def test_intake_accessed_via_manual() -> None:
    text = "Данные [[1]](https://example.com) из документа."
    sources = extract_sources_from_markdown(text, "amenities-main.md")
    assert sources[0].accessed_via == "manual_upload"


# ---------------------------------------------------------------------------
# Large fixture tests (if fixture available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (FIXTURES_DIR.parent.parent / "runs" / "night_upgrade" / "fixtures" / "amenities-main.md").exists(),
    reason="amenities-main.md fixture not available",
)
def test_intake_extracts_all_urls_from_amenities_main() -> None:
    """amenities-main.md has 126+ URLs; we should extract at least 100."""
    fixture_path = (
        FIXTURES_DIR.parent.parent
        / "runs"
        / "night_upgrade"
        / "fixtures"
        / "amenities-main.md"
    )
    content = fixture_path.read_text(encoding="utf-8")
    sources = extract_sources_from_markdown(content, "amenities-main.md")
    assert len(sources) >= 100, (
        f"Expected 100+ sources from amenities-main.md, got {len(sources)}"
    )


@pytest.mark.skipif(
    not (FIXTURES_DIR.parent.parent / "runs" / "night_upgrade" / "fixtures" / "amenities-main.md").exists(),
    reason="amenities-main.md fixture not available",
)
@pytest.mark.expensive
@pytest.mark.asyncio
async def test_intake_extracts_numeric_facts() -> None:
    """amenities-main.md should yield 800+ numeric facts via LLM extraction."""
    fixture_path = (
        FIXTURES_DIR.parent.parent
        / "runs"
        / "night_upgrade"
        / "fixtures"
        / "amenities-main.md"
    )
    content = fixture_path.read_text(encoding="utf-8")
    report = UploadedMarkdown(
        filename="amenities-main.md",
        content=content,
        word_count=len(content.split()),
    )
    nr = await normalize_report(
        report,
        research_prompt="amenities в бизнес и премиум новостройках Москвы",
    )
    assert len(nr.extracted_numeric_facts) >= 800, (
        f"Expected 800+ numeric facts, got {len(nr.extracted_numeric_facts)}"
    )


# ---------------------------------------------------------------------------
# Mocked LLM normalize_report test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_report_mocked() -> None:
    """normalize_report returns NormalizedReport with facts from mocked LLM."""
    mock_llm_response = {
        "numeric_facts": [
            {
                "value": "55%",
                "metric": "доля ипотеки",
                "subject": "бизнес-класс Москва 2024",
                "timeframe": "2024",
                "fact_category": "share",
                "relevance_to_question": "high",
                "source_urls": ["https://erzrf.ru/test"],
            },
            {
                "value": "880 тыс. руб./м²",
                "metric": "средняя цена",
                "subject": "Prime Park",
                "timeframe": "H1 2025",
                "fact_category": "price",
                "relevance_to_question": "high",
                "source_urls": [],
            },
        ],
        "qualitative_facts": [
            {
                "statement": "Бассейны требуют профессиональной УК",
                "subject": "бассейн в ЖК",
                "fact_category": "expert_opinion",
                "relevance_to_question": "medium",
                "source_urls": [],
            }
        ],
        "claims": [
            {
                "text": "Закрытая территория даёт +7–12% к цене",
                "claim_type": "numeric",
                "confidence_level": "high",
                "source_urls": ["https://erzrf.ru/test"],
            }
        ],
    }

    content = (
        "Данные о рынке [[1]](https://erzrf.ru/test) показывают рост.\n"
        "Цена составила 880 тыс. руб./м² [2]\n\n"
        "[2]. Источник — https://metrium.ru/report\n"
    )
    report = UploadedMarkdown(
        filename="test-report.md",
        content=content,
        word_count=len(content.split()),
    )

    import json
    from smart_report.llm import LLMResult

    mock_result = LLMResult(
        text=json.dumps(mock_llm_response),
        cost_rub=0.5,
    )

    with patch("smart_report.intake.call_json", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_result
        nr = await normalize_report(
            report,
            research_prompt="тест",
            mock=False,
        )

    assert nr.source_filename == "test-report.md"
    assert len(nr.extracted_numeric_facts) == 2
    assert len(nr.extracted_qualitative_facts) == 1
    assert len(nr.extracted_claims) == 1
    # Sources extracted by regex (not LLM)
    assert any("erzrf.ru" in s.url for s in nr.extracted_sources_inventory)
    # Fact IDs are deterministic
    from smart_report.models import NumericFact
    expected_id = NumericFact.make_id("55%", "доля ипотеки", "бизнес-класс Москва 2024")
    fact_ids = [nf.fact_id for nf in nr.extracted_numeric_facts]
    assert expected_id in fact_ids
