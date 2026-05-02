from smart_report.benchmark_eval import evaluate_report_quality
from smart_report.models import ChartSpec, ExecutiveSummaryV4, FinalReport, Source, Table


def test_benchmark_eval_rejects_weak_report():
    report = FinalReport(
        session_id="be",
        question="Will prices rise?",
        executive_summary=ExecutiveSummaryV4(main_answer="Prices rise by 30% without proof."),
        main_synthesis="Too short.",
    )

    result = evaluate_report_quality(report)

    assert result.passed is False
    assert result.score < 85
    assert {issue.code for issue in result.issues} >= {
        "eval_evidence_graph_weak",
        "eval_unsupported_claims",
        "eval_page_plan_not_ready",
        "eval_synthesis_too_short",
        "eval_too_few_sources",
        "eval_visual_support_thin",
    }
    assert result.profile_id == "consulting_publication"
    assert any(item.code == "visual_blocks" and not item.passed for item in result.criteria)


def test_benchmark_eval_supports_named_board_brief_profile():
    report = FinalReport(
        session_id="be-board",
        question="EU AI Act regulatory impact on enterprise SaaS",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer with enough direction."),
        main_synthesis="Evidence-backed board brief. " * 35,
        all_sources=[
            Source(title="European Commission", url="https://ec.europa.eu/example"),
            Source(title="EU law", url="https://eur-lex.europa.eu/example"),
            Source(title="Parliament", url="https://europarl.europa.eu/example"),
            Source(title="Industry", url="https://oecd.org/example"),
            Source(title="Benchmark", url="https://bcg.com/example"),
        ],
        charts=[ChartSpec(chart_type="bar", title="Impact", data={"points": [1]})],
        tables=[Table(title="Sources", columns=["A"], rows=[["B"]])],
    )

    result = evaluate_report_quality(report, profile_id="board_brief")

    assert result.profile_id == "board_brief"
    assert any(item.code == "main_synthesis_length" for item in result.criteria)
    assert not any(issue.code == "eval_visual_support_thin" for issue in result.issues)
