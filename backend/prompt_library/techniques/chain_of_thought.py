from backend.prompt_library.techniques.base import PromptTechniqueBase


class ChainOfThought(PromptTechniqueBase):
    name = "chain_of_thought"
    description = "Encourages step-by-step reasoning"

    def apply(self, prompt: str, context: dict) -> str:
        return f"{prompt}\n\nThink through this step-by-step:\n1. First, identify the key aspects of the question\n2. Analyze each aspect systematically\n3. Consider relationships between findings\n4. Synthesize into a coherent conclusion\n5. Verify your reasoning chain"
