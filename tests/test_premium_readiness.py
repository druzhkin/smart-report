from __future__ import annotations

from smart_report.analytic_closure import AnalyticClosureReport
from smart_report.analytic_depth import build_analytic_depth_plan
from smart_report.exporters.premium import (
    PremiumEvidenceRequirement,
    assess_premium_readiness,
    build_premium_report_plan,
)
from smart_report.models import (
    AnalysisOutput,
    Conflict,
    ConsensusClaim,
    ExecutiveSummaryV4,
    FinalReport,
    Gap,
    NumberedSource,
    NumericFact,
    Source,
    SourceRef,
)


def _report(source_count: int = 3, *, citation_coverage: float = 0.9) -> FinalReport:
    sources = [
        Source(title=f"Primary source {i}", url=f"https://example.com/{i}", reliability="high")
        for i in range(source_count)
    ]
    return FinalReport(
        session_id="premium-readiness",
        question="Market forecast with scenarios and investment implications",
        executive_summary=ExecutiveSummaryV4(
            main_answer="Answer with decision implications. [1][2]",
            top_findings=["Finding one. [1][2]", "Finding two. [2][3]"],
            confidence_note="High confidence with listed limitations.",
            what_meta_adds="Cross-source comparison and fact audit.",
        ),
        main_synthesis="Deep synthesis with evidence and scenario logic.",
        consensus_section="Consensus across sources.",
        conflicts_section=(
            "Methodology conflict between A and B is resolved on balance: A is more reliable "
            "within the stated scope, while B remains a scenario limitation."
        ),
        gaps_filled_section="Remaining limitations are explicit.",
        all_sources=sources,
        bibliography=[
            NumberedSource(
                number=i + 1,
                source_ref=SourceRef(
                    url=f"https://example.com/{i}",
                    title=f"Primary source {i}",
                    confidence="primary",
                ),
            )
            for i in range(source_count)
        ],
        citation_coverage=citation_coverage,
        metadata={"gap_count_by_severity": {"critical": 0, "moderate": 0, "minor": 1}},
    )


def _analysis(facts: int = 3, *, critical_conflict: bool = False) -> AnalysisOutput:
    numeric = [
        NumericFact(
            fact_id=f"fact{i}",
            value=str(i),
            metric="metric",
            subject="subject",
            relevance_to_question="high",
            sources=[
                SourceRef(
                    url=f"https://example.com/{i}",
                    title=f"Primary source {i}",
                    confidence="primary",
                )
            ],
        )
        for i in range(facts)
    ]
    return AnalysisOutput(
        consensus=[
            ConsensusClaim(
                claim="Consensus one. [1]",
                supporting_sources=["https://example.com/1", "https://example.com/2"],
                confidence="high",
            ),
            ConsensusClaim(
                claim="Consensus two. [2]",
                supporting_sources=["https://example.com/2", "https://example.com/3"],
                confidence="medium",
            ),
        ],
        conflicts=[
            Conflict(
                topic="Methodology",
                source_a="A",
                claim_a="A claim",
                source_b="B",
                claim_b="B claim",
                resolution_hint="A has stronger methodology within the report scope.",
                importance="critical" if critical_conflict else "material",
            )
        ],
        gaps=[
            Gap(
                topic="Unavailable microdata",
                why_critical="Needed for local precision",
                what_to_find="Closed paid dataset",
            )
        ],
        all_numeric_facts=numeric,
        high_relevance_facts=numeric,
        fact_coverage_target=facts,
    )


def _small_evidence_plan(report: FinalReport, analysis: AnalysisOutput):
    plan = build_premium_report_plan(report, analysis=analysis)
    return plan.model_copy(
        update={
            "evidence": PremiumEvidenceRequirement(
                min_sources=3,
                min_authoritative_sources=2,
                min_numeric_facts=3,
            )
        }
    )


def _closed_closure() -> AnalyticClosureReport:
    return AnalyticClosureReport(
        overall_score=92,
        closed=3,
        partial=0,
        not_closed=0,
        not_started=0,
        lead_count=3,
        followup_report_count=2,
        lead_closures=[],
        summary="Closure score 92/100 across 3 priority leads.",
    )


def test_premium_readiness_passes_for_deep_evidence_package():
    report = _report()
    analysis = _analysis()
    readiness = assess_premium_readiness(
        report,
        analysis=analysis,
        plan=_small_evidence_plan(report, analysis),
        depth_plan=build_analytic_depth_plan(report.question, analysis=analysis, report=report),
        closure_report=_closed_closure(),
    )

    assert readiness.ready is True
    assert readiness.score >= 85
    assert readiness.issues == []
    assert any("Evidence base" in strength for strength in readiness.strengths)
    assert any("Visual/table plan" in strength for strength in readiness.strengths)


def test_premium_readiness_blocks_missing_analysis_and_thin_sources():
    report = _report(source_count=1, citation_coverage=0.2)
    plan = build_premium_report_plan(report)
    plan = plan.model_copy(
        update={
            "evidence": PremiumEvidenceRequirement(
                min_sources=3,
                min_authoritative_sources=2,
                min_numeric_facts=3,
            )
        }
    )

    readiness = assess_premium_readiness(report, analysis=None, plan=plan)

    codes = {issue.code for issue in readiness.issues}
    assert readiness.ready is False
    assert readiness.score < 85
    assert {
        "premium_too_few_sources",
        "premium_too_few_authoritative_sources",
        "premium_missing_analysis_output",
        "premium_low_citation_coverage",
        "premium_missing_analytic_depth_plan",
    } <= codes


def test_premium_readiness_blocks_unresolved_critical_conflict():
    report = _report()
    analysis = _analysis(critical_conflict=True)

    readiness = assess_premium_readiness(
        report,
        analysis=analysis,
        plan=_small_evidence_plan(report, analysis),
        depth_plan=build_analytic_depth_plan(report.question, analysis=analysis, report=report),
        closure_report=_closed_closure(),
    )

    assert readiness.ready is False
    assert "premium_unresolved_critical_conflicts" in {
        issue.code for issue in readiness.issues
    }


def test_premium_readiness_requires_depth_plan_for_paid_quality():
    report = _report()
    analysis = _analysis()
    readiness = assess_premium_readiness(
        report,
        analysis=analysis,
        plan=_small_evidence_plan(report, analysis),
    )

    assert readiness.ready is False
    assert "premium_missing_analytic_depth_plan" in {
        issue.code for issue in readiness.issues
    }


def test_premium_readiness_requires_closure_when_must_leads_exist():
    report = _report()
    analysis = _analysis()
    readiness = assess_premium_readiness(
        report,
        analysis=analysis,
        plan=_small_evidence_plan(report, analysis),
        depth_plan=build_analytic_depth_plan(report.question, analysis=analysis, report=report),
    )

    assert readiness.ready is False
    assert "premium_missing_analytic_closure" in {
        issue.code for issue in readiness.issues
    }


def test_premium_readiness_blocks_low_closure_score():
    report = _report()
    analysis = _analysis()
    low_closure = AnalyticClosureReport(
        overall_score=35,
        closed=0,
        partial=1,
        not_closed=1,
        not_started=1,
        lead_count=3,
        followup_report_count=1,
        lead_closures=[],
        summary="Closure score 35/100 across 3 priority leads.",
    )

    readiness = assess_premium_readiness(
        report,
        analysis=analysis,
        plan=_small_evidence_plan(report, analysis),
        depth_plan=build_analytic_depth_plan(report.question, analysis=analysis, report=report),
        closure_report=low_closure,
    )

    codes = {issue.code for issue in readiness.issues}
    assert readiness.ready is False
    assert "premium_low_analytic_closure_score" in codes
    assert "premium_open_analytic_leads" in codes
