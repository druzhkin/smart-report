"""Async orchestrator: planner → scouts → analysts → bisociator → summarizer.

Also: save/load and second-pass operations (deepen_cell, add_domain, connect_domains).
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from agents.analyst import analyst
from agents.bisociator import bisociate_pair, bisociator
from agents.planner import plan_deepen, plan_new_domain, planner
from agents.scout import scout
from agents.summarizer import summarize
from config import (
    depth_profile,
    model_for,
    profile_int,
    set_active_profile,
    settings,
)
from llm import LLMAuthError, call_text, reset_meter
from models import (
    Block,
    CellPlan,
    Connection,
    Finding,
    Matrix,
    Report,
    ScoutResult,
    ScoutTask,
)

logger = logging.getLogger(__name__)


T = TypeVar("T")

ProgressCb = Callable[[str, str], None]


def _noop(event: str, message: str) -> None:
    pass


async def _bounded_gather(coros: list[Awaitable[T]], limit: int) -> list[T]:
    sem = asyncio.Semaphore(limit)

    async def _run(c: Awaitable[T]) -> T:
        async with sem:
            return await c

    return await asyncio.gather(*[_run(c) for c in coros])


# ---------- shared building blocks ----------


async def _rewrite_task_broader(task: ScoutTask) -> ScoutTask:
    """One cheap scout-model call to reformulate an empty-cell task with broader scope."""
    try:
        new_q = await call_text(
            model=model_for("scout"),
            system="Ты переформулируешь поисковые задания Scout-агента.",
            user=(
                f"Задание не вернуло результатов: «{task.query_focus}»\n"
                "Переформулируй его шире: убери специфические термины, используй синонимы, "
                "расширь временной диапазон и географию. Верни только новый запрос, одной строкой, без кавычек."
            ),
            temperature=0.4,
            max_tokens=180,
        )
        new_q = new_q.strip().strip('"«»')
        if not new_q:
            return task
        return task.model_copy(update={"query_focus": new_q})
    except Exception:
        return task


async def _rewrite_task_international(task: ScoutTask) -> ScoutTask:
    """Translate query to English and pivot to international analogs; force web search_type."""
    try:
        new_q = await call_text(
            model=model_for("scout"),
            system="Ты переформулируешь поисковые задания Scout-агента на английский язык.",
            user=(
                f"Задание не вернуло результатов на русском: «{task.query_focus}»\n"
                "Переведи на английский и переориентируй на международные аналоги "
                "(например, вместо «московская премиум недвижимость» → "
                "«Moscow-comparable global cities premium residential price premiums Knight Frank CBRE Savills»). "
                "Включи названия ведущих консультантов/агентств (Knight Frank, CBRE, Savills, JLL, McKinsey, OECD). "
                "Верни только один поисковый запрос на английском, одной строкой, без кавычек."
            ),
            temperature=0.4,
            max_tokens=200,
        )
        new_q = new_q.strip().strip('"\'')
        if not new_q:
            return task
        return task.model_copy(update={"query_focus": new_q, "search_type": "web"})
    except Exception:
        return task


async def _rewrite_task_pivot(task: ScoutTask) -> ScoutTask:
    """Pivot to a different angle / adjacent domain when direct and international queries both failed."""
    try:
        new_q = await call_text(
            model=model_for("scout"),
            system="Ты переформулируешь поисковые задания Scout-агента, меняя угол зрения.",
            user=(
                f"Два предыдущих варианта поискового задания не дали результатов: «{task.query_focus}»\n"
                "Предложи смежный угол: если исходное задание о предпочтениях покупателей — "
                "попробуй кейсы девелоперов, смежный массовый сегмент, паттерны трат на люкс. "
                "Если о ценах — попробуй транзакционные данные, ипотечные показатели, индексы аренды. "
                "Сохрани ту же тематическую область. Верни только новый запрос, одной строкой, без кавычек."
            ),
            temperature=0.5,
            max_tokens=200,
        )
        new_q = new_q.strip().strip('"«»')
        if not new_q:
            return task
        return task.model_copy(update={"query_focus": new_q})
    except Exception:
        return task


async def _run_scouts_for_tasks(
    tasks: list[ScoutTask], progress: ProgressCb
) -> list[ScoutResult]:
    limit = profile_int("max_parallel_scouts", settings.max_parallel_scouts)
    progress("scout", f"Запускаю {len(tasks)} Scout'ов (до {limit} параллельно)")

    async def _one(task: ScoutTask) -> ScoutResult:
        progress("scout", f"[{task.cell}] {task.query_focus[:110]}")
        try:
            return await scout(task)
        except LLMAuthError:
            raise
        except Exception as err:
            progress("scout", f"[{task.cell}] ОШИБКА: {err}")
            return ScoutResult(task=task, findings=[], notes=f"scout failed: {err}")

    return await _bounded_gather([_one(t) for t in tasks], limit)


async def _analyze_cells(
    by_cell: dict[str, list[ScoutResult]], progress: ProgressCb
) -> list[Block]:
    limit = profile_int("max_parallel_analysts", settings.max_parallel_analysts)
    progress("analyst", f"Синтезирую {len(by_cell)} блок(ов) (до {limit} параллельно)")

    async def _one(cell: str, results: list[ScoutResult]) -> Block | None:
        if not any(sr.findings for sr in results):
            progress("analyst", f"[{cell}] пусто — пропущен")
            return None
        try:
            block = await analyst(cell, results)
            progress("analyst", f"[{cell}] готов: {len(block.findings)} источников, {len(block.gaps)} пробелов")
            return block
        except LLMAuthError:
            raise
        except Exception as err:
            progress("analyst", f"[{cell}] ОШИБКА: {err}")
            return None

    out = await _bounded_gather(
        [_one(cell, rs) for cell, rs in by_cell.items()],
        limit,
    )
    return [b for b in out if b is not None]


async def _finalize(
    goal: str,
    matrix: Matrix,
    blocks: list[Block],
    progress: ProgressCb,
) -> Report:
    connections: list[Connection] = []
    if len(blocks) >= 2:
        progress("bisociator", "Ищу кросс-доменные связи (минимум 10)")
        try:
            connections = await bisociator(blocks, min_target=10)
            progress("bisociator", f"Найдено связей: {len(connections)}")
        except Exception as err:
            progress("bisociator", f"ОШИБКА: {err}")
    else:
        progress("bisociator", "Недостаточно блоков для бисоциации (нужно ≥2)")

    exec_summary = None
    block_headers = []
    if blocks:
        progress("summarizer", "Собираю Executive Summary и шапки блоков")
        try:
            payload = await summarize(goal, matrix, blocks, connections)
            exec_summary = payload.exec_summary
            block_headers = payload.block_headers
            progress(
                "summarizer",
                f"Приоритеты: {sum(1 for h in block_headers if h.priority == 'high')} high / "
                f"{sum(1 for h in block_headers if h.priority == 'medium')} medium / "
                f"{sum(1 for h in block_headers if h.priority == 'low')} low",
            )
        except Exception as err:
            progress("summarizer", f"ОШИБКА: {err}")

    pre_mortems = []
    if blocks:
        progress("pre_mortem", "Пре-мортем: где вывод может провалиться")
        try:
            from agents.pre_mortem import pre_mortem as _pre_mortem
            pre_mortems = await _pre_mortem(goal, blocks, connections)
            progress("pre_mortem", f"Режимов провала: {len(pre_mortems)}")
        except Exception as err:
            progress("pre_mortem", f"ОШИБКА: {err}")

    causal_chains = []
    if len(blocks) >= 2:
        try:
            from agents.causal_chains import causal_chains as _chains
            causal_chains = await _chains(goal, blocks, connections)
            progress("causal_chains", f"Длинных цепочек: {len(causal_chains)}")
        except Exception as err:
            progress("causal_chains", f"ОШИБКА: {err}")

    scenario_cone = None
    try:
        from agents.scenarios import scenarios as _scenarios
        scenario_cone = await _scenarios(
            goal=goal,
            question_type=matrix.question_type,
            blocks=blocks,
            connections=connections,
        )
        progress("scenarios", f"cone_generated={scenario_cone is not None}")
    except Exception as err:
        progress("scenarios", f"ОШИБКА: {err}")

    assumption_inversions = []
    try:
        from agents.quadrant_crunch import quadrant_crunch as _quadrant_crunch
        assumption_inversions = await _quadrant_crunch(
            goal=goal,
            blocks=blocks,
        )
        progress("quadrant_crunch", f"blocks_processed={len(assumption_inversions)}")
    except Exception as e:
        progress("quadrant_crunch", f"failed: {e}")
        assumption_inversions = []

    return Report(
        goal=goal,
        matrix=matrix,
        blocks=blocks,
        connections=connections,
        exec_summary=exec_summary,
        block_headers=block_headers,
        pre_mortems=pre_mortems,
        causal_chains=causal_chains,
        scenario_cone=scenario_cone,
        assumption_inversions=assumption_inversions,
    )


# ---------- first pass ----------


async def run_research(
    goal: str,
    progress: ProgressCb = _noop,
    matrix: Matrix | None = None,
    depth: str = "standard",
) -> Report:
    set_active_profile(depth_profile(depth))
    reset_meter()
    progress("depth", f"Глубина: {depth}")

    if matrix is None:
        progress("planner", f"Декомпозирую цель ({depth}): {goal!r}")
        matrix = await planner(goal, depth=depth)
        progress("planner", f"question_type={matrix.question_type}")
        progress(
            "planner",
            f"Матрица: {len(matrix.domains)} домен(ов), "
            f"{sum(len(d.layers) for d in matrix.domains)} ячеек, "
            f"{sum(len(cp.tasks) for cp in matrix.cell_plans)} заданий",
        )

    all_tasks: list[ScoutTask] = []
    for cp in matrix.cell_plans:
        for t in cp.tasks:
            if not t.cell:
                t = t.model_copy(update={"cell": cp.cell})
            all_tasks.append(t)

    scout_results = await _run_scouts_for_tasks(all_tasks, progress)

    by_cell: dict[str, list[ScoutResult]] = {}
    for sr in scout_results:
        by_cell.setdefault(sr.task.cell, []).append(sr)

    # Empty-cell fallback: 3-level cascade
    empty_cells = [c for c, rs in by_cell.items() if not any(sr.findings for sr in rs)]
    for cp in matrix.cell_plans:
        if cp.cell not in by_cell:
            empty_cells.append(cp.cell)
            by_cell[cp.cell] = []

    _fallback_rewriters = [
        ("L1", _rewrite_task_broader),
        ("L2", _rewrite_task_international),
        ("L3", _rewrite_task_pivot),
    ]

    if empty_cells:
        progress("scout", f"Пустых ячеек: {len(empty_cells)} — запускаю 3-уровневый fallback")
        still_empty = list(empty_cells)
        for level_tag, rewriter in _fallback_rewriters:
            if not still_empty:
                break
            progress("scout", f"fallback {level_tag} для {len(still_empty)} ячеек: {still_empty}")
            retry_tasks: list[ScoutTask] = []
            for cell in still_empty:
                src = next(
                    (t for t in all_tasks if t.cell == cell),
                    ScoutTask(cell=cell, query_focus=cell, source_hints=""),
                )
                progress("scout", f"fallback {level_tag} for cell={cell}")
                retry_tasks.append(await rewriter(src))
            try:
                retry_results = await _run_scouts_for_tasks(retry_tasks, progress)
                for sr in retry_results:
                    by_cell.setdefault(sr.task.cell, []).append(sr)
            except Exception as err:
                progress("scout", f"fallback {level_tag} failed: {err}")
            still_empty = [c for c in still_empty if not any(sr.findings for sr in by_cell.get(c, []))]

        for cell in still_empty:
            stub = ScoutResult(
                task=ScoutTask(cell=cell, query_focus="stub", source_hints=""),
                findings=[
                    Finding(
                        claim="Данные по этой ячейке не найдены в открытых источниках.",
                        source="system",
                        source_label="system",
                        source_type="opinion",
                        has_numbers=False,
                    )
                ],
                notes="empty-cell stub",
            )
            by_cell.setdefault(cell, []).append(stub)

    blocks = await _analyze_cells(by_cell, progress)
    return await _finalize(goal, matrix, blocks, progress)


# ---------- persistence ----------


def save_report(report: Report, path: Path) -> None:
    path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


_VALID_SOURCE_TYPES = {
    "primary_academic", "primary_official", "primary_data",
    "secondary", "opinion",
}


def _fix_source_types(data: dict) -> dict:
    """Remap legacy source_type values that no longer match the Literal enum."""
    for block in data.get("blocks", []):
        for finding in block.get("findings", []):
            st = finding.get("source_type")
            if st and st not in _VALID_SOURCE_TYPES:
                finding["source_type"] = "secondary"
    return data


def load_report(path: Path) -> Report:
    data = json.loads(path.read_text(encoding="utf-8"))
    data = _fix_source_types(data)
    return Report.model_validate(data)


# ---------- second-pass operations ----------


async def deepen_cell(
    report: Report, cell: str, focus: str, progress: ProgressCb = _noop
) -> Report:
    existing = next((b for b in report.blocks if b.cell == cell), None)
    if existing is None:
        progress("deepen", f"Блок {cell!r} не найден — создам с нуля")
    progress("deepen", f"Планирую новые задания для {cell!r} с фокусом: {focus!r}")
    tasks = await plan_deepen(
        cell=cell,
        focus=focus,
        existing_gaps=existing.gaps if existing else [],
        existing_entities=existing.key_entities if existing else [],
    )
    progress("deepen", f"Получено заданий: {len(tasks)}")
    scout_results = await _run_scouts_for_tasks(tasks, progress)
    # Re-run analyst with merged old+new findings (as fake ScoutResults)
    merged: list[ScoutResult] = list(scout_results)
    if existing:
        # Wrap existing findings as one synthetic ScoutResult so analyst sees them too.
        merged.append(
            ScoutResult(
                task=ScoutTask(
                    cell=cell,
                    query_focus=f"[прошлые находки блока] {focus}",
                    source_hints="prior-run",
                ),
                findings=existing.findings,
                notes="previous block findings, preserved",
            )
        )
    blocks_new = await _analyze_cells({cell: merged}, progress)
    if not blocks_new:
        progress("deepen", "Новый синтез пуст — оставляю предыдущий блок")
        return report

    new_block = blocks_new[0]
    rebuilt_blocks = [new_block if b.cell == cell else b for b in report.blocks]
    if existing is None:
        rebuilt_blocks.append(new_block)
    return await _finalize(report.goal, report.matrix, rebuilt_blocks, progress)


async def add_domain(
    report: Report,
    domain_name: str,
    layers_hint: list[str] | None = None,
    progress: ProgressCb = _noop,
) -> Report:
    progress("add-domain", f"Добавляю домен {domain_name!r}")
    new_domain, cell_plans = await plan_new_domain(
        goal=report.goal,
        existing_matrix=report.matrix,
        domain_name=domain_name,
        layers_hint=layers_hint,
    )
    progress(
        "add-domain",
        f"{new_domain.name}: {len(new_domain.layers)} слоёв, "
        f"{sum(len(cp.tasks) for cp in cell_plans)} заданий",
    )
    tasks: list[ScoutTask] = []
    for cp in cell_plans:
        for t in cp.tasks:
            if not t.cell:
                t = t.model_copy(update={"cell": cp.cell})
            tasks.append(t)
    scout_results = await _run_scouts_for_tasks(tasks, progress)
    by_cell: dict[str, list[ScoutResult]] = {}
    for sr in scout_results:
        by_cell.setdefault(sr.task.cell, []).append(sr)
    new_blocks = await _analyze_cells(by_cell, progress)

    new_matrix = report.matrix.model_copy(
        update={
            "domains": [*report.matrix.domains, new_domain],
            "cell_plans": [*report.matrix.cell_plans, *cell_plans],
        }
    )
    all_blocks = [*report.blocks, *new_blocks]
    return await _finalize(report.goal, new_matrix, all_blocks, progress)


async def connect_domains(
    report: Report, domain_a: str, domain_b: str, progress: ProgressCb = _noop
) -> Report:
    def _belongs(block_cell: str, domain: str) -> bool:
        return block_cell.split(" / ", 1)[0].strip() == domain.strip()

    blocks_a = [b for b in report.blocks if _belongs(b.cell, domain_a)]
    blocks_b = [b for b in report.blocks if _belongs(b.cell, domain_b)]
    if not blocks_a or not blocks_b:
        progress("connect", f"Не хватает блоков в {domain_a!r} или {domain_b!r}")
        return report

    progress("connect", f"{len(blocks_a)} × {len(blocks_b)} пар блоков")

    async def _one(pair: tuple[Block, Block]) -> list[Connection]:
        a, b = pair
        try:
            return await bisociate_pair(a, b)
        except Exception as err:
            progress("connect", f"[{a.cell} × {b.cell}] ОШИБКА: {err}")
            return []

    results = await _bounded_gather(
        [_one((a, b)) for a in blocks_a for b in blocks_b],
        profile_int("max_parallel_analysts", settings.max_parallel_analysts),
    )
    new_conns: list[Connection] = [c for sub in results for c in sub]

    # dedup by (sorted domains, shared_entity, nature)
    seen: set[tuple] = set()
    merged: list[Connection] = []
    for c in [*report.connections, *new_conns]:
        key = (tuple(sorted(c.domains)), c.shared_entity.lower().strip(), c.nature)
        if key in seen:
            continue
        seen.add(key)
        merged.append(c)
    progress("connect", f"Всего связей после мержа: {len(merged)} (добавлено новых: {len(new_conns)})")

    # Re-run summarizer so exec summary reflects new connections.
    progress("summarizer", "Пересобираю Executive Summary")
    try:
        payload = await summarize(report.goal, report.matrix, report.blocks, merged)
        exec_summary = payload.exec_summary
        block_headers = payload.block_headers
    except Exception as err:
        progress("summarizer", f"ОШИБКА: {err}")
        exec_summary = report.exec_summary
        block_headers = report.block_headers

    return report.model_copy(
        update={
            "connections": merged,
            "exec_summary": exec_summary,
            "block_headers": block_headers,
        }
    )
