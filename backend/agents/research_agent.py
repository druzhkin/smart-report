import asyncio
import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import estimate_cost_for_model
from backend.pipeline.state import AgentState
from backend.schemas.research_result import ResearchResult, Source
from backend.utils.retry import llm_retry

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"

MAX_QUERIES_DEV = 3

SYSTEM_PROMPT = (
    "You are a senior research analyst. Conduct thorough research on the given query. "
    "Provide detailed, factual findings with proper sourcing."
)


@dataclass(frozen=True)
class ResearchModelConfig:
    direct_model: str
    routed_model: str


RESEARCH_MODEL_BY_DEPTH: dict[str, ResearchModelConfig] = {
    "light": ResearchModelConfig("sonar", "perplexity/sonar"),
    "standard": ResearchModelConfig("sonar", "perplexity/sonar"),
    "deep": ResearchModelConfig("sonar-pro", "perplexity/sonar-pro"),
    "exhaustive": ResearchModelConfig("sonar-deep-research", "perplexity/sonar-deep-research"),
}

DEV_RESEARCH_MODEL = ResearchModelConfig("sonar", "perplexity/sonar")


def _get_research_model_config(depth: str | None) -> ResearchModelConfig:
    if settings.dev_mode:
        return DEV_RESEARCH_MODEL
    return RESEARCH_MODEL_BY_DEPTH.get(depth or "standard", RESEARCH_MODEL_BY_DEPTH["standard"])


@llm_retry()
async def _call_perplexity(query: str, depth: str | None = None) -> dict:
    """Call Perplexity with a model matched to the requested research depth.

    Primary: direct Perplexity API (returns citations).
    Fallback: OpenRouter (when direct key missing/invalid).
    """
    model_config = _get_research_model_config(depth)

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
                        "model": model_config.direct_model,
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
    logger.info(f"Using OpenRouter research model: {model_config.routed_model}")
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": model_config.routed_model,
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
    seen_urls: set[str] = set()
    citations = raw_response.get("citations", [])

    message = ((raw_response.get("choices") or [{}])[0].get("message") or {})
    if isinstance(message, dict):
        for key in ("citations", "annotations", "references"):
            value = message.get(key)
            if isinstance(value, list):
                citations.extend(value)

    top_level_refs = raw_response.get("references")
    if isinstance(top_level_refs, list):
        citations.extend(top_level_refs)

    for cite in citations:
        if isinstance(cite, str):
            url = cite
            domain = urlparse(url).netloc if url else ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append(Source(
                url=url,
                title=domain,
                snippet="",
                domain=domain,
            ))
        elif isinstance(cite, dict):
            url = (
                cite.get("url")
                or cite.get("uri")
                or cite.get("source")
                or cite.get("link")
                or ""
            )
            domain = cite.get("domain", "")
            if not domain and url:
                domain = urlparse(url).netloc
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append(Source(
                url=url,
                title=cite.get("title", cite.get("name", domain)),
                snippet=cite.get("snippet", cite.get("text", cite.get("quote", ""))),
                domain=domain,
            ))

    content = message.get("content", "") if isinstance(message, dict) else ""
    if isinstance(content, str):
        for url in re.findall(r"https?://[^\s)\]>\"']+", content):
            normalized = url.rstrip(".,;:")
            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            sources.append(Source(
                url=normalized,
                title=urlparse(normalized).netloc,
                snippet="Extracted from generated content",
                domain=urlparse(normalized).netloc,
            ))

    return sources


def _extract_findings(content: str) -> list[str]:
    """Split LLM content into individual finding paragraphs."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        return [content]
    return paragraphs


async def _research_single(query: str, iteration: int, depth: str | None) -> tuple[ResearchResult, float]:
    """Run a single research query against Perplexity."""
    model_config = _get_research_model_config(depth)
    raw = await _call_perplexity(query, depth=depth)

    content = raw["choices"][0]["message"]["content"]
    sources = _parse_citations(raw)
    findings = _extract_findings(content)

    usage = raw.get("usage", {})
    in_tokens = usage.get("prompt_tokens", len(query) // 4)
    out_tokens = usage.get("completion_tokens", len(content) // 4)
    cost = estimate_cost_for_model(model_config.routed_model, in_tokens, out_tokens)

    result = ResearchResult(
        query=query,
        findings=findings,
        sources=sources,
        confidence=min(0.9, 0.35 + len(sources) * 0.1),
        gaps=[] if sources else ["No citations were returned by the research provider"],
        iteration=iteration,
    )
    return result, cost


@traceable(name="research_agent")
async def run_research(state: AgentState) -> dict:
    """Run research queries from supervisor batches via Perplexity models matched to depth."""
    logger.info("Research agent started")

    batches = state.get("parallel_batches")
    iteration = state.get("iteration", 1)
    intake = state.get("intake_result")
    depth = getattr(intake, "depth", None) if intake else None
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
        parallel_tasks = [_research_single(q, iteration, depth) for q, m in batch_queries if m == "parallel"]
        sequential_qs = [q for q, m in batch_queries if m != "parallel"]
        if parallel_tasks:
            for result, cost in await asyncio.gather(*parallel_tasks):
                all_results.append(result)
                total_cost += cost
        for q in sequential_qs:
            result, cost = await _research_single(q, iteration, depth)
            all_results.append(result)
            total_cost += cost
    else:
        # Fall back: use data_queries, then master prompt, then original request.
        queries = state.get("data_queries", [])
        if not queries:
            master = state.get("master_prompt")
            queries = [master.user_prompt if master else state["user_request"].get("query", "")]

        tasks = [_research_single(q, iteration, depth) for q in queries]
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
