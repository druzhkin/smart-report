from pydantic import BaseModel, Field


class UserRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User's report request (text or transcribed voice)")
    voice_input: bool = Field(default=False)
    context_files: list[str] = Field(default_factory=list)
    preferred_format: str | None = Field(default=None, description="e.g. 'pdf', 'docx', 'slides'")


class SimilarReport(BaseModel):
    chunk_id: str = ""
    content: str = ""
    score: float = 0.0
    document_name: str = ""


class IntakeResult(BaseModel):
    original_query: str
    cleaned_query: str
    intent: str = Field(..., description="Classified intent: research, analysis, comparison, overview, deep_dive, forecast")
    domain: str = Field(..., description="Detected domain: finance, tech, healthcare, energy, retail, general")
    complexity: str = Field(..., description="low / medium / high")
    depth: str = Field(default="standard", description="light / standard / deep / exhaustive")
    key_entities: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list, max_length=5)
    language: str = Field(default="en")
    similar_reports: list[SimilarReport] = Field(default_factory=list)
    budget_limit: float = Field(default=2.0, description="Budget cap in USD based on depth")
