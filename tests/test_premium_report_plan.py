from __future__ import annotations

from smart_report.exporters import v4_to_report_dict
from smart_report.exporters.premium import build_premium_report_plan
from smart_report.models import ExecutiveSummaryV4, FinalReport, Source


def _report(question: str, synthesis: str = "") -> FinalReport:
    return FinalReport(
        session_id="premium-test",
        question=question,
        research_prompt_used="prompt",
        executive_summary=ExecutiveSummaryV4(
            main_answer="Answer.",
            ranking=None,
            top_findings=["Finding one."],
            key_numbers=[],
            confidence_note="Medium.",
            what_meta_adds="Adds source comparison.",
        ),
        main_synthesis=synthesis,
        consensus_section="",
        conflicts_section="",
        gaps_filled_section="",
        all_sources=[
            Source(title="Official source", url="https://example.com/a", tool="other", reliability="high"),
            Source(title="Industry source", url="https://example.com/b", tool="other", reliability="medium"),
        ],
        metadata={},
    )


def test_market_question_gets_market_plan():
    plan = build_premium_report_plan(
        _report("Forecast market prices, demand, supply, and scenarios for 2026")
    )

    assert plan.report_type == "market"
    assert plan.deliverables.report_min_pages >= 20
    assert plan.deliverables.deck_min_slides >= 10
    assert len(plan.sections) >= 8
    assert any(section.id == "market_baseline" for section in plan.sections)
    assert any(visual.kind == "scenario_matrix" for visual in plan.required_visuals)
    assert any("Report and deck are separate" in note for note in plan.non_breaking_notes)


def test_technical_question_gets_technical_audit_plan():
    plan = build_premium_report_plan(
        _report("Audit this repo architecture, security, bugs, and verification risks")
    )

    assert plan.report_type == "technical_audit"
    assert plan.audience == "technical_lead"
    assert any(section.id == "findings" for section in plan.sections)
    assert any("severity" in title.lower() for title in plan.deck_outline)


def test_investment_question_gets_investor_plan():
    plan = build_premium_report_plan(
        _report("Should an investor buy this asset, what IRR and downside risk?")
    )

    assert plan.report_type == "investment"
    assert plan.audience == "investor"
    assert any(section.id == "investment_thesis" for section in plan.sections)
    assert any(visual.kind == "sensitivity_table" for visual in plan.required_visuals)


def test_premium_planning_does_not_change_legacy_report_dict():
    final = _report("Market forecast for a category")
    before = v4_to_report_dict(final)
    _ = build_premium_report_plan(final)
    after = v4_to_report_dict(final)

    assert before == after
