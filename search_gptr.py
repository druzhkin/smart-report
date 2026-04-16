"""gpt-researcher search backend (bench-only, NOT wired into production pipeline).

Environment injection strategy
-------------------------------
gpt-researcher reads its configuration exclusively from environment variables at
instantiation time.  We set the required vars in os.environ right before each
call so they take effect without touching .env or any shared state that other
backends rely on:

  OPENAI_API_KEY      — forwarded from OPENROUTER_API_KEY (gptr uses this key name
                        when provider == "openrouter")
  OPENROUTER_API_KEY  — same key; gptr's openrouter provider reads this directly
  FAST_LLM            — "openrouter:google/gemini-2.5-flash"
  SMART_LLM           — "openrouter:google/gemini-2.5-flash"
  STRATEGIC_LLM       — "openrouter:google/gemini-2.5-flash"
  RETRIEVER           — "duckduckgo" (free, no API key needed)
                        Falls back to "tavily" if TAVILY_API_KEY is set and
                        duckduckgo is unavailable (see _ensure_retriever()).

Cost accounting
---------------
gpt-researcher accumulates cost via researcher.get_costs() → float USD.
We convert that to ₽ via settings.usd_to_credits and call account_provider().
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

        researcher = GPTResearcher(
            query=query,
            report_type="research_report",
            verbose=False,
        )
        await researcher.conduct_research()
        report: str = await researcher.write_report()

        sources: list[dict[str, Any]] = researcher.get_research_sources()
        citations = _extract_citations(sources)

        cost_usd: float = researcher.get_costs() or 0.0
        cost_rub = cost_usd * settings.usd_to_credits
        account_provider("gpt_researcher", cost_rub, calls=1)

        log.info(
            "search_gptr: query=%r text_len=%d cites=%d inline_refs=%d cost_usd=%.4f cost_rub=%.2f",
            query[:60],
            len(report),
            len(citations),
            _count_citation_refs(report),
            cost_usd,
            cost_rub,
        )

        return {
            "text": report,
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
