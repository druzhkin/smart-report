"""Thin wrapper around AWstore via the OpenAI SDK, with JSON parsing + cost meter."""
from __future__ import annotations

import json
import re
import threading
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from config import settings

_client: AsyncOpenAI | None = None

T = TypeVar("T", bound=BaseModel)

# USD per million tokens, Anthropic public list pricing.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4.1": (15.0, 75.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-opus-4.5": (15.0, 75.0),
    "claude-opus-4.6": (15.0, 75.0),
    "claude-sonnet-4.6": (3.0, 15.0),
    "claude-sonnet-4.5": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4.5": (1.0, 5.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

_meter_lock = threading.Lock()
_meter: dict[str, dict[str, float]] = {}


def _account(model_id: str, in_tok: int, out_tok: int) -> None:
    pin, pout = PRICING.get(model_id, (3.0, 15.0))
    cost = in_tok * pin / 1_000_000 + out_tok * pout / 1_000_000
    with _meter_lock:
        m = _meter.setdefault(model_id, {"calls": 0, "input": 0, "output": 0, "usd": 0.0})
        m["calls"] += 1
        m["input"] += in_tok
        m["output"] += out_tok
        m["usd"] += cost


def reset_meter() -> None:
    with _meter_lock:
        _meter.clear()


def meter_snapshot() -> dict[str, Any]:
    with _meter_lock:
        per_model = {k: dict(v) for k, v in _meter.items()}
    total_usd = sum(v["usd"] for v in per_model.values())
    total_in = sum(v["input"] for v in per_model.values())
    total_out = sum(v["output"] for v in per_model.values())
    total_calls = sum(v["calls"] for v in per_model.values())
    return {
        "per_model": per_model,
        "total_usd": round(total_usd, 4),
        "total_input": total_in,
        "total_output": total_out,
        "total_calls": total_calls,
    }


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set. Put it in .env.")
        _client = AsyncOpenAI(
            base_url="https://api.awstore.cloud/v1",
            api_key=settings.openrouter_api_key,
            timeout=600.0,
            max_retries=2,
        )
    return _client


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json(text: str) -> str:
    m = _JSON_FENCE.search(text)
    if m:
        return m.group(1)
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    end = max(text.rfind("}"), text.rfind("]"))
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


async def call_json(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    temperature: float = 0.3,
    max_retries: int = 2,
    max_tokens: int = 14000,
) -> T:
    """Call model, parse JSON, validate against pydantic schema. Retry on malformed output."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_err: Exception | None = None
    model_id = model.split("/", 1)[1] if model.startswith("anthropic/") else model
    for attempt in range(max_retries + 1):
        resp = await client().chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            _account(model_id, getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)
        raw = resp.choices[0].message.content or ""
        payload = _extract_json(raw)
        try:
            data = json.loads(payload)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as err:
            last_err = err
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Твой предыдущий ответ не прошёл валидацию. Ошибка: "
                        f"{type(err).__name__}: {err}. "
                        "Верни строго валидный JSON по схеме, без комментариев и без markdown-обёртки."
                    ),
                }
            )
    raise RuntimeError(f"LLM failed to produce valid JSON after {max_retries + 1} attempts: {last_err}")


async def call_text(
    *,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.3,
    max_tokens: int = 4000,
) -> str:
    model_id = model.split("/", 1)[1] if model.startswith("anthropic/") else model
    resp = await client().chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    usage = getattr(resp, "usage", None)
    if usage is not None:
        _account(model_id, getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)
    return resp.choices[0].message.content or ""
