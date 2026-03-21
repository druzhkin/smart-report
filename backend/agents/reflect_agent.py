from __future__ import annotations

import json

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, estimate_cost, get_model
from backend.pipeline.state import AgentState
from backend.schemas.quality import ReflectResult
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry


@llm_retry()
async def _call_llm(system_prompt: str, user_message: str, model: str) -> str:
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.4,
    }
    if supports_json_mode(model):
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://smart-report.app",
                "X-Title": "Smart Report",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


@traceable(name="reflect_agent")
async def run_reflect(state: AgentState) -> dict:
    logger.info("Reflect agent started")
    model = get_model(AgentTask.REFLECTION)
    results = state.get("research_results", [])

    if not results:
        empty = ReflectResult()
        return {
            "messages": state.get("messages", []) + [
                {"role": "reflect", "content": empty.model_dump_json()}
            ],
            "reflect_result": empty,
            "current_agent": "reflect",
        }

    system_prompt = _load_prompt("prompts/reflect_system.txt")

    intake = state.get("intake_result")
    context = {
        "original_query": intake.cleaned_query if intake else state.get("original_request", ""),
        "research_findings": [r.model_dump(mode="json") for r in results],
    }
    user_message = json.dumps(context, default=str)

    raw = await _call_llm(system_prompt, user_message, model)

    try:
        data = parse_llm_json(raw, context="reflect_agent")
        reflect_result = ReflectResult(**data)
    except (ValueError, Exception) as exc:
        logger.warning(f"Reflect parse failed, using PASS fallback: {exc}")
        reflect_result = ReflectResult()

    cost = estimate_cost(
        AgentTask.REFLECTION, len(user_message) // 4, len(raw) // 4
    )

    logger.info(
        f"Reflect: {len(reflect_result.issues)} issues, "
        f"{len(reflect_result.additional_queries)} additional queries, "
        f"quality_score={reflect_result.quality_score:.2f}"
    )

    return {
        "messages": state.get("messages", []) + [
            {"role": "reflect", "content": reflect_result.model_dump_json()}
        ],
        "reflect_result": reflect_result,
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "reflect",
    }


def _load_prompt(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {path}, using fallback")
        return _FALLBACK_PROMPT


_FALLBACK_PROMPT = """\
You are a first-pass research quality reflection agent (claude-opus-4.6).

Analyze the research findings critically. Identify:
1. Structure gaps — missing sections, weak transitions
2. Content gaps — topics not covered, shallow treatment
3. Evidence gaps — unsupported claims, single-source conclusions
4. Perspective gaps — missing viewpoints, bias indicators

Return JSON matching this schema:
{
    "issues": [{"description": "...", "severity": "critical|major|minor", "section": "..."}],
    "additional_queries": ["query to fill gap 1", "..."],
    "strengths": ["..."],
    "weaknesses": ["..."],
    "gaps": ["..."],
    "quality_score": 0.0-1.0,
    "needs_more_research": true/false
}
"""
