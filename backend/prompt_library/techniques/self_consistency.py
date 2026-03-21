from backend.prompt_library.techniques.base import PromptTechniqueBase


class SelfConsistency(PromptTechniqueBase):
    name = "self_consistency"
    description = "Generate multiple answers and find consensus"

    def apply(self, prompt: str, context: dict) -> str:
        return f"""{prompt}

Generate three independent analyses of this topic. For each:
1. Approach from a different angle
2. Arrive at your conclusion independently

Then compare all three analyses:
- Identify points of agreement (high confidence)
- Identify contradictions (flag for review)
- Produce a final synthesized answer based on consensus"""
