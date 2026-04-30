from __future__ import annotations

from smart_report.evidence_audit import assess_evidence_support
from smart_report.models import (
    AnalysisOutput,
    ConsensusClaim,
    ExecutiveSummaryV4,
    FinalReport,
    NumericFact,
    QualitativeFact,
    Source,
    SourceRef,
)


def test_evidence_audit_scores_supported_claims():
    report = FinalReport(
        session_id="evidence-audit",
        question="Assess market outlook",
        executive_summary=ExecutiveSummaryV4(
            main_answer="The base case is 7% growth. [1][2]",
            top_findings=["Demand improved by 7%. [1][2]"],
        ),
        all_sources=[
            Source(title="Official", url="https://example.com/official", reliability="high"),
            Source(title="Industry", url="https://example.com/industry", reliability="high"),
        ],
    )
    analysis = AnalysisOutput(
        consensus=[
            ConsensusClaim(
                claim="Demand improved by 7%. [1]",
                supporting_sources=["https://example.com/official", "https://example.com/industry"],
                confidence="high",
            )
        ],
        high_relevance_facts=[
            NumericFact(
                fact_id="f1",
                value="7%",
                metric="growth",
                subject="demand",
                relevance_to_question="high",
                sources=[
                    SourceRef(
                        url="https://example.com/official",
                        title="Official",
                        confidence="primary",
                    )
                ],
            )
        ],
    )

    audit = assess_evidence_support(report, analysis)

    assert audit.overall_score >= 70
    assert audit.unsupported == 0
    assert audit.supported >= 2


def test_evidence_audit_flags_unsupported_executive_claim():
    report = FinalReport(
        session_id="evidence-audit",
        question="Assess market outlook",
        executive_summary=ExecutiveSummaryV4(
            main_answer="The market will accelerate by 15% next year.",
            top_findings=["Supply will collapse sharply."],
        ),
        all_sources=[],
    )

    audit = assess_evidence_support(report, None)

    assert audit.overall_score < 35
    assert audit.unsupported == 2
    assert all(item.missing_signals for item in audit.claim_audits)


def test_evidence_audit_matches_numeric_ranges_across_formatting():
    report = FinalReport(
        session_id="evidence-audit",
        question="Assess market outlook",
        executive_summary=ExecutiveSummaryV4(
            main_answer="Base case price growth is +15-20% over two years."
        ),
    )
    analysis = AnalysisOutput(
        high_relevance_facts=[
            NumericFact(
                fact_id="f1",
                value="+15% до +20%",
                metric="price growth",
                subject="base case",
                relevance_to_question="high",
            )
        ]
    )

    audit = assess_evidence_support(report, analysis)

    assert audit.claim_audits[0].numeric_matches == 1
    assert audit.claim_audits[0].status == "partial"


def test_evidence_audit_matches_qualitative_facts_with_sources():
    report = FinalReport(
        session_id="evidence-audit",
        question="Assess funding landscape",
        executive_summary=ExecutiveSummaryV4(main_answer=""),
        ranking=[
            {
                "label": "EU transition funding",
                "rationale": (
                    "Concessional financing below market rates is useful for projects "
                    "that need additional capital."
                ),
                "evidence_strength": "medium",
            }
        ],
    )
    analysis = AnalysisOutput(
        all_qualitative_facts=[
            QualitativeFact(
                fact_id="q1",
                statement=(
                    "Concessional financing below market rates can support projects "
                    "that require additional capital during deployment."
                ),
                subject="EU transition funding",
                sources=[
                    SourceRef(
                        url="https://example.com/funding",
                        title="Funding programme",
                        confidence="primary",
                    )
                ],
                relevance_to_question="high",
            )
        ]
    )

    audit = assess_evidence_support(report, analysis)

    assert audit.unsupported == 0
    assert audit.claim_audits[0].qualitative_matches == 1
    assert audit.claim_audits[0].status == "partial"


def test_evidence_audit_ignores_formula_digits_when_matching_numeric_facts():
    report = FinalReport(
        session_id="evidence-audit",
        question="Compare subsidies",
        executive_summary=ExecutiveSummaryV4(main_answer=""),
        key_numbers_highlight=[
            {
                "label": "maximum 45Q credit for CO₂ removal",
                "value": "$180/t",
                "source_ref": "",
                "importance": "headline",
            }
        ],
    )
    analysis = AnalysisOutput(
        high_relevance_facts=[
            NumericFact(
                fact_id="f45q",
                value="$180 per tonne CO2 removed",
                metric="maximum subsidy under US 45Q credit scheme",
                subject="United States 45Q tax credit scheme",
                relevance_to_question="high",
                sources=[
                    SourceRef(
                        url="https://example.com/45q",
                        title="45Q",
                        confidence="primary",
                    )
                ],
            )
        ]
    )

    audit = assess_evidence_support(report, analysis)

    assert audit.claim_audits[0].numeric_matches == 1
    assert audit.claim_audits[0].status == "partial"


def test_evidence_audit_treats_subscript_formula_numbers_as_numeric_claims():
    report = FinalReport(
        session_id="evidence-audit",
        question="Assess infrastructure",
        executive_summary=ExecutiveSummaryV4(
            main_answer="CO₂ transport infrastructure unlocks the carbon removal pathway."
        ),
    )
    analysis = AnalysisOutput(
        high_relevance_facts=[
            NumericFact(
                fact_id="co2",
                value="CO2 transport infrastructure",
                metric="infrastructure dependency",
                subject="carbon removal pathway",
                relevance_to_question="high",
            )
        ]
    )

    audit = assess_evidence_support(report, analysis)

    assert audit.claim_audits[0].has_number is True
