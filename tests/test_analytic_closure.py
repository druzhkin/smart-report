from __future__ import annotations

from smart_report.analytic_closure import assess_analytic_closure
from smart_report.analytic_depth import build_analytic_depth_plan
from smart_report.models import (
    AnalysisOutput,
    Conflict,
    ExecutiveSummaryV4,
    FinalReport,
    Gap,
    Source,
    UploadedMarkdown,
)


def _plan():
    analysis = AnalysisOutput(
        conflicts=[
            Conflict(
                topic="Price growth range",
                source_a="A",
                claim_a="+3%",
                source_b="B",
                claim_b="+12%",
                resolution_hint="Check transaction prices vs asking prices.",
                importance="critical",
            )
        ],
        gaps=[
            Gap(
                topic="Real transaction prices",
                why_critical="Asking prices can overstate the entry price.",
                what_to_find="Transaction-level or deal-price evidence by segment.",
                candidate_sources=["official registry", "industry data"],
            )
        ],
    )
    return build_analytic_depth_plan(
        "Forecast Moscow primary real estate prices",
        analysis=analysis,
        max_research_leads=4,
    )


def test_closure_reports_not_started_without_followups():
    report = assess_analytic_closure(_plan(), [])

    assert report.overall_score == 0
    assert report.not_started == report.lead_count
    assert "No follow-up reports" in report.summary


def test_closure_scores_followup_that_addresses_gap_and_conflict():
    followup = UploadedMarkdown(
        filename="auto_followup_perplexity_12345678.md",
        content=(
            "# Follow-up\n\n"
            "According to the official registry https://example.com/registry, "
            "transaction prices and deal-price evidence show 7.2% growth. "
            "The conflict is resolved by scope: asking prices include premium listings, "
            "while transaction prices are stronger evidence. Therefore the +12% claim is weaker."
        ),
        detected_tool="other",
        word_count=42,
    )

    report = assess_analytic_closure(_plan(), [followup])

    assert report.followup_report_count == 1
    assert report.overall_score > 0
    assert any(item.status in {"closed", "partial"} for item in report.lead_closures)
    assert any("url_citation" in item.evidence_signals for item in report.lead_closures)
    assert any("numeric_evidence" in item.evidence_signals for item in report.lead_closures)


def test_closure_uses_analytic_depth_lead_marker():
    plan = _plan()
    lead = next(item for item in plan.research_leads if item.priority == "must")
    followup = UploadedMarkdown(
        filename="auto_followup_perplexity_12345678.md",
        content=(
            "<!-- Smart Report analytic-depth metadata\n"
            f"Smart Report analytic-depth lead: {lead.id}\n"
            "Kind: close_gap\n"
            "Priority: must\n"
            "-->\n\n"
            "# Follow-up\n\n"
            "Evidence from https://example.com/source shows 7.2% transaction growth."
        ),
        detected_tool="other",
        word_count=30,
    )

    report = assess_analytic_closure(plan, [followup])
    closure = next(item for item in report.lead_closures if item.lead_id == lead.id)

    assert closure.status in {"closed", "partial"}
    assert "analytic_depth_lead_marker" in closure.evidence_signals


def test_required_source_family_closure_requires_each_missing_family():
    report = FinalReport(
        session_id="closure",
        question="Forecast Moscow primary real estate prices",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer."),
        all_sources=[Source(title="Generic", url="https://example.com")],
    )
    plan = build_analytic_depth_plan(
        "Forecast Moscow primary real estate prices",
        analysis=AnalysisOutput(),
        report=report,
        max_research_leads=6,
    )
    lead = next(item for item in plan.research_leads if item.id == "required_source_families")
    partial = UploadedMarkdown(
        filename="auto_followup_perplexity_required_source_families.md",
        content=(
            f"Smart Report analytic-depth lead: {lead.id}\n\n"
            "CBR source https://cbr.ru/statistics shows 15.5% and explains the rate backdrop."
        ),
        detected_tool="other",
        word_count=18,
    )

    closure_report = assess_analytic_closure(plan, [partial])
    closure = next(item for item in closure_report.lead_closures if item.lead_id == lead.id)

    assert closure.status == "partial"
    assert "required_source_family_hits:1" in closure.evidence_signals
    assert any("domrf" in signal for signal in closure.missing_signals)


def test_required_source_family_closure_closes_when_all_families_are_present():
    report = FinalReport(
        session_id="closure-full",
        question="Forecast Moscow primary real estate prices",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer."),
        all_sources=[Source(title="Generic", url="https://example.com")],
    )
    plan = build_analytic_depth_plan(
        "Forecast Moscow primary real estate prices",
        analysis=AnalysisOutput(),
        report=report,
        max_research_leads=6,
    )
    lead = next(item for item in plan.research_leads if item.id == "required_source_families")
    full = UploadedMarkdown(
        filename="auto_followup_perplexity_required_source_families.md",
        content=(
            f"Smart Report analytic-depth lead: {lead.id}\n\n"
            "CBR https://cbr.ru/statistics gives 15.5%; DOM.RF https://xn--d1aqf.xn--p1ai "
            "tracks mortgage programs; Rosstat https://rosstat.gov.ru provides housing output; "
            "ERZ https://erzrf.ru provides developer pipeline; Moscow portal https://mos.ru "
            "confirms city construction policy and launch context."
        ),
        detected_tool="other",
        word_count=44,
    )

    closure_report = assess_analytic_closure(plan, [full])
    closure = next(item for item in closure_report.lead_closures if item.lead_id == lead.id)

    assert closure.status == "closed"
    assert "required_source_family_hits:5" in closure.evidence_signals
    assert not any("Required source families still missing" in s for s in closure.missing_signals)
