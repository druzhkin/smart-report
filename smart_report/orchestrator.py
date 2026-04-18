"""End-to-end orchestrator. Async, bounded parallelism for scout+analyst per cell."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from .analyst import analyze
from .bisociator import bisociate
from .config import MAX_PARALLEL_CELLS
from .events import EventEmitter, NullEmitter
from .io import make_run_dir, write_json, write_markdown_report
from .models import Block, Cell, Finding, Question, Report
from .planner import plan
from .scout import scout
from .scrape import extract_via_jina
from .summarizer import summarize

__version__ = "0.5.0"


def _question_id(text: str) -> str:
    slug = re.sub(r"\W+", "-", text.lower(), flags=re.UNICODE).strip("-")[:48] or "q"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{slug}"


async def _gather_findings(
    cell: Cell, *, mock: bool, log_dir: Path
) -> list[Finding]:
    task = cell.scout_task
    if task.strategy == "extract":
        if mock:
            return []
        return await extract_via_jina(
            task.target_urls,
            focus=task.query,
            cell_id=task.cell_id,
            log_dir=log_dir,
        )
    return await scout(task, mock=mock, log_dir=log_dir)


async def _cell_pipeline(
    cell: Cell,
    *,
    sem: asyncio.Semaphore,
    mock: bool,
    log_dir: Path,
    emitter: EventEmitter | None = None,
) -> Block:
    emitter = emitter or NullEmitter()
    async with sem:
        emitter.emit(
            "scout",
            f"[{cell.id}] Поиск начат",
            data={"cell_id": cell.id, "query": cell.scout_task.query},
        )
        findings = await _gather_findings(cell, mock=mock, log_dir=log_dir)
        emitter.emit(
            "scout",
            f"[{cell.id}] Поиск завершён: {len(findings)} находок",
            data={"cell_id": cell.id, "n_findings": len(findings)},
        )

        emitter.emit(
            "analyst",
            f"[{cell.id}] Анализ начат",
            data={"cell_id": cell.id},
        )
        block = await analyze(cell, findings, mock=mock, log_dir=log_dir)
        emitter.emit(
            "analyst",
            f"Блок {cell.id} готов",
            data={"cell_id": cell.id, "conclusion": (block.conclusion or "")[:120]},
        )
        return block


async def run(
    question: str,
    dry_run: bool = False,
    *,
    emitter: EventEmitter | None = None,
) -> Report:
    em: EventEmitter = emitter or NullEmitter()
    qid = _question_id(question)
    q = Question(text=question, id=qid)
    run_dir = make_run_dir(name=qid)

    try:
        em.emit("status", "Запуск пайплайна", data={"question_id": qid, "dry_run": dry_run})

        # 1. Plan
        em.emit("planner", "Планировщик начал работу")
        matrix = await plan(q, mock=dry_run, log_dir=run_dir)
        em.emit(
            "planner",
            f"Матрица готова: {len(matrix.cells)} ячеек",
            data={"n_cells": len(matrix.cells), "domains": matrix.domains},
        )

        # 2. Scout + analyze per cell (bounded parallel)
        sem = asyncio.Semaphore(MAX_PARALLEL_CELLS)
        blocks: list[Block] = await asyncio.gather(
            *[
                _cell_pipeline(cell, sem=sem, mock=dry_run, log_dir=run_dir, emitter=em)
                for cell in matrix.cells
            ]
        )

        # 3. Bisociate
        em.emit("bisociator", "Поиск кросс-доменных связей")
        cross_links = await bisociate(blocks, mock=dry_run, log_dir=run_dir)
        em.emit(
            "bisociator",
            f"Найдено связей: {len(cross_links)}",
            data={"n_cross_links": len(cross_links)},
        )

        # 4. Summarize
        em.emit("summarizer", "Формирование executive summary")
        summary = await summarize(
            q, list(blocks), cross_links, mock=dry_run, log_dir=run_dir
        )
        em.emit(
            "summarizer",
            "Executive summary готов",
            data={
                "n_top_numbers": len(summary.top_numbers),
                "n_key_tensions": len(summary.key_tensions),
                "n_open_questions": len(summary.open_questions),
            },
        )

        # 5. Assemble + persist
        report = Report(
            question=q,
            matrix=matrix,
            blocks=list(blocks),
            cross_links=cross_links,
            summary=summary,
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
        em.emit(
            "done",
            "Готово",
            data={
                "question_id": qid,
                "run_dir": str(run_dir),
                "n_cells": len(matrix.cells),
                "n_cross_links": len(cross_links),
            },
        )
        return report
    except Exception as e:
        em.emit(
            "error",
            f"Ошибка: {type(e).__name__}: {e}",
            data={"error_type": type(e).__name__},
        )
        raise
