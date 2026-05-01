from __future__ import annotations

import pytest

from smart_report.exporters.premium import (
    ReportEditRequest,
    apply_publication_remediation,
    apply_report_edits,
    build_regeneration_plan,
    final_report_from_structured_source,
    hash_structured_source,
    run_enterprise_quality_gates,
    structured_source_from_final_report,
)
from smart_report.models import (
    ChartSpec,
    ExecutiveSummaryV4,
    FinalReport,
    KeyNumberHighlight,
    Source,
    Table,
)


def test_structured_source_is_single_editable_truth_for_report_package():
    source = structured_source_from_final_report(_report())

    assert source.metadata.title
    assert len(source.sections) >= 4
    assert source.sources
    assert "valyu" in source.research_coverage.connectors_used
    assert source.versions

    plan = build_regeneration_plan(source)

    assert plan.can_regenerate
    assert plan.requested_formats[:3] == ["docx", "pdf", "pptx"]
    assert plan.default_word_artifact == "docx"
    assert plan.quality_gate.passed


def test_client_edit_changes_structured_source_and_creates_version():
    source = structured_source_from_final_report(_report())
    before_hash = hash_structured_source(source)

    updated = apply_report_edits(
        source,
        [
            ReportEditRequest(
                actor_role="client_reviewer",
                target_path="metadata.title",
                value="Новый заголовок клиентского отчета",
                reason="Client renamed the publication.",
            )
        ],
    )

    assert updated.metadata.title == "Новый заголовок клиентского отчета"
    assert hash_structured_source(updated) != before_hash
    assert len(updated.versions) == len(source.versions) + 1
    assert updated.versions[-1].actor_role == "client_reviewer"


def test_structured_source_projects_back_to_renderer_report():
    base = _report()
    source = structured_source_from_final_report(base)
    updated = apply_report_edits(
        source,
        [
            ReportEditRequest(
                actor_role="editor",
                target_path="metadata.title",
                value="Редакционный заголовок",
            ),
            ReportEditRequest(
                actor_role="editor",
                target_path=(
                    f"sections.executive_summary.blocks."
                    f"{source.sections[0].blocks[0].id}.content"
                ),
                value="Новый главный вывод для клиента.",
            ),
        ],
    )

    projected = final_report_from_structured_source(base, updated)

    assert projected.question == "Редакционный заголовок"
    assert projected.executive_summary.main_answer == "Новый главный вывод для клиента."
    assert projected.metadata["structured_source_hash"] == hash_structured_source(updated)


def test_quality_reviewer_cannot_edit_content():
    source = structured_source_from_final_report(_report())

    with pytest.raises(PermissionError):
        apply_report_edits(
            source,
            [
                ReportEditRequest(
                    actor_role="quality_reviewer",
                    target_path="metadata.title",
                    value="Unauthorized edit",
                )
            ],
        )


def test_regeneration_plan_readds_docx_when_client_requests_pdf_only():
    source = structured_source_from_final_report(_report())

    plan = build_regeneration_plan(source, requested_formats=["pdf"])

    assert plan.requested_formats == ["docx", "pdf"]
    assert plan.quality_gate.passed


def test_quality_gate_blocks_internal_client_surface_markers():
    source = structured_source_from_final_report(_report())
    bad_block = source.sections[0].blocks[0]
    bad_block.content = "main_synthesis [STRONG] leaked internal annotation"

    gate = run_enterprise_quality_gates(source)

    assert not gate.passed
    assert {issue.code for issue in gate.issues} >= {"internal_marker_leak"}


def test_quality_gate_blocks_thin_visual_support():
    source = structured_source_from_final_report(_report())
    source.sections = [section for section in source.sections if section.id != "visual_evidence"]
    for section in source.sections:
        section.blocks = [block for block in section.blocks if block.kind != "kpi_strip"]

    gate = run_enterprise_quality_gates(source)

    assert not gate.passed
    assert "thin_visual_support" in {issue.code for issue in gate.issues}


def test_publication_remediation_adds_safe_source_backed_visuals():
    source = structured_source_from_final_report(_report())
    source.sections = [section for section in source.sections if section.id != "visual_evidence"]
    for section in source.sections:
        section.blocks = [block for block in section.blocks if block.kind != "kpi_strip"]

    updated = apply_publication_remediation(
        source,
        [
            {
                "issue_code": "thin_visual_support",
                "severity": "major",
                "priority": 20,
                "action": "Add source-backed visuals.",
            }
        ],
    )

    visual_blocks = [
        block
        for section in updated.sections
        for block in section.blocks
        if block.kind in {"chart", "table", "kpi_strip"}
    ]
    assert len(visual_blocks) >= 2
    assert all(block.source_ids for block in visual_blocks)
    assert len(updated.versions) == len(source.versions) + 1

    projected = final_report_from_structured_source(_report(), updated)
    assert projected.charts or projected.tables or projected.key_numbers_highlight


def test_structured_source_tracks_scientific_connectors_explicitly():
    report = _report()
    report.all_sources = [
        Source(
            title="arXiv paper",
            url="https://arxiv.org/abs/1234.5678",
            tool="valyu/valyu-arxiv",
            reliability="high",
        ),
        Source(
            title="Clinical trial",
            url="https://clinicaltrials.gov/study/NCT00000000",
            tool="valyu/valyu-clinical-trials",
            reliability="high",
        ),
        Source(
            title="Semantic academic result",
            url="https://example.com/paper",
            tool="exa-semantic-academic",
            reliability="medium",
        ),
    ]
    report.metadata = {"detected_domain": "technical_research"}

    source = structured_source_from_final_report(report)

    assert source.research_coverage.connectors_used == [
        "valyu_arxiv",
        "valyu_clinical_trials",
        "exa_semantic",
    ]
    assert source.research_coverage.scientific_or_primary_connectors == [
        "valyu_arxiv",
        "valyu_clinical_trials",
        "exa_semantic",
    ]
    assert source.research_coverage.known_coverage_gaps == []
    assert run_enterprise_quality_gates(source).passed


def test_quality_gate_blocks_scientific_domain_without_paper_search():
    report = _report()
    report.all_sources = [
        Source(
            title="Manual market note",
            url="https://example.com/manual",
            tool="manual",
            reliability="medium",
        )
    ]
    report.metadata = {"detected_domain": "scientific"}
    source = structured_source_from_final_report(report)

    gate = run_enterprise_quality_gates(source)

    assert not gate.passed
    assert "missing_scientific_connector" in {issue.code for issue in gate.issues}
    assert source.research_coverage.known_coverage_gaps == [
        "scientific_or_paper_search_not_declared"
    ]


def _report() -> FinalReport:
    return FinalReport(
        session_id="enterprise-source",
        question="Оценить рынок первичного жилья Москвы на горизонте 2026-2027.",
        executive_summary=ExecutiveSummaryV4(
            main_answer=(
                "Базовый сценарий предполагает умеренный рост цен при высокой "
                "дифференциации между бизнес- и премиум-сегментами."
            ),
            top_findings=[
                "Ставка ЦБ остается главным ограничителем спроса.",
                "Премиум-сегмент сильнее зависит от наличных покупателей.",
            ],
            confidence_note="Уверенность средняя: часть проектных данных неполная.",
        ),
        main_synthesis=(
            "Рынок входит в 2026 год с разными траекториями по сегментам. "
            "Бизнес-класс чувствительнее к ипотеке, премиум сильнее связан с "
            "доходностью альтернативных активов и готовностью покупателей платить за локацию."
        ),
        consensus_section=(
            "Источники сходятся в том, что ставка и структура предложения будут "
            "определять краткосрочную динамику."
        ),
        conflicts_section=(
            "Расхождения касаются масштаба роста цен: консервативные оценки дают "
            "6-8%, оптимистичные выше 10%."
        ),
        gaps_filled_section=(
            "Остается проверить проектные продажи и фактические дисконты по крупным комплексам."
        ),
        all_sources=[
            Source(title="Valyu source", url="https://example.com/valyu", tool="valyu", reliability="high"),
            Source(title="Exa source", url="https://example.com/exa", tool="exa", reliability="medium"),
            Source(title="Manual source", url="https://example.com/manual", tool="", reliability="medium"),
        ],
        metadata={"detected_domain": "russian_market"},
        key_numbers_highlight=[
            KeyNumberHighlight(
                value="6-8%",
                label="медианный прогноз роста цен",
                source_ref="https://example.com/valyu",
                importance="headline",
            ),
            KeyNumberHighlight(
                value="13-14%",
                label="прогнозная ставка в 2026",
                source_ref="https://example.com/exa",
                importance="primary",
            ),
        ],
        charts=[
            ChartSpec(
                chart_type="bar",
                title="Разброс прогнозов роста цен",
                data={"points": [{"label": "Base", "value": 7}, {"label": "Upside", "value": 12}]},
                caption="Консенсусная таблица источников.",
            )
        ],
        tables=[
            Table(
                title="Сводка источников",
                columns=["Источник", "Вывод"],
                rows=[["Valyu", "Базовый рост"], ["Exa", "Ставка ограничивает спрос"]],
            )
        ],
    )
