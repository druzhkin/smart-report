import json
from pathlib import Path

from backend.prompt_library.techniques.base import PromptTechniqueBase


class FewShot(PromptTechniqueBase):
    name = "few_shot"
    description = "Provides examples to guide output format"

    def apply(self, prompt: str, context: dict) -> str:
        domain = context.get("domain", "")
        examples = self._load_examples(domain)
        if not examples:
            return prompt
        examples_text = "\n\n".join(
            f"Example {i+1}:\nInput: {ex.get('input', '')}\nOutput: {ex.get('output', '')}"
            for i, ex in enumerate(examples[:3])
        )
        return f"{prompt}\n\nHere are examples of expected output:\n{examples_text}\n\nNow produce your analysis following the same format."

    def _load_examples(self, domain: str) -> list[dict]:
        mapping = {
            "finance": "investment_memo.json",
            "market": "market_analysis.json",
            "science": "scientific_review.json",
        }
        filename = mapping.get(domain)
        if not filename:
            return []
        path = Path(f"prompt_library/knowledge_base/few_shot_examples/{filename}")
        if not path.exists():
            return []
        with open(path) as f:
            return json.load(f).get("examples", [])
