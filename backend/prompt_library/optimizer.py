"""Nightly APO (Automatic Prompt Optimization) scheduler and utilities."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from tzlocal import get_localzone_name

from backend.config import settings

PERFORMANCE_LOG = Path("prompt_library/knowledge_base/performance_log.jsonl")
PROMPTS_DIR = Path("prompts")
FEW_SHOT_DIR = Path("prompt_library/knowledge_base/few_shot_examples")

SCORE_THRESHOLD = 7.0
NUM_VARIANTS = 3
NUM_EXAMPLES = 5
OPTIMIZER_MODEL = "openai/gpt-4o-mini"
SCHEDULER_TIMEZONE = get_localzone_name()


def _coerce_critic_score(raw_score: Any) -> float | None:
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return None

    if score <= 1.0:
        score *= 10.0
    return max(0.0, min(10.0, score))


def log_performance(
    task_id: str,
    techniques: list[str],
    score: float,
    metadata: dict | None = None,
) -> None:
    critic_score = _coerce_critic_score(score)
    entry = {
        "task_id": task_id,
        "techniques": techniques,
        "score": score,
        "critic_score": critic_score if critic_score is not None else score,
        "metadata": metadata or {},
    }
    PERFORMANCE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PERFORMANCE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.debug(f"Logged performance: task={task_id}, critic_score={entry['critic_score']}")


def get_best_techniques(domain: str, top_k: int = 5) -> list[str]:
    if not PERFORMANCE_LOG.exists():
        return []

    scores: dict[str, list[float]] = {}
    with PERFORMANCE_LOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            score = _coerce_critic_score(entry.get("critic_score", entry.get("score")))
            if score is None:
                continue
            meta = entry.get("metadata", {})
            if meta.get("domain") == domain or not domain:
                for tech in entry.get("techniques", []):
                    scores.setdefault(tech, []).append(score)

    averages = {tech: sum(values) / len(values) for tech, values in scores.items()}
    return sorted(averages, key=averages.get, reverse=True)[:top_k]  # type: ignore[arg-type]


def _read_underperforming_prompts() -> list[tuple[str, float]]:
    if not PERFORMANCE_LOG.exists():
        return []

    grouped: dict[str, list[float]] = defaultdict(list)
    with PERFORMANCE_LOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            metadata = entry.get("metadata", {})
            prompt_file = metadata.get("prompt_file", "")
            if not prompt_file:
                continue

            score = _coerce_critic_score(entry.get("critic_score", entry.get("score")))
            if score is None:
                continue

            grouped[Path(prompt_file).stem].append(score)

    return [
        (prompt_stem, statistics.mean(scores))
        for prompt_stem, scores in grouped.items()
        if statistics.mean(scores) < SCORE_THRESHOLD
    ]


async def _llm_call(
    system: str,
    user: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.4,
    response_format: dict[str, str] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": OPTIMIZER_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://smart-report.ai",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


def _load_examples(n: int = NUM_EXAMPLES) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    if not FEW_SHOT_DIR.exists():
        return examples

    for path in sorted(FEW_SHOT_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        for example in payload.get("examples", []):
            if isinstance(example, dict):
                examples.append(
                    {
                        "type": payload.get("type", path.stem),
                        "input": example.get("input", ""),
                        "output": example.get("output", {}),
                    }
                )
            if len(examples) >= n:
                return examples

    return examples[:n]


async def _generate_variants(current_prompt: str, avg_score: float) -> list[str]:
    system = (
        "You optimize system prompts for an analytical reporting pipeline. "
        "Return JSON with a single key 'variants' containing exactly 3 improved prompt strings."
    )
    user = (
        f"This prompt underperformed with an average critic_score of {avg_score:.2f}/10.\n\n"
        f"Current prompt:\n```text\n{current_prompt}\n```\n\n"
        "Generate 3 stronger variants focused on clearer instructions, stricter evidence standards, "
        "and more structured output requirements."
    )
    raw = await _llm_call(
        system,
        user,
        max_tokens=4096,
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("APO variant generation returned invalid JSON")
        return []

    variants = [variant.strip() for variant in parsed.get("variants", []) if isinstance(variant, str) and variant.strip()]
    return variants[:NUM_VARIANTS]


async def _score_variant(variant: str, examples: list[dict[str, Any]]) -> float:
    if not examples:
        return SCORE_THRESHOLD

    scores: list[float] = []
    system = (
        "You are a strict evaluator for prompt quality. "
        "Score how well the candidate prompt would drive a high-quality critic-reviewed report. "
        "Return JSON with a numeric key 'critic_score' from 0 to 10."
    )

    for example in examples[:NUM_EXAMPLES]:
        user = (
            "Evaluate the candidate prompt against this representative task example.\n\n"
            f"Example:\n```json\n{json.dumps(example, ensure_ascii=False)}\n```\n\n"
            f"Candidate prompt:\n```text\n{variant}\n```\n"
        )
        try:
            raw = await _llm_call(
                system,
                user,
                max_tokens=64,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(raw)
            score = _coerce_critic_score(parsed.get("critic_score"))
            if score is not None:
                scores.append(score)
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(f"Variant scoring failed: {exc}")

    return statistics.mean(scores) if scores else SCORE_THRESHOLD


def _select_best_variant(scored_variants: list[tuple[str, float]]) -> tuple[str, float]:
    if not scored_variants:
        raise ValueError("No scored variants supplied")
    return max(scored_variants, key=lambda item: item[1])


def _log_optimizer_result(
    prompt_stem: str,
    previous_score: float,
    best_score: float,
    applied: bool,
) -> None:
    delta = round(best_score - previous_score, 4)
    PERFORMANCE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "task_id": f"apo::{prompt_stem}",
        "techniques": [],
        "critic_score": round(best_score, 4),
        "metadata": {
            "prompt_file": prompt_stem,
            "optimizer_run": True,
            "previous_avg_critic_score": round(previous_score, 4),
            "new_avg_critic_score": round(best_score, 4),
            "improvement_delta": delta,
            "applied": applied,
        },
    }
    with PERFORMANCE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def _optimize_prompt(prompt_stem: str, avg_score: float) -> None:
    prompt_path = PROMPTS_DIR / f"{prompt_stem}.txt"
    if not prompt_path.exists():
        logger.warning(f"APO: prompt file not found: {prompt_path}")
        return

    current_prompt = prompt_path.read_text(encoding="utf-8")
    logger.info(f"APO: optimizing '{prompt_stem}' (avg critic_score={avg_score:.2f})")

    try:
        variants = await _generate_variants(current_prompt, avg_score)
    except Exception as exc:
        logger.error(f"APO: variant generation failed for '{prompt_stem}': {exc}")
        return

    if not variants:
        logger.warning(f"APO: no variants generated for '{prompt_stem}'")
        return

    examples = _load_examples(NUM_EXAMPLES)
    scored_variants: list[tuple[str, float]] = []
    for variant in variants[:NUM_VARIANTS]:
        score = await _score_variant(variant, examples)
        scored_variants.append((variant, score))
        logger.debug(f"APO: variant for '{prompt_stem}' scored {score:.2f}/10")

    best_variant, best_score = _select_best_variant(scored_variants)
    applied = best_score > avg_score

    if applied:
        prompt_path.write_text(best_variant, encoding="utf-8")
        logger.info(
            f"APO: updated '{prompt_stem}' ({avg_score:.2f} -> {best_score:.2f}, "
            f"delta={best_score - avg_score:+.2f})"
        )
    else:
        logger.info(
            f"APO: no better variant for '{prompt_stem}' "
            f"(current={avg_score:.2f}, best={best_score:.2f})"
        )

    _log_optimizer_result(prompt_stem, avg_score, best_score, applied)


async def run_apo_optimization() -> None:
    logger.info("APO nightly optimization started")
    underperforming = _read_underperforming_prompts()
    if not underperforming:
        logger.info("APO: no underperforming prompts found")
        return

    logger.info(
        f"APO: {len(underperforming)} prompts below threshold "
        f"({SCORE_THRESHOLD:.1f}): {[prompt for prompt, _ in underperforming]}"
    )
    for prompt_stem, avg_score in underperforming:
        try:
            await _optimize_prompt(prompt_stem, avg_score)
        except Exception as exc:  # pragma: no cover - scheduler safety
            logger.error(f"APO: failed for '{prompt_stem}': {exc}")
    logger.info("APO nightly optimization complete")


_scheduler = AsyncIOScheduler(timezone=SCHEDULER_TIMEZONE)
_scheduler.add_job(
    run_apo_optimization,
    CronTrigger(hour=3, minute=0, timezone=SCHEDULER_TIMEZONE),
    id="apo_nightly",
    replace_existing=True,
)


def start_scheduler() -> None:
    if not _scheduler.running:
        _scheduler.start()
        logger.info(f"APO scheduler started (job: daily 03:00 {SCHEDULER_TIMEZONE})")


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APO scheduler stopped")
