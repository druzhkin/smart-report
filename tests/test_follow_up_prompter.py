"""Tests for the v4.5 Phase 2 Step 2.4 follow-up DR prompter.

Mock-only — no LLM, no network. Live coverage runs through the
combined Step 2.3 + 2.4 acceptance fixture.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from smart_report.follow_up_prompter import (
    DEFAULT_FOLLOW_UP_MODEL,
    _parse_follow_up_output,
    generate_follow_up_prompts,
)
from smart_report.llm import LLMResult
from smart_report.models import EvidenceGap, FollowUpPrompt


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _gap(
    sid: str,
    *,
    severity: str = "moderate",
    text: str = "Какие риски рынка жилья при ставке ЦБ 16%?",
    sources: list[str] | None = None,
    reason: str = "Не найдено авторитетных источников.",
) -> EvidenceGap:
    return EvidenceGap(
        sub_question_id=sid,
        sub_question_text=text,
        severity=severity,  # type: ignore[arg-type]
        reason=reason,
        suggested_search_directions=sources or ["regulatory", "market_data"],
    )


def _follow_up_response(items: list[dict]) -> str:
    return json.dumps({"follow_up_prompts": items}, ensure_ascii=False)


def _stub_call_json(text: str):
    async def _stub(*a, **kw):
        return LLMResult(text=text, cost_rub=0.5)
    return _stub


# ---------------------------------------------------------------------------
# Spec acceptance cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critical_gap_generates_prompt():
    """Critical gap → at least one FollowUpPrompt with non-empty prompt_text."""
    g = _gap("sq1", severity="critical")
    payload = _follow_up_response([
        {
            "sub_question_id": "sq1",
            "prompt_text": "Дайте подробный отчёт по рискам ставки ЦБ для рынка жилья 2026, опираясь на ЦБ РФ и Минстрой.",
            "suggested_dr_tool": "perplexity_dr",
            "rationale": "Critical gap, RU regulatory sources are best fit.",
        }
    ])
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_stub_call_json(payload),
    ):
        result = await generate_follow_up_prompts([g], original_query="Q", model=DEFAULT_FOLLOW_UP_MODEL)
    assert len(result) == 1
    assert result[0].sub_question_id == "sq1"
    assert result[0].prompt_text.strip() != ""


@pytest.mark.asyncio
async def test_moderate_gap_generates_prompt():
    g = _gap("sq2", severity="moderate")
    payload = _follow_up_response([
        {
            "sub_question_id": "sq2",
            "prompt_text": "Подробный обзор рынка жилья премиум-сегмента 2024-2025 с цитированием Knight Frank и JLL.",
            "suggested_dr_tool": "perplexity_dr",
            "rationale": "Moderate — cite top consultancies.",
        }
    ])
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_stub_call_json(payload),
    ):
        result = await generate_follow_up_prompts([g], original_query="Q")
    assert len(result) == 1
    assert result[0].sub_question_id == "sq2"


@pytest.mark.asyncio
async def test_minor_gap_skipped_no_llm_call():
    """Minor severity (1 of 2 authoritative) is not worth a second DR run.
    The function must short-circuit to empty list WITHOUT invoking the LLM.
    """
    call_count = 0

    async def counting_stub(*a, **kw):
        nonlocal call_count
        call_count += 1
        return LLMResult(text=_follow_up_response([]), cost_rub=0.0)

    g = _gap("sq3", severity="minor")
    with patch("smart_report.follow_up_prompter.call_json", new=counting_stub):
        result = await generate_follow_up_prompts([g], original_query="Q")
    assert result == []
    assert call_count == 0


@pytest.mark.asyncio
async def test_dr_tool_selection_russian_re():
    """When the LLM picks perplexity_dr for a RU regulatory gap, it
    propagates through to the FollowUpPrompt unchanged.
    """
    g = _gap(
        "sq1",
        severity="critical",
        text="Какие изменения 214-ФЗ в 2026 году?",
        sources=["regulatory", "minstroy", "pravo"],
    )
    payload = _follow_up_response([
        {
            "sub_question_id": "sq1",
            "prompt_text": "Найди изменения в 214-ФЗ принятые в 2026 году с цитированием pravo.gov.ru и Минстроя.",
            "suggested_dr_tool": "perplexity_dr",
            "rationale": "Regulatory RU topic — Perplexity DR has best ru-domain coverage.",
        }
    ])
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_stub_call_json(payload),
    ):
        result = await generate_follow_up_prompts([g], original_query="Q")
    assert len(result) == 1
    assert result[0].suggested_dr_tool == "perplexity_dr"


@pytest.mark.asyncio
async def test_handles_haiku_json_fences():
    """Same Haiku 4.5 quirk caught in Step 2.2 acceptance: JSON wrapped
    in ```json fences. Parser uses extract_json (paid lesson 7.9).
    """
    g = _gap("sq1", severity="critical")
    inner = json.dumps({
        "follow_up_prompts": [
            {
                "sub_question_id": "sq1",
                "prompt_text": "valid prompt text wrapped in fences",
                "suggested_dr_tool": "perplexity_dr",
                "rationale": "r",
            }
        ]
    }, ensure_ascii=False)
    fence_wrapped = f"```json\n{inner}\n```"
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_stub_call_json(fence_wrapped),
    ):
        result = await generate_follow_up_prompts([g], original_query="Q")
    assert len(result) == 1
    assert result[0].prompt_text == "valid prompt text wrapped in fences"


@pytest.mark.asyncio
async def test_no_gaps_returns_empty_list():
    """Empty gap list → empty result without LLM call (cheaper than no-op'ing
    a real network round-trip).
    """
    call_count = 0

    async def counting_stub(*a, **kw):
        nonlocal call_count
        call_count += 1
        return LLMResult(text=_follow_up_response([]), cost_rub=0.0)

    with patch("smart_report.follow_up_prompter.call_json", new=counting_stub):
        result = await generate_follow_up_prompts([], original_query="Q")
    assert result == []
    assert call_count == 0


# ---------------------------------------------------------------------------
# Tolerant failure modes — must NOT crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_json_returns_empty():
    g = _gap("sq1", severity="critical")
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_stub_call_json("this is not json {[}"),
    ):
        result = await generate_follow_up_prompts([g], original_query="Q")
    assert result == []


@pytest.mark.asyncio
async def test_unknown_sub_question_id_filtered_out():
    """LLM hallucinates an id we didn't ask about — must drop the
    hallucinated entry rather than emit a FollowUpPrompt for it.
    """
    g = _gap("sq1", severity="critical")
    payload = _follow_up_response([
        {
            "sub_question_id": "sq1",
            "prompt_text": "valid",
            "suggested_dr_tool": "perplexity_dr",
        },
        {
            "sub_question_id": "sq999",  # not in actionable set
            "prompt_text": "hallucinated",
            "suggested_dr_tool": "chatgpt_dr",
        },
    ])
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_stub_call_json(payload),
    ):
        result = await generate_follow_up_prompts([g], original_query="Q")
    assert len(result) == 1
    assert result[0].sub_question_id == "sq1"


@pytest.mark.asyncio
async def test_invalid_dr_tool_falls_back_to_default():
    """LLM picks an unrecognised tool → silently default to perplexity_dr."""
    g = _gap("sq1", severity="critical")
    payload = _follow_up_response([
        {
            "sub_question_id": "sq1",
            "prompt_text": "valid",
            "suggested_dr_tool": "you_dot_com",  # not in our literal
            "rationale": "r",
        }
    ])
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_stub_call_json(payload),
    ):
        result = await generate_follow_up_prompts([g], original_query="Q")
    assert result[0].suggested_dr_tool == "perplexity_dr"


@pytest.mark.asyncio
async def test_mock_flag_short_circuits_without_llm():
    g = _gap("sq1", severity="critical")

    async def explosive_stub(*a, **kw):
        raise AssertionError("call_json must not be invoked when mock=True")

    with patch(
        "smart_report.follow_up_prompter.call_json", new=explosive_stub
    ):
        result = await generate_follow_up_prompts(
            [g], original_query="Q", mock=True
        )
    assert result == []


# ---------------------------------------------------------------------------
# _parse_follow_up_output direct tests
# ---------------------------------------------------------------------------


def test_parse_drops_items_missing_prompt_text():
    raw = _follow_up_response([
        {"sub_question_id": "sq1", "prompt_text": "valid"},
        {"sub_question_id": "sq2"},  # missing prompt_text
        {"sub_question_id": "sq3", "prompt_text": "  "},  # whitespace only
    ])
    result = _parse_follow_up_output(raw, actionable_ids={"sq1", "sq2", "sq3"})
    assert len(result) == 1
    assert result[0].sub_question_id == "sq1"


def test_parse_drops_non_dict_items():
    raw = _follow_up_response([
        {"sub_question_id": "sq1", "prompt_text": "valid"},
        "not a dict",
        12345,
    ])
    result = _parse_follow_up_output(raw, actionable_ids={"sq1"})
    assert len(result) == 1
