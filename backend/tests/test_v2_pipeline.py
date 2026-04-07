from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.schemas.report_schema import ReportOutput, ReportSection, ReportStatus
from backend.schemas.research_result import ResearchResult, Source
from backend.v2.audit import audit_report_package
from backend.v2.grounding import extract_numeric_facts
from backend.v2.intake import build_request_spec, build_task_spec
from backend.v2.models import (
    ClaimRecord,
    CoverageReport,
    EvidenceRecord,
    QualityAssessment,
    QualityDimensionScore,
    QuestionKind,
    ResearchPlan,
    ResearchQuestion,
    SearchCandidate,
    SourceLedgerEntry,
    SourceSnapshot,
    SourceType,
)
from backend.v2.pipeline import (
    LATERAL_REVIEW_PROMPT,
    _adjacent_to_primary_question_id,
    _build_stack_backfill_queries,
    _build_live_research_queries,
    _build_live_evidence,
    _language_name,
    _sanitize_llm_markdown,
    build_claim_table,
    build_evidence_ledger,
    build_research_plan,
    build_adjacent_question_candidates,
    build_decision_triggers,
    build_draft_run,
    detect_contradictions,
    execute_report_run,
    select_adjacent_questions,
)
from backend.v2.quality import assess_report_quality, build_revision_focus
from backend.v2.repository import FileRunRepository


async def _run_pipeline(repo: FileRunRepository, run_id: str, prompt: str):
    request_spec = build_request_spec(prompt, depth="standard")
    task_spec = build_task_spec(request_spec)
    summary = build_draft_run(run_id, prompt, depth="standard")
    summary.request_spec = request_spec
    summary.task_spec = task_spec
    repo.create_run(summary)

    events = []

    async def emit(event) -> None:
        events.append(event)

    final_summary = await execute_report_run(repo, summary, task_spec, emit)
    return final_summary, events


def _write_quality_files(package_dir: Path, score: float = 72.0, iterations: list[dict] | None = None) -> None:
    if iterations is None:
        iterations = [
            {
                "iteration": 0,
                "assessment": {"overall_score": score, "verdict": "usable"},
                "delta_from_previous": 0.0,
                "improved": False,
                "consecutive_improvements": 0,
                "revision_focus": [],
                "notes": [],
            }
        ]
    (package_dir / "quality_assessment.json").write_text(
        json.dumps({"overall_score": score, "verdict": "usable"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (package_dir / "quality_iterations.json").write_text(
        json.dumps(iterations, ensure_ascii=False),
        encoding="utf-8",
    )


def test_pipeline_generates_releaseable_report_package(tmp_path: Path) -> None:
    repo = FileRunRepository(root=str(tmp_path / "runs"), reports_root=str(tmp_path / "reports"))
    final_summary, events = asyncio.run(
        _run_pipeline(
            repo,
            "llm-observability-test",
            "Evaluate LLM observability platforms for an enterprise document workflow product.",
        )
    )

    report_dir = repo.report_dir("llm-observability-test")
    required_files = {
        "report.md",
        "report.html",
        "report.pdf",
        "sources.json",
        "claim_table.json",
        "adjacent_questions.json",
        "critique_findings.json",
        "decision_triggers.json",
        "lateral_review.json",
        "analysis_brief.json",
        "coverage_report.json",
        "quality_assessment.json",
        "quality_iterations.json",
        "audit_summary.json",
    }

    assert final_summary.status.value == "completed"
    assert required_files.issubset({path.name for path in report_dir.iterdir()})
    assert len(events) >= 6

    report_markdown = (report_dir / "report.md").read_text(encoding="utf-8")
    assert "[Evidence:" in report_markdown
    assert "## Option Space" in report_markdown
    assert "## What Could Change The Recommendation" in report_markdown

    claim_table = json.loads((report_dir / "claim_table.json").read_text(encoding="utf-8"))
    assert claim_table

    audit_summary = audit_report_package(report_dir)
    assert audit_summary.release_status in {"released", "blocked"}


def test_audit_blocks_incomplete_package(tmp_path: Path) -> None:
    package_dir = tmp_path / "broken-package"
    package_dir.mkdir(parents=True)
    (package_dir / "report.md").write_text(
        "# Broken Report\n\n## Recommendation and Decision Posture\n\n- Recommend platform A immediately.\n",
        encoding="utf-8",
    )
    (package_dir / "report.html").write_text("<html><body>broken</body></html>", encoding="utf-8")
    (package_dir / "sources.json").write_text("[]", encoding="utf-8")
    (package_dir / "claim_table.json").write_text("[]", encoding="utf-8")
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text("{}", encoding="utf-8")

    audit_summary = audit_report_package(package_dir)

    assert audit_summary.release_status == "blocked"
    assert any("lacks evidence linkage" in failure for failure in audit_summary.failures)


def test_adjacent_question_selection_prioritizes_alternatives_and_counterarguments() -> None:
    request_spec = build_request_spec("Evaluate Sonar for enterprise AI research workflows.", depth="standard")
    task_spec = build_task_spec(request_spec)
    candidates = build_adjacent_question_candidates(task_spec)
    selected = select_adjacent_questions(task_spec, candidates)
    triggers = build_decision_triggers(task_spec)

    assert len(selected) == 4
    assert selected[0].kind.value == "adjacent_alternative"
    assert selected[1].kind.value == "adjacent_counterargument"
    assert any(trigger.label for trigger in triggers)


def test_lateral_review_prompt_formats_without_key_errors() -> None:
    rendered = LATERAL_REVIEW_PROMPT.format(language_name=_language_name("en"))
    assert '"adjacent_questions"' in rendered
    assert '"critique_findings"' in rendered
    assert '"decision_triggers"' in rendered


def test_build_revision_focus_skips_non_actionable_source_dimensions() -> None:
    assessment = QualityAssessment(
        overall_score=61.0,
        verdict="thin",
        strengths=[],
        weaknesses=[],
        rewrite_priorities=[
            "Bring in more authoritative and diverse sources, especially official docs, benchmarks, and mature project material.",
            "Increase section depth, exhibits, and analytical density rather than adding filler.",
        ],
        dimensions=[
            QualityDimensionScore(dimension="source_authority", score=32.0, rationale="", raw_metrics={}),
            QualityDimensionScore(dimension="coverage", score=40.0, rationale="", raw_metrics={}),
            QualityDimensionScore(dimension="decision_usefulness", score=48.0, rationale="", raw_metrics={}),
            QualityDimensionScore(dimension="presentation_depth", score=53.0, rationale="", raw_metrics={}),
            QualityDimensionScore(dimension="lateral_breadth", score=58.0, rationale="", raw_metrics={}),
        ],
        metrics={},
    )

    focus = build_revision_focus(assessment)

    assert "source authority" not in focus
    assert "coverage" not in focus
    assert any(item in focus for item in ["decision usefulness", "presentation depth", "lateral breadth"])


def test_detect_contradictions_ignores_unrelated_numeric_claims() -> None:
    claims = [
        ClaimRecord(
            claim_id="C-1",
            statement="Enterprise architecture tools market reaches 1.28 billion dollars in 2025.",
            question_id="q1",
            supporting_evidence_ids=["E-1"],
            source_ids=["S-1"],
            confidence=0.9,
        ),
        ClaimRecord(
            claim_id="C-2",
            statement="84 percent of enterprises operate across at least two hyperscalers.",
            question_id="q1",
            supporting_evidence_ids=["E-2"],
            source_ids=["S-2"],
            confidence=0.9,
        ),
    ]

    notes = detect_contradictions(claims)

    assert notes == []
    assert all(not claim.contradiction_notes for claim in claims)


def test_build_evidence_ledger_respects_source_question_links() -> None:
    plan = build_research_plan(
        build_task_spec(
            build_request_spec(
                "Design the best LLM and GitHub stack for web search and deep research with explicit build-vs-buy boundaries.",
                depth="deep",
            ),
            answers={"decision-context": "Choose the core architecture."},
        )
    )
    q1 = plan.primary_questions[0]
    q2 = plan.primary_questions[1]
    snapshots = [
        SourceSnapshot(
            source_id="S-1",
            url="https://docs.example.com/claude",
            title="Claude web search documentation",
            content="Claude API supports web search with citations for grounded research workflows.",
        ),
        SourceSnapshot(
            source_id="S-2",
            url="https://github.com/assafelovic/gpt-researcher",
            title="GPT Researcher repository",
            content="GPT Researcher orchestrates web research and long-form report generation with citation support.",
        ),
    ]
    evidence = build_evidence_ledger(
        ResearchPlan(primary_questions=[q1, q2]),
        snapshots,
        {"S-1": 0.95, "S-2": 0.95},
        {"S-1": {q1.question_id}, "S-2": {q2.question_id}},
    )

    assert {item.question_id for item in evidence if item.source_id == "S-1"} == {q1.question_id}
    assert {item.question_id for item in evidence if item.source_id == "S-2"} == {q2.question_id}


def test_build_claim_table_keeps_identical_statement_for_different_questions() -> None:
    claims = build_claim_table(
        [
            EvidenceRecord(
                evidence_id="E-1",
                question_id="q3",
                source_id="S-1",
                claim="LangGraph provides durable execution and checkpointed state for long-running research agents.",
                snippet="LangGraph provides durable execution and checkpointed state for long-running research agents.",
                confidence=0.9,
            ),
            EvidenceRecord(
                evidence_id="E-2",
                question_id="q4",
                source_id="S-1",
                claim="LangGraph provides durable execution and checkpointed state for long-running research agents.",
                snippet="LangGraph provides durable execution and checkpointed state for long-running research agents.",
                confidence=0.9,
            ),
        ]
    )

    assert len(claims) == 2
    assert {claim.question_id for claim in claims} == {"q3", "q4"}


def test_build_evidence_ledger_filters_navigation_and_install_commands() -> None:
    question = ResearchQuestion(
        question_id="q2",
        question="Which GitHub projects are mature enough to use for orchestration, search integration, or deep research in production?",
        kind=QuestionKind.PRIMARY,
        priority=1,
        required_evidence_count=2,
    )
    snapshots = [
        SourceSnapshot(
            source_id="S-1",
            url="https://docs.example.com/gptr",
            title="GPT Researcher",
            excerpt="copy Copy chevron-down Integrations GPT Researcher",
            content=(
                "Clone the repository: Copy git clone https://github.com/assafelovic/gpt-researcher.git. "
                "The project supports long-form research with citations and parallel evidence collection."
            ),
        )
    ]

    evidence = build_evidence_ledger(
        ResearchPlan(primary_questions=[question]),
        snapshots,
        {"S-1": 0.95},
        {"S-1": {"q2"}},
    )

    assert evidence
    assert all("git clone" not in item.claim.lower() for item in evidence)
    assert all("copy chevron-down" not in item.claim.lower() for item in evidence)


def test_build_live_evidence_filters_stack_topic_api_chrome_and_offtopic_architecture() -> None:
    request_spec = build_request_spec(
        "Design the default Smart Report v2 architecture for 2026: which LLMs, managed search APIs, open-source frameworks, and GitHub repos should power decision-grade web research and long-form deep-analysis reports that beat Perplexity on traceability, controllability, and revision quality?",
        depth="deep",
    )
    task_spec = build_task_spec(request_spec, answers={"decision-context": "Choose the default Smart Report v2 stack."})
    sources = [
        SourceLedgerEntry(
            source_id="S-1",
            url="https://firecrawl.dev/docs/search",
            title="Search - Firecrawl Docs",
            domain="firecrawl.dev",
            source_type=SourceType.OFFICIAL_DOCUMENTATION,
            publisher="firecrawl.dev",
            reliability_score=0.95,
            selection_reason="docs",
            question_links=["q3"],
        ),
        SourceLedgerEntry(
            source_id="S-2",
            url="https://example.com/matter-stack",
            title="Matter protocol stack documentation",
            domain="example.com",
            source_type=SourceType.OFFICIAL_DOCUMENTATION,
            publisher="example.com",
            reliability_score=0.9,
            selection_reason="docs",
            question_links=["q3"],
        ),
    ]
    rows = [
        {
            "question_id": "q3",
            "query": "Which stack and architecture best satisfy the Smart Report goal and outperform Perplexity?",
            "source_urls": ["https://firecrawl.dev/docs/search"],
            "findings": [
                "Body application/json query string required maximum string length and sources to search.",
                "Firecrawl provides open-source, self-hostable search and extraction with browser automation for traceable report workflows.",
            ],
        },
        {
            "question_id": "q3",
            "query": "Which stack and architecture best satisfy the Smart Report goal and outperform Perplexity?",
            "source_urls": ["https://example.com/matter-stack"],
            "findings": [
                "Matter protocol stack outperforms Perplexity on interoperability benchmarks for smart devices.",
            ],
        },
    ]

    evidence = _build_live_evidence(rows, sources, task_spec)

    assert len(evidence) == 1
    assert "firecrawl provides open-source" in evidence[0].claim.lower()


def test_detect_contradictions_ignores_year_markers_when_other_metrics_exist() -> None:
    claims = [
        ClaimRecord(
            claim_id="C-1",
            statement="In 2026 DeepSeek-V3.2 is priced around $2.5 per million tokens for this workload.",
            question_id="q1",
            supporting_evidence_ids=["E-1"],
            source_ids=["S-1"],
            confidence=0.9,
        ),
        ClaimRecord(
            claim_id="C-2",
            statement="In 2026 Claude 4.6 remains closer to $5 per million tokens on comparable usage.",
            question_id="q1",
            supporting_evidence_ids=["E-2"],
            source_ids=["S-2"],
            confidence=0.9,
        ),
    ]

    notes = detect_contradictions(claims)

    assert notes == []


def test_detect_contradictions_flags_same_subject_same_metric() -> None:
    claims = [
        ClaimRecord(
            claim_id="C-1",
            statement="DeepSeek API pricing is about $2.5 per million tokens for input traffic.",
            question_id="q1",
            supporting_evidence_ids=["E-1"],
            source_ids=["S-1"],
            confidence=0.9,
        ),
        ClaimRecord(
            claim_id="C-2",
            statement="DeepSeek API pricing is closer to $6 per million tokens for input traffic.",
            question_id="q1",
            supporting_evidence_ids=["E-2"],
            source_ids=["S-2"],
            confidence=0.9,
        ),
    ]

    notes = detect_contradictions(claims)

    assert len(notes) == 1
    assert "DeepSeek".lower() in notes[0].lower()
    assert all(claim.contradiction_notes for claim in claims)


def test_detect_contradictions_ignores_different_models_with_shared_pro_suffix() -> None:
    claims = [
        ClaimRecord(
            claim_id="C-1",
            statement="GPT-5.4 Pro reaches 50.0% on advanced reasoning evaluations.",
            question_id="q1",
            supporting_evidence_ids=["E-1"],
            source_ids=["S-1"],
            confidence=0.9,
        ),
        ClaimRecord(
            claim_id="C-2",
            statement="Gemini 2.5 Pro scores 86.4% on GPQA Diamond.",
            question_id="q1",
            supporting_evidence_ids=["E-2"],
            source_ids=["S-2"],
            confidence=0.9,
        ),
    ]

    notes = detect_contradictions(claims)

    assert notes == []
    assert all(not claim.contradiction_notes for claim in claims)


def test_detect_contradictions_ignores_comparison_sentence_that_mentions_other_model_name() -> None:
    claims = [
        ClaimRecord(
            claim_id="C-1",
            statement="GPT-5.4 Pro achieves 50.0% on Epoch AI benchmarks and 92.8% on GPQA Diamond.",
            question_id="q1",
            supporting_evidence_ids=["E-1"],
            source_ids=["S-1"],
            confidence=0.9,
        ),
        ClaimRecord(
            claim_id="C-2",
            statement="Claude Opus 4.6 ranks immediately behind GPT-5.4 Pro at 40.7% on Epoch AI benchmarks and 91.3% on GPQA Diamond.",
            question_id="q1",
            supporting_evidence_ids=["E-2"],
            source_ids=["S-2"],
            confidence=0.9,
        ),
    ]

    notes = detect_contradictions(claims)

    assert notes == []
    assert all(not claim.contradiction_notes for claim in claims)


def test_detect_contradictions_ignores_different_api_price_surfaces() -> None:
    claims = [
        ClaimRecord(
            claim_id="C-1",
            statement="web_search costs $0.005 per invocation while fetch_url costs $0.0005 per invocation.",
            question_id="q4",
            supporting_evidence_ids=["E-1"],
            source_ids=["S-1"],
            confidence=0.9,
        ),
        ClaimRecord(
            claim_id="C-2",
            statement="Search API is priced at $5.00 per 1K requests with no token costs.",
            question_id="q4",
            supporting_evidence_ids=["E-2"],
            source_ids=["S-2"],
            confidence=0.9,
        ),
    ]

    notes = detect_contradictions(claims)

    assert notes == []
    assert all(not claim.contradiction_notes for claim in claims)


def test_extract_numeric_facts_ignores_model_versions_but_keeps_real_metrics() -> None:
    facts = extract_numeric_facts(
        "DeepSeek-V3.2 cuts costs by 40-60% while Claude 4.6 remains stronger on reasoning quality."
    )

    raw_values = {fact.raw for fact in facts}
    assert "3.2" not in raw_values
    assert "4.6" not in raw_values
    assert any("40" in value or "60" in value for value in raw_values)


def test_extract_numeric_facts_uses_local_subjects_for_comparison_sentences() -> None:
    facts = extract_numeric_facts(
        "Claude Opus 4.6 ranks immediately behind GPT-5.4 Pro at 40.7% on Epoch AI benchmarks and 91.3% on GPQA Diamond."
    )

    benchmark_facts = [fact for fact in facts if fact.family in {"benchmark", "ratio"}]
    assert benchmark_facts
    assert all("gpt-5.4" not in fact.subjects for fact in benchmark_facts)


def test_live_evidence_uses_primary_question_id_hint() -> None:
    source = SourceLedgerEntry(
        url="https://example.com/source",
        title="Source",
        domain="example.com",
        source_type=SourceType.VENDOR_PAGE,
        reliability_score=0.82,
        selection_reason="test",
        question_links=["aq1"],
    )
    rows = [
        {
            "question_id": "aq1",
            "primary_question_id": "q4",
            "findings": ["This finding contains enough detail about risk, tradeoffs, and switch conditions to count as evidence."],
            "source_urls": ["https://example.com/source"],
        }
    ]

    evidence = _build_live_evidence(rows, [source])

    assert evidence
    assert evidence[0].question_id == "q4"


def test_live_evidence_filters_heading_like_noise() -> None:
    source = SourceLedgerEntry(
        url="https://github.com/langchain-ai/open_deep_research",
        title="open_deep_research",
        domain="github.com",
        source_type=SourceType.OFFICIAL_DOCUMENTATION,
        reliability_score=0.95,
        selection_reason="test",
        question_links=["q2"],
    )
    rows = [
        {
            "question_id": "q2",
            "query": "Which GitHub projects are mature enough for deep research orchestration?",
            "findings": [
                "### Recommended Projects by Capability | Project | Strengths |",
                "**open_deep_research** is a LangGraph-based open-source deep research project with configurable provider routing and production-oriented evaluation scaffolding.",
            ],
            "source_urls": ["https://github.com/langchain-ai/open_deep_research"],
        }
    ]

    evidence = _build_live_evidence(rows, [source])

    assert len(evidence) == 1
    assert "Recommended Projects by Capability" not in evidence[0].claim
    assert "open_deep_research" in evidence[0].claim


def test_adjacent_boundary_question_maps_to_stack_decision_question() -> None:
    request_spec = build_request_spec(
        "Design the best LLM and GitHub stack for web search and deep research with explicit build-vs-buy boundaries.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={"decision-context": "Choose the core architecture that should beat Perplexity."},
    )
    plan = build_research_plan(task_spec)
    question = ResearchQuestion(
        question_id="aq4",
        question="How does the proposed DeepSeek-R1 + Claude + LangGraph stack quantitatively outperform Perplexity on traceability metrics, revision accuracy, and cost per query?",
        kind=QuestionKind.ADJACENT_BOUNDARY,
        priority=1,
        required_evidence_count=1,
    )

    mapped = _adjacent_to_primary_question_id(plan, question)

    assert mapped == "q3"


def test_live_research_queries_prioritize_stack_specific_angles_for_llm_search_topics() -> None:
    request_spec = build_request_spec(
        "Design a decision-grade architecture for an evidence-first research product that beats consumer answer engines on traceability and revision quality by combining managed search APIs with open-source orchestration frameworks. Compare candidate model and framework stacks with explicit build-vs-buy boundaries.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the core architecture for the next product iteration.",
            "geography": "global",
        },
    )
    plan = build_research_plan(task_spec)

    queries = _build_live_research_queries(task_spec, plan)

    assert queries
    assert queries[0][1].startswith("Primary research question:")
    assert "managed search APIs" in queries[0][1]
    assert "LangChain/LangGraph" in queries[0][1]
    assert "Ignore generic product-architecture literature" in queries[0][1]
    assert any("Do not answer with standalone observability vendors" in prompt for _, prompt in queries)


def test_stack_backfill_queries_target_official_docs_for_stack_research_topics() -> None:
    request_spec = build_request_spec(
        "Design the best LLM and GitHub stack for web search and deep research with explicit build-vs-buy boundaries.",
        depth="deep",
    )
    task_spec = build_task_spec(request_spec, answers={"decision-context": "Choose the core architecture."})

    queries = _build_stack_backfill_queries(task_spec)

    assert queries
    assert ("q2", "gpt-researcher github official docs") in queries
    assert ("q3", "Tavily docs extract crawl pricing") in queries
    assert ("q3", "Langfuse docs traces evaluations self hosting") in queries
    assert ("q4", "AWS agentic AI frameworks LangGraph tradeoffs") in queries


def test_sanitize_llm_markdown_removes_broken_footnotes_and_mojibake() -> None:
    cleaned = _sanitize_llm_markdown(
        "The stack wins on traceabilityвЂ”but only at scale [1].\n\nBudget dominance в†’ simpler stack [2 from q4].\n\n(Word count: 512)"
    )

    assert "вЂ" not in cleaned
    assert "в†" not in cleaned
    assert "[1]" not in cleaned
    assert "[2 from q4]" not in cleaned
    assert "Word count" not in cleaned
    assert "traceability-but only at scale" in cleaned
    assert "Budget dominance -> simpler stack" in cleaned


def test_audit_ignores_action_substring_inside_abstraction(tmp_path: Path) -> None:
    package_dir = tmp_path / "browser-agents-like"
    package_dir.mkdir(parents=True)
    (package_dir / "report.md").write_text(
        "\n".join(
            [
                "# Browser agents",
                "",
                "## Comparative Analysis",
                "",
                "- Which stacks are best for deterministic control versus agent abstraction?",
                "",
                "## Recommendation and Decision Posture",
                "",
                "- Bounded recommendation: evidence is informative but not strong enough for an unqualified winner call.",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (package_dir / "sources.json").write_text('[{"url": "https://playwright.dev/"}]', encoding="utf-8")
    (package_dir / "claim_table.json").write_text('[{"claim_id": "C-1"}]', encoding="utf-8")
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text("{}", encoding="utf-8")
    _write_quality_files(package_dir)

    audit_summary = audit_report_package(package_dir)

    assert not any("lacks evidence linkage" in failure for failure in audit_summary.failures)


def test_audit_ignores_recommendation_language_inside_sources_section(tmp_path: Path) -> None:
    package_dir = tmp_path / "source-language-does-not-count"
    package_dir.mkdir(parents=True)
    (package_dir / "report.md").write_text(
        "\n".join(
            [
                "# Model landscape",
                "",
                "## Recommendation and Decision Posture",
                "",
                "- Bounded recommendation: evidence is informative but not strong enough for an unqualified winner call.",
                "",
                "## Sources",
                "",
                "- [Recommended open models list](https://example.com/recommended-models)",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (package_dir / "sources.json").write_text('[{"url": "https://example.com/recommended-models"}]', encoding="utf-8")
    (package_dir / "claim_table.json").write_text('[{"claim_id": "C-1"}]', encoding="utf-8")
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text("{}", encoding="utf-8")
    _write_quality_files(package_dir)

    audit_summary = audit_report_package(package_dir)

    assert not any("lacks evidence linkage" in failure for failure in audit_summary.failures)


def test_audit_allows_legitimate_self_critique_language(tmp_path: Path) -> None:
    package_dir = tmp_path / "self-critique-allowed"
    package_dir.mkdir(parents=True)
    (package_dir / "report.md").write_text(
        "\n".join(
            [
                "# Stack review",
                "",
                "## Option Space",
                "",
                "- Add a self-critique stage to improve revision quality between research and synthesis.",
                "",
                "## What Could Change The Recommendation",
                "",
                "- Managed search quality could narrow the need for a custom critic loop.",
                "",
                "## Unknowns and Next Questions",
                "",
                "- Production latency under real load still needs validation.",
                "",
                "## Recommendation and Decision Posture",
                "",
                "- Keep the critic layer because the evidence suggests revision quality is a differentiator [Evidence: C-1].",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (package_dir / "sources.json").write_text('[{"url":"https://example.com/source","source_type":"official_documentation"}]', encoding="utf-8")
    (package_dir / "claim_table.json").write_text(
        '[{"claim_id":"C-1","statement":"A self-critique stage improves revision quality in research workflows."}]',
        encoding="utf-8",
    )
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text('{"coverage_ratio":1.0,"contradiction_count":0}', encoding="utf-8")
    (package_dir / "adjacent_questions.json").write_text('[{"question_id":"aq1"}]', encoding="utf-8")
    (package_dir / "critique_findings.json").write_text('[{"summary":"gap"}]', encoding="utf-8")
    (package_dir / "decision_triggers.json").write_text('[{"label":"cost"}]', encoding="utf-8")
    (package_dir / "lateral_review.json").write_text('{"source":"model"}', encoding="utf-8")
    _write_quality_files(package_dir)

    audit_summary = audit_report_package(package_dir)

    assert not any("self-critique" in failure for failure in audit_summary.failures)


def test_audit_blocks_unsupported_precise_numbers(tmp_path: Path) -> None:
    package_dir = tmp_path / "unsupported-numbers"
    package_dir.mkdir(parents=True)
    (package_dir / "report.md").write_text(
        "\n".join(
            [
                "# Stack review",
                "",
                "## Option Space",
                "",
                "- DeepSeek appears at $2.5 per million tokens in the current evidence base.",
                "",
                "## What Could Change The Recommendation",
                "",
                "- If Perplexity falls to $0.28 per query at scale, the build-vs-buy boundary could move.",
                "",
                "## Unknowns and Next Questions",
                "",
                "- Enterprise latency data still needs verification.",
                "",
                "## Recommendation and Decision Posture",
                "",
                "- Keep a hybrid stack only if the pricing advantage remains durable [Evidence: C-1].",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (package_dir / "sources.json").write_text('[{"url":"https://example.com/source","source_type":"official_documentation"}]', encoding="utf-8")
    (package_dir / "claim_table.json").write_text(
        '[{"claim_id":"C-1","statement":"DeepSeek appears at $2.5 per million tokens in the current evidence base."}]',
        encoding="utf-8",
    )
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text('{"coverage_ratio":1.0,"contradiction_count":0}', encoding="utf-8")
    (package_dir / "adjacent_questions.json").write_text('[{"question_id":"aq1"}]', encoding="utf-8")
    (package_dir / "critique_findings.json").write_text('[{"summary":"gap"}]', encoding="utf-8")
    (package_dir / "decision_triggers.json").write_text('[{"label":"cost"}]', encoding="utf-8")
    (package_dir / "lateral_review.json").write_text('{"source":"model"}', encoding="utf-8")
    _write_quality_files(package_dir)

    audit_summary = audit_report_package(package_dir)

    assert any("Unsupported precise numbers" in failure for failure in audit_summary.failures)


def test_audit_ignores_appendix_table_numbers_in_grounding_scan(tmp_path: Path) -> None:
    package_dir = tmp_path / "appendix-table-grounding"
    package_dir.mkdir(parents=True)
    (package_dir / "report.md").write_text(
        "\n".join(
            [
                "# Stack review",
                "",
                "## Executive Summary",
                "",
                "The recommendation remains evidence-backed without new precise numbers.",
                "",
                "## Recommendation and Decision Posture",
                "",
                "- Keep the hybrid stack while the evidence advantage remains durable [Evidence: C-1].",
                "",
                "## Evidence Coverage and Source Quality",
                "",
                "Exhibit 7",
                "",
                "| Metric | Value |",
                "|---|---:|",
                "| Reliability | 0.95 |",
                "| Cost ceiling | $200/mo |",
                "",
                "## Sources",
                "",
                "- [Source](https://example.com/source)",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (package_dir / "sources.json").write_text('[{"url":"https://example.com/source","source_type":"official_documentation"}]', encoding="utf-8")
    (package_dir / "claim_table.json").write_text(
        '[{"claim_id":"C-1","statement":"The recommendation remains evidence-backed without new precise numbers."}]',
        encoding="utf-8",
    )
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text('{"coverage_ratio":1.0,"contradiction_count":0}', encoding="utf-8")
    (package_dir / "adjacent_questions.json").write_text('[{"question_id":"aq1"}]', encoding="utf-8")
    (package_dir / "critique_findings.json").write_text('[{"summary":"gap"}]', encoding="utf-8")
    (package_dir / "decision_triggers.json").write_text('[{"label":"cost"}]', encoding="utf-8")
    (package_dir / "lateral_review.json").write_text('{"source":"model"}', encoding="utf-8")
    _write_quality_files(package_dir, score=68.0)

    audit_summary = audit_report_package(package_dir)

    assert not any("Unsupported precise numbers" in failure for failure in audit_summary.failures)


def test_audit_blocks_release_when_core_coverage_is_incomplete(tmp_path: Path) -> None:
    package_dir = tmp_path / "coverage-gap-package"
    package_dir.mkdir(parents=True)
    (package_dir / "report.md").write_text(
        "\n".join(
            [
                "# Stack decision",
                "",
                "## Option Space",
                "",
                "- Compare Tavily, Exa, and Perplexity.",
                "",
                "## What Could Change The Recommendation",
                "",
                "- Volume economics can flip the choice.",
                "",
                "## Unknowns and Next Questions",
                "",
                "- Direct Perplexity superiority is still unverified.",
                "",
                "## Recommendation and Decision Posture",
                "",
                "- Recommend the hybrid stack only directionally [Evidence: C-1].",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (package_dir / "sources.json").write_text('[{"url":"https://github.com/langchain-ai/open_deep_research","source_type":"official_documentation"}]', encoding="utf-8")
    (package_dir / "claim_table.json").write_text('[{"claim_id":"C-1"}]', encoding="utf-8")
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text('{"coverage_ratio":0.75,"contradiction_count":0}', encoding="utf-8")
    (package_dir / "adjacent_questions.json").write_text('[{"question_id":"aq1"}]', encoding="utf-8")
    (package_dir / "critique_findings.json").write_text('[{"summary":"gap"}]', encoding="utf-8")
    (package_dir / "decision_triggers.json").write_text('[{"label":"cost"}]', encoding="utf-8")
    (package_dir / "lateral_review.json").write_text('{"source":"model"}', encoding="utf-8")
    (package_dir / "quality_iterations.json").write_text('[{"iteration":0}]', encoding="utf-8")
    (package_dir / "quality_assessment.json").write_text(
        json.dumps(
            {
                "overall_score": 78.0,
                "verdict": "strong",
                "dimensions": [{"dimension": "topic_alignment", "score": 88.0}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    audit_summary = audit_report_package(package_dir)

    assert audit_summary.release_status == "blocked"
    assert any("coverage is incomplete" in failure for failure in audit_summary.failures)


def test_quality_assessment_penalizes_topic_drift() -> None:
    request_spec = build_request_spec(
        "Best LLM models and GitHub projects for web search and deep research in 2026",
        depth="deep",
    )
    task_spec = build_task_spec(request_spec, answers={"decision-context": "Choose the default Smart Report v2 stack."})
    report = ReportOutput(
        id="topic-drift",
        title="Generic product architecture report",
        executive_summary="This report discusses generic product architecture choices and operating models rather than web search or deep research stacks.",
        sections=[
            ReportSection(
                title="Decision Context",
                content="Product architecture frameworks and operating models matter, but this section does not discuss GitHub projects, LLM models, or search APIs in a concrete way.",
                order=1,
                sources=["https://www.fdic.gov/resources/supervision-and-examinations/examination-policies-manual/risk-management-manual-complete.pdf"],
            )
        ],
        status=ReportStatus.COMPLETED,
        total_cost_usd=0.0,
        metadata={},
    )
    sources = [
        SourceLedgerEntry(
            url="https://www.fdic.gov/resources/supervision-and-examinations/examination-policies-manual/risk-management-manual-complete.pdf",
            title="FDIC Risk Management Manual",
            domain="www.fdic.gov",
            source_type=SourceType.RESEARCH_PAPER,
            reliability_score=0.9,
            selection_reason="test",
            question_links=["q4"],
        )
    ]

    coverage = CoverageReport(
        total_questions=4,
        covered_questions=4,
        coverage_ratio=1.0,
        strong_source_ratio=1.0,
        contradiction_count=0,
        questions=[],
        gaps=[],
    )

    assessment = assess_report_quality(task_spec, report, sources, [], [], coverage, [], [], [])

    topic_alignment = next(item.score for item in assessment.dimensions if item.dimension == "topic_alignment")
    assert topic_alignment < 60.0


def test_quality_assessment_penalizes_unsupported_precise_numbers() -> None:
    request_spec = build_request_spec("Choose the best LLM stack for web research.", depth="deep")
    task_spec = build_task_spec(request_spec, answers={"decision-context": "Choose the default Smart Report stack."})
    report = ReportOutput(
        id="unsupported-numerics",
        title="Stack decision",
        executive_summary="DeepSeek appears at $2.5 per million tokens, but the draft also claims Perplexity costs $0.28 per query without evidence.",
        sections=[
            ReportSection(
                title="Recommendation and Decision Posture",
                content="- Use the hybrid path if Perplexity truly lands at $0.28 per query [Evidence: C-1].",
                order=1,
                sources=["https://example.com/source-a"],
            )
        ],
        status=ReportStatus.COMPLETED,
        total_cost_usd=0.0,
        metadata={},
    )
    sources = [
        SourceLedgerEntry(
            url="https://example.com/source-a",
            title="Official pricing",
            domain="example.com",
            source_type=SourceType.OFFICIAL_DOCUMENTATION,
            reliability_score=0.9,
            selection_reason="test",
            question_links=["q1"],
        )
    ]
    claims = [
        ClaimRecord(
            claim_id="C-1",
            statement="DeepSeek appears at $2.5 per million tokens in the current evidence base.",
            question_id="q1",
            supporting_evidence_ids=["E-1"],
            source_ids=["S-1"],
            confidence=0.9,
            recommendation_safe=True,
        )
    ]
    coverage = CoverageReport(
        covered_questions=1,
        total_questions=1,
        coverage_ratio=1.0,
        strong_source_ratio=1.0,
        contradiction_count=0,
        questions=[],
        gaps=[],
    )

    assessment = assess_report_quality(task_spec, report, sources, claims, [], coverage, [], [], [])

    grounding = next(item.score for item in assessment.dimensions if item.dimension == "grounding_discipline")
    assert grounding < 70.0
    assert assessment.metrics["unsupported_numeric_count"] >= 1


def test_pipeline_materializes_package_when_some_sources_fail(tmp_path: Path, monkeypatch) -> None:
    repo = FileRunRepository(root=str(tmp_path / "runs"), reports_root=str(tmp_path / "reports"))
    prompt = "Compare browser automation stacks for deterministic QA coverage."
    request_spec = build_request_spec(prompt, depth="standard")
    task_spec = build_task_spec(request_spec)
    summary = build_draft_run("partial-fetch-run", prompt, depth="standard")
    summary.request_spec = request_spec
    summary.task_spec = task_spec
    repo.create_run(summary)

    class FlakyProvider:
        name = "flaky"

        async def search(self, query, plan):
            question_id = plan.primary_questions[0].question_id if plan.primary_questions else "primary"
            return [
                SearchCandidate(
                    question_id=question_id,
                    query=query,
                    url="https://example.com/good",
                    title="Good source",
                    snippet="",
                    domain="example.com",
                    provider=self.name,
                ),
                SearchCandidate(
                    question_id=question_id,
                    query=query,
                    url="https://example.com/bad",
                    title="Bad source",
                    snippet="",
                    domain="example.com",
                    provider=self.name,
                ),
            ]

        async def fetch(self, source):
            if source.url.endswith("/bad"):
                return SourceSnapshot(
                    source_id=source.source_id,
                    url=source.url,
                    title=source.title,
                    content="Source fetch failed: simulated timeout",
                    excerpt="Source fetch failed: simulated timeout",
                    provider=self.name,
                    fetch_status="error",
                )
            return SourceSnapshot(
                source_id=source.source_id,
                url=source.url,
                title=source.title,
                content=(
                    "The decision context is deterministic browser QA for document workflows. "
                    "The options compared include Playwright and Selenium with 2 supported execution styles. "
                    "The strongest tradeoffs are integration fit, debugging depth, and operational cost."
                ),
                excerpt="Deterministic QA tradeoffs for browser automation stacks.",
                provider=self.name,
                fetch_status="ok",
            )

    async def fake_choose_provider(_task_spec):
        return FlakyProvider()

    from backend.v2 import pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "choose_provider", fake_choose_provider)

    events = []

    async def emit(event) -> None:
        events.append(event)

    final_summary = asyncio.run(execute_report_run(repo, summary, task_spec, emit))

    assert final_summary.analysis_brief is not None
    assert (repo.report_dir("partial-fetch-run") / "report.md").exists()
    snapshots = json.loads((repo.run_dir("partial-fetch-run") / "artifacts" / "source_snapshots.json").read_text(encoding="utf-8"))
    assert any(item["fetch_status"] == "error" for item in snapshots)
    assert any("fetched sources" in event.message for event in events)


def test_audit_accepts_markdown_source_links_in_recommendation_section(tmp_path: Path) -> None:
    package_dir = tmp_path / "link-backed-recommendations"
    package_dir.mkdir(parents=True)
    (package_dir / "report.md").write_text(
        "\n".join(
            [
                "# Strategic report",
                "",
                "## Recommendation and Decision Posture",
                "",
                "- Prioritize staged rollout with a constrained pilot [Source](https://example.com/source-a)",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (package_dir / "sources.json").write_text('[{"url": "https://example.com/source-a"}]', encoding="utf-8")
    (package_dir / "claim_table.json").write_text('[{"claim_id": "C-1"}]', encoding="utf-8")
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text("{}", encoding="utf-8")
    _write_quality_files(package_dir)

    audit_summary = audit_report_package(package_dir)

    assert not any("lacks evidence linkage" in failure for failure in audit_summary.failures)


def test_audit_blocks_thin_report_and_broken_citations(tmp_path: Path) -> None:
    package_dir = tmp_path / "thin-report"
    package_dir.mkdir(parents=True)
    (package_dir / "report.md").write_text(
        "\n".join(
            [
                "# Thin Report",
                "",
                "## Recommendation and Decision Posture",
                "",
                "- Recommend option A [1].",
                "",
                "## Option Space",
                "",
                "- Option A vs B",
                "",
                "## What Could Change The Recommendation",
                "",
                "- Budget dominance -> switch",
                "",
                "## Unknowns and Next Questions",
                "",
                "- Need better validation",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (package_dir / "sources.json").write_text(
        json.dumps([{"url": "https://example.com", "source_type": "official_documentation"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (package_dir / "claim_table.json").write_text('[{"claim_id": "C-1"}]', encoding="utf-8")
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text("{}", encoding="utf-8")
    (package_dir / "adjacent_questions.json").write_text("[{}]", encoding="utf-8")
    (package_dir / "critique_findings.json").write_text("[{}]", encoding="utf-8")
    (package_dir / "decision_triggers.json").write_text("[{}]", encoding="utf-8")
    (package_dir / "lateral_review.json").write_text('{"source":"model"}', encoding="utf-8")
    _write_quality_files(package_dir, score=50.0)

    audit_summary = audit_report_package(package_dir)

    assert audit_summary.release_status == "blocked"
    assert any("Broken footnote-style citations" in failure for failure in audit_summary.failures)
    assert any("Quality score too low" in failure for failure in audit_summary.failures)


def test_live_pipeline_generates_longform_unicode_package(tmp_path: Path, monkeypatch) -> None:
    repo = FileRunRepository(root=str(tmp_path / "runs"), reports_root=str(tmp_path / "reports"))
    prompt = "Подготовь стратегический отчёт по практике продажи квартир с отделкой в России и международным бенчмаркам."
    request_spec = build_request_spec(prompt, depth="deep")
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Определить, какие практики и продуктовые решения стоит внедрить девелоперу в ближайшие 24 месяца.",
            "geography": "Россия",
        },
    )
    summary = build_draft_run("live-longform-ru", prompt, depth="deep")
    summary.request_spec = request_spec
    summary.task_spec = task_spec
    repo.create_run(summary)

    from backend.v2 import pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "match_reference_pack", lambda _query: None)

    async def fake_research_single(query: str, iteration: int, depth: str):
        sources = [
            Source(
                url=f"https://example.com/source-{iteration}-a",
                title=f"Источник {iteration}A",
                snippet="Международный кейс с цифрами по стоимости и скорости внедрения.",
                domain="example.com",
            ),
            Source(
                url=f"https://example.com/source-{iteration}-b",
                title=f"Источник {iteration}B",
                snippet="Операционные эффекты и управленческие выводы.",
                domain="example.com",
            ),
        ]
        findings = [
            f"На ветке {iteration} подтверждается, что стандартизация процесса снижает вариативность себестоимости на 12-18% и сокращает число дефектов при передаче квартир.",
            f"На ветке {iteration} кейсы показывают, что управляемая кастомизация повышает конверсию апсейла на 8-15% и уменьшает конфликтность с покупателем.",
            f"На ветке {iteration} международные примеры указывают, что отдельный контур контроля качества окупается за счёт снижения рекламаций и повторных выездов.",
            f"На ветке {iteration} зрелые игроки связывают продуктовую стратегию, подрядчиков, гарантийный сервис и цифровые инструменты в единую операционную модель.",
        ]
        return ResearchResult(query=query, findings=findings, sources=sources, confidence=0.88, gaps=[], iteration=iteration), 0.14, []

    def build_section(title: str, exhibit_no: int, primary_url: str, secondary_url: str) -> str:
        paragraph = " ".join(
            [
                "Российский рынок чувствителен к качеству продукта, управляемости подрядчиков, прозрачности стоимости и скорости устранения дефектов."
            ]
            * 30
        )
        exhibit = "\n".join(
            [
                f"Exhibit {exhibit_no}",
                "",
                "| Параметр | Вывод | Подтверждение |",
                "|---|---|---|",
                f"| Контроль качества | Снижает дефекты и повышает доверие | [Источник]({primary_url}) |",
                f"| Кастомизация | Даёт дополнительную выручку и удерживает клиента | [Источник]({secondary_url}) |",
            ]
        )
        if "Рекомендация" in title:
            recommendations = "\n".join(
                [
                    f"- Запустить staged pilot на одном продукте и одной подрядной связке [Источник]({primary_url})",
                    f"- Ввести формализованный чек-лист handover и двухконтурную инспекцию [Источник]({secondary_url})",
                    f"- Зафиксировать базовый продукт и отдельно продавать улучшения через каталог [Источник]({primary_url})",
                    f"- Привязать KPI подрядчиков к дефектам, срокам и повторным обращениям [Источник]({secondary_url})",
                    f"- Подготовить 24-месячную программу внедрения с промежуточными метриками [Источник]({primary_url})",
                ]
            )
            return f"{paragraph}\n\n{exhibit}\n\n{recommendations}"
        return f"{paragraph}\n\n{exhibit}\n\n{paragraph}"

    async def fake_call_llm(system: str, user: str, model: str) -> str:
        payload = json.loads(user)
        titles = payload["required_section_titles"]
        urls = [source["url"] for source in payload["sources"]]
        sections = []
        for index, title in enumerate(titles, start=1):
            primary_url = urls[(index - 1) % len(urls)]
            secondary_url = urls[index % len(urls)]
            sections.append(
                {
                    "title": title,
                    "content": build_section(title, index, primary_url, secondary_url),
                    "order": index,
                    "sources": [primary_url, secondary_url],
                }
            )
        executive_summary = " ".join(
            [
                "Вывод исследования состоит в том, что девелоперу нужен не один тактический шаг, а связанная система стандартов, контроля качества, кастомизации и phased rollout."
            ]
            * 35
        )
        report_payload = {
            "title": "Эволюция практики продажи квартир с отделкой: управленческий отчёт",
            "subtitle": "Международный опыт, экономика модели и уроки для российского девелопера",
            "facts_line": "12 источников · 24+ подтверждённых claims · 8 аналитических секций",
            "executive_summary": executive_summary,
            "sections": sections,
        }
        return json.dumps(report_payload, ensure_ascii=False)

    async def fake_call_report_writer(system_prompt: str, user_payload: dict, model: str, **kwargs) -> str:
        return await fake_call_llm(system_prompt, json.dumps(user_payload, ensure_ascii=False), model)

    monkeypatch.setattr(pipeline_module, "_research_single", fake_research_single)
    monkeypatch.setattr(pipeline_module, "_call_renderer_llm", fake_call_llm)
    monkeypatch.setattr(pipeline_module, "_call_report_writer_model", fake_call_report_writer)

    events = []

    async def emit(event) -> None:
        events.append(event)

    final_summary = asyncio.run(execute_report_run(repo, summary, task_spec, emit))
    report_dir = repo.report_dir("live-longform-ru")

    assert final_summary.status.value == "completed"
    assert final_summary.cost_usd > 0
    assert (report_dir / "report.md").exists()
    assert (report_dir / "report.pdf").exists()
    assert (report_dir / "report.docx").exists()
    markdown_text = (report_dir / "report.md").read_text(encoding="utf-8")
    assert "Эволюция практики продажи квартир с отделкой" in markdown_text
    assert "Exhibit 1" in markdown_text
    assert "Дорожная карта внедрения" in markdown_text
    assert "## Пространство альтернатив" in markdown_text
    assert "## Что может изменить рекомендацию" in markdown_text
    assert len(markdown_text.split()) > 3200
    assert (report_dir / "lateral_review.json").exists()
    assert any(event.step == "research" for event in events)


def test_live_quality_loop_records_three_improvements(tmp_path: Path, monkeypatch) -> None:
    repo = FileRunRepository(root=str(tmp_path / "runs"), reports_root=str(tmp_path / "reports"))
    prompt = "Prepare a decision-grade report on browser automation stacks for enterprise QA."
    request_spec = build_request_spec(prompt, depth="deep")
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the primary automation stack for the next 12 months.",
            "geography": "global",
        },
    )
    summary = build_draft_run("quality-loop-live", prompt, depth="deep")
    summary.request_spec = request_spec
    summary.task_spec = task_spec
    repo.create_run(summary)

    from backend.v2 import pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "match_reference_pack", lambda _query: None)

    async def fake_research_single(query: str, iteration: int, depth: str):
        sources = [
            Source(
                url=f"https://example.com/stack-{iteration}-a",
                title=f"Source {iteration}A",
                snippet="Benchmarks on debugging depth, maintenance load, and operating cost.",
                domain="example.com",
            ),
            Source(
                url=f"https://example.com/stack-{iteration}-b",
                title=f"Source {iteration}B",
                snippet="Comparative guidance on tradeoffs, rollout patterns, and failure modes.",
                domain="example.com",
            ),
        ]
        findings = [
            f"Iteration {iteration} shows that deterministic debugging, traceability, and maintenance cost move together and create explicit tradeoffs between Playwright and Selenium.",
            f"Iteration {iteration} shows that teams choosing a framework without switch conditions often lock themselves into higher regression maintenance within 6 to 12 months.",
            f"Iteration {iteration} shows that stronger recommendation quality comes from comparing alternatives, stakeholder objections, and operating constraints instead of relying on feature lists.",
            f"Iteration {iteration} shows that a phased pilot with explicit failure modes improves decision usefulness and reduces hidden implementation risk.",
        ]
        return ResearchResult(query=query, findings=findings, sources=sources, confidence=0.9, gaps=[], iteration=iteration), 0.11, []

    revision_round = {"count": 0}

    def build_section(title: str, exhibit_no: int, primary_url: str, secondary_url: str, richness: int) -> str:
        paragraph = " ".join(
            [
                "Enterprise QA leaders care about tradeoffs between debugging depth, portability, operating cost, and reliability under change.",
                "A useful report must show option space, anti-thesis, and recommendation-switch conditions rather than defend a single tool.",
                "Decision usefulness improves when the report names hidden variables, phased rollout, and stakeholder objections explicitly.",
            ]
            * (4 + richness * 9)
        )
        exhibits = []
        for exhibit_index in range(exhibit_no, exhibit_no + min(1 + richness, 3)):
            exhibits.append(
                "\n".join(
                    [
                        f"Exhibit {exhibit_index}",
                        "",
                        "| Dimension | Implication | Evidence |",
                        "|---|---|---|",
                        f"| Debugging depth | Shapes deterministic troubleshooting and QA traceability | [Source]({primary_url}) |",
                        f"| Operating cost | Changes the winning stack when scale and maintenance burden matter | [Source]({secondary_url}) |",
                    ]
                )
            )
        body = f"{paragraph}\n\n" + "\n\n".join(exhibits)
        if richness >= 2:
            body += (
                "\n\nUnknowns and next questions remain around migration path, organization design, and failure handling under rapid suite growth."
            )
        if "Recommendation" in title:
            bullets = [
                f"- Run a bounded pilot first and define success thresholds before broad rollout [Source]({primary_url})",
                f"- Compare Playwright and Selenium against explicit operating constraints, not just feature checklists [Source]({secondary_url})",
                f"- Document switch conditions and failure modes so the recommendation remains honest under change [Source]({primary_url})",
                f"- Separate migration cost from steady-state maintenance cost in the decision memo [Source]({secondary_url})",
                f"- Use a phased roadmap with governance checkpoints and rollback criteria [Source]({primary_url})",
                f"- Capture stakeholder objections from engineering, security, and QA operations before scaling [Source]({secondary_url})",
            ]
            return body + "\n\n" + "\n".join(bullets[: 2 + richness])
        return body + "\n\n" + paragraph

    async def fake_call_llm(system: str, user: str, model: str) -> str:
        payload = json.loads(user)
        titles = payload["required_section_titles"]
        urls = [source["url"] for source in payload["sources"]]
        if "client-ready analytical report" in system.lower() and "revis" in system.lower():
            revision_round["count"] += 1
        richness = revision_round["count"]
        sections = []
        for index, title in enumerate(titles, start=1):
            primary_url = urls[(index - 1) % len(urls)]
            secondary_url = urls[index % len(urls)]
            sections.append(
                {
                    "title": title,
                    "content": build_section(title, index, primary_url, secondary_url, richness),
                    "order": index,
                    "sources": [primary_url, secondary_url],
                }
            )
        executive_summary = " ".join(
            [
                "The decision is not only about which stack looks stronger today, but about which one remains controllable, auditable, and cost-effective after twelve months of change.",
                "A serious report therefore needs alternative comparison, hidden variables, anti-thesis, and phased rollout logic.",
            ]
            * (5 + richness * 8)
        )
        return json.dumps(
            {
                "title": "Browser Automation Stacks: Decision Report",
                "subtitle": "Comparative evaluation of enterprise QA options",
                "facts_line": f"revision {revision_round['count']}",
                "executive_summary": executive_summary,
                "sections": sections,
            },
            ensure_ascii=False,
        )

    async def fake_call_report_writer(system_prompt: str, user_payload: dict, model: str, **kwargs) -> str:
        return await fake_call_llm(system_prompt, json.dumps(user_payload, ensure_ascii=False), model)

    monkeypatch.setattr(pipeline_module, "_research_single", fake_research_single)
    monkeypatch.setattr(pipeline_module, "_call_renderer_llm", fake_call_llm)
    monkeypatch.setattr(pipeline_module, "_call_report_writer_model", fake_call_report_writer)

    events = []

    async def emit(event) -> None:
        events.append(event)

    final_summary = asyncio.run(execute_report_run(repo, summary, task_spec, emit))
    report_dir = repo.report_dir("quality-loop-live")
    quality_iterations = json.loads((report_dir / "quality_iterations.json").read_text(encoding="utf-8"))

    assert final_summary.status.value == "completed"
    assert (report_dir / "quality_assessment.json").exists()
    assert len(quality_iterations) >= 4
    assert len([item for item in quality_iterations if item["improved"]]) >= 3
    assert any(event.step == "quality" for event in events)
