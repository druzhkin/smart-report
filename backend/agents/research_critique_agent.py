from __future__ import annotations

import json

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, estimate_cost, get_model
from backend.pipeline.state import AgentState
from backend.schemas.quality import ResearchCritiqueResult
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry


@llm_retry()
async def _call_llm(system_prompt: str, user_message: str, model: str) -> str:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://smart-report.app",
                "X-Title": "Smart Report",
            },
            json={
                "model": model,
                "provider": {"order": ["OpenAI"]},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 1,
                **( {"response_format": {"type": "json_object"}} if supports_json_mode(model) else {} ),
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


@traceable(name="research_critique_agent")
async def run_research_critique(state: AgentState) -> dict:
    logger.info("Research Critique agent started")
    model = get_model(AgentTask.CRITIQUE)
    results = state.get("research_results", [])

    if not results:
        empty = ResearchCritiqueResult(verdict="ACCEPT", overall_score=1.0)
        return {
            "messages": state.get("messages", []) + [
                {"role": "research_critique", "content": empty.model_dump_json()}
            ],
            "research_critique_result": empty,
            "current_agent": "research_critique",
        }

    system_prompt = _load_prompt("prompts/research_critique_system.txt")

    citation_msg = next(
        (m for m in state.get("messages", []) if m["role"] == "citation_verifier"),
        None,
    )
    reflect_msg = next(
        (m for m in state.get("messages", []) if m["role"] == "reflect"),
        None,
    )

    context = {
        "research_findings": [r.model_dump(mode="json") for r in results],
        "citation_verification": json.loads(citation_msg["content"]) if citation_msg else None,
        "reflection": json.loads(reflect_msg["content"]) if reflect_msg else None,
    }
    user_message = json.dumps(context, default=str)

    raw = await _call_llm(system_prompt, user_message, model)
    try:
        data = parse_llm_json(raw, context="research_critique")
        critique = ResearchCritiqueResult(**data)
    except (ValueError, Exception) as exc:
        logger.warning(f"Research critique parse failed, using PASS fallback: {exc}")
        critique = ResearchCritiqueResult(verdict="PROCEED", overall_score=0.7)

    cost = estimate_cost(
        AgentTask.CRITIQUE, len(user_message) // 4, len(raw) // 4
    )

    logger.info(
        f"Research Critique: verdict={critique.verdict}, "
        f"overall={critique.overall_score:.2f}, "
        f"blocking_issues={len(critique.blocking_issues)}"
    )

    return {
        "messages": state.get("messages", []) + [
            {"role": "research_critique", "content": raw}
        ],
        "research_critique_result": critique,
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "research_critique",
    }


def _load_prompt(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {path}, using fallback")
        return _FALLBACK_PROMPT


_FALLBACK_PROMPT = """\
You are a deep research critique agent (o3). Your role is rigorous fact-checking.

Evaluate research on exactly 5 criteria (score 0.0-1.0 each):
1. factual_accuracy — Are claims factually correct and verifiable?
2. coverage — Does the research cover the topic comprehensively?
3. logic — Is the reasoning logically sound, free of fallacies?
4. depth — Is the analysis deep enough for the stated complexity?
5. sources — Are sources reliable, diverse, and properly cited?

Determine verdict:
- ACCEPT: overall_score >= 0.7 AND no blocking issues
- REVISE: overall_score < 0.7 OR blocking issues exist

Return JSON:
{
    "verdict": "ACCEPT" or "REVISE",
    "scores": {
        "factual_accuracy": 0.0-1.0,
        "coverage": 0.0-1.0,
        "logic": 0.0-1.0,
        "depth": 0.0-1.0,
        "sources": 0.0-1.0
    },
    "overall_score": 0.0-1.0,
    "blocking_issues": ["issue that MUST be fixed before acceptance"],
    "recommendations": ["optional improvement"],
    "challenged_claims": [{"claim": "...", "challenge": "...", "severity": "high|medium|low"}]
}
"""
