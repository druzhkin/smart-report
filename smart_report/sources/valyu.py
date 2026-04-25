"""Valyu source backend (v4.5 week-7 Day 2).

Thin async wrapper around the Valyu Python SDK 2.9.4. The SDK is sync
(uses `requests`); we wrap calls in ``asyncio.to_thread`` so the rest
of the async pipeline doesn't have to switch context models.

Design choices:
  * ``fast_mode=True`` is the default — every product call goes through
    the cheap path. Brief §1 reserves the standard tier for the one-off
    recon call (already done in Day 1).
  * ``search_type="proprietary"`` is the default — Valyu's value-add is
    its curated corpora (SEC filings, FRED, PubMed, EU regulatory).
    Generic web search overlaps with Perplexity. Callers can override.
  * Transient-failure retry shim modelled on the Step 3.1 OpenRouter
    one: 3 attempts, exponential backoff (1s/2s/4s), retry on 5xx +
    requests.ConnectionError + requests.Timeout, NO retry on 4xx.
  * ``ValyuResult`` is a tiny dataclass — the SDK's SearchResult has
    20+ fields; we only need a handful for adapter into ``SourceRef``.
  * No SourceRegistry abstraction yet — added in Day 3 once routing
    actually needs it.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import requests

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class ValyuSearchError(Exception):
    """Raised when a Valyu search permanently fails (after retries)."""


@dataclass
class ValyuResult:
    """Minimal projection of valyu.types.response.SearchResult.

    We deliberately avoid passing through the full SDK type — keeping
    a thin adapter shape lets the rest of the pipeline depend on
    ``SourceRef`` (smart_report.models) instead of pulling in the
    Valyu pydantic graph.
    """

    url: str
    title: str
    content: str  # may be markdown text or stringified structured data
    source: str  # dataset id (e.g. "valyu/valyu-fred")
    price: float
    relevance_score: Optional[float] = None
    publication_date: Optional[str] = None
    data_type: Optional[str] = None  # "structured" | "unstructured"
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Retry constants (mirror Step 3.1 OpenRouter shim)
# ---------------------------------------------------------------------------


_MAX_VALYU_ATTEMPTS = 3
_BACKOFF_BASE_SEC = 1.0


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


SearchType = Literal["web", "proprietary", "all", "news"]


class ValyuClient:
    """Async Valyu client. Lazily initialises the SDK Valyu instance.

    Usage::

        client = ValyuClient(api_key=os.environ["VALYU_API_KEY"])
        results = await client.search(
            "Tesla Q4 2025 earnings",
            search_type="proprietary",
            category="company",
            max_results=10,
        )
    """

    def __init__(
        self,
        api_key: str,
        *,
        sdk_factory: Optional[Any] = None,
    ) -> None:
        """Create a client.

        ``sdk_factory`` is an injection seam for tests — the default
        instantiates ``valyu.Valyu(api_key=...)`` lazily. Tests can
        pass a callable that returns a mock with a ``.search`` method.
        """
        self._api_key = api_key
        self._sdk_factory = sdk_factory
        self._sdk_instance: Any = None

    def _get_sdk(self) -> Any:
        if self._sdk_instance is None:
            if self._sdk_factory is not None:
                self._sdk_instance = self._sdk_factory()
            else:
                # Local import so test environments without `valyu`
                # installed can still import this module.
                from valyu import Valyu

                self._sdk_instance = Valyu(api_key=self._api_key)
        return self._sdk_instance

    async def search(
        self,
        query: str,
        *,
        search_type: SearchType = "all",
        category: Optional[str] = None,
        max_results: int = 10,
        fast_mode: bool = True,
        included_sources: Optional[list[str]] = None,
        excluded_sources: Optional[list[str]] = None,
        relevance_threshold: float = 0.5,
    ) -> list[ValyuResult]:
        """Run a Valyu DeepSearch query and return mapped ``ValyuResult`` list.

        Defaults: ``search_type="all"`` and ``fast_mode=True``. The Valyu
        API has a real constraint not surfaced by introspection:
        ``fast_mode=True`` is incompatible with ``search_type="proprietary"``
        (the API responds with an error). When the caller wants Valyu's
        proprietary corpora (SEC filings, FRED, PubMed, EU regulatory),
        they MUST pass ``search_type="proprietary", fast_mode=False``
        explicitly — the cost goes up to ~$0.005-0.020/call but that's
        the only path to Valyu's value-add. Day 3 routing will set
        these explicitly per detected_domain. Logged in BLOCKERS.md A3.

        Empty result list is a valid success — the caller treats it as
        "fall back to secondary backend" per the brief's hybrid routing.
        """
        if not query or not query.strip():
            return []
        sdk = self._get_sdk()

        def _do_search() -> Any:
            return sdk.search(
                query=query,
                search_type=search_type,
                max_num_results=max_results,
                fast_mode=fast_mode,
                category=category,
                included_sources=included_sources,
                excluded_sources=excluded_sources,
                relevance_threshold=relevance_threshold,
                is_tool_call=False,  # we're calling for our own pipeline
            )

        response = await self._call_with_retry(_do_search)
        if response is None:
            return []
        if not getattr(response, "success", False):
            error = getattr(response, "error", "unknown")
            raise ValyuSearchError(f"Valyu reported error: {error}")
        return [_to_valyu_result(r) for r in (response.results or [])]

    async def _call_with_retry(self, fn: Any) -> Any:
        """Run *fn* (a sync callable) in a thread with retry on transient failures.

        Mirrors the Step 3.1 OpenRouter retry policy: 3 attempts,
        exponential backoff (1s, 2s, 4s), retry on transport errors
        and 5xx, do NOT retry on 4xx (auth/payment/rate-limit).
        """
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_VALYU_ATTEMPTS):
            try:
                return await asyncio.to_thread(fn)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if 400 <= status < 500:
                    raise  # 4xx — expected failure, do not retry
                last_exc = e
                _logger.warning(
                    "Valyu attempt %d/%d failed with HTTP %d — retrying",
                    attempt + 1,
                    _MAX_VALYU_ATTEMPTS,
                    status,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                _logger.warning(
                    "Valyu attempt %d/%d failed with %s: %s — retrying",
                    attempt + 1,
                    _MAX_VALYU_ATTEMPTS,
                    type(e).__name__,
                    e,
                )
            if attempt < _MAX_VALYU_ATTEMPTS - 1:
                await asyncio.sleep(_BACKOFF_BASE_SEC * (2**attempt))
        assert last_exc is not None
        raise ValyuSearchError(f"Valyu retries exhausted: {last_exc!r}") from last_exc


# ---------------------------------------------------------------------------
# SDK → our model adapter
# ---------------------------------------------------------------------------


def _to_valyu_result(sdk_result: Any) -> ValyuResult:
    """Adapt a single SDK SearchResult to our ValyuResult shape.

    Defensive: missing optional fields are tolerated; content is
    stringified if the SDK returned a structured object.
    """
    content = getattr(sdk_result, "content", "")
    if not isinstance(content, str):
        # Structured (list/dict) — stringify for downstream text use
        try:
            import json as _json

            content = _json.dumps(content, ensure_ascii=False, indent=2)
        except Exception:
            content = str(content)
    metadata = getattr(sdk_result, "metadata", None) or {}
    return ValyuResult(
        url=getattr(sdk_result, "url", "") or "",
        title=getattr(sdk_result, "title", "") or "",
        content=content,
        source=getattr(sdk_result, "source", "") or "",
        price=float(getattr(sdk_result, "price", 0.0) or 0.0),
        relevance_score=getattr(sdk_result, "relevance_score", None),
        publication_date=getattr(sdk_result, "publication_date", None),
        data_type=getattr(sdk_result, "data_type", None),
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )
