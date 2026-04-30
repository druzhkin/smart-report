from __future__ import annotations

from smart_report.analytic_closure import assess_analytic_closure
from smart_report.analytic_depth import build_analytic_depth_plan
from smart_report.models import (
    AnalysisOutput,
    Conflict,
    Gap,
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
