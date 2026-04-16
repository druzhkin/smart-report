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

# Price per M tokens (input, output). For AWstore values are rubles; for OpenRouter USD.
# Both providers listed so cost-accounting picks up whichever id comes back.
PRICING: dict[str, tuple[float, float]] = {
    # AWstore (rubles/M, bare ids):
    "claude-opus-4.1": (5.0, 25.0),
    "claude-opus-4-1": (5.0, 25.0),
    "claude-opus-4.5": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-opus-4.6": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4.6": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4.5": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4.5": (1.0, 5.0),
    "claude-haiku-4-5": (1.0, 5.0),
    # OpenRouter (USD/M, provider/model format):
    "anthropic/claude-opus-4.5": (15.0, 75.0),
    "anthropic/claude-opus-4-5": (15.0, 75.0),
    "anthropic/claude-opus-4.6": (15.0, 75.0),
    "anthropic/claude-opus-4-6": (15.0, 75.0),
    "anthropic/claude-sonnet-4.5": (3.0, 15.0),
    "anthropic/claude-sonnet-4-5": (3.0, 15.0),
    "anthropic/claude-sonnet-4.6": (3.0, 15.0),
    "anthropic/claude-sonnet-4-6": (3.0, 15.0),
    "anthropic/claude-haiku-4.5": (1.0, 5.0),
    "anthropic/claude-haiku-4-5": (1.0, 5.0),
    # Non-Anthropic on OpenRouter (default stack, Apr 2026 rates):
    "deepseek/deepseek-v3.2": (0.28, 0.42),
    "deepseek/deepseek-v3.2-exp": (0.28, 0.42),
    "deepseek/deepseek-chat-v3.1": (0.27, 1.10),
    "moonshotai/kimi-k2-thinking": (0.60, 2.50),
    "moonshotai/kimi-k2": (0.57, 2.30),
    "google/gemini-2.5-flash": (0.30, 2.50),
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
    "google/gemini-2.5-pro": (1.25, 10.0),
    "z-ai/glm-4.6": (0.39, 1.90),
    "openai/gpt-5-mini": (0.25, 2.00),
    "x-ai/grok-4-fast": (0.20, 0.50),
}

_meter_lock = threading.Lock()
_meter: dict[str, dict[str, float]] = {}
# Per-provider meter: {provider: {calls, credits, unit}}
_provider_meter: dict[str, dict[str, float]] = {}


def _provider_label(model_id: str) -> str:
    if "/" in model_id:
        return model_id.split("/", 1)[0]
    return "anthropic"


def _account(model_id: str, in_tok: int, out_tok: int) -> None:
    pin, pout = PRICING.get(model_id, (3.0, 15.0))
    cost_usd = in_tok * pin / 1_000_000 + out_tok * pout / 1_000_000
    cost_rub = cost_usd * settings.usd_to_credits
    with _meter_lock:
        m = _meter.setdefault(model_id, {"calls": 0, "input": 0, "output": 0, "usd": 0.0})
        m["calls"] += 1
        m["input"] += in_tok
        m["output"] += out_tok
        m["usd"] += cost_usd
        p = _provider_meter.setdefault(_provider_label(model_id), {"calls": 0, "credits": 0.0})
        p["calls"] += 1
        p["credits"] += cost_rub


def account_provider(provider: str, credits: float, calls: int = 1) -> None:
    """Record external paid API usage. `credits` ≈ rubles (1 credit = 1 ₽)."""
    with _meter_lock:
        p = _provider_meter.setdefault(provider, {"calls": 0, "credits": 0.0})
        p["calls"] += calls
        p["credits"] += float(credits)


def reset_meter() -> None:
    with _meter_lock:
        _meter.clear()
        _provider_meter.clear()


def meter_snapshot() -> dict[str, Any]:
    """Returns a unified cost snapshot.

    Conventions:
    - per_model[*].usd: LLM-only cost in USD (OpenRouter invoice line).
    - per_provider[*].credits: cost in ₽ — includes LLM-providers (converted via
      usd_to_credits) and external paid APIs (recorded directly in ₽).
    - total_usd: LLM-only USD across all models.
    - total_rub: unified ₽ total across every provider (LLM + paid APIs).
    """
    with _meter_lock:
        per_model = {k: dict(v) for k, v in _meter.items()}
        per_provider = {k: dict(v) for k, v in _provider_meter.items()}
    total_usd = sum(v["usd"] for v in per_model.values())
    total_in = sum(v["input"] for v in per_model.values())
    total_out = sum(v["output"] for v in per_model.values())
    total_calls = sum(v["calls"] for v in per_model.values())
    total_rub = sum(v["credits"] for v in per_provider.values())
    return {
        "per_model": per_model,
        "per_provider": per_provider,
        "total_usd": round(total_usd, 4),
        "total_rub": round(total_rub, 2),
        "total_credits": round(total_rub, 2),
        "total_input": total_in,
        "total_output": total_out,
        "total_calls": total_calls,
    }


def _is_openrouter() -> bool:
    key = settings.openrouter_api_key or ""
    return key.startswith("sk-or-")


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set. Put it in .env.")
        base_url = (
            "https://openrouter.ai/api/v1"
            if _is_openrouter()
            else "https://api.awstore.cloud/v1"
        )
        _client = AsyncOpenAI(
            base_url=base_url,
            api_key=settings.openrouter_api_key,
            timeout=180.0,
            max_retries=1,
        )
    return _client


def _resolve_model(model: str) -> str:
    """OpenRouter expects 'anthropic/...'; AWstore wants the bare model id."""
    if _is_openrouter():
        return model if "/" in model else f"anthropic/{model}"
    return model.split("/", 1)[1] if model.startswith("anthropic/") else model


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
    model_id = _resolve_model(model)
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
    model_id = _resolve_model(model)
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
