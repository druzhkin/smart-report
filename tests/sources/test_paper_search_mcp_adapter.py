from __future__ import annotations

from datetime import datetime

import pytest

from smart_report.sources.paper_search_mcp_adapter import PaperSearchMCPAdapter


class FakePaper:
    def __init__(
        self,
        *,
        paper_id: str,
        title: str,
        abstract: str,
        doi: str = "",
        url: str = "",
        source: str = "arxiv",
    ) -> None:
        self.paper_id = paper_id
        self.title = title
        self.abstract = abstract
        self.doi = doi
        self.url = url
        self.pdf_url = ""
        self.authors = ["A. Author"]
        self.published_date = datetime(2025, 1, 1)
        self.source = source
        self.categories = ["economics"]
        self.citations = 12

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "doi": self.doi,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "authors": self.authors,
            "published_date": self.published_date,
            "source": self.source,
            "categories": self.categories,
            "citations": self.citations,
        }


@pytest.mark.asyncio
async def test_paper_search_adapter_maps_public_academic_sources() -> None:
    adapter = PaperSearchMCPAdapter(
        searchers={
            "arxiv": lambda query, limit: [
                FakePaper(
                    paper_id="2501.12345",
                    title="Housing supply constraints and price dynamics",
                    abstract="A quantified study of supply constraints and mortgage rates.",
                    doi="10.1000/test",
                    url="https://arxiv.org/abs/2501.12345",
                )
            ],
            "semantic": lambda query, limit: [
                FakePaper(
                    paper_id="duplicate",
                    title="Duplicate should be removed",
                    abstract="Same DOI.",
                    doi="10.1000/test",
                    url="https://www.semanticscholar.org/paper/duplicate",
                    source="semantic",
                )
            ],
            "crossref": lambda query, limit: [],
            "pubmed": lambda query, limit: [],
            "biorxiv": lambda query, limit: [],
            "medrxiv": lambda query, limit: [],
        }
    )

    result = await adapter.search(
        "mortgage rates housing prices",
        domain_hint="scientific",
        max_results=5,
    )

    assert not result.is_empty_or_error
    assert result.cost_usd == 0
    assert result.raw_metadata["backend"] == "paper_search_mcp"
    assert result.raw_metadata["open_access_only"] is True
    assert result.sources[0].backend == "paper_search"
    assert result.sources[0].raw_metadata["paper_search_source"] == "arxiv"
    assert result.sources[0].raw_metadata["connector"] == "paper_search_mcp"
    assert len(result.sources) == 1
    assert result.findings[0].sources == [result.sources[0]]


@pytest.mark.asyncio
async def test_paper_search_adapter_surfaces_partial_source_errors() -> None:
    def fail(query: str, limit: int) -> list[FakePaper]:
        raise RuntimeError("rate limited")

    adapter = PaperSearchMCPAdapter(
        searchers={
            "arxiv": fail,
            "semantic": lambda query, limit: [
                FakePaper(
                    paper_id="s2",
                    title="Semantic Scholar result",
                    abstract="Recovered from another academic source.",
                    url="https://www.semanticscholar.org/paper/s2",
                    source="semantic",
                )
            ],
            "crossref": lambda query, limit: [],
        }
    )

    result = await adapter.search("academic query", max_results=3)

    assert not result.is_empty_or_error
    assert "arxiv" in result.raw_metadata["errors"]
    assert result.sources[0].raw_metadata["paper_search_source"] == "semantic"
