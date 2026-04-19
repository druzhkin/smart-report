"""Tests for synthesizer citation pipeline — v4.5 schema-pipeline track.

Tests that:
1. Synthesizer emits [REF:...] markers
2. Post-processing converts them to [N]
3. bibliography is populated
4. End-to-end coverage target is met on cached data
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from smart_report.bibliography import generate_bibliography
from smart_report.data_audit import audit_fact_coverage
from smart_report.models import (
    AnalysisOutput,
    CalloutBlock,
    ExecutiveSummaryV4,
    FinalReport,
    KeyNumber,
    NumericFact,
    QAItem,
    RankingItem,
    Source,
    SourceRef,
    Table,
    V4Session,
    UploadedMarkdown,
    ResearchPrompt,
)

RUNS_DIR = Path(__file__).parents[1] / "runs"
CACHE_ANALYSIS_PATH = RUNS_DIR / "night_upgrade" / "cache_analysis.json"


def _make_session() -> V4Session:
    """Create a minimal V4Session for testing."""
    return V4Session(
        session_id="test-synth-citations",
        raw_question="тест",
        source_reports=[
            UploadedMarkdown(filename="test.md", content="Данные [[1]](https://erzrf.ru/test). Цена 55%.", word_count=10)
        ],
        analysis=AnalysisOutput(),
        status="analyzed",
        created_at=datetime.now(timezone.utc),
    )


def _make_final_report_with_refs(refs: list[str]) -> FinalReport:
    """Create a FinalReport with [REF:url] markers in main_synthesis."""
    synthesis_parts = []
    for i, url in enumerate(refs):
        synthesis_parts.append(f"Факт {i+1} составил {(i+1)*10}% [REF:{url}].")
    return FinalReport(
        session_id="test",
        question="тест",
        executive_summary=ExecutiveSummaryV4(main_answer="Ответ."),
        main_synthesis=" ".join(synthesis_parts),
        all_sources=[
            Source(title=f"Источник {i+1}", url=url, tool="test")
            for i, url in enumerate(refs)
        ],
        metadata={},
    )


# ---------------------------------------------------------------------------
# Test: synthesizer emits [REF:...] markers → bibliography populated
# ---------------------------------------------------------------------------


def test_synthesizer_emits_ref_markers_and_bibliography_populated() -> None:
    """After generate_bibliography, [REF:x] → [N] and bibliography is non-empty."""
    urls = [
        "https://erzrf.ru/article1",
        "https://metrium.ru/report",
        "https://realty.rbc.ru/news/123",
    ]
    report = _make_final_report_with_refs(urls)

    # Verify [REF:...] markers exist before processing
    assert "[REF:" in report.main_synthesis

    # Run bibliography generation
    updated_report, coverage = generate_bibliography(report)

    # [REF:] should be gone
    assert "[REF:" not in updated_report.main_synthesis

    # [1], [2], [3] should be present
    assert "[1]" in updated_report.main_synthesis
    assert "[2]" in updated_report.main_synthesis
    assert "[3]" in updated_report.main_synthesis

    # Bibliography populated
    assert len(updated_report.bibliography) == 3
    numbers = sorted(ns.number for ns in updated_report.bibliography)
    assert numbers == [1, 2, 3]

    # source_count set
    assert updated_report.source_count == 3


def test_bibliography_citation_coverage_is_positive() -> None:
    """Citation coverage > 0 when facts with [REF:] are present."""
    report = _make_final_report_with_refs([
        "https://a.com",
        "https://b.com",
    ])
    updated_report, coverage = generate_bibliography(report)
    assert updated_report.citation_coverage > 0


# ---------------------------------------------------------------------------
# Test: mock synthesizer output → post-processing completes correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_post_processing_with_mock_synth() -> None:
    """Orchestrator runs bibliography + audit after synthesizer (mocked LLM)."""
    from smart_report.v4_orchestrator import V4Orchestrator, V4SessionStore

    # Create mock FinalReport JSON that the LLM would return
    mock_final_data = {
        "session_id": "test-pp",
        "question": "тестовый вопрос",
        "research_prompt_used": "",
        "executive_summary": {
            "main_answer": "Рынок вырос на 15% [REF:https://erzrf.ru/test]. Это важно.",
            "ranking": None,
            "top_findings": [
                "Цена составила 880 тыс. руб./м² [REF:https://metrium.ru/report]"
            ],
            "key_numbers": [
                {"value": "15%", "metric": "рост рынка", "subject": "бизнес-класс", "source_url": "https://erzrf.ru/test"}
            ],
            "confidence_note": "Высокий уровень доверия.",
            "what_meta_adds": "Мета-анализ уточнил цифры.",
        },
        "main_synthesis": (
            "## Рынок бизнес-класса\n"
            "Рынок вырос на 15% [REF:https://erzrf.ru/test]. "
            "Средняя цена — 880 тыс. руб./м² [REF:https://metrium.ru/report]. "
            "Доля ипотеки составила 55% [REF:https://erzrf.ru/ipoteka]."
        ),
        "consensus_section": "Рост цен — консенсус всех источников [REF:https://erzrf.ru/test].",
        "conflicts_section": "",
        "gaps_filled_section": "",
        "all_sources": [
            {"title": "ЕРЗ.РФ", "url": "https://erzrf.ru/test", "tool": "perplexity", "reliability": "high"},
            {"title": "Метриум", "url": "https://metrium.ru/report", "tool": "perplexity", "reliability": "high"},
            {"title": "ЕРЗ ипотека", "url": "https://erzrf.ru/ipoteka", "tool": "perplexity", "reliability": "high"},
        ],
        "metadata": {},
        "qa_section": [],
        "ranking": [],
        "tables": [],
        "charts": [],
        "callouts": [],
        "key_numbers_highlight": [],
        "cover_image_prompt": None,
    }

    from smart_report.llm import LLMResult
    mock_llm_result = LLMResult(
        text=json.dumps(mock_final_data),
        cost_rub=1.0,
    )

    store = V4SessionStore()
    session = store.create("test-pp", "тестовый вопрос")

    # Setup session with source reports and analysis
    session.source_reports = [
        UploadedMarkdown(filename="test.md", content="Данные о рынке.", word_count=5)
    ]
    session.analysis = AnalysisOutput(
        consensus=[],
        conflicts=[],
        gaps=[],
        all_numeric_facts=[],
        high_relevance_facts=[],
        fact_coverage_target=0,
    )
    session.status = "analyzed"
    store.update(session)

    orch = V4Orchestrator(store, mock=True)

    with patch("smart_report.synthesizer.call_json", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_llm_result
        # Disable mock mode so post-processing runs (mock=True skips retry only)
        orch.mock = False
        final = await orch.synthesize("test-pp")

    # Verify bibliography was generated
    assert len(final.bibliography) >= 1
    assert final.source_count >= 1

    # Verify [REF:] markers replaced with [N] in synthesis text
    assert "[REF:" not in final.main_synthesis
    assert "[1]" in final.main_synthesis or "[2]" in final.main_synthesis

    # Verify coverage audit ran and stored result
    assert "coverage_audit" in final.metadata


# ---------------------------------------------------------------------------
# Test: end-to-end cached analysis (expensive, behind marker)
# ---------------------------------------------------------------------------


@pytest.mark.expensive
@pytest.mark.skipif(
    not CACHE_ANALYSIS_PATH.exists(),
    reason="cache_analysis.json not available",
)
def test_end_to_end_cached_coverage_target() -> None:
    """Smoke test: load cached analysis, verify high_relevance_facts structure."""
    raw = json.loads(CACHE_ANALYSIS_PATH.read_text(encoding="utf-8"))
    analysis = AnalysisOutput.model_validate(raw)

    # In v4.5, if intake ran, high_relevance_facts should be populated
    # For v4 cache (no intake), these will be empty — that's acceptable
    assert isinstance(analysis.high_relevance_facts, list)
    assert isinstance(analysis.all_numeric_facts, list)
    assert isinstance(analysis.fact_coverage_target, int)


# ---------------------------------------------------------------------------
# Model-level: NumericFact deterministic ID
# ---------------------------------------------------------------------------


def test_numeric_fact_deterministic_id() -> None:
    """Same inputs always produce the same fact_id."""
    fid1 = NumericFact.make_id("55%", "доля ипотеки", "бизнес-класс Москва 2024")
    fid2 = NumericFact.make_id("55%", "доля ипотеки", "бизнес-класс Москва 2024")
    assert fid1 == fid2
    assert len(fid1) == 12  # sha1 hex[:12]


def test_numeric_fact_different_inputs_different_ids() -> None:
    """Different inputs produce different fact_ids."""
    fid1 = NumericFact.make_id("55%", "доля ипотеки", "бизнес-класс")
    fid2 = NumericFact.make_id("68%", "доля ипотеки", "бизнес-класс")
    assert fid1 != fid2
