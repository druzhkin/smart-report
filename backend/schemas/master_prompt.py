from pydantic import BaseModel, Field


class PromptTechnique(BaseModel):
    name: str
    weight: float = Field(ge=0.0, le=1.0)
    rationale: str


class SectionSchema(BaseModel):
    title: str
    description: str = ""
    required: bool = True
    min_words: int = 0
    max_words: int = 0
    subsections: list[str] = Field(default_factory=list)


class ReportSchema(BaseModel):
    title_template: str = ""
    sections: list[SectionSchema] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    output_format: str = "markdown"
    expected_length: str = ""


class RouterResult(BaseModel):
    task_type: str = Field(..., description="Classified task type from PROMPT_TECHNIQUE_MAP")
    techniques: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class MasterPrompt(BaseModel):
    system_prompt: str
    user_prompt: str
    master_prompt: str = Field(default="", description="Composed master prompt with PROFILE/KNOWLEDGE/REASONING/RELIABILITY")
    techniques_applied: list[PromptTechnique] = Field(default_factory=list)
    report_schema: ReportSchema = Field(default_factory=ReportSchema)
    target_model: str = Field(default="anthropic/claude-sonnet-4")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192)
    estimated_cost_usd: float = Field(default=0.0)
