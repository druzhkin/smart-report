from __future__ import annotations

from smart_report.models import ChartSpec, ExecutiveSummaryV4, FinalReport, KeyNumberHighlight, Source, Table, V4Session
from smart_report.quality_contract import audit_claim_support, build_execution_trace, evaluate_enterprise_quality


def test_enterprise_quality_blocks_unsupported_text_only_report() -> None:
    report = FinalReport(
        session_id="eq-weak",
        question="peer-reviewed evidence on LLM observability benchmarks",
        executive_summary=ExecutiveSummaryV4(
            main_answer="LLM observability benchmarks are mature enough for board adoption.",
            top_findings=[
                "Benchmark coverage is broad across production monitoring workflows.",
                "Academic evidence supports the maturity claim.",
                "Vendors can safely standardize on one framework.",
            ],
        ),
        main_synthesis="Unsupported assertion. " * 40,
        all_sources=[Source(title="Vendor blog", url="https://example.com/blog", tool="other")],
    )

    result = evaluate_enterprise_quality(report)

    assert result.passed is False
    assert result.verdict == "blocked"
    assert any(issue.code == "enterprise_research_policy_failed" for issue in result.issues)
    assert any(issue.code == "enterprise_unsupported_claims" for issue in result.issues)
    assert result.visual_intelligence.visual_count == 0


def test_enterprise_quality_audits_claim_refs_visuals_and_trace() -> None:
    report = _strong_report()
    session = V4Session(
        session_id="eq-strong",
        raw_question=report.question,
        final_report=report,
        status="synthesized",
        created_at="2026-05-02T00:00:00",
        total_cost_rub=1200.0,
    )
    session.followup_reports = []
    session.pending_dr_jobs = [
        {
            "task_id": "paper-1",
            "service": "paper_search",
            "mode": "standard",
            "state": "completed",
        }
    ]

    claim_audit = audit_claim_support(report)
    trace = build_execution_trace(session)
    result = evaluate_enterprise_quality(report, session=session)

    assert claim_audit.support_ratio > 0.8
    assert trace.paper_search_used is True
    assert result.execution_trace is not None
    assert result.execution_trace.services_used == ["paper_search"]
    assert result.visual_intelligence.useful_visual_count >= 3


def _strong_report() -> FinalReport:
    return FinalReport(
        session_id="eq-strong",
        question="peer-reviewed evidence on LLM observability benchmarks",
        executive_summary=ExecutiveSummaryV4(
            main_answer=(
                "Peer-reviewed and academic-indexed evidence supports using LLM observability "
                "benchmarks as one input to enterprise governance, but not as a standalone "
                "buying decision [REF:https://arxiv.org/abs/2501.1]."
            ),
            top_findings=[
                "Academic evidence exists but remains method-fragmented [REF:https://doi.org/10.1000/example].",
                "Benchmark datasets are useful only when paired with production traces [REF:https://semanticscholar.org/paper/abc].",
                "Decision teams should triangulate papers, vendor docs, and field telemetry [REF:https://arxiv.org/abs/2501.1].",
            ],
        ),
        main_synthesis=("The evidence base is useful but incomplete [REF:https://arxiv.org/abs/2501.1]. " * 90),
        consensus_section=("Multiple academic sources agree on traceability requirements [REF:https://doi.org/10.1000/example]."),
        conflicts_section=("Methods diverge on offline benchmark transferability [REF:https://semanticscholar.org/paper/abc]."),
        gaps_filled_section=("Production incident datasets remain the largest missing input [REF:https://arxiv.org/abs/2501.1]."),
        all_sources=[
            Source(title="arXiv paper", url="https://arxiv.org/abs/2501.1", tool="paper_search_mcp:arxiv", reliability="high"),
            Source(title="DOI paper", url="https://doi.org/10.1000/example", tool="paper_search_mcp:crossref", reliability="high"),
            Source(title="Semantic Scholar", url="https://semanticscholar.org/paper/abc", tool="paper_search_mcp:semantic", reliability="high"),
            Source(title="GitHub benchmark", url="https://github.com/example/benchmark", reliability="medium"),
            Source(title="Vendor docs", url="https://docs.example.com", reliability="medium"),
            Source(title="ACM", url="https://acm.org/example", reliability="high"),
            Source(title="IEEE", url="https://ieee.org/example", reliability="high"),
            Source(title="Papers with Code", url="https://paperswithcode.com/example", reliability="medium"),
        ],
        charts=[
            ChartSpec(chart_type="bar", title="Evidence coverage", caption="Academic sources cover methodology, not adoption.", data={"labels": ["papers"], "values": [3]}),
            ChartSpec(chart_type="line", title="Benchmark maturity", caption="Coverage rises but remains uneven.", data={"labels": ["2024", "2025"], "values": [1, 3]}),
        ],
        tables=[
            Table(title="Source matrix", columns=["Source", "Use"], rows=[["arXiv", "methodology"]], caption="Academic papers support method quality.", source_ref="https://arxiv.org/abs/2501.1")
        ],
        key_numbers_highlight=[
            KeyNumberHighlight(value="3", label="academic source families", source_ref="https://arxiv.org/abs/2501.1", importance="primary")
        ],
    )
