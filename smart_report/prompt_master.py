"""Prompt Master — raw analyst question -> powerful ResearchPrompt for external DR tools.

This is the first of three v4 Opus-4.7 reasoning steps. It does NOT fetch anything —
it only rewrites the question. The analyst pastes full_prompt into Perplexity DR /
OpenAI DR / Claude themselves and uploads the resulting reports back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .decomposition_templates import decompose, format_template_guidance
from .events import EventEmitter, NullEmitter
from .io import extract_json, load_prompt
from .llm import LLMResult, call_json
from .models import ResearchPrompt


# v4.5 bakeoff winner: GPT-4o scores 100/100 at $0.02/call (vs $0.18 Opus).
# Override via ModelConfig.PROMPT_MASTER_MODEL.
from .config import ModelConfig as _ModelConfig
PROMPT_MASTER_MODEL = _ModelConfig.PROMPT_MASTER_MODEL


async def generate_research_prompt(
    question: str,
    *,
    emitter: EventEmitter | None = None,
    log_dir: Path | None = None,
    mock: bool = False,
    model: str | None = None,
) -> tuple[ResearchPrompt, float]:
    """Call the Prompt Master LLM and return ``(ResearchPrompt, cost_rub)``.

    ``cost_rub`` is the per-call cost in RUB (0.0 when mocked).
    The caller (v4_orchestrator) is responsible for accumulating it into
    the V4Session via ``_accumulate_cost``.
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

    result: LLMResult = await call_json(
        role="prompt_master",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=model or PROMPT_MASTER_MODEL,
        temperature=0.4,
        mock=mock,
        log_dir=log_dir,
        response_format={"type": "json_object"} if not mock else None,
    )

    data = extract_json(result.text)
    if not isinstance(data, dict):
        raise ValueError(f"Prompt Master returned non-object JSON: {type(data).__name__}")

    prompt = ResearchPrompt(
        full_prompt=_require_str(data, "full_prompt"),
        reasoning=_optional_str(data, "reasoning"),
        expected_structure=_as_str_list(data.get("expected_structure")),
        key_entities=_as_str_list(data.get("key_entities")),
        tips_for_search=_optional_str(data, "tips_for_search"),
    )

    # v4.5 Phase 2 Step 2.1 — domain-template decomposition.
    # When the question matches a known strategic template (currently:
    # Russian RE strategic), append a structured guidance addendum so
    # the analyst runs N targeted DR queries instead of one wide one.
    # No extra LLM call; no schema change. Auto-retrieval is Phase 3.
    sub_queries = decompose(q)
    if sub_queries:
        guidance = format_template_guidance(sub_queries)
        prompt = prompt.model_copy(
            update={"full_prompt": prompt.full_prompt + guidance}
        )

    em.emit(
        "prompt_master",
        "Research-промт готов",
        data={
            "full_prompt_chars": len(prompt.full_prompt),
            "n_entities": len(prompt.key_entities),
            "n_sections": len(prompt.expected_structure),
            "template_applied": (
                "russian_re_strategic" if sub_queries else None
            ),
            "cost_rub": result.cost_rub,
        },
    )
    return prompt, result.cost_rub


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
