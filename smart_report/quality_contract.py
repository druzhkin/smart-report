"""Enterprise quality contract for analytical report delivery.

This module is intentionally deterministic. It does not try to judge prose like
an LLM would; it checks whether the report pipeline produced the minimum
evidence, claim, visual, and operational trace that a serious analyst would
expect before showing a client-facing artifact.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .benchmark_eval import evaluate_report_quality
from .consulting_eval import evaluate_consulting_report
from .models import AnalysisOutput, FinalReport, V4Session
from .research_policy import assess_research_policy


class _QualityBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


EnterpriseIssueSeverity = Literal["critical", "major", "minor"]


class EnterpriseQualityIssue(_QualityBase):
    code: str
    severity: EnterpriseIssueSeverity
    message: str
    recommendation: str = ""


class ClaimAuditResult(_QualityBase):
    claim_count: int
    supported_claim_count: int
    unsupported_claim_count: int
    support_ratio: float
    unsupported_claims: list[str] = Field(default_factory=list)


class VisualIntelligenceResult(_QualityBase):
    visual_count: int
    useful_visual_count: int
    weak_visual_count: int
    issues: list[EnterpriseQualityIssue] = Field(default_factory=list)


class ReportStructureResult(_QualityBase):
    narrative_chars: int
    section_count: int
    text_visual_balance: str
    issues: list[EnterpriseQualityIssue] = Field(default_factory=list)


class ExecutionTraceResult(_QualityBase):
    total_cost_rub: float
    source_report_count: int
    followup_report_count: int
    pending_job_count: int
    running_job_count: int
    completed_long_task_count: int
    failed_long_task_count: int
    services_used: list[str] = Field(default_factory=list)
    paper_search_used: bool = False


class EnterpriseQualityContract(_QualityBase):
    score: int
    passed: bool
    verdict: Literal["publishable", "needs_work", "blocked"]
    issues: list[EnterpriseQualityIssue] = Field(default_factory=list)
    research_policy: dict[str, Any]
    claim_audit: ClaimAuditResult
    visual_intelligence: VisualIntelligenceResult
    report_structure: ReportStructureResult
    benchmark: dict[str, Any]
    consulting_eval: dict[str, Any]
    execution_trace: ExecutionTraceResult | None = None


def evaluate_enterprise_quality(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
    session: V4Session | None = None,
) -> EnterpriseQualityContract:
    """Evaluate the complete client-readiness contract for a final report."""

    policy = assess_research_policy(report.question, report)
    claim_audit = audit_claim_support(report)
    visual = audit_visual_intelligence(report)
    structure = audit_report_structure(report)
    benchmark = evaluate_report_quality(report, analysis=analysis)
    consulting = evaluate_consulting_report(report, analysis=analysis)
    trace = build_execution_trace(session) if session is not None else None

    issues: list[EnterpriseQualityIssue] = []
    if not policy.passed:
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_research_policy_failed",
                severity="critical" if policy.requires_academic_retrieval else "major",
                message="; ".join(policy.issues),
                recommendation="Run the recommended retrieval services before final export.",
            )
        )
    if claim_audit.unsupported_claim_count:
        severity: EnterpriseIssueSeverity = (
            "critical" if claim_audit.support_ratio < 0.55 else "major"
        )
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_unsupported_claims",
                severity=severity,
                message=(
                    f"{claim_audit.unsupported_claim_count} of "
                    f"{claim_audit.claim_count} audited claims lack visible source support."
                ),
                recommendation="Attach inline [REF:...] markers or remove unsupported assertions.",
            )
        )
    issues.extend(visual.issues)
    issues.extend(structure.issues)
    if not benchmark.passed:
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_benchmark_failed",
                severity="major",
                message=f"Benchmark score is {benchmark.score}/100.",
                recommendation="Close evidence, source, page-plan, and visual benchmark gaps.",
            )
        )
    if not consulting.passed:
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_consulting_eval_failed",
                severity="major",
                message=f"Consulting evaluator verdict is {consulting.verdict}.",
                recommendation="Improve storyline, visual support, and client surface before demo.",
            )
        )
    if trace and trace.running_job_count:
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_research_jobs_still_running",
                severity="major",
                message=f"{trace.running_job_count} research job(s) are still running.",
                recommendation="Wait for jobs to finish before claiming final quality.",
            )
        )

    critical = sum(1 for issue in issues if issue.severity == "critical")
    major = sum(1 for issue in issues if issue.severity == "major")
    minor = sum(1 for issue in issues if issue.severity == "minor")
    score = max(
        0,
        min(
            100,
            round(
                (
                    claim_audit.support_ratio * 25
                    + min(1.0, visual.useful_visual_count / 3) * 20
                    + min(1.0, structure.narrative_chars / 5000) * 20
                    + (benchmark.score / 100) * 20
                    + (consulting.score / 100) * 15
                )
                - critical * 18
                - major * 7
                - minor * 2
            ),
        ),
    )
    passed = critical == 0 and major == 0 and score >= 85
    verdict: Literal["publishable", "needs_work", "blocked"]
    if critical:
        verdict = "blocked"
    elif passed:
        verdict = "publishable"
    else:
        verdict = "needs_work"
    return EnterpriseQualityContract(
        score=score,
        passed=passed,
        verdict=verdict,
        issues=issues,
        research_policy=policy.model_dump(mode="json"),
        claim_audit=claim_audit,
        visual_intelligence=visual,
        report_structure=structure,
        benchmark=benchmark.model_dump(mode="json"),
        consulting_eval=consulting.model_dump(mode="json"),
        execution_trace=trace,
    )


def audit_claim_support(report: FinalReport) -> ClaimAuditResult:
    claims = _client_claims(report)
    supported = [claim for claim in claims if _has_visible_support(claim, report)]
    unsupported = [claim for claim in claims if claim not in supported]
    total = len(claims)
    ratio = round(len(supported) / total, 4) if total else 0.0
    return ClaimAuditResult(
        claim_count=total,
        supported_claim_count=len(supported),
        unsupported_claim_count=len(unsupported),
        support_ratio=ratio,
        unsupported_claims=unsupported[:8],
    )


def audit_visual_intelligence(report: FinalReport) -> VisualIntelligenceResult:
    issues: list[EnterpriseQualityIssue] = []
    weak = 0
    useful = 0
    for chart in report.charts:
        if not chart.title or not chart.caption:
            weak += 1
            issues.append(
                EnterpriseQualityIssue(
                    code="enterprise_chart_without_thesis_or_caption",
                    severity="major",
                    message=f"Chart '{chart.title or '(untitled)'} lacks a caption or thesis.",
                    recommendation="Every chart must explain what decision-relevant claim it proves.",
                )
            )
        elif not chart.data:
            weak += 1
            issues.append(
                EnterpriseQualityIssue(
                    code="enterprise_chart_without_data",
                    severity="critical",
                    message=f"Chart '{chart.title}' has no data payload.",
                    recommendation="Remove decorative charts or attach structured data.",
                )
            )
        else:
            useful += 1
    for table in report.tables:
        if not table.caption and not table.source_ref:
            weak += 1
            issues.append(
                EnterpriseQualityIssue(
                    code="enterprise_table_without_interpretation",
                    severity="major",
                    message=f"Table '{table.title}' lacks caption/source interpretation.",
                    recommendation="Add a caption that states the conclusion and cite the source.",
                )
            )
        else:
            useful += 1
    useful += len(report.key_numbers_highlight)
    count = len(report.charts) + len(report.tables) + len(report.key_numbers_highlight)
    if count < 3:
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_visual_support_too_thin",
                severity="major",
                message=f"Report has only {count} visual support block(s).",
                recommendation="Add at least three decision-relevant exhibits or KPI blocks.",
            )
        )
    return VisualIntelligenceResult(
        visual_count=count,
        useful_visual_count=useful,
        weak_visual_count=weak,
        issues=issues,
    )


def audit_report_structure(report: FinalReport) -> ReportStructureResult:
    sections = [
        report.executive_summary.main_answer,
        report.main_synthesis,
        report.consensus_section,
        report.conflicts_section,
        report.gaps_filled_section,
    ]
    narrative_chars = sum(len(text or "") for text in sections)
    section_count = sum(1 for text in sections if (text or "").strip())
    visual_count = len(report.charts) + len(report.tables) + len(report.key_numbers_highlight)
    issues: list[EnterpriseQualityIssue] = []
    if narrative_chars < 5000:
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_report_too_short",
                severity="major",
                message=f"Narrative body has {narrative_chars} characters; target is at least 5000.",
                recommendation="Expand interpretation, implications, risks, and scenario logic.",
            )
        )
    if section_count < 4:
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_report_structure_incomplete",
                severity="major",
                message=f"Only {section_count} substantive report sections are populated.",
                recommendation="Populate executive answer, synthesis, consensus, conflicts, and gaps/next steps.",
            )
        )
    if visual_count == 0:
        balance = "text_only"
    elif narrative_chars < 2500 and visual_count >= 4:
        balance = "presentation_like"
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_presentation_not_report",
                severity="major",
                message="Visual count is high while narrative body is thin.",
                recommendation="Add explanatory report prose around exhibits instead of slide-like fragments.",
            )
        )
    elif narrative_chars > 7000 and visual_count < 2:
        balance = "text_heavy"
        issues.append(
            EnterpriseQualityIssue(
                code="enterprise_text_without_visual_support",
                severity="major",
                message="Report is text-heavy and lacks enough visual proof.",
                recommendation="Add exhibits for the most important numbers, trends, and comparisons.",
            )
        )
    else:
        balance = "balanced"
    return ReportStructureResult(
        narrative_chars=narrative_chars,
        section_count=section_count,
        text_visual_balance=balance,
        issues=issues,
    )


def build_execution_trace(session: V4Session | None) -> ExecutionTraceResult:
    if session is None:
        return ExecutionTraceResult(
            total_cost_rub=0.0,
            source_report_count=0,
            followup_report_count=0,
            pending_job_count=0,
            running_job_count=0,
            completed_long_task_count=0,
            failed_long_task_count=0,
        )
    services: set[str] = set()
    paper_search_used = False
    for upload in list(session.source_reports or []) + list(session.followup_reports or []):
        tool = str(upload.detected_tool or "")
        filename = upload.filename or ""
        if tool:
            services.add(tool)
        if "paper_search" in tool or "paper_search" in filename.lower():
            paper_search_used = True
    for job in session.pending_dr_jobs or []:
        service = str(job.get("service") or "")
        if service:
            services.add(service)
        if service == "paper_search":
            paper_search_used = True
    running = sum(1 for job in session.pending_dr_jobs or [] if job.get("state") == "running")
    completed_long = sum(1 for task in session.pending_long_tasks or [] if task.get("state") == "completed")
    failed_long = sum(1 for task in session.pending_long_tasks or [] if task.get("state") == "failed")
    return ExecutionTraceResult(
        total_cost_rub=float(session.total_cost_rub or 0.0),
        source_report_count=len(session.source_reports or []),
        followup_report_count=len(session.followup_reports or []),
        pending_job_count=len(session.pending_dr_jobs or []),
        running_job_count=running,
        completed_long_task_count=completed_long,
        failed_long_task_count=failed_long,
        services_used=sorted(services),
        paper_search_used=paper_search_used,
    )


def _client_claims(report: FinalReport) -> list[str]:
    raw: list[str] = []
    raw.append(report.executive_summary.main_answer or "")
    raw.extend(report.executive_summary.top_findings or [])
    raw.extend([item.rationale for item in report.ranking or []])
    raw.extend([item.body for item in report.callouts or []])
    for text in [
        report.main_synthesis,
        report.consensus_section,
        report.conflicts_section,
        report.gaps_filled_section,
    ]:
        raw.extend(_split_claim_sentences(text))
    return [_normalize_claim(item) for item in raw if len(_normalize_claim(item)) >= 35]


def _split_claim_sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", str(text or ""))
        if part.strip()
    ]


def _normalize_claim(text: str) -> str:
    return " ".join(str(text or "").split())


def _has_visible_support(claim: str, report: FinalReport) -> bool:
    lowered = claim.lower()
    if "[ref:" in lowered or re.search(r"https?://", lowered):
        return True
    urls = [source.url.lower() for source in report.all_sources if source.url]
    titles = [source.title.lower() for source in report.all_sources if source.title]
    return any(url and url in lowered for url in urls) or any(
        len(title) >= 12 and title in lowered for title in titles
    )
