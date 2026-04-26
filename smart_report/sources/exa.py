"""Exa search backend (week-7 §5.10 / 2-week autonomous Day 1).

Semantic search backend with optional structured `outputSchema` for
grounded JSON. Best fit for `technical_research` / `scientific` augment
where Valyu's arxiv coverage is solid but we want semantic similarity
("find papers like X") on top.

Per v3 brief and docs/VALYU_CAPABILITY_MAP.md:
  type='auto'       — default, ~$0.005-0.020/call, Exa picks neural
                      vs keyword based on query
  type='fast'       — speed > depth, ~$0.005/call
  type='deep-lite'  — only when outputSchema needed and `auto` doesn't
                      land structured data, ~$0.020-0.050/call
  type='deep' / 'deep-reasoning' — FORBIDDEN per brief (recon only)

`outputSchema` is the unique value-add: pass a JSON schema, get
`output.content` (structured payload) + `output.grounding` (citations
per field). Saves a synthesis LLM call when the analyst wants
specific structured data.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

_logger = logging.getLogger(__name__)


class ExaSearchError(Exception):
    """Permanent Exa failure (after retries / on 4xx)."""


@dataclass
class ExaResult:
    """Minimal projection of Exa SDK SearchResponse item."""

    url: str
    title: str
    text: str = ""
    highlights: list[str] = field(default_factory=list)
    score: Optional[float] = None
    published_date: Optional[str] = None
    author: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


_MAX_EXA_ATTEMPTS = 3
_BACKOFF_BASE_SEC = 1.0


ExaType = Literal["auto", "fast", "neural", "keyword", "deep-lite"]


class ExaClient:
    """Async-friendly Exa wrapper.

    `sdk_factory` is the test seam — pass a callable returning a mock
    SDK with `.search_and_contents(...)` for unit tests.
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
                from exa_py import Exa as _Sdk
                self._sdk_instance = _Sdk(api_key=self._api_key)
        return self._sdk_instance

    async def search(
        self,
        query: str,
        *,
        type: ExaType = "auto",
        num_results: int = 10,
        include_domains: Optional[list[str]] = None,
        exclude_domains: Optional[list[str]] = None,
        text_max_characters: int = 20000,
        include_highlights: bool = True,
    ) -> list[ExaResult]:
        """Run an Exa semantic search and return mapped results.

        `text_max_characters` caps the snippet length per result —
        critical because Exa can return long page extracts that bloat
        downstream LLM context. 20k chars per source × 10 sources =
        200k tokens worst case — already on the edge of Sonnet limit.
        """
        if not query or not query.strip():
            return []
        sdk = self._get_sdk()

        contents_kwargs = {
            "text": {"max_characters": text_max_characters},
        }
        if include_highlights:
            contents_kwargs["highlights"] = {"num_sentences": 3}

        def _do_search() -> Any:
            return sdk.search_and_contents(
                query=query,
                type=type,
                num_results=num_results,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                **contents_kwargs,
            )

        response = await self._call_with_retry(_do_search)
        if response is None:
            return []
        # SDK returns a SearchResponse object with .results = list of Result objects
        results_raw = getattr(response, "results", None) or []
        return [_to_exa_result(r) for r in results_raw]

    async def _call_with_retry(self, fn: Any) -> Any:
        import requests  # local import — only needed in retry hot path
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_EXA_ATTEMPTS):
            try:
                return await asyncio.to_thread(fn)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if 400 <= status < 500:
                    raise ExaSearchError(f"Exa HTTP {status}") from e
                last_exc = e
                _logger.warning(
                    "Exa attempt %d/%d failed with HTTP %d — retrying",
                    attempt + 1, _MAX_EXA_ATTEMPTS, status,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                _logger.warning(
                    "Exa attempt %d/%d failed with %s — retrying",
                    attempt + 1, _MAX_EXA_ATTEMPTS, type(e).__name__,
                )
            except Exception as e:
                # Exa SDK ValueError / KeyError — treat as permanent.
                raise ExaSearchError(f"Exa SDK error: {e!r}") from e
            if attempt < _MAX_EXA_ATTEMPTS - 1:
                await asyncio.sleep(_BACKOFF_BASE_SEC * (2**attempt))
        assert last_exc is not None
        raise ExaSearchError(f"Exa retries exhausted: {last_exc!r}") from last_exc


def _to_exa_result(raw: Any) -> ExaResult:
    """Adapt SDK Result object to ExaResult."""
    # SDK returns objects with attributes, not dicts
    text = getattr(raw, "text", "") or ""
    highlights = getattr(raw, "highlights", None) or []
    return ExaResult(
        url=getattr(raw, "url", "") or "",
        title=getattr(raw, "title", "") or "",
        text=text,
        highlights=list(highlights),
        score=getattr(raw, "score", None),
        published_date=getattr(raw, "published_date", None),
        author=getattr(raw, "author", None),
        raw={
            "id": getattr(raw, "id", None),
        },
    )
