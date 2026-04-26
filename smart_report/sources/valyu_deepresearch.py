"""Valyu Research API wrapper — async deep research jobs.

Distinct from `valyu.py` (which wraps the per-result `valyu.search()` —
instant, cheap, $0.001-0.005/result). This module wraps the
`valyu.deepresearch.*` SDK surface — true async deep research jobs
that take 5-180 minutes and produce a full markdown report. Pricing
is fixed-per-mode (not per-result):

    fast       $0.10   ~5 min    quick queries / batch
    standard   $0.50   10-20 min balanced research (default)
    heavy      $2.50   ~90 min   complex topics + fact verification
    max        $15.00  ~180 min  exhaustive

Architectural fit: long-running. The endpoint returns immediately
with `task_id`, the frontend polls `/auto-dr-status/{task_id}` until
done, then we pull the markdown asset and prepend to source_reports.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

_logger = logging.getLogger(__name__)


ValyuResearchMode = Literal["fast", "standard", "heavy", "max"]

# Fixed per-mode prices in USD (Valyu published rates 2026-04).
RESEARCH_MODE_PRICE_USD: dict[str, float] = {
    "fast": 0.10,
    "standard": 0.50,
    "heavy": 2.50,
    "max": 15.00,
}

# Approximate ETA per mode (minutes).
RESEARCH_MODE_ETA_MIN: dict[str, tuple[int, int]] = {
    "fast": (3, 7),
    "standard": (10, 20),
    "heavy": (60, 90),
    "max": (120, 180),
}


class ValyuResearchError(Exception):
    """Raised on permanent Valyu Research failure (4xx or job final-failed)."""


@dataclass
class ValyuResearchSubmission:
    task_id: str
    mode: str
    cost_usd: float
    eta_min_low: int
    eta_min_high: int
    raw: dict = field(default_factory=dict)


@dataclass
class ValyuResearchStatus:
    task_id: str
    state: str               # "queued" | "running" | "completed" | "failed" | "cancelled"
    progress_pct: Optional[int] = None
    message: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class ValyuResearchResult:
    task_id: str
    markdown: str
    sources_count: int = 0
    word_count: int = 0
    raw: dict = field(default_factory=dict)


class ValyuResearchClient:
    """Async-friendly wrapper around `Valyu().deepresearch.*`.

    `sdk_factory` is the test seam — pass a callable returning a mock
    `Valyu` instance with a `.deepresearch` attribute exposing
    `create / status / get_assets / cancel`.
    """

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
                from valyu import Valyu as _Sdk
                self._sdk_instance = _Sdk(api_key=self._api_key)
        return self._sdk_instance

    async def submit(
        self,
        query: str,
        *,
        mode: ValyuResearchMode = "standard",
    ) -> ValyuResearchSubmission:
        """Submit a research job. Returns task_id immediately (sub-second)."""
        if not query or not query.strip():
            raise ValyuResearchError("empty query")
        if mode not in RESEARCH_MODE_PRICE_USD:
            raise ValyuResearchError(f"unknown mode: {mode}")
        sdk = self._get_sdk()

        def _do() -> Any:
            return sdk.deepresearch.create(
                query=query,
                mode=mode,
                output_formats=["markdown"],
            )

        try:
            resp = await asyncio.to_thread(_do)
        except Exception as e:
            raise ValyuResearchError(f"submit failed: {type(e).__name__}: {e}") from e

        task_id = self._task_id_from_response(resp)
        if not task_id:
            raise ValyuResearchError(f"no task_id in response: {resp!r}")
        eta_lo, eta_hi = RESEARCH_MODE_ETA_MIN[mode]
        return ValyuResearchSubmission(
            task_id=task_id,
            mode=mode,
            cost_usd=RESEARCH_MODE_PRICE_USD[mode],
            eta_min_low=eta_lo,
            eta_min_high=eta_hi,
            raw=self._to_dict(resp),
        )

    async def status(self, task_id: str) -> ValyuResearchStatus:
        """Poll the job status. Sub-second."""
        sdk = self._get_sdk()
        try:
            resp = await asyncio.to_thread(sdk.deepresearch.status, task_id)
        except Exception as e:
            raise ValyuResearchError(f"status failed: {type(e).__name__}: {e}") from e
        d = self._to_dict(resp)
        state = (d.get("status") or d.get("state") or "running").lower()
        # Normalise SDK's various state names → our minimal vocabulary.
        if state in {"complete", "completed", "succeeded", "success", "done"}:
            state = "completed"
        elif state in {"failed", "error", "errored"}:
            state = "failed"
        elif state in {"cancelled", "canceled"}:
            state = "cancelled"
        elif state in {"queued", "pending"}:
            state = "queued"
        else:
            state = "running"
        return ValyuResearchStatus(
            task_id=task_id,
            state=state,
            progress_pct=d.get("progress") or d.get("progress_pct"),
            message=d.get("message") or d.get("status_message"),
            raw=d,
        )

    async def fetch_result(self, task_id: str) -> ValyuResearchResult:
        """Fetch the final markdown report. Call only after status="completed"."""
        sdk = self._get_sdk()
        try:
            assets = await asyncio.to_thread(sdk.deepresearch.get_assets, task_id)
        except Exception as e:
            raise ValyuResearchError(f"get_assets failed: {type(e).__name__}: {e}") from e
        d = self._to_dict(assets)

        # SDK returns a dict-like with 'markdown' or 'report' field, plus per-format URLs.
        markdown = (
            d.get("markdown")
            or d.get("report")
            or d.get("report_markdown")
            or ""
        )
        # Some SDK versions return assets as a list of {format, content/url}.
        if not markdown and isinstance(d.get("assets"), list):
            for asset in d["assets"]:
                if isinstance(asset, dict) and asset.get("format") == "markdown":
                    markdown = asset.get("content") or asset.get("text") or ""
                    if markdown:
                        break
        if not markdown:
            raise ValyuResearchError(
                f"completed task {task_id} has no markdown asset; raw: {str(d)[:500]}"
            )

        # Naive citation count: lines starting with a number in the Sources section.
        import re
        sources_count = len(re.findall(r"^\s*\d+\.\s+http", markdown, re.MULTILINE))
        word_count = len(markdown.split())

        return ValyuResearchResult(
            task_id=task_id,
            markdown=markdown,
            sources_count=sources_count,
            word_count=word_count,
            raw=d,
        )

    async def cancel(self, task_id: str) -> None:
        """Best-effort cancellation. Errors are swallowed (idempotent)."""
        sdk = self._get_sdk()
        try:
            await asyncio.to_thread(sdk.deepresearch.cancel, task_id)
        except Exception as e:
            _logger.warning("valyu research cancel failed for %s: %s", task_id, e)

    @staticmethod
    def _task_id_from_response(resp: Any) -> Optional[str]:
        if isinstance(resp, dict):
            return resp.get("task_id") or resp.get("id")
        return getattr(resp, "task_id", None) or getattr(resp, "id", None)

    @staticmethod
    def _to_dict(obj: Any) -> dict:
        """Normalise SDK response (Pydantic model or dict) to a plain dict."""
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            try:
                return obj.dict()
            except Exception:
                pass
        # Fallback: scrape public attrs.
        return {k: getattr(obj, k) for k in dir(obj)
                if not k.startswith("_") and not callable(getattr(obj, k, None))}
