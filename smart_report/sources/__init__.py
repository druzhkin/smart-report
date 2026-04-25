"""Source backends: Valyu, manual Perplexity loop, future async wrappers.

Day-3 of week-7 brief adds the SearchOrchestrator: it picks a backend
per detected query domain (smart_report.domain_detector.BackendPlan)
and falls through primary→fallback on empty results / transient
errors. Routing rules live in domain_detector; this package exposes
the dispatch surface.
"""

from .orchestrator import SearchOrchestrator, SearchOutcome
from .valyu import ValyuClient, ValyuResult, ValyuSearchError

__all__ = [
    "SearchOrchestrator",
    "SearchOutcome",
    "ValyuClient",
    "ValyuResult",
    "ValyuSearchError",
]
