"""SearchBackend Protocol + shared dataclasses (v3 brief §3.1 + §5.6).

Common interface for all retrieval backends — Valyu, Perplexity (via
adapter), Tavily, Exa. Per v3 brief §0 architectural invariant:
`is_primary_capable = True` ONLY for Valyu. Augment backends never
replace Valyu as primary on covered domains.

Source-quality classifier from Phase 3.3 fills `Source.quality_tier`
AFTER backend mapping — keeping classification uniform across backends
rather than each backend computing its own grades.

Path note: per BLOCKERS.md A8, this lives at `smart_report/sources/`
not the brief's `backend/v2/sources/` to avoid mid-pivot refactor risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class CostEstimate:
    """Per-call cost estimate for budget planning at the routing layer."""

    per_call_usd: float
    notes: str = ""


@dataclass
class Source:
    """Single retrieval source in a unified shape across backends.

    `quality_tier` is intentionally `None` at adapter boundary — the
    Phase 3.3 source-quality classifier owns its assignment. Adapters
    must NOT pre-tier sources or downstream calibration loses its
    single source of truth.
    """

    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    backend: str = ""  # "perplexity" | "valyu" | "tavily" | "exa"
    raw_metadata: dict = field(default_factory=dict)
    quality_tier: Optional[str] = None  # "STRONG" | "MODERATE" | "WEAK" | None


@dataclass
class Finding:
    """A factual claim drawn from one or more sources."""

    text: str
    sources: list[Source]
    raw_metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """Uniform return shape from any SearchBackend.search() call.

    The orchestrator (v3 §3.4) uses `is_empty_or_error` to drive the
    augment-on-failure routing — empty AND error both signal "fall
    through to augment backend". `error` is set only for true failures,
    not for empty result sets.
    """

    findings: list[Finding]
    sources: list[Source]
    raw_metadata: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    latency_ms: int = 0
    is_empty_or_error: bool = False
    error: Optional[str] = None


@runtime_checkable
class SearchBackend(Protocol):
    """Common Protocol every retrieval backend implements.

    `is_primary_capable` is the architectural invariant from v3 brief
    §0 + §3.5: only Valyu may set this True. The invariant test
    (`tests/test_routing_invariants.py`) enforces matrix-side; this
    Protocol exposes the per-backend declaration so the orchestrator
    can defensively double-check before promoting an augment to
    primary by accident.
    """

    name: str  # "valyu" | "perplexity" | "tavily" | "exa"
    is_primary_capable: bool

    async def search(
        self,
        query: str,
        *,
        domain_hint: Optional[str] = None,
        max_results: int = 10,
        cost_budget_usd: Optional[float] = None,
    ) -> SearchResult: ...

    @property
    def cost_per_call(self) -> CostEstimate: ...
