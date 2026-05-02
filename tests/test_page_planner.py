from smart_report.models import (
    AnalysisOutput,
    ChartSpec,
    ConsensusClaim,
    ExecutiveSummaryV4,
    FinalReport,
    NumericFact,
    QualitativeFact,
    SourceRef,
    Table,
)
from smart_report.page_planner import build_page_plan


def test_page_plan_blocks_unsupported_claims_and_missing_exhibits():
    report = FinalReport(
        session_id="pp",
        question="Will prices rise?",
        executive_summary=ExecutiveSummaryV4(main_answer="Prices rise by 20% without proof."),
        main_synthesis="Short.",
    )

    plan = build_page_plan(report)

    assert plan.summary.status == "blocked"
    assert any("unsupported" in issue.lower() for issue in plan.global_issues)
    assert any("chart/table" in issue.lower() for issue in plan.global_issues)


def test_page_plan_uses_analysis_and_exhibits_for_consulting_report_shape():
    source = SourceRef(url="https://example.com/primary", title="Primary", confidence="primary")
    fact = NumericFact(
        fact_id="f1",
        value="15%",
        metric="growth",
        subject="market",
        sources=[source],
        relevance_to_question="high",
    )
    qualitative = QualitativeFact(
        fact_id="q1",
        statement="Benchmark adoption is broad across enterprise buyers",
        subject="Benchmark adoption",
        sources=[source],
        relevance_to_question="high",
    )
    report = FinalReport(
        session_id="pp",
        question="LLM observability market benchmark",
        executive_summary=ExecutiveSummaryV4(
            main_answer="Market growth is 15% [1].",
            top_findings=["Benchmark adoption is broad [1]."],
        ),
        main_synthesis="Long synthesis " * 120,
        charts=[
            ChartSpec(chart_type="bar", title=f"Chart {idx}", data={"x": ["A"], "y": [idx]})
            for idx in range(1, 5)
        ],
        tables=[Table(title="Assumptions", columns=["A"], rows=[["B"]])],
    )
    analysis = AnalysisOutput(
        consensus=[
            ConsensusClaim(
                claim="Benchmark adoption is broad",
                supporting_sources=["https://example.com/primary"],
                confidence="high",
            )
        ],
        high_relevance_facts=[fact],
        all_numeric_facts=[fact],
        all_qualitative_facts=[qualitative],
    )

    plan = build_page_plan(report, analysis=analysis)

    assert plan.summary.page_count >= 10
    assert plan.summary.exhibit_pages >= 4
    assert plan.summary.status in {"ready", "needs_work"}
