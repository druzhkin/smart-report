"""Consulting-style editorial evaluator for final reports."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .benchmark_eval import evaluate_report_quality
from .exporters.client_view import contains_client_leak, sanitize_final_report
from .exporters.premium import assemble_premium_report_document, assess_premium_storyboard_quality
from .models import AnalysisOutput, FinalReport


class _ConsultingEvalBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConsultingEvalIssue(_ConsultingEvalBase):
    code: str
    severity: str
    message: str
    recommendation: str = ""


class ConsultingDimensionScore(_ConsultingEvalBase):
    dimension: str
    score: int
    passed: bool
    rationale: str


class ConsultingReportEval(_ConsultingEvalBase):
    score: int
    passed: bool
    verdict: str
    dimensions: list[ConsultingDimensionScore] = Field(default_factory=list)
    issues: list[ConsultingEvalIssue] = Field(default_factory=list)


def evaluate_consulting_report(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
) -> ConsultingReportEval:
    """Evaluate whether a report is fit for a consulting-style client surface."""

    client_report = sanitize_final_report(report)
    benchmark = evaluate_report_quality(client_report, analysis=analysis)
    document = assemble_premium_report_document(client_report, analysis=analysis)
    storyboard = assess_premium_storyboard_quality(document)
    leaks = contains_client_leak(client_report)

    issues: list[ConsultingEvalIssue] = []
    dimensions = [
        _dimension(
            "answer",
            _score_answer(client_report),
            "Executive answer is explicit and decision-oriented.",
        ),
        _dimension(
            "evidence",
            benchmark.evidence_score,
            "Client-facing claims are traceable to sources.",
        ),
        _dimension(
            "storyline",
            100 if storyboard.get("ready") else int(storyboard.get("score") or 0),
            "Narrative and exhibit sequence reads like a report, not a slide dump.",
        ),
        _dimension(
            "visual_support",
            _score_visual_support(client_report),
            "Charts, tables, and KPI blocks reinforce the text.",
        ),
        _dimension(
            "client_surface",
            100 if not leaks else 40,
            "No internal process labels or evidence tags leak to the client.",
        ),
    ]

    if not benchmark.passed:
        issues.append(
            ConsultingEvalIssue(
                code="consulting_benchmark_failed",
                severity="major",
                message=f"Benchmark profile score is {benchmark.score}/100.",
                recommendation="Close benchmark criteria before paid external delivery.",
            )
        )
    if not storyboard.get("ready"):
        issues.append(
            ConsultingEvalIssue(
                code="consulting_storyboard_not_ready",
                severity="major",
                message=f"Storyboard quality score is {storyboard.get('score')}/100.",
                recommendation="Improve page flow, early visuals, and exhibit source notes.",
            )
        )
    if leaks:
        issues.append(
            ConsultingEvalIssue(
                code="consulting_client_surface_leaks",
                severity="critical",
                message="Client report still contains internal markers: " + ", ".join(leaks[:6]),
                recommendation="Sanitize internal process vocabulary before export.",
            )
        )
    if len(client_report.executive_summary.top_findings) < 3:
        issues.append(
            ConsultingEvalIssue(
                code="consulting_thin_key_findings",
                severity="major",
                message="Executive summary has fewer than three key findings.",
                recommendation="Add a tight fact-backed finding set before publication.",
            )
        )

    critical = sum(1 for issue in issues if issue.severity == "critical")
    major = sum(1 for issue in issues if issue.severity == "major")
    raw_score = round(sum(item.score for item in dimensions) / len(dimensions))
    score = max(0, raw_score - critical * 25 - major * 8)
    passed = critical == 0 and major == 0 and score >= 85
    return ConsultingReportEval(
        score=score,
        passed=passed,
        verdict="publishable" if passed else "not_publishable",
        dimensions=dimensions,
        issues=issues,
    )


def _dimension(dimension: str, score: int, rationale: str) -> ConsultingDimensionScore:
    score = max(0, min(100, int(score)))
    return ConsultingDimensionScore(
        dimension=dimension,
        score=score,
        passed=score >= 80,
        rationale=rationale,
    )


def _score_answer(report: FinalReport) -> int:
    answer = (report.executive_summary.main_answer or "").strip()
    if len(answer) < 120:
        return 45
    if any(marker in answer.lower() for marker in ("maybe", "unclear", "depends")):
        return 65
    return 90


def _score_visual_support(report: FinalReport) -> int:
    count = len(report.charts) + len(report.tables) + len(report.key_numbers_highlight)
    if count >= 4:
        return 90
    if count >= 2:
        return 78
    if count == 1:
        return 60
    return 35
