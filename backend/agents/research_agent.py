import asyncio
import json
from urllib.parse import urlparse

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, estimate_cost
from backend.pipeline.state import AgentState
from backend.schemas.research_result import ResearchResult, Source
from backend.utils.retry import llm_retry

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar-deep-research"
PERPLEXITY_OR_MODEL = "perplexity/sonar-deep-research"
PERPLEXITY_OR_MODEL_DEV = "perplexity/sonar"

MAX_QUERIES_DEV = 3

SYSTEM_PROMPT = (
    "You are a senior research analyst. Conduct thorough research on the given query. "
    "Provide detailed, factual findings with proper sourcing."
)


@llm_retry()
async def _call_perplexity(query: str) -> dict:
    """Call Perplexity sonar-deep-research.

    Primary: direct Perplexity API (returns citations).
    Fallback: OpenRouter (when direct key missing/invalid).
    """
    or_model = PERPLEXITY_OR_MODEL_DEV if settings.dev_mode else PERPLEXITY_OR_MODEL

    # Use direct Perplexity API if key is configured, not empty, and not dev_mode
    if settings.perplexity_api_key and not settings.dev_mode:
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    PERPLEXITY_URL,
                    headers={
                        "Authorization": f"Bearer {settings.perplexity_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": PERPLEXITY_MODEL,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": query},
                        ],
                        "temperature": 0.2,
                        "return_citations": True,
                        "return_related_questions": False,
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.warning(f"Perplexity direct API auth failed ({e.response.status_code}), falling back to OpenRouter")
            else:
                raise

    # OpenRouter fallback (always used in dev_mode)
    logger.info(f"Using OpenRouter: {or_model}")
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": or_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        return resp.json()


def _parse_citations(raw_response: dict) -> list[Source]:
    """Extract citations from Perplexity response into Source objects."""
    sources: list[Source] = []
    citations = raw_response.get("citations", [])

    for cite in citations:
        if isinstance(cite, str):
            url = cite
            domain = urlparse(url).netloc if url else ""
            sources.append(Source(
                url=url,
                title=domain,
                snippet="",
                domain=domain,
            ))
        elif isinstance(cite, dict):
            url = cite.get("url", "")
            domain = cite.get("domain", "")
            if not domain and url:
                domain = urlparse(url).netloc
            sources.append(Source(
                url=url,
                title=cite.get("title", ""),
                snippet=cite.get("snippet", cite.get("text", "")),
                domain=domain,
            ))

    return sources


def _extract_findings(content: str) -> list[str]:
    """Split LLM content into individual finding paragraphs."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        return [content]
    return paragraphs


async def _research_single(query: str, iteration: int) -> tuple[ResearchResult, float]:
    """Run a single research query against Perplexity."""
    raw = await _call_perplexity(query)

    content = raw["choices"][0]["message"]["content"]
    sources = _parse_citations(raw)
    findings = _extract_findings(content)

    usage = raw.get("usage", {})
    in_tokens = usage.get("prompt_tokens", len(query) // 4)
    out_tokens = usage.get("completion_tokens", len(content) // 4)
    cost = estimate_cost(AgentTask.RESEARCH_DEEP, in_tokens, out_tokens)

    result = ResearchResult(
        query=query,
        findings=findings,
        sources=sources,
        confidence=min(0.9, 0.5 + len(sources) * 0.05),
        gaps=[],
        iteration=iteration,
    )
    return result, cost


@traceable(name="research_agent")
async def run_research(state: AgentState) -> dict:
    """Run research queries from supervisor batches via Perplexity sonar-deep-research."""
    logger.info("Research agent started")

    batches = state.get("parallel_batches")
    iteration = state.get("iteration", 1)
    all_results: list[ResearchResult] = []
    total_cost = 0.0

    # Collect all non-empty queries from batches.
    batch_queries: list[tuple[str, str]] = []  # (query, mode)
    if batches and batches.batches:
        for batch in batches.batches:
            for q in batch.queries:
                batch_queries.append((q, batch.mode))

    if settings.dev_mode and batch_queries:
        batch_queries = batch_queries[:MAX_QUERIES_DEV]
        logger.info(f"[DEV] Capped research queries to {MAX_QUERIES_DEV}")

    if batch_queries:
        parallel_tasks = [_research_single(q, iteration) for q, m in batch_queries if m == "parallel"]
        sequential_qs = [q for q, m in batch_queries if m != "parallel"]
        if parallel_tasks:
            for result, cost in await asyncio.gather(*parallel_tasks):
                all_results.append(result)
                total_cost += cost
        for q in sequential_qs:
            result, cost = await _research_single(q, iteration)
            all_results.append(result)
            total_cost += cost
    else:
        # Fall back: use data_queries, then master prompt, then original request.
        queries = state.get("data_queries", [])
        if not queries:
            master = state.get("master_prompt")
            queries = [master.user_prompt if master else state["user_request"].get("query", "")]

        tasks = [_research_single(q, iteration) for q in queries]
        for result, cost in await asyncio.gather(*tasks):
            all_results.append(result)
            total_cost += cost

    logger.info(
        f"Research completed: {len(all_results)} results, "
        f"{sum(len(r.sources) for r in all_results)} total sources"
    )

    return {
        "research_results": state.get("research_results", []) + all_results,
        "cost_usd": state.get("cost_usd", 0.0) + total_cost,
        "current_agent": "research",
    }
