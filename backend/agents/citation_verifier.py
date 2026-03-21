from __future__ import annotations

import asyncio
import json
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
        resp = await client.head(url)
        return resp.status_code < 400


# ---------------------------------------------------------------------------
# Content fetching: aiohttp → firecrawl fallback
# ---------------------------------------------------------------------------

async def _fetch_via_aiohttp(url: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15), ssl=False
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

        if not alive:
            return CitationCheckResult(
                url=url, claim=claim, status=CitationStatus.DEAD_LINK
            )

        content = await _fetch_content(url)
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

        if score >= SIMILARITY_THRESHOLDS["verified"]:
            status = CitationStatus.VERIFIED
        elif score >= SIMILARITY_THRESHOLDS["partial"]:
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
            claim = source.snippet or source.title or ""
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
