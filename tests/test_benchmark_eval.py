from smart_report.benchmark_eval import evaluate_report_quality
from smart_report.models import ExecutiveSummaryV4, FinalReport


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
    }
