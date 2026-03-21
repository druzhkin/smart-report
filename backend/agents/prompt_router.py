import json
from pathlib import Path

import httpx
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, get_model, estimate_cost
from backend.pipeline.state import AgentState
from backend.schemas.master_prompt import RouterResult
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry

PROMPT_TECHNIQUE_MAP: dict[str, list[str]] = {
    "analytical_deep_dive": ["chain_of_thought", "tree_of_thought", "self_consistency", "structured_output", "constraint"],
    "market_research": ["chain_of_thought", "few_shot", "role_prompting", "structured_output"],
    "investment_analysis": ["chain_of_thought", "self_consistency", "constraint", "devil_advocate", "structured_output"],
    "comparative_study": ["chain_of_thought", "structured_output", "constraint", "few_shot"],
    "trend_forecast": ["tree_of_thought", "meta_prompting", "chain_of_thought", "structured_output"],
    "due_diligence": ["chain_of_thought", "self_consistency", "devil_advocate", "constraint", "structured_output"],
    "strategic_review": ["tree_of_thought", "role_prompting", "meta_prompting", "chain_of_thought", "structured_output"],
    "technical_assessment": ["chain_of_thought", "meta_prompting", "structured_output", "constraint"],
    "deep_exploratory": ["chain_of_thought", "tree_of_thought", "self_consistency", "role_prompting", "meta_prompting", "structured_output"],
}

FALLBACK_TASK_TYPE = "deep_exploratory"
CONFIDENCE_THRESHOLD = 0.7


def _load_prompt(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {path}, using default")
        return (
            "You are a prompt routing expert. Classify the task_type and select techniques. "
            "Return JSON with task_type, techniques, confidence, rationale."
        )


@llm_retry()
async def _call_llm(system_prompt: str, user_message: str, model: str) -> str:
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.3,
    }
    if supports_json_mode(model):
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def run_prompt_router(state: AgentState) -> dict:
    logger.info("Prompt Router agent started")
    model = get_model(AgentTask.PROMPT_ROUTING)
    intake = state["intake_result"]

    system_prompt = _load_prompt("prompts/prompt_router_system.txt")
    user_msg = json.dumps(intake.model_dump(), default=str)
    raw = await _call_llm(system_prompt, user_msg, model)

    try:
        parsed = parse_llm_json(raw, context="prompt_router")
    except ValueError:
        logger.warning("Prompt router JSON parse failed, using fallback")
        parsed = {}
    task_type = parsed.get("task_type", FALLBACK_TASK_TYPE)
    confidence = float(parsed.get("confidence", 0.0))
    techniques = parsed.get("techniques", [])
    rationale = parsed.get("rationale", "")

    if confidence < CONFIDENCE_THRESHOLD:
        logger.warning(
            f"Low confidence {confidence:.2f} for task_type='{task_type}', "
            f"falling back to '{FALLBACK_TASK_TYPE}'"
        )
        task_type = FALLBACK_TASK_TYPE
        techniques = PROMPT_TECHNIQUE_MAP[FALLBACK_TASK_TYPE]
        rationale = f"Fallback: original confidence {confidence:.2f} < {CONFIDENCE_THRESHOLD}"

    if task_type not in PROMPT_TECHNIQUE_MAP:
        logger.warning(f"Unknown task_type '{task_type}', falling back to '{FALLBACK_TASK_TYPE}'")
        task_type = FALLBACK_TASK_TYPE

    valid_techniques = PROMPT_TECHNIQUE_MAP.get(task_type, PROMPT_TECHNIQUE_MAP[FALLBACK_TASK_TYPE])
    techniques = [t for t in techniques if t in valid_techniques] or valid_techniques

    router_result = RouterResult(
        task_type=task_type,
        techniques=techniques,
        confidence=confidence,
        rationale=rationale,
    )

    cost = estimate_cost(AgentTask.PROMPT_ROUTING, len(user_msg) // 4, len(raw) // 4)
    logger.info(
        f"Prompt Router: task_type={task_type}, confidence={confidence:.2f}, "
        f"techniques={techniques}"
    )

    return {
        "router_result": router_result,
        "selected_techniques": techniques,
        "messages": state.get("messages", []) + [{"role": "prompt_router", "content": raw}],
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "prompt_router",
    }
