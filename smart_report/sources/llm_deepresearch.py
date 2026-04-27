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

# Perplexity sonar-deep-research — distinct from sonar-pro (which is sync
# and used for quick LLM-with-web responses). The deep-research model
# does multi-step planning + browsing + synthesis, takes 5-15 min.
PERPLEXITY_DR_MODELS: dict[str, tuple[str, float, int, int]] = {
    "deep": ("perplexity/sonar-deep-research", 0.10, 5, 15),
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


def submit_perplexity_deep_research(
    question: str,
    *,
    mode: str = "deep",
    session_id: Optional[str] = None,
    store: Optional[Any] = None,
) -> LLMResearchTaskInfo:
    """Same async pattern as OpenAI DR but for Perplexity sonar-deep-research.

    Submit returns task_id immediately; background asyncio.Task runs the
    long OpenRouter call (5-15 min). Result persists to session.source_reports
    on completion.
    """
    if mode not in PERPLEXITY_DR_MODELS:
        raise ValueError(f"unknown perplexity DR mode: {mode!r}")
    if not question or not question.strip():
        raise ValueError("question is required")
    model_id, est_cost, eta_lo, eta_hi = PERPLEXITY_DR_MODELS[mode]
    task_id = str(uuid.uuid4())
    _TASKS[task_id] = {
        "state": "running",
        "service": "perplexity",
        "mode": mode,
        "model": model_id,
        "started_at": time.time(),
        "result": None,
        "error": None,
    }
    bg = asyncio.create_task(
        _run_llm_dr(task_id, question, model_id, "perplexity", "perplexity", session_id, store)
    )
    _TASKS[task_id]["asyncio_task"] = bg
    return LLMResearchTaskInfo(
        task_id=task_id, service="perplexity", mode=mode,
        cost_usd=est_cost, eta_min_low=eta_lo, eta_min_high=eta_hi,
    )


def submit_openai_deep_research(
    question: str,
    *,
    mode: str = "mini",
    session_id: Optional[str] = None,
    store: Optional[Any] = None,
) -> LLMResearchTaskInfo:
    """Kick off OpenAI Deep Research as a background asyncio task.

    Returns a synthetic task_id immediately. The frontend polls
    `get_llm_research_task(task_id)` until state is completed/failed.

    `session_id` + `store`: when both passed, the background task will
    persist the completed AutoDRResult directly to the session's
    `source_reports` (and remove the entry from `pending_dr_jobs`) on
    completion — so a container restart AFTER the OpenAI API call
    returned doesn't lose the user's paid-for result. Restart DURING
    the API call is still lossy (would need OpenAI direct API + a
    persistent response_id to fully recover).
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
    bg = asyncio.create_task(
        _run_llm_dr(task_id, question, model_id, "openai", "openai_dr", session_id, store)
    )
    _TASKS[task_id]["asyncio_task"] = bg  # so cancel_openai_dr_task can task.cancel()
    return LLMResearchTaskInfo(
        task_id=task_id,
        service="openai",
        mode=mode,
        cost_usd=est_cost,
        eta_min_low=eta_lo,
        eta_min_high=eta_hi,
    )


async def _run_llm_dr(
    task_id: str,
    question: str,
    model_id: str,
    service: str,
    detected_tool: str,
    session_id: Optional[str],
    store: Optional[Any],
) -> None:
    """Background runner — calls OpenRouter, writes result to registry.

    Generic over service (openai / perplexity / future). Persists result
    to session.source_reports on completion (PG-backed for restart-safety
    after the API call returns).
    """
    from smart_report.llm import call_json
    from smart_report.models import UploadedMarkdown
    from smart_report.sources.auto_dr import AutoDRResult, _USD_RUB_RATE

    started = time.time()
    try:
        # OpenRouter's deep-research models (openai/o3-deep-research,
        # perplexity/sonar-deep-research, etc.) block the call for 5-30 min
        # while the upstream agent loop runs. Any timeout error lands in
        # `except` below.
        result = await call_json(
            role=f"auto_dr_{service}",
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
        )
    except Exception as e:
        _TASKS[task_id]["state"] = "failed"
        _TASKS[task_id]["error"] = f"{type(e).__name__}: {e}"
        _TASKS[task_id]["finished_at"] = time.time()
        _logger.warning("%s DR task %s failed: %s", service, task_id, e)
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
        filename=f"auto_dr_{service}_{task_id[:8]}.md",
        content=md,
        detected_tool=detected_tool,  # type: ignore[arg-type]
        word_count=len(md.split()),
    )
    # Citation count: try a "Sources" section first, then fall back to
    # counting unique URL references. Both OpenAI DR and Perplexity vary
    # in format (inline / footnote / References block).
    import re
    src_match = re.search(
        r"##\s*(Sources?|References|Bibliography|Источники)\s*$(.+)",
        md, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if src_match:
        sources_count = len(re.findall(r"^\s*\d+\.\s", src_match.group(2), re.MULTILINE))
    else:
        urls = set(re.findall(r"https?://[^\s\)\]\>]+", md))
        sources_count = len(urls)

    auto_dr_result = AutoDRResult(
        upload=upload,
        service=service,
        cost_usd=cost_usd,
        cost_rub=cost_rub,
        source_count=sources_count,
        notes=f"backend={service}_deep_research model={model_id} duration_s={int(time.time()-started)}",
    )
    _TASKS[task_id]["state"] = "completed"
    _TASKS[task_id]["result"] = auto_dr_result
    _TASKS[task_id]["finished_at"] = time.time()
    _logger.info(
        "%s DR task %s completed in %ds (cost $%.2f)",
        service, task_id, int(time.time()-started), cost_usd,
    )

    # Persistence shortcut: if caller passed session_id+store, write the
    # upload to the session immediately. This means a container restart
    # AFTER the OpenAI call returned but BEFORE the user polls won't lose
    # the result — it's already in PostgreSQL. Idempotent: status endpoint
    # also adds it on poll if not yet there, so double-write is harmless.
    if session_id and store is not None:
        try:
            session = store.get(session_id)
            already = any(
                u.filename == upload.filename for u in (session.source_reports or [])
            )
            if not already:
                session.source_reports = list(session.source_reports or []) + [upload]
                if session.status in {"created", "prompt_generated"}:
                    session.status = "reports_uploaded"
                session.pending_dr_jobs = [
                    j for j in (session.pending_dr_jobs or [])
                    if j.get("task_id") != task_id
                ]
                store.update(session)
                _logger.info(
                    "openai DR task %s persisted to session %s", task_id, session_id,
                )
        except Exception as e:
            _logger.warning(
                "openai DR task %s: failed to persist to session %s: %s",
                task_id, session_id, e,
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


def cancel_openai_dr_task(task_id: str) -> bool:
    """Best-effort cancel: marks state cancelled + .cancel()s the asyncio task.

    Returns True if the task was found and cancellation was attempted.
    Returns False if the task_id is unknown.

    IMPORTANT: cancellation does NOT refund the OpenAI API call. If the
    request already reached OpenRouter/OpenAI, we paid for whatever
    tokens were generated. Cancellation only ensures we discard the
    eventual result and stop showing 'running' to the user.
    """
    t = _TASKS.get(task_id)
    if t is None:
        return False
    # Only cancel if still in flight; completed/failed are terminal.
    if t.get("state") not in ("running", "queued"):
        return True  # idempotent
    bg = t.get("asyncio_task")
    if bg is not None and not bg.done():
        try:
            bg.cancel()
        except Exception as e:
            _logger.warning("openai DR task %s: bg.cancel() raised: %s", task_id, e)
    t["state"] = "cancelled"
    t["finished_at"] = time.time()
    t["error"] = "cancelled by user"
    return True
