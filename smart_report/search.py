"""Perplexity async retrieval wrapper. Logs to runs/<ts>/llm_log.jsonl (unified log)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from . import _stub_data
from .config import (
    PERPLEXITY_API_KEY,
    PERPLEXITY_BASE_URL,
    PERPLEXITY_MODEL,
    REQUEST_TIMEOUT_S,
)
from .io import append_jsonl


async def search(
    query: str,
    *,
    cell_id: str | None = None,
    mock: bool = False,
    log_dir: Path | None = None,
    model: str | None = None,
) -> list[dict]:
    """Return a list of {claim, number, source_url, source_type, verbatim_quote} dicts."""
    t0 = time.monotonic()

    if mock:
        results = _mock_results(cell_id or "", query)
        _log(log_dir, query, cell_id, results, time.monotonic() - t0, mocked=True)
        return results

    if not PERPLEXITY_API_KEY:
        raise RuntimeError(
            "PERPLEXITY_API_KEY is empty — set it in .env or pass mock=True / use --dry-run."
        )

    payload: dict[str, Any] = {
        "model": model or PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a retrieval scout. Return a JSON array of findings, each with keys: "
                    "claim, number (string or null), source_url, source_type "
                    "(one of: academic, official, industry, media, other), verbatim_quote."
                ),
            },
            {"role": "user", "content": query},
        ],
        "return_citations": True,
    }
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        r = await client.post(
            f"{PERPLEXITY_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    # Parsing the LLM-shaped Perplexity response into structured findings is the
    # real scout's responsibility — here we just return the raw assistant text
    # wrapped as one 'other'-type finding so the orchestrator can still run.
    assistant = data["choices"][0]["message"]["content"]
    citations = data.get("citations") or []
    results = _parse_or_fallback(assistant, citations)
    _log(log_dir, query, cell_id, results, time.monotonic() - t0, mocked=False)
    return results


def _parse_or_fallback(text: str, citations: list[str]) -> list[dict]:
    import json as _json

    try:
        parsed = _json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    # minimal fallback — keep pipeline flowing even if scout returns prose
    return [
        {
            "claim": (text[:300] if text else "no content returned"),
            "number": None,
            "source_url": citations[0] if citations else "https://perplexity.ai/",
            "source_type": "other",
            "verbatim_quote": None,
        }
    ]


def _mock_results(cell_id: str, query: str) -> list[dict]:
    if cell_id and cell_id in _stub_data.MOCK_FINDINGS:
        return [dict(f) for f in _stub_data.MOCK_FINDINGS[cell_id]]
    # generic fallback — still structurally valid
    return [
        {
            "claim": f"Mocked finding for query: {query[:80]}",
            "number": None,
            "source_url": "https://example.org/mock",
            "source_type": "other",
            "verbatim_quote": None,
        }
    ]


def _log(
    log_dir: Path | None,
    query: str,
    cell_id: str | None,
    results: list[dict],
    latency: float,
    *,
    mocked: bool,
) -> None:
    if log_dir is None:
        return
    append_jsonl(
        log_dir / "llm_log.jsonl",
        {
            "kind": "search",
            "cell_id": cell_id,
            "query": query,
            "mocked": mocked,
            "latency_s": round(latency, 3),
            "n_results": len(results),
            "results": results,
        },
    )
