from typing import Any, TypedDict

from backend.schemas.intake import IntakeResult
from backend.schemas.master_prompt import MasterPrompt, RouterResult
from backend.schemas.qa_result import QAResult
from backend.schemas.quality import (
    CitationVerificationResult,
    ReflectResult,
    ResearchCritiqueResult,
)
from backend.schemas.report_schema import ReportOutput, ReportStatus
from backend.schemas.research_result import ParallelBatches, ResearchResult


class AgentState(TypedDict, total=False):
    session_id: str
    report_id: str
    original_request: str
    selected_depth: str
    user_request: dict[str, Any]
    status: ReportStatus
    messages: list[dict[str, str]]
    cost_usd: float

    intake_result: IntakeResult
    router_result: RouterResult
    selected_techniques: list[str]
    master_prompt: MasterPrompt
    data_queries: list[str]
    parallel_batches: ParallelBatches
    research_results: list[ResearchResult]
    report: ReportOutput
    qa_result: QAResult

    citation_verification: CitationVerificationResult
    reflect_result: ReflectResult
    research_critique_result: ResearchCritiqueResult

    chart_paths: list[str]
    presentation_url: str
    presentation_path: str

    critic_score: float
    revision_count: int
    verdict: str
    final_report_paths: list[str]

    current_agent: str
    iteration: int
    qa_iterations: int
    max_iterations: int
    errors: list[str]
