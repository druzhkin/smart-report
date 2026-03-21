from __future__ import annotations

from typing import Literal, TypedDict

from backend.config import settings

Depth = Literal["light", "standard", "deep", "exhaustive"]


class PricingTier(TypedDict):
    depth: Depth
    label: str
    tagline: str
    description: str
    estimated_time_minutes: int
    public_price_usd: float
    internal_budget_usd: float


DEPTH_ORDER: tuple[Depth, ...] = ("light", "standard", "deep", "exhaustive")

DEPTH_META: dict[Depth, dict[str, str | int]] = {
    "light": {
        "label": "Light",
        "tagline": "Quick orientation",
        "description": "Fast overview for scoping a topic, market, or hypothesis.",
        "estimated_time_minutes": 3,
    },
    "standard": {
        "label": "Standard",
        "tagline": "Balanced research",
        "description": "Mainstream choice for most business questions and decision memos.",
        "estimated_time_minutes": 8,
    },
    "deep": {
        "label": "Deep",
        "tagline": "Serious investigation",
        "description": "Thorough analysis with broader source coverage and stronger synthesis.",
        "estimated_time_minutes": 15,
    },
    "exhaustive": {
        "label": "Exhaustive",
        "tagline": "Maximum effort",
        "description": "Highest-effort run for strategic work, complex domains, or sensitive asks.",
        "estimated_time_minutes": 30,
    },
}


def get_public_pricing() -> list[PricingTier]:
    price_map: dict[Depth, float] = {
        "light": settings.public_price_light,
        "standard": settings.public_price_standard,
        "deep": settings.public_price_deep,
        "exhaustive": settings.public_price_exhaustive,
    }
    budget_map: dict[Depth, float] = {
        "light": settings.budget_light,
        "standard": settings.budget_standard,
        "deep": settings.budget_deep,
        "exhaustive": settings.budget_exhaustive,
    }

    tiers: list[PricingTier] = []
    for depth in DEPTH_ORDER:
        meta = DEPTH_META[depth]
        tiers.append(
            {
                "depth": depth,
                "label": str(meta["label"]),
                "tagline": str(meta["tagline"]),
                "description": str(meta["description"]),
                "estimated_time_minutes": int(meta["estimated_time_minutes"]),
                "public_price_usd": float(price_map[depth]),
                "internal_budget_usd": float(budget_map[depth]),
            }
        )
    return tiers

