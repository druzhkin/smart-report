from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.agents.renderer import _build_html, _ensure_table_spacing
from backend.schemas.report_schema import ReportOutput, ReportSection, ReportStatus
from backend.schemas.research_result import ResearchResult, Source
from backend.v2.audit import audit_report_package
from backend.v2.grounding import extract_numeric_facts, find_unsupported_precise_numbers, sanitize_unsupported_precise_numbers
from backend.v2.intake import build_request_spec, build_task_spec
from backend.v2.models import (
    AnalysisBrief,
    ClaimRecord,
    CritiqueKind,
    CritiqueFinding,
    CoverageReport,
    CoverageQuestionStatus,
    DecisionTrigger,
    EvidenceRecord,
    QualityAssessment,
    QualityDimensionScore,
    QuestionKind,
    ResearchPlan,
    ResearchQuestion,
    SearchCandidate,
    SpendCategory,
    SourceLedgerEntry,
    SourceSnapshot,
    SourceType,
)
from backend.v2.pipeline import (
    LATERAL_REVIEW_PROMPT,
    _adjacent_to_primary_question_id,
    _aggregate_research_spend,
    _build_business_backfill_queries,
    _build_stack_backfill_queries,
    _build_question_fallback_queries,
    _build_live_research_queries,
    _build_live_evidence,
    _build_validation_questions,
    _coverage_gap_question_ids,
    _final_markdown_compliance_cleanup,
    _language_name,
    _append_decision_addendum_sections,
    _rank_live_sources,
    _sanitize_llm_markdown,
    _traceability_appendix_sections,
    build_analysis_brief,
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


def test_audit_blocks_html_with_raw_markdown_tables(tmp_path: Path) -> None:
    package_dir = tmp_path / "format-broken-package"
    package_dir.mkdir(parents=True)
    report_md = (
        "# Format Broken\n\n"
        "## Executive Summary\n\n"
        "Short summary.\n\n"
        "## Recommendation and Decision Posture\n\n"
        "- Recommend a phased pilot with bounded rollout [Evidence: C-01]\n\n"
        "## Option Space\n\n"
        "Comparison text.\n\n"
        "## What Could Change The Recommendation\n\n"
        "Trigger text.\n\n"
        "## Unknowns and Next Questions\n\n"
        "Open questions.\n"
    )
    report_html = (
        "<html><body>"
        "<p>| Option | Cost |</p>"
        "<p>|---|---|</p>"
        "<p>| Deep | $0.75 |</p>"
        "</body></html>"
    )
    (package_dir / "report.md").write_text(report_md, encoding="utf-8")
    (package_dir / "report.html").write_text(report_html, encoding="utf-8")
    (package_dir / "sources.json").write_text(
        json.dumps(
            [
                {
                    "source_id": "S-01",
                    "url": "https://example.com/source",
                    "source_type": "research_paper",
                    "reliability_score": 0.9,
                }
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "claim_table.json").write_text(
        json.dumps(
            [
                {
                    "claim_id": "C-01",
                    "statement": "A phased pilot reduces rollout risk.",
                }
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "analysis_brief.json").write_text("{}", encoding="utf-8")
    (package_dir / "coverage_report.json").write_text(
        json.dumps({"coverage_ratio": 1.0, "contradiction_count": 0}),
        encoding="utf-8",
    )
    (package_dir / "quality_assessment.json").write_text(
        json.dumps({"overall_score": 80.0, "verdict": "strong", "dimensions": []}),
        encoding="utf-8",
    )
    (package_dir / "quality_iterations.json").write_text(
        json.dumps([{"iteration": 0, "improved": False}]),
        encoding="utf-8",
    )
    (package_dir / "adjacent_questions.json").write_text(json.dumps([{"question_id": "aq1"}]), encoding="utf-8")
    (package_dir / "critique_findings.json").write_text(json.dumps([{"finding_id": "f1"}]), encoding="utf-8")
    (package_dir / "decision_triggers.json").write_text(json.dumps([{"label": "Budget"}]), encoding="utf-8")
    (package_dir / "lateral_review.json").write_text(json.dumps({"source": "model"}), encoding="utf-8")

    audit_summary = audit_report_package(package_dir)

    assert audit_summary.release_status == "blocked"
    assert any("raw markdown tables" in failure for failure in audit_summary.failures)


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


def test_extract_numeric_facts_preserves_thousand_separators() -> None:
    facts = extract_numeric_facts("The platform handled 40,000 requests per day during the benchmark window.")

    assert any(int(fact.value) == 40000 for fact in facts)


def test_sanitize_unsupported_precise_numbers_rewrites_unbacked_metrics() -> None:
    report_text = "Launch at $50 per user, size the market at USD 13.3 billion, and expect 30% conversion in the first quarter."
    claim_texts = ["Comparable tools are sold with paid subscriptions, but exact price and conversion are not validated yet."]

    sanitized = sanitize_unsupported_precise_numbers(report_text, claim_texts)

    assert "$50" not in sanitized
    assert "13.3 billion" not in sanitized
    assert "30%" not in sanitized
    assert "a paid tier" in sanitized
    assert "a large market category" in sanitized
    assert "a meaningful threshold" in sanitized
    assert "pointillion" not in sanitized


def test_find_unsupported_precise_numbers_ignores_low_signal_document_counters() -> None:
    report_text = "Exhibit 4\n\nPhase 1 validates the workflow in 6 months before a broader rollout."
    claim_texts = ["The workflow should be validated before broad rollout."]

    unsupported = find_unsupported_precise_numbers(report_text, claim_texts)

    assert unsupported == []


def test_final_markdown_compliance_cleanup_strips_unlinked_recommendation_bullets_and_numbers() -> None:
    report_markdown = (
        "# Demo\n\n"
        "## Recommendation and Decision Posture\n\n"
        "- Keep the product free until adoption rises above 25%\n"
        "- Launch a premium tier [Evidence: C-01]\n\n"
        "Net Promoter Score above 50\n\n"
        "## Other Section\n\n"
        "- Evidence-backed point with 42% growth.\n"
    )
    claim_texts = ["Launch a premium tier when adoption reaches a validated threshold."]

    cleaned = _final_markdown_compliance_cleanup(report_markdown, claim_texts)

    assert "- Keep the product free until adoption rises above 25%" not in cleaned
    assert "Keep the product free until adoption rises above a meaningful threshold" in cleaned
    assert "- Launch a premium tier [Evidence: C-01]" in cleaned
    assert "42%" not in cleaned
    assert "Net Promoter Score above 50" not in cleaned
    assert "Net Promoter Score above a strong satisfaction threshold" in cleaned


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


def test_sanitize_llm_markdown_removes_invalid_internal_evidence_markers() -> None:
    cleaned = _sanitize_llm_markdown(
        "Recommendation: pursue validation. [Evidence: q1, aq1]\n\nRoadmap [Evidence: C-01, C-02]\n\n[...]"
    )

    assert "[Evidence: q1, aq1]" not in cleaned
    assert "[Evidence: C-01, C-02]" in cleaned
    assert "[...]" not in cleaned


def test_sanitize_llm_markdown_collapses_blank_lines_inside_tables() -> None:
    cleaned = _sanitize_llm_markdown(
        "\n".join(
            [
                "Exhibit 9",
                "",
                "| Validation issue | Severity | Why it still matters |",
                "",
                "|---|---|---|",
                "",
                "| weak_evidence | high | Current draft still relies on thinly supported claims. |",
                "",
                "| omitted_question | high | At least one core question remains under-covered. |",
            ]
        )
    )

    assert "|\n\n|---|---|---|\n\n|" not in cleaned
    assert "| Validation issue | Severity | Why it still matters |\n|---|---|---|\n| weak_evidence | high | Current draft still relies on thinly supported claims. |" in cleaned


def test_traceability_appendix_tables_are_emitted_as_contiguous_markdown() -> None:
    coverage = CoverageReport(
        covered_questions=4,
        total_questions=4,
        coverage_ratio=1.0,
        strong_source_ratio=0.9,
        contradiction_count=0,
        questions=[],
    )
    source_ledger = [
        SourceLedgerEntry(
            source_id="S-1",
            url="https://docs.example.com/source-1",
            title="Example Source",
            domain="docs.example.com",
            source_type=SourceType.OFFICIAL_DOCUMENTATION,
            reliability_score=0.94,
            question_links=["q1", "q2"],
            selected_for_report=True,
            selection_reason="Relevant and authoritative.",
        )
    ]
    critique_findings = [
        CritiqueFinding(
            kind="weak_evidence",
            severity="high",
            summary="Thin evidence",
            rationale="Current draft still relies on thinly supported claims.",
        )
    ]
    decision_triggers = [
        DecisionTrigger(
            label="Budget dominance",
            condition="Budget becomes the main constraint.",
            implication="Shift toward the cheaper stack.",
            confidence=0.72,
        )
    ]

    sections = _traceability_appendix_sections(
        coverage=coverage,
        source_ledger=source_ledger,
        critique_findings=critique_findings,
        decision_triggers=decision_triggers,
        language="en",
    )

    coverage_section = dict(sections)["Evidence Coverage and Source Quality"]
    validation_section = dict(sections)["Validation Priorities and Decision Triggers"]
    assert "|\n\n|---|---|---|---:|---:|" not in coverage_section
    assert "|\n\n| Validation issue | Severity | Why it still matters |" not in validation_section


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


def test_ensure_table_spacing_keeps_markdown_table_rows_contiguous() -> None:
    text = (
        "Exhibit 1\n"
        "| Column A | Column B |\n"
        "|---|---|\n"
        "| Alpha | Beta |\n"
        "Follow-up paragraph."
    )

    formatted = _ensure_table_spacing(text)

    assert "\n\n| Column A | Column B |\n|---|---|\n| Alpha | Beta |\n\nFollow-up paragraph." in formatted
    assert "\n\n|---|---|\n\n" not in formatted
    assert "\n\n| Alpha | Beta |\n\n" not in formatted


def test_build_html_renders_markdown_tables_as_table_elements() -> None:
    report = ReportOutput(
        id="table-report",
        title="Table Rendering",
        executive_summary="Summary paragraph.",
        sections=[
            ReportSection(
                title="Comparative Exhibit",
                content=(
                    "Exhibit 1\n\n"
                    "| Option | Cost |\n"
                    "|---|---:|\n"
                    "| Light | $0.29 |\n"
                    "| Deep | $0.75 |\n\n"
                    "Interpretation paragraph."
                ),
                order=1,
                sources=[],
            )
        ],
        total_cost_usd=0.0,
        metadata={},
    )

    html = _build_html(report, [], lang="en")

    assert "<table>" in html
    assert "<thead>" in html
    assert "<tbody>" in html
    assert "<td>Light</td>" in html
    assert "$0.75</td>" in html


def test_build_decision_triggers_do_not_embed_long_subject_verbatim() -> None:
    request_spec = build_request_spec(
        "Assess whether there is a real market for decision-grade AI research/report tools like Smart Report, identify buyer segments, and estimate willingness to pay.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Decide whether Smart Report should be positioned as a paid product for consulting and strategy teams.",
            "geography": "global",
        },
    )

    triggers = build_decision_triggers(task_spec)
    serialized = " ".join(f"{item.label} {item.condition} {item.implication}" for item in triggers)

    assert "option around whether there is a real market" not in serialized
    assert "the dominant filter" in serialized
    assert any(item.label == "Budget Dominance" for item in triggers)


def test_build_analysis_brief_uses_analytical_lines_instead_of_raw_questions() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    coverage = CoverageReport(
        total_questions=4,
        covered_questions=3,
        coverage_ratio=0.75,
        strong_source_ratio=1.0,
        contradiction_count=0,
        questions=[],
        gaps=["What are the strongest evidence-backed tradeoffs, risks, and decision triggers?"],
    )
    adjacent_questions = [
        ResearchQuestion(
            question_id="aq1",
            question="What are the top existing AI market research tools (e.g., Perplexity, Aomni, GWI Spark) and how do they compare to Smart Report on quality, cost, and operational risk?",
            kind=QuestionKind.ADJACENT_ALTERNATIVE,
            priority=1,
            required_evidence_count=1,
        ),
        ResearchQuestion(
            question_id="aq2",
            question="What evidence shows low willingness to pay for AI research tools among consulting/strategy teams, or preference for free options like ChatGPT/Perplexity?",
            kind=QuestionKind.ADJACENT_COUNTERARGUMENT,
            priority=2,
            required_evidence_count=1,
        ),
    ]
    critique_findings = [
        CritiqueFinding(
            summary="The current draft still relies on thinly supported claims and should not finalize an unqualified recommendation.",
            kind=CritiqueKind.WEAK_EVIDENCE,
            severity="high",
        )
    ]
    decision_triggers = [
        DecisionTrigger(
            label="Budget Dominance",
            condition="If total cost of ownership becomes the dominant filter, favor the lowest-burden option over the richest feature set.",
            implication="The recommendation may shift toward a cheaper, simpler stack even if it is weaker on absolute quality.",
            confidence=0.74,
        )
    ]

    brief = build_analysis_brief(
        task_spec,
        claims=[],
        coverage=coverage,
        adjacent_questions=adjacent_questions,
        critique_findings=critique_findings,
        decision_triggers=decision_triggers,
    )

    assert brief.option_space
    assert all(not line.endswith("?") for line in brief.option_space)
    assert any("Perplexity" in line for line in brief.option_space)
    assert any("Tradeoffs, risks" in line for line in brief.critical_unknowns)


def test_adjacent_boundary_and_hidden_variable_map_into_q4() -> None:
    plan = ResearchPlan(
        primary_questions=[
            ResearchQuestion(question_id="q1", question="Decision framing", kind=QuestionKind.PRIMARY, priority=1, required_evidence_count=2),
            ResearchQuestion(question_id="q2", question="Alternatives and comparators", kind=QuestionKind.PRIMARY, priority=2, required_evidence_count=2),
            ResearchQuestion(question_id="q3", question="Recommended option and stack fit", kind=QuestionKind.PRIMARY, priority=3, required_evidence_count=2),
            ResearchQuestion(question_id="q4", question="Tradeoffs, risks, failure modes, and decision triggers", kind=QuestionKind.PRIMARY, priority=4, required_evidence_count=2),
        ]
    )

    boundary = ResearchQuestion(
        question_id="aq4",
        question="Under what conditions does the recommendation stop working?",
        kind=QuestionKind.ADJACENT_BOUNDARY,
        priority=4,
        required_evidence_count=1,
    )
    hidden = ResearchQuestion(
        question_id="aq3",
        question="Which hidden variables and operating risks can still overturn the recommendation?",
        kind=QuestionKind.ADJACENT_HIDDEN_VARIABLE,
        priority=3,
        required_evidence_count=1,
    )

    assert _adjacent_to_primary_question_id(plan, boundary) == "q4"
    assert _adjacent_to_primary_question_id(plan, hidden) == "q4"


def test_append_decision_addendum_sections_overwrites_placeholder_sections() -> None:
    report = ReportOutput(
        id="overwrite-demo",
        title="Overwrite Demo",
        executive_summary="Summary",
        sections=[
            ReportSection(
                title="Option Space",
                content="- Raw planner question?",
                order=1,
                sources=[],
            ),
            ReportSection(
                title="What Could Change The Recommendation",
                content="- Old broken trigger line",
                order=2,
                sources=[],
            ),
        ],
        total_cost_usd=0.0,
        metadata={},
    )
    brief = AnalysisBrief(
        title="Brief",
        executive_summary="Summary",
        decision_context="Choose a path",
        recommendation_posture="bounded_analysis_only",
        key_findings=[],
        key_risks=[],
        option_space=["The comparison set should explicitly include Perplexity, Aomni, GWI Spark, not just the focal product."],
        critical_unknowns=["Tradeoffs, risks, and recommendation-switch conditions remain under-evidenced."],
        decision_triggers=["Budget Dominance: If total cost of ownership becomes the dominant filter, favor the lowest-burden option over the richest feature set. -> The recommendation may shift toward a cheaper, simpler stack even if it is weaker on absolute quality."],
        improvement_priorities=[],
        limitations=[],
        uncertainty_statement="",
        chart_candidates=[],
    )
    sources = [
        SourceLedgerEntry(
            question_links=["q1"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.com/source",
            title="Example Source",
            domain="example.com",
            reliability_score=0.91,
            selection_reason="Strong source",
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

    updated = _append_decision_addendum_sections(
        report,
        brief,
        sources,
        coverage,
        critique_findings=[],
        decision_triggers=[],
        language="en",
    )

    option_section = next(section for section in updated.sections if section.title == "Option Space")
    trigger_section = next(section for section in updated.sections if section.title == "What Could Change The Recommendation")

    assert "Raw planner question?" not in option_section.content
    assert "The comparison set should explicitly include Perplexity" in option_section.content
    assert "Old broken trigger line" not in trigger_section.content
    assert "Budget Dominance:" in trigger_section.content


def test_rank_live_sources_preserves_anchor_source_for_each_primary_question() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    plan = build_research_plan(task_spec)
    entries = [
        SourceLedgerEntry(
            question_links=["q1"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.com/q1",
            title="Market demand overview",
            domain="example.com",
            reliability_score=0.92,
            selection_reason="q1",
        ),
        SourceLedgerEntry(
            question_links=["q2"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.org/q2",
            title="Alternative analysis methodology",
            domain="example.org",
            reliability_score=0.91,
            selection_reason="q2",
        ),
        SourceLedgerEntry(
            question_links=["q3"],
            source_type=SourceType.HIGH_QUALITY_SECONDARY,
            url="https://example.net/q3",
            title="Pricing and positioning benchmark",
            domain="example.net",
            reliability_score=0.84,
            selection_reason="q3",
        ),
        SourceLedgerEntry(
            question_links=["q4"],
            source_type=SourceType.VENDOR_PAGE,
            url="https://low-signal.example/q4",
            title="Operational rollout notes",
            domain="low-signal.example",
            reliability_score=0.62,
            selection_reason="q4",
        ),
    ]

    selected = _rank_live_sources(entries, task_spec, plan, limit=4)

    selected_urls = {entry.url for entry in selected}
    assert "https://low-signal.example/q4" in selected_urls
    assert len(selected) == 4


def test_rank_live_sources_prefers_q4_tradeoff_source_over_generic_q4_source() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    plan = build_research_plan(task_spec)
    entries = [
        SourceLedgerEntry(
            question_links=["q1"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.com/q1",
            title="Market demand overview",
            domain="example.com",
            reliability_score=0.92,
            selection_reason="q1",
        ),
        SourceLedgerEntry(
            question_links=["q2"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.org/q2",
            title="Alternative analysis methodology",
            domain="example.org",
            reliability_score=0.91,
            selection_reason="q2",
        ),
        SourceLedgerEntry(
            question_links=["q3"],
            source_type=SourceType.HIGH_QUALITY_SECONDARY,
            url="https://example.net/q3",
            title="Pricing and positioning benchmark",
            domain="example.net",
            reliability_score=0.84,
            selection_reason="q3",
        ),
        SourceLedgerEntry(
            question_links=["q4"],
            source_type=SourceType.HIGH_QUALITY_SECONDARY,
            url="https://generic.example/q4",
            title="Decision-Grade Data and Operational Excellence",
            domain="generic.example",
            reliability_score=0.86,
            selection_reason="generic q4",
        ),
        SourceLedgerEntry(
            question_links=["q4"],
            source_type=SourceType.BENCHMARK,
            url="https://specific.example/q4",
            title="Enterprise AI pricing, procurement friction, ROI, and integration tradeoffs",
            domain="specific.example",
            reliability_score=0.8,
            selection_reason="specific q4",
        ),
    ]

    selected = _rank_live_sources(entries, task_spec, plan, limit=4)

    selected_urls = [entry.url for entry in selected]
    assert "https://specific.example/q4" in selected_urls
    assert "https://generic.example/q4" not in selected_urls


def test_build_live_evidence_filters_generic_q4_findings_and_keeps_tradeoff_evidence() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    source_ledger = [
        SourceLedgerEntry(
            question_links=["q4"],
            source_type=SourceType.HIGH_QUALITY_SECONDARY,
            url="https://generic.example/q4",
            title="Decision-Grade Data and Operational Excellence",
            domain="generic.example",
            reliability_score=0.86,
            selection_reason="generic q4",
        ),
        SourceLedgerEntry(
            question_links=["q4"],
            source_type=SourceType.BENCHMARK,
            url="https://specific.example/q4",
            title="Enterprise AI pricing, procurement friction, ROI, and integration tradeoffs",
            domain="specific.example",
            reliability_score=0.82,
            selection_reason="specific q4",
        ),
    ]
    research_rows = [
        {
            "question_id": "q4",
            "primary_question_id": "q4",
            "query": "What are the strongest evidence-backed tradeoffs, risks, and decision triggers?",
            "source_urls": ["https://generic.example/q4", "https://specific.example/q4"],
            "findings": [
                "Decision-Grade Data is the foundation of operational excellence in modern enterprises and matters for better decisions.",
                "Enterprise buyers most often object on pricing, procurement friction, integration burden, and unclear ROI until switching conditions are explicit.",
            ],
        }
    ]

    evidence = _build_live_evidence(research_rows, source_ledger, task_spec)

    assert len(evidence) == 1
    assert "pricing" in evidence[0].claim.lower()
    assert evidence[0].source_id == source_ledger[1].source_id


def test_q4_queries_include_pricing_procurement_and_switch_signals() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    plan = build_research_plan(task_spec)
    live_queries = dict(_build_live_research_queries(task_spec, plan))
    q4_question = next(question for question in plan.primary_questions if question.question_id == "q4")
    fallback_queries = _build_question_fallback_queries(task_spec, q4_question)

    q4_prompt = live_queries["q4"].lower()
    assert "pricing" in q4_prompt
    assert "procurement" in q4_prompt
    assert "switch" in q4_prompt

    joined_fallback = " ".join(fallback_queries).lower()
    assert "ai saas monetization consulting investment teams pricing" in joined_fallback
    assert "enterprise software pricing procurement objections consulting firms" in joined_fallback
    assert "go to market packaging ai workflow software professional services" in joined_fallback


def test_business_live_queries_disambiguate_smart_report_product_name() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    plan = build_research_plan(task_spec)
    live_queries = dict(_build_live_research_queries(task_spec, plan))

    assert "Treat Smart Report as the name of the user's product" in live_queries["q1"]
    assert "Exclude Oracle, BMC" in live_queries["q1"]
    assert "Compare Perplexity, AlphaSense, PitchBook, CB Insights, Hebbia" in live_queries["q2"]
    assert "Avoid generic reporting documentation" in live_queries["q2"]


def test_business_backfill_queries_exist_for_monetization_topics() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )

    query_specs = _build_business_backfill_queries(task_spec)

    assert query_specs
    assert any(question_id == "q1" for question_id, _ in query_specs)
    assert any(question_id == "q3" for question_id, _ in query_specs)
    assert any(question_id == "q4" for question_id, _ in query_specs)
    assert any("monetization" in query.lower() for _, query in query_specs)
    assert [question_id for question_id, _ in query_specs[:4]] == ["q3", "q3", "q4", "q4"]


def test_business_backfill_queries_can_be_limited_to_uncovered_questions() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )

    query_specs = _build_business_backfill_queries(task_spec, {"q4"})

    assert query_specs
    assert all(question_id == "q4" for question_id, _ in query_specs)
    assert any("pricing objections" in query.lower() or "willingness to pay" in query.lower() for _, query in query_specs)


def test_business_q2_fallback_queries_include_named_competitors() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    question = build_research_plan(task_spec).primary_questions[1]

    queries = _build_question_fallback_queries(task_spec, question)

    assert any("AlphaSense" in query or "PitchBook" in query or "Hebbia" in query for query in queries)
    assert any("manual workflow" in query.lower() for query in queries)


def test_coverage_gap_question_ids_returns_only_uncovered_questions() -> None:
    coverage = CoverageReport(
        total_questions=4,
        covered_questions=2,
        coverage_ratio=0.5,
        strong_source_ratio=0.5,
        contradiction_count=0,
        questions=[
            CoverageQuestionStatus(question_id="q1", question="Demand", evidence_count=3, source_count=2, status="covered"),
            CoverageQuestionStatus(question_id="q2", question="Alternatives", evidence_count=2, source_count=1, status="covered"),
            CoverageQuestionStatus(question_id="q3", question="Packaging", evidence_count=1, source_count=1, status="gap"),
            CoverageQuestionStatus(question_id="q4", question="Tradeoffs", evidence_count=0, source_count=0, status="gap"),
        ],
        gaps=["Packaging", "Tradeoffs"],
    )

    assert _coverage_gap_question_ids(coverage) == {"q3", "q4"}


def test_validation_questions_prioritize_uncovered_core_gap_before_generic_critique() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    coverage = CoverageReport(
        total_questions=4,
        covered_questions=3,
        coverage_ratio=0.75,
        strong_source_ratio=1.0,
        contradiction_count=0,
        questions=[
            CoverageQuestionStatus(question_id="q1", question="Demand", evidence_count=2, source_count=2, status="covered"),
            CoverageQuestionStatus(question_id="q2", question="Alternatives", evidence_count=2, source_count=2, status="covered"),
            CoverageQuestionStatus(question_id="q3", question="Packaging", evidence_count=2, source_count=2, status="covered"),
            CoverageQuestionStatus(question_id="q4", question="Tradeoffs", evidence_count=0, source_count=0, status="gap"),
        ],
        gaps=["Tradeoffs"],
    )
    critique_findings = [
        CritiqueFinding(
            kind=CritiqueKind.WEAK_EVIDENCE,
            severity="high",
            summary="Some recommendation bullets still rely on thin evidence.",
        )
    ]

    questions = _build_validation_questions(task_spec, critique_findings, build_decision_triggers(task_spec), coverage)

    assert questions
    assert questions[0].question_id.startswith("vg")
    assert questions[0].kind == QuestionKind.ADJACENT_BOUNDARY
    assert "tradeoffs" in questions[0].question.lower()


def test_rank_live_sources_prefers_business_monetization_source_over_unrelated_smart_reporting_doc() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    plan = build_research_plan(task_spec)
    entries = [
        SourceLedgerEntry(
            question_links=["q1"],
            source_type=SourceType.OFFICIAL_DOCUMENTATION,
            url="https://docs.oracle.com/cd/B40099_02/books/Reports/ReportsSmartReport3.html",
            title="Bookshelf v8.0: Purpose of Smart Reports - Oracle",
            domain="docs.oracle.com",
            reliability_score=0.95,
            selection_reason="oracle smart reports",
        ),
        SourceLedgerEntry(
            question_links=["q1"],
            source_type=SourceType.VENDOR_PAGE,
            url="https://my.idc.com/getdoc.jsp?containerId=IDC_P7407",
            title="AI Monetization, Pricing Strategies, and Business Models",
            domain="my.idc.com",
            reliability_score=0.78,
            selection_reason="idc monetization",
        ),
        SourceLedgerEntry(
            question_links=["q2"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.org/q2",
            title="Alternative analysis methodology",
            domain="example.org",
            reliability_score=0.91,
            selection_reason="q2",
        ),
        SourceLedgerEntry(
            question_links=["q3"],
            source_type=SourceType.BENCHMARK,
            url="https://example.net/q3",
            title="Pricing and packaging benchmark for professional software",
            domain="example.net",
            reliability_score=0.84,
            selection_reason="q3",
        ),
        SourceLedgerEntry(
            question_links=["q4"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.com/q4",
            title="Tradeoffs and risk thresholds",
            domain="example.com",
            reliability_score=0.89,
            selection_reason="q4",
        ),
    ]

    selected = _rank_live_sources(entries, task_spec, plan, limit=4)
    selected_urls = {entry.url for entry in selected}

    assert "https://my.idc.com/getdoc.jsp?containerId=IDC_P7407" in selected_urls
    assert "https://docs.oracle.com/cd/B40099_02/books/Reports/ReportsSmartReport3.html" not in selected_urls


def test_rank_live_sources_prefers_competitor_landscape_for_business_q2_over_generic_cost_docs() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    plan = build_research_plan(task_spec)
    entries = [
        SourceLedgerEntry(
            question_links=["q2"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://www.gao.gov/assets/gao-20-195g.pdf",
            title="Cost Estimating and Assessment Guide",
            domain="www.gao.gov",
            reliability_score=0.9,
            selection_reason="generic",
        ),
        SourceLedgerEntry(
            question_links=["q2"],
            source_type=SourceType.HIGH_QUALITY_SECONDARY,
            url="https://www.alphasense.com/blog/market-intelligence/what-is-market-intelligence/",
            title="Market intelligence platform overview | AlphaSense",
            domain="www.alphasense.com",
            reliability_score=0.68,
            selection_reason="competitor landscape",
        ),
        SourceLedgerEntry(
            question_links=["q2"],
            source_type=SourceType.OFFICIAL_DOCUMENTATION,
            url="https://docs.oracle.com/cd/E05553_01/books/Reports/ReportsSmartReport3.html",
            title="Bookshelf v7.7: Purpose of Smart Reports - Oracle",
            domain="docs.oracle.com",
            reliability_score=0.95,
            selection_reason="oracle smart reports",
        ),
    ]

    selected = _rank_live_sources(entries, task_spec, plan, limit=3)

    assert selected[0].domain == "www.alphasense.com"
    assert selected[-1].domain == "docs.oracle.com"


def test_rank_live_sources_prefers_business_q4_tradeoff_source_over_generic_paper() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={
            "decision-context": "Choose the monetization path.",
            "geography": "global",
        },
    )
    plan = build_research_plan(task_spec)
    entries = [
        SourceLedgerEntry(
            question_links=["q4"],
            source_type=SourceType.VENDOR_PAGE,
            url="https://www.bvp.com/atlas/the-ai-pricing-and-monetization-playbook",
            title="The AI Pricing and Monetization Playbook",
            domain="www.bvp.com",
            reliability_score=0.78,
            selection_reason="pricing tradeoffs",
        ),
        SourceLedgerEntry(
            question_links=["q4"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://www.sciencedirect.com/science/article/pii/S104450052300046X",
            title="Employee benefits and company performance: Evidence from a high ...",
            domain="www.sciencedirect.com",
            reliability_score=0.9,
            selection_reason="generic paper",
        ),
    ]

    selected = _rank_live_sources(entries, task_spec, plan, limit=2)

    assert selected[0].domain == "www.bvp.com"


def test_rank_live_sources_dedupes_same_url_variants() -> None:
    request_spec = build_request_spec(
        "Assess whether Smart Report should become a paid product for consulting and investment teams.",
        depth="deep",
    )
    task_spec = build_task_spec(
        request_spec,
        answers={"decision-context": "Choose the monetization path."},
    )
    plan = build_research_plan(task_spec)
    entries = [
        SourceLedgerEntry(
            question_links=["q1"],
            source_type=SourceType.VENDOR_PAGE,
            url="https://example.com/monetization",
            title="AI monetization guide",
            domain="example.com",
            reliability_score=0.8,
            selection_reason="a",
        ),
        SourceLedgerEntry(
            question_links=["q1"],
            source_type=SourceType.VENDOR_PAGE,
            url="https://example.com/monetization",
            title="AI monetization guide duplicate",
            domain="example.com",
            reliability_score=0.8,
            selection_reason="b",
        ),
        SourceLedgerEntry(
            question_links=["q2"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.org/alt",
            title="Alternatives",
            domain="example.org",
            reliability_score=0.9,
            selection_reason="q2",
        ),
        SourceLedgerEntry(
            question_links=["q3"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.net/gtm",
            title="GTM benchmark",
            domain="example.net",
            reliability_score=0.88,
            selection_reason="q3",
        ),
        SourceLedgerEntry(
            question_links=["q4"],
            source_type=SourceType.RESEARCH_PAPER,
            url="https://example.edu/risk",
            title="Risk benchmark",
            domain="example.edu",
            reliability_score=0.9,
            selection_reason="q4",
        ),
    ]

    selected = _rank_live_sources(entries, task_spec, plan, limit=5)
    urls = [entry.url for entry in selected]
    assert urls.count("https://example.com/monetization") == 1


def test_aggregate_research_spend_preserves_direct_provider_metadata() -> None:
    spend_entry = _aggregate_research_spend(
        [
            {
                "provider": "perplexity",
                "model": "sonar-pro",
                "pricing_basis": "provider_usage",
                "input_tokens": 120,
                "output_tokens": 40,
                "cost_usd": 0.012345,
            },
            {
                "provider": "perplexity",
                "model": "sonar-pro",
                "pricing_basis": "provider_usage",
                "input_tokens": 80,
                "output_tokens": 20,
                "cost_usd": 0.004321,
            },
        ],
        category=SpendCategory.RESEARCH,
        stage="initial_research",
        fallback_provider="perplexity",
        fallback_model="standard",
        branch_count=2,
        notes="Primary research pass",
    )

    assert spend_entry is not None
    assert spend_entry.provider == "perplexity"
    assert spend_entry.model == "sonar-pro"
    assert spend_entry.pricing_basis == "provider_usage"
    assert spend_entry.input_tokens == 200
    assert spend_entry.output_tokens == 60
    assert spend_entry.cost_usd == 0.016666
    assert "providers=perplexity" in spend_entry.notes


def test_aggregate_research_spend_marks_mixed_provider_fallbacks() -> None:
    spend_entry = _aggregate_research_spend(
        [
            {
                "provider": "perplexity",
                "model": "sonar-pro",
                "pricing_basis": "provider_usage",
                "input_tokens": 120,
                "output_tokens": 40,
                "cost_usd": 0.012345,
            },
            {
                "provider": "openrouter",
                "model": "perplexity/sonar-pro",
                "pricing_basis": "estimated_chars",
                "input_tokens": 90,
                "output_tokens": 30,
                "cost_usd": 0.006789,
            },
        ],
        category=SpendCategory.RESEARCH,
        stage="initial_research",
        fallback_provider="perplexity",
        fallback_model="standard",
        branch_count=2,
        notes="Primary research pass",
    )

    assert spend_entry is not None
    assert spend_entry.provider == "mixed"
    assert spend_entry.pricing_basis == "mixed"
    assert "openrouter" in spend_entry.notes
    assert "perplexity" in spend_entry.notes
