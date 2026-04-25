"""OpenRouter async wrapper. Every call logged to runs/<ts>/llm_log.jsonl."""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import _stub_data
from .config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    REQUEST_TIMEOUT_S,
    model_for,
    temperature_for,
)
from .io import append_jsonl

_logger = logging.getLogger(__name__)
# Note: name is intentionally _logger, not _log — the latter is already
# a private helper function defined further down in this module.

# USD → RUB exchange rate used for cost conversion.
# OpenRouter bills in USD; we display in RUB for the analyst dashboard.
_USD_TO_RUB: float = 90.0


# v4.5 Phase 3 Step 3.1 Task 1.4 — httpx retry shim (Run 1 finding 4).
# Q1 first attempt in Comparison Run 1 lost $0.47 to a transient
# httpx.JSONDecodeError on r.json() (HTTP 200 but malformed body).
# These constants pin the retry policy: max 3 attempts total with
# exponential backoff (1s, 2s, 4s). 4xx errors are NOT retried —
# they are expected failures (auth, payment, rate-limit) where retry
# would either succeed for a wrong reason or amplify rate-limiting.
_MAX_TRANSPORT_ATTEMPTS = 3
_BACKOFF_BASE_SEC = 1.0  # attempts use 1s, 2s, 4s


async def _post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict,
    json: dict,
) -> dict:
    """POST to OpenRouter with retry on transient failures.

    Retries on:
      - httpx.ConnectError / TimeoutException / RemoteProtocolError
      - 5xx HTTPStatusError
      - JSONDecodeError on response.json() (HTTP 200 with malformed body —
        the exact failure mode of Run 1 finding 4)

    Does NOT retry on:
      - 4xx HTTPStatusError (401 / 402 / 429 — expected failures)
      - Non-transport exceptions (programmer error)

    Logs each retry as a warning so production telemetry can surface
    transient-failure rate without re-instrumenting callers.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_TRANSPORT_ATTEMPTS):
        try:
            response = await client.post(url, headers=headers, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            # 4xx → expected failure, do not retry
            if 400 <= e.response.status_code < 500:
                raise
            last_exc = e
            _logger.warning(
                "OpenRouter POST attempt %d/%d failed with HTTP %d — retrying",
                attempt + 1,
                _MAX_TRANSPORT_ATTEMPTS,
                e.response.status_code,
            )
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
            _json.JSONDecodeError,
        ) as e:
            last_exc = e
            _logger.warning(
                "OpenRouter POST attempt %d/%d failed with %s: %s — retrying",
                attempt + 1,
                _MAX_TRANSPORT_ATTEMPTS,
                type(e).__name__,
                e,
            )
        if attempt < _MAX_TRANSPORT_ATTEMPTS - 1:
            await asyncio.sleep(_BACKOFF_BASE_SEC * (2**attempt))
    assert last_exc is not None
    raise last_exc


@dataclass
class LLMResult:
    """Return value of :func:`call_json` / :func:`chat`.

    ``text`` holds the raw assistant response.  ``cost_rub`` is the per-call
    cost converted from USD (0.0 when mocked or when the API returns no cost).
    """

    text: str
    cost_rub: float = field(default=0.0)
    tokens_in: int | None = field(default=None)
    tokens_out: int | None = field(default=None)


async def call_json(
    role: str,
    messages: list[dict],
    *,
    mock: bool = False,
    log_dir: Path | None = None,
    model: str | None = None,
    temperature: float | None = None,
    response_format: dict | None = None,
    **kwargs: Any,
) -> LLMResult:
    """Send a chat completion; return :class:`LLMResult` with text + cost.

    This is the primary entry-point for v4 callers that need per-call cost
    accounting.  ``chat()`` remains as a thin compatibility shim that returns
    only the text string for v3 callers.
    """
    model_id = model or model_for(role)
    temp = temperature if temperature is not None else temperature_for(role)
    t0 = time.monotonic()

    if mock:
        text = _mock_response(role, messages)
        latency = time.monotonic() - t0
        _log(log_dir, role, model_id, messages, text, latency, mocked=True)
        return LLMResult(text=text, cost_rub=0.0)

    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is empty — set it in .env or pass mock=True / use --dry-run."
        )

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": temp,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    payload.update(kwargs)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/smart-report-mvp",
        "X-Title": "smart-report-mvp-v3",
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        # Step 3.1 Task 1.4: retry shim around the transport so a
        # transient JSONDecodeError / ConnectError / 5xx no longer
        # vaporises a paid LLM call (Run 1 cost $0.47 to this exact bug).
        data = await _post_with_retry(
            client,
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {}) or {}
    latency = time.monotonic() - t0
    cost_usd: float | None = usage.get("cost")
    cost_rub: float = round(cost_usd * _USD_TO_RUB, 4) if cost_usd else 0.0
    tokens_in: int | None = usage.get("prompt_tokens")
    tokens_out: int | None = usage.get("completion_tokens")
    _log(
        log_dir,
        role,
        model_id,
        messages,
        text,
        latency,
        mocked=False,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost_usd,
    )
    return LLMResult(
        text=text,
        cost_rub=cost_rub,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


async def chat(
    role: str,
    messages: list[dict],
    *,
    mock: bool = False,
    log_dir: Path | None = None,
    model: str | None = None,
    temperature: float | None = None,
    response_format: dict | None = None,
    **kwargs: Any,
) -> str:
    """Compatibility shim — returns only the assistant text string.

    v3 orchestrator and all existing callers that don't need cost use this.
    New v4 callers should use :func:`call_json` instead.
    """
    result = await call_json(
        role,
        messages,
        mock=mock,
        log_dir=log_dir,
        model=model,
        temperature=temperature,
        response_format=response_format,
        **kwargs,
    )
    return result.text


def _log(
    log_dir: Path | None,
    role: str,
    model_id: str,
    messages: list[dict],
    response: str,
    latency: float,
    *,
    mocked: bool,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost: float | None = None,
) -> None:
    if log_dir is None:
        return
    append_jsonl(
        log_dir / "llm_log.jsonl",
        {
            "kind": "llm",
            "role": role,
            "model": model_id,
            "mocked": mocked,
            "latency_s": round(latency, 3),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost": cost,
            "messages": messages,
            "response": response,
        },
    )


def _mock_response(role: str, messages: list[dict]) -> str:
    """Return plausible role-appropriate stub text. Structured consumers parse downstream."""
    import json as _json

    if role == "planner":
        return _json.dumps(_stub_data.MOCK_MATRIX, ensure_ascii=False)
    if role == "analyst":
        # Look up cell_id if embedded in last user message
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        cell_id = _extract_cell_id(last_user) or "market:structure"
        block = _stub_data.MOCK_BLOCK.get(cell_id) or _stub_data.MOCK_BLOCK["market:structure"]
        return _json.dumps(block, ensure_ascii=False)
    if role == "bisociator":
        return _json.dumps(_stub_data.MOCK_CROSS_LINKS, ensure_ascii=False)
    if role == "summarizer":
        return _json.dumps(_stub_data.MOCK_EXECUTIVE_SUMMARY, ensure_ascii=False)
    if role == "scout":
        # Scout in our design leans on search.search(); if ever invoked as llm, return empty list
        return "[]"
    # v4 roles — return minimal valid JSON so mock=True flows don't crash on JSON parsing.
    if role == "prompt_master":
        return _json.dumps(
            {
                "full_prompt": "Mock research prompt: investigate the question thoroughly.",
                "reasoning": "Mock reasoning for dry-run mode.",
                "expected_structure": ["Introduction", "Analysis", "Conclusion"],
                "key_entities": [],
                "tips_for_search": "Use Perplexity Deep Research.",
            },
            ensure_ascii=False,
        )
    if role == "analyzer":
        return _json.dumps(
            {
                "per_source_summary": [],
                "consensus": [],
                "conflicts": [],
                "gaps": [],
                "unverified_numbers": [],
                "quality_notes": "Mock analyzer output for dry-run mode.",
                "followup_prompts": [],
            },
            ensure_ascii=False,
        )
    if role == "synthesizer":
        return _json.dumps(
            {
                "session_id": "mock",
                "question": "Mock question",
                "research_prompt_used": "",
                "executive_summary": {
                    "main_answer": "Mock final answer for dry-run mode.",
                    "ranking": None,
                    "top_findings": [],
                    "key_numbers": [],
                    "confidence_note": "low — mock data",
                    "what_meta_adds": "",
                },
                "main_synthesis": "Mock synthesis.",
                "consensus_section": "",
                "conflicts_section": "",
                "gaps_filled_section": "",
                "all_sources": [],
                "metadata": {},
            },
            ensure_ascii=False,
        )
    return ""


def _extract_cell_id(text: str) -> str | None:
    # tag shape: "[cell_id=market:structure]" — orchestrator will inject this
    import re

    m = re.search(r"\[cell_id=([^\]]+)\]", text or "")
    return m.group(1) if m else None
