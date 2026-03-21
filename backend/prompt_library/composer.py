from loguru import logger

from backend.prompt_library.techniques.base import PromptTechniqueBase
from backend.prompt_library.techniques.chain_of_thought import ChainOfThought
from backend.prompt_library.techniques.few_shot import FewShot
from backend.prompt_library.techniques.tree_of_thought import TreeOfThought
from backend.prompt_library.techniques.self_consistency import SelfConsistency
from backend.prompt_library.techniques.role_prompting import RolePrompting
from backend.prompt_library.techniques.meta_prompting import MetaPrompting
from backend.prompt_library.techniques.structured_output import StructuredOutput
from backend.prompt_library.techniques.constraint import Constraint
from backend.prompt_library.techniques.devil_advocate import DevilAdvocate

REGISTRY: dict[str, type[PromptTechniqueBase]] = {
    "chain_of_thought": ChainOfThought,
    "few_shot": FewShot,
    "tree_of_thought": TreeOfThought,
    "self_consistency": SelfConsistency,
    "role_prompting": RolePrompting,
    "meta_prompting": MetaPrompting,
    "structured_output": StructuredOutput,
    "constraint": Constraint,
    "devil_advocate": DevilAdvocate,
}


def compose_prompt(base_prompt: str, techniques: list[str], context: dict | None = None) -> str:
    ctx = context or {}
    result = base_prompt
    for name in techniques:
        cls = REGISTRY.get(name)
        if not cls:
            logger.warning(f"Unknown technique: {name}")
            continue
        technique = cls()
        result = technique.apply(result, ctx)
        logger.debug(f"Applied technique: {name}")
    return result
