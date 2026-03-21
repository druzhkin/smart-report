import asyncio
import json

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, get_model, estimate_cost
from backend.pipeline.state import AgentState
from backend.schemas.research_result import ResearchResult, Source
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry

SYSTEM_PROMPT = """\
You are a summarization specialist. Compress the research text to under 2000 tokens while:
1. Preserving ALL factual claims and key data points.
2. Preserving ALL citation references — do not drop any source.
3. Removing redundant phrasing, filler, and repeated information.
4. Maintaining logical structure.

Return valid JSON:
{
  "summary": "compressed text here",
  "key_facts": ["fact1", "fact2"],
  "preserved_citation_count": 5
}
"""

MAX_INPUT_CHARS = 12000


@llm_retry()
async def _call_summarize(text: str, model: str) -> str:
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text[:MAX_INPUT_CHARS]},
        ],
        "temperature": 0.2,
        "max_tokens": 2500,
    }
    if supports_json_mode(model):
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _summarize_one(result: ResearchResult, model: str) -> tuple[ResearchResult, float]:
    """Summarize a single ResearchResult independently (context efficiency)."""
    findings_text = "\n".join(f"- {f}" for f in result.findings)
    sources_text = "\n".join(
        f"[{i+1}] {s.title} ({s.domain}): {s.snippet[:200]}"
        for i, s in enumerate(result.sources)
    )
    user_text = f"Query: {result.query}\n\nFindings:\n{findings_text}\n\nSources:\n{sources_text}"

    raw = await _call_summarize(user_text, model)
    try:
        parsed = parse_llm_json(raw, context="summarization_agent")
    except ValueError:
        logger.warning(f"Summarization parse failed for query '{result.query}', using raw text")
        parsed = {"key_facts": [raw[:2000]], "summary": raw[:2000]}

    summarized = ResearchResult(
        query=result.query,
        findings=parsed.get("key_facts", [parsed.get("summary", "")]),
        sources=result.sources,
        confidence=result.confidence,
        gaps=result.gaps,
        iteration=result.iteration,
    )

    cost = estimate_cost(
        AgentTask.SUMMARIZATION,
        len(user_text) // 4,
        len(raw) // 4,
    )
    return summarized, cost


@traceable(name="summarization_agent")
async def run_summarization(state: AgentState) -> dict:
    """Compress each research result to max 2000 tokens, preserving citations."""
    logger.info("Summarization agent started")
    model = get_model(AgentTask.SUMMARIZATION)
    results = state.get("research_results", [])

    if not results:
        logger.warning("No research results to summarize")
        return {"current_agent": "summarization"}

    tasks = [_summarize_one(r, model) for r in results]
    summarized_pairs = await asyncio.gather(*tasks)

    summarized_results: list[ResearchResult] = []
    total_cost = 0.0
    for result, cost in summarized_pairs:
        summarized_results.append(result)
        total_cost += cost

    combined_summary = "\n\n".join(
        f"## {r.query}\n" + "\n".join(f"- {f}" for f in r.findings)
        for r in summarized_results
    )

    logger.info(
        f"Summarization complete: {len(summarized_results)} results compressed, "
        f"{sum(len(r.sources) for r in summarized_results)} citations preserved"
    )

    return {
        "research_results": summarized_results,
        "messages": state.get("messages", []) + [
            {"role": "summarization", "content": combined_summary}
        ],
        "cost_usd": state.get("cost_usd", 0.0) + total_cost,
        "current_agent": "summarization",
    }
