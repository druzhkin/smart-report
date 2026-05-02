from smart_report.consulting_eval import evaluate_consulting_report
from smart_report.models import ChartSpec, ExecutiveSummaryV4, FinalReport, KeyNumberHighlight, Source, Table


def test_consulting_eval_rejects_thin_report():
    report = FinalReport(
        session_id="consulting-thin",
        question="Will prices rise?",
        executive_summary=ExecutiveSummaryV4(main_answer="Maybe."),
        main_synthesis="Too short.",
    )

    result = evaluate_consulting_report(report)

    assert result.passed is False
    assert result.verdict == "not_publishable"
    assert {issue.code for issue in result.issues} >= {
        "consulting_benchmark_failed",
        "consulting_storyboard_not_ready",
        "consulting_thin_key_findings",
    }
    assert any(item.dimension == "visual_support" and item.score < 80 for item in result.dimensions)


def test_consulting_eval_scores_report_dimensions():
    report = FinalReport(
        session_id="consulting-shaped",
        question="EU AI Act regulatory impact on enterprise SaaS",
        executive_summary=ExecutiveSummaryV4(
            main_answer=(
                "The regulation will raise compliance cost but create a defensible "
                "enterprise software opportunity for vendors that productize audit workflows."
            ),
            top_findings=[
                "Regulatory text defines the compliance trigger.",
                "Enterprise buyers need auditability.",
                "Benchmarks shift toward governed workflows.",
            ],
        ),
        main_synthesis="Evidence-backed consulting storyline. " * 80,
        all_sources=[
            Source(title="European Commission", url="https://ec.europa.eu/example"),
            Source(title="EU law", url="https://eur-lex.europa.eu/example"),
            Source(title="Parliament", url="https://europarl.europa.eu/example"),
            Source(title="OECD", url="https://oecd.org/example"),
            Source(title="Benchmark", url="https://bcg.com/example"),
            Source(title="Industry", url="https://mckinsey.com/example"),
            Source(title="Academic", url="https://doi.org/10.1000/example"),
            Source(title="Vendor docs", url="https://docs.example.com"),
        ],
        charts=[ChartSpec(chart_type="bar", title="Impact", data={"points": [1]})],
        tables=[Table(title="Evidence", columns=["A"], rows=[["B"]])],
        key_numbers_highlight=[
            KeyNumberHighlight(
                value="3",
                label="key effects",
                source_ref="https://ec.europa.eu/example",
                importance="primary",
            )
        ],
    )

    result = evaluate_consulting_report(report)

    assert result.score > 0
    assert {item.dimension for item in result.dimensions} == {
        "answer",
        "evidence",
        "storyline",
        "visual_support",
        "client_surface",
    }
