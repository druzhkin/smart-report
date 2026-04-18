"""OpenRouter async wrapper. Every call logged to runs/<ts>/llm_log.jsonl."""

from __future__ import annotations

import time
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
    """Send a chat completion; return assistant text. Logs prompt/response/tokens/cost/latency."""
    model_id = model or model_for(role)
    temp = temperature if temperature is not None else temperature_for(role)
    t0 = time.monotonic()

    if mock:
        text = _mock_response(role, messages)
        latency = time.monotonic() - t0
        _log(log_dir, role, model_id, messages, text, latency, mocked=True)
        return text

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
        r = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {}) or {}
    latency = time.monotonic() - t0
    _log(
        log_dir,
        role,
        model_id,
        messages,
        text,
        latency,
        mocked=False,
        tokens_in=usage.get("prompt_tokens"),
        tokens_out=usage.get("completion_tokens"),
        cost=data.get("usage", {}).get("cost"),
    )
    return text


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
    return ""


def _extract_cell_id(text: str) -> str | None:
    # tag shape: "[cell_id=market:structure]" — orchestrator will inject this
    import re

    m = re.search(r"\[cell_id=([^\]]+)\]", text or "")
    return m.group(1) if m else None
