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
    target_sources: list[str] | None = None,
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
    domains = _filter_to_domains(target_sources)
    if domains:
        payload["search_domain_filter"] = domains
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
    _log(log_dir, query, cell_id, results, time.monotonic() - t0, mocked=False, citations=citations)
    return results


def _filter_to_domains(sources: list[str] | None) -> list[str]:
    """Keep only strings that look like TLDs: ASCII, contains a dot, no whitespace.

    Planner's current `target_sources` is a mix of org names ("ЦБ РФ", "Frank RG")
    and occasional domains ("erzrf.ru"). Perplexity's `search_domain_filter` rejects
    non-domain strings with 400. Until Planner emits a dedicated domain list, we
    forward only the shapes Perplexity can actually consume.
    """
    if not sources:
        return []
    out: list[str] = []
    for s in sources:
        if not isinstance(s, str):
            continue
        cand = s.strip().lower()
        if not cand or not cand.isascii() or " " in cand or "." not in cand:
            continue
        # Strip leading protocol/slash if someone ever sends a URL
        cand = cand.removeprefix("https://").removeprefix("http://").removeprefix("www.")
        cand = cand.split("/", 1)[0]
        if "." in cand and cand not in out:
            out.append(cand)
    return out


def _parse_or_fallback(text: str, citations: list[str]) -> list[dict]:
    import json as _json
    import re

    body = (text or "").strip()

    # Strip reasoning-model <think>...</think> blocks. Sonar occasionally leaks its
    # chain-of-thought into the content field; if the closing tag is present we can
    # recover the JSON that follows. If it's open-ended, body becomes empty and we
    # fall through to citation-salvage below.
    body = re.sub(r"<think>.*?</think>\s*", "", body, flags=re.DOTALL).strip()
    if body.startswith("<think>"):
        body = ""

    # Strip ```json / ``` code fences that sonar-pro frequently wraps around arrays.
    if body.startswith("```"):
        body = re.sub(r"^```[a-zA-Z]*\s*\n?", "", body)
        body = re.sub(r"\n?```\s*$", "", body).strip()

    parsed = None
    if body:
        try:
            parsed = _json.loads(body)
        except Exception:
            # second attempt: locate first '[' ... last ']'
            l, r = body.find("["), body.rfind("]")
            if l != -1 and r > l:
                try:
                    parsed = _json.loads(body[l : r + 1])
                except Exception:
                    parsed = None

    if isinstance(parsed, list):
        return _reconcile_urls_with_citations(parsed, citations)

    # Rich-citation salvage: parsing failed but Perplexity did real retrieval —
    # emit one placeholder finding per top citation so Analyst gets real URLs
    # instead of a single raw-text blob. This happens when the model leaks a
    # <think> trace or answers in prose instead of JSON.
    if len(citations) >= 3:
        return [
            {
                "claim": f"Retrieval returned prose/reasoning; raw source cited for Analyst review: {c}",
                "number": None,
                "source_url": c,
                "source_type": "other",
                "verbatim_quote": None,
            }
            for c in citations[:5]
        ]

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


def _reconcile_urls_with_citations(findings: list[dict], citations: list[str]) -> list[dict]:
    """If a finding's source_url is not in Perplexity's citations, replace it.

    Sonar-pro frequently invents plausible-looking URLs inside the JSON body while the
    `citations` array (what it actually retrieved) is authoritative. When the two
    disagree, prefer a citation over a hallucinated URL.
    """
    if not citations:
        return findings
    cite_set = {c.strip().rstrip("/") for c in citations if isinstance(c, str)}
    out = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        url = (f.get("source_url") or "").strip().rstrip("/")
        if url and url in cite_set:
            out.append(f)
            continue
        # fabricated or missing — pin to first citation and downgrade source_type
        replaced = dict(f)
        replaced["source_url"] = citations[0]
        if replaced.get("source_type") not in ("other",):
            replaced["source_type"] = "other"
        out.append(replaced)
    return out


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
    citations: list[str] | None = None,
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
            "citations": citations or [],
        },
    )
