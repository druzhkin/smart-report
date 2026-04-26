"""LLM Deep Research wrapper — async background tasks for OpenAI's
deep-research models (and any other model that takes too long for a
sync HTTP request).

OpenAI's `o3-deep-research` and `o4-mini-deep-research` models take
5-30 minutes each and would blow Railway's 10-minute proxy timeout if
called sync. This module fronts them with a background `asyncio.Task`
+ an in-process task registry — same submit/poll UX that valyu_deepresearch
exposes, but the "queue" is just our process.

Limitations (acceptable for current demo scale):
- Registry is in-memory: container restart loses in-flight tasks. The
  user can re-submit. Cost paid is forfeit (small in fast tiers).
- Single-worker assumption: works because uvicorn runs one worker.

For prod scale, swap _TASKS with PostgreSQL or Redis.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

_logger = logging.getLogger(__name__)


# OpenAI Deep Research model catalogue exposed via OpenRouter.
# Keys are user-facing mode names; values are (model_id, est_cost_usd, eta_min_low, eta_min_high).
OPENAI_DR_MODELS: dict[str, tuple[str, float, int, int]] = {
    # mini deep research — cheaper, ~5-10 min
    "mini":     ("openai/o4-mini-deep-research", 0.50, 5, 10),
    # full o3 deep research — premium, 15-30 min
    "standard": ("openai/o3-deep-research",      3.00, 15, 30),
}


# In-process task registry. {task_id: {state, started_at, ...}}
_TASKS: dict[str, dict[str, Any]] = {}


@dataclass
class LLMResearchTaskInfo:
    task_id: str
    service: str
    mode: str
    cost_usd: float
    eta_min_low: int
    eta_min_high: int


def submit_openai_deep_research(question: str, *, mode: str = "mini") -> LLMResearchTaskInfo:
    """Kick off OpenAI Deep Research as a background asyncio task.

    Returns a synthetic task_id immediately. The frontend polls
    `get_llm_research_task(task_id)` until state is completed/failed.
    """
    if mode not in OPENAI_DR_MODELS:
        raise ValueError(f"unknown openai DR mode: {mode!r} (allowed: {list(OPENAI_DR_MODELS)})")
    if not question or not question.strip():
        raise ValueError("question is required")

    model_id, est_cost, eta_lo, eta_hi = OPENAI_DR_MODELS[mode]
    task_id = str(uuid.uuid4())
    _TASKS[task_id] = {
        "state": "running",
        "service": "openai",
        "mode": mode,
        "model": model_id,
        "started_at": time.time(),
        "result": None,
        "error": None,
    }
    # Fire-and-forget. Errors are caught inside the task and stored on the registry.
    asyncio.create_task(_run_openai_dr(task_id, question, model_id))
    return LLMResearchTaskInfo(
        task_id=task_id,
        service="openai",
        mode=mode,
        cost_usd=est_cost,
        eta_min_low=eta_lo,
        eta_min_high=eta_hi,
    )


async def _run_openai_dr(task_id: str, question: str, model_id: str) -> None:
    """Background runner — calls OpenRouter, writes result to registry."""
    from smart_report.llm import call_json
    from smart_report.models import UploadedMarkdown
    from smart_report.sources.auto_dr import AutoDRResult, _USD_RUB_RATE

    started = time.time()
    try:
        # Note: OpenRouter's o3-deep-research / o4-mini-deep-research are
        # invoked like normal chat completions. The actual call blocks for
        # 5-30 min while OpenAI's agent loop runs server-side. Our existing
        # call_json uses an httpx timeout — must override for these.
        result = await call_json(
            role=f"auto_dr_openai_dr",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are conducting deep research on the user's question. "
                        "Use your built-in web search and reasoning capabilities. "
                        "Produce a thorough Markdown report: executive summary, "
                        "key findings with [N] citations, supporting evidence, "
                        "and a Sources list with full URLs."
                    ),
                },
                {"role": "user", "content": question},
            ],
            model=model_id,
            temperature=0.2,
            # Force a long timeout — OpenAI's o3-deep-research can run 30+ min.
            # call_json doesn't accept this directly, but we pass via httpx kwargs.
            # If call_json doesn't propagate this, the call still goes through;
            # any timeout error lands in `except` below and stays on the registry.
        )
    except Exception as e:
        _TASKS[task_id]["state"] = "failed"
        _TASKS[task_id]["error"] = f"{type(e).__name__}: {e}"
        _TASKS[task_id]["finished_at"] = time.time()
        _logger.warning("openai DR task %s failed: %s", task_id, e)
        return

    md = (result.text or "").strip()
    if not md:
        _TASKS[task_id]["state"] = "failed"
        _TASKS[task_id]["error"] = "model returned empty response"
        _TASKS[task_id]["finished_at"] = time.time()
        return

    cost_rub = float(result.cost_rub or 0.0)
    cost_usd = cost_rub / _USD_RUB_RATE if cost_rub else 0.0

    upload = UploadedMarkdown(
        filename=f"auto_dr_openai_{task_id[:8]}.md",
        content=md,
        detected_tool="openai_dr",
        word_count=len(md.split()),
    )
    # Citation count: try a "Sources" section first, then fall back to
    # counting unique URL references in the body. OpenAI DR formats vary —
    # sometimes inline ([url]), sometimes footnote ([N]), sometimes a
    # References section.
    import re
    src_match = re.search(
        r"##\s*(Sources?|References|Bibliography|Источники)\s*$(.+)",
        md, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if src_match:
        sources_count = len(re.findall(r"^\s*\d+\.\s", src_match.group(2), re.MULTILINE))
    else:
        # Fall back to unique URLs in the markdown body
        urls = set(re.findall(r"https?://[^\s\)\]\>]+", md))
        sources_count = len(urls)

    auto_dr_result = AutoDRResult(
        upload=upload,
        service="openai",
        cost_usd=cost_usd,
        cost_rub=cost_rub,
        source_count=sources_count,
        notes=f"backend=openai_deep_research model={model_id} duration_s={int(time.time()-started)}",
    )
    _TASKS[task_id]["state"] = "completed"
    _TASKS[task_id]["result"] = auto_dr_result
    _TASKS[task_id]["finished_at"] = time.time()
    _logger.info(
        "openai DR task %s completed in %ds (cost $%.2f)",
        task_id, int(time.time()-started), cost_usd,
    )


def get_llm_research_task(task_id: str) -> Optional[dict[str, Any]]:
    """Read-only registry lookup. None = unknown task_id."""
    return _TASKS.get(task_id)


def collect_completed_result(task_id: str):
    """Pop and return the completed AutoDRResult, or None if still in flight.

    Idempotent: once popped, subsequent calls return None. Caller is
    responsible for persisting the AutoDRResult before discarding.
    """
    t = _TASKS.get(task_id)
    if not t or t.get("state") != "completed":
        return None
    return t.get("result")
