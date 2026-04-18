"""Orchestrator routing contract: Planner.strategy selects the backend.

These tests pin that `strategy="extract"` → `scrape.extract_via_jina` and
`strategy="search"` → `search.search` (via `scout.scout`). They are the contract
that replaces the pre-smoke-11 hardcoded ЕРЗ enrichment gate in `orchestrator.py`.
If the gate silently comes back or the wrong backend gets wired, these fail.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from smart_report import orchestrator
from smart_report.models import Block, Cell, ScoutTask


async def _run_one_cell(cell: Cell, monkeypatch) -> tuple[list, list]:
    """Invoke the orchestrator's per-cell pipeline with patched Scout/Jina/Analyst.

    Returns (extract_calls, scout_calls): each is a list of the args the fake
    was called with. Lets tests assert which backend fired.
    """
    extract_calls: list = []
    scout_calls: list = []

    async def fake_extract(target_urls, *, focus=None, cell_id=None, log_dir=None):
        extract_calls.append({"urls": list(target_urls), "focus": focus, "cell_id": cell_id})
        return []

    async def fake_scout(task, *, mock=False, log_dir=None):
        scout_calls.append({"cell_id": task.cell_id, "query": task.query})
        return []

    async def fake_analyze(cell, findings, *, mock=False, log_dir=None):
        return Block(cell_id=cell.id, conclusion="stub")

    monkeypatch.setattr(orchestrator, "extract_via_jina", fake_extract)
    monkeypatch.setattr(orchestrator, "scout", fake_scout)
    monkeypatch.setattr(orchestrator, "analyze", fake_analyze)

    with tempfile.TemporaryDirectory() as td:
        block = await orchestrator._cell_pipeline(
            cell,
            sem=asyncio.Semaphore(1),
            mock=False,
            log_dir=Path(td),
        )
    assert isinstance(block, Block)
    return extract_calls, scout_calls


async def test_extract_strategy_calls_jina_not_perplexity(monkeypatch) -> None:
    task = ScoutTask(
        cell_id="c",
        query="Top-5 sector X market cap",
        strategy="extract",
        target_urls=["https://example.com/sector-x/market-cap"],
    )
    cell = Cell(id="c", domain="d", layer="l", scout_task=task)

    extract_calls, scout_calls = await _run_one_cell(cell, monkeypatch)

    assert len(extract_calls) == 1, "extract backend must fire exactly once"
    assert extract_calls[0]["urls"] == ["https://example.com/sector-x/market-cap"]
    assert extract_calls[0]["focus"] == "Top-5 sector X market cap"
    assert scout_calls == [], "search backend must NOT fire for strategy=extract"


async def test_search_strategy_calls_perplexity_not_jina(monkeypatch) -> None:
    task = ScoutTask(
        cell_id="c",
        query="overview of sector X dynamics 2023-2025",
        target_sources=["example.com"],
        # strategy defaults to "search"
    )
    cell = Cell(id="c", domain="d", layer="l", scout_task=task)

    extract_calls, scout_calls = await _run_one_cell(cell, monkeypatch)

    assert len(scout_calls) == 1, "search backend must fire exactly once"
    assert scout_calls[0]["cell_id"] == "c"
    assert extract_calls == [], "extract backend must NOT fire for strategy=search"


def test_scout_task_extract_requires_target_urls() -> None:
    """Validator: strategy='extract' with empty target_urls must raise."""
    with pytest.raises(ValidationError) as excinfo:
        ScoutTask(cell_id="c", query="q", strategy="extract", target_urls=[])
    assert "target_url" in str(excinfo.value).lower()


def test_scout_task_search_is_default_and_permits_empty_urls() -> None:
    """Default strategy is search; target_urls can be empty."""
    t = ScoutTask(cell_id="c", query="q")
    assert t.strategy == "search"
    assert t.target_urls == []
