"""Exa Research API wrapper — async deep research jobs.

Distinct from `exa.py` (instant `Exa().search_and_contents()` —
~$0.01-0.02/call). Wraps `Exa().research.create()` + `.research.get()`
+ `.research.poll_until_finished()` — agentic research with three
model tiers and optional structured output schema.

Exa pricing (per docs as of 2026-04):
    exa-research-fast   ~$0.10  ~3-7 min   quick research
    exa-research        ~$0.50  ~10-20 min standard
    exa-research-pro    ~$2.00  ~30-60 min deep + structured
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

_logger = logging.getLogger(__name__)

from .valyu_deepresearch import _coerce_progress_pct


ExaResearchModel = Literal["exa-research-fast", "exa-research", "exa-research-pro"]

# 2026-04: exa.ai/pricing repriced to per-1k-requests for Search /
# Deep Search / Deep-Reasoning Search ($7/$12/$15 per 1k = ~$0.007 /
# $0.012 / $0.015 each), plus $1/1k pages contents. Old per-call
# tiers (fast/research/pro) are an approximation tied to roughly
# Search vs Deep Search vs Deep-Reasoning + Contents. Exa SDK does
# not return actual cost in research-completion responses → these
# estimates stand. Numbers below are realistic averages including
# typical contents fetches. Worth re-verifying every quarter.
RESEARCH_MODEL_PRICE_USD: dict[str, float] = {
    "exa-research-fast": 0.05,    # Search + small contents
    "exa-research":      0.20,    # Deep Search + contents pages
    "exa-research-pro":  0.50,    # Deep-Reasoning Search + many contents
}

RESEARCH_MODEL_ETA_MIN: dict[str, tuple[int, int]] = {
    "exa-research-fast": (3, 7),
    "exa-research":      (10, 20),
    "exa-research-pro":  (30, 60),
}


class ExaResearchError(Exception):
    """Permanent Exa Research failure."""


@dataclass
class ExaResearchSubmission:
    research_id: str
    model: str
    cost_usd: float
    eta_min_low: int
    eta_min_high: int
    raw: dict = field(default_factory=dict)


@dataclass
class ExaResearchStatus:
    research_id: str
    state: str
    progress_pct: Optional[int] = None
    message: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class ExaResearchResult:
    research_id: str
    markdown: str
    sources_count: int = 0
    word_count: int = 0
    raw: dict = field(default_factory=dict)


class ExaResearchClient:
    """Async wrapper for `Exa().research.*`."""

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
                from exa_py import Exa as _Sdk
                self._sdk_instance = _Sdk(api_key=self._api_key)
        return self._sdk_instance

    async def submit(
        self,
        query: str,
        *,
        model: ExaResearchModel = "exa-research",
    ) -> ExaResearchSubmission:
        if not query or not query.strip():
            raise ExaResearchError("empty query")
        if model not in RESEARCH_MODEL_PRICE_USD:
            raise ExaResearchError(f"unknown model: {model}")
        sdk = self._get_sdk()

        def _do() -> Any:
            return sdk.research.create(instructions=query, model=model)

        try:
            resp = await asyncio.to_thread(_do)
        except Exception as e:
            raise ExaResearchError(f"submit failed: {type(e).__name__}: {e}") from e

        d = self._to_dict(resp)
        rid = d.get("research_id") or d.get("id") or d.get("task_id")
        if not rid:
            raise ExaResearchError(f"no research_id in response: {str(d)[:300]}")
        eta_lo, eta_hi = RESEARCH_MODEL_ETA_MIN[model]
        return ExaResearchSubmission(
            research_id=rid, model=model,
            cost_usd=RESEARCH_MODEL_PRICE_USD[model],
            eta_min_low=eta_lo, eta_min_high=eta_hi, raw=d,
        )

    async def status(self, research_id: str) -> ExaResearchStatus:
        sdk = self._get_sdk()
        try:
            resp = await asyncio.to_thread(sdk.research.get, research_id)
        except Exception as e:
            raise ExaResearchError(f"status failed: {type(e).__name__}: {e}") from e
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
        return ExaResearchStatus(
            research_id=research_id, state=state,
            progress_pct=_coerce_progress_pct(d.get("progress") or d.get("progress_pct")),
            message=d.get("message") or d.get("status_message"),
            raw=d,
        )

    async def fetch_result(self, research_id: str) -> ExaResearchResult:
        """Read `output.content` (markdown) and walk `events[]` for citations.

        Per Exa SDK ResearchCompletedDto:
          output: ResearchOutput { content: str, parsed: dict | None }
          events: list of {plan,task}-{operation,output} events. Each
                  task-operation with type='search' has results: list[Result(url)],
                  type='crawl' has a single result. We collect all URLs
                  across events as the citation list.
        """
        st = await self.status(research_id)
        if st.state != "completed":
            raise ExaResearchError(f"task {research_id} not completed (state={st.state})")
        d = st.raw

        # ---- Extract markdown from output.content ----
        output = d.get("output")
        markdown = ""
        if isinstance(output, dict):
            markdown = output.get("content") or ""
            # If output_schema was used, content is empty and `parsed` is the dict.
            if not markdown and isinstance(output.get("parsed"), dict):
                import json as _json
                markdown = "```json\n" + _json.dumps(output["parsed"], indent=2, ensure_ascii=False) + "\n```"
        elif isinstance(output, str):
            markdown = output

        if not markdown:
            raise ExaResearchError(
                f"completed task {research_id} has no output.content; raw keys: {list(d.keys())}"
            )

        # ---- Walk events[] for citations (URLs) ----
        urls_seen: list[str] = []
        urls_set: set[str] = set()

        def _add_url(u: Any) -> None:
            if isinstance(u, str) and u and u not in urls_set:
                urls_set.add(u)
                urls_seen.append(u)

        events = d.get("events") or []
        if isinstance(events, list):
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                # Both plan-operation and task-operation events have data: {type, ...}
                data = ev.get("data")
                if isinstance(data, dict):
                    op_type = data.get("type")
                    if op_type == "search":
                        for r in (data.get("results") or []):
                            if isinstance(r, dict):
                                _add_url(r.get("url"))
                    elif op_type == "crawl":
                        r = data.get("result")
                        if isinstance(r, dict):
                            _add_url(r.get("url"))

        # If somehow events were absent, fall back to scraping URLs from the markdown body.
        if not urls_seen:
            import re
            for u in re.findall(r"https?://[^\s\)\]\>]+", markdown):
                _add_url(u)

        sources_count = len(urls_seen)

        # Append a Sources section if the markdown doesn't already have one.
        if urls_seen and ("## Sources" not in markdown and "## Источники" not in markdown):
            tail = ["\n\n## Sources\n"]
            for i, u in enumerate(urls_seen, 1):
                tail.append(f"{i}. {u}")
            markdown = markdown + "\n".join(tail)

        word_count = len(markdown.split())

        return ExaResearchResult(
            research_id=research_id,
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
