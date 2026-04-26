"""Tavily search backend (week-7 §5.9 / 2-week autonomous Day 1).

Cheap general-web search backend for the Valyu-first hybrid (per
docs/VALYU_CAPABILITY_MAP.md routing matrix: `general` and
`realtime_news` domains route to Tavily basic, where Valyu's
proprietary corpora aren't a fit).

Two depth modes per Tavily docs:
  basic      — $0.005/call, 5-10 results, fast (~1-2s)
  advanced   — $0.020/call, deeper crawl, slow (~5-15s), better
               for non-trivial general queries

Implementation choices:
  * Sync requests under the hood (Tavily SDK is sync); wrap calls
    in `asyncio.to_thread` so callers stay async.
  * Same retry shim shape as Valyu (3 attempts, 1s/2s/4s backoff,
    retry transport errors + 5xx, no retry on 4xx).
  * `TavilySearchError` for all permanent failures so the
    orchestrator handles one error type from this module.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import requests

_logger = logging.getLogger(__name__)


class TavilySearchError(Exception):
    """Raised on permanent Tavily failure (after retries / on 4xx)."""


@dataclass
class TavilyResult:
    """Minimal projection of Tavily SDK response item."""

    url: str
    title: str
    content: str           # snippet text returned by Tavily
    score: Optional[float] = None
    published_date: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


_MAX_TAVILY_ATTEMPTS = 3
_BACKOFF_BASE_SEC = 1.0


SearchDepth = Literal["basic", "advanced"]


class TavilyClient:
    """Async-friendly Tavily wrapper.

    `sdk_factory` is the test seam — pass a callable returning a mock
    object with `.search(...)` for unit tests. Production path lazily
    imports the real `tavily.TavilyClient`.
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
                from tavily import TavilyClient as _Sdk  # local import — keeps module importable without dep
                self._sdk_instance = _Sdk(api_key=self._api_key)
        return self._sdk_instance

    async def search(
        self,
        query: str,
        *,
        search_depth: SearchDepth = "basic",
        max_results: int = 10,
        include_domains: Optional[list[str]] = None,
        exclude_domains: Optional[list[str]] = None,
        include_answer: bool = False,
    ) -> list[TavilyResult]:
        """Run a Tavily search and return mapped results.

        Empty result list is a valid success — caller may fall back
        to a different backend per the routing matrix.
        """
        if not query or not query.strip():
            return []
        sdk = self._get_sdk()

        def _do_search() -> Any:
            return sdk.search(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                include_domains=include_domains or [],
                exclude_domains=exclude_domains or [],
                include_answer=include_answer,
            )

        response = await self._call_with_retry(_do_search)
        if response is None:
            return []
        # SDK returns dict { "query":..., "results":[...], ... }
        results_raw = response.get("results", []) if isinstance(response, dict) else []
        return [_to_tavily_result(r) for r in results_raw]

    async def _call_with_retry(self, fn: Any) -> Any:
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_TAVILY_ATTEMPTS):
            try:
                return await asyncio.to_thread(fn)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if 400 <= status < 500:
                    raise TavilySearchError(f"Tavily HTTP {status}") from e
                last_exc = e
                _logger.warning(
                    "Tavily attempt %d/%d failed with HTTP %d — retrying",
                    attempt + 1, _MAX_TAVILY_ATTEMPTS, status,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                _logger.warning(
                    "Tavily attempt %d/%d failed with %s — retrying",
                    attempt + 1, _MAX_TAVILY_ATTEMPTS, type(e).__name__,
                )
            except Exception as e:
                # Tavily SDK occasionally raises non-requests errors (e.g.
                # ValueError on malformed key). Treat as permanent.
                raise TavilySearchError(f"Tavily SDK error: {e!r}") from e
            if attempt < _MAX_TAVILY_ATTEMPTS - 1:
                await asyncio.sleep(_BACKOFF_BASE_SEC * (2**attempt))
        assert last_exc is not None
        raise TavilySearchError(f"Tavily retries exhausted: {last_exc!r}") from last_exc


def _to_tavily_result(raw: Any) -> TavilyResult:
    """Adapt one SDK result dict to TavilyResult."""
    if not isinstance(raw, dict):
        return TavilyResult(url="", title="", content="", raw={})
    return TavilyResult(
        url=raw.get("url", "") or "",
        title=raw.get("title", "") or "",
        content=raw.get("content", "") or raw.get("snippet", "") or "",
        score=raw.get("score"),
        published_date=raw.get("published_date"),
        raw=raw,
    )
