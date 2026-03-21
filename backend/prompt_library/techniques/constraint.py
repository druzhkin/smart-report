from backend.prompt_library.techniques.base import PromptTechniqueBase


class Constraint(PromptTechniqueBase):
    name = "constraint"
    description = "Adds quality constraints and guardrails"

    def apply(self, prompt: str, context: dict) -> str:
        constraints = context.get("constraints", [
            "Every claim must be supported by a specific source",
            "Distinguish between facts, estimates, and opinions",
            "Flag any data older than 2 years",
            "Acknowledge uncertainty where applicable",
            "Avoid superlatives unless backed by data",
        ])
        constraints_text = "\n".join(f"- {c}" for c in constraints)
        return f"""{prompt}

CONSTRAINTS (must follow strictly):
{constraints_text}"""
