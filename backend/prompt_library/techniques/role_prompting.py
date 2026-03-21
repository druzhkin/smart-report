import json
from pathlib import Path

from backend.prompt_library.techniques.base import PromptTechniqueBase


class RolePrompting(PromptTechniqueBase):
    name = "role_prompting"
    description = "Assigns expert persona for domain-specific analysis"

    def apply(self, prompt: str, context: dict) -> str:
        domain = context.get("domain", "general")
        persona = self._get_persona(domain)
        return f"You are {persona}.\n\n{prompt}"

    def _get_persona(self, domain: str) -> str:
        path = Path("prompt_library/knowledge_base/role_personas.json")
        if path.exists():
            with open(path) as f:
                personas = json.load(f)
                if domain in personas:
                    return personas[domain]
        defaults = {
            "finance": "a senior McKinsey partner with 20 years of financial advisory experience",
            "tech": "a principal analyst at Gartner specializing in emerging technology",
            "healthcare": "a senior healthcare strategy consultant with clinical research background",
            "general": "a senior strategy consultant at a top-tier consulting firm",
        }
        return defaults.get(domain, defaults["general"])
