"""End-to-end orchestrator. Async, bounded parallelism for scout+analyst per cell."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from .analyst import analyze
from .bisociator import bisociate
from .config import MAX_PARALLEL_CELLS
from .io import append_jsonl, make_run_dir, write_json, write_markdown_report
from .models import Block, Cell, Finding, Question, Report
from .planner import plan
from .scout import scout
from .scrape import (
    ERZ_MOSCOW_TOP_URL,
    erz_rows_as_findings,
    fetch_erz_moscow_developer_rows,
)

__version__ = "0.3.0"


def _question_id(text: str) -> str:
    slug = re.sub(r"\W+", "-", text.lower(), flags=re.UNICODE).strip("-")[:48] or "q"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{slug}"


_ERZ_TRIGGER_TOKENS = ("срок", "перенос", "ввод", "deadline", "ерз", "erz")


def _should_enrich_with_erz(cell: Cell) -> bool:
    """True when this cell is about construction deadlines — ЕРЗ has per-developer
    transfer-delay % and monthly slip data that Perplexity cannot extract reliably.

    Conservative trigger: target_sources must include erzrf.ru AND query/layer must
    mention срок/перенос/ввод tokens. We don't want to bolt ЕРЗ onto unrelated cells.
    """
    sources = cell.scout_task.target_sources or []
    if not any("erzrf.ru" in (s or "").lower() for s in sources):
        return False
    haystack = f"{cell.layer} {cell.scout_task.query} {cell.id}".lower()
    return any(tok in haystack for tok in _ERZ_TRIGGER_TOKENS)


async def _enrich_with_erz(cell: Cell, *, log_dir: Path, mock: bool) -> list[Finding]:
    """Fetch ЕРЗ Moscow developer ranking and materialise as Finding objects.

    Failure-soft: if Jina Reader / ЕРЗ is unreachable or the table shape drifts,
    log the exception and return [] so the pipeline degrades to pure-Perplexity
    output instead of aborting.
    """
    if mock:
        return []
    try:
        rows = await fetch_erz_moscow_developer_rows(top_n=10)
    except Exception as e:  # network, 4xx, parse regression
        append_jsonl(
            log_dir / "llm_log.jsonl",
            {
                "kind": "scrape_error",
                "cell_id": cell.id,
                "source": ERZ_MOSCOW_TOP_URL,
                "error": f"{type(e).__name__}: {e}",
            },
        )
        return []
    dicts = erz_rows_as_findings(rows)
    append_jsonl(
        log_dir / "llm_log.jsonl",
        {
            "kind": "scrape",
            "cell_id": cell.id,
            "source": ERZ_MOSCOW_TOP_URL,
            "n_rows": len(rows),
            "findings": dicts,
        },
    )
    return [Finding(**d) for d in dicts]


async def _cell_pipeline(
    cell: Cell,
    *,
    sem: asyncio.Semaphore,
    mock: bool,
    log_dir: Path,
) -> Block:
    async with sem:
        findings = await scout(cell.scout_task, mock=mock, log_dir=log_dir)
        if _should_enrich_with_erz(cell):
            findings = findings + await _enrich_with_erz(cell, log_dir=log_dir, mock=mock)
        return await analyze(cell, findings, mock=mock, log_dir=log_dir)


async def run(question: str, dry_run: bool = False) -> Report:
    qid = _question_id(question)
    q = Question(text=question, id=qid)
    run_dir = make_run_dir(name=qid)

    # 1. Plan
    matrix = await plan(q, mock=dry_run, log_dir=run_dir)

    # 2. Scout + analyze per cell (bounded parallel)
    sem = asyncio.Semaphore(MAX_PARALLEL_CELLS)
    blocks: list[Block] = await asyncio.gather(
        *[
            _cell_pipeline(cell, sem=sem, mock=dry_run, log_dir=run_dir)
            for cell in matrix.cells
        ]
    )

    # 3. Bisociate
    cross_links = await bisociate(blocks, mock=dry_run, log_dir=run_dir)

    # 4. Assemble + persist
    report = Report(
        question=q,
        matrix=matrix,
        blocks=list(blocks),
        cross_links=cross_links,
        metadata={
            "run_dir": str(run_dir),
            "dry_run": dry_run,
            "version": __version__,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "n_cells": len(matrix.cells),
            "n_cross_links": len(cross_links),
        },
    )
    write_json(run_dir / "raw.json", report.model_dump())
    write_markdown_report(run_dir / "report.md", report.model_dump())
    return report
