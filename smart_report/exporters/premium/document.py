"""Assemble a renderer-neutral premium report document.

The document assembler reuses the existing v4 analytical layer instead of
replacing it: executive answer, consensus, conflicts, gaps, numeric facts,
sources, bibliography, tables, charts, and metadata all flow into a richer
section/block structure. Renderers can target DOCX/PDF/PPTX later without
needing topic-specific logic.
"""

from __future__ import annotations

from ...models import AnalysisOutput, FinalReport, NumericFact
from .models import (
    PremiumBlockKind,
    PremiumDeckSlideSpec,
    PremiumPreparedBlock,
    PremiumPreparedSection,
    PremiumReportDocument,
    PremiumReportPlan,
    PremiumSectionSpec,
)
from .planner import build_premium_report_plan


def assemble_premium_report_document(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
    plan: PremiumReportPlan | None = None,
    premium_readiness: dict[str, object] | None = None,
) -> PremiumReportDocument:
    """Create a universal premium report/deck content model.

    This function is side-effect free and intentionally does not call legacy
    exporters. It prepares content that a future renderer can lay out with a
    premium visual system.
    """

    plan = plan or build_premium_report_plan(report, analysis=analysis)
    sections = [
        _section_from_spec(spec, report=report, analysis=analysis)
        for spec in plan.sections
        if spec.id != "appendix"
    ]
    appendices = _appendix_sections(report, analysis=analysis)
    deck_slides = _deck_slides(plan)
    numeric_facts = _numeric_facts(analysis)

    return PremiumReportDocument(
        title=_title_for(report),
        subtitle=_subtitle_for(plan),
        plan=plan,
        sections=sections,
        appendices=appendices,
        deck_slides=deck_slides,
        source_count=len(report.all_sources or []),
        numeric_fact_count=len(numeric_facts),
        premium_readiness=premium_readiness,
    )


def _section_from_spec(
    spec: PremiumSectionSpec,
    *,
    report: FinalReport,
    analysis: AnalysisOutput | None,
) -> PremiumPreparedSection:
    blocks: list[PremiumPreparedBlock] = []
    blocks.extend(_blocks_for_section(spec, report=report, analysis=analysis))
    if not blocks:
        blocks.append(
            PremiumPreparedBlock(
                kind="narrative",
                title=spec.title,
                body=_fallback_body_for(spec, report),
            )
        )
    return PremiumPreparedSection(
        id=spec.id,
        title=spec.title,
        purpose=spec.purpose,
        min_pages=spec.min_pages,
        blocks=blocks,
    )


def _blocks_for_section(
    spec: PremiumSectionSpec,
    *,
    report: FinalReport,
    analysis: AnalysisOutput | None,
) -> list[PremiumPreparedBlock]:
    if spec.id == "executive_summary":
        return [
            PremiumPreparedBlock(
                kind="narrative",
                title="Answer",
                body=report.executive_summary.main_answer,
            ),
            _kpi_grid(report, analysis),
            _decision_matrix(report),
        ]
    if spec.id == "question_framing":
        return [
            PremiumPreparedBlock(
                kind="methodology_box",
                title="Scope and decision context",
                body=report.question,
                notes=[
                    "The premium document must separate verified facts, interpretation, and recommendations.",
                    "Limitations and unavailable data are explicit deliverable components.",
                ],
            )
        ]
    if spec.id == "evidence_base":
        return [_evidence_table(analysis), _source_quality_table(report)]
    if spec.id in {"market_baseline", "current_state", "context", "target_profile"}:
        return [
            PremiumPreparedBlock(
                kind="narrative",
                title="Baseline synthesis",
                body=report.main_synthesis,
            ),
            _timeline_block(report),
        ]
    if spec.id in {"demand_supply", "analysis", "capability_benchmark"}:
        return [_consensus_table(analysis), _conflicts_table(analysis)]
    if spec.id in {"scenarios", "strategic_options", "valuation_and_exit"}:
        return [_scenario_matrix(report), _sensitivity_table(analysis)]
    if spec.id in {"findings", "diligence_findings", "risk_interpretation"}:
        return [_conflicts_table(analysis), _risk_register(report, analysis)]
    if spec.id in {"recommendations", "risk_adjusted_decision", "go_no_go"}:
        return [_decision_matrix(report), _risk_register(report, analysis)]
    if spec.id in {"risks_and_monitoring", "roadmap", "remediation", "compliance_actions"}:
        return [_risk_register(report, analysis), _timeline_block(report)]
    if spec.id in {"competitive_landscape", "strategic_moves"}:
        return [_generic_matrix("Competitive / option matrix", "competitive_matrix", analysis)]
    if spec.id in {"investment_thesis", "asset_or_target_profile", "system_map", "regulatory_baseline"}:
        return [_kpi_grid(report, analysis), _evidence_table(analysis)]
    return []


def _kpi_grid(report: FinalReport, analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows: list[list[str]] = []
    for number in report.executive_summary.key_numbers:
        rows.append([number.metric, number.value, number.subject, number.source_url])
    for fact in _numeric_facts(analysis)[:8]:
        rows.append([fact.metric, fact.value, fact.subject, _first_fact_source(fact)])
    return PremiumPreparedBlock(
        kind="kpi_grid",
        title="Key metrics",
        columns=["Metric", "Value", "Subject", "Source"],
        rows=rows,
        notes=["Empty rows mean the upstream analyzer did not provide enough numeric facts."],
    )


def _evidence_table(analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows = [
        [
            fact.fact_id,
            fact.value,
            fact.metric,
            fact.subject,
            fact.timeframe or "",
            fact.relevance_to_question,
            _first_fact_source(fact),
        ]
        for fact in _numeric_facts(analysis)[:30]
    ]
    return PremiumPreparedBlock(
        kind="evidence_table",
        title="Numeric evidence register",
        columns=["ID", "Value", "Metric", "Subject", "Timeframe", "Relevance", "Source"],
        rows=rows,
    )


def _source_quality_table(report: FinalReport) -> PremiumPreparedBlock:
    rows = [
        [source.title, source.url, source.tool, source.reliability]
        for source in (report.all_sources or [])
    ]
    return PremiumPreparedBlock(
        kind="source_quality_table",
        title="Source quality register",
        columns=["Source", "URL", "Tool", "Reliability"],
        rows=rows,
    )


def _consensus_table(analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows = []
    if analysis is not None:
        rows = [
            [claim.claim, claim.confidence, ", ".join(claim.supporting_sources)]
            for claim in analysis.consensus
        ]
    return PremiumPreparedBlock(
        kind="evidence_table",
        title="Consensus claims",
        columns=["Claim", "Confidence", "Supporting sources"],
        rows=rows,
    )


def _conflicts_table(analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows = []
    if analysis is not None:
        rows = [
            [
                conflict.topic,
                conflict.source_a,
                conflict.claim_a,
                conflict.source_b,
                conflict.claim_b,
                conflict.importance,
                conflict.resolution_hint,
            ]
            for conflict in analysis.conflicts
        ]
    return PremiumPreparedBlock(
        kind="evidence_table",
        title="Conflicts and divergent claims",
        columns=["Topic", "Source A", "Claim A", "Source B", "Claim B", "Importance", "Resolution"],
        rows=rows,
    )


def _scenario_matrix(report: FinalReport) -> PremiumPreparedBlock:
    rows = [
        ["Base", "Most likely interpretation of the evidence", report.executive_summary.main_answer],
        ["Upside", "Conditions that improve the answer", "See recommendations and monitoring triggers."],
        ["Downside", "Conditions that invalidate the answer", "See risk register and open limitations."],
    ]
    return PremiumPreparedBlock(
        kind="scenario_matrix",
        title="Scenario matrix",
        columns=["Scenario", "Definition", "Implication"],
        rows=rows,
    )


def _sensitivity_table(analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    variables = []
    if analysis is not None:
        variables.extend(fact.metric for fact in analysis.high_relevance_facts[:8])
    rows = [[variable, "Lower case", "Base case", "Higher case"] for variable in variables]
    return PremiumPreparedBlock(
        kind="sensitivity_table",
        title="Sensitivity framework",
        columns=["Driver", "Downside movement", "Base assumption", "Upside movement"],
        rows=rows,
        notes=["Renderer/model layer can fill numeric deltas when source data supports it."],
    )


def _decision_matrix(report: FinalReport) -> PremiumPreparedBlock:
    findings = report.executive_summary.top_findings or []
    rows = [
        ["Proceed", "Evidence supports action", findings[0] if findings else report.executive_summary.main_answer],
        ["Wait", "Key trigger not met", report.gaps_filled_section or "Open questions remain."],
        ["Reject / redesign", "Critical risk becomes binding", report.conflicts_section or "No critical conflict stated."],
    ]
    return PremiumPreparedBlock(
        kind="decision_matrix",
        title="Decision matrix",
        columns=["Action", "Condition", "Rationale"],
        rows=rows,
    )


def _risk_register(report: FinalReport, analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows: list[list[str]] = []
    if analysis is not None:
        rows.extend(
            [gap.topic, "Evidence gap", gap.why_critical, gap.what_to_find]
            for gap in analysis.gaps
        )
        rows.extend(
            [
                conflict.topic,
                f"Conflict: {conflict.importance}",
                conflict.claim_a,
                conflict.resolution_hint,
            ]
            for conflict in analysis.conflicts
        )
    if report.gaps_filled_section and not rows:
        rows.append(["Open limitation", "Gap", report.gaps_filled_section, "Track before decision."])
    return PremiumPreparedBlock(
        kind="risk_register",
        title="Risk register",
        columns=["Risk / topic", "Type", "Why it matters", "Mitigation / monitoring"],
        rows=rows,
    )


def _timeline_block(report: FinalReport) -> PremiumPreparedBlock:
    return PremiumPreparedBlock(
        kind="timeline",
        title="Monitoring timeline",
        columns=["Stage", "What to check", "Why"],
        rows=[
            ["Now", "Verify source coverage and unresolved gaps", "Avoid false precision."],
            ["Next update", "Refresh key facts and triggers", "Detect scenario change."],
            ["Decision point", "Apply decision matrix", "Convert analysis into action."],
        ],
        notes=[report.executive_summary.confidence_note] if report.executive_summary.confidence_note else [],
    )


def _generic_matrix(
    title: str,
    kind: PremiumBlockKind,
    analysis: AnalysisOutput | None,
) -> PremiumPreparedBlock:
    rows = []
    if analysis is not None:
        rows = [[claim.claim, claim.confidence, ", ".join(claim.supporting_sources)] for claim in analysis.consensus]
    return PremiumPreparedBlock(
        kind=kind,
        title=title,
        columns=["Dimension", "Assessment", "Evidence"],
        rows=rows,
    )


def _appendix_sections(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None,
) -> list[PremiumPreparedSection]:
    return [
        PremiumPreparedSection(
            id="appendix_sources",
            title="Appendix A: Sources",
            purpose="Full source register for verification.",
            min_pages=1,
            blocks=[_source_quality_table(report)],
        ),
        PremiumPreparedSection(
            id="appendix_facts",
            title="Appendix B: Fact Base",
            purpose="Extracted numeric facts and source links.",
            min_pages=1,
            blocks=[_evidence_table(analysis)],
        ),
        PremiumPreparedSection(
            id="appendix_limits",
            title="Appendix C: Limitations",
            purpose="Known gaps, constraints, and unresolved tensions.",
            min_pages=1,
            blocks=[_risk_register(report, analysis)],
        ),
    ]


def _deck_slides(plan: PremiumReportPlan) -> list[PremiumDeckSlideSpec]:
    slides: list[PremiumDeckSlideSpec] = []
    section_ids = [section.id for section in plan.sections]
    for index, title in enumerate(plan.deck_outline):
        source_section_id = section_ids[min(index, len(section_ids) - 1)] if section_ids else None
        slides.append(
            PremiumDeckSlideSpec(
                title=title,
                objective="Executive presentation slide derived from the full report.",
                source_section_id=source_section_id,
                suggested_blocks=_suggested_blocks_for_slide(title),
            )
        )
    return slides


def _suggested_blocks_for_slide(title: str) -> list[PremiumBlockKind]:
    lower = title.lower()
    if "evidence" in lower or "confidence" in lower:
        return ["source_quality_table"]
    if "risk" in lower:
        return ["risk_register"]
    if "decision" in lower:
        return ["decision_matrix"]
    if "scenario" in lower or "option" in lower:
        return ["scenario_matrix"]
    if "visual" in lower or "key" in lower:
        return ["kpi_grid"]
    return ["narrative"]


def _title_for(report: FinalReport) -> str:
    question = " ".join((report.question or "").split())
    return question[:120] if question else "Premium Research Report"


def _subtitle_for(plan: PremiumReportPlan) -> str:
    return (
        f"{plan.report_type.replace('_', ' ').title()} report for "
        f"{plan.audience.replace('_', ' ')} decision-making"
    )


def _fallback_body_for(spec: PremiumSectionSpec, report: FinalReport) -> str:
    if report.main_synthesis:
        return report.main_synthesis
    return f"{spec.purpose} This section requires additional assembled content."


def _numeric_facts(analysis: AnalysisOutput | None) -> list[NumericFact]:
    if analysis is None:
        return []
    return list(analysis.high_relevance_facts or analysis.all_numeric_facts)


def _first_fact_source(fact: NumericFact) -> str:
    if not fact.sources:
        return ""
    ref = fact.sources[0]
    return ref.url or ref.title or ""
