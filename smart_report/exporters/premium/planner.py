"""Universal planner for premium client deliverables.

The planner is deliberately heuristic and side-effect free. It creates a
domain-neutral premium report/deck plan from a final report question and, when
available, evidence metadata. Renderers can use the plan later, but this module
does not modify existing export behavior.
"""

from __future__ import annotations

import re

from ...models import AnalysisOutput, FinalReport
from .models import (
    PremiumAppendixSpec,
    PremiumAudience,
    PremiumDeliverableSpec,
    PremiumEvidenceRequirement,
    PremiumReportPlan,
    PremiumReportType,
    PremiumSectionSpec,
    PremiumVisualSpec,
)


def build_premium_report_plan(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
    min_report_pages: int = 20,
    min_deck_slides: int = 10,
) -> PremiumReportPlan:
    """Build an opt-in premium report plan without touching legacy exporters."""

    question = report.question or ""
    report_type = infer_report_type(question, report)
    audience = infer_audience(question)
    decision_context = _decision_context(question, report_type, audience)

    sections = _base_sections(report_type)
    required_visuals = _visuals_for(report_type)
    appendices = _appendices_for(report_type)
    deck_outline = _deck_outline_for(report_type)

    source_count = len(report.all_sources or [])
    fact_count = _fact_count(analysis)
    evidence = PremiumEvidenceRequirement(
        min_sources=max(8, min(source_count + 3, 15)),
        min_authoritative_sources=3,
        min_numeric_facts=max(20, min(fact_count + 10, 60)),
    )

    return PremiumReportPlan(
        report_type=report_type,
        audience=audience,
        decision_context=decision_context,
        deliverables=PremiumDeliverableSpec(
            report_min_pages=max(20, min_report_pages),
            deck_min_slides=max(10, min_deck_slides),
        ),
        evidence=evidence,
        sections=sections,
        required_visuals=required_visuals,
        appendices=appendices,
        deck_outline=deck_outline,
        non_breaking_notes=[
            "Premium layer is opt-in and must not change legacy export behavior.",
            "Report and deck are separate deliverables, not substitutes.",
            "Topic-specific facts belong in evidence tables, not renderer code.",
        ],
    )


def infer_report_type(question: str, report: FinalReport | None = None) -> PremiumReportType:
    text = _combined_text(question, report)
    if _has(text, "рынок", "market", "цены", "price", "demand", "supply", "forecast"):
        return "market"
    if _has(text, "инвест", "investment", "irr", "доход", "valuation", "окуп"):
        return "investment"
    if _has(text, "конкур", "competitor", "competitive", "benchmark", "позициони"):
        return "competitive"
    if _has(text, "стратег", "strategy", "go-to-market", "roadmap", "рост"):
        return "strategy"
    if _has(text, "код", "архитект", "security", "аудит", "bug", "technical", "repo"):
        return "technical_audit"
    if _has(text, "закон", "регуля", "legal", "compliance", "налог", "санкц"):
        return "legal_regulatory"
    if _has(text, "due diligence", "провер", "risk", "риски", "сделк"):
        return "due_diligence"
    return "general_research"


def infer_audience(question: str) -> PremiumAudience:
    text = question.lower()
    if _has(text, "покуп", "buyer", "купить"):
        return "buyer"
    if _has(text, "инвест", "investor", "irr", "доход"):
        return "investor"
    if _has(text, "ceo", "директор", "executive", "совет"):
        return "executive"
    if _has(text, "developer", "девелоп", "застрой"):
        return "developer"
    if _has(text, "cto", "tech lead", "инженер", "архитектор", "repo", "security", "bug"):
        return "technical_lead"
    if _has(text, "операц", "operator", "ops"):
        return "operator"
    if _has(text, "аналит", "analyst"):
        return "analyst"
    return "general_client"


def _base_sections(report_type: PremiumReportType) -> list[PremiumSectionSpec]:
    common = [
        PremiumSectionSpec(
            id="executive_summary",
            title="Executive summary",
            purpose="State the answer, decision implications, and confidence.",
            min_pages=1,
            required_blocks=["kpi_grid", "decision_matrix"],
        ),
        PremiumSectionSpec(
            id="question_framing",
            title="Question framing and scope",
            purpose="Clarify what is being answered, for whom, and what is out of scope.",
            min_pages=1,
            required_blocks=["methodology_box"],
        ),
        PremiumSectionSpec(
            id="evidence_base",
            title="Evidence base",
            purpose="Show the facts, source tiers, and reliability constraints.",
            min_pages=2,
            required_blocks=["evidence_table", "source_quality_table"],
        ),
    ]

    type_specific: dict[PremiumReportType, list[PremiumSectionSpec]] = {
        "market": [
            PremiumSectionSpec(
                id="market_baseline",
                title="Market baseline",
                purpose="Define the market, segments, historical data, and current state.",
                min_pages=3,
                required_blocks=["timeline", "chart"],
            ),
            PremiumSectionSpec(
                id="demand_supply",
                title="Demand and supply drivers",
                purpose="Explain what moves the market and which forces dominate.",
                min_pages=3,
                required_blocks=["market_map", "chart"],
            ),
            PremiumSectionSpec(
                id="scenarios",
                title="Scenario forecast",
                purpose="Model base, upside, and downside outcomes with triggers.",
                min_pages=3,
                required_blocks=["scenario_matrix", "sensitivity_table"],
            ),
        ],
        "investment": [
            PremiumSectionSpec(
                id="investment_thesis",
                title="Investment thesis",
                purpose="Define upside, downside, entry conditions, and expected return logic.",
                min_pages=3,
                required_blocks=["kpi_grid", "sensitivity_table"],
            ),
            PremiumSectionSpec(
                id="valuation_and_exit",
                title="Valuation and exit",
                purpose="Explain price, return, liquidity, and exit assumptions.",
                min_pages=3,
                required_blocks=["scenario_matrix", "chart"],
            ),
            PremiumSectionSpec(
                id="risk_adjusted_decision",
                title="Risk-adjusted decision",
                purpose="Translate analysis into invest / wait / reject thresholds.",
                min_pages=2,
                required_blocks=["risk_register", "decision_matrix"],
            ),
        ],
        "competitive": [
            PremiumSectionSpec(
                id="competitive_landscape",
                title="Competitive landscape",
                purpose="Map competitors, segments, positioning, and strategic pressure.",
                min_pages=3,
                required_blocks=["competitive_matrix", "market_map"],
            ),
            PremiumSectionSpec(
                id="capability_benchmark",
                title="Capability benchmark",
                purpose="Compare strengths, gaps, pricing, distribution, and product depth.",
                min_pages=3,
                required_blocks=["competitive_matrix", "chart"],
            ),
            PremiumSectionSpec(
                id="strategic_moves",
                title="Strategic moves",
                purpose="Recommend moves, trade-offs, and sequencing.",
                min_pages=2,
                required_blocks=["decision_matrix", "risk_register"],
            ),
        ],
        "strategy": [
            PremiumSectionSpec(
                id="current_state",
                title="Current state",
                purpose="Define the operating context and constraints.",
                min_pages=2,
                required_blocks=["kpi_grid", "market_map"],
            ),
            PremiumSectionSpec(
                id="strategic_options",
                title="Strategic options",
                purpose="Compare viable strategic paths and trade-offs.",
                min_pages=3,
                required_blocks=["decision_matrix", "scenario_matrix"],
            ),
            PremiumSectionSpec(
                id="roadmap",
                title="Roadmap and operating metrics",
                purpose="Translate strategy into milestones and metrics.",
                min_pages=2,
                required_blocks=["timeline", "risk_register"],
            ),
        ],
        "technical_audit": [
            PremiumSectionSpec(
                id="system_map",
                title="System map",
                purpose="Explain architecture, trust boundaries, and operational flow.",
                min_pages=3,
                required_blocks=["market_map", "evidence_table"],
            ),
            PremiumSectionSpec(
                id="findings",
                title="Findings and severity",
                purpose="Prioritize bugs, risks, regressions, and missing verification.",
                min_pages=4,
                required_blocks=["risk_register", "evidence_table"],
            ),
            PremiumSectionSpec(
                id="remediation",
                title="Remediation and verification plan",
                purpose="Define fixes, owners, tests, and release gates.",
                min_pages=2,
                required_blocks=["timeline", "decision_matrix"],
            ),
        ],
        "legal_regulatory": [
            PremiumSectionSpec(
                id="regulatory_baseline",
                title="Regulatory baseline",
                purpose="Summarize governing rules and authoritative sources.",
                min_pages=3,
                required_blocks=["evidence_table", "source_quality_table"],
            ),
            PremiumSectionSpec(
                id="risk_interpretation",
                title="Risk interpretation",
                purpose="Translate rules into operational and financial risk.",
                min_pages=3,
                required_blocks=["risk_register", "scenario_matrix"],
            ),
            PremiumSectionSpec(
                id="compliance_actions",
                title="Compliance actions",
                purpose="Define action thresholds, monitoring, and escalation.",
                min_pages=2,
                required_blocks=["decision_matrix", "timeline"],
            ),
        ],
        "due_diligence": [
            PremiumSectionSpec(
                id="asset_or_target_profile",
                title="Target profile",
                purpose="Define the object of diligence and its evidence trail.",
                min_pages=2,
                required_blocks=["kpi_grid", "evidence_table"],
            ),
            PremiumSectionSpec(
                id="diligence_findings",
                title="Diligence findings",
                purpose="Assess strengths, weaknesses, unknowns, and red flags.",
                min_pages=4,
                required_blocks=["risk_register", "source_quality_table"],
            ),
            PremiumSectionSpec(
                id="go_no_go",
                title="Go / no-go decision",
                purpose="Define conditions to proceed, renegotiate, or reject.",
                min_pages=2,
                required_blocks=["decision_matrix", "sensitivity_table"],
            ),
        ],
        "general_research": [
            PremiumSectionSpec(
                id="context",
                title="Context and baseline",
                purpose="Establish the known facts and decision context.",
                min_pages=3,
                required_blocks=["timeline", "evidence_table"],
            ),
            PremiumSectionSpec(
                id="analysis",
                title="Analysis",
                purpose="Develop the core argument and compare interpretations.",
                min_pages=4,
                required_blocks=["chart", "decision_matrix"],
            ),
            PremiumSectionSpec(
                id="implications",
                title="Implications",
                purpose="Translate findings into action and monitoring.",
                min_pages=2,
                required_blocks=["risk_register", "timeline"],
            ),
        ],
    }

    closing = [
        PremiumSectionSpec(
            id="recommendations",
            title="Recommendations and thresholds",
            purpose="Give concrete action rules, not generic advice.",
            min_pages=2,
            required_blocks=["decision_matrix"],
        ),
        PremiumSectionSpec(
            id="risks_and_monitoring",
            title="Risks and monitoring dashboard",
            purpose="Define what can invalidate the answer and how to track it.",
            min_pages=2,
            required_blocks=["risk_register", "timeline"],
        ),
        PremiumSectionSpec(
            id="appendix",
            title="Appendix",
            purpose="Provide source, fact, and calculation backup.",
            min_pages=3,
            required_blocks=["appendix_table"],
        ),
    ]

    return common + type_specific[report_type] + closing


def _visuals_for(report_type: PremiumReportType) -> list[PremiumVisualSpec]:
    visuals = [
        PremiumVisualSpec(
            kind="kpi_grid",
            title="Key metrics",
            purpose="Make the answer scannable and numerically grounded.",
        ),
        PremiumVisualSpec(
            kind="evidence_table",
            title="Evidence table",
            purpose="Tie important claims to sources and reliability tiers.",
        ),
        PremiumVisualSpec(
            kind="decision_matrix",
            title="Decision matrix",
            purpose="Convert analysis into client actions.",
        ),
        PremiumVisualSpec(
            kind="risk_register",
            title="Risk register",
            purpose="Show downside, severity, mitigation, and monitoring.",
        ),
    ]
    if report_type in {"market", "investment", "strategy", "due_diligence"}:
        visuals.append(
            PremiumVisualSpec(
                kind="scenario_matrix",
                title="Scenario matrix",
                purpose="Separate base, upside, and downside outcomes.",
            )
        )
        visuals.append(
            PremiumVisualSpec(
                kind="sensitivity_table",
                title="Sensitivity table",
                purpose="Show how outputs change when key assumptions move.",
            )
        )
    if report_type == "competitive":
        visuals.append(
            PremiumVisualSpec(
                kind="competitive_matrix",
                title="Competitive matrix",
                purpose="Compare players on the dimensions that matter.",
            )
        )
    if report_type == "technical_audit":
        visuals.append(
            PremiumVisualSpec(
                kind="timeline",
                title="Remediation roadmap",
                purpose="Show fix sequence and verification gates.",
            )
        )
    return visuals


def _appendices_for(report_type: PremiumReportType) -> list[PremiumAppendixSpec]:
    appendices = [
        PremiumAppendixSpec(
            title="Fact base",
            purpose="Full list of extracted claims, numbers, and source links.",
        ),
        PremiumAppendixSpec(
            title="Source quality register",
            purpose="Reliability tier, relevance, and limitation per source.",
        ),
        PremiumAppendixSpec(
            title="Open questions and unavailable data",
            purpose="Prevent false precision and show what remains unverified.",
        ),
    ]
    if report_type in {"market", "investment", "strategy"}:
        appendices.append(
            PremiumAppendixSpec(
                title="Assumption and sensitivity appendix",
                purpose="Document scenario inputs and how conclusions shift.",
            )
        )
    if report_type in {"technical_audit", "legal_regulatory", "due_diligence"}:
        appendices.append(
            PremiumAppendixSpec(
                title="Issue register",
                purpose="Detailed finding list with severity and remediation status.",
            )
        )
    return appendices


def _deck_outline_for(report_type: PremiumReportType) -> list[str]:
    base = [
        "Title and decision question",
        "Executive answer",
        "What changed or what matters most",
        "Evidence base and confidence",
        "Key visual 1",
        "Key visual 2",
        "Scenarios or options",
        "Decision matrix",
        "Risks and watchpoints",
        "Recommended next steps",
    ]
    if report_type == "technical_audit":
        base[4] = "Architecture / system map"
        base[5] = "Findings by severity"
        base[6] = "Remediation roadmap"
    elif report_type == "competitive":
        base[4] = "Market map"
        base[5] = "Competitor benchmark"
        base[6] = "Strategic options"
    return base


def _combined_text(question: str, report: FinalReport | None) -> str:
    chunks = [question]
    if report is not None:
        chunks.extend(
            [
                report.executive_summary.main_answer,
                report.main_synthesis,
                report.consensus_section,
                report.conflicts_section,
            ]
        )
    return " ".join(chunks).lower()


def _has(text: str, *needles: str) -> bool:
    return any(needle.lower() in text for needle in needles)


def _decision_context(
    question: str,
    report_type: PremiumReportType,
    audience: PremiumAudience,
) -> str:
    clean = re.sub(r"\s+", " ", question).strip()
    if clean:
        return f"Help a {audience.replace('_', ' ')} answer: {clean}"
    return f"Help a {audience.replace('_', ' ')} make a {report_type.replace('_', ' ')} decision."


def _fact_count(analysis: AnalysisOutput | None) -> int:
    if analysis is None:
        return 0
    high = getattr(analysis, "high_relevance_facts", None) or []
    all_facts = getattr(analysis, "all_numeric_facts", None) or []
    return len(high or all_facts)
