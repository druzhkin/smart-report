"""Source backends: Valyu, future Perplexity wrapper, etc.

Day-2 of week-7 brief — minimal Valyu client. Step 3 (Day 3) will
add a SourceBackend enum + routing here once domain-aware routing
needs the abstraction.
"""

from .valyu import ValyuClient, ValyuResult, ValyuSearchError

__all__ = ["ValyuClient", "ValyuResult", "ValyuSearchError"]
