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


ExaResearchModel = Literal["exa-research-fast", "exa-research", "exa-research-pro"]

RESEARCH_MODEL_PRICE_USD: dict[str, float] = {
    "exa-research-fast": 0.10,
    "exa-research":      0.50,
    "exa-research-pro":  2.00,
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
            progress_pct=d.get("progress") or d.get("progress_pct"),
            message=d.get("message") or d.get("status_message"),
            raw=d,
        )

    async def fetch_result(self, research_id: str) -> ExaResearchResult:
        st = await self.status(research_id)
        if st.state != "completed":
            raise ExaResearchError(f"task {research_id} not completed (state={st.state})")
        d = st.raw

        markdown = (
            d.get("report")
            or d.get("markdown")
            or d.get("answer")
            or d.get("output")
            or ""
        )
        if not markdown and isinstance(d.get("structured_output"), dict):
            import json
            markdown = "```json\n" + json.dumps(d["structured_output"], indent=2, ensure_ascii=False) + "\n```"

        citations = d.get("citations") or d.get("sources") or []
        if not markdown and isinstance(citations, list) and citations:
            lines = [f"# Exa research result\n"]
            for i, c in enumerate(citations, 1):
                if isinstance(c, dict):
                    lines.append(f"{i}. {c.get('title','(untitled)')} — {c.get('url','')}")
                else:
                    lines.append(f"{i}. {c}")
            markdown = "\n".join(lines)

        if not markdown:
            raise ExaResearchError(
                f"completed task {research_id} has no markdown/report; raw: {str(d)[:400]}"
            )

        sources_count = len(citations) if isinstance(citations, list) else 0
        word_count = len(markdown.split())

        if isinstance(citations, list) and citations and "## Sources" not in markdown and "## Источники" not in markdown:
            tail = ["\n\n## Sources\n"]
            for i, c in enumerate(citations, 1):
                if isinstance(c, dict):
                    url = c.get("url", "")
                    if url:
                        tail.append(f"{i}. {url}")
                else:
                    tail.append(f"{i}. {c}")
            markdown = markdown + "\n".join(tail)

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
