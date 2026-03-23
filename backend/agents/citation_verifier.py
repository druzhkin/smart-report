from __future__ import annotations

import asyncio
import json
import re
from functools import lru_cache
from typing import TYPE_CHECKING

import aiohttp
import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.state import AgentState
from backend.schemas.quality import (
    CitationCheckResult,
    CitationStatus,
    CitationVerificationResult,
)
from backend.utils.retry import api_retry

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


SIMILARITY_THRESHOLDS = {
    "verified": 0.75,
    "partial": 0.45,
}

MAX_CONTENT_CHARS = 8_000
CONCURRENT_CHECKS = 10
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
}


# ---------------------------------------------------------------------------
# Lazy-loaded embedding model (singleton)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_embedder() -> SentenceTransformer:
    from sentence_transformers import SentenceTransformer

    logger.info("Loading sentence-transformers model all-MiniLM-L6-v2")
    return SentenceTransformer("all-MiniLM-L6-v2")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    import numpy as np

    a_arr, b_arr = np.array(a), np.array(b)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


# ---------------------------------------------------------------------------
# URL liveness check (HTTP HEAD)
# ---------------------------------------------------------------------------

@api_retry(max_attempts=2)
async def _head_check(url: str) -> bool:
    async with httpx.AsyncClient(
        timeout=10, follow_redirects=True, verify=False
    ) as client:
        resp = await client.head(url, headers=REQUEST_HEADERS)
        return resp.status_code < 400


# ---------------------------------------------------------------------------
# Content fetching: aiohttp → firecrawl fallback
# ---------------------------------------------------------------------------

async def _fetch_via_aiohttp(url: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=False,
                headers=REQUEST_HEADERS,
            ) as resp:
                if resp.status >= 400:
                    return None
                html = await resp.text(errors="replace")
                from html.parser import HTMLParser
                from io import StringIO

                class _TextExtractor(HTMLParser):
                    def __init__(self) -> None:
                        super().__init__()
                        self._buf = StringIO()
                        self._skip = False

                    def handle_starttag(self, tag: str, _: list) -> None:
                        if tag in ("script", "style", "noscript"):
                            self._skip = True

                    def handle_endtag(self, tag: str) -> None:
                        if tag in ("script", "style", "noscript"):
                            self._skip = False

                    def handle_data(self, data: str) -> None:
                        if not self._skip:
                            self._buf.write(data + " ")

                    def get_text(self) -> str:
                        return self._buf.getvalue()

                extractor = _TextExtractor()
                extractor.feed(html)
                text = extractor.get_text().strip()
                return text[:MAX_CONTENT_CHARS] if text else None
    except Exception as exc:
        logger.debug(f"aiohttp fetch failed for {url}: {exc}")
        return None


async def _fetch_via_firecrawl(url: str) -> str | None:
    if not settings.firecrawl_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={
                    "Authorization": f"Bearer {settings.firecrawl_api_key}",
                    "Content-Type": "application/json",
                },
                json={"url": url, "formats": ["markdown"]},
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("data", {}).get("markdown", "")
            return text[:MAX_CONTENT_CHARS] if text else None
    except Exception as exc:
        logger.debug(f"Firecrawl fetch failed for {url}: {exc}")
        return None


async def _fetch_content(url: str) -> str | None:
    content = await _fetch_via_aiohttp(url)
    if content and len(content) > 100:
        return content
    return await _fetch_via_firecrawl(url)


def _normalize_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Zа-яА-Я0-9]+", (text or "").lower())
        if len(token) >= 4 and not token.isdigit()
    }


def _token_overlap_ratio(claim: str, content: str) -> float:
    claim_tokens = _normalize_tokens(claim)
    if not claim_tokens:
        return 0.0
    content_tokens = _normalize_tokens(content)
    if not content_tokens:
        return 0.0
    return len(claim_tokens & content_tokens) / len(claim_tokens)


# ---------------------------------------------------------------------------
# Single citation check
# ---------------------------------------------------------------------------

async def _check_citation(
    url: str, claim: str, semaphore: asyncio.Semaphore
) -> CitationCheckResult:
    async with semaphore:
        alive = False
        try:
            alive = await _head_check(url)
        except Exception:
            pass

        content = await _fetch_content(url)
        if not alive and not content:
            return CitationCheckResult(
                url=url,
                claim=claim,
                status=CitationStatus.DEAD_LINK,
                error="HEAD and content fetch both failed",
            )
        if not content:
            return CitationCheckResult(
                url=url,
                claim=claim,
                status=CitationStatus.PARTIAL,
                similarity_score=0.0,
                error="Could not fetch page content",
            )

        embedder = _get_embedder()
        embeddings = embedder.encode([claim, content])
        score = _cosine_similarity(embeddings[0].tolist(), embeddings[1].tolist())
        overlap_ratio = _token_overlap_ratio(claim, content[:2_500])
        claim_too_short = len((claim or "").strip()) < 80

        if score >= SIMILARITY_THRESHOLDS["verified"]:
            status = CitationStatus.VERIFIED
        elif score >= SIMILARITY_THRESHOLDS["partial"]:
            status = CitationStatus.PARTIAL
        elif overlap_ratio >= 0.12 or (claim_too_short and overlap_ratio >= 0.04):
            # Snippets/titles are often terse or provider-generated. Treat weak
            # semantic mismatch as partial when lexical overlap still indicates
            # the page is plausibly relevant.
            status = CitationStatus.PARTIAL
        else:
            status = CitationStatus.FABRICATED

        title = content[:120].split("\n")[0].strip()

        return CitationCheckResult(
            url=url,
            claim=claim,
            status=status,
            similarity_score=round(max(0.0, score), 4),
            page_title=title,
            error="" if status != CitationStatus.PARTIAL else ("Low-confidence citation match" if content else "Could not fetch page content"),
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

@traceable(name="citation_verifier")
async def run_citation_verifier(state: AgentState) -> dict:
    logger.info("Citation Verifier agent started")
    results = state.get("research_results", [])

    pairs: list[tuple[str, str]] = []
    for result in results:
        for source in result.sources:
            findings_context = " ".join(result.findings[:2])
            claim = " ".join(
                part.strip()
                for part in [source.title or "", source.snippet or "", findings_context]
                if part and part.strip()
            )[:1_000]
            pairs.append((source.url, claim))

    if not pairs:
        logger.info("No citations to verify")
        empty = CitationVerificationResult(passed=True)
        return {
            "messages": state.get("messages", []) + [
                {"role": "citation_verifier", "content": empty.model_dump_json()}
            ],
            "citation_verification": empty,
            "current_agent": "citation_verifier",
        }

    semaphore = asyncio.Semaphore(CONCURRENT_CHECKS)
    tasks = [_check_citation(url, claim, semaphore) for url, claim in pairs]
    checks = await asyncio.gather(*tasks)

    verification = CitationVerificationResult(checks=list(checks))
    verification.compute_stats()

    logger.info(
        f"Citation verification: {verification.verified_count}/{verification.total} verified, "
        f"pass_rate={verification.pass_rate:.2%}, passed={verification.passed}"
    )

    return {
        "messages": state.get("messages", []) + [
            {"role": "citation_verifier", "content": verification.model_dump_json()}
        ],
        "citation_verification": verification,
        "current_agent": "citation_verifier",
    }
