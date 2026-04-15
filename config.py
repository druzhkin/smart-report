"""Runtime configuration. Loaded from .env."""
from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DepthTier = str  # "light" | "standard" | "deep" | "exhaustive"


DEPTH_PROFILES: dict[str, dict] = {
    "light": {
        "domains": (2, 3),
        "layers": (1, 2),
        "scouts_per_cell": 2,
        "max_parallel_scouts": 6,
        "max_parallel_analysts": 4,
        "planner_model": "anthropic/claude-haiku-4.5",
        "scout_model": "anthropic/claude-haiku-4.5",
        "analyst_model": "anthropic/claude-sonnet-4.5",
        "bisociator_model": "anthropic/claude-sonnet-4.5",
        "cost_cap_usd": 0.50,
        "perplexity_model": "sonar",
    },
    "standard": {
        "domains": (3, 4),
        "layers": (2, 3),
        "scouts_per_cell": 3,
        "max_parallel_scouts": 8,
        "max_parallel_analysts": 4,
        "planner_model": "anthropic/claude-sonnet-4.5",
        "scout_model": "anthropic/claude-haiku-4.5",
        "analyst_model": "anthropic/claude-sonnet-4.5",
        "bisociator_model": "anthropic/claude-sonnet-4.5",
        "cost_cap_usd": 2.00,
        "perplexity_model": "sonar-pro",
    },
    "deep": {
        "domains": (4, 5),
        "layers": (2, 4),
        "scouts_per_cell": 4,
        "max_parallel_scouts": 10,
        "max_parallel_analysts": 5,
        "planner_model": "anthropic/claude-opus-4.6",
        "scout_model": "anthropic/claude-sonnet-4.5",
        "analyst_model": "anthropic/claude-sonnet-4.5",
        "bisociator_model": "anthropic/claude-opus-4.6",
        "cost_cap_usd": 6.00,
        "perplexity_model": "sonar-pro",
    },
    "exhaustive": {
        "domains": (5, 6),
        "layers": (3, 4),
        "scouts_per_cell": 5,
        "max_parallel_scouts": 12,
        "max_parallel_analysts": 6,
        "planner_model": "anthropic/claude-opus-4.6",
        "scout_model": "anthropic/claude-sonnet-4.5",
        "analyst_model": "anthropic/claude-opus-4.6",
        "bisociator_model": "anthropic/claude-opus-4.6",
        "cost_cap_usd": 15.00,
        "perplexity_model": "sonar-pro",
    },
}


def depth_profile(depth: str) -> dict:
    return DEPTH_PROFILES.get(depth, DEPTH_PROFILES["standard"])


_active_profile: ContextVar[dict | None] = ContextVar("active_profile", default=None)


def set_active_profile(profile: dict | None) -> None:
    _active_profile.set(profile)


def model_for(role: str) -> str:
    """Resolve model by role ('planner'|'scout'|'analyst'|'bisociator'), respecting active depth profile."""
    p = _active_profile.get()
    key = f"{role}_model"
    if p and key in p:
        return p[key]
    return getattr(settings, key)


def perplexity_model_for() -> str:
    p = _active_profile.get()
    if p and "perplexity_model" in p:
        return p["perplexity_model"]
    return settings.perplexity_model


def profile_int(key: str, default: int) -> int:
    p = _active_profile.get()
    if p and key in p:
        return int(p[key])
    return default

ROOT = Path(__file__).parent
PROMPTS_DIR = ROOT / "prompts"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "")
    firecrawl_api_key: str = os.getenv("FIRECRAWL_API_KEY", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    core_api_key: str = os.getenv("CORE_API_KEY", "")
    semantic_scholar_api_key: str = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    pubmed_api_key: str = os.getenv("PUBMED_API_KEY", "")

    planner_model: str = os.getenv("PLANNER_MODEL", "anthropic/claude-opus-4.5")
    scout_model: str = os.getenv("SCOUT_MODEL", "anthropic/claude-haiku-4.5")
    analyst_model: str = os.getenv("ANALYST_MODEL", "anthropic/claude-sonnet-4.5")
    bisociator_model: str = os.getenv("BISOCIATOR_MODEL", "anthropic/claude-opus-4.5")

    perplexity_model: str = os.getenv("PERPLEXITY_MODEL", "sonar-pro")

    scouts_per_cell: int = int(os.getenv("SCOUTS_PER_CELL", "3"))
    max_parallel_scouts: int = int(os.getenv("MAX_PARALLEL_SCOUTS", "8"))
    max_parallel_analysts: int = int(os.getenv("MAX_PARALLEL_ANALYSTS", "4"))



settings = Settings()


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")
