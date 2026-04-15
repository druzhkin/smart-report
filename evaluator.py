"""Self-improvement loop for prompts. Karpathy-style propose → evaluate → keep/discard.

- evaluate_report(report) → dict of 7 metrics (via llm.call_json)
- eval_loop(query, max_iterations=2) — run → evaluate → update prompts → rerun → compare → rollback if worse
- Logs everything to reports/eval_log.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from config import PROMPTS_DIR, settings
from llm import call_json
from models import Report
from orchestrator import run_research

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
EVAL_LOG = REPORTS_DIR / "eval_log.json"
PROMPT_BACKUPS = REPORTS_DIR / "prompt_backups"
PROMPT_BACKUPS.mkdir(exist_ok=True)


# ---------- schemas ----------

class CriterionScore(BaseModel):
    name: str
    score: int = Field(ge=0, le=10)
    justification: str
    recommendation: str = Field(default="", description="Что поменять в промпте, если score < 7")
    target_prompt: str = Field(
        default="",
        description="Имя промпт-файла (без .md) — planner / scout / analyst / bisociator / summarizer",
    )


class EvaluationResult(BaseModel):
    exec_summary: CriterionScore
    concreteness: CriterionScore
    depth: CriterionScore
    bisociation: CriterionScore
    gaps: CriterionScore
    assumptions: CriterionScore
    banality: CriterionScore

    def total(self) -> int:
        return sum(
            getattr(self, n).score
            for n in (
                "exec_summary", "concreteness", "depth",
                "bisociation", "gaps", "assumptions", "banality",
            )
        )

    def low_scores(self, threshold: int = 7) -> list[CriterionScore]:
        return [
            c for c in (
                self.exec_summary, self.concreteness, self.depth,
                self.bisociation, self.gaps, self.assumptions, self.banality,
            ) if c.score < threshold
        ]


class PromptPatch(BaseModel):
    new_content: str = Field(..., description="Полный новый текст промпт-файла")
    change_note: str = Field(..., description="Краткое описание изменения — 1-2 предложения")


# ---------- eval prompt ----------

EVAL_SYSTEM = """Ты — строгий AI-редактор. Оценивай аналитические отчёты для топ-менеджмента по 7 критериям.
Отвечай ТОЛЬКО валидным JSON по схеме. Каждый критерий — от 0 до 10. Для score < 7 обязательно укажи
recommendation (что именно изменить в промпте) и target_prompt (один из: planner, scout, analyst, bisociator, summarizer).
Будь честен и конкретен — банальные оценки «и так норм» не нужны."""

EVAL_USER_TEMPLATE = """Отчёт в JSON:

```json
{report_json}
```

Оцени по 7 критериям (0-10 каждый):

1. exec_summary — помещается ли Executive Summary на 1 страницу? Даёт ли картину за 2 минуты чтения?
2. concreteness — какой % блоков содержит конкретные цифры с первичным источником?
3. depth — есть ли выводы, требующие комбинации 2+ источников (не пересказ одного)?
4. bisociation — сколько связей найдено? Сколько парадоксов/причинных цепочек? (10 и больше нетривиальных = высший балл)
5. gaps — конкретные ли пробелы (с адресом поиска) или абстрактные?
6. assumptions — перечислены ли неявные допущения в каждом блоке?
7. banality — есть ли блоки, не дающие ничего сверх здравого смысла? (ПЕРЕВЁРНУТАЯ шкала: 10 = нет банальности, 0 = сплошная банальность)

Для каждого score < 7 — укажи конкретную рекомендацию (что поменять в промпте и как) и target_prompt (имя файла без .md).
Если score ≥ 7, recommendation и target_prompt можно оставить пустыми строками.

Верни JSON строго по схеме:
{{
  "exec_summary": {{"name":"exec_summary","score":0,"justification":"...","recommendation":"...","target_prompt":"summarizer"}},
  "concreteness": {{...}},
  "depth": {{...}},
  "bisociation": {{...}},
  "gaps": {{...}},
  "assumptions": {{...}},
  "banality": {{...}}
}}
"""


async def evaluate_report(report: Report) -> dict:
    """Evaluate a report. Returns dict with scores + total + raw EvaluationResult."""
    # Trim report JSON to avoid blowing context/credits
    report_dict = report.model_dump()
    # Keep executive summary, block headers, connections in full; trim block findings details
    for b in report_dict.get("blocks", []):
        # Keep only first 6 findings per block; trim claim length
        b["findings"] = b.get("findings", [])[:6]
        for f in b["findings"]:
            f["claim"] = f["claim"][:240]
        b["summary"] = b.get("summary", "")[:800]

    payload = json.dumps(report_dict, ensure_ascii=False)
    # Hard cap context: ~60k chars (~15k tokens)
    if len(payload) > 60000:
        payload = payload[:60000] + "...[truncated]"

    user = EVAL_USER_TEMPLATE.format(report_json=payload)

    result = await call_json(
        model=settings.analyst_model,
        system=EVAL_SYSTEM,
        user=user,
        schema=EvaluationResult,
        temperature=0.2,
        max_tokens=4000,
    )
    return {
        "total": result.total(),
        "scores": result.model_dump(),
        "low_scores": [c.model_dump() for c in result.low_scores()],
        "raw": result,
    }


# ---------- prompt mutation ----------

PROMPT_UPDATE_SYSTEM = """Ты — prompt-engineer. Тебе дают текущий промпт и критику: оценку и рекомендацию.
Твоя задача — переписать промпт, чтобы устранить проблему. Сохрани структуру и стиль оригинального промпта.
Не меняй JSON-схемы выхода. Не удаляй полезные разделы. Только усиль там, где указывает критика.

Отвечай ТОЛЬКО валидным JSON вида:
{
  "new_content": "полный новый текст промпта",
  "change_note": "1-2 предложения про изменение"
}
"""

PROMPT_UPDATE_USER = """Файл: {prompt_name}.md

Текущий промпт:
---
{current_content}
---

Оценка: {score}/10
Критика: {justification}
Рекомендация: {recommendation}

Перепиши промпт, чтобы поднять оценку. Верни JSON с полями new_content и change_note."""


async def propose_prompt_patch(
    prompt_name: str, current: str, criterion: CriterionScore
) -> PromptPatch | None:
    user = PROMPT_UPDATE_USER.format(
        prompt_name=prompt_name,
        current_content=current[:12000],
        score=criterion.score,
        justification=criterion.justification,
        recommendation=criterion.recommendation,
    )
    try:
        return await call_json(
            model=settings.analyst_model,
            system=PROMPT_UPDATE_SYSTEM,
            user=user,
            schema=PromptPatch,
            temperature=0.3,
            max_tokens=8000,
        )
    except Exception as err:
        print(f"[eval-loop] propose_prompt_patch({prompt_name}) FAILED: {err}")
        return None


# ---------- prompt backup / restore ----------

def _backup_prompts(run_id: str) -> Path:
    backup_dir = PROMPT_BACKUPS / run_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in PROMPTS_DIR.glob("*.md"):
        shutil.copy2(p, backup_dir / p.name)
    return backup_dir


def _restore_prompts(backup_dir: Path) -> None:
    for p in backup_dir.glob("*.md"):
        shutil.copy2(p, PROMPTS_DIR / p.name)


def _write_prompt(name: str, content: str) -> None:
    (PROMPTS_DIR / f"{name}.md").write_text(content, encoding="utf-8")


# ---------- eval log ----------

def _append_log(entry: dict) -> None:
    data = []
    if EVAL_LOG.exists():
        try:
            data = json.loads(EVAL_LOG.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = [data]
        except Exception:
            data = []
    data.append(entry)
    EVAL_LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- main loop ----------

VALID_PROMPTS = {"planner", "scout", "analyst", "bisociator", "summarizer"}


async def eval_loop(query: str, max_iterations: int = 2) -> tuple[Report, dict]:
    """Run research, evaluate, optionally iterate prompts, compare, rollback if worse.

    Returns: (best_report, final_evaluation_entry)
    """
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    print(f"\n[eval-loop] === START run={run_id}  query={query!r}  max_iter={max_iterations} ===")

    # Iteration 1
    t0 = time.time()
    report = await run_research(query, progress=lambda ev, m: print(f"  [{ev}] {m}"))
    print(f"[eval-loop] run 1 done in {time.time()-t0:.1f}s — {len(report.blocks)} blocks, {len(report.connections)} conns")

    try:
        eval_1 = await evaluate_report(report)
    except Exception as err:
        print(f"[eval-loop] evaluate_report FAILED: {err}")
        entry = {
            "run_id": run_id, "query": query, "iterations": 1,
            "error": f"eval failed: {err}", "total_1": None,
        }
        _append_log(entry)
        return report, entry

    print(f"[eval-loop] iter 1 total={eval_1['total']}/70  low={[c['name'] for c in eval_1['low_scores']]}")

    best_report = report
    best_eval = eval_1
    changes_log: list[dict] = []

    for iteration in range(2, max_iterations + 1):
        low = eval_1["low_scores"]
        if not low:
            print("[eval-loop] no low scores — stopping")
            break

        backup_dir = _backup_prompts(f"{run_id}-iter{iteration-1}")
        print(f"[eval-loop] backed up prompts to {backup_dir}")

        patched_any = False
        for crit_dict in low:
            target = crit_dict.get("target_prompt", "").strip()
            if target not in VALID_PROMPTS:
                print(f"[eval-loop] skip criterion {crit_dict['name']} — invalid target {target!r}")
                continue
            pfile = PROMPTS_DIR / f"{target}.md"
            if not pfile.exists():
                print(f"[eval-loop] prompt file {pfile} not found")
                continue
            current = pfile.read_text(encoding="utf-8")
            crit_obj = CriterionScore.model_validate(crit_dict)
            patch = await propose_prompt_patch(target, current, crit_obj)
            if patch is None:
                continue
            _write_prompt(target, patch.new_content)
            changes_log.append({
                "iteration": iteration,
                "criterion": crit_dict["name"],
                "prompt": target,
                "note": patch.change_note,
            })
            patched_any = True
            print(f"[eval-loop] patched {target}.md — {patch.change_note[:140]}")

        if not patched_any:
            print("[eval-loop] no prompts patched — stopping")
            break

        # Rerun
        try:
            t0 = time.time()
            report_v = await run_research(query, progress=lambda ev, m: print(f"  [{ev}] {m}"))
            print(f"[eval-loop] run {iteration} done in {time.time()-t0:.1f}s")
            eval_v = await evaluate_report(report_v)
            print(f"[eval-loop] iter {iteration} total={eval_v['total']}/70 (prev best {best_eval['total']})")
        except Exception as err:
            print(f"[eval-loop] rerun {iteration} FAILED: {err} — rollback")
            _restore_prompts(backup_dir)
            break

        if eval_v["total"] > best_eval["total"]:
            print(f"[eval-loop] KEEP — iter {iteration} better ({eval_v['total']} > {best_eval['total']})")
            best_report = report_v
            best_eval = eval_v
            eval_1 = eval_v  # feed into next iter
        else:
            print(f"[eval-loop] ROLLBACK — iter {iteration} not better ({eval_v['total']} ≤ {best_eval['total']})")
            _restore_prompts(backup_dir)
            break

    # Log
    entry = {
        "run_id": run_id,
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "iterations_completed": max_iterations if best_eval is not eval_1 or max_iterations == 1 else None,
        "final_total": best_eval["total"],
        "final_scores": {
            k: v["score"] for k, v in best_eval["scores"].items()
            if isinstance(v, dict) and "score" in v
        },
        "full_scores": best_eval["scores"],
        "prompt_changes": changes_log,
    }
    _append_log(entry)
    print(f"[eval-loop] === DONE run={run_id} final={best_eval['total']}/70 ===\n")
    return best_report, entry
