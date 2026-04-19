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


# ---------------------------------------------------------------------------
# v4.5 Bake-off winner configuration
# ---------------------------------------------------------------------------
# Generated after bakeoff run 2026-04-19T13:25:41Z
# To revert to Opus everywhere, set all MODEL fields to "anthropic/claude-opus-4.7"
#
# Bake-off results summary:
#   §1 PM:        GPT-4o (100/100, $0.02/call vs $0.18 Opus — all tied, cheapest wins)
#   §2 Intake:    Haiku 4.5 fallback (>70% retention vs Opus baseline)
#   §3 Analyzer:  Opus 4.7 (90/100 — only model above 70 floor; Sonnet gets 60)
#   §4 Synth:     Sonnet 4.6 (88/100 — beats Opus 83/100 at 36% lower cost)
#   §5 Critic:    Opus 4.7 fixed (per user decision)
#   Total prod run cost (winner): ~$2.69 vs ~$3.06 Opus-everywhere (-12%)


class ModelConfig:
    """Winner model configuration from v4.5 bake-off (2026-04-19)."""

    # §1 Prompt Master: GPT-4o scores 100/100, costs ~$0.02 vs $0.18 Opus
    # Fallback: Sonnet 4.6 (also 100/100, $0.10) if GPT-4o prompts prove too short
    PROMPT_MASTER_MODEL: str = "openai/gpt-4o"

    # §2 Intake: deterministic parser runs first (no LLM).
    # LLM fallback only triggered for legacy files without Сводная таблица данных section.
    # Haiku 4.5 approved as fallback: >70% retention ratio vs Opus baseline at -81% cost.
    INTAKE_LLM_FALLBACK_MODEL: str = "anthropic/claude-haiku-4.5"

    # §3 Analyzer: only Opus passes 70 floor (90/100).
    # Sonnet gets 60 (fails conflicts_ge5 and all_numeric_facts=0).
    # Revisit if Analyzer prompt is tuned for non-Opus models.
    ANALYZER_MODEL: str = "anthropic/claude-opus-4.7"

    # §4 Synthesizer: Sonnet 4.6 (reverted from Opus after prod blocker).
    # 2026-04-19 evening: on real user session with Russian content (quotes, citations),
    # Opus consistently produced malformed JSON mid-response (char 63713 JSONDecodeError).
    # All 3 retries failed → endpoint returned 400 instantly, user blocked.
    # Sonnet 4.6 passed bake-off with 88/100 auto-score (vs Opus 83), valid JSON,
    # 36% cheaper, 2-3× faster. Revisit Opus when JSON reliability bug diagnosed.
    SYNTHESIZER_MODEL: str = "anthropic/claude-sonnet-4.6"

    # §5 Critic: Opus fixed per user decision (FP risk too high to downgrade)
    SYNTHESIS_CRITIC_MODEL: str = "anthropic/claude-opus-4.7"
