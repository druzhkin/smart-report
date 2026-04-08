import asyncio
import json
import re
from hashlib import md5
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.knowledge_library.retriever import retriever
from backend.pipeline.model_router import estimate_cost_for_model
from backend.pipeline.state import AgentState
from backend.schemas.research_result import EvidenceItem, ResearchBranchState, ResearchResult, Source
from backend.utils.retry import llm_retry

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"

MAX_QUERIES_DEV = 3
MAX_FINDINGS_PER_QUERY = 8
MAX_QUERY_CHARS = 260

LOW_AUTHORITY_DOMAINS = {
    "dev.to",
    "youtube.com",
    "www.youtube.com",
    "leetcode.com",
    "reddit.com",
    "www.reddit.com",
    "medium.com",
    "www.medium.com",
    "t.me",
    "telegram.me",
    "dzen.ru",
    "zen.yandex.ru",
}

SYSTEM_PROMPT = (
    "You are a senior research analyst. Conduct thorough research on the given query. "
    "Provide detailed, factual findings with proper sourcing. "
    "Return plain-text analytical findings, not markdown tables, not bullet pyramids, and not generic filler."
)


def _compact_text(text: str, max_len: int = MAX_QUERY_CHARS) -> str:
    compact = " ".join((text or "").split()).strip()
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip() + "…"


def _normalize_url(url: str) -> str:
    normalized = (url or "").strip().rstrip(".,;:")
    if not normalized.startswith("http://") and not normalized.startswith("https://"):
        return ""
    return normalized


def _is_usable_source_url(url: str) -> bool:
    normalized = _normalize_url(url)
    if not normalized:
        return False
    try:
        domain = urlparse(normalized).netloc.lower().strip()
    except Exception:
        return False
    if not domain or domain in LOW_AUTHORITY_DOMAINS:
        return False
    if domain.startswith("localhost") or domain.startswith("127."):
        return False
    return True


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
    return RESEARCH_MODEL_BY_DEPTH.get(depth or "standard", RESEARCH_MODEL_BY_DEPTH["standard"])


@llm_retry()
async def _call_perplexity(query: str, depth: str | None = None) -> dict:
    """Call Perplexity with a model matched to the requested research depth.

    Primary: direct Perplexity API (returns citations).
    Fallback: OpenRouter (when direct key missing/invalid).
    """
    model_config = _get_research_model_config(depth)

    # Prefer direct Perplexity whenever a key is available because it yields better
    # citation fidelity than routed fallbacks. Dev mode still caps query volume later.
    if settings.perplexity_api_key:
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
                payload = resp.json()
                payload["_research_provider"] = "perplexity"
                payload["_research_model"] = model_config.direct_model
                payload["_research_pricing_basis"] = "provider_usage"
                return payload
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
        payload = resp.json()
        payload["_research_provider"] = "openrouter"
        payload["_research_model"] = payload.get("model", model_config.routed_model)
        payload["_research_pricing_basis"] = "estimated_chars"
        return payload


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
            url = _normalize_url(cite)
            domain = urlparse(url).netloc if url else ""
            if not url or url in seen_urls:
                continue
            if not _is_usable_source_url(url):
                continue
            seen_urls.add(url)
            sources.append(Source(
                url=url,
                title=domain,
                snippet="",
                domain=domain,
            ))
        elif isinstance(cite, dict):
            citation_payload = cite
            nested_citation = cite.get("url_citation")
            if isinstance(nested_citation, dict):
                citation_payload = nested_citation
            url_raw = (
                citation_payload.get("url")
                or citation_payload.get("uri")
                or citation_payload.get("source")
                or citation_payload.get("link")
                or ""
            )
            url = _normalize_url(url_raw)
            domain = citation_payload.get("domain", "") or cite.get("domain", "")
            if not domain and url:
                domain = urlparse(url).netloc
            if not url or url in seen_urls:
                continue
            if not _is_usable_source_url(url):
                continue
            seen_urls.add(url)
            sources.append(Source(
                url=url,
                title=citation_payload.get("title", citation_payload.get("name", cite.get("title", domain))),
                snippet=citation_payload.get("snippet", citation_payload.get("text", citation_payload.get("quote", ""))),
                domain=domain,
            ))

    content = message.get("content", "") if isinstance(message, dict) else ""
    if isinstance(content, str):
        for url in re.findall(r"https?://[^\s)\]>\"']+", content):
            normalized = _normalize_url(url)
            if normalized in seen_urls:
                continue
            if not _is_usable_source_url(normalized):
                continue
            seen_urls.add(normalized)
            sources.append(Source(
                url=normalized,
                title=urlparse(normalized).netloc,
                snippet="Extracted from generated content",
                domain=urlparse(normalized).netloc,
            ))

    return sources[:12]


def _extract_findings(content: str) -> list[str]:
    """Split LLM content into individual finding paragraphs."""
    raw_paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    paragraphs: list[str] = []
    for paragraph in raw_paragraphs:
        normalized = " ".join(paragraph.split()).strip()
        if len(normalized) < 8:
            continue
        if any(
            marker in normalized.lower()
            for marker in (
                "i appreciate the detailed query",
                "what the search results cover",
                "limitations of the provided search results",
            )
        ):
            continue
        paragraphs.append(normalized[:700])
        if len(paragraphs) >= MAX_FINDINGS_PER_QUERY:
            break
    if not paragraphs:
        fallback = _compact_text(content, max_len=400)
        return [fallback] if fallback else []
    return paragraphs


def _build_research_prompt(
    query: str,
    retrieved_context: list[dict],
    branch_state: ResearchBranchState | None = None,
) -> str:
    sections = [query]
    sections.append(
        "Output format: return 5-8 short evidence findings as separate paragraphs. "
        "Each paragraph should contain one substantive claim with named entities, no markdown tables, no headings, and no bare numeric footnotes like [1]."
    )
    sections.append(
        "Source policy: strongly prefer official docs, official GitHub repos, benchmark pages, and serious technical papers. "
        "Avoid listicles, trend roundups, generic blogs, community posts, and 'top/best/guide' pages unless no stronger source exists."
    )

    if branch_state:
        action = branch_state.next_action or "deepen"
        if action == "widen":
            sections.append(
                "Research strategy: widen coverage. Prioritize additional independent sources, new domains, and alternative viewpoints."
            )
        elif action == "verify":
            sections.append(
                "Research strategy: verify contradiction or unresolved gaps. Reconcile conflicting claims and prefer authoritative sources."
            )
        elif action == "deepen":
            sections.append(
                "Research strategy: deepen analysis. Look for richer evidence, more specific metrics, and stronger causal support."
            )
        if branch_state.action_reason:
            sections.append(f"Why this branch is being revisited: {branch_state.action_reason}")
        if branch_state.contradiction_notes:
            sections.append(
                "Contradiction notes:\n" + "\n".join(f"- {note}" for note in branch_state.contradiction_notes[:4])
            )
        if branch_state.follow_up_queries:
            sections.append(
                "Follow-up checks:\n" + "\n".join(f"- {item}" for item in branch_state.follow_up_queries[:4])
            )
        if branch_state.source_strategy == "ragflow":
            sections.append("Source preference: prioritize internal memory and RagFlow evidence before expanding outward.")
        elif branch_state.source_strategy == "hybrid":
            sections.append("Source preference: combine internal memory with fresh web verification.")

    if not retrieved_context:
        return "\n\n".join(sections)

    context_lines = [
        f"- [{item.get('source', 'memory')}] {item.get('content', '')}"
        for item in retrieved_context[:5]
        if item.get("content")
    ]
    if context_lines:
        sections.append(
            "Use this retrieved context as supporting memory, but verify live claims independently when possible:\n"
            + "\n".join(context_lines)
        )
    return "\n\n".join(sections)


def _build_evidence_items(query: str, findings: list[str], sources: list[Source]) -> list[EvidenceItem]:
    evidence_items: list[EvidenceItem] = []
    for idx, finding in enumerate(findings, start=1):
        source = sources[(idx - 1) % len(sources)] if sources else None
        evidence_id = md5(f"{query}:{idx}:{finding}".encode("utf-8")).hexdigest()[:16]
        evidence_items.append(
            EvidenceItem(
                id=f"ev_{evidence_id}",
                query_id=md5(query.encode("utf-8")).hexdigest()[:12],
                claim=finding,
                source_url=source.url if source else "",
                source_title=source.title if source else "",
                snippet=source.snippet if source else finding[:240],
                domain=source.domain if source else "",
                confidence=min(0.95, 0.45 + len(sources) * 0.1),
                tags=[],
            )
        )
    return evidence_items


async def _research_single(
    query: str,
    iteration: int,
    depth: str | None,
    retrieved_context: list[dict] | None = None,
    branch_state: ResearchBranchState | None = None,
 ) -> tuple[ResearchResult, float, list[EvidenceItem], dict]:
    """Run a single research query against Perplexity."""
    model_config = _get_research_model_config(depth)
    query_safe = _compact_text(query, max_len=MAX_QUERY_CHARS)
    research_prompt = _build_research_prompt(query_safe, retrieved_context or [], branch_state=branch_state)
    raw = await _call_perplexity(research_prompt, depth=depth)

    content = raw["choices"][0]["message"]["content"]
    sources = _parse_citations(raw)
    findings = _extract_findings(content)

    usage = raw.get("usage", {})
    in_tokens = usage.get("prompt_tokens", len(query) // 4)
    out_tokens = usage.get("completion_tokens", len(content) // 4)
    direct_cost = (((usage.get("cost") or {}) if isinstance(usage, dict) else {}) or {}).get("total_cost")
    resolved_model = str(raw.get("_research_model") or model_config.routed_model)
    provider = str(raw.get("_research_provider") or "perplexity")
    pricing_basis = str(raw.get("_research_pricing_basis") or "estimated_chars")
    cost = float(direct_cost) if direct_cost is not None else estimate_cost_for_model(resolved_model, in_tokens, out_tokens)

    result = ResearchResult(
        query=query_safe,
        findings=findings,
        sources=sources,
        confidence=min(0.9, 0.35 + len(sources) * 0.1),
        gaps=[] if sources else ["No citations were returned by the research provider"],
        iteration=iteration,
    )
    return result, cost, _build_evidence_items(query, findings, sources), {
        "provider": provider,
        "model": resolved_model,
        "pricing_basis": pricing_basis,
        "input_tokens": int(in_tokens or 0),
        "output_tokens": int(out_tokens or 0),
    }


@traceable(name="research_agent")
async def run_research(state: AgentState) -> dict:
    """Run research queries from supervisor batches via Perplexity models matched to depth."""
    logger.info("Research agent started")

    batches = state.get("parallel_batches")
    iteration = state.get("iteration", 1)
    intake = state.get("intake_result")
    depth = getattr(intake, "depth", None) if intake else None
    all_results: list[ResearchResult] = []
    evidence_items = list(state.get("evidence_items", []) or [])
    branch_states = {
        branch.question: branch
        for branch in list(state.get("branch_states", []) or [])
    }
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

    retrieval_cache: dict[str, list[dict]] = {}
    if batch_queries:
        unique_queries = list(dict.fromkeys(query for query, _mode in batch_queries))
    else:
        unique_queries = list(state.get("data_queries", []))
    if not unique_queries:
        unique_queries = [state.get("user_request", {}).get("query", "")]

    retrieved_lists = await asyncio.gather(
        *[
            retriever.retrieve(query, use_ragflow=bool(settings.ragflow_api_key), top_k=5)
            for query in unique_queries
        ]
    )
    retrieval_cache = dict(zip(unique_queries, retrieved_lists))

    if batch_queries:
        parallel_tasks = [
            _research_single(q, iteration, depth, retrieval_cache.get(q, []), branch_states.get(q))
            for q, m in batch_queries
            if m == "parallel"
        ]
        sequential_qs = [q for q, m in batch_queries if m != "parallel"]
        if parallel_tasks:
            for result, cost, evidence, _meta in await asyncio.gather(*parallel_tasks):
                all_results.append(result)
                total_cost += cost
                evidence_items.extend(evidence)
        for q in sequential_qs:
            result, cost, evidence, _meta = await _research_single(
                q, iteration, depth, retrieval_cache.get(q, []), branch_states.get(q)
            )
            all_results.append(result)
            total_cost += cost
            evidence_items.extend(evidence)
    else:
        # Fall back: use data_queries, then master prompt, then original request.
        queries = state.get("data_queries", [])
        if not queries:
            master = state.get("master_prompt")
            queries = [master.user_prompt if master else state["user_request"].get("query", "")]

        tasks = [
            _research_single(q, iteration, depth, retrieval_cache.get(q, []), branch_states.get(q))
            for q in queries
        ]
        for result, cost, evidence, _meta in await asyncio.gather(*tasks):
            all_results.append(result)
            total_cost += cost
            evidence_items.extend(evidence)

    logger.info(
        f"Research completed: {len(all_results)} results, "
        f"{sum(len(r.sources) for r in all_results)} total sources"
    )

    for result in all_results:
        previous = branch_states.get(result.query)
        branch_states[result.query] = ResearchBranchState(
            task_id=previous.task_id if previous else f"branch-{md5(result.query.encode('utf-8')).hexdigest()[:8]}",
            question=result.query,
            status="needs_follow_up" if len(result.sources) < 2 or result.gaps else "completed",
            next_action="widen" if len(result.sources) < 2 else ("verify" if result.gaps else "complete"),
            action_reason=(
                "Need more independent sources for this branch."
                if len(result.sources) < 2
                else ("Research still has unresolved gaps." if result.gaps else "Branch has enough support for this cycle.")
            ),
            contradiction_notes=previous.contradiction_notes if previous else [],
            evidence_count=sum(1 for item in evidence_items if result.query.lower() in item.claim.lower()),
            source_count=len(result.sources),
            source_domains=sorted({source.domain for source in result.sources if source.domain}),
            confidence=result.confidence,
            gaps=result.gaps,
            follow_up_queries=(previous.follow_up_queries if previous else []),
            source_strategy=previous.source_strategy if previous else "hybrid",
            last_iteration=iteration,
        )

    return {
        "research_results": state.get("research_results", []) + all_results,
        "branch_states": list(branch_states.values()),
        "evidence_items": evidence_items,
        "cost_usd": state.get("cost_usd", 0.0) + total_cost,
        "current_agent": "research",
    }
