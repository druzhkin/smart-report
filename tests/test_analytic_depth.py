from __future__ import annotations

from smart_report.analytic_depth import build_analytic_depth_plan, infer_domain_hint
from smart_report.models import (
    AnalysisOutput,
    Conflict,
    ExecutiveSummaryV4,
    FinalReport,
    Gap,
    NumericFact,
    RankingItem,
    Source,
    SourceRef,
    UnverifiedNumber,
)


def _report(question: str) -> FinalReport:
    return FinalReport(
        session_id="depth",
        question=question,
        executive_summary=ExecutiveSummaryV4(
            main_answer="Base hypothesis: growth slows unless financing improves.",
            top_findings=["Financing is the binding variable."],
            confidence_note="Medium confidence.",
        ),
        main_synthesis="The answer depends on demand, supply, and financing constraints.",
    )


def _analysis() -> AnalysisOutput:
    fact = NumericFact(
        fact_id="f1",
        value="18%",
        metric="mortgage rate",
        subject="primary market",
        timeframe="2026",
        relevance_to_question="high",
        sources=[SourceRef(url="https://example.com/rate", title="Rate source")],
    )
    return AnalysisOutput(
        conflicts=[
            Conflict(
                topic="Price growth range",
                source_a="A",
                claim_a="+3%",
                source_b="B",
                claim_b="+12%",
                resolution_hint="Check comparable scope and transaction vs asking prices.",
                importance="critical",
            )
        ],
        gaps=[
            Gap(
                topic="Real transaction prices",
                why_critical="Asking prices can overstate the investable entry price.",
                what_to_find="Transaction-level or deal-price evidence by segment.",
                candidate_sources=["official registry", "industry data"],
            )
        ],
        unverified_numbers=[
            UnverifiedNumber(
                value="18%",
                metric="mortgage rate",
                subject="new-build loans",
                source_tool="uploaded report",
                why_unverified="No primary URL.",
            )
        ],
        all_numeric_facts=[fact],
        high_relevance_facts=[fact],
    )


def test_depth_plan_builds_non_linear_inquiry_tree():
    plan = build_analytic_depth_plan(
        "Forecast Moscow primary real estate prices",
        analysis=_analysis(),
        report=_report("Forecast Moscow primary real estate prices"),
    )

    assert plan.domain_hint == "russian_market"
    assert plan.root.methods == ["issue_tree"]
    assert {child.id for child in plan.root.children} == {
        "evidence_base",
        "hypotheses",
        "benchmarks",
        "decision",
    }
    assert len(plan.hypotheses) >= 3
    assert any(probe.disconfirming for probe in plan.evidence_probes)
    assert any(lead.kind == "resolve_conflict" for lead in plan.research_leads)
    assert any(lead.kind == "verify_number" for lead in plan.research_leads)
    assert any(lead.kind == "find_benchmark" for lead in plan.research_leads)


def test_depth_plan_routes_valyu_for_financial_us():
    analysis = _analysis()
    plan = build_analytic_depth_plan(
        "Analyze Tesla 10-K, SEC filings, FRED rates, and earnings risk",
        analysis=analysis,
        report=_report("Analyze Tesla SEC filings"),
    )

    assert plan.domain_hint == "financial_us"
    assert any(lead.recommended_service == "valyu" for lead in plan.research_leads)


def test_infer_domain_hint_keeps_russian_market_off_valyu():
    assert infer_domain_hint("рынок недвижимости Москвы ставки ЦБ ДОМ.РФ ЕРЗ") == "russian_market"


def test_depth_plan_has_disconfirming_research_lead():
    plan = build_analytic_depth_plan("Should we enter this market?", analysis=_analysis())

    disconfirm = [lead for lead in plan.research_leads if lead.id == "disconfirm_1"]
    assert disconfirm
    assert disconfirm[0].kind == "test_hypothesis"
    assert "make the current likely answer wrong" in disconfirm[0].prompt


def test_depth_plan_adds_authority_source_lead_when_source_base_is_weak():
    plan = build_analytic_depth_plan(
        "Forecast Moscow primary real estate prices",
        analysis=_analysis(),
        report=_report("Forecast Moscow primary real estate prices"),
    )

    authority = [lead for lead in plan.research_leads if lead.id == "authority_sources"]
    assert authority
    assert authority[0].priority == "must"
    assert authority[0].kind == "strengthen_source_base"
    assert "cbr.ru" in authority[0].candidate_sources


def test_depth_plan_skips_authority_source_lead_when_source_base_is_strong():
    report = _report("Forecast Moscow primary real estate prices")
    report.all_sources = [
        Source(title="CBR", url="https://cbr.ru/statistics", reliability="medium"),
        Source(title="DOM.RF", url="https://xn--d1aqf.xn--p1ai", reliability="medium"),
        Source(title="Official Moscow", url="https://mos.ru/news", reliability="medium"),
    ]

    plan = build_analytic_depth_plan(
        "Forecast Moscow primary real estate prices",
        analysis=_analysis(),
        report=report,
    )

    assert not [lead for lead in plan.research_leads if lead.id == "authority_sources"]


def test_depth_plan_adds_claim_support_lead_for_unsupported_structured_conclusion():
    report = _report("Assess regulatory risk")
    report.ranking = [
        RankingItem(
            label="Regulatory risk",
            weight=80,
            rationale="Four separate legal changes together create systemic tightening.",
            evidence_strength="medium",
        )
    ]

    plan = build_analytic_depth_plan(
        "Assess regulatory risk",
        analysis=AnalysisOutput(),
        report=report,
    )

    support = [lead for lead in plan.research_leads if lead.kind == "support_claim"]
    assert support
    assert support[0].priority == "must"
    assert "supports, qualifies, or disproves" in support[0].prompt
