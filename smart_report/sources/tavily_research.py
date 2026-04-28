"""Tavily Research API wrapper — async deep research jobs.

Distinct from `tavily.py` (instant `client.search()` — $0.005-0.020/call).
Wraps `client.research()` + `client.get_research()` — proper agentic
research with `mini` / `pro` / `auto` model tiers. Returns a job
request_id to poll, much like Valyu Research.

Tavily pricing (per docs as of 2026-04):
    mini   ~$0.05  ~2-5 min   short queries
    pro    ~$0.30  ~5-15 min  in-depth (default)
    auto   varies  Tavily picks tier based on query complexity
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

_logger = logging.getLogger(__name__)

# Reuse the dict-or-int progress normaliser from valyu_deepresearch.
from .valyu_deepresearch import _coerce_progress_pct


TavilyResearchModel = Literal["mini", "pro", "auto"]

# 2026-04 (docs.tavily.com/documentation/api-credits): credit-based,
# $0.008/credit. Mini = 4-110 credits/call ($0.032-$0.880), Pro =
# 15-250 credits/call ($0.120-$2.000). Cost varies with depth, so these
# are mid-range estimates. Tavily SDK does NOT return actual cost in the
# response, so reconciliation isn't possible — the user is billed the
# estimate. If estimates drift consistently, raise these values.
RESEARCH_MODEL_PRICE_USD: dict[str, float] = {
    "mini": 0.20,   # mid-range; was understated $0.05
    "pro":  0.60,   # mid-range; was understated $0.30
    "auto": 0.40,   # mid-range; was understated $0.20
}

RESEARCH_MODEL_ETA_MIN: dict[str, tuple[int, int]] = {
    "mini": (2, 5),
    "pro":  (5, 15),
    "auto": (3, 12),
}


class TavilyResearchError(Exception):
    """Permanent Tavily Research failure (4xx, retries exhausted, or final-failed)."""


@dataclass
class TavilyResearchSubmission:
    request_id: str
    model: str
    cost_usd: float
    eta_min_low: int
    eta_min_high: int
    raw: dict = field(default_factory=dict)


@dataclass
class TavilyResearchStatus:
    request_id: str
    state: str                # queued | running | completed | failed | cancelled
    progress_pct: Optional[int] = None
    message: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class TavilyResearchResult:
    request_id: str
    markdown: str
    sources_count: int = 0
    word_count: int = 0
    raw: dict = field(default_factory=dict)


class TavilyResearchClient:
    """Async wrapper for `tavily.TavilyClient.research()` + `.get_research()`."""

    def __init__(
        self,
        api_key: str,
        *,
        sdk_factory: Optional[Any] = None,
    ) -> None:
        self._api_key = api_key
        self._sdk_factory = sdk_factory
        self._sdk_instance: Any = None

    def _get_sdk(self) -> Any:
        if self._sdk_instance is None:
            if self._sdk_factory is not None:
                self._sdk_instance = self._sdk_factory()
            else:
                from tavily import TavilyClient as _Sdk
                self._sdk_instance = _Sdk(api_key=self._api_key)
        return self._sdk_instance

    async def submit(
        self,
        query: str,
        *,
        model: TavilyResearchModel = "pro",
    ) -> TavilyResearchSubmission:
        if not query or not query.strip():
            raise TavilyResearchError("empty query")
        if model not in RESEARCH_MODEL_PRICE_USD:
            raise TavilyResearchError(f"unknown model: {model}")
        sdk = self._get_sdk()

        def _do() -> Any:
            return sdk.research(
                input=query, model=model, citation_format="numbered",
            )

        try:
            resp = await asyncio.to_thread(_do)
        except Exception as e:
            raise TavilyResearchError(f"submit failed: {type(e).__name__}: {e}") from e

        d = self._to_dict(resp)
        request_id = d.get("request_id") or d.get("id") or d.get("research_id")
        if not request_id:
            raise TavilyResearchError(f"no request_id in response: {str(d)[:300]}")
        eta_lo, eta_hi = RESEARCH_MODEL_ETA_MIN[model]
        return TavilyResearchSubmission(
            request_id=request_id, model=model,
            cost_usd=RESEARCH_MODEL_PRICE_USD[model],
            eta_min_low=eta_lo, eta_min_high=eta_hi, raw=d,
        )

    async def status(self, request_id: str) -> TavilyResearchStatus:
        sdk = self._get_sdk()
        try:
            resp = await asyncio.to_thread(sdk.get_research, request_id)
        except Exception as e:
            raise TavilyResearchError(f"status failed: {type(e).__name__}: {e}") from e
        d = self._to_dict(resp)
        state = (d.get("status") or d.get("state") or "running").lower()
        if state in {"complete", "completed", "success", "succeeded", "done", "finished"}:
            state = "completed"
        elif state in {"failed", "error", "errored"}:
            state = "failed"
        elif state in {"cancelled", "canceled"}:
            state = "cancelled"
        elif state in {"queued", "pending"}:
            state = "queued"
        else:
            state = "running"
        return TavilyResearchStatus(
            request_id=request_id, state=state,
            progress_pct=_coerce_progress_pct(d.get("progress") or d.get("progress_pct")),
            message=d.get("message") or d.get("status_message"),
            raw=d,
        )

    async def fetch_result(self, request_id: str) -> TavilyResearchResult:
        """Fetch the completed report. Tavily's get_research returns the
        full result inline once status==completed."""
        st = await self.status(request_id)
        if st.state != "completed":
            raise TavilyResearchError(f"task {request_id} not completed (state={st.state})")
        d = st.raw

        # Tavily returns the report under various names depending on version.
        # Tavily response shape varies — fields may be plain strings OR
        # nested dicts/lists. Same defensive coercion as exa_research.
        def _coerce_to_md(value) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                for k in ("content", "markdown", "text", "report", "answer", "output"):
                    inner = value.get(k)
                    if isinstance(inner, str) and inner:
                        return inner
                import json as _json
                try:
                    return "```json\n" + _json.dumps(value, indent=2, ensure_ascii=False) + "\n```"
                except Exception:
                    return str(value)
            if isinstance(value, list):
                parts = [v for v in value if isinstance(v, str)]
                if parts:
                    return "\n\n".join(parts)
                import json as _json
                try:
                    return "```json\n" + _json.dumps(value, indent=2, ensure_ascii=False) + "\n```"
                except Exception:
                    return str(value)
            return str(value)

        markdown = ""
        for field_name in ("markdown", "report", "answer", "output"):
            candidate = _coerce_to_md(d.get(field_name))
            if candidate:
                markdown = candidate
                break
        # If structured: dict, render as JSON-like markdown.
        if not markdown and isinstance(d.get("structured_output"), dict):
            import json
            markdown = "```json\n" + json.dumps(d["structured_output"], indent=2, ensure_ascii=False) + "\n```"

        sources = d.get("sources") or d.get("citations") or []
        if isinstance(sources, list) and sources and not markdown:
            # Build a minimal markdown shell from citations only.
            lines = [f"# Tavily research result\n"]
            for i, s in enumerate(sources, 1):
                if isinstance(s, dict):
                    lines.append(f"{i}. {s.get('title','(untitled)')} — {s.get('url','')}")
                else:
                    lines.append(f"{i}. {s}")
            markdown = "\n".join(lines)

        if not markdown:
            raise TavilyResearchError(
                f"completed task {request_id} has no markdown/answer; raw: {str(d)[:400]}"
            )

        sources_count = len(sources) if isinstance(sources, list) else 0
        word_count = len(markdown.split())

        # Tail the markdown with a Sources block if not already present, for
        # the v4 intake parser.
        if isinstance(sources, list) and sources and "## Sources" not in markdown and "## Источники" not in markdown:
            tail = ["\n\n## Sources\n"]
            for i, s in enumerate(sources, 1):
                if isinstance(s, dict):
                    url = s.get("url", "")
                    if url:
                        tail.append(f"{i}. {url}")
                else:
                    tail.append(f"{i}. {s}")
            markdown = markdown + "\n".join(tail)

        return TavilyResearchResult(
            request_id=request_id,
            markdown=markdown,
            sources_count=sources_count,
            word_count=word_count,
            raw=d,
        )

    @staticmethod
    def _to_dict(obj: Any) -> dict:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            try:
                return obj.dict()
            except Exception:
                pass
        return {k: getattr(obj, k) for k in dir(obj)
                if not k.startswith("_") and not callable(getattr(obj, k, None))}
