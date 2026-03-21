from backend.prompt_library.techniques.base import PromptTechniqueBase


class MetaPrompting(PromptTechniqueBase):
    name = "meta_prompting"
    description = "Asks the model to design its own optimal approach"

    def apply(self, prompt: str, context: dict) -> str:
        return f"""Before answering the following question, first design your optimal analysis approach:

1. What frameworks or models are most relevant?
2. What data points would be most valuable?
3. What potential biases should you watch for?
4. What structure would best present the findings?

Design your approach, then execute it:

{prompt}"""
