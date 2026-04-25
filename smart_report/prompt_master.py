"""Prompt Master — raw analyst question -> powerful ResearchPrompt for external DR tools.

This is the first of three v4 Opus-4.7 reasoning steps. It does NOT fetch anything —
it only rewrites the question. The analyst pastes full_prompt into Perplexity DR /
OpenAI DR / Claude themselves and uploads the resulting reports back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .decomposition_templates import (
    DEFAULT_PLANNER_MODEL,
    decompose,
    format_planner_guidance,
    format_template_guidance,
    generate_sub_questions,
    is_strategic_query,
)
from .events import EventEmitter, NullEmitter
from .io import extract_json, load_prompt
from .llm import LLMResult, call_json
from .models import ResearchPrompt, SubQuestion


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
    planner_model: str | None = None,
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

    # v4.5 Phase 2 — three-way decomposition routing:
    #   Step 2.1 path: is_russian_re_strategic → fixed RU RE template,
    #                  zero LLM call, deterministic guidance addendum.
    #   Step 2.2 path: is_strategic_query → LLM planner generates 3-5
    #                  sub-questions with dependencies, costs ~$0.005-0.02
    #                  on Haiku 4.5. Falls back to "none" decomposition
    #                  on planner failure.
    #   else        : pass-through, single-pass query, no addendum.
    # Domain template wins precedence — it's free and pre-validated.
    decomposition_method: str = "none"
    sub_questions_v22: list[SubQuestion] = []
    template_sub_queries = decompose(q)

    if template_sub_queries:
        guidance = format_template_guidance(template_sub_queries)
        prompt = prompt.model_copy(
            update={
                "full_prompt": prompt.full_prompt + guidance,
                "decomposition_method": "domain_template_ru_re",
            }
        )
        decomposition_method = "domain_template_ru_re"
    elif is_strategic_query(q):
        sub_questions_v22 = await generate_sub_questions(
            q,
            model=planner_model or DEFAULT_PLANNER_MODEL,
            mock=mock,
        )
        if sub_questions_v22:
            guidance = format_planner_guidance(sub_questions_v22)
            prompt = prompt.model_copy(
                update={
                    "full_prompt": prompt.full_prompt + guidance,
                    "decomposition_method": "llm_planner",
                    "sub_questions": sub_questions_v22,
                }
            )
            decomposition_method = "llm_planner"
        else:
            # Planner returned empty — record the failure but keep the
            # original full_prompt so the analyst still has something to
            # paste into a DR tool.
            prompt = prompt.model_copy(
                update={"decomposition_method": "llm_planner_failed"}
            )
            decomposition_method = "llm_planner_failed"

    em.emit(
        "prompt_master",
        "Research-промт готов",
        data={
            "full_prompt_chars": len(prompt.full_prompt),
            "n_entities": len(prompt.key_entities),
            "n_sections": len(prompt.expected_structure),
            "decomposition_method": decomposition_method,
            "sub_questions_count": (
                len(template_sub_queries) if template_sub_queries
                else len(sub_questions_v22)
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
