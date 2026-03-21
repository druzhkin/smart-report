from loguru import logger

from backend.schemas.intake import IntakeResult


TECHNIQUE_RULES: dict[str, list[str]] = {
    "high": ["chain_of_thought", "tree_of_thought", "self_consistency", "devil_advocate", "structured_output"],
    "medium": ["chain_of_thought", "few_shot", "role_prompting", "structured_output"],
    "low": ["few_shot", "role_prompting", "structured_output"],
}

DOMAIN_TECHNIQUES: dict[str, list[str]] = {
    "finance": ["constraint", "self_consistency", "devil_advocate"],
    "tech": ["chain_of_thought", "meta_prompting"],
    "healthcare": ["chain_of_thought", "constraint", "self_consistency"],
    "general": ["few_shot", "role_prompting"],
}


def select_techniques(intake: IntakeResult) -> list[str]:
    base = TECHNIQUE_RULES.get(intake.complexity, TECHNIQUE_RULES["medium"])
    domain_extra = DOMAIN_TECHNIQUES.get(intake.domain, DOMAIN_TECHNIQUES["general"])
    combined = list(dict.fromkeys(base + domain_extra))
    logger.debug(f"Selected techniques for {intake.complexity}/{intake.domain}: {combined}")
    return combined
