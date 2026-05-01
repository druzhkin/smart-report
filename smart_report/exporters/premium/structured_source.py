"""Canonical editable source for enterprise report regeneration.

The rendered files are disposable artifacts. This module defines the durable
source that clients, analysts, and editors are allowed to change before the
DOCX/PDF/deck package is regenerated.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...models import ChartSpec, FinalReport, KeyNumberHighlight, Source, Table


class _EnterpriseBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ReportActorRole = Literal["analyst", "editor", "client_reviewer", "quality_reviewer"]
ReportBlockKind = Literal[
    "narrative",
    "bullets",
    "callout",
    "chart",
    "table",
    "kpi_strip",
    "source_note",
]
ReportEditOperation = Literal["replace", "append"]
ReportArtifactFormat = Literal["docx", "pdf", "pptx", "gamma_pptx", "html", "data_pack"]
QualityGateSeverity = Literal["critical", "major", "minor"]
ResearchConnector = Literal[
    "valyu",
    "valyu_arxiv",
    "valyu_pubmed",
    "valyu_biorxiv",
    "valyu_medrxiv",
    "valyu_clinical_trials",
    "exa",
    "exa_semantic",
    "tavily",
    "perplexity",
    "uploaded_source",
    "academic_upload",
    "manual_source",
]

SCIENTIFIC_CONNECTORS: set[ResearchConnector] = {
    "valyu",
    "valyu_arxiv",
    "valyu_pubmed",
    "valyu_biorxiv",
    "valyu_medrxiv",
    "valyu_clinical_trials",
    "exa",
    "exa_semantic",
    "academic_upload",
}

SCIENCE_REQUIRED_DOMAINS = {
    "academic",
    "biomedical",
    "clinical",
    "medical",
    "scientific",
    "technical_research",
}


DEFAULT_REGENERATION_FORMATS: tuple[ReportArtifactFormat, ...] = ("docx", "pdf", "pptx")

INTERNAL_CLIENT_MARKERS = (
    "[STRONG]",
    "[MODERATE]",
    "[WEAK]",
    "[SPECULATIVE]",
    "[REF:",
    "main_synthesis",
    "consensus_section",
    "conflicts_section",
    "gaps_filled_section",
    "source_reports",
    "followup_reports",
    "позиция автора",
    "результат синтеза",
)


class ReportSourceMetadata(_EnterpriseBase):
    report_id: str = Field(default_factory=lambda: f"report_{uuid.uuid4().hex[:12]}")
    title: str
    subtitle: str = ""
    client_name: str = ""
    language: str = "ru"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StructuredReportSourceRef(_EnterpriseBase):
    id: str = Field(default_factory=lambda: f"src_{uuid.uuid4().hex[:10]}")
    title: str
    url: str = ""
    connector: ResearchConnector = "manual_source"
    reliability: str = "medium"


class StructuredReportVisual(_EnterpriseBase):
    id: str = Field(default_factory=lambda: f"vis_{uuid.uuid4().hex[:10]}")
    title: str
    visual_type: str
    thesis: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    caption: str = ""
    source_ids: list[str] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    why_it_matters: str = ""


class StructuredReportBlock(_EnterpriseBase):
    id: str = Field(default_factory=lambda: f"block_{uuid.uuid4().hex[:10]}")
    kind: ReportBlockKind
    title: str = ""
    content: str = ""
    bullets: list[str] = Field(default_factory=list)
    visual: StructuredReportVisual | None = None
    table_columns: list[str] = Field(default_factory=list)
    table_rows: list[list[str]] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class StructuredReportSection(_EnterpriseBase):
    id: str
    title: str
    summary: str = ""
    blocks: list[StructuredReportBlock] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_is_slug_like(cls, value: str) -> str:
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("section id must be stable and slug-like")
        return value


class ResearchCoverage(_EnterpriseBase):
    declared_domain: str = "general"
    connectors_used: list[ResearchConnector] = Field(default_factory=list)
    scientific_or_primary_connectors: list[ResearchConnector] = Field(default_factory=list)
    known_coverage_gaps: list[str] = Field(default_factory=list)


class ReportVersionEntry(_EnterpriseBase):
    version_id: str = Field(default_factory=lambda: f"v_{uuid.uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor_role: ReportActorRole
    summary: str
    source_hash: str


class StructuredReportSource(_EnterpriseBase):
    metadata: ReportSourceMetadata
    sections: list[StructuredReportSection] = Field(default_factory=list)
    sources: list[StructuredReportSourceRef] = Field(default_factory=list)
    research_coverage: ResearchCoverage = Field(default_factory=ResearchCoverage)
    versions: list[ReportVersionEntry] = Field(default_factory=list)


class ReportEditRequest(_EnterpriseBase):
    actor_role: ReportActorRole
    operation: ReportEditOperation = "replace"
    target_path: str
    value: Any
    reason: str = ""


class ReportQualityGateIssue(_EnterpriseBase):
    code: str
    severity: QualityGateSeverity
    message: str
    recommendation: str = ""


class ReportQualityGateResult(_EnterpriseBase):
    passed: bool
    score: int
    issues: list[ReportQualityGateIssue] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReportRegenerationPlan(_EnterpriseBase):
    source_hash: str
    requested_formats: list[ReportArtifactFormat]
    default_word_artifact: ReportArtifactFormat = "docx"
    quality_gate: ReportQualityGateResult
    can_regenerate: bool


def structured_source_from_final_report(report: FinalReport) -> StructuredReportSource:
    """Convert the legacy FinalReport into the editable enterprise source."""

    source_refs = [
        StructuredReportSourceRef(
            title=source.title,
            url=source.url,
            connector=_connector_from_tool(source.tool),
            reliability=str(source.reliability or "medium"),
        )
        for source in report.all_sources
    ]
    source_ids = [source.id for source in source_refs]

    sections = [
        StructuredReportSection(
            id="executive_summary",
            title="Резюме для решения",
            summary=report.executive_summary.main_answer,
            blocks=[
                StructuredReportBlock(
                    kind="narrative",
                    title="Главный вывод",
                    content=report.executive_summary.main_answer,
                    source_ids=source_ids[:3],
                ),
                StructuredReportBlock(
                    kind="bullets",
                    title="Ключевые выводы",
                    bullets=list(report.executive_summary.top_findings),
                    source_ids=source_ids[:3],
                ),
            ],
        ),
        StructuredReportSection(
            id="market_storyline",
            title="Логика и доказательная база",
            summary=_first_sentence(report.main_synthesis),
            blocks=[
                StructuredReportBlock(
                    kind="narrative",
                    title="Развернутый анализ",
                    content=report.main_synthesis,
                    source_ids=source_ids[:6],
                )
            ],
        ),
        StructuredReportSection(
            id="consensus_and_tensions",
            title="Консенсус, расхождения и ограничения",
            summary=_first_sentence(report.consensus_section or report.conflicts_section),
            blocks=[
                StructuredReportBlock(
                    kind="narrative",
                    title="Где источники согласны",
                    content=report.consensus_section,
                    source_ids=source_ids[:6],
                ),
                StructuredReportBlock(
                    kind="narrative",
                    title="Где остаются расхождения",
                    content=report.conflicts_section,
                    source_ids=source_ids[:6],
                ),
                StructuredReportBlock(
                    kind="callout",
                    title="Что еще нужно проверять",
                    content=report.gaps_filled_section,
                    source_ids=source_ids[:6],
                ),
            ],
        ),
    ]

    if report.key_numbers_highlight:
        sections[0].blocks.append(
            StructuredReportBlock(
                kind="kpi_strip",
                title="Главные числа",
                bullets=[f"{item.value} — {item.label}" for item in report.key_numbers_highlight],
                source_ids=source_ids[:6],
            )
        )

    if report.charts:
        sections.append(
            StructuredReportSection(
                id="visual_evidence",
                title="Визуальные доказательства",
                summary="Графики и таблицы раскрывают числовые выводы, а не заменяют текст отчета.",
                blocks=[
                    StructuredReportBlock(
                        kind="chart",
                        title=chart.title,
                        content=chart.caption or "",
                        visual=StructuredReportVisual(
                            title=chart.title,
                            visual_type=chart.chart_type,
                            data=dict(chart.data or {}),
                            caption=chart.caption or "",
                            source_ids=source_ids[:3],
                        ),
                        source_ids=source_ids[:3],
                    )
                    for chart in report.charts
                ],
            )
        )

    if report.tables:
        sections.append(
            StructuredReportSection(
                id="tables",
                title="Табличные приложения",
                blocks=[
                    StructuredReportBlock(
                        kind="table",
                        title=table.title,
                        content=table.caption or "",
                        table_columns=list(table.columns),
                        table_rows=[list(row) for row in table.rows],
                        source_ids=source_ids[:3],
                    )
                    for table in report.tables
                ],
            )
        )

    source = StructuredReportSource(
        metadata=ReportSourceMetadata(
            title=_report_title(report),
            subtitle=report.question,
        ),
        sections=sections,
        sources=source_refs,
        research_coverage=_coverage_from_sources(source_refs, report.metadata),
    )
    return create_report_version(source, actor_role="analyst", summary="Initial structured source")


def final_report_from_structured_source(
    base_report: FinalReport,
    source: StructuredReportSource,
) -> FinalReport:
    """Project the editable source back into the legacy renderer contract.

    This keeps current DOCX/PDF/PPTX renderers useful while making the
    structured source authoritative for client-visible edits.
    """

    report = base_report.model_copy(deep=True)
    report.question = source.metadata.title or report.question
    report.metadata = {
        **dict(report.metadata or {}),
        "title": source.metadata.title,
        "subtitle": source.metadata.subtitle,
        "structured_source_hash": hash_structured_source(source),
        "structured_report_id": source.metadata.report_id,
    }

    executive = _section_by_id(source, "executive_summary")
    if executive:
        narrative = _first_block_text(executive, kind="narrative")
        bullets = _first_block_bullets(executive, kind="bullets")
        if narrative:
            report.executive_summary.main_answer = narrative
        if bullets:
            report.executive_summary.top_findings = bullets

    report.main_synthesis = _section_text(source, exclude_ids={"executive_summary"})
    consensus = _section_by_id(source, "consensus_and_tensions")
    if consensus:
        report.consensus_section = _block_text_by_title(consensus, "соглас")
        report.conflicts_section = _block_text_by_title(consensus, "расхожд")
        report.gaps_filled_section = _block_text_by_title(consensus, "провер")

    report.all_sources = [
        source_ref_to_final_source(source_ref) for source_ref in source.sources
    ]
    _project_structured_visuals(report, source)
    return report


def apply_publication_remediation(
    source: StructuredReportSource,
    remediation_plan: list[dict[str, Any]],
) -> StructuredReportSource:
    """Apply safe publication-quality remediation to the editable source.

    This function intentionally does not invent facts. It only adds structure,
    exhibit placeholders backed by existing source ids, and editorial scaffolds
    that tell the analyst/editor what evidence must be supplied.
    """

    updated = source.model_copy(deep=True)
    source_ids = [item.id for item in updated.sources]
    applied: list[str] = []
    for item in remediation_plan:
        issue_code = str(item.get("issue_code") or "")
        if issue_code in {
            "storyboard_visual_ratio_low",
            "storyboard_not_visual_early",
            "storyboard_missing_early_visual_types",
            "thin_visual_support",
        }:
            if _ensure_evidence_visuals(updated, source_ids, issue_code=issue_code):
                applied.append(issue_code)
        elif issue_code in {
            "storyboard_visual_sources_weak",
            "storyboard_page_visual_without_source",
        }:
            if _attach_missing_visual_sources(updated, source_ids):
                applied.append(issue_code)
        elif issue_code in {"storyboard_page_narrative_too_thin", "thin_narrative"}:
            if _expand_thin_narratives(updated, source_ids):
                applied.append(issue_code)
        elif issue_code == "storyboard_page_implication_too_thin":
            if _ensure_implication_callouts(updated, source_ids):
                applied.append(issue_code)

    updated.metadata.updated_at = datetime.now(UTC)
    summary = (
        "Applied publication remediation: " + ", ".join(sorted(set(applied)))
        if applied
        else "Publication remediation inspected; no safe automatic edits applied"
    )
    return create_report_version(updated, actor_role="editor", summary=summary)


def apply_report_edits(
    source: StructuredReportSource,
    edits: list[ReportEditRequest],
) -> StructuredReportSource:
    """Apply client/editor edits to the structured source and return a copy."""

    updated = source.model_copy(deep=True)
    for edit in edits:
        if not _role_can_edit(edit.actor_role):
            raise PermissionError(f"role {edit.actor_role!r} cannot edit report content")
        _apply_single_edit(updated, edit)
    updated.metadata.updated_at = datetime.now(UTC)
    actor = edits[-1].actor_role if edits else "editor"
    summary = "; ".join(edit.reason or edit.target_path for edit in edits) or "Structured edit"
    return create_report_version(updated, actor_role=actor, summary=summary)


def build_regeneration_plan(
    source: StructuredReportSource,
    *,
    requested_formats: list[ReportArtifactFormat] | None = None,
) -> ReportRegenerationPlan:
    formats = _normalize_formats(requested_formats)
    gate = run_enterprise_quality_gates(source, requested_formats=formats)
    return ReportRegenerationPlan(
        source_hash=hash_structured_source(source),
        requested_formats=formats,
        quality_gate=gate,
        can_regenerate=gate.passed,
    )


def run_enterprise_quality_gates(
    source: StructuredReportSource,
    *,
    requested_formats: list[ReportArtifactFormat] | None = None,
) -> ReportQualityGateResult:
    formats = _normalize_formats(requested_formats)
    issues: list[ReportQualityGateIssue] = []

    if not source.metadata.title:
        issues.append(_issue("missing_title", "critical", "Report title is required."))
    if len(source.sections) < 3:
        issues.append(_issue("too_few_sections", "critical", "Report needs at least 3 sections."))
    if "docx" not in formats:
        issues.append(
            _issue(
                "missing_default_docx",
                "critical",
                "DOCX must be generated by default because it is the editable client artifact.",
            )
        )
    if not source.sources:
        issues.append(_issue("missing_sources", "critical", "Report has no source registry."))
    if not source.research_coverage.connectors_used:
        issues.append(
            _issue(
                "missing_research_coverage",
                "major",
                "Research connector coverage is not declared.",
                "Record whether Valyu, Exa, Tavily, Perplexity, uploads, or manual sources were used.",
            )
        )
    if _requires_scientific_connector(source.research_coverage) and not source.research_coverage.scientific_or_primary_connectors:
        issues.append(
            _issue(
                "missing_scientific_connector",
                "major",
                "Report domain requires paper or scientific search coverage, but none is declared.",
                "Use Valyu arXiv/PubMed/bioRxiv/medRxiv, Exa semantic academic search, or upload academic sources.",
            )
        )

    text = _client_text(source)
    for marker in INTERNAL_CLIENT_MARKERS:
        if marker.lower() in text.lower():
            issues.append(
                _issue(
                    "internal_marker_leak",
                    "critical",
                    f"Client-facing source contains internal marker: {marker}",
                    "Clean the structured source before regeneration.",
                )
            )
            break

    narrative_blocks = [
        block
        for section in source.sections
        for block in section.blocks
        if block.kind in {"narrative", "bullets", "callout"} and _block_has_text(block)
    ]
    visual_blocks = [
        block
        for section in source.sections
        for block in section.blocks
        if block.kind in {"chart", "table", "kpi_strip"} and _block_has_visual_payload(block)
    ]
    if len(narrative_blocks) < 4:
        issues.append(
            _issue(
                "thin_narrative",
                "major",
                "Report has too little authored text for publication-grade output.",
            )
        )
    if len(visual_blocks) < 2:
        issues.append(
            _issue(
                "thin_visual_support",
                "major",
                "Report needs multiple charts, tables, or KPI blocks to support the text.",
            )
        )
    if not source.versions:
        issues.append(_issue("missing_version_history", "major", "Report source has no version history."))

    score = max(0, 100 - sum(25 if item.severity == "critical" else 12 for item in issues))
    return ReportQualityGateResult(passed=not issues, score=score, issues=issues)


def create_report_version(
    source: StructuredReportSource,
    *,
    actor_role: ReportActorRole,
    summary: str,
) -> StructuredReportSource:
    updated = source.model_copy(deep=True)
    updated.versions.append(
        ReportVersionEntry(
            actor_role=actor_role,
            summary=summary,
            source_hash=hash_structured_source(updated, include_versions=False),
        )
    )
    return updated


def hash_structured_source(source: StructuredReportSource, *, include_versions: bool = True) -> str:
    payload = source.model_dump(mode="json")
    if not include_versions:
        payload["versions"] = []
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def source_ref_to_final_source(source_ref: StructuredReportSourceRef) -> Source:
    return Source(
        title=source_ref.title,
        url=source_ref.url,
        tool=source_ref.connector,
        reliability=source_ref.reliability if source_ref.reliability else "medium",
    )


def _project_structured_visuals(report: FinalReport, source: StructuredReportSource) -> None:
    charts = list(report.charts)
    tables = list(report.tables)
    key_numbers = list(report.key_numbers_highlight)
    existing_chart_titles = {chart.title for chart in charts}
    existing_table_titles = {table.title for table in tables}
    existing_key_labels = {item.label for item in key_numbers}
    source_lookup = {item.id: item for item in source.sources}

    for section in source.sections:
        for block in section.blocks:
            source_ref = _source_ref_for_block(block, source_lookup)
            if block.kind == "kpi_strip":
                for bullet in block.bullets[:6]:
                    value, label = _split_kpi_bullet(bullet)
                    if label in existing_key_labels:
                        continue
                    key_numbers.append(
                        KeyNumberHighlight(
                            value=value,
                            label=label,
                            source_ref=source_ref,
                            importance="secondary",
                        )
                    )
                    existing_key_labels.add(label)
            elif block.kind == "chart" and block.visual:
                if block.visual.title in existing_chart_titles:
                    continue
                charts.append(
                    ChartSpec(
                        chart_type=_chart_type_for_visual(block.visual.visual_type),
                        title=block.visual.title,
                        data=block.visual.data or _chart_data_from_sources(block, source_lookup),
                        caption=_visual_caption(block, section),
                    )
                )
                existing_chart_titles.add(block.visual.title)
            elif block.kind == "table":
                if block.title in existing_table_titles:
                    continue
                tables.append(
                    Table(
                        title=block.title or section.title,
                        columns=block.table_columns or ["Показатель", "Значение"],
                        rows=block.table_rows
                        or [["Требуется заполнение", block.content or section.summary]],
                        caption=block.content or None,
                        source_ref=source_ref,
                    )
                )
                existing_table_titles.add(block.title)

    report.charts = charts
    report.tables = tables
    report.key_numbers_highlight = key_numbers


def _apply_single_edit(source: StructuredReportSource, edit: ReportEditRequest) -> None:
    path = edit.target_path.split(".")
    if edit.target_path in {"title", "metadata.title"}:
        source.metadata.title = str(edit.value)
        return
    if edit.target_path in {"subtitle", "metadata.subtitle"}:
        source.metadata.subtitle = str(edit.value)
        return
    if len(path) < 3 or path[0] != "sections":
        raise ValueError(f"unsupported edit target path: {edit.target_path}")

    section = _find_section(source, path[1])
    if len(path) == 3 and path[2] in {"title", "summary"}:
        setattr(section, path[2], str(edit.value))
        return
    if len(path) < 5 or path[2] != "blocks":
        raise ValueError(f"unsupported edit target path: {edit.target_path}")

    block = _find_block(section, path[3])
    field = path[4]
    if field == "content":
        block.content = _append_or_replace(block.content, str(edit.value), edit.operation)
    elif field == "title":
        block.title = str(edit.value)
    elif field == "bullets":
        values = [str(item) for item in edit.value] if isinstance(edit.value, list) else [str(edit.value)]
        block.bullets = [*block.bullets, *values] if edit.operation == "append" else values
    else:
        raise ValueError(f"unsupported block edit field: {field}")


def _ensure_evidence_visuals(
    source: StructuredReportSource,
    source_ids: list[str],
    *,
    issue_code: str,
) -> bool:
    section = _ensure_section(
        source,
        "visual_evidence",
        "Визуальные доказательства",
        "Визуалы раскрывают ключевые выводы и показывают, на каких источниках они основаны.",
    )
    changed = False
    visual_count = sum(
        1
        for item in source.sections
        for block in item.blocks
        if block.kind in {"chart", "table", "kpi_strip"} and _block_has_visual_payload(block)
    )
    if visual_count < 1:
        section.blocks.append(
            StructuredReportBlock(
                kind="kpi_strip",
                title="Ключевые доказательства",
                bullets=[
                    f"{len(source.sources)} источн. — база отчета",
                    (
                        f"{len(source.research_coverage.connectors_used)} коннект. "
                        "— покрытие исследования"
                    ),
                ],
                source_ids=source_ids[:3],
            )
        )
        visual_count += 1
        changed = True
    if visual_count < 2:
        section.blocks.append(
            StructuredReportBlock(
                kind="chart",
                title="Качество доказательной базы",
                content=(
                    "Показывает состав источников, использованных в отчете. "
                    "Не заменяет фактологический анализ, а фиксирует прозрачность evidence base."
                ),
                visual=StructuredReportVisual(
                    title="Качество доказательной базы",
                    visual_type="evidence_quality",
                    thesis="Отчет должен показывать не только выводы, но и качество доказательной базы.",
                    data=_source_mix_data(source),
                    caption="Распределение источников по уровню надежности и коннекторам.",
                    source_ids=source_ids[:6],
                    source_notes=_source_notes_for_ids(source, source_ids[:6]),
                    why_it_matters=(
                        "Читатель видит, насколько выводы опираются на проверяемые источники, "
                        "а не на неподтвержденный нарратив."
                    ),
                ),
                source_ids=source_ids[:6],
            )
        )
        visual_count += 1
        changed = True
    if visual_count < 3 and source.sources:
        section.blocks.append(
            StructuredReportBlock(
                kind="table",
                title="Реестр источников для проверки",
                content="Таблица нужна для быстрой проверки доказательной базы перед публикацией.",
                table_columns=["Источник", "Коннектор", "Надежность"],
                table_rows=[
                    [item.title, item.connector, item.reliability]
                    for item in source.sources[:8]
                ],
                source_ids=source_ids[:8],
            )
        )
        changed = True
    if issue_code == "storyboard_missing_early_visual_types":
        changed = _ensure_required_exhibit_mix(source, section, source_ids) or changed
    return changed


def _ensure_required_exhibit_mix(
    source: StructuredReportSource,
    section: StructuredReportSection,
    source_ids: list[str],
) -> bool:
    changed = False
    existing_types = {
        block.visual.visual_type
        for item in source.sections
        for block in item.blocks
        if block.visual
    }
    if "ranking_bar" not in existing_types:
        section.blocks.append(
            StructuredReportBlock(
                kind="chart",
                title="Ранжирование ключевых факторов",
                content="Сравнивает факторы, которые поддерживают главный вывод отчета.",
                visual=StructuredReportVisual(
                    title="Ранжирование ключевых факторов",
                    visual_type="ranking_bar",
                    thesis="Главный вывод должен быть разложен на сравнимые факторы.",
                    data=_ranking_data_from_source(source),
                    caption="Ранжирование построено по структуре выводов отчета и требует редакционной проверки весов.",
                    source_ids=source_ids[:6],
                    source_notes=_source_notes_for_ids(source, source_ids[:6]),
                    why_it_matters="Ранжирование помогает читателю понять, что действительно влияет на решение.",
                ),
                source_ids=source_ids[:6],
            )
        )
        changed = True
    if "risk_heatmap" not in existing_types:
        section.blocks.append(
            StructuredReportBlock(
                kind="table",
                title="Карта рисков и пробелов",
                content="Фиксирует слабые места доказательной базы, которые нельзя скрывать в публикации.",
                table_columns=["Риск", "Влияние", "Что проверить"],
                table_rows=_risk_rows_from_source(source),
                source_ids=source_ids[:6],
            )
        )
        changed = True
    return changed


def _attach_missing_visual_sources(source: StructuredReportSource, source_ids: list[str]) -> bool:
    if not source_ids:
        return False
    changed = False
    for section in source.sections:
        for block in section.blocks:
            if block.kind not in {"chart", "table", "kpi_strip"}:
                continue
            if not block.source_ids:
                block.source_ids = source_ids[:3]
                changed = True
            if block.visual and not block.visual.source_ids:
                block.visual.source_ids = block.source_ids or source_ids[:3]
                changed = True
            if block.visual and not block.visual.source_notes:
                block.visual.source_notes = _source_notes_for_ids(source, block.visual.source_ids)
                changed = True
    return changed


def _expand_thin_narratives(source: StructuredReportSource, source_ids: list[str]) -> bool:
    changed = False
    for section in source.sections:
        if len(section.summary.strip()) < 80:
            section.summary = _append_or_replace(
                section.summary,
                (
                    "Редакторская заготовка: раздел должен связать тезис, доказательство "
                    "и управленческий вывод. Перед публикацией подтвердите формулировку "
                    "источниками."
                ),
                "append",
            )
            changed = True
        for block in section.blocks:
            if block.kind in {"narrative", "callout"} and len(block.content.strip()) < 120:
                block.content = _append_or_replace(
                    block.content,
                    (
                        "Редакторская заготовка: добавьте интерпретацию фактов, "
                        "объясните механизм влияния и укажите, какие источники "
                        "подтверждают вывод."
                    ),
                    "append",
                )
                if not block.source_ids:
                    block.source_ids = source_ids[:3]
                changed = True
    return changed


def _ensure_implication_callouts(source: StructuredReportSource, source_ids: list[str]) -> bool:
    changed = False
    for section in source.sections:
        has_implication = any(
            block.kind == "callout" and "вывод" in block.title.lower()
            for block in section.blocks
        )
        if has_implication:
            continue
        section.blocks.append(
            StructuredReportBlock(
                kind="callout",
                title="Управленческий вывод",
                content=(
                    "Перед публикацией сформулируйте, какое решение, риск или следующий "
                    "шаг следует из доказательств этого раздела."
                ),
                source_ids=source_ids[:3],
            )
        )
        changed = True
    return changed


def _ensure_section(
    source: StructuredReportSource,
    section_id: str,
    title: str,
    summary: str,
) -> StructuredReportSection:
    existing = _section_by_id(source, section_id)
    if existing:
        return existing
    section = StructuredReportSection(id=section_id, title=title, summary=summary)
    source.sections.append(section)
    return section


def _source_mix_data(source: StructuredReportSource) -> dict[str, Any]:
    reliability_counts: dict[str, int] = {}
    connector_counts: dict[str, int] = {}
    for item in source.sources:
        reliability_counts[item.reliability] = reliability_counts.get(item.reliability, 0) + 1
        connector_counts[item.connector] = connector_counts.get(item.connector, 0) + 1
    return {
        "reliability": [
            {"label": key, "value": value}
            for key, value in sorted(reliability_counts.items())
        ],
        "connectors": [
            {"label": key, "value": value}
            for key, value in sorted(connector_counts.items())
        ],
    }


def _source_notes_for_ids(source: StructuredReportSource, source_ids: list[str]) -> list[str]:
    lookup = {item.id: item for item in source.sources}
    notes: list[str] = []
    for source_id in source_ids:
        source_ref = lookup.get(source_id)
        if not source_ref:
            continue
        label = source_ref.title
        if source_ref.url:
            label = f"{label}: {source_ref.url}"
        notes.append(label)
    return notes


def _ranking_data_from_source(source: StructuredReportSource) -> dict[str, Any]:
    executive = _section_by_id(source, "executive_summary")
    bullets: list[str] = []
    if executive:
        for block in executive.blocks:
            bullets.extend(block.bullets)
    points = [
        {"label": _compact_label(item), "value": max(1, 6 - index)}
        for index, item in enumerate(bullets[:5], start=1)
    ]
    if not points:
        points = [{"label": section.title[:48], "value": 1} for section in source.sections[:5]]
    return {"points": points}


def _risk_rows_from_source(source: StructuredReportSource) -> list[list[str]]:
    gaps = list(source.research_coverage.known_coverage_gaps)
    if not gaps:
        gaps = ["Проверить полноту источников и числовых фактов перед публикацией"]
    return [
        [gap, "Среднее/высокое", "Закрыть источником или явно оставить как ограничение"]
        for gap in gaps[:6]
    ]


def _compact_label(text: str) -> str:
    clean = " ".join(str(text or "").split())
    return clean[:64] + ("..." if len(clean) > 64 else "")


def _normalize_formats(
    requested_formats: list[ReportArtifactFormat] | None,
) -> list[ReportArtifactFormat]:
    formats = list(requested_formats or DEFAULT_REGENERATION_FORMATS)
    if "docx" not in formats:
        formats.insert(0, "docx")
    return list(dict.fromkeys(formats))


def _role_can_edit(role: ReportActorRole) -> bool:
    return role in {"analyst", "editor", "client_reviewer"}


def _find_section(source: StructuredReportSource, section_id: str) -> StructuredReportSection:
    for section in source.sections:
        if section.id == section_id:
            return section
    raise ValueError(f"unknown section id: {section_id}")


def _find_block(section: StructuredReportSection, block_id: str) -> StructuredReportBlock:
    for block in section.blocks:
        if block.id == block_id:
            return block
    raise ValueError(f"unknown block id: {block_id}")


def _section_by_id(
    source: StructuredReportSource,
    section_id: str,
) -> StructuredReportSection | None:
    for section in source.sections:
        if section.id == section_id:
            return section
    return None


def _first_block_text(section: StructuredReportSection, *, kind: ReportBlockKind) -> str:
    for block in section.blocks:
        if block.kind == kind and block.content:
            return block.content
    return ""


def _first_block_bullets(section: StructuredReportSection, *, kind: ReportBlockKind) -> list[str]:
    for block in section.blocks:
        if block.kind == kind and block.bullets:
            return list(block.bullets)
    return []


def _block_text_by_title(section: StructuredReportSection, title_fragment: str) -> str:
    needle = title_fragment.lower()
    for block in section.blocks:
        if needle in block.title.lower() and block.content:
            return block.content
    return ""


def _section_text(
    source: StructuredReportSource,
    *,
    exclude_ids: set[str],
) -> str:
    chunks: list[str] = []
    for section in source.sections:
        if section.id in exclude_ids:
            continue
        if section.summary:
            chunks.append(f"## {section.title}\n\n{section.summary}")
        for block in section.blocks:
            body = block.content
            if block.bullets:
                bullet_text = "\n".join(f"- {item}" for item in block.bullets)
                body = f"{body}\n{bullet_text}".strip()
            if body:
                heading = block.title or section.title
                chunks.append(f"### {heading}\n\n{body}")
    return "\n\n".join(chunks).strip()


def _append_or_replace(old: str, new: str, operation: ReportEditOperation) -> str:
    if operation == "append" and old:
        return f"{old.rstrip()}\n\n{new.lstrip()}"
    return new


def _issue(
    code: str,
    severity: QualityGateSeverity,
    message: str,
    recommendation: str = "",
) -> ReportQualityGateIssue:
    return ReportQualityGateIssue(
        code=code,
        severity=severity,
        message=message,
        recommendation=recommendation,
    )


def _client_text(source: StructuredReportSource) -> str:
    parts = [source.metadata.title, source.metadata.subtitle]
    for section in source.sections:
        parts.extend([section.title, section.summary])
        for block in section.blocks:
            parts.extend([block.title, block.content, *block.bullets])
            if block.visual:
                parts.extend([block.visual.title, block.visual.caption])
    return "\n".join(part for part in parts if part)


def _block_has_text(block: StructuredReportBlock) -> bool:
    return bool(block.content.strip() or any(item.strip() for item in block.bullets))


def _block_has_visual_payload(block: StructuredReportBlock) -> bool:
    return bool(
        block.visual
        or block.table_rows
        or block.table_columns
        or (block.kind == "kpi_strip" and block.bullets)
    )


def _source_ref_for_block(
    block: StructuredReportBlock,
    source_lookup: dict[str, StructuredReportSourceRef],
) -> str:
    for source_id in [*block.source_ids, *(block.visual.source_ids if block.visual else [])]:
        source = source_lookup.get(source_id)
        if source:
            return source.url or source.title
    return ""


def _visual_caption(
    block: StructuredReportBlock,
    section: StructuredReportSection,
) -> str | None:
    if not block.visual:
        return block.content or section.summary or None
    parts = [
        block.visual.caption,
        block.visual.why_it_matters,
        block.content,
        section.summary,
    ]
    return " ".join(part.strip() for part in parts if part and part.strip()) or None


def _split_kpi_bullet(text: str) -> tuple[str, str]:
    clean = " ".join(str(text or "").split())
    if "—" in clean:
        value, label = clean.split("—", 1)
        return value.strip() or clean, label.strip() or clean
    if "-" in clean:
        value, label = clean.split("-", 1)
        return value.strip() or clean, label.strip() or clean
    return clean[:24] or "n/a", clean


def _chart_type_for_visual(
    visual_type: str,
) -> Literal["bar", "line", "pie", "scatter", "stacked_bar", "waterfall"]:
    normalized = str(visual_type or "").lower()
    if "time" in normalized or "line" in normalized:
        return "line"
    if "waterfall" in normalized:
        return "waterfall"
    if "pie" in normalized:
        return "pie"
    if "scatter" in normalized:
        return "scatter"
    if "stack" in normalized:
        return "stacked_bar"
    return "bar"


def _chart_data_from_sources(
    block: StructuredReportBlock,
    source_lookup: dict[str, StructuredReportSourceRef],
) -> dict[str, Any]:
    rows = []
    for source_id in block.source_ids[:8]:
        source = source_lookup.get(source_id)
        if source:
            rows.append({"label": source.connector, "value": 1})
    return {"points": rows or [{"label": "sources", "value": len(source_lookup)}]}


def _report_title(report: FinalReport) -> str:
    title = str(report.metadata.get("title") or "").strip()
    if title:
        return title
    return _first_sentence(report.executive_summary.main_answer) or report.question


def _first_sentence(text: str) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return ""
    return re.split(r"(?<=[.!?])\s+", clean, maxsplit=1)[0]


def _connector_from_tool(tool: str) -> ResearchConnector:
    value = str(tool or "").lower()
    normalized = value.replace("-", "_").replace("/", "_")
    if "pubmed" in normalized:
        return "valyu_pubmed"
    if "clinical_trials" in normalized or "clinicaltrials" in normalized:
        return "valyu_clinical_trials"
    if "medrxiv" in normalized:
        return "valyu_medrxiv"
    if "biorxiv" in normalized or "bio_rxiv" in normalized:
        return "valyu_biorxiv"
    if "arxiv" in normalized or "ar_xiv" in normalized:
        return "valyu_arxiv"
    if "exa" in normalized and ("semantic" in normalized or "academic" in normalized):
        return "exa_semantic"
    if "academic" in normalized and ("upload" in normalized or "manual" in normalized):
        return "academic_upload"
    for connector in ("valyu", "exa", "tavily", "perplexity"):
        if connector in value:
            return connector  # type: ignore[return-value]
    if "upload" in value:
        return "uploaded_source"
    return "manual_source"


def _coverage_from_sources(
    sources: list[StructuredReportSourceRef],
    metadata: dict[str, Any],
) -> ResearchCoverage:
    connectors = list(dict.fromkeys(source.connector for source in sources))
    scientific = [item for item in connectors if item in SCIENTIFIC_CONNECTORS]
    domain = str(metadata.get("detected_domain") or metadata.get("domain") or "general")
    gaps: list[str] = []
    if _domain_requires_scientific_connector(domain) and not scientific:
        gaps.append("scientific_or_paper_search_not_declared")
    return ResearchCoverage(
        declared_domain=domain,
        connectors_used=connectors,
        scientific_or_primary_connectors=scientific,
        known_coverage_gaps=gaps,
    )


def _requires_scientific_connector(coverage: ResearchCoverage) -> bool:
    return _domain_requires_scientific_connector(coverage.declared_domain)


def _domain_requires_scientific_connector(domain: str) -> bool:
    normalized = str(domain or "").lower().replace("-", "_").replace(" ", "_")
    return any(marker in normalized for marker in SCIENCE_REQUIRED_DOMAINS)
