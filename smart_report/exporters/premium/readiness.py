"""Readiness checks for premium client deliverables.

This module is deliberately additive. It does not block or change legacy
exports; it gives the new premium pipeline a stricter, explainable quality
gate before a report/deck package is presented as paid-client ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...adjudication_audit import AdjudicationAuditReport, assess_adjudication_quality
from ...analytic_closure import AnalyticClosureReport
from ...analytic_depth import AnalyticDepthPlan
from ...evidence_audit import EvidenceAuditReport, assess_evidence_support
from ...models import AnalysisOutput, FinalReport
from ...source_authority import count_authoritative_sources
from ..client_view import contains_client_leak
from .models import PremiumReportPlan
from .planner import build_premium_report_plan


@dataclass(frozen=True)
class PremiumReadinessIssue:
    code: str
    severity: str
    message: str
    recommendation: str = ""


@dataclass(frozen=True)
class PremiumReadiness:
    ready: bool
    score: int
    issues: list[PremiumReadinessIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)

    def model_dump(self) -> dict:
        return {
            "ready": self.ready,
            "score": self.score,
            "issues": [issue.__dict__ for issue in self.issues],
            "strengths": list(self.strengths),
        }


def assess_premium_readiness(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
    plan: PremiumReportPlan | None = None,
    depth_plan: AnalyticDepthPlan | None = None,
    closure_report: AnalyticClosureReport | None = None,
    evidence_audit: EvidenceAuditReport | None = None,
    adjudication_audit: AdjudicationAuditReport | None = None,
) -> PremiumReadiness:
    """Assess whether a report can support a premium report + deck package.

    The bar is intentionally higher than ``assess_client_readiness`` because a
    20+ page paid report needs more than safe text: it needs a defensible
    evidence base, an explicit analytical structure, separate report/deck
    deliverables, and enough visual/table material to support design work.
    """

    plan = plan or build_premium_report_plan(report, analysis=analysis)
    issues: list[PremiumReadinessIssue] = []
    strengths: list[str] = []
    metadata = report.metadata or {}

    _check_sources(report, plan, issues, strengths)
    _check_analysis_depth(analysis, plan, issues, strengths)
    _check_existing_quality_gates(report, metadata, issues, strengths)
    _check_evidence_support(report, analysis, evidence_audit, issues, strengths)
    _check_adjudication_quality(report, analysis, adjudication_audit, issues, strengths)
    _check_analytic_depth(depth_plan, issues, strengths)
    _check_analytic_closure(depth_plan, closure_report, issues, strengths)
    _check_visual_and_delivery_plan(plan, issues, strengths)
    _check_client_surface(report, issues, strengths)

    critical = sum(1 for issue in issues if issue.severity == "critical")
    major = sum(1 for issue in issues if issue.severity == "major")
    minor = sum(1 for issue in issues if issue.severity == "minor")
    score = max(0, 100 - critical * 25 - major * 10 - minor * 3)
    return PremiumReadiness(
        ready=critical == 0 and major == 0 and score >= 85,
        score=score,
        issues=issues,
        strengths=strengths,
    )


def _check_sources(
    report: FinalReport,
    plan: PremiumReportPlan,
    issues: list[PremiumReadinessIssue],
    strengths: list[str],
) -> None:
    source_count = len(report.all_sources or [])
    if source_count < plan.evidence.min_sources:
        issues.append(
            PremiumReadinessIssue(
                code="premium_too_few_sources",
                severity="critical",
                message=(
                    f"Report has {source_count} source(s); premium plan requires "
                    f"{plan.evidence.min_sources}."
                ),
                recommendation="Run more source collection or upload additional research reports.",
            )
        )
    else:
        strengths.append(f"Evidence base has {source_count} sources.")

    authoritative_count = count_authoritative_sources(report)
    if authoritative_count < plan.evidence.min_authoritative_sources:
        issues.append(
            PremiumReadinessIssue(
                code="premium_too_few_authoritative_sources",
                severity="critical",
                message=(
                    f"Report has {authoritative_count} authoritative source(s); "
                    f"premium plan requires {plan.evidence.min_authoritative_sources}."
                ),
                recommendation=(
                    "Add primary/official/high-reliability sources before premium export."
                ),
            )
        )
    else:
        strengths.append(f"Authoritative source threshold met: {authoritative_count}.")

    if plan.evidence.require_fact_to_source_mapping and not report.bibliography:
        issues.append(
            PremiumReadinessIssue(
                code="premium_missing_bibliography",
                severity="major",
                message="Premium evidence requirements include fact-to-source mapping, but bibliography is empty.",
                recommendation="Generate bibliography and carry source references into the report.",
            )
        )


def _check_analysis_depth(
    analysis: AnalysisOutput | None,
    plan: PremiumReportPlan,
    issues: list[PremiumReadinessIssue],
    strengths: list[str],
) -> None:
    if analysis is None:
        issues.append(
            PremiumReadinessIssue(
                code="premium_missing_analysis_output",
                severity="critical",
                message="Premium assessment has no AnalysisOutput, so consensus/conflicts/gaps/facts cannot be audited.",
                recommendation="Run the v4 analyzer before premium document assembly.",
            )
        )
        return

    numeric_fact_count = len(analysis.high_relevance_facts or analysis.all_numeric_facts)
    if numeric_fact_count < plan.evidence.min_numeric_facts:
        issues.append(
            PremiumReadinessIssue(
                code="premium_insufficient_numeric_facts",
                severity="major",
                message=(
                    f"Analysis has {numeric_fact_count} high-relevance numeric fact(s); "
                    f"premium plan requires {plan.evidence.min_numeric_facts}."
                ),
                recommendation="Use the intake fact table/data-pack path or add stronger numeric source material.",
            )
        )
    else:
        strengths.append(f"Numeric fact base is deep enough: {numeric_fact_count}.")

    if len(analysis.consensus) < 2:
        issues.append(
            PremiumReadinessIssue(
                code="premium_thin_consensus",
                severity="major",
                message="Analysis has fewer than two consensus claims.",
                recommendation="Strengthen cross-source synthesis before producing the paid report.",
            )
        )
    else:
        strengths.append("Consensus layer is present.")

    if len(analysis.conflicts) == 0 and len(analysis.gaps) == 0:
        issues.append(
            PremiumReadinessIssue(
                code="premium_no_tensions_or_gaps",
                severity="minor",
                message="Analysis contains no conflicts or gaps; this can indicate shallow source comparison.",
                recommendation="Confirm that the analyzer compared sources critically, not just summarized them.",
            )
        )
    else:
        strengths.append("Critical comparison layer is present.")

    critical_conflicts = sum(1 for conflict in analysis.conflicts if conflict.importance == "critical")
    if critical_conflicts:
        issues.append(
            PremiumReadinessIssue(
                code="premium_unresolved_critical_conflicts",
                severity="critical",
                message=f"Analysis still contains {critical_conflicts} critical conflict(s).",
                recommendation="Resolve or explicitly bracket critical conflicts before premium export.",
            )
        )


def _check_existing_quality_gates(
    report: FinalReport,
    metadata: dict,
    issues: list[PremiumReadinessIssue],
    strengths: list[str],
) -> None:
    if metadata.get("evidence_quality") == "LOW_EVIDENCE_QUALITY":
        issues.append(
            PremiumReadinessIssue(
                code="premium_low_evidence_quality",
                severity="critical",
                message="Existing v4 evidence gate marked the report as LOW_EVIDENCE_QUALITY.",
                recommendation="Close authoritative-source gaps before creating a premium artifact.",
            )
        )

    gap_counts = metadata.get("gap_count_by_severity") or {}
    critical_gaps = int(gap_counts.get("critical") or 0)
    moderate_gaps = int(gap_counts.get("moderate") or 0)
    if critical_gaps:
        issues.append(
            PremiumReadinessIssue(
                code="premium_critical_gaps_open",
                severity="critical",
                message=f"Existing v4 gap detector reports {critical_gaps} critical gap(s).",
                recommendation="Run targeted follow-up research before premium export.",
            )
        )
    if moderate_gaps:
        issues.append(
            PremiumReadinessIssue(
                code="premium_moderate_gaps_open",
                severity="major",
                message=f"Existing v4 gap detector reports {moderate_gaps} moderate gap(s).",
                recommendation="Either close the gaps or move them into explicit limitations.",
            )
        )

    lint = metadata.get("language_lint") or {}
    lint_count = int(lint.get("warnings_count") or 0)
    if lint_count:
        issues.append(
            PremiumReadinessIssue(
                code="premium_language_lint_warnings",
                severity="major",
                message=f"Language lint reports {lint_count} warning(s).",
                recommendation="Clean language before rendering client-facing files.",
            )
        )

    if report.citation_coverage >= 0.8:
        strengths.append(f"Citation coverage is strong: {report.citation_coverage:.0%}.")
    elif report.citation_coverage > 0:
        issues.append(
            PremiumReadinessIssue(
                code="premium_low_citation_coverage",
                severity="major",
                message=f"Citation coverage is only {report.citation_coverage:.0%}.",
                recommendation="Increase inline citation coverage for key claims.",
            )
        )


def _check_evidence_support(
    report: FinalReport,
    analysis: AnalysisOutput | None,
    evidence_audit: EvidenceAuditReport | None,
    issues: list[PremiumReadinessIssue],
    strengths: list[str],
) -> None:
    audit = evidence_audit or assess_evidence_support(report, analysis)
    if audit.claim_count == 0:
        issues.append(
            PremiumReadinessIssue(
                code="premium_no_claims_for_evidence_audit",
                severity="major",
                message="No client-facing conclusions were available for evidence-support auditing.",
                recommendation="Add an executive answer and explicit top findings before paid delivery.",
            )
        )
        return

    if audit.unsupported:
        severity = "critical" if audit.overall_score < 35 else "major"
        issues.append(
            PremiumReadinessIssue(
                code="premium_unsupported_conclusions",
                severity=severity,
                message=(
                    f"Evidence audit found {audit.unsupported} unsupported conclusion(s); "
                    f"overall evidence-support score is {audit.overall_score}/100."
                ),
                recommendation=(
                    "Add inline citations, source-backed consensus links, or numeric fact references "
                    "to unsupported executive conclusions."
                ),
            )
        )
    elif audit.overall_score < 70:
        issues.append(
            PremiumReadinessIssue(
                code="premium_weak_claim_evidence_support",
                severity="major",
                message=f"Evidence-support score is only {audit.overall_score}/100.",
                recommendation="Tighten source-to-claim coverage before premium delivery.",
            )
        )
    else:
        strengths.append(f"Evidence-support audit passed: {audit.overall_score}/100.")


def _check_adjudication_quality(
    report: FinalReport,
    analysis: AnalysisOutput | None,
    adjudication_audit: AdjudicationAuditReport | None,
    issues: list[PremiumReadinessIssue],
    strengths: list[str],
) -> None:
    audit = adjudication_audit or assess_adjudication_quality(report, analysis)
    if audit.conflict_count == 0:
        issues.append(
            PremiumReadinessIssue(
                code="premium_no_conflicts_for_adjudication",
                severity="minor",
                message="No conflicts were available for adjudication scoring.",
                recommendation="Confirm that source comparison was genuinely critical, not only summarizing.",
            )
        )
        return

    if audit.critical_unresolved:
        issues.append(
            PremiumReadinessIssue(
                code="premium_critical_conflict_not_adjudicated",
                severity="critical",
                message=f"Adjudication audit found {audit.critical_unresolved} unresolved critical conflict(s).",
                recommendation="Run targeted follow-up research and write a sourced adjudication before paid delivery.",
            )
        )
    elif audit.unresolved:
        issues.append(
            PremiumReadinessIssue(
                code="premium_unresolved_conflicts_not_adjudicated",
                severity="major",
                message=(
                    f"Adjudication audit found {audit.unresolved} unresolved conflict(s); "
                    f"overall adjudication score is {audit.overall_score}/100."
                ),
                recommendation="Add resolution logic, scope boundaries, or explicit limitations.",
            )
        )
    elif audit.overall_score < 70:
        issues.append(
            PremiumReadinessIssue(
                code="premium_weak_conflict_adjudication",
                severity="major",
                message=f"Conflict adjudication score is only {audit.overall_score}/100.",
                recommendation="Strengthen conflict resolution language before premium delivery.",
            )
        )
    else:
        strengths.append(f"Conflict adjudication audit passed: {audit.overall_score}/100.")


def _check_analytic_depth(
    depth_plan: AnalyticDepthPlan | None,
    issues: list[PremiumReadinessIssue],
    strengths: list[str],
) -> None:
    if depth_plan is None:
        issues.append(
            PremiumReadinessIssue(
                code="premium_missing_analytic_depth_plan",
                severity="major",
                message="No AnalyticDepthPlan was provided; premium readiness cannot verify issue tree, hypotheses, or research branches.",
                recommendation="Build an AnalyticDepthPlan before premium report assembly.",
            )
        )
        return

    if len(depth_plan.root.children) < 3:
        issues.append(
            PremiumReadinessIssue(
                code="premium_thin_issue_tree",
                severity="major",
                message="Analytic issue tree has fewer than three top-level branches.",
                recommendation="Add evidence, hypotheses, benchmarks, and decision branches.",
            )
        )
    else:
        strengths.append("Issue-tree decomposition is present.")

    if len(depth_plan.hypotheses) < 2:
        issues.append(
            PremiumReadinessIssue(
                code="premium_thin_hypothesis_set",
                severity="major",
                message="Analytic plan has fewer than two competing hypotheses.",
                recommendation="Add alternative explanations or scenario hypotheses.",
            )
        )
    else:
        strengths.append(f"Competing hypothesis set has {len(depth_plan.hypotheses)} item(s).")

    if not any(probe.disconfirming for probe in depth_plan.evidence_probes):
        issues.append(
            PremiumReadinessIssue(
                code="premium_missing_disconfirming_probe",
                severity="major",
                message="Analytic plan has no disconfirming evidence probe.",
                recommendation="Add at least one probe asking what would make the answer wrong.",
            )
        )
    else:
        strengths.append("Disconfirming evidence probe is present.")

    must_leads = [lead for lead in depth_plan.research_leads if lead.priority == "must"]
    if not must_leads:
        issues.append(
            PremiumReadinessIssue(
                code="premium_missing_must_research_leads",
                severity="major",
                message="Analytic plan has no must-priority research leads.",
                recommendation="Convert critical gaps/conflicts/unverified numbers into executable leads.",
            )
        )
    else:
        strengths.append(f"Executable must-priority research leads: {len(must_leads)}.")


def _check_analytic_closure(
    depth_plan: AnalyticDepthPlan | None,
    closure_report: AnalyticClosureReport | None,
    issues: list[PremiumReadinessIssue],
    strengths: list[str],
) -> None:
    if depth_plan is None:
        return

    must_leads = [lead for lead in depth_plan.research_leads if lead.priority == "must"]
    if not must_leads:
        return

    if closure_report is None:
        issues.append(
            PremiumReadinessIssue(
                code="premium_missing_analytic_closure",
                severity="major",
                message=(
                    "Analytic plan contains must-priority research leads, but no closure "
                    "score was provided."
                ),
                recommendation="Run or upload follow-up research and assess analytic closure.",
            )
        )
        return

    open_priority = closure_report.not_closed + closure_report.not_started
    if closure_report.overall_score < 60:
        issues.append(
            PremiumReadinessIssue(
                code="premium_low_analytic_closure_score",
                severity="major",
                message=f"Analytic closure score is {closure_report.overall_score}/100.",
                recommendation="Run targeted follow-up on open leads before premium delivery.",
            )
        )
    elif closure_report.overall_score < 80:
        issues.append(
            PremiumReadinessIssue(
                code="premium_partial_analytic_closure",
                severity="minor",
                message=f"Analytic closure score is only {closure_report.overall_score}/100.",
                recommendation="Review partial leads and decide whether limitations are acceptable.",
            )
        )

    if open_priority:
        issues.append(
            PremiumReadinessIssue(
                code="premium_open_analytic_leads",
                severity="major" if closure_report.not_started else "minor",
                message=(
                    f"Analytic closure still has {open_priority} open priority lead(s): "
                    f"{closure_report.not_closed} not closed, {closure_report.not_started} not started."
                ),
                recommendation="Close or explicitly bracket these leads before paid delivery.",
            )
        )

    if closure_report.overall_score >= 80 and not open_priority:
        strengths.append(f"Analytic closure score is strong: {closure_report.overall_score}/100.")


def _check_visual_and_delivery_plan(
    plan: PremiumReportPlan,
    issues: list[PremiumReadinessIssue],
    strengths: list[str],
) -> None:
    if plan.deliverables.report_min_pages < 20:
        issues.append(
            PremiumReadinessIssue(
                code="premium_report_too_short",
                severity="critical",
                message="Premium report deliverable is planned below 20 pages.",
                recommendation="Use the full premium report plan, not a one-pager or deck-only format.",
            )
        )
    if plan.deliverables.deck_min_slides < 10:
        issues.append(
            PremiumReadinessIssue(
                code="premium_deck_too_short",
                severity="major",
                message="Premium deck deliverable is planned below 10 slides.",
                recommendation="Keep the client report and executive presentation as separate artifacts.",
            )
        )
    if len(plan.required_visuals) < 4:
        issues.append(
            PremiumReadinessIssue(
                code="premium_visual_plan_too_thin",
                severity="major",
                message="Premium plan has fewer than four required visual/table blocks.",
                recommendation="Add KPI grid, evidence table, decision matrix, and risk register at minimum.",
            )
        )
    if not plan.deliverables.require_pdf or not plan.deliverables.require_docx:
        issues.append(
            PremiumReadinessIssue(
                code="premium_missing_report_formats",
                severity="major",
                message="Premium deliverable must include both PDF and editable DOCX report outputs.",
                recommendation="Keep both formats enabled for premium delivery.",
            )
        )
    if not plan.deliverables.require_pptx:
        issues.append(
            PremiumReadinessIssue(
                code="premium_missing_presentation",
                severity="major",
                message="Premium deliverable must include a separate presentation deck.",
                recommendation="Generate a deck from the report plan after the report is assembled.",
            )
        )

    if not any(issue.code.startswith("premium_report_too_short") for issue in issues):
        strengths.append(f"Report target meets premium length: {plan.deliverables.report_min_pages}+ pages.")
    if len(plan.required_visuals) >= 4:
        strengths.append(f"Visual/table plan has {len(plan.required_visuals)} required blocks.")


def _check_client_surface(
    report: FinalReport,
    issues: list[PremiumReadinessIssue],
    strengths: list[str],
) -> None:
    leaks = contains_client_leak(report)
    if leaks:
        issues.append(
            PremiumReadinessIssue(
                code="premium_client_surface_leaks",
                severity="critical",
                message="Client-facing text still contains internal markers: " + ", ".join(sorted(set(leaks))),
                recommendation="Sanitize the report before premium rendering.",
            )
        )
    else:
        strengths.append("No obvious internal client-surface leaks detected.")
