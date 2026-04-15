"""Perplexity wrapper with mock fallback."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from config import settings

PPLX_URL = "https://api.perplexity.ai/chat/completions"


async def search(query: str, focus: str = "general") -> dict[str, Any]:
    """Run one search query. Returns {text, citations}."""
    if settings.use_mock_search or not settings.perplexity_api_key:
        return _mock(query, focus)
    payload = {
        "model": settings.perplexity_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a research assistant. Answer the user's query with concrete facts, "
                    "numbers and named sources. Prefer primary sources (official statistics, "
                    "regulators, peer-reviewed, company filings). Keep it dense, no fluff."
                ),
            },
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.perplexity_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=90) as http:
        for attempt in range(3):
            try:
                r = await http.post(PPLX_URL, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                citations = data.get("citations") or data.get("search_results") or []
                return {"text": text, "citations": citations, "query": query}
            except (httpx.HTTPError, KeyError) as err:
                if attempt == 2:
                    return {
                        "text": f"[search error: {err}]",
                        "citations": [],
                        "query": query,
                    }
                await asyncio.sleep(1.5 * (attempt + 1))
    return {"text": "", "citations": [], "query": query}


def _mock(query: str, focus: str) -> dict[str, Any]:
    return {
        "query": query,
        "text": (
            f"[MOCK SEARCH]\nQuery: {query}\nFocus: {focus}\n"
            "No real data fetched — USE_MOCK_SEARCH=1 or PERPLEXITY_API_KEY missing.\n"
            "Finding 1: placeholder primary-source claim with a number (e.g. 12.3%) [example.gov, 2024].\n"
            "Finding 2: placeholder secondary comment [example.org/article, 2025]."
        ),
        "citations": [
            {"url": "https://example.gov/stat", "title": "Mock primary source"},
            {"url": "https://example.org/article", "title": "Mock secondary"},
        ],
    }
