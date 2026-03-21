from enum import Enum

from loguru import logger

# Cheap dev-mode substitutes (target: <$0.10/run)
DEV_MODEL_MAP: dict[str, str] = {
    "anthropic/claude-opus-4.6": "anthropic/claude-haiku-4.5",
    "anthropic/claude-sonnet-4": "anthropic/claude-haiku-4.5",
    "openai/gpt-5.4": "openai/gpt-4.1-mini",
    "openai/o3": "openai/gpt-4.1-mini",
    "google/gemini-3-flash-preview": "google/gemini-2.5-flash-lite",
    "google/gemini-3.1-pro-preview": "google/gemini-2.5-flash-lite",
    "perplexity/sonar-deep-research": "perplexity/sonar",
}

MODEL_PRICING_ALIASES: dict[str, str] = {
    "sonar": "perplexity/sonar",
    "sonar-pro": "perplexity/sonar-pro",
    "sonar-deep-research": "perplexity/sonar-deep-research",
}


class AgentTask(str, Enum):
    INTAKE = "intake"
    PROMPT_ROUTING = "prompt_routing"
    PROMPT_COMPOSITION = "prompt_composition"
    SUPERVISION = "supervision"
    RESEARCH = "research"
    RESEARCH_DEEP = "research_deep"
    SUMMARIZATION = "summarization"
    REFLECTION = "reflection"
    CRITIQUE = "critique"
    CITATION_VERIFY = "citation_verify"
    VISUALIZATION = "visualization"
    RENDERING = "rendering"
    PRESENTATION = "presentation"
    QA_VISUAL = "qa_visual"
    QA_SUBSTANCE = "qa_substance"


MODEL_MAP: dict[AgentTask, str] = {
    AgentTask.INTAKE: "anthropic/claude-3.5-haiku",
    AgentTask.PROMPT_ROUTING: "openai/gpt-4.1-mini",
    AgentTask.PROMPT_COMPOSITION: "anthropic/claude-opus-4.6",
    AgentTask.SUPERVISION: "openai/gpt-5.4",
    AgentTask.RESEARCH: "anthropic/claude-sonnet-4",
    AgentTask.RESEARCH_DEEP: "perplexity/sonar-deep-research",
    AgentTask.SUMMARIZATION: "google/gemini-3-flash-preview",
    AgentTask.REFLECTION: "anthropic/claude-opus-4.6",
    AgentTask.CRITIQUE: "openai/o3",
    AgentTask.CITATION_VERIFY: "google/gemini-2.5-flash",
    AgentTask.VISUALIZATION: "anthropic/claude-opus-4.6",
    AgentTask.RENDERING: "google/gemini-3.1-pro-preview",
    AgentTask.PRESENTATION: "anthropic/claude-sonnet-4",
    AgentTask.QA_VISUAL: "anthropic/claude-opus-4.6",
    AgentTask.QA_SUBSTANCE: "openai/o3",
}

COST_PER_1K_INPUT: dict[str, float] = {
    # Production models
    "anthropic/claude-3.5-haiku": 0.001,
    "openai/gpt-4.1-mini": 0.0004,
    "openai/gpt-5.4": 0.005,
    "anthropic/claude-opus-4.6": 0.015,
    "anthropic/claude-sonnet-4": 0.003,
    "google/gemini-2.5-flash": 0.000075,
    "google/gemini-3-flash-preview": 0.0001,
    "google/gemini-3.1-pro-preview": 0.00125,
    "perplexity/sonar": 0.001,
    "perplexity/sonar-pro": 0.003,
    "perplexity/sonar-deep-research": 0.005,
    "openai/o3": 0.010,
    # Dev-mode models
    "anthropic/claude-haiku-4.5": 0.0008,
    "google/gemini-2.5-flash-lite": 0.000075,
    "perplexity/sonar": 0.001,
}

COST_PER_1K_OUTPUT: dict[str, float] = {
    # Production models
    "anthropic/claude-3.5-haiku": 0.005,
    "openai/gpt-4.1-mini": 0.0016,
    "openai/gpt-5.4": 0.02,
    "anthropic/claude-opus-4.6": 0.075,
    "anthropic/claude-sonnet-4": 0.015,
    "google/gemini-2.5-flash": 0.0003,
    "google/gemini-3-flash-preview": 0.0001,
    "google/gemini-3.1-pro-preview": 0.005,
    "perplexity/sonar": 0.001,
    "perplexity/sonar-pro": 0.015,
    "perplexity/sonar-deep-research": 0.028,
    "openai/o3": 0.040,
    # Dev-mode models
    "anthropic/claude-haiku-4.5": 0.004,
    "google/gemini-2.5-flash-lite": 0.0003,
    "perplexity/sonar": 0.005,
}


def get_model(task: AgentTask) -> str:
    from backend.config import settings  # avoid circular import at module level
    model = MODEL_MAP[task]
    if settings.dev_mode:
        model = DEV_MODEL_MAP.get(model, model)
        logger.debug(f"[DEV] Model for {task.value}: {model}")
    else:
        logger.debug(f"Model for {task.value}: {model}")
    return model


def normalize_model_name(model: str) -> str:
    return MODEL_PRICING_ALIASES.get(model, model)


def estimate_cost_for_model(model: str, input_tokens: int, output_tokens: int) -> float:
    normalized = normalize_model_name(model)
    input_cost = (input_tokens / 1000) * COST_PER_1K_INPUT.get(normalized, 0.001)
    output_cost = (output_tokens / 1000) * COST_PER_1K_OUTPUT.get(normalized, 0.005)
    return input_cost + output_cost


def estimate_cost(task: AgentTask, input_tokens: int, output_tokens: int) -> float:
    from backend.config import settings
    model = MODEL_MAP[task]
    if settings.dev_mode:
        model = DEV_MODEL_MAP.get(model, model)
    return estimate_cost_for_model(model, input_tokens, output_tokens)
