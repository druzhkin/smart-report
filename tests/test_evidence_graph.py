from smart_report.evidence_graph import build_evidence_graph
from smart_report.models import (
    AnalysisOutput,
    ExecutiveSummaryV4,
    FinalReport,
    NumericFact,
    SourceRef,
)


def test_evidence_graph_flags_unsupported_numbered_claim():
    report = FinalReport(
        session_id="eg",
        question="Will prices rise?",
        executive_summary=ExecutiveSummaryV4(
            main_answer="Prices will rise by 15% in 2027.",
            top_findings=["Supply is constrained."],
        ),
        main_synthesis="Short synthesis.",
    )

    graph = build_evidence_graph(report)

    assert graph.summary.claim_count == 2
    assert graph.summary.unsupported >= 1
    assert graph.nodes[0].has_number is True
    assert "matching numeric fact" in " ".join(graph.nodes[0].missing)


def test_evidence_graph_links_numeric_fact_to_claim():
    source = SourceRef(
        url="https://example.com/source",
        title="Primary source",
        confidence="primary",
    )
    fact = NumericFact(
        fact_id="f1",
        value="15%",
        metric="price growth",
        subject="2027",
        sources=[source],
        relevance_to_question="high",
    )
    report = FinalReport(
        session_id="eg",
        question="Will prices rise?",
        executive_summary=ExecutiveSummaryV4(
            main_answer="Prices will rise by 15% in 2027 [1].",
            top_findings=[],
        ),
        main_synthesis="Long enough synthesis.",
    )
    analysis = AnalysisOutput(all_numeric_facts=[fact], high_relevance_facts=[fact])

    graph = build_evidence_graph(report, analysis)

    assert graph.summary.unsupported == 0
    assert graph.summary.numeric_fact_links == 1
    assert graph.nodes[0].status == "supported"
