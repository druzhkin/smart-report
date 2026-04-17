"""gpt-researcher search backend — cheap mode.

Our scout already extracts facts from raw text, so we skip gpt-researcher's
`write_report()` step (which is ~60% of its cost) and feed the accumulated
research context straight to the scout.

Cost levers applied (all via env vars read at GPTResearcher instantiation):
  MAX_ITERATIONS=1                 — one sub-query pass, not three
  MAX_SUBTOPICS=1                  — no topic branching
  MAX_SEARCH_RESULTS_PER_QUERY=3   — fewer URLs scraped per sub-query
  CURATE_SOURCES=False             — skip extra LLM curation pass
  SIMILARITY_THRESHOLD=0.5         — tighter source filtering
  RETRIEVER=duckduckgo             — free retriever, no API key
  FAST/SMART/STRATEGIC_LLM         — all pinned to gemini-2.5-flash

Accessors used instead of write_report():
  researcher.conduct_research()    — scrapes + builds context
  researcher.get_research_context() — accumulated RAG text
  researcher.get_research_sources() — list of {url,title,content} dicts

Cost accounting: researcher.get_costs() → USD, converted to ₽ via
settings.usd_to_credits, recorded under provider 'gpt_researcher'.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from config import settings
from llm import account_provider

log = logging.getLogger("search_gptr")

# LLM spec sent to gpt-researcher (provider:model format it expects)
_GPTR_MODEL = "openrouter:google/gemini-2.5-flash"
# Preferred free retriever; fallback to tavily when key is present
_PREFERRED_RETRIEVER = "duckduckgo"


def _prepare_env() -> None:
    """Inject gpt-researcher env vars before each call (safe to call repeatedly)."""
    key = settings.openrouter_api_key
    os.environ["OPENROUTER_API_KEY"] = key
    # gptr also probes OPENAI_API_KEY for some internal paths
    os.environ["OPENAI_API_KEY"] = key
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    os.environ["FAST_LLM"] = _GPTR_MODEL
    os.environ["SMART_LLM"] = _GPTR_MODEL
    os.environ["STRATEGIC_LLM"] = _GPTR_MODEL
    os.environ["RETRIEVER"] = _choose_retriever()
    # Cheap mode: minimise LLM fan-out inside gpt-researcher. Our scout does
    # extraction itself, so gpt-researcher only needs to gather raw evidence.
    os.environ["MAX_ITERATIONS"] = "1"
    os.environ["MAX_SUBTOPICS"] = "1"
    os.environ["MAX_SEARCH_RESULTS_PER_QUERY"] = "3"
    os.environ["CURATE_SOURCES"] = "False"
    os.environ["SIMILARITY_THRESHOLD"] = "0.5"
    if settings.tavily_api_key:
        os.environ["TAVILY_API_KEY"] = settings.tavily_api_key


def _choose_retriever() -> str:
    """Return the retriever name; prefer duckduckgo (free), fall back to tavily.

    gpt-researcher's duckduckgo retriever requires the `ddgs` package (not
    `duckduckgo-search`).  We probe for it by name; pip install ddgs if missing.
    """
    try:
        import ddgs  # noqa: F401 — availability check only
        return _PREFERRED_RETRIEVER
    except ImportError:
        pass
    if settings.tavily_api_key:
        log.warning("search_gptr: ddgs package not available, falling back to tavily")
        return "tavily"
    log.warning("search_gptr: no retriever available; defaulting to duckduckgo and hoping for the best")
    return _PREFERRED_RETRIEVER


def _extract_citations(sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Normalise gpt-researcher source dicts to {url, title}."""
    seen: set[str] = set()
    citations: list[dict[str, str]] = []
    for src in sources:
        url = src.get("url", "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        citations.append({"url": url, "title": src.get("title", url)})
    return citations


def _count_citation_refs(text: str) -> int:
    """Count [n]-style inline citations in the report text."""
    return len(re.findall(r"\[\d+\]", text))


async def gpt_researcher_search(query: str) -> dict[str, Any]:
    """Run gpt-researcher for one query.

    Returns the same shape as our other search backends:
    {
        "text":          str   — synthesized research text with inline [n] citations,
        "citations":     list[{"url": str, "title": str}],
        "query":         str,
        "source_db":     "gpt_researcher",
        "academic_items": [],  — always empty; gpt-researcher is web-only,
        "fallback":      "gpt_researcher",
    }
    On failure returns a stub dict with fallback="gpt_researcher_failed".
    """
    _prepare_env()

    try:
        from gpt_researcher import GPTResearcher  # late import so env is set first

        # outline_report is the lightest report_type; we skip write_report anyway
        # but the config needs a valid type during instantiation.
        researcher = GPTResearcher(
            query=query,
            report_type="outline_report",
            verbose=False,
        )
        await researcher.conduct_research()

        sources: list[dict[str, Any]] = researcher.get_research_sources()
        context: str = researcher.get_research_context() or ""
        citations = _extract_citations(sources)

        # Compose raw evidence corpus from scraped sources — the scout LLM will
        # extract numeric facts downstream. Skipping write_report() saves ~60%
        # of gpt-researcher's LLM spend.
        corpus_parts = [context] if context else []
        for i, s in enumerate(sources, 1):
            body = (s.get("raw_content") or s.get("content") or s.get("body") or "").strip()
            if not body:
                continue
            url = s.get("url", "")
            title = s.get("title") or url
            corpus_parts.append(f"[{i}] {title} — {url}\n{body[:2000]}")
        corpus = "\n\n---\n\n".join(corpus_parts)[:30000]

        cost_usd: float = researcher.get_costs() or 0.0
        cost_rub = cost_usd * settings.usd_to_credits
        account_provider("gpt_researcher", cost_rub, calls=1)

        log.info(
            "search_gptr: query=%r corpus_len=%d cites=%d cost_usd=%.4f cost_rub=%.2f",
            query[:60],
            len(corpus),
            len(citations),
            cost_usd,
            cost_rub,
        )

        return {
            "text": corpus,
            "citations": citations,
            "query": query,
            "source_db": "gpt_researcher",
            "academic_items": [],
            "fallback": "gpt_researcher",
        }

    except Exception as exc:
        log.error("search_gptr: failed for query=%r: %s", query[:60], exc, exc_info=True)
        return {
            "text": f"[gpt_researcher failed: {exc}]",
            "citations": [],
            "query": query,
            "academic_items": [],
            "fallback": "gpt_researcher_failed",
        }
