from __future__ import annotations

from backend.v2.intake import build_clarification_pack, build_request_spec, build_task_spec, infer_subject
from backend.v2.models import ReportType


def test_request_spec_classifies_known_prompt() -> None:
    spec = build_request_spec(
        "Compare open-source coding models for a self-hosted code review assistant.",
        depth="standard",
    )

    assert spec.report_type == ReportType.VENDOR_EVALUATION
    assert spec.subject == "Open-source coding models for self-hosted assistants"
    assert spec.decision_context
    assert spec.budget_tier.value == "standard"


def test_clarification_pack_asks_semantic_questions() -> None:
    spec = build_request_spec("Evaluate LLM observability platforms for an enterprise document workflow product.")
    pack = build_clarification_pack("test-run", spec)

    fields = [question.field.value for question in pack.questions]
    assert fields == ["decision_context", "evaluation_dimensions", "geography", "budget"]
    assert all(question.prompt for question in pack.questions)
    assert all(question.rationale for question in pack.questions)


def test_task_spec_applies_answers_structurally() -> None:
    spec = build_request_spec("Map the enterprise RAG platform landscape for internal knowledge assistants.")
    task = build_task_spec(
        spec,
        answers={
            "decision-context": "Choose a platform for an internal pilot.",
            "dimensions": "retrieval quality, enterprise controls, deployment flexibility",
            "geography": "europe",
            "budget": "EU hosting preferred; moderate budget.",
        },
    )

    assert task.request_spec.decision_context == "Choose a platform for an internal pilot."
    assert task.request_spec.geography == "europe"
    assert task.evaluation_dimensions == [
        "retrieval quality",
        "enterprise controls",
        "deployment flexibility",
    ]
    assert task.constraints == ["EU hosting preferred; moderate budget."]


def test_web_search_deep_research_topic_uses_reference_pack_questions() -> None:
    spec = build_request_spec("Best LLM models and GitHub projects for web search and deep research in 2026", depth="deep")
    task = build_task_spec(
        spec,
        answers={
            "decision-context": "Choose the default Smart Report v2 stack that should outperform Perplexity.",
        },
    )

    assert spec.subject == "LLM and GitHub stacks for web search and deep research"
    assert task.must_cover_questions[0].startswith("Which managed models and APIs")
    assert any("Perplexity" in question for question in task.must_cover_questions)


def test_infer_subject_prefers_clean_head_clause_for_long_queries() -> None:
    subject = infer_subject(
        "Design a decision-grade architecture for an evidence-first research product that beats consumer answer engines on traceability and revision quality by combining managed search APIs with open-source orchestration frameworks and explicit build-vs-buy boundaries for the next iteration."
    )

    assert subject == "Design a decision-grade architecture for an evidence-first research product"
