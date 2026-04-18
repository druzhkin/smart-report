"""Model routing + constants. Read env once at import, override via env vars if set."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# ---- API endpoints ---------------------------------------------------------
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
PERPLEXITY_BASE_URL = os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

# ---- Model routing table ---------------------------------------------------
ROLE_MODELS: dict[str, str] = {
    "planner": os.getenv("PLANNER_MODEL", "anthropic/claude-opus-4"),
    "scout": os.getenv("SCOUT_MODEL", "anthropic/claude-haiku-4.5"),
    "analyst": os.getenv("ANALYST_MODEL", "anthropic/claude-sonnet-4.6"),
    "bisociator": os.getenv("BISOCIATOR_MODEL", "anthropic/claude-opus-4"),
    "summarizer": os.getenv("SUMMARIZER_MODEL", "anthropic/claude-sonnet-4.6"),
}

# Perplexity retrieval model (citations + content)
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar-pro")

# ---- Orchestration constants ----------------------------------------------
MAX_PARALLEL_CELLS = int(os.getenv("MAX_PARALLEL_CELLS", "4"))
REQUEST_TIMEOUT_S = float(os.getenv("REQUEST_TIMEOUT_S", "120"))

# Role → temperature
ROLE_TEMPERATURE: dict[str, float] = {
    "planner": 0.0,
    "scout": 0.2,
    "analyst": 0.3,
    "bisociator": 0.4,
    "summarizer": 0.3,
}


def model_for(role: str) -> str:
    try:
        return ROLE_MODELS[role]
    except KeyError as e:
        raise ValueError(f"unknown role: {role!r}") from e


def temperature_for(role: str) -> float:
    return ROLE_TEMPERATURE.get(role, 0.2)
