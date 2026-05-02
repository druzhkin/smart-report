"""Deterministic benchmark harness for report pipeline quality.

This is not a replacement for human review. It gives the repository a stable
contract for "would we show this to a serious analyst?" across evidence,
research policy, page planning, and visual readiness.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .evidence_graph import build_evidence_graph
from .models import AnalysisOutput, FinalReport
from .page_planner import build_page_plan
from .research_policy import assess_research_policy


class _EvalBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BenchmarkEvalIssue(_EvalBase):
    code: str
    severity: str
    message: str


class BenchmarkEvalResult(_EvalBase):
    score: int
    passed: bool
    issues: list[BenchmarkEvalIssue] = Field(default_factory=list)
    evidence_score: int
    research_policy_passed: bool
    page_plan_status: str


def evaluate_report_quality(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
) -> BenchmarkEvalResult:
    graph = build_evidence_graph(report, analysis)
    policy = assess_research_policy(report.question, report)
    page_plan = build_page_plan(report, analysis=analysis, evidence_graph=graph)
    issues: list[BenchmarkEvalIssue] = []

    if graph.summary.score < 70:
        issues.append(
            BenchmarkEvalIssue(
                code="eval_evidence_graph_weak",
                severity="critical" if graph.summary.score < 45 else "major",
                message=f"Evidence graph score is {graph.summary.score}/100.",
            )
        )
    if graph.summary.unsupported:
        issues.append(
            BenchmarkEvalIssue(
                code="eval_unsupported_claims",
                severity="critical",
                message=f"{graph.summary.unsupported} client-facing claim(s) are unsupported.",
            )
        )
    if not policy.passed:
        issues.append(
            BenchmarkEvalIssue(
                code="eval_research_policy_failed",
                severity="major",
                message="; ".join(policy.issues),
            )
        )
    if page_plan.summary.status != "ready":
        issues.append(
            BenchmarkEvalIssue(
                code="eval_page_plan_not_ready",
                severity="major" if page_plan.summary.status == "needs_work" else "critical",
                message="; ".join(page_plan.global_issues[:4]) or page_plan.summary.status,
            )
        )
    if len(report.main_synthesis or "") < 1200:
        issues.append(
            BenchmarkEvalIssue(
                code="eval_synthesis_too_short",
                severity="major",
                message="Main synthesis is too short for a full analytical report.",
            )
        )

    critical = sum(1 for issue in issues if issue.severity == "critical")
    major = sum(1 for issue in issues if issue.severity == "major")
    minor = sum(1 for issue in issues if issue.severity == "minor")
    score = max(0, 100 - critical * 30 - major * 12 - minor * 4)
    return BenchmarkEvalResult(
        score=score,
        passed=critical == 0 and major == 0 and score >= 85,
        issues=issues,
        evidence_score=graph.summary.score,
        research_policy_passed=policy.passed,
        page_plan_status=page_plan.summary.status,
    )
