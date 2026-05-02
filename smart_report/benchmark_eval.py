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


class BenchmarkCriterionResult(_EvalBase):
    code: str
    label: str
    passed: bool
    observed: int | str | bool
    target: int | str | bool


class BenchmarkProfile(_EvalBase):
    id: str
    label: str
    min_score: int = 85
    min_evidence_score: int = 70
    min_sources: int = 8
    min_main_synthesis_chars: int = 1200
    min_visual_blocks: int = 2
    require_research_policy: bool = True
    require_ready_page_plan: bool = True


class BenchmarkEvalResult(_EvalBase):
    profile_id: str = "consulting_publication"
    profile_label: str = "Consulting publication report"
    score: int
    passed: bool
    issues: list[BenchmarkEvalIssue] = Field(default_factory=list)
    criteria: list[BenchmarkCriterionResult] = Field(default_factory=list)
    evidence_score: int
    research_policy_passed: bool
    page_plan_status: str


BENCHMARK_PROFILES: dict[str, BenchmarkProfile] = {
    "consulting_publication": BenchmarkProfile(
        id="consulting_publication",
        label="Consulting publication report",
        min_score=85,
        min_evidence_score=70,
        min_sources=8,
        min_main_synthesis_chars=1200,
        min_visual_blocks=2,
        require_research_policy=True,
        require_ready_page_plan=True,
    ),
    "board_brief": BenchmarkProfile(
        id="board_brief",
        label="Board-ready analytical brief",
        min_score=78,
        min_evidence_score=62,
        min_sources=5,
        min_main_synthesis_chars=700,
        min_visual_blocks=1,
        require_research_policy=True,
        require_ready_page_plan=False,
    ),
}


def evaluate_report_quality(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
    profile_id: str = "consulting_publication",
) -> BenchmarkEvalResult:
    profile = BENCHMARK_PROFILES.get(profile_id, BENCHMARK_PROFILES["consulting_publication"])
    graph = build_evidence_graph(report, analysis)
    policy = assess_research_policy(report.question, report)
    page_plan = build_page_plan(report, analysis=analysis, evidence_graph=graph)
    issues: list[BenchmarkEvalIssue] = []
    criteria: list[BenchmarkCriterionResult] = []

    criteria.append(
        BenchmarkCriterionResult(
            code="evidence_score",
            label="Evidence graph score",
            passed=graph.summary.score >= profile.min_evidence_score,
            observed=graph.summary.score,
            target=profile.min_evidence_score,
        )
    )
    if graph.summary.score < profile.min_evidence_score:
        issues.append(
            BenchmarkEvalIssue(
                code="eval_evidence_graph_weak",
                severity="critical" if graph.summary.score < 45 else "major",
                message=(
                    f"Evidence graph score is {graph.summary.score}/100; "
                    f"profile target is {profile.min_evidence_score}."
                ),
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
    criteria.append(
        BenchmarkCriterionResult(
            code="research_policy",
            label="Domain research policy",
            passed=policy.passed,
            observed=policy.passed,
            target=True,
        )
    )
    if profile.require_research_policy and not policy.passed:
        issues.append(
            BenchmarkEvalIssue(
                code="eval_research_policy_failed",
                severity="major",
                message="; ".join(policy.issues),
            )
        )
    criteria.append(
        BenchmarkCriterionResult(
            code="page_plan",
            label="Page plan readiness",
            passed=page_plan.summary.status == "ready",
            observed=page_plan.summary.status,
            target="ready",
        )
    )
    if profile.require_ready_page_plan and page_plan.summary.status != "ready":
        issues.append(
            BenchmarkEvalIssue(
                code="eval_page_plan_not_ready",
                severity="major" if page_plan.summary.status == "needs_work" else "critical",
                message="; ".join(page_plan.global_issues[:4]) or page_plan.summary.status,
            )
        )
    synthesis_chars = len(report.main_synthesis or "")
    criteria.append(
        BenchmarkCriterionResult(
            code="main_synthesis_length",
            label="Main synthesis length",
            passed=synthesis_chars >= profile.min_main_synthesis_chars,
            observed=synthesis_chars,
            target=profile.min_main_synthesis_chars,
        )
    )
    if synthesis_chars < profile.min_main_synthesis_chars:
        issues.append(
            BenchmarkEvalIssue(
                code="eval_synthesis_too_short",
                severity="major",
                message="Main synthesis is too short for a full analytical report.",
            )
        )
    source_count = len(report.all_sources)
    criteria.append(
        BenchmarkCriterionResult(
            code="source_count",
            label="Source count",
            passed=source_count >= profile.min_sources,
            observed=source_count,
            target=profile.min_sources,
        )
    )
    if source_count < profile.min_sources:
        issues.append(
            BenchmarkEvalIssue(
                code="eval_too_few_sources",
                severity="major",
                message=f"Report has {source_count} source(s); profile target is {profile.min_sources}.",
            )
        )
    visual_blocks = len(report.charts) + len(report.tables) + len(report.key_numbers_highlight)
    criteria.append(
        BenchmarkCriterionResult(
            code="visual_blocks",
            label="Charts, tables, or KPI blocks",
            passed=visual_blocks >= profile.min_visual_blocks,
            observed=visual_blocks,
            target=profile.min_visual_blocks,
        )
    )
    if visual_blocks < profile.min_visual_blocks:
        issues.append(
            BenchmarkEvalIssue(
                code="eval_visual_support_thin",
                severity="major",
                message=(
                    f"Report has {visual_blocks} visual support block(s); "
                    f"profile target is {profile.min_visual_blocks}."
                ),
            )
        )

    critical = sum(1 for issue in issues if issue.severity == "critical")
    major = sum(1 for issue in issues if issue.severity == "major")
    minor = sum(1 for issue in issues if issue.severity == "minor")
    score = max(0, 100 - critical * 30 - major * 12 - minor * 4)
    return BenchmarkEvalResult(
        profile_id=profile.id,
        profile_label=profile.label,
        score=score,
        passed=critical == 0 and major == 0 and score >= profile.min_score,
        issues=issues,
        criteria=criteria,
        evidence_score=graph.summary.score,
        research_policy_passed=policy.passed,
        page_plan_status=page_plan.summary.status,
    )
