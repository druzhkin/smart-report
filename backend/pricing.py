from __future__ import annotations

from datetime import timedelta
from statistics import median
from typing import Literal, TypedDict

from backend.config import settings
from backend.v2.intake import build_depth_profile
from backend.v2.models import BudgetTier, RunStatus, utc_now
from backend.v2.repository import FileRunRepository

Depth = Literal["light", "standard", "deep", "exhaustive"]


class PricingTier(TypedDict):
    depth: Depth
    label: str
    tagline: str
    description: str
    estimated_time_minutes: int
    public_price_usd: float
    internal_budget_usd: float
    initial_research_branches: int
    adjacent_research_branches: int
    validation_research_branches: int
    quality_max_rounds: int
    observed_sample_size: int
    observed_completed_runs: int
    observed_released_runs: int
    observed_median_cost_usd: float | None
    observed_p90_cost_usd: float | None
    observed_last_cost_usd: float | None
    observed_release_rate: float | None


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


def _percentile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    index = max(0, min(len(sorted_values) - 1, round((len(sorted_values) - 1) * q)))
    return float(sorted_values[index])


def _observed_depth_metrics(depth: Depth, repo: FileRunRepository) -> dict[str, float | int | None]:
    cutoff = utc_now() - timedelta(days=30)
    finished_statuses = {RunStatus.COMPLETED, RunStatus.FAILED}
    recent_runs = [
        run
        for run in repo.list_runs()
        if run.budget_tier.value == depth
        and run.created_at >= cutoff
        and run.status in finished_statuses
        and run.cost_usd > 0
    ]
    recent_runs.sort(key=lambda item: item.created_at, reverse=True)
    costs = sorted(float(run.cost_usd) for run in recent_runs)
    completed_runs = [run for run in recent_runs if run.status == RunStatus.COMPLETED]
    released_runs = [
        run for run in completed_runs if run.audit_summary is not None and run.audit_summary.release_status == "released"
    ]
    sample_size = len(recent_runs)
    release_rate = (len(released_runs) / len(completed_runs)) if completed_runs else None
    return {
        "observed_sample_size": sample_size,
        "observed_completed_runs": len(completed_runs),
        "observed_released_runs": len(released_runs),
        "observed_median_cost_usd": round(float(median(costs)), 6) if costs else None,
        "observed_p90_cost_usd": round(float(_percentile(costs, 0.9) or 0.0), 6) if costs else None,
        "observed_last_cost_usd": round(float(recent_runs[0].cost_usd), 6) if recent_runs else None,
        "observed_release_rate": round(float(release_rate), 4) if release_rate is not None else None,
    }


def get_public_pricing(*, repo: FileRunRepository | None = None) -> list[PricingTier]:
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
    repository = repo or FileRunRepository()

    tiers: list[PricingTier] = []
    for depth in DEPTH_ORDER:
        meta = DEPTH_META[depth]
        profile = build_depth_profile(BudgetTier(depth))
        observed = _observed_depth_metrics(depth, repository)
        tiers.append(
            {
                "depth": depth,
                "label": str(meta["label"]),
                "tagline": str(meta["tagline"]),
                "description": str(meta["description"]),
                "estimated_time_minutes": int(meta["estimated_time_minutes"]),
                "public_price_usd": float(price_map[depth]),
                "internal_budget_usd": float(budget_map[depth]),
                "initial_research_branches": profile.initial_research_branches,
                "adjacent_research_branches": profile.adjacent_research_branches,
                "validation_research_branches": profile.validation_research_branches,
                "quality_max_rounds": profile.quality_max_rounds,
                "observed_sample_size": int(observed["observed_sample_size"] or 0),
                "observed_completed_runs": int(observed["observed_completed_runs"] or 0),
                "observed_released_runs": int(observed["observed_released_runs"] or 0),
                "observed_median_cost_usd": observed["observed_median_cost_usd"],
                "observed_p90_cost_usd": observed["observed_p90_cost_usd"],
                "observed_last_cost_usd": observed["observed_last_cost_usd"],
                "observed_release_rate": observed["observed_release_rate"],
            }
        )
    return tiers
