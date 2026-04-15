"""Perplexity primary search; Firecrawl fallback (live web + markdown + Claude synth).

Fallback chain: Firecrawl /v1/search (preferred) → DuckDuckGo HTML SERP (last resort).
Firecrawl returns already-scraped markdown so no second fetch round-trip is needed."""
from __future__ import annotations

import asyncio
import re
from html import unescape
from typing import Any
from urllib.parse import unquote

import httpx

from config import settings

PPLX_URL = "https://api.perplexity.ai/chat/completions"
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)


def _strip_html(html: str) -> str:
    html = _SCRIPT_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", unescape(text)).strip()


def _clean_ddg_url(href: str) -> str:
    m = re.search(r"uddg=([^&]+)", href)
    if m:
        return unquote(m.group(1))
    return href


async def _ddg_search(http: httpx.AsyncClient, query: str, k: int = 6) -> list[dict[str, str]]:
    r = await http.post(
        DDG_HTML_URL,
        data={"q": query, "kl": "ru-ru"},
        headers={"User-Agent": UA, "Accept": "text/html"},
    )
    r.raise_for_status()
    out: list[dict[str, str]] = []
    for m in _RESULT_RE.finditer(r.text):
        url = _clean_ddg_url(m.group(1))
        if not url.startswith("http"):
            continue
        title = _strip_html(m.group(2))
        snippet = _strip_html(m.group(3))
        out.append({"url": url, "title": title, "snippet": snippet})
        if len(out) >= k:
            break
    return out


async def _fetch_page(http: httpx.AsyncClient, url: str, max_chars: int = 6000) -> str:
    try:
        r = await http.get(url, headers={"User-Agent": UA}, follow_redirects=True, timeout=20)
        if r.status_code >= 400 or "text" not in r.headers.get("content-type", ""):
            return ""
        return _strip_html(r.text)[:max_chars]
    except Exception:
        return ""


async def _firecrawl_search(http: httpx.AsyncClient, query: str, k: int = 6) -> list[dict[str, str]]:
    """Firecrawl /v1/search: returns SERP with pre-scraped markdown (no second fetch needed)."""
    if not settings.firecrawl_api_key:
        return []
    try:
        r = await http.post(
            FIRECRAWL_SEARCH_URL,
            json={
                "query": query,
                "limit": k,
                "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
            },
            headers={
                "Authorization": f"Bearer {settings.firecrawl_api_key}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        out: list[dict[str, str]] = []
        for item in (data.get("data") or [])[:k]:
            url = item.get("url") or ""
            if not url.startswith("http"):
                continue
            md = item.get("markdown") or ""
            out.append({
                "url": url,
                "title": item.get("title") or url,
                "snippet": item.get("description") or "",
                "body": md[:6000],
            })
        return out
    except Exception:
        return []


async def _fallback(query: str) -> dict[str, Any]:
    """Live-web fallback: Firecrawl search+scrape → DDG SERP + fetch → Claude synth."""
    from llm import call_text

    try:
        async with httpx.AsyncClient(timeout=90) as http:
            fc = await _firecrawl_search(http, query, k=6)
            if fc:
                results = fc
                pages = [r.get("body", "") for r in fc]
                source_tag = "firecrawl+claude"
            else:
                results = await _ddg_search(http, query, k=6)
                if not results:
                    return {"text": f"[fallback: no results for '{query}']",
                            "citations": [], "query": query, "fallback": True}
                pages = await asyncio.gather(*[_fetch_page(http, r["url"]) for r in results[:5]])
                source_tag = "ddg+claude"

        corpus_parts: list[str] = []
        citations: list[dict[str, str]] = []
        for i, (r, body) in enumerate(zip(results, list(pages) + [""] * (len(results) - len(pages))), 1):
            citations.append({"url": r["url"], "title": r["title"]})
            chunk = body or r.get("snippet", "")
            corpus_parts.append(f"[{i}] {r['title']} — {r['url']}\n{chunk}")
        corpus = "\n\n---\n\n".join(corpus_parts)[:30000]

        system = (
            "You are a research analyst. Synthesize a dense, fact-rich answer to the user's query "
            "using ONLY the provided web sources. Cite sources inline as [n] matching the numbered list. "
            "Prefer concrete numbers, dates, named entities. If sources disagree, say so. "
            "Russian output if the query is in Russian."
        )
        user = f"Query: {query}\n\nWeb sources:\n{corpus}\n\nWrite the synthesis now."
        text = await call_text(
            model=settings.scout_model,
            system=system,
            user=user,
            temperature=0.2,
            max_tokens=3000,
        )
        return {
            "text": text,
            "citations": citations,
            "query": query,
            "fallback": source_tag,
        }
    except Exception as err:
        return {"text": f"[search+fallback failed: {err}]", "citations": [], "query": query}


async def search(query: str, focus: str = "general") -> dict[str, Any]:
    """Run one search query. Returns {text, citations}."""
    if not settings.perplexity_api_key:
        raise RuntimeError("PERPLEXITY_API_KEY is not set — refusing to run without a real search backend.")
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
                    return await _fallback(query)
                await asyncio.sleep(1.5 * (attempt + 1))
    return await _fallback(query)
