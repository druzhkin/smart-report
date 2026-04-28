"""LLM Deep Research wrapper — streaming-resilient async tasks via OpenRouter.

OpenRouter doesn't expose a durable response_id pattern (you can't poll
for a completion that finished while your connection was dead). The
trick we use to be restart-resilient: STREAM the completion and flush
the accumulated partial content to PostgreSQL every few seconds. If
the container dies mid-stream, the partial is durable in
`session.pending_dr_jobs[i].partial_content` and the user can:
  * accept the partial as-is (insert into source_reports), or
  * resubmit a continuation prompt to finish.

State lives in **PostgreSQL** (via V4SessionStore), not in-memory
`_TASKS` — that was the old fragile pattern. We keep an in-memory
asyncio.Task reference only for cancel; everything else reads/writes
the session.

Per-job entry shape inside `session.pending_dr_jobs`:
    {
      "task_id":         "<uuid>",
      "service":         "openai" | "perplexity",
      "mode":            "<mode>",
      "model":           "openai/o4-mini-deep-research" | ...,
      "cost_usd":        <float>,
      "cost_rub":        <float>,
      "submitted_at":    <unix_ts>,
      "state":           "running" | "completed" | "failed" | "cancelled" | "interrupted_with_partial",
      "partial_content": "<accumulated markdown>",
      "partial_chars":   <int>,
      "last_progress_at":<unix_ts>,
      "error":           "<str>" | None,
      "interrupted_at":  <unix_ts> | None,
    }
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import httpx

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model catalogues
# ---------------------------------------------------------------------------

# OpenAI Deep Research. Model id stays in OpenRouter form ('openai/...');
# the streamer strips the prefix when routing direct to OpenAI.
OPENAI_DR_MODELS: dict[str, tuple[str, float, int, int]] = {
    "mini":     ("openai/o4-mini-deep-research", 0.50, 5, 10),
    "standard": ("openai/o3-deep-research",      3.00, 15, 30),
}

# Per-token prices for direct OpenAI Responses API billing (cost computed
# from usage tokens at completion). OpenRouter path returns its own
# `usage.cost` and skips this table. Source: OpenAI pricing page, 2026-04.
OPENAI_DR_TOKEN_PRICES_USD: dict[str, tuple[float, float]] = {
    # (input_per_token, output_per_token)
    "o4-mini-deep-research": (2.00 / 1_000_000, 8.00 / 1_000_000),
    "o3-deep-research":      (10.00 / 1_000_000, 40.00 / 1_000_000),
}

# Perplexity sonar-deep-research via OpenRouter.
# Pricing 2026-04 (docs.perplexity.ai/getting-started/pricing): token-based
# ($2/$8 per 1M in/out + $5/1k searches + $6-$14 per 1k requests by context
# size). A typical deep call lands $0.50-$3.00. We charge a $1.00 estimate
# upfront; _finalise reconciles to the real OpenRouter usage.cost when the
# stream completes. Underestimating means the user can submit, then the
# debit grows post-completion — by design.
PERPLEXITY_DR_MODELS: dict[str, tuple[str, float, int, int]] = {
    "deep": ("perplexity/sonar-deep-research", 1.00, 5, 15),
}


# In-process asyncio.Task references — purely for cancel(), nothing else.
# State of truth is the session in PostgreSQL.
_LIVE_TASKS: dict[str, asyncio.Task] = {}


@dataclass
class LLMResearchTaskInfo:
    task_id: str
    service: str
    mode: str
    cost_usd: float
    eta_min_low: int
    eta_min_high: int


# ---------------------------------------------------------------------------
# Submit functions
# ---------------------------------------------------------------------------


def submit_openai_deep_research(
    question: str,
    *,
    mode: str = "mini",
    session_id: Optional[str] = None,
    store: Optional[Any] = None,
) -> LLMResearchTaskInfo:
    if mode not in OPENAI_DR_MODELS:
        raise ValueError(f"unknown openai DR mode: {mode!r}")
    if not question or not question.strip():
        raise ValueError("question is required")
    if session_id is None or store is None:
        raise ValueError("session_id and store are required for durable LLM DR")
    model_id, est_cost, eta_lo, eta_hi = OPENAI_DR_MODELS[mode]
    return _submit_llm_dr(
        question, service="openai", model_id=model_id, mode=mode,
        cost_usd=est_cost, eta_lo=eta_lo, eta_hi=eta_hi,
        session_id=session_id, store=store, detected_tool="openai_dr",
    )


def submit_perplexity_deep_research(
    question: str,
    *,
    mode: str = "deep",
    session_id: Optional[str] = None,
    store: Optional[Any] = None,
) -> LLMResearchTaskInfo:
    if mode not in PERPLEXITY_DR_MODELS:
        raise ValueError(f"unknown perplexity DR mode: {mode!r}")
    if not question or not question.strip():
        raise ValueError("question is required")
    if session_id is None or store is None:
        raise ValueError("session_id and store are required for durable LLM DR")
    model_id, est_cost, eta_lo, eta_hi = PERPLEXITY_DR_MODELS[mode]
    return _submit_llm_dr(
        question, service="perplexity", model_id=model_id, mode=mode,
        cost_usd=est_cost, eta_lo=eta_lo, eta_hi=eta_hi,
        session_id=session_id, store=store, detected_tool="perplexity",
    )


def _submit_llm_dr(
    question: str, *,
    service: str, model_id: str, mode: str,
    cost_usd: float, eta_lo: int, eta_hi: int,
    session_id: str, store: Any, detected_tool: str,
) -> LLMResearchTaskInfo:
    task_id = str(uuid.uuid4())
    print(f"[dr-submit] {service}/{mode} task_id={task_id} session={session_id} model={model_id}", flush=True)
    # Pre-populate pending_dr_jobs SYNCHRONOUSLY before scheduling the
    # asyncio task. Otherwise the streaming runner's first flush races
    # against the endpoint's separate write and can silently no-op
    # ("job not in pending_dr_jobs"). Idempotent: if endpoint also adds
    # an entry with the same task_id, the dedupe in callers handles it.
    cost_rub = round(cost_usd * _USD_RUB_RATE, 4)
    try:
        session = store.get(session_id)
        existing_ids = {j.get("task_id") for j in (session.pending_dr_jobs or [])}
        if task_id not in existing_ids:
            session.pending_dr_jobs = list(session.pending_dr_jobs or []) + [{
                "task_id": task_id,
                "service": service,
                "mode": mode,
                "model": model_id,
                "cost_usd": cost_usd,
                "cost_rub": cost_rub,
                "submitted_at": time.time(),
                "state": "running",
                "partial_content": "",
                "partial_chars": 0,
                "last_progress_at": time.time(),
            }]
            store.update(session)
    except Exception as e:
        _logger.warning("submit pre-populate failed for %s: %s", task_id, e)

    bg = asyncio.create_task(
        _run_streaming_dr(
            task_id=task_id, question=question, model_id=model_id,
            service=service, detected_tool=detected_tool,
            session_id=session_id, store=store,
        )
    )
    _LIVE_TASKS[task_id] = bg
    return LLMResearchTaskInfo(
        task_id=task_id, service=service, mode=mode,
        cost_usd=cost_usd, eta_min_low=eta_lo, eta_min_high=eta_hi,
    )


# ---------------------------------------------------------------------------
# Streaming runner
# ---------------------------------------------------------------------------


_FLUSH_EVERY_SECONDS = 5.0
_FLUSH_EVERY_CHARS = 1000
from ..config import USD_RUB_RATE as _USD_RUB_RATE  # single source of truth
_AUTO_RESUBMIT_PARTIAL_THRESHOLD = 200  # interrupted tasks with fewer chars are auto-restarted on container boot


async def _run_streaming_dr(
    *,
    task_id: str,
    question: str,
    model_id: str,
    service: str,
    detected_tool: str,
    session_id: str,
    store: Any,
) -> None:
    """Background runner: streams OpenRouter response + flushes partial to PG.

    Restart-resilient: every ~5s or ~1000 chars we write the accumulated
    text to `session.pending_dr_jobs[i].partial_content`. On any failure
    (network, timeout, cancel), the partial stays. Startup hook marks
    such tasks `interrupted_with_partial` for user-visible recovery.
    """
    started = time.time()
    accumulated: list[str] = []
    cost_usd_total: float = 0.0
    last_flush_at = 0.0
    last_flush_chars = 0
    full_text = ""
    print(f"[dr-run] {service} task_id={task_id} starting stream model={model_id}", flush=True)

    def _len() -> int:
        return sum(len(c) for c in accumulated)

    async def _flush(*, force: bool = False) -> None:
        nonlocal last_flush_at, last_flush_chars
        now = time.time()
        cur_chars = _len()
        should = (
            force
            or (now - last_flush_at) >= _FLUSH_EVERY_SECONDS
            or (cur_chars - last_flush_chars) >= _FLUSH_EVERY_CHARS
        )
        if not should:
            return
        text = "".join(accumulated)
        try:
            session = store.get(session_id)
            for j in (session.pending_dr_jobs or []):
                if j.get("task_id") == task_id:
                    j["partial_content"] = text
                    j["partial_chars"] = len(text)
                    j["last_progress_at"] = now
                    break
            store.update(session)
            last_flush_at = now
            last_flush_chars = cur_chars
        except Exception as e:
            _logger.warning("dr task %s: flush failed: %s", task_id, e)

    async def _finalise(state: str, *, error: Optional[str] = None) -> None:
        """Write terminal state. For 'completed', also append to source_reports.

        Reconciles billed cost: at submit we debited an estimate from
        OPENAI_DR_MODELS / PERPLEXITY_DR_MODELS. The streamer captures the
        actual cost (OpenRouter `usage.cost`, or token×price for OpenAI
        direct). At terminal state we replace the job's stored estimate
        with the actual and apply the delta to session.total_cost_rub —
        without this the user is billed the estimate forever even though
        the real cost is known. Reconciliation only fires when
        cost_usd_total > 0 (provider returned usage); otherwise we keep
        the estimate to stay conservative.
        """
        from smart_report.models import UploadedMarkdown

        text = "".join(accumulated).strip()
        try:
            session = store.get(session_id)
        except Exception as e:
            _logger.warning("dr task %s: finalise getSession failed: %s", task_id, e)
            return

        # Find the job entry
        job = None
        for j in (session.pending_dr_jobs or []):
            if j.get("task_id") == task_id:
                job = j
                break
        if job is None:
            _logger.warning("dr task %s: finalise — job not in pending_dr_jobs", task_id)
            return

        # Reconcile billed cost against actual reported cost.
        # Applies on every terminal state (completed/failed/cancelled/
        # interrupted_with_partial) so partial work that consumed tokens
        # is also billed accurately.
        if cost_usd_total > 0:
            est_usd = float(job.get("cost_usd") or 0.0)
            delta_usd = cost_usd_total - est_usd
            actual_rub = round(cost_usd_total * _USD_RUB_RATE, 4)
            delta_rub = round(delta_usd * _USD_RUB_RATE, 4)
            job["cost_usd"] = round(cost_usd_total, 6)
            job["cost_rub"] = actual_rub
            job["cost_estimate_usd"] = est_usd  # keep audit trail
            session.total_cost_rub = round(
                float(session.total_cost_rub or 0.0) + delta_rub, 4
            )
            print(
                f"[dr-cost-reconcile] task_id={task_id} service={service} "
                f"est=${est_usd:.4f} actual=${cost_usd_total:.4f} "
                f"delta=${delta_usd:+.4f} (₽{delta_rub:+.2f})",
                flush=True,
            )

        if state == "completed" and text:
            # Build upload + add to source_reports + remove from pending
            filename = f"auto_dr_{service}_{task_id[:8]}.md"
            already = any(u.filename == filename for u in (session.source_reports or []))
            if not already:
                upload = UploadedMarkdown(
                    filename=filename,
                    content=text,
                    detected_tool=detected_tool,  # type: ignore[arg-type]
                    word_count=len(text.split()),
                )
                session.source_reports = list(session.source_reports or []) + [upload]
                if session.status in {"created", "prompt_generated"}:
                    session.status = "reports_uploaded"
            # Remove from pending
            session.pending_dr_jobs = [
                j for j in (session.pending_dr_jobs or []) if j.get("task_id") != task_id
            ]
        else:
            # Failed/cancelled/interrupted — keep job entry with terminal state
            job["state"] = state
            job["partial_content"] = text
            job["partial_chars"] = len(text)
            job["last_progress_at"] = time.time()
            if error:
                job["error"] = error
            if state == "interrupted_with_partial":
                job["interrupted_at"] = time.time()

        try:
            store.update(session)
            _logger.info(
                "dr task %s: finalised state=%s chars=%d duration=%ds",
                task_id, state, len(text), int(time.time() - started),
            )
        except Exception as e:
            _logger.warning("dr task %s: finalise update failed: %s", task_id, e)

    # Build prompt
    messages = [
        {"role": "system", "content": (
            "You are conducting deep research on the user's question. "
            "Use your built-in web search and reasoning. Produce a thorough "
            "Markdown report: executive summary, key findings with [N] "
            "citations, supporting evidence, and a Sources list with full URLs."
        )},
        {"role": "user", "content": question},
    ]

    # Route OpenAI DR direct to OpenAI Responses API when OPENAI_API_KEY is
    # set (saves the 5% OpenRouter margin). Perplexity and the OpenRouter
    # fallback for OpenAI continue through chat-completions.
    use_direct_openai = (
        service == "openai" and bool(os.environ.get("OPENAI_API_KEY"))
    )
    stream_iter = (
        _stream_openai_responses(model_id, messages)
        if use_direct_openai
        else _stream_openrouter_chat(model_id, messages)
    )
    try:
        async for chunk in stream_iter:
            if chunk.get("delta"):
                accumulated.append(chunk["delta"])
                await _flush()
            if "cost_usd" in chunk:
                cost_usd_total = chunk["cost_usd"]
        # Stream ended cleanly
        await _flush(force=True)
        full_text = "".join(accumulated).strip()
        if not full_text:
            await _finalise("failed", error="empty response from model")
            return
        await _finalise("completed")
    except asyncio.CancelledError:
        # User cancel — write cancelled state + partial
        print(f"[dr-run] {service} task_id={task_id} CANCELLED chars={_len()}", flush=True)
        await _flush(force=True)
        await _finalise("cancelled", error="cancelled by user")
        raise
    except Exception as e:
        print(f"[dr-run] {service} task_id={task_id} FAILED chars={_len()} err={type(e).__name__}: {e}", flush=True)
        await _flush(force=True)
        await _finalise("failed", error=f"{type(e).__name__}: {e}")
        _logger.warning("dr task %s failed: %s", task_id, e)
    else:
        print(f"[dr-run] {service} task_id={task_id} COMPLETED chars={_len()} duration={int(time.time()-started)}s", flush=True)
    finally:
        _LIVE_TASKS.pop(task_id, None)


# ---------------------------------------------------------------------------
# OpenRouter streaming — minimal SSE parser, no temperature for DR models
# ---------------------------------------------------------------------------


async def _stream_openrouter_chat(
    model_id: str, messages: list[dict],
) -> AsyncIterator[dict]:
    """Stream chat-completions deltas from OpenRouter.

    Yields: {"delta": "...partial text..."} for each token chunk, and
    finally {"cost_usd": <float>} once when usage is reported.

    Skips `temperature` for reasoning models (they 400 with it).
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    payload = {
        "model": model_id,
        "messages": messages,
        "stream": True,
        "usage": {"include": True},  # OpenRouter cost in stream tail
    }
    if not any(m in model_id for m in ("deep-research", "/o3-", "/o4-", "/o3:", "/o4:")):
        payload["temperature"] = 0.2

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/smart-report-mvp",
        "X-Title": "smart-report-mvp-v3",
    }

    # Long timeout — DR can run 30+ min
    timeout = httpx.Timeout(connect=30.0, read=2400.0, write=30.0, pool=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            if response.status_code >= 400:
                body = await response.aread()
                raise RuntimeError(
                    f"OpenRouter HTTP {response.status_code}: {body.decode('utf-8', 'replace')[:500]}"
                )
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = _json.loads(data)
                except _json.JSONDecodeError:
                    continue
                # Standard streaming chunk
                choices = obj.get("choices") or []
                for ch in choices:
                    delta = (ch.get("delta") or {}).get("content")
                    if delta:
                        yield {"delta": delta}
                usage = obj.get("usage")
                if isinstance(usage, dict) and usage.get("cost") is not None:
                    yield {"cost_usd": float(usage["cost"])}


# ---------------------------------------------------------------------------
# OpenAI Responses API streaming — direct path for o3/o4-mini deep-research
# ---------------------------------------------------------------------------


def _strip_openrouter_prefix(model_id: str) -> str:
    """OpenRouter ids look like 'openai/o4-mini-deep-research'; the OpenAI
    Responses API expects the bare 'o4-mini-deep-research' form."""
    if model_id.startswith("openai/"):
        return model_id[len("openai/"):]
    return model_id


async def _stream_openai_responses(
    model_id: str, messages: list[dict],
) -> AsyncIterator[dict]:
    """Stream from OpenAI Responses API for deep-research models.

    Yields ``{"delta": "<text>"}`` chunks per ``response.output_text.delta``
    event and a single ``{"cost_usd": <float>}`` at completion (computed
    from ``usage.input_tokens`` / ``usage.output_tokens`` × per-model price
    in ``OPENAI_DR_TOKEN_PRICES_USD``).

    Required tool: ``web_search_preview``. Deep-research models 400 if
    no data source is supplied — they are agents, not text generators.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    direct_model = _strip_openrouter_prefix(model_id)

    payload = {
        "model": direct_model,
        "input": messages,
        "tools": [{"type": "web_search_preview"}],
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=30.0, read=2400.0, write=30.0, pool=30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", "https://api.openai.com/v1/responses",
            headers=headers, json=payload,
        ) as response:
            if response.status_code >= 400:
                body = await response.aread()
                raise RuntimeError(
                    f"OpenAI Responses HTTP {response.status_code}: "
                    f"{body.decode('utf-8','replace')[:500]}"
                )
            current_event: Optional[str] = None
            async for line in response.aiter_lines():
                if not line:
                    current_event = None
                    continue
                if line.startswith("event:"):
                    current_event = line[len("event:"):].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    obj = _json.loads(data)
                except _json.JSONDecodeError:
                    continue
                et = current_event or obj.get("type")
                if et == "response.output_text.delta":
                    delta = obj.get("delta")
                    if delta:
                        yield {"delta": delta}
                elif et == "response.completed":
                    usage = (obj.get("response") or {}).get("usage") or {}
                    in_tok = int(usage.get("input_tokens") or 0)
                    out_tok = int(usage.get("output_tokens") or 0)
                    prices = OPENAI_DR_TOKEN_PRICES_USD.get(direct_model)
                    if prices:
                        cost = in_tok * prices[0] + out_tok * prices[1]
                        yield {"cost_usd": float(cost)}
                elif et == "error":
                    msg = obj.get("message") or _json.dumps(obj)[:300]
                    raise RuntimeError(f"OpenAI Responses API error: {msg}")


# ---------------------------------------------------------------------------
# Status / cancel — read state from PG (the source of truth)
# ---------------------------------------------------------------------------


def cancel_openai_dr_task(task_id: str) -> bool:
    """Cancel an in-flight LLM DR task.

    Cancels the asyncio.Task (which raises CancelledError into _run_streaming_dr,
    which writes 'cancelled' state with partial preserved). Returns True if
    a live task was found, False otherwise.
    """
    bg = _LIVE_TASKS.get(task_id)
    if bg is None or bg.done():
        return False
    bg.cancel()
    return True


def get_llm_research_task(task_id: str) -> Optional[dict[str, Any]]:
    """Legacy compat: in-memory _TASKS lookup. Returns minimal shape if the
    asyncio.Task is still alive locally; otherwise None — caller falls back
    to reading state from session.pending_dr_jobs in PG."""
    bg = _LIVE_TASKS.get(task_id)
    if bg is None or bg.done():
        return None
    return {"state": "running"}


# Backward-compat alias used by older imports.
_TASKS = _LIVE_TASKS


# ---------------------------------------------------------------------------
# Startup recovery — mark in-flight DR jobs as interrupted on container boot
# ---------------------------------------------------------------------------


def reconcile_orphaned_dr_jobs(store: Any) -> int:
    """Scan all sessions; mark any pending_dr_jobs of services 'openai' or
    'perplexity' that are still in 'running' state as 'interrupted_with_partial'.

    Auto-resubmit: if the job barely started (partial_chars < threshold),
    silently re-fire the asyncio task with the same parameters so the
    user doesn't see a loss. Above threshold we keep partial and let the
    user decide via recovery UI.

    Returns count of jobs marked. Idempotent — already-terminal jobs are
    untouched. Safe to call on every app startup.
    """
    now = time.time()
    marked = 0
    auto_resubmitted = 0
    try:
        sessions = store.all()
    except Exception as e:
        _logger.warning("reconcile_orphaned_dr_jobs: store.all() failed: %s", e)
        return 0

    for session in sessions:
        jobs = session.pending_dr_jobs or []
        if not jobs:
            continue
        changed = False
        # We may need to remove auto-resubmitted jobs and add fresh ones.
        new_jobs: list[dict] = []
        resubmit_specs: list[tuple[str, str, str, str]] = []  # (service, mode, question, original_task_id)

        for j in jobs:
            if j.get("service") not in ("openai", "perplexity"):
                new_jobs.append(j)
                continue
            state = j.get("state") or "running"
            if state != "running":
                new_jobs.append(j)
                continue

            partial_chars = int(j.get("partial_chars", 0) or 0)
            mode = j.get("mode") or ("mini" if j.get("service") == "openai" else "deep")
            # We also need the question to resubmit. Use research_prompt or raw_question.
            question = ""
            if session.research_prompt and session.research_prompt.full_prompt:
                question = session.research_prompt.full_prompt
            elif session.raw_question:
                question = session.raw_question

            if partial_chars < _AUTO_RESUBMIT_PARTIAL_THRESHOLD and question:
                # Auto-resubmit: drop this entry, defer fresh submit until after
                # the loop (we can't call asyncio.create_task before event loop
                # is running on startup; collect specs and fire in a deferred
                # coroutine).
                resubmit_specs.append((j.get("service"), mode, question, j.get("task_id", "?")))
                changed = True
                continue

            j["state"] = "interrupted_with_partial"
            j["interrupted_at"] = now
            j.setdefault("partial_content", "")
            j.setdefault("partial_chars", len(j.get("partial_content", "")))
            j.setdefault("error", "container restarted before completion")
            new_jobs.append(j)
            changed = True
            marked += 1

        if changed:
            session.pending_dr_jobs = new_jobs
            try:
                store.update(session)
            except Exception as e:
                _logger.warning(
                    "reconcile_orphaned_dr_jobs: update %s failed: %s",
                    getattr(session, "session_id", "?"), e,
                )
                continue

            # Fire auto-resubmits for this session. They schedule new
            # asyncio tasks which append fresh entries to pending_dr_jobs.
            for service, mode, question, original_task_id in resubmit_specs:
                try:
                    if service == "openai":
                        info = submit_openai_deep_research(
                            question, mode=mode,
                            session_id=session.session_id, store=store,
                        )
                    else:
                        info = submit_perplexity_deep_research(
                            question, mode=mode,
                            session_id=session.session_id, store=store,
                        )
                    auto_resubmitted += 1
                    print(
                        f"[dr-reconcile] auto-resubmit {service}/{mode} "
                        f"orig_task={original_task_id[:8]} new_task={info.task_id[:8]} "
                        f"session={session.session_id}",
                        flush=True,
                    )
                except Exception as e:
                    _logger.warning(
                        "auto-resubmit failed for %s/%s in session %s: %s",
                        service, mode, session.session_id, e,
                    )

    if marked or auto_resubmitted:
        _logger.info(
            "reconcile_orphaned_dr_jobs: marked %d interrupted, auto-resubmitted %d",
            marked, auto_resubmitted,
        )
    return marked + auto_resubmitted


# ---------------------------------------------------------------------------
# "Accept partial" — promote partial_content to source_reports
# ---------------------------------------------------------------------------


def accept_partial_into_source_reports(session: Any, task_id: str) -> bool:
    """Move pending_dr_jobs[task_id].partial_content into source_reports as
    a normal markdown upload. Removes the job entry. Returns True if done.
    """
    from smart_report.models import UploadedMarkdown

    job = None
    for j in (session.pending_dr_jobs or []):
        if j.get("task_id") == task_id:
            job = j
            break
    if job is None:
        return False
    text = (job.get("partial_content") or "").strip()
    if not text:
        return False
    service = job.get("service", "llm")
    detected_tool = "openai_dr" if service == "openai" else (
        "perplexity" if service == "perplexity" else "other"
    )
    filename = f"auto_dr_{service}_{task_id[:8]}_partial.md"
    already = any(u.filename == filename for u in (session.source_reports or []))
    if not already:
        upload = UploadedMarkdown(
            filename=filename,
            content=text + "\n\n_(частичный результат — задача была прервана)_",
            detected_tool=detected_tool,  # type: ignore[arg-type]
            word_count=len(text.split()),
        )
        session.source_reports = list(session.source_reports or []) + [upload]
        if session.status in {"created", "prompt_generated"}:
            session.status = "reports_uploaded"
    session.pending_dr_jobs = [
        j for j in (session.pending_dr_jobs or []) if j.get("task_id") != task_id
    ]
    return True
