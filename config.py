"""Runtime configuration. Loaded from .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
PROMPTS_DIR = ROOT / "prompts"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "")
    firecrawl_api_key: str = os.getenv("FIRECRAWL_API_KEY", "")

    planner_model: str = os.getenv("PLANNER_MODEL", "anthropic/claude-opus-4.5")
    scout_model: str = os.getenv("SCOUT_MODEL", "anthropic/claude-haiku-4.5")
    analyst_model: str = os.getenv("ANALYST_MODEL", "anthropic/claude-sonnet-4.5")
    bisociator_model: str = os.getenv("BISOCIATOR_MODEL", "anthropic/claude-opus-4.5")

    perplexity_model: str = os.getenv("PERPLEXITY_MODEL", "sonar-pro")

    scouts_per_cell: int = int(os.getenv("SCOUTS_PER_CELL", "3"))
    max_parallel_scouts: int = int(os.getenv("MAX_PARALLEL_SCOUTS", "8"))
    max_parallel_analysts: int = int(os.getenv("MAX_PARALLEL_ANALYSTS", "4"))

    use_mock_search: bool = os.getenv("USE_MOCK_SEARCH", "0") == "1"


settings = Settings()


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")
