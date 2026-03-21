from backend.prompt_library.techniques.base import PromptTechniqueBase


class DevilAdvocate(PromptTechniqueBase):
    name = "devil_advocate"
    description = "Forces consideration of opposing viewpoints"

    def apply(self, prompt: str, context: dict) -> str:
        return f"""{prompt}

After your main analysis, include a "Devil's Advocate" section:
1. What are the strongest counter-arguments to your conclusions?
2. What assumptions might be wrong?
3. What scenarios would invalidate your analysis?
4. What risks are you potentially underweighting?

Address each counter-argument and explain why your main conclusion still holds (or adjust it)."""
