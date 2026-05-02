from __future__ import annotations

from smart_report.models import (
    AnalysisOutput,
    Conflict,
    ConsensusClaim,
    Gap,
    NormalizedReport,
    NumericFact,
    SourceRef,
    UploadedMarkdown,
)
from smart_report.research_brief import evaluate_research_brief


def test_research_brief_blocks_thin_academic_package() -> None:
    result = evaluate_research_brief(
        "peer-reviewed benchmark evidence for LLM observability",
        source_reports=[
            UploadedMarkdown(
                filename="one.md",
                content="Vendor blog https://example.com/blog",
                detected_tool="other",
            )
        ],
        normalized_reports=[],
        analysis=AnalysisOutput(),
    )

    assert result.passed is False
    assert result.verdict == "blocked"
    assert {issue.code for issue in result.issues} >= {
        "research_brief_too_few_reports",
        "research_brief_policy_failed",
        "research_brief_facts_too_thin",
        "research_brief_no_counter_evidence",
    }


def test_research_brief_accepts_source_fact_counterevidence_and_visual_plan() -> None:
    sources = [
        SourceRef(title="arXiv", url="https://arxiv.org/abs/2501.1", confidence="primary"),
        SourceRef(title="PubMed", url="https://pubmed.ncbi.nlm.nih.gov/1", confidence="primary"),
        SourceRef(title="DOI", url="https://doi.org/10.1000/example", confidence="primary"),
        SourceRef(title="Semantic", url="https://semanticscholar.org/paper/abc", confidence="primary"),
        SourceRef(title="ACM", url="https://acm.org/example", confidence="primary"),
        SourceRef(title="Benchmark", url="https://paperswithcode.com/benchmark/example", confidence="secondary"),
    ]
    facts = [
        NumericFact(
            fact_id=f"f{i}",
            value=str(10 + i),
            metric="benchmark score",
            subject=f"method {i}",
            timeframe="2026",
            relevance_to_question="high",
            sources=[sources[i % len(sources)]],
        )
        for i in range(10)
    ]
    normalized = [
        NormalizedReport(
            source_tool="paper_search_mcp",
            source_filename="papers.md",
            raw_text="Academic evidence",
            extracted_sources_inventory=sources,
            extracted_numeric_facts=facts,
        )
    ]
    analysis = AnalysisOutput(
        consensus=[
            ConsensusClaim(
                claim="Benchmarks are useful but incomplete.",
                supporting_sources=["arXiv", "Semantic"],
                confidence="high",
            )
        ],
        conflicts=[
            Conflict(
                topic="Offline-to-production transferability",
                source_a="arXiv",
                claim_a="offline benchmark transfers",
                source_b="Semantic",
                claim_b="transferability remains limited",
                resolution_hint="Use benchmark evidence only with production telemetry.",
                importance="critical",
            )
        ],
        gaps=[
            Gap(
                topic="Production traces",
                why_critical="Benchmarks need field validation.",
                what_to_find="Incident telemetry",
                candidate_sources=["vendor docs"],
            )
        ],
    )

    result = evaluate_research_brief(
        "peer-reviewed benchmark evidence for LLM observability",
        source_reports=[
            UploadedMarkdown(filename="a.md", content=" ".join(src.url for src in sources), detected_tool="paper_search_mcp"),
            UploadedMarkdown(filename="b.md", content="https://paperswithcode.com/benchmark/example", detected_tool="paper_search_mcp"),
        ],
        normalized_reports=normalized,
        analysis=analysis,
    )

    assert result.passed is True
    assert result.verdict == "ready_for_synthesis"
    assert result.source_mix.academic_sources >= 4
    assert result.freshness.high_relevance_numeric_facts == 10
    assert sum(1 for item in result.visual_plan if item.ready) >= 5
