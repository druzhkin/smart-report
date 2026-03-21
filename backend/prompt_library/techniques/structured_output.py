from backend.prompt_library.techniques.base import PromptTechniqueBase


class StructuredOutput(PromptTechniqueBase):
    name = "structured_output"
    description = "Enforces structured JSON output format"

    def apply(self, prompt: str, context: dict) -> str:
        return f"""{prompt}

Return your response as valid JSON with the following structure:
{{
    "title": "string",
    "executive_summary": "string (2-3 paragraphs)",
    "sections": [
        {{
            "title": "string",
            "content": "string (detailed analysis)",
            "order": "integer",
            "sources": ["url1", "url2"]
        }}
    ],
    "key_insights": ["insight1", "insight2"],
    "confidence": 0.0-1.0
}}"""
