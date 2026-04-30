from __future__ import annotations

import pytest

from smart_report.exporters import v4_to_report_dict
from smart_report.exporters.premium import (
    assemble_premium_report_document,
    render_premium_docx,
    render_premium_pptx,
)
from smart_report.models import (
    AnalysisOutput,
    Conflict,
    ConsensusClaim,
    ExecutiveSummaryV4,
    FinalReport,
    Gap,
    NumericFact,
    Source,
    SourceRef,
)


def _report() -> FinalReport:
    return FinalReport(
        session_id="premium-doc",
        question="Forecast a market with scenario and risk recommendations",
        executive_summary=ExecutiveSummaryV4(
            main_answer="Base case is moderate growth with material downside triggers.",
            top_findings=["Demand is rate-sensitive.", "Supply remains constrained."],
            confidence_note="Confidence is medium because transaction data is partial.",
            what_meta_adds="Consensus, conflicts, and gaps are separated.",
        ),
        main_synthesis="The market baseline combines price, demand, supply, and policy drivers.",
        consensus_section="Sources agree on the direction but differ on magnitude.",
        conflicts_section="Sources disagree on timing.",
        gaps_filled_section="Project-level microdata remains unavailable.",
        all_sources=[
            Source(title="Official source", url="https://example.com/official", reliability="high"),
            Source(title="Industry source", url="https://example.com/industry", reliability="medium"),
        ],
    )


def _analysis() -> AnalysisOutput:
    facts = [
        NumericFact(
            fact_id="f1",
            value="10%",
            metric="growth",
            subject="market",
            relevance_to_question="high",
            sources=[SourceRef(url="https://example.com/official", title="Official")],
        )
    ]
    return AnalysisOutput(
        consensus=[
            ConsensusClaim(claim="Demand is sensitive to financing conditions.", confidence="high")
        ],
        conflicts=[
            Conflict(
                topic="Growth range",
                source_a="A",
                claim_a="High growth",
                source_b="B",
                claim_b="Moderate growth",
                importance="material",
            )
        ],
        gaps=[
            Gap(
                topic="Transaction microdata",
                why_critical="Needed for exact pricing",
                what_to_find="Closed transaction dataset",
            )
        ],
        all_numeric_facts=facts,
        high_relevance_facts=facts,
    )


def test_assemble_premium_document_uses_existing_analysis_layers():
    document = assemble_premium_report_document(_report(), analysis=_analysis())

    assert document.plan.deliverables.report_min_pages >= 20
    assert document.plan.deliverables.deck_min_slides >= 10
    assert document.source_count == 2
    assert document.numeric_fact_count == 1
    assert len(document.sections) >= 7
    assert len(document.appendices) == 3
    assert len(document.deck_slides) >= 10

    block_titles = {
        block.title
        for section in [*document.sections, *document.appendices]
        for block in section.blocks
    }
    assert "Реестр числовых доказательств" in block_titles
    assert "Противоречия и расхождения" in block_titles
    assert "Реестр рисков" in block_titles
    assert "Матрица решений" in block_titles


def test_assemble_premium_document_does_not_mutate_legacy_report():
    report = _report()
    before = v4_to_report_dict(report)
    _ = assemble_premium_report_document(report, analysis=_analysis())
    after = v4_to_report_dict(report)

    assert before == after


def test_render_premium_docx_opens_and_contains_report_structure(tmp_path):
    pytest.importorskip("docx")
    from docx import Document

    document = assemble_premium_report_document(
        _report(),
        analysis=_analysis(),
        premium_readiness={
            "ready": False,
            "score": 61,
            "issues": [
                {
                    "code": "premium_too_few_authoritative_sources",
                    "severity": "critical",
                    "message": "Authoritative source threshold is not met.",
                    "recommendation": "Add primary sources before delivery.",
                }
            ],
            "strengths": ["Consensus layer is present."],
        },
    )
    out = render_premium_docx(document, tmp_path / "premium.docx")

    assert out.exists()
    assert out.stat().st_size > 1000
    loaded = Document(out)
    table_text = "\n".join(
        cell.text
        for table in loaded.tables
        for row in table.rows
        for cell in row.cells
    )
    text = "\n".join([*(p.text for p in loaded.paragraphs), table_text])
    assert "SMART REPORT | ПРЕМИАЛЬНЫЙ АНАЛИТИЧЕСКИЙ ОТЧЁТ" in text
    assert "Панель решения клиента" in text
    assert "Короткий ответ" in text
    assert "Гейт платной выдачи" in text
    assert "Карта доказательной базы" in text
    assert "Гейт готовности к платной выдаче" in text
    assert "НЕ ГОТОВ К ПЛАТНОЙ ВЫДАЧЕ КЛИЕНТУ" in text
    assert "Структура отчёта" in text
    assert "Реестр числовых доказательств" in text
    assert len(loaded.tables) >= 4


def test_render_premium_pptx_opens_and_contains_deck_structure(tmp_path):
    pytest.importorskip("pptx")
    from pptx import Presentation

    document = assemble_premium_report_document(
        _report(),
        analysis=_analysis(),
        premium_readiness={
            "ready": False,
            "score": 61,
            "issues": [
                {
                    "code": "premium_too_few_authoritative_sources",
                    "severity": "critical",
                    "message": "Authoritative source threshold is not met.",
                    "recommendation": "Add primary sources before delivery.",
                }
            ],
            "strengths": ["Consensus layer is present."],
        },
    )
    out = render_premium_pptx(document, tmp_path / "premium_deck.pptx")

    assert out.exists()
    assert out.stat().st_size > 1000
    deck = Presentation(str(out))
    assert len(deck.slides) >= 10
    slide_text = "\n".join(
        shape.text
        for slide in deck.slides
        for shape in slide.shapes
        if hasattr(shape, "text")
    )
    assert "Короткий ответ" in slide_text
    assert "Готовность к платной выдаче" in slide_text
    assert "НЕ ГОТОВ" in slide_text
