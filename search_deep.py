"""Deep-research backends: Tavily Research, Parallel.ai, Valyu DeepResearch.

All three expose a multi-agent research task: submit a query, poll for a report
with citations. We wrap them under one async contract so `search.py` can fan
them out alongside Perplexity / gpt-researcher.

Return contract (same as every other backend in search.py):
    {
        "text":          str  — synthesized report with inline or bullet citations,
        "citations":     list[{"url": str, "title": str}],
        "query":         str,
        "source_db":     str  (e.g. "tavily_deep", "parallel", "valyu"),
        "fallback":      str  (same label; used for bench attribution),
        "academic_items": [] — these vendors are web-only.
    }

Each entry point returns ``None`` when the key is missing, the SDK isn't
installed, or the task failed — the orchestrator treats that as "backend not
available, move on".
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import settings
from llm import account_provider

log = logging.getLogger("search_deep")


# ---------- helpers ------------------------------------------------------

def _citations_from_sources(sources: list[Any]) -> list[dict[str, str]]:
    """Normalise vendor source objects (dict or attrs) to {url, title}."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in sources or []:
        url = _attr(s, "url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "title": _attr(s, "title") or url})
    return out


def _attr(obj: Any, key: str) -> Any:
    """Read a field from either a dict or an object with attributes."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _compose_corpus(content: str, sources: list[Any], cap: int = 30000) -> str:
    """Mirror search_gptr's pattern: header with synth + per-source bodies for the scout."""
    parts: list[str] = []
    if content:
        parts.append(content.strip())
    for i, s in enumerate(sources or [], 1):
        body = (_attr(s, "raw_content") or _attr(s, "content") or _attr(s, "snippet") or "")
        if not body:
            continue
        url = _attr(s, "url") or ""
        title = _attr(s, "title") or url
        parts.append(f"[{i}] {title} — {url}\n{str(body)[:2000]}")
    return "\n\n---\n\n".join(parts)[:cap]


# ---------- Tavily Research API ------------------------------------------

async def tavily_deep_research(query: str) -> dict[str, Any] | None:
    """Call Tavily Deep Research (client.research / get_research).

    Tiers via TAVILY_DEEP_MODEL: mini (cheapest), auto, pro. We run with
    stream=False and poll status in a background thread so the SDK's sync
    calls don't block the event loop.
    """
    if not settings.tavily_api_key:
        return None
    try:
        from tavily import TavilyClient  # lazy: optional dep
    except ImportError:
        log.warning("tavily_deep: tavily SDK missing; `pip install tavily-python`")
        return None

    model = settings.tavily_deep_model or "mini"

    def _run() -> dict[str, Any] | None:
        client = TavilyClient(api_key=settings.tavily_api_key)
        task = client.research(input=query, model=model)
        req_id = task.get("request_id") if isinstance(task, dict) else getattr(task, "request_id", None)
        if not req_id:
            return None
        deadline = 1800  # 30 min safety cap; mini tier usually finishes in minutes
        waited = 0
        while waited < deadline:
            result = client.get_research(req_id)
            status = _attr(result, "status")
            if status == "completed":
                return result if isinstance(result, dict) else {"status": status, "content": _attr(result, "content"), "sources": _attr(result, "sources")}
            if status == "failed":
                return None
            import time as _t
            _t.sleep(5)
            waited += 5
        return None

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        log.warning("tavily_deep: call failed for %r: %s", query[:60], exc)
        return None
    if not result:
        return None

    content = str(_attr(result, "content") or "")
    sources = _attr(result, "sources") or []
    citations = _citations_from_sources(sources)
    corpus = _compose_corpus(content, sources)
    # Prefer actual credits_used from the response; fall back to tier midpoint.
    credits_used = _attr(result, "credits_used") or _attr(result, "credits") or None
    if isinstance(credits_used, (int, float)) and credits_used > 0:
        cost_usd = float(credits_used) * settings.tavily_usd_per_credit
    else:
        cost_usd = settings.tavily_deep_usd_per_query
    account_provider("tavily_deep", cost_usd * settings.usd_to_credits)
    log.info("tavily_deep: q=%r corpus=%d cites=%d model=%s cost=$%.3f credits=%s", query[:60], len(corpus), len(citations), model, cost_usd, credits_used)
    return {
        "text": corpus,
        "citations": citations,
        "query": query,
        "source_db": "tavily_deep",
        "fallback": "tavily_deep",
        "academic_items": [],
    }


# ---------- Parallel.ai Task API -----------------------------------------

async def parallel_research(query: str) -> dict[str, Any] | None:
    """Call Parallel.ai Task API (processor base|core|ultra).

    Polling is handled by SDK's task_run.result(run_id, api_timeout=...) which
    blocks — wrap in a thread.
    """
    if not settings.parallel_api_key:
        return None
    try:
        from parallel import Parallel  # lazy: `pip install parallel-web`
    except ImportError:
        log.warning("parallel: SDK missing; `pip install parallel-web`")
        return None

    processor = settings.parallel_processor or "core"

    def _run() -> Any:
        client = Parallel(api_key=settings.parallel_api_key)
        task_run = client.task_run.create(input=query, processor=processor)
        run_id = _attr(task_run, "run_id")
        if not run_id:
            return None
        return client.task_run.result(run_id, api_timeout=1800)

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        log.warning("parallel: call failed for %r: %s", query[:60], exc)
        return None
    if not result:
        return None

    content = str(_attr(result, "output") or "")
    sources = _attr(result, "sources") or _attr(result, "excerpts") or []
    citations = _citations_from_sources(sources)
    corpus = _compose_corpus(content, sources)
    if not corpus and not citations:
        return None
    # Parallel bills flat per processor tier — no usage metric to read back.
    cost_usd = settings.parallel_usd_per_query
    account_provider("parallel", cost_usd * settings.usd_to_credits)
    log.info("parallel: q=%r corpus=%d cites=%d processor=%s cost=$%.3f", query[:60], len(corpus), len(citations), processor, cost_usd)
    return {
        "text": corpus,
        "citations": citations,
        "query": query,
        "source_db": "parallel",
        "fallback": "parallel",
        "academic_items": [],
    }


# ---------- Valyu DeepResearch -------------------------------------------

async def valyu_research(query: str) -> dict[str, Any] | None:
    """Call Valyu DeepResearch (mode fast|standard|heavy|max).

    Valyu's key edge is proprietary databases (SEC/EDGAR, PubMed, arXiv,
    ClinicalTrials.gov, USPTO, ChEMBL, FRED). Useful when a query needs
    primary-source citations the open web can't surface.
    """
    if not settings.valyu_api_key:
        return None
    try:
        from valyu import Valyu  # lazy: `pip install valyu`
    except ImportError:
        log.warning("valyu: SDK missing; `pip install valyu`")
        return None

    mode = settings.valyu_mode or "standard"

    def _run() -> Any:
        # SDK reads VALYU_API_KEY from env automatically.
        import os as _os
        _os.environ["VALYU_API_KEY"] = settings.valyu_api_key
        client = Valyu()
        task = client.deepresearch.create(query=query, mode=mode)
        task_id = _attr(task, "deepresearch_id") or _attr(task, "id")
        if not task_id:
            return None
        return client.deepresearch.wait(task_id, poll_interval=5, max_wait_time=1800)

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        log.warning("valyu: call failed for %r: %s", query[:60], exc)
        return None
    if not result or _attr(result, "status") != "completed":
        return None

    content = str(_attr(result, "output") or "")
    sources = _attr(result, "sources") or []
    citations = _citations_from_sources(sources)
    corpus = _compose_corpus(content, sources)
    cost_usd_raw = _attr(result, "cost")
    try:
        cost_usd = float(cost_usd_raw) if cost_usd_raw is not None else settings.valyu_usd_per_query
    except (TypeError, ValueError):
        cost_usd = settings.valyu_usd_per_query
    account_provider("valyu", cost_usd * settings.usd_to_credits)
    log.info("valyu: q=%r corpus=%d cites=%d mode=%s cost=$%.2f", query[:60], len(corpus), len(citations), mode, cost_usd)
    return {
        "text": corpus,
        "citations": citations,
        "query": query,
        "source_db": "valyu",
        "fallback": "valyu",
        "academic_items": [],
    }
