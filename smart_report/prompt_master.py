"""Prompt Master — raw analyst question -> powerful ResearchPrompt for external DR tools.

This is the first of three v4 Opus-4.7 reasoning steps. It does NOT fetch anything —
it only rewrites the question. The analyst pastes full_prompt into Perplexity DR /
OpenAI DR / Claude themselves and uploads the resulting reports back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .events import EventEmitter, NullEmitter
from .io import extract_json, load_prompt
from .llm import chat
from .models import ResearchPrompt


# v4 spec §7 rule 2: Opus 4.7, don't swap.
PROMPT_MASTER_MODEL = "anthropic/claude-opus-4-7"


async def generate_research_prompt(
    question: str,
    *,
    emitter: EventEmitter | None = None,
    log_dir: Path | None = None,
    mock: bool = False,
) -> ResearchPrompt:
    """Call the Prompt Master LLM and return a ResearchPrompt.

    The caller is responsible for attributing cost / updating the V4Session.
    """
    em: EventEmitter = emitter or NullEmitter()
    q = (question or "").strip()
    if not q:
        raise ValueError("question must be non-empty")

    em.emit(
        "prompt_master",
        "Генерирую research-промт",
        data={"question_preview": q[:120]},
    )

    system = load_prompt("prompt_master")
    if not system:
        raise RuntimeError(
            "prompts/prompt_master.md not found — Track A must commit it alongside this module."
        )
    user = (
        "Raw analyst question:\n"
        f"{q}\n\n"
        "Return only the JSON object described in the output contract. "
        "No preface, no trailing commentary."
    )

    raw = await chat(
        role="prompt_master",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=PROMPT_MASTER_MODEL,
        temperature=0.4,
        mock=mock,
        log_dir=log_dir,
        response_format={"type": "json_object"} if not mock else None,
    )

    data = extract_json(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Prompt Master returned non-object JSON: {type(data).__name__}")

    prompt = ResearchPrompt(
        full_prompt=_require_str(data, "full_prompt"),
        reasoning=_optional_str(data, "reasoning"),
        expected_structure=_as_str_list(data.get("expected_structure")),
        key_entities=_as_str_list(data.get("key_entities")),
        tips_for_search=_optional_str(data, "tips_for_search"),
    )

    em.emit(
        "prompt_master",
        "Research-промт готов",
        data={
            "full_prompt_chars": len(prompt.full_prompt),
            "n_entities": len(prompt.key_entities),
            "n_sections": len(prompt.expected_structure),
        },
    )
    return prompt


def _require_str(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"Prompt Master JSON missing required string field '{key}'")
    return v.strip()


def _optional_str(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    return v.strip() if isinstance(v, str) else ""


def _as_str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for item in v:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out
