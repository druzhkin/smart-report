"""Tests for the v4.5 Phase 2 Step 2.2 LLM-driven sub-question planner.

Covers:
  * generate_sub_questions output shape (mocked LLM)
  * Schema validation (id, text, depends_on, rationale, suggested_sources)
  * Dependency tracking preservation
  * Tolerant failure modes:
      - Malformed JSON → empty list, no crash
      - Schema-invalid items → skipped, valid items returned
      - Empty query → empty list without LLM call
  * format_planner_guidance Markdown shape
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from smart_report.decomposition_templates import (
    DEFAULT_PLANNER_MODEL,
    _parse_planner_output,
    format_planner_guidance,
    generate_sub_questions,
)
from smart_report.llm import LLMResult
from smart_report.models import SubQuestion


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _planner_response(items: list[dict]) -> str:
    return json.dumps({"sub_questions": items}, ensure_ascii=False)


def _stub_call_json(text: str):
    async def _stub(*a, **kw):
        return LLMResult(text=text, cost_rub=0.5)
    return _stub


# ---------------------------------------------------------------------------
# generate_sub_questions — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_sub_questions_returns_validated_list():
    payload = _planner_response([
        {
            "id": "sq1",
            "text": "What is the current regulatory baseline for Russian RE in 2026?",
            "depends_on": [],
            "rationale": "Sets the policy backdrop everything else reads against.",
            "suggested_sources": ["regulatory", "industry_report"],
        },
        {
            "id": "sq2",
            "text": "Which segments have shown >15% YoY price moves in 2024-2025?",
            "depends_on": ["sq1"],
            "rationale": "Identifies where the policy backdrop binds hardest.",
            "suggested_sources": ["market_data"],
        },
        {
            "id": "sq3",
            "text": "What developer pipeline plans to absorb that demand?",
            "depends_on": ["sq2"],
            "rationale": "Covers the supply-side response to the demand signal.",
            "suggested_sources": ["industry_report", "news"],
        },
    ])
    with patch(
        "smart_report.decomposition_templates.call_json",
        new=_stub_call_json(payload),
    ):
        result = await generate_sub_questions("какие тренды на рынке 2026", model=DEFAULT_PLANNER_MODEL)

    assert len(result) == 3
    assert all(isinstance(sq, SubQuestion) for sq in result)
    assert result[0].id == "sq1"
    assert result[0].depends_on == []
    assert result[1].depends_on == ["sq1"]
    assert "market_data" in result[1].suggested_sources


@pytest.mark.asyncio
async def test_generate_sub_questions_caps_at_max():
    """If the LLM returns more sub-questions than max_sub_questions, the
    extras must be silently dropped. Otherwise downstream guidance text
    blows out and we lose the whole point of the cap.
    """
    items = [
        {
            "id": f"sq{i}",
            "text": f"sub-question {i}",
            "rationale": "r",
            "suggested_sources": ["news"],
        }
        for i in range(8)
    ]
    payload = _planner_response(items)
    with patch(
        "smart_report.decomposition_templates.call_json",
        new=_stub_call_json(payload),
    ):
        result = await generate_sub_questions(
            "test query that is long enough to count as strategic", max_sub_questions=4
        )
    assert len(result) == 4


@pytest.mark.asyncio
async def test_empty_query_returns_empty_without_llm_call():
    """The planner must not even initialize an HTTP client for an empty
    query — it's a fast pre-flight reject.
    """
    call_count = 0

    async def counting_stub(*a, **kw):
        nonlocal call_count
        call_count += 1
        return LLMResult(text=_planner_response([]), cost_rub=0.0)

    with patch("smart_report.decomposition_templates.call_json", new=counting_stub):
        assert await generate_sub_questions("") == []
        assert await generate_sub_questions("   ") == []
    assert call_count == 0


@pytest.mark.asyncio
async def test_mock_flag_short_circuits_without_llm():
    """``mock=True`` is the unit-test contract: never reach call_json."""

    async def explosive_stub(*a, **kw):
        raise AssertionError("call_json must not be invoked when mock=True")

    with patch("smart_report.decomposition_templates.call_json", new=explosive_stub):
        result = await generate_sub_questions("real query here", mock=True)
    assert result == []


# ---------------------------------------------------------------------------
# Tolerant failure modes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_json_returns_empty_list_not_crash():
    """A bad JSON response must NOT bring down the orchestrator. The
    Step 2.2 contract says: planner failure → empty list →
    decomposition_method = "llm_planner_failed".
    """
    with patch(
        "smart_report.decomposition_templates.call_json",
        new=_stub_call_json("this is not json at all }{[}"),
    ):
        result = await generate_sub_questions("strategic query that is long enough")
    assert result == []


@pytest.mark.asyncio
async def test_non_dict_top_level_returns_empty():
    """LLM occasionally returns a bare array; must not crash."""
    with patch(
        "smart_report.decomposition_templates.call_json",
        new=_stub_call_json('["sq1","sq2"]'),
    ):
        result = await generate_sub_questions("strategic query that is long enough")
    assert result == []


@pytest.mark.asyncio
async def test_schema_invalid_items_are_skipped_not_fatal():
    """Mixed valid+invalid items: the valid ones come through, the
    invalid ones are silently dropped. Better partial decomposition
    than no decomposition.
    """
    payload = _planner_response([
        {"id": "sq1", "text": "valid sub-question one", "rationale": "r"},
        {"id": "sq2"},  # missing text — should be dropped (empty text post-strip)
        "not even an object",  # type error — should be dropped
        {"id": "sq3", "text": "another valid one", "rationale": "r"},
    ])
    with patch(
        "smart_report.decomposition_templates.call_json",
        new=_stub_call_json(payload),
    ):
        result = await generate_sub_questions("strategic query that is long enough")
    assert len(result) == 2
    assert {sq.id for sq in result} == {"sq1", "sq3"}


@pytest.mark.asyncio
async def test_http_error_returns_empty_no_crash():
    """A flaky OpenRouter call must downgrade to no-decomposition, not
    propagate.
    """
    async def boom(*a, **kw):
        raise RuntimeError("simulated HTTP 503")

    with patch("smart_report.decomposition_templates.call_json", new=boom):
        result = await generate_sub_questions("strategic query that is long enough")
    assert result == []


# ---------------------------------------------------------------------------
# _parse_planner_output unit tests (no LLM, no async)
# ---------------------------------------------------------------------------


def test_parse_planner_output_preserves_dependencies():
    raw = _planner_response([
        {"id": "sq1", "text": "first", "rationale": "r1"},
        {"id": "sq2", "text": "second", "depends_on": ["sq1"], "rationale": "r2"},
        {"id": "sq3", "text": "third", "depends_on": ["sq1", "sq2"], "rationale": "r3"},
    ])
    result = _parse_planner_output(raw, cap=5)
    assert [sq.id for sq in result] == ["sq1", "sq2", "sq3"]
    assert result[1].depends_on == ["sq1"]
    assert result[2].depends_on == ["sq1", "sq2"]


def test_parse_planner_output_drops_non_string_dependencies():
    raw = _planner_response([
        {"id": "sq1", "text": "first", "rationale": "r"},
        {"id": "sq2", "text": "second", "depends_on": ["sq1", 999, None], "rationale": "r"},
    ])
    result = _parse_planner_output(raw, cap=5)
    assert result[1].depends_on == ["sq1"]


def test_parse_planner_output_handles_missing_optional_fields():
    """Only ``text`` is strictly required; missing rationale/suggested_sources
    must be tolerated (empty defaults).
    """
    raw = _planner_response([
        {"id": "sq1", "text": "minimal sub-question"},
    ])
    result = _parse_planner_output(raw, cap=5)
    assert len(result) == 1
    assert result[0].rationale == ""
    assert result[0].suggested_sources == []


def test_parse_planner_output_assigns_default_id_when_missing():
    raw = _planner_response([
        {"text": "first sub"},
        {"text": "second sub"},
    ])
    result = _parse_planner_output(raw, cap=5)
    assert len(result) == 2
    assert result[0].id == "sq1"
    assert result[1].id == "sq2"


# ---------------------------------------------------------------------------
# format_planner_guidance
# ---------------------------------------------------------------------------


def test_format_planner_guidance_empty_for_empty_list():
    assert format_planner_guidance([]) == ""


def test_format_planner_guidance_renders_full_shape():
    sub_qs = [
        SubQuestion(
            id="sq1",
            text="What's the regulatory baseline?",
            rationale="Sets the policy frame.",
            suggested_sources=["regulatory"],
        ),
        SubQuestion(
            id="sq2",
            text="Where do prices move fastest?",
            depends_on=["sq1"],
            rationale="Locates impact.",
            suggested_sources=["market_data", "industry_report"],
        ),
    ]
    text = format_planner_guidance(sub_qs)
    # Header mentions count and method
    assert "planner LLM" in text
    assert "2 sub-questions" in text
    # Each sub-question rendered
    assert "`sq1`" in text
    assert "`sq2`" in text
    assert "What's the regulatory baseline?" in text
    assert "Where do prices move fastest?" in text
    # Dependencies surfaced
    assert "Зависит от:" in text
    assert "`sq1`" in text  # dependency reference
    # Source types surfaced
    assert "regulatory" in text
    assert "market_data" in text
