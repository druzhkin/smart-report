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

from ...models import FinalReport, Source


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
    data: dict[str, Any] = Field(default_factory=dict)
    caption: str = ""
    source_ids: list[str] = Field(default_factory=list)


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
    return report


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
