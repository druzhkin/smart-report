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
    # light: cheapest tier — single fast DR backend + cheap scouts, no contrarian.
    # Target: <$2 per report. Use for drafts, sanity checks, personal research.
    "light": {
        "domains": (2, 3),
        "layers": (1, 2),
        "scouts_per_cell": 2,
        "max_parallel_scouts": 6,
        "max_parallel_analysts": 4,
        "planner_model": "google/gemini-2.5-flash",
        "scout_model": "deepseek/deepseek-chat-v3.1",
        "analyst_model": "google/gemini-2.5-flash",
        "mapper_model": "google/gemini-2.5-flash",
        "bisociator_model": "moonshotai/kimi-k2",
        "perplexity_model": "sonar",
        # Corpus flow knobs (Variant E)
        "corpus_backends": ["valyu", "gpt_researcher"],
        "valyu_mode": "fast",
        "contrarian_enabled": False,
        "consensus_layer": False,
        "doubt_cycle_enabled": False,
        "save_raw_corpus": False,
        "cost_cap_usd": 1.5,
    },
    # standard: production default — 3 DR backends, contrarian ON. Target: $3–5.
    "standard": {
        "domains": (3, 4),
        "layers": (2, 3),
        "scouts_per_cell": 3,
        "max_parallel_scouts": 8,
        "max_parallel_analysts": 4,
        "planner_model": "google/gemini-2.5-flash",
        "scout_model": "deepseek/deepseek-chat-v3.1",
        "analyst_model": "google/gemini-2.5-flash",
        "mapper_model": "google/gemini-2.5-flash",
        "bisociator_model": "moonshotai/kimi-k2",
        "perplexity_model": "sonar-pro",
        "corpus_backends": ["valyu", "sonar_dr", "gpt_researcher"],
        "valyu_mode": "fast",
        "contrarian_enabled": True,
        "consensus_layer": False,
        "doubt_cycle_enabled": False,
        "save_raw_corpus": False,
        "cost_cap_usd": 3.0,
    },
    # deep: valyu_standard for richer sources, same backends. Target: $6–8.
    "deep": {
        "domains": (4, 5),
        "layers": (2, 4),
        "scouts_per_cell": 4,
        "max_parallel_scouts": 10,
        "max_parallel_analysts": 5,
        "planner_model": "google/gemini-2.5-flash",
        "scout_model": "deepseek/deepseek-chat-v3.1",
        "analyst_model": "google/gemini-2.5-flash",
        "mapper_model": "google/gemini-2.5-flash",
        "bisociator_model": "moonshotai/kimi-k2",
        "perplexity_model": "sonar-deep-research",
        "corpus_backends": ["valyu", "sonar_dr", "gpt_researcher"],
        "valyu_mode": "standard",
        "contrarian_enabled": True,
        "consensus_layer": False,
        "doubt_cycle_enabled": False,
        "save_raw_corpus": False,
        "cost_cap_usd": 6.0,
    },
    # premium: adds OpenAI DR + Gemini DR + consensus meta-analysis. Target: $15–25.
    "premium": {
        "domains": (5, 6),
        "layers": (3, 4),
        "scouts_per_cell": 5,
        "max_parallel_scouts": 12,
        "max_parallel_analysts": 6,
        "planner_model": "google/gemini-2.5-flash",
        "scout_model": "deepseek/deepseek-chat-v3.1",
        "analyst_model": "google/gemini-2.5-pro",
        "mapper_model": "google/gemini-2.5-flash",
        "bisociator_model": "moonshotai/kimi-k2",
        "perplexity_model": "sonar-deep-research",
        "corpus_backends": ["valyu", "sonar_dr", "gpt_researcher", "openai_dr", "gemini_dr"],
        "valyu_mode": "fast",
        "contrarian_enabled": True,
        "consensus_layer": True,
        "doubt_cycle_enabled": False,
        "save_raw_corpus": False,
        "cost_cap_usd": 25.0,
    },
}


DEPTH_PROFILES["exhaustive"] = DEPTH_PROFILES["premium"]

TIER_ALIASES: dict[str, str] = {
    "quick_take": "light",
    "investment_brief": "standard",
    "strategy_note": "deep",
    "full_research": "exhaustive",
}


def resolve_tier(tier_or_depth: str) -> str:
    return TIER_ALIASES.get(tier_or_depth, tier_or_depth)


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


def profile_float(key: str, default: float) -> float:
    p = _active_profile.get()
    if p and key in p:
        return float(p[key])
    return default


def profile_bool(key: str, default: bool) -> bool:
    p = _active_profile.get()
    if p and key in p:
        return bool(p[key])
    return default


def profile_str(key: str, default: str) -> str:
    p = _active_profile.get()
    if p and key in p:
        return str(p[key])
    return default


def profile_list(key: str, default: list) -> list:
    p = _active_profile.get()
    if p and key in p and isinstance(p[key], (list, tuple)):
        return list(p[key])
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
    gamma_api_key: str = os.getenv("GAMMA_API_KEY", "")
    gamma_theme_id: str = os.getenv("GAMMA_THEME_ID", "")
    brave_api_key: str = os.getenv("BRAVE_API_KEY", "")
    jina_api_key: str = os.getenv("JINA_API_KEY", "")
    # Deep-research vendors (polling APIs). Keys absent → backend is skipped at runtime.
    parallel_api_key: str = os.getenv("PARALLEL_API_KEY", "")
    valyu_api_key: str = os.getenv("VALYU_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    # Economy switches: defaults favor free fetchers over paid search.
    use_perplexity: bool = os.getenv("USE_PERPLEXITY", "true").lower() in ("1", "true", "yes")
    use_jina_reader: bool = os.getenv("USE_JINA_READER", "true").lower() in ("1", "true", "yes")
    # Per-backend gates for bench matrix. Defaults preserve current production behavior.
    use_academic: bool = os.getenv("USE_ACADEMIC", "true").lower() in ("1", "true", "yes")
    use_cheap_web: bool = os.getenv("USE_CHEAP_WEB", "true").lower() in ("1", "true", "yes")
    use_tavily: bool = os.getenv("USE_TAVILY", "true").lower() in ("1", "true", "yes")
    use_gpt_researcher: bool = os.getenv("USE_GPT_RESEARCHER", "false").lower() in ("1", "true", "yes")
    # Deep-research flags. Default OFF until the operator sets the key; flip per-run via env.
    use_tavily_deep: bool = os.getenv("USE_TAVILY_DEEP", "false").lower() in ("1", "true", "yes")
    use_parallel: bool = os.getenv("USE_PARALLEL", "false").lower() in ("1", "true", "yes")
    use_valyu: bool = os.getenv("USE_VALYU", "false").lower() in ("1", "true", "yes")
    # Variant E — corpus-first research flow: one holistic fetch (Valyu+Sonar DR+gpt-researcher)
    # → LLM-mapped to cells → gap-filling scouts only for low-coverage cells. Replaces 42-scout
    # fanout. Falls back to the legacy flow if disabled or if corpus comes back empty.
    use_corpus_flow: bool = os.getenv("USE_CORPUS_FLOW", "false").lower() in ("1", "true", "yes")
    corpus_min_findings_per_cell: int = int(os.getenv("CORPUS_MIN_FINDINGS_PER_CELL", "5"))
    corpus_valyu_mode: str = os.getenv("CORPUS_VALYU_MODE", "fast")  # fast | standard | heavy | max
    # Premium DR: OpenAI Responses API (o3-deep-research) + Gemini 2.5 Pro with Google Search grounding.
    use_openai_dr: bool = os.getenv("USE_OPENAI_DR", "false").lower() in ("1", "true", "yes")
    use_gemini_dr: bool = os.getenv("USE_GEMINI_DR", "false").lower() in ("1", "true", "yes")
    openai_dr_model: str = os.getenv("OPENAI_DR_MODEL", "o3-deep-research-2025-06-26")
    gemini_dr_model: str = os.getenv("GEMINI_DR_MODEL", "gemini-2.5-pro")
    # Fallback cost estimates (USD per query). Overridden by actual usage when the SDK reports it.
    openai_dr_usd_per_query: float = float(os.getenv("OPENAI_DR_USD", "2.50"))
    gemini_dr_usd_per_query: float = float(os.getenv("GEMINI_DR_USD", "0.50"))
    # Contrarian Pass — post-analyst critic that appends weaknesses + strongest_point per block.
    # Depth tiers override this via profile_bool("contrarian_enabled") once Phase 3 lands.
    use_contrarian_pass: bool = os.getenv("USE_CONTRARIAN_PASS", "true").lower() in ("1", "true", "yes")
    # Tier/model knobs per deep-research vendor.
    tavily_deep_model: str = os.getenv("TAVILY_DEEP_MODEL", "mini")           # mini | auto | pro
    parallel_processor: str = os.getenv("PARALLEL_PROCESSOR", "core")         # base | core | ultra
    valyu_mode: str = os.getenv("VALYU_MODE", "standard")                     # fast | standard | heavy | max
    # Tavily whitelist mode: comma-separated list of domains or empty. When set,
    # Tavily calls pass include_domains to filter out blog/marketing noise.
    tavily_include_domains: str = os.getenv("TAVILY_INCLUDE_DOMAINS", "")

    intake_dialog_enabled: bool = os.getenv("INTAKE_DIALOG_ENABLED", "true").lower() in ("1", "true", "yes")
    intake_model: str = os.getenv("INTAKE_MODEL", "google/gemini-2.5-flash")
    intake_max_turns: int = int(os.getenv("INTAKE_MAX_TURNS", "4"))

    planner_model: str = os.getenv("PLANNER_MODEL", "deepseek/deepseek-chat-v3.1")
    scout_model: str = os.getenv("SCOUT_MODEL", "deepseek/deepseek-chat-v3.1")
    analyst_model: str = os.getenv("ANALYST_MODEL", "google/gemini-2.5-flash")
    mapper_model: str = os.getenv("MAPPER_MODEL", "google/gemini-2.5-flash")
    bisociator_model: str = os.getenv("BISOCIATOR_MODEL", "moonshotai/kimi-k2")

    perplexity_model: str = os.getenv("PERPLEXITY_MODEL", "sonar-deep-research")

    scouts_per_cell: int = int(os.getenv("SCOUTS_PER_CELL", "3"))
    max_parallel_scouts: int = int(os.getenv("MAX_PARALLEL_SCOUTS", "8"))
    max_parallel_analysts: int = int(os.getenv("MAX_PARALLEL_ANALYSTS", "4"))

    # Currency: AWstore (Anthropic proxy) is billed in rubles — 1 credit = 1 ₽, values in
    # llm.PRICING are already in rubles. All other paid APIs are priced in USD on their
    # official dashboards and converted to ₽ via USD_TO_CREDITS at accounting time.
    currency_label: str = os.getenv("CURRENCY_LABEL", "₽")
    usd_to_credits: float = float(os.getenv("USD_TO_CREDITS", "95"))  # ≈ ₽/USD

    # Official USD rates (per API docs). Overridable via ENV.
    # Perplexity sonar: $1/$1 per 1M tokens + $1/1000 req. Typical query ≈ $0.002.
    # Perplexity sonar-pro: $3/$15 per 1M tokens + $5/1000 req. Typical query ≈ $0.014.
    perplexity_usd_sonar: float = float(os.getenv("PPLX_USD_SONAR", "0.002"))
    perplexity_usd_sonar_pro: float = float(os.getenv("PPLX_USD_SONAR_PRO", "0.014"))
    # sonar-deep-research: $2/$8 per 1M tokens + $5/1000 req + $5/1000 reasoning tokens.
    # Measured real-DR: ~175k reasoning tokens + 44 searches → $0.88/call.
    # Keep strategy_cap=200 in corpus_fetch or it falls to 20s fast-fallback with 0 citations.
    perplexity_usd_sonar_dr: float = float(os.getenv("PPLX_USD_SONAR_DR", "0.90"))
    # Tavily advanced search: $0.008 per request.
    tavily_usd_per_query: float = float(os.getenv("TAVILY_USD", "0.008"))
    # Tavily DR (dynamic pricing: credits × $0.005–$0.008). Medians by tier at $0.008/credit:
    # mini (4–110cr) ≈ $0.25; auto ≈ $0.50; pro (15–250cr) ≈ $1.00. Used only if SDK doesn't
    # surface credits_used on the response; otherwise we charge credits × tavily_usd_per_credit.
    tavily_deep_usd_per_query: float = float(os.getenv("TAVILY_DEEP_USD", "0.25"))
    tavily_usd_per_credit: float = float(os.getenv("TAVILY_USD_PER_CREDIT", "0.008"))
    # Parallel.ai exact tiers: lite $0.005 / base $0.01 / core $0.025 / core2x $0.05 / pro $0.10 /
    # ultra $0.30 (+ 2x/4x/8x). Default matches PARALLEL_PROCESSOR=core.
    parallel_usd_per_query: float = float(os.getenv("PARALLEL_USD", "0.025"))
    # Valyu cost comes back on result.cost — this is a fallback estimate for the mode tiers.
    valyu_usd_per_query: float = float(os.getenv("VALYU_USD", "0.50"))
    # Firecrawl growth plan ≈ $0.004 per scraped page.
    firecrawl_usd_per_result: float = float(os.getenv("FIRECRAWL_USD", "0.004"))
    # Gamma paid plan ≈ $0.15 per presentation generation.
    gamma_usd_per_generation: float = float(os.getenv("GAMMA_USD", "0.15"))



settings = Settings()


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")
