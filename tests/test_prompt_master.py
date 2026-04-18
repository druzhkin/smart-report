"""prompt_master.generate_research_prompt — LLM call mocked out."""

from __future__ import annotations

import json

import pytest

from smart_report import prompt_master as pm_module
from smart_report.events import ListEmitter
from smart_report.models import ResearchPrompt
from smart_report.prompt_master import generate_research_prompt


_STUB_FULL_PROMPT = (
    "Goal: evaluate whether brand, speed, or product is the dominant driver of "
    "commercial success for developers in Moscow's business-class residential "
    "segment over 2023-2025. Analyse the following nine developers by 2024 "
    "supply volume, time-to-market, and customer NPS (see ERZ, bnMAP, CIAN Pro "
    "for sources): PIK, Donstroy, MR Group, Level Group, Etalon, Sminex, "
    "Capital Group, FSK, A101. Structure the answer in six sections and cite "
    "every number with a URL. Do not hedge — pick a driver and defend it."
)

_STUB_RESPONSE = json.dumps(
    {
        "full_prompt": _STUB_FULL_PROMPT,
        "reasoning": "Splits a vague question into measurable components and names concrete players.",
        "expected_structure": ["Player scoring", "Brand", "Speed", "Product", "Correlation", "Limits"],
        "key_entities": ["PIK", "Donstroy", "MR Group", "ERZ", "bnMAP"],
        "tips_for_search": "Perplexity DR for figures; OpenAI DR for narrative sections.",
    },
    ensure_ascii=False,
)


@pytest.fixture
def mock_chat(monkeypatch):
    calls: list[dict] = []

    async def _stub(*args, **kwargs):
        calls.append(kwargs)
        return _STUB_RESPONSE

    monkeypatch.setattr(pm_module, "chat", _stub)
    return calls


@pytest.mark.asyncio
async def test_generate_research_prompt_returns_research_prompt(mock_chat):
    rp = await generate_research_prompt("what defines developer success in Moscow?")
    assert isinstance(rp, ResearchPrompt)
    assert len(rp.full_prompt) > 200
    assert "PIK" in rp.key_entities
    assert len(rp.expected_structure) == 6
    assert rp.reasoning


@pytest.mark.asyncio
async def test_generate_research_prompt_uses_opus_4_7(mock_chat):
    await generate_research_prompt("short question")
    assert mock_chat, "chat() was not called"
    assert mock_chat[0]["model"] == "anthropic/claude-opus-4-7"
    assert mock_chat[0]["role"] == "prompt_master"


@pytest.mark.asyncio
async def test_generate_research_prompt_emits_events(mock_chat):
    em = ListEmitter()
    await generate_research_prompt("q?", emitter=em)
    phases = [e["phase"] for e in em.events]
    assert phases.count("prompt_master") >= 2  # start + done


@pytest.mark.asyncio
async def test_generate_research_prompt_rejects_empty_question(mock_chat):
    with pytest.raises(ValueError):
        await generate_research_prompt("   ")


@pytest.mark.asyncio
async def test_generate_research_prompt_rejects_missing_full_prompt(monkeypatch):
    async def _bad_stub(*args, **kwargs):
        return json.dumps({"reasoning": "no full_prompt here"})

    monkeypatch.setattr(pm_module, "chat", _bad_stub)
    with pytest.raises(ValueError):
        await generate_research_prompt("x?")
