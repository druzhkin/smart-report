"""End-to-end orchestrator. Async, bounded parallelism for scout+analyst per cell."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from .analyst import analyze
from .bisociator import bisociate
from .config import MAX_PARALLEL_CELLS
from .io import make_run_dir, write_json, write_markdown_report
from .models import Block, Cell, Question, Report
from .planner import plan
from .scout import scout

__version__ = "0.3.0"


def _question_id(text: str) -> str:
    slug = re.sub(r"\W+", "-", text.lower(), flags=re.UNICODE).strip("-")[:48] or "q"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{slug}"


async def _cell_pipeline(
    cell: Cell,
    *,
    sem: asyncio.Semaphore,
    mock: bool,
    log_dir: Path,
) -> Block:
    async with sem:
        findings = await scout(cell.scout_task, mock=mock, log_dir=log_dir)
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
