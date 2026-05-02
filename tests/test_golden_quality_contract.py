from smart_report.benchmark_eval import evaluate_report_quality
from smart_report.consulting_eval import evaluate_consulting_report
from smart_report.exporters.premium import (
    build_regeneration_plan,
    structured_source_from_final_report,
)
from smart_report.exporters.client_view import sanitize_final_report
from smart_report.models import ChartSpec, ExecutiveSummaryV4, FinalReport, KeyNumberHighlight, Source, Table


def test_golden_report_quality_contract_accepts_shaped_report():
    report = _golden_report()

    benchmark = evaluate_report_quality(report, profile_id="board_brief")
    consulting = evaluate_consulting_report(report)
    structured = structured_source_from_final_report(sanitize_final_report(report))
    regeneration = build_regeneration_plan(structured)

    assert benchmark.criteria
    assert not any(issue.code == "eval_visual_support_thin" for issue in benchmark.issues)
    assert any(item.dimension == "visual_support" and item.score >= 78 for item in consulting.dimensions)
    assert regeneration.can_regenerate


def test_golden_report_quality_contract_rejects_weak_report():
    report = FinalReport(
        session_id="golden-weak",
        question="Will prices rise?",
        executive_summary=ExecutiveSummaryV4(main_answer="Maybe prices rise."),
        main_synthesis="Too short.",
    )

    benchmark = evaluate_report_quality(report)
    consulting = evaluate_consulting_report(report)

    assert benchmark.passed is False
    assert consulting.passed is False
    assert {issue.code for issue in benchmark.issues} >= {
        "eval_synthesis_too_short",
        "eval_visual_support_thin",
    }
    assert any(issue.code == "consulting_thin_key_findings" for issue in consulting.issues)


def _golden_report() -> FinalReport:
    return FinalReport(
        session_id="golden-shaped",
        question="EU AI Act regulatory impact on enterprise SaaS",
        executive_summary=ExecutiveSummaryV4(
            main_answer=(
                "The AI Act raises compliance cost but creates a board-level buying trigger "
                "for workflow vendors that can turn model governance into auditable controls "
                "[REF:https://ec.europa.eu/example]."
            ),
            top_findings=[
                "Regulatory obligations define the compliance trigger.",
                "Enterprise buyers need traceable audit workflows.",
                "Benchmarks favour governed deployment patterns.",
            ],
            confidence_note="Confidence is medium-high because primary regulatory sources are present.",
        ),
        main_synthesis=(
            "Evidence-backed consulting storyline with implications "
            "[REF:https://eur-lex.europa.eu/example]. "
        ) * 80,
        consensus_section=(
            "Primary legal sources and industry benchmarks agree on higher governance demand "
            "[REF:https://europarl.europa.eu/example]."
        ),
        conflicts_section=(
            "Timing remains uncertain across jurisdictions and enforcement calendars "
            "[REF:https://europa.eu/example]."
        ),
        gaps_filled_section=(
            "Vendor implementation cost data should be refreshed quarterly "
            "[REF:https://bcg.com/example]."
        ),
        all_sources=[
            Source(title="Europa portal", url="https://europa.eu/example", reliability="high"),
            Source(title="European Commission", url="https://ec.europa.eu/example", reliability="high"),
            Source(title="EU law", url="https://eur-lex.europa.eu/example", reliability="high"),
            Source(title="Parliament", url="https://europarl.europa.eu/example", reliability="high"),
            Source(title="OECD", url="https://oecd.org/example", reliability="medium"),
            Source(title="BCG benchmark", url="https://bcg.com/example", reliability="medium"),
            Source(title="McKinsey benchmark", url="https://mckinsey.com/example", reliability="medium"),
            Source(title="Academic paper", url="https://doi.org/10.1000/example", reliability="high"),
            Source(title="Vendor docs", url="https://docs.example.com", reliability="medium"),
        ],
        charts=[ChartSpec(chart_type="bar", title="Compliance impact", data={"points": [1, 2, 3]})],
        tables=[Table(title="Source matrix", columns=["Source", "Use"], rows=[["EU", "Regulatory baseline"]])],
        key_numbers_highlight=[
            KeyNumberHighlight(
                value="3",
                label="board-level implications",
                source_ref="https://ec.europa.eu/example",
                importance="primary",
            )
        ],
    )
