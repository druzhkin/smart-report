from backend.prompt_library.techniques.base import PromptTechniqueBase


class TreeOfThought(PromptTechniqueBase):
    name = "tree_of_thought"
    description = "Explores multiple reasoning paths and selects the best"

    def apply(self, prompt: str, context: dict) -> str:
        return f"""{prompt}

Explore this problem using multiple reasoning paths:

Path A: Consider from a quantitative/data-driven perspective
Path B: Consider from a qualitative/strategic perspective
Path C: Consider from a contrarian/risk perspective

For each path:
- Develop the key arguments
- Assess the strength of evidence
- Rate confidence (0-1)

Then synthesize the strongest elements from each path into your final analysis."""
