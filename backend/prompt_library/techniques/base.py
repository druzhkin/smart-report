from abc import ABC, abstractmethod


class PromptTechniqueBase(ABC):
    name: str = "base"
    description: str = ""

    @abstractmethod
    def apply(self, prompt: str, context: dict) -> str:
        ...
