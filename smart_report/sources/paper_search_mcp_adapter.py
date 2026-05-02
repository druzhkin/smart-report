"""Paper Search MCP adapter for academic-source discovery.

The upstream package is an MCP server, but its searchable platform classes are
plain Python. Calling those classes directly keeps the report pipeline
server-side and testable while using the installed package as the source layer.
Sci-Hub is intentionally not wired here: production report generation must stay
on open/public sources by default.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from .base import CostEstimate, Finding, SearchResult, Source

_logger = logging.getLogger(__name__)

_SearchFn = Callable[[str, int], list[Any]]


class PaperSearchMCPAdapter:
    name = "paper_search"
    is_primary_capable = False

    _COST_NOTE = "paper-search-mcp uses public/open academic APIs; direct API cost $0"
    _DEFAULT_SOURCES = ("arxiv", "semantic", "crossref")
    _MEDICAL_SOURCES = ("pubmed", "semantic", "crossref", "biorxiv", "medrxiv")
    _SCIENTIFIC_SOURCES = ("arxiv", "semantic", "crossref", "pubmed", "biorxiv", "medrxiv")

    def __init__(self, searchers: dict[str, _SearchFn] | None = None) -> None:
        self._searchers = searchers or self._load_default_searchers()

    async def search(
        self,
        query: str,
        *,
        domain_hint: str | None = None,
        max_results: int = 10,
        cost_budget_usd: float | None = None,
    ) -> SearchResult:
        del cost_budget_usd
        t0 = time.monotonic()
        source_names = self._sources_for_domain(domain_hint)
        per_source_limit = max(2, min(8, (max_results + len(source_names) - 1) // len(source_names) + 1))

        tasks = [
            asyncio.to_thread(self._run_source, source_name, query, per_source_limit)
            for source_name in source_names
            if source_name in self._searchers
        ]
        raw_batches = await asyncio.gather(*tasks, return_exceptions=True)

        errors: dict[str, str] = {}
        raw_papers: list[tuple[str, Any]] = []
        for source_name, batch in zip(source_names, raw_batches, strict=False):
            if isinstance(batch, Exception):
                errors[source_name] = f"{type(batch).__name__}: {batch}"
                _logger.warning("paper_search_mcp.%s failed: %s", source_name, batch)
                continue
            raw_papers.extend((source_name, paper) for paper in batch)

        sources, findings = self._map_raw(raw_papers, query=query, max_results=max_results)
        latency_ms = int((time.monotonic() - t0) * 1000)
        is_empty = not sources
        return SearchResult(
            findings=findings,
            sources=sources,
            raw_metadata={
                "backend": "paper_search_mcp",
                "domain_hint": domain_hint,
                "queried_sources": list(source_names),
                "raw_count": len(raw_papers),
                "errors": errors,
                "open_access_only": True,
            },
            cost_usd=0.0,
            latency_ms=latency_ms,
            is_empty_or_error=is_empty,
            error="; ".join(f"{k}: {v}" for k, v in errors.items()) if is_empty and errors else None,
        )

    @property
    def cost_per_call(self) -> CostEstimate:
        return CostEstimate(per_call_usd=0.0, notes=self._COST_NOTE)

    def _run_source(self, source_name: str, query: str, limit: int) -> list[Any]:
        return list(self._searchers[source_name](query, limit) or [])

    def _sources_for_domain(self, domain_hint: str | None) -> tuple[str, ...]:
        normalized = str(domain_hint or "").lower().replace("-", "_")
        if any(marker in normalized for marker in ("medical", "clinical", "biomedical")):
            return self._MEDICAL_SOURCES
        if any(marker in normalized for marker in ("academic", "scientific", "technical_research")):
            return self._SCIENTIFIC_SOURCES
        return self._DEFAULT_SOURCES

    def _load_default_searchers(self) -> dict[str, _SearchFn]:
        try:
            from paper_search_mcp.academic_platforms.arxiv import ArxivSearcher
            from paper_search_mcp.academic_platforms.biorxiv import BioRxivSearcher
            from paper_search_mcp.academic_platforms.crossref import CrossRefSearcher
            from paper_search_mcp.academic_platforms.medrxiv import MedRxivSearcher
            from paper_search_mcp.academic_platforms.pubmed import PubMedSearcher
            from paper_search_mcp.academic_platforms.semantic import SemanticSearcher
        except Exception as e:  # pragma: no cover - exercised only when dependency missing
            raise RuntimeError("paper-search-mcp is not installed or importable") from e

        arxiv = ArxivSearcher()
        semantic = SemanticSearcher()
        crossref = CrossRefSearcher()
        pubmed = PubMedSearcher()
        biorxiv = BioRxivSearcher()
        medrxiv = MedRxivSearcher()
        return {
            "arxiv": lambda q, n: arxiv.search(q, max_results=n),
            "semantic": lambda q, n: semantic.search(q, max_results=n),
            "crossref": lambda q, n: crossref.search(q, max_results=n),
            "pubmed": lambda q, n: pubmed.search(q, max_results=n),
            "biorxiv": lambda q, n: biorxiv.search(q, max_results=n),
            "medrxiv": lambda q, n: medrxiv.search(q, max_results=n),
        }

    def _map_raw(
        self,
        raw_papers: list[tuple[str, Any]],
        *,
        query: str,
        max_results: int,
    ) -> tuple[list[Source], list[Finding]]:
        ranked: list[tuple[int, str, str, dict[str, Any]]] = []
        for source_name, paper in raw_papers:
            data = _paper_to_dict(paper)
            title = _pick(data, "title") or "(untitled paper)"
            snippet = _pick(data, "abstract") or _pick(data, "snippet")
            score = _relevance_score(query, f"{title} {snippet}")
            ranked.append((score, source_name, snippet, data))
        if any(score > 0 for score, *_ in ranked):
            ranked = [item for item in ranked if item[0] > 0]
        ranked.sort(key=lambda item: item[0], reverse=True)

        sources: list[Source] = []
        findings: list[Finding] = []
        seen: set[str] = set()

        for score, source_name, snippet, data in ranked:
            url = _pick(data, "url", "pdf_url")
            title = _pick(data, "title") or "(untitled paper)"
            key = _dedupe_key(data, title=title, url=url)
            if key in seen:
                continue
            seen.add(key)
            metadata = {
                "paper_search_source": source_name,
                "paper_id": _pick(data, "paper_id"),
                "doi": _pick(data, "doi"),
                "authors": _pick(data, "authors"),
                "publication_date": _normalize_date(_pick(data, "published_date")),
                "pdf_url": _pick(data, "pdf_url"),
                "citations": data.get("citations"),
                "categories": _pick(data, "categories"),
                "connector": "paper_search_mcp",
                "relevance_score": score,
            }
            source = Source(
                url=url or metadata["pdf_url"] or f"paper-search-mcp:{source_name}:{key}",
                title=title,
                snippet=snippet[:600] if snippet else None,
                backend=self.name,
                raw_metadata={k: v for k, v in metadata.items() if v not in (None, "")},
                quality_tier=None,
            )
            sources.append(source)
            findings.append(
                Finding(
                    text=snippet or title,
                    sources=[source],
                    raw_metadata={"paper_search_source": source_name},
                )
            )
            if len(sources) >= max_results:
                break
        return sources, findings


def _paper_to_dict(paper: Any) -> dict[str, Any]:
    if hasattr(paper, "to_dict"):
        return dict(paper.to_dict())
    if isinstance(paper, dict):
        return paper
    return {
        key: getattr(paper, key)
        for key in (
            "paper_id",
            "title",
            "authors",
            "abstract",
            "doi",
            "published_date",
            "pdf_url",
            "url",
            "source",
            "categories",
            "citations",
        )
        if hasattr(paper, key)
    }


def _pick(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            return "; ".join(str(item) for item in value if item)
        text = str(value).strip()
        if text:
            return text
    return ""


def _dedupe_key(data: dict[str, Any], *, title: str, url: str) -> str:
    doi = _pick(data, "doi").lower()
    if doi:
        return f"doi:{doi}"
    paper_id = _pick(data, "paper_id").lower()
    if paper_id:
        return f"id:{paper_id}"
    if url:
        return f"url:{url.lower()}"
    return f"title:{' '.join(title.lower().split())}"


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def _relevance_score(query: str, text: str) -> int:
    query_terms = {
        term
        for term in _tokenize(query)
        if len(term) >= 3 and term not in _STOPWORDS
    }
    if not query_terms:
        return 0
    text_terms = set(_tokenize(text))
    score = sum(1 for term in query_terms if term in text_terms)
    normalized_text = " ".join(_tokenize(text))
    normalized_query = " ".join(_tokenize(query))
    if normalized_query and normalized_query in normalized_text:
        score += len(query_terms)
    return score


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Zа-яА-Я0-9]+", str(text).lower())
