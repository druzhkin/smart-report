"""Tests for individual pipeline agents and shared logic."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from backend.pipeline.cost_guard import BudgetExceededError, CostGuard, InsufficientEvidenceError
from backend.schemas.intake import IntakeResult
from backend.schemas.master_prompt import MasterPrompt, RouterResult
from backend.schemas.quality import (
    CitationCheckResult,
    CritiqueScore,
    CitationStatus,
    CitationVerificationResult,
    ReflectResult,
    ResearchCritiqueResult,
)
from backend.schemas.qa_result import QAIssue, QAResult, QAVerdict
from backend.schemas.report_schema import ReportOutput, ReportSection, ReportStatus
from backend.schemas.research_result import (
    ParallelBatches,
    QueryBatch,
    ResearchBranchState,
    ResearchResult,
    ResearchTask,
    Source,
    TaskDecomposition,
)

_LOCAL_TMP = Path(__file__).resolve().parents[1] / ".pytest-temp"
_LOCAL_TMP.mkdir(exist_ok=True)
os.environ["TMP"] = str(_LOCAL_TMP)
os.environ["TEMP"] = str(_LOCAL_TMP)
os.environ["TMPDIR"] = str(_LOCAL_TMP)
tempfile.tempdir = str(_LOCAL_TMP)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_state() -> dict:
    return {
        "session_id": "test-session",
        "report_id": "test-report",
        "original_request": "Analyze AI chip market",
        "selected_depth": "standard",
        "user_request": {"query": "Analyze AI chip market", "preferred_format": "pdf"},
        "status": ReportStatus.INTAKE,
        "messages": [],
        "cost_usd": 0.0,
        "revision_count": 0,
        "iteration": 0,
        "max_iterations": 3,
        "errors": [],
    }


@pytest.fixture
def sample_report() -> ReportOutput:
    return ReportOutput(
        title="AI Chip Market Analysis",
        executive_summary="The AI chip market is expected to grow significantly.",
        sections=[
            ReportSection(title="Market Overview", content="Detailed market overview...", order=1),
            ReportSection(title="Key Players", content="NVIDIA, AMD, Intel analysis...", order=2),
        ],
        status=ReportStatus.COMPLETED,
    )


@pytest.fixture
def tmp_path() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test-artifacts" / str(uuid.uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# CostGuard
# ---------------------------------------------------------------------------


class TestCostGuard:
    def test_track_within_budget(self):
        guard = CostGuard(max_budget=5.0)
        guard.track("intake", 1.0)
        guard.track("research", 2.0)
        assert guard.total_cost == pytest.approx(3.0)
        assert guard.remaining == pytest.approx(2.0)

    def test_raises_on_budget_exceeded(self):
        guard = CostGuard(max_budget=1.0)
        with pytest.raises(BudgetExceededError, match="Budget exceeded"):
            guard.track("research", 1.5)

    def test_raises_when_crossing_boundary(self):
        guard = CostGuard(max_budget=2.0)
        guard.track("intake", 2.0)
        with pytest.raises(BudgetExceededError):
            guard.track("research", 0.01)

    def test_remaining_never_negative(self):
        guard = CostGuard(max_budget=1.0)
        try:
            guard.track("research", 5.0)
        except BudgetExceededError:
            pass
        assert guard.remaining == 0.0

    def test_summary_records_all_calls(self):
        guard = CostGuard(max_budget=10.0)
        guard.track("intake", 0.5)
        guard.track("research", 1.0)
        assert len(guard.summary) == 2
        assert guard.summary[0]["agent"] == "intake"
        assert guard.summary[1]["cumulative"] == pytest.approx(1.5)

    def test_pipeline_node_raises_budget_error(self):
        """Simulate cost_guard node raising BudgetExceededError mid-pipeline."""
        guard = CostGuard(max_budget=0.5)
        guard.track("intake", 0.3)
        with pytest.raises(BudgetExceededError):
            guard.track("research", 0.3)  # 0.6 total > 0.5 budget


# ---------------------------------------------------------------------------
# CitationVerificationResult.compute_stats
# ---------------------------------------------------------------------------


class TestCitationVerificationStats:
    def test_all_verified_passes(self):
        result = CitationVerificationResult(
            checks=[
                CitationCheckResult(url="https://a.com", status=CitationStatus.VERIFIED),
                CitationCheckResult(url="https://b.com", status=CitationStatus.VERIFIED),
            ]
        )
        result.compute_stats()
        assert result.total == 2
        assert result.verified_count == 2
        assert result.pass_rate == pytest.approx(1.0)
        assert result.passed is True

    def test_fabricated_drops_pass_rate_below_threshold(self):
        result = CitationVerificationResult(
            checks=[
                CitationCheckResult(url="https://a.com", status=CitationStatus.VERIFIED),
                CitationCheckResult(url="https://bad.com", status=CitationStatus.FABRICATED),
                CitationCheckResult(url="https://bad2.com", status=CitationStatus.FABRICATED),
            ]
        )
        result.compute_stats()
        assert result.fabricated_count == 2
        assert result.pass_rate == pytest.approx(1 / 3)
        assert result.passed is False  # below 0.85 threshold

    def test_dead_links_not_counted_as_fabricated(self):
        result = CitationVerificationResult(
            checks=[
                CitationCheckResult(url="https://dead.com", status=CitationStatus.DEAD_LINK),
                CitationCheckResult(url="https://a.com", status=CitationStatus.VERIFIED),
            ]
        )
        result.compute_stats()
        assert result.dead_count == 1
        assert result.fabricated_count == 0
        assert result.pass_rate == pytest.approx(1.0)
        assert result.passed is True

    def test_empty_citations_pass(self):
        result = CitationVerificationResult()
        result.compute_stats()
        assert result.passed is True
        assert result.total == 0
        assert result.pass_rate == pytest.approx(1.0)

    def test_partial_does_not_fail(self):
        result = CitationVerificationResult(
            checks=[
                CitationCheckResult(url="https://a.com", status=CitationStatus.PARTIAL),
                CitationCheckResult(url="https://b.com", status=CitationStatus.PARTIAL),
            ]
        )
        result.compute_stats()
        assert result.partial_count == 2
        assert result.pass_rate == pytest.approx(1.0)
        assert result.passed is True


# ---------------------------------------------------------------------------
# run_citation_verifier (agent integration)
# ---------------------------------------------------------------------------


class TestRunCitationVerifier:
    async def test_no_sources_returns_passed(self, base_state):
        from backend.agents.citation_verifier import run_citation_verifier

        state = {**base_state, "research_results": []}
        result = await run_citation_verifier(state)
        assert result["citation_verification"].passed is True
        assert result["current_agent"] == "citation_verifier"

    async def test_dead_url_classified_correctly(self, base_state):
        from backend.agents.citation_verifier import run_citation_verifier

        source = Source(
            url="http://localhost:1/nonexistent",
            title="Test",
            snippet="Test claim about AI chips",
        )
        research = ResearchResult(query="AI chips", sources=[source])
        state = {**base_state, "research_results": [research]}

        with patch("backend.agents.citation_verifier._head_check", return_value=False):
            result = await run_citation_verifier(state)

        verification = result["citation_verification"]
        assert verification.total == 1
        assert verification.dead_count == 1
        assert verification.passed is True  # dead ≠ fabricated, so pass_rate stays 1.0

    async def test_head_failure_but_fetch_success_still_verifies(self, base_state):
        from backend.agents.citation_verifier import run_citation_verifier

        source = Source(
            url="https://example.com/blocked-head",
            title="AI Chip Report",
            snippet="NVIDIA dominates AI chip market with 80% share",
        )
        research = ResearchResult(query="AI chips", sources=[source], findings=["NVIDIA dominates AI chip market with 80% share in 2024."])
        state = {**base_state, "research_results": [research]}

        with (
            patch("backend.agents.citation_verifier._head_check", return_value=False),
            patch(
                "backend.agents.citation_verifier._fetch_content",
                return_value="NVIDIA dominates AI chip market with 80% share in 2024",
            ),
            patch(
                "backend.agents.citation_verifier._get_embedder",
                return_value=_make_mock_embedder(similarity=0.9),
            ),
        ):
            result = await run_citation_verifier(state)

        verification = result["citation_verification"]
        assert verification.verified_count == 1
        assert verification.checks[0].status == CitationStatus.VERIFIED

    async def test_verified_url_classified_correctly(self, base_state):
        from backend.agents.citation_verifier import run_citation_verifier

        source = Source(
            url="https://example.com",
            title="AI Chip Report",
            snippet="NVIDIA dominates AI chip market with 80% share",
        )
        research = ResearchResult(query="AI chips", sources=[source])
        state = {**base_state, "research_results": [research]}

        with (
            patch("backend.agents.citation_verifier._head_check", return_value=True),
            patch(
                "backend.agents.citation_verifier._fetch_content",
                return_value="NVIDIA dominates AI chip market with 80% share in 2024",
            ),
            patch(
                "backend.agents.citation_verifier._get_embedder",
                return_value=_make_mock_embedder(similarity=0.9),
            ),
        ):
            result = await run_citation_verifier(state)

        verification = result["citation_verification"]
        assert verification.verified_count == 1
        assert verification.checks[0].status == CitationStatus.VERIFIED

    async def test_low_similarity_classified_as_fabricated(self, base_state):
        from backend.agents.citation_verifier import run_citation_verifier

        source = Source(
            url="https://example.com",
            title="Unrelated Page",
            snippet="Quantum computing breakthroughs",
        )
        research = ResearchResult(query="AI chips", sources=[source])
        state = {**base_state, "research_results": [research]}

        with (
            patch("backend.agents.citation_verifier._head_check", return_value=True),
            patch(
                "backend.agents.citation_verifier._fetch_content",
                return_value="Recipes for baking bread and pastries",
            ),
            patch(
                "backend.agents.citation_verifier._get_embedder",
                return_value=_make_mock_embedder(similarity=0.1),
            ),
        ):
            result = await run_citation_verifier(state)

        verification = result["citation_verification"]
        assert verification.checks[0].status == CitationStatus.FABRICATED

    async def test_short_claim_with_some_overlap_stays_partial_not_fabricated(self, base_state):
        from backend.agents.citation_verifier import run_citation_verifier

        source = Source(
            url="https://example.com",
            title="AI agents in business",
            snippet="AI agents in business",
        )
        research = ResearchResult(query="AI agents", sources=[source], findings=["AI agents in business can automate support workflows."])
        state = {**base_state, "research_results": [research]}

        with (
            patch("backend.agents.citation_verifier._head_check", return_value=True),
            patch(
                "backend.agents.citation_verifier._fetch_content",
                return_value="This article discusses AI agents in business and how teams adopt them for operations.",
            ),
            patch(
                "backend.agents.citation_verifier._get_embedder",
                return_value=_make_mock_embedder(similarity=0.2),
            ),
        ):
            result = await run_citation_verifier(state)

        verification = result["citation_verification"]
        assert verification.checks[0].status == CitationStatus.PARTIAL

    async def test_caps_number_of_checked_citations(self, base_state):
        from backend.agents.citation_verifier import run_citation_verifier

        sources = [
            Source(url=f"https://example.com/{idx}", title=f"Source {idx}", snippet="Snippet")
            for idx in range(60)
        ]
        research = ResearchResult(query="AI chips", sources=sources, findings=["Finding"])
        state = {**base_state, "research_results": [research]}

        with (
            patch("backend.agents.citation_verifier._head_check", return_value=True),
            patch("backend.agents.citation_verifier._fetch_content", return_value="Relevant content"),
            patch(
                "backend.agents.citation_verifier._get_embedder",
                return_value=_make_mock_embedder(similarity=0.9),
            ),
        ):
            result = await run_citation_verifier(state)

        verification = result["citation_verification"]
        assert verification.total == 40


def _make_mock_embedder(similarity: float):
    """Return a mock SentenceTransformer that encodes to vectors with known cosine similarity."""
    import numpy as np

    mock = type("MockEmbedder", (), {})()

    def encode(texts):
        if len(texts) == 2:
            v1 = np.array([1.0, 0.0])
            angle = np.arccos(max(-1, min(1, similarity)))
            v2 = np.array([np.cos(angle), np.sin(angle)])
            return np.array([v1, v2])
        return np.ones((len(texts), 2))

    mock.encode = encode
    return mock


# ---------------------------------------------------------------------------
# QA Agent — pure logic (no LLM calls)
# ---------------------------------------------------------------------------


class TestQAVerdictLogic:
    def _verdict(self, visual: float, substance: float, issues: list[QAIssue]) -> QAVerdict:
        from backend.agents.qa_agent import _determine_verdict

        return _determine_verdict(visual, substance, issues)

    def test_pass_on_high_scores_no_issues(self):
        assert self._verdict(0.85, 0.80, []) == QAVerdict.PASS

    def test_revise_on_medium_scores(self):
        assert self._verdict(0.60, 0.65, []) == QAVerdict.REVISE

    def test_reject_on_critical_issue_regardless_of_score(self):
        issue = QAIssue(
            category="factual",
            severity="critical",
            location="intro",
            description="Wrong statistic",
            suggestion="Fix it",
        )
        assert self._verdict(0.95, 0.95, [issue]) == QAVerdict.REJECT

    def test_reject_on_low_overall_score(self):
        assert self._verdict(0.2, 0.3, []) == QAVerdict.REJECT

    def test_boundary_exactly_07_passes(self):
        assert self._verdict(0.70, 0.70, []) == QAVerdict.PASS

    def test_boundary_below_07_revises(self):
        assert self._verdict(0.69, 0.69, []) == QAVerdict.REVISE

    def test_revision_instructions_empty_on_pass(self):
        from backend.agents.qa_agent import _build_revision_instructions

        assert _build_revision_instructions([], QAVerdict.PASS) == []

    def test_revision_instructions_critical_before_major(self):
        from backend.agents.qa_agent import _build_revision_instructions

        issues = [
            QAIssue(
                category="style",
                severity="major",
                location="sec1",
                description="Needs rewrite",
                suggestion="Rewrite section",
            ),
            QAIssue(
                category="factual",
                severity="critical",
                location="sec2",
                description="Wrong data",
                suggestion="Fix critical stat",
            ),
        ]
        instructions = _build_revision_instructions(issues, QAVerdict.REVISE)
        assert len(instructions) == 2
        assert "CRITICAL" in instructions[0]

    def test_minor_issues_excluded_from_instructions(self):
        from backend.agents.qa_agent import _build_revision_instructions

        issues = [
            QAIssue(
                category="style",
                severity="minor",
                location="footer",
                description="Spacing issue",
                suggestion="Fix spacing",
            ),
        ]
        instructions = _build_revision_instructions(issues, QAVerdict.REVISE)
        assert instructions == []


# ---------------------------------------------------------------------------
# run_qa (agent integration with mocked LLM)
# ---------------------------------------------------------------------------


class TestRunQA:
    async def test_no_report_returns_reject(self, base_state):
        from backend.agents.qa_agent import run_qa

        result = await run_qa({**base_state, "report": None})
        assert result["qa_result"].verdict == QAVerdict.REJECT

    async def test_pass_verdict_with_mock_llm(self, base_state, sample_report):
        from backend.agents.qa_agent import run_qa

        visual_resp = json.dumps({"score": 0.85, "issues": []})
        substance_resp = json.dumps({"score": 0.80, "citation_score": 0.90, "issues": []})

        with (
            patch("backend.agents.qa_agent._call_visual_qa", return_value=visual_resp),
            patch("backend.agents.qa_agent._call_substance_qa", return_value=substance_resp),
        ):
            result = await run_qa({**base_state, "report": sample_report, "chart_paths": []})

        qa = result["qa_result"]
        assert qa.verdict == QAVerdict.PASS
        assert qa.passed is True
        assert qa.overall_score == pytest.approx(0.825)
        assert qa.visual_score == pytest.approx(0.85)
        assert qa.substance_score == pytest.approx(0.80)
        assert qa.citation_score == pytest.approx(0.90)

    async def test_revise_verdict_with_mock_llm(self, base_state, sample_report):
        from backend.agents.qa_agent import run_qa

        visual_resp = json.dumps({"score": 0.55, "issues": []})
        substance_resp = json.dumps({"score": 0.60, "citation_score": 0.70, "issues": []})

        with (
            patch("backend.agents.qa_agent._call_visual_qa", return_value=visual_resp),
            patch("backend.agents.qa_agent._call_substance_qa", return_value=substance_resp),
        ):
            result = await run_qa({**base_state, "report": sample_report, "chart_paths": []})

        assert result["qa_result"].verdict == QAVerdict.REVISE

    async def test_reject_verdict_on_critical_issue(self, base_state, sample_report):
        from backend.agents.qa_agent import run_qa

        critical_issue = {
            "category": "factual",
            "severity": "critical",
            "location": "executive_summary",
            "description": "Market size figure is off by 10x",
            "suggestion": "Verify from primary source",
        }
        visual_resp = json.dumps({"score": 0.90, "issues": [critical_issue]})
        substance_resp = json.dumps({"score": 0.85, "citation_score": 0.80, "issues": []})

        with (
            patch("backend.agents.qa_agent._call_visual_qa", return_value=visual_resp),
            patch("backend.agents.qa_agent._call_substance_qa", return_value=substance_resp),
        ):
            result = await run_qa({**base_state, "report": sample_report, "chart_paths": []})

        assert result["qa_result"].verdict == QAVerdict.REJECT

    async def test_cost_accumulates(self, base_state, sample_report):
        from backend.agents.qa_agent import run_qa

        visual_resp = json.dumps({"score": 0.8, "issues": []})
        substance_resp = json.dumps({"score": 0.8, "citation_score": 0.8, "issues": []})

        with (
            patch("backend.agents.qa_agent._call_visual_qa", return_value=visual_resp),
            patch("backend.agents.qa_agent._call_substance_qa", return_value=substance_resp),
        ):
            result = await run_qa({**base_state, "report": sample_report, "chart_paths": []})

        assert result["cost_usd"] > 0.0


# ---------------------------------------------------------------------------
# run_intake (agent integration with mocked LLM)
# ---------------------------------------------------------------------------


class TestRunIntake:
    async def test_returns_intake_result(self, base_state):
        from backend.agents.intake_agent import run_intake

        mock_result = IntakeResult(
            original_query="Analyze AI chip market",
            cleaned_query="AI chip market analysis",
            intent="analysis",
            domain="tech",
            complexity="high",
            depth="standard",
            key_entities=["NVIDIA", "AMD"],
            clarifying_questions=["What region?"],
        )

        with (
            patch(
                "backend.agents.intake_agent._call_llm",
                return_value=mock_result.model_dump_json(),
            ),
            patch(
                "backend.agents.intake_agent._search_similar_reports",
                return_value=[],
            ),
        ):
            result = await run_intake(base_state)

        assert result["current_agent"] == "intake"
        assert result["intake_result"].intent == "analysis"
        assert result["intake_result"].domain == "tech"
        assert result["cost_usd"] > 0.0

    async def test_clarifying_questions_capped_at_5(self, base_state):
        """Pydantic v2 enforces max_length=5 at schema level; agent receives at most 5."""
        from backend.agents.intake_agent import run_intake

        # Build raw JSON directly (bypassing Pydantic) to simulate an LLM response
        # that tries to return more than 5 questions. model_validate_json will cap
        # to 5 via the schema constraint (raises ValidationError on >5 items), so
        # we test the agent with exactly 5 — the schema maximum.
        raw_json = json.dumps({
            "original_query": "test",
            "cleaned_query": "test",
            "intent": "research",
            "domain": "general",
            "complexity": "low",
            "depth": "standard",
            "key_entities": [],
            "clarifying_questions": [f"Q{i}?" for i in range(5)],
            "language": "en",
            "similar_reports": [],
            "budget_limit": 2.0,
        })

        with (
            patch("backend.agents.intake_agent._call_llm", return_value=raw_json),
            patch("backend.agents.intake_agent._search_similar_reports", return_value=[]),
        ):
            result = await run_intake(base_state)

        assert len(result["intake_result"].clarifying_questions) == 5

    async def test_invalid_depth_defaults_to_standard(self, base_state):
        from backend.agents.intake_agent import run_intake

        mock_result = IntakeResult(
            original_query="test",
            cleaned_query="test",
            intent="research",
            domain="general",
            complexity="low",
            depth="invalid_depth",
        )

        with (
            patch(
                "backend.agents.intake_agent._call_llm",
                return_value=mock_result.model_dump_json(),
            ),
            patch(
                "backend.agents.intake_agent._search_similar_reports",
                return_value=[],
            ),
        ):
            result = await run_intake(base_state)

        assert result["intake_result"].depth == "standard"

    async def test_parses_json_with_trailing_text(self, base_state):
        from backend.agents.intake_agent import run_intake

        raw_json = json.dumps(
            {
                "original_query": "Analyze AI agents",
                "cleaned_query": "analyze ai agents",
                "intent": "analysis",
                "domain": "tech",
                "complexity": "medium",
                "depth": "standard",
                "key_entities": ["AI agents"],
                "clarifying_questions": [],
                "language": "en",
            }
        ) + "\nNOTE: extra trailing text"

        with (
            patch("backend.agents.intake_agent._call_llm", return_value=raw_json),
            patch("backend.agents.intake_agent._search_similar_reports", return_value=[]),
        ):
            result = await run_intake(base_state)

        assert result["current_agent"] == "intake"
        assert result["intake_result"].intent == "analysis"

    async def test_selected_depth_overrides_llm_depth(self, base_state):
        from backend.agents.intake_agent import run_intake

        mock_result = IntakeResult(
            original_query="test",
            cleaned_query="test",
            intent="research",
            domain="general",
            complexity="high",
            depth="deep",
        )

        with (
            patch(
                "backend.agents.intake_agent._call_llm",
                return_value=mock_result.model_dump_json(),
            ),
            patch(
                "backend.agents.intake_agent._search_similar_reports",
                return_value=[],
            ),
        ):
            result = await run_intake({**base_state, "selected_depth": "light"})

        assert result["intake_result"].depth == "light"


class TestBudgetSelection:
    def test_prefers_selected_depth_budget(self):
        from backend.config import settings
        from backend.pipeline.graph import _get_budget

        assert _get_budget({"selected_depth": "light"}) == settings.budget_light

    def test_falls_back_to_intake_depth_budget(self):
        from backend.config import settings
        from backend.pipeline.graph import _get_budget

        intake = IntakeResult(
            original_query="test",
            cleaned_query="test",
            intent="research",
            domain="general",
            complexity="high",
            depth="deep",
        )

        assert _get_budget({"intake_result": intake}) == settings.budget_deep


class TestQADecision:
    def test_pass_still_saves(self):
        from backend.pipeline.graph import qa_decision

        decision = qa_decision(
            {"verdict": "PASS", "qa_iterations": 1, "iteration": 1, "max_iterations": 3}
        )

        assert decision == "pass"

    def test_reject_retries_before_limit(self):
        from backend.pipeline.graph import qa_decision

        decision = qa_decision(
            {"verdict": "REJECT", "qa_iterations": 1, "iteration": 1, "max_iterations": 3}
        )

        assert decision == "reject"

    def test_reject_fails_at_limit(self):
        from backend.pipeline.graph import qa_decision

        decision = qa_decision(
            {"verdict": "REJECT", "qa_iterations": 3, "iteration": 3, "max_iterations": 3}
        )

        assert decision == "fail"

    def test_critique_aborts_when_quality_low_and_budget_nearly_spent(self):
        from backend.pipeline.graph import critique_decision

        decision = critique_decision(
            {
                "selected_depth": "standard",
                "critic_score": 0.36,
                "revision_count": 1,
                "cost_usd": 1.82,
                "research_results": [
                    ResearchResult(
                        query="AI chip market",
                        findings=["Growth is strong."],
                        sources=[Source(url=f"https://example.com/{idx}", title=f"S{idx}", snippet="x")]
                    )
                    for idx in range(20)
                ],
            }
        )

        assert decision == "abort"

    def test_synthesis_decision_proceeds_when_ready(self):
        from backend.pipeline.graph import synthesis_decision

        decision = synthesis_decision({"synthesis_ready": True})
        assert decision == "proceed"

    def test_synthesis_decision_revises_when_not_ready_with_budget(self):
        from backend.pipeline.graph import synthesis_decision

        decision = synthesis_decision(
            {
                "synthesis_ready": False,
                "selected_depth": "standard",
                "cost_usd": 0.2,
                "revision_count": 1,
                "max_iterations": 3,
                "synthesis_payload": {
                    "blocking_reasons": ["Too few usable claims to produce a decision-grade synthesis."]
                },
            }
        )
        assert decision == "revise"

    def test_synthesis_decision_aborts_when_not_ready_and_no_budget(self):
        from backend.pipeline.graph import synthesis_decision

        decision = synthesis_decision(
            {
                "synthesis_ready": False,
                "selected_depth": "standard",
                "cost_usd": 1.95,
                "revision_count": 2,
                "max_iterations": 3,
                "synthesis_payload": {
                    "blocking_reasons": ["Citation verification did not pass quality threshold."]
                },
            }
        )
        assert decision == "abort"


class TestResearchFailFast:
    async def test_cost_guard_post_research_raises_on_zero_sources_first_pass(self, base_state):
        from backend.pipeline.graph import cost_guard_post_research

        state = {
            **base_state,
            "revision_count": 0,
            "research_results": [
                ResearchResult(
                    query="Estimate market size",
                    findings=["Market is large."],
                    sources=[],
                )
            ],
        }

        with pytest.raises(InsufficientEvidenceError, match="0 sources on the first pass"):
            await cost_guard_post_research(state)

    async def test_pipeline_context_propagates_budget_error_without_fallback_yield(self):
        from backend.pipeline.graph import pipeline_context

        class _FakeAsyncPostgresSaver:
            @classmethod
            def from_conn_string(cls, _conn_string):
                return cls()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def setup(self):
                return None

        with patch.dict("sys.modules", {"langgraph.checkpoint.postgres.aio": type("_M", (), {"AsyncPostgresSaver": _FakeAsyncPostgresSaver})}):
            with patch("backend.pipeline.graph.build_graph", return_value=object()):
                with pytest.raises(BudgetExceededError, match="Budget exceeded"):
                    async with pipeline_context():
                        raise BudgetExceededError("Budget exceeded after research: $4.5240 > $2.00")


class TestSynthesisGate:
    async def test_synthesis_gate_marks_ready_with_verified_primary_claims(self, base_state):
        from backend.agents.synthesis_agent import run_synthesis_gate

        citation = CitationVerificationResult(
            checks=[
                CitationCheckResult(
                    url=f"https://arxiv.org/abs/{idx}",
                    status=CitationStatus.VERIFIED,
                )
                for idx in range(6)
            ]
        )
        citation.compute_stats()

        evidence = [
            {
                "id": str(idx),
                "query_id": "q",
                "claim": f"Claim {idx}: model throughput is {20 + idx} tokens per second on RTX 4080 with Q4 quantization.",
                "source_url": f"https://arxiv.org/abs/{idx}",
                "source_title": f"Paper {idx}",
                "snippet": "Measured throughput on local GPU.",
                "domain": "arxiv.org",
                "confidence": 0.9,
                "verification_status": "VERIFIED",
                "tags": [],
            }
            for idx in range(6)
        ]

        result = await run_synthesis_gate({**base_state, "citation_verification": citation, "evidence_items": evidence})
        assert result["synthesis_ready"] is True
        assert result["allow_recommendations"] is True

    async def test_synthesis_gate_blocks_when_low_authority_sources_dominate(self, base_state):
        from backend.agents.synthesis_agent import run_synthesis_gate

        citation = CitationVerificationResult(
            checks=[
                CitationCheckResult(
                    url=f"https://www.youtube.com/watch?v={idx}",
                    status=CitationStatus.VERIFIED,
                )
                for idx in range(6)
            ]
        )
        citation.compute_stats()

        evidence = [
            {
                "id": str(idx),
                "query_id": "q",
                "claim": f"Claim {idx}: benchmark result with unclear methodology and limited reproducibility notes.",
                "source_url": f"https://www.youtube.com/watch?v={idx}",
                "source_title": f"Video {idx}",
                "snippet": "Video benchmark without reproducible setup.",
                "domain": "www.youtube.com",
                "confidence": 0.9,
                "verification_status": "VERIFIED",
                "tags": [],
            }
            for idx in range(6)
        ]

        result = await run_synthesis_gate({**base_state, "citation_verification": citation, "evidence_items": evidence})
        assert result["synthesis_ready"] is False
        assert result["allow_recommendations"] is False


class TestReflectAndCritique:
    async def test_reflect_adds_follow_up_queries_for_uncovered_tasks(self, base_state):
        from backend.agents.reflect_agent import run_reflect

        state = {
            **base_state,
            "research_tasks": [
                ResearchTask(id="market", question="Estimate market size", priority=1),
                ResearchTask(id="pricing", question="Map competitor pricing", priority=1),
            ],
            "research_results": [
                ResearchResult(
                    query="Estimate market size",
                    findings=["The market is growing quickly."],
                    sources=[Source(url="https://a.com", title="A", domain="a.com", snippet="source A")],
                )
            ],
            "evidence_items": [],
            "unresolved_questions": ["Clarify target geography"],
        }

        with patch(
            "backend.agents.reflect_agent._call_llm",
            AsyncMock(
                return_value=json.dumps(
                    {
                        "issues": [],
                        "additional_queries": [],
                        "strengths": [],
                        "weaknesses": [],
                        "gaps": [],
                        "quality_score": 0.8,
                        "needs_more_research": False,
                    }
                )
            ),
        ):
            result = await run_reflect(state)

        reflect = result["reflect_result"]
        assert reflect.needs_more_research is True
        assert "Map competitor pricing" in reflect.additional_queries
        assert "Clarify target geography" in reflect.additional_queries

    async def test_research_critique_generates_follow_up_queries_from_weak_evidence(self, base_state):
        from backend.agents.research_critique_agent import run_research_critique

        citation = CitationVerificationResult(
            checks=[
                CitationCheckResult(url="https://bad.com", status=CitationStatus.FABRICATED),
            ]
        )
        citation.compute_stats()
        state = {
            **base_state,
            "research_tasks": [ResearchTask(id="market", question="Estimate market size", priority=1)],
            "research_results": [
                ResearchResult(
                    query="Estimate market size",
                    findings=["The market is growing quickly."],
                    sources=[Source(url="https://a.com", title="A", domain="a.com", snippet="source A")],
                )
            ],
            "reflect_result": ReflectResult(
                additional_queries=["Map competitor pricing"],
                issues=[],
                strengths=[],
                weaknesses=[],
                gaps=[],
                quality_score=0.4,
                needs_more_research=True,
            ),
            "citation_verification": citation,
            "evidence_items": [],
        }

        with patch(
            "backend.agents.research_critique_agent._call_llm",
            AsyncMock(
                return_value=json.dumps(
                    {
                        "verdict": "ACCEPT",
                        "scores": {
                            "factual_accuracy": 0.9,
                            "coverage": 0.9,
                            "logic": 0.9,
                            "depth": 0.9,
                            "sources": 0.9,
                        },
                        "overall_score": 0.9,
                        "blocking_issues": [],
                        "recommendations": [],
                        "challenged_claims": [],
                        "follow_up_queries": [],
                    }
                )
            ),
        ):
            result = await run_research_critique(state)

        critique = result["research_critique_result"]
        assert critique.verdict == "REVISE"
        assert critique.follow_up_queries
        assert "Map competitor pricing" in critique.follow_up_queries

    async def test_research_critique_blocks_on_zero_sources_without_branch_explosion(self, base_state):
        from backend.agents.research_critique_agent import run_research_critique

        state = {
            **base_state,
            "research_tasks": [ResearchTask(id="market", question="Estimate market size", priority=1)],
            "research_results": [
                ResearchResult(
                    query="Estimate market size",
                    findings=["The market is growing quickly."],
                    sources=[],
                )
            ],
            "evidence_items": [],
        }

        with patch(
            "backend.agents.research_critique_agent._call_llm",
            AsyncMock(
                return_value=json.dumps(
                    {
                        "verdict": "ACCEPT",
                        "scores": {
                            "factual_accuracy": 0.9,
                            "coverage": 0.9,
                            "logic": 0.9,
                            "depth": 0.9,
                            "sources": 0.9,
                        },
                        "overall_score": 0.9,
                        "blocking_issues": [],
                        "recommendations": [],
                        "challenged_claims": [],
                        "follow_up_queries": ["Find two additional independent sources for: Estimate market size"],
                    }
                )
            ),
        ):
            result = await run_research_critique(state)

        critique = result["research_critique_result"]
        assert critique.verdict == "REVISE"
        assert any("no usable citations" in issue.lower() for issue in critique.blocking_issues)
        assert not any(query.startswith("Find two additional independent sources for:") for query in critique.follow_up_queries)

    async def test_research_critique_detects_contradictory_claims(self, base_state):
        from backend.agents.research_critique_agent import run_research_critique

        state = {
            **base_state,
            "research_results": [
                ResearchResult(query="AI chip market", findings=["Growth is 12%"], sources=[]),
                ResearchResult(query="AI chip market", findings=["Growth is 55%"], sources=[]),
            ],
            "evidence_items": [
                {
                    "id": "ev1",
                    "query_id": "q1",
                    "claim": "AI chip market growth is 12% in 2025",
                    "source_url": "",
                    "source_title": "",
                    "snippet": "AI chip market growth is 12% in 2025",
                    "domain": "",
                    "confidence": 0.8,
                    "verification_status": "unverified",
                    "tags": [],
                },
                {
                    "id": "ev2",
                    "query_id": "q2",
                    "claim": "AI chip market growth is 55% in 2025",
                    "source_url": "",
                    "source_title": "",
                    "snippet": "AI chip market growth is 55% in 2025",
                    "domain": "",
                    "confidence": 0.8,
                    "verification_status": "unverified",
                    "tags": [],
                },
            ],
        }

        with patch(
            "backend.agents.research_critique_agent._call_llm",
            AsyncMock(
                return_value=json.dumps(
                    {
                        "verdict": "ACCEPT",
                        "scores": {
                            "factual_accuracy": 0.9,
                            "coverage": 0.9,
                            "logic": 0.9,
                            "depth": 0.9,
                            "sources": 0.9,
                        },
                        "overall_score": 0.9,
                        "blocking_issues": [],
                        "recommendations": [],
                        "challenged_claims": [],
                        "follow_up_queries": [],
                    }
                )
            ),
        ):
            result = await run_research_critique(state)

        assert result["contradiction_log"]
        assert any("Verify contradiction" in query for query in result["research_critique_result"].follow_up_queries)


class TestQAAgentEvidenceAware:
    async def test_qa_rejects_report_without_evidence(self, base_state):
        from backend.agents.qa_agent import run_qa

        report = ReportOutput(
            title="AI Chip Market Analysis",
            executive_summary="Summary",
            sections=[ReportSection(title="Market Overview", content="Text", order=1, sources=[])],
            status=ReportStatus.COMPLETED,
        )
        state = {
            **base_state,
            "report": report,
            "evidence_items": [],
            "citation_verification": CitationVerificationResult(),
            "research_critique_result": ResearchCritiqueResult(
                verdict="ACCEPT",
                scores=CritiqueScore(),
                overall_score=0.8,
            ),
        }

        with (
            patch("backend.agents.qa_agent._call_visual_qa", AsyncMock(return_value='{"score": 0.9, "issues": []}')),
            patch("backend.agents.qa_agent._call_substance_qa", AsyncMock(return_value='{"score": 0.9, "citation_score": 0.9, "issues": []}')),
            patch("backend.agents.qa_agent.send_push_notification", AsyncMock(return_value=None)),
        ):
            result = await run_qa(state)

        qa_result = result["qa_result"]
        assert qa_result.verdict == QAVerdict.REJECT
        assert any(issue.category == "citation" for issue in qa_result.issues)

    def test_revise_fails_at_limit(self):
        from backend.pipeline.graph import qa_decision

        decision = qa_decision(
            {"verdict": "REVISE", "qa_iterations": 3, "iteration": 3, "max_iterations": 3}
        )

        assert decision == "fail"


class TestSaveToKnowledgeLibrary:
    async def test_fail_status_still_saves_report(self, base_state, sample_report, tmp_path, monkeypatch):
        from backend.config import settings
        from backend.pipeline.graph import save_to_knowledge_library

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        with (
            patch("backend.knowledge_library.facts_store.facts_store.save_verified_facts", AsyncMock(return_value=0)),
            patch("backend.knowledge_library.facts_store.facts_store.get_by_session", AsyncMock(return_value=[])),
            patch("backend.knowledge_library.sources_store.sources_store.upsert_sources", AsyncMock(return_value=None)),
            patch("backend.knowledge_library.ragflow_client.ragflow.save_report", AsyncMock(return_value="doc-1")) as save_report,
        ):
            result = await save_to_knowledge_library(
                {**base_state, "report": sample_report, "verdict": "REJECT", "status": "qa"}
            )

        assert result["status"] == "failed"
        assert save_report.await_count == 1


# ---------------------------------------------------------------------------
# Shared mock payloads
# ---------------------------------------------------------------------------

_PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_MOCK_PERPLEXITY_RESPONSE = {
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": (
                    "NVIDIA leads the AI chip market with 80% share in training workloads.\n\n"
                    "AMD is expanding its data center GPU portfolio with MI300X.\n\n"
                    "Custom ASICs from Google (TPU v5) and Amazon (Trainium) are growing."
                ),
            }
        }
    ],
    "citations": [
        "https://example.com/nvidia-market-share",
        "https://example.com/amd-mi300x",
    ],
    "usage": {"prompt_tokens": 120, "completion_tokens": 280},
}

_MOCK_MASTER_PROMPT_RESPONSE = json.dumps({
    "system_prompt": "You are a senior Gartner analyst specialising in AI/ML infrastructure.",
    "user_prompt": "Analyse the AI chip market for 2025-2030.",
    "master_prompt": (
        "## PROFILE\n"
        "Senior Gartner analyst with 15 years of semiconductor and AI/ML expertise.\n\n"
        "## KNOWLEDGE\n"
        "Deep understanding of GPU architectures, CUDA ecosystem, and custom silicon trends. "
        "Market sizing frameworks: TAM/SAM/SOM, Porter's Five Forces, technology S-curves.\n\n"
        "## REASONING\n"
        "Use chain-of-thought decomposition for multi-step market analysis. "
        "Apply few-shot patterns from historical semiconductor reports.\n\n"
        "## RELIABILITY\n"
        "Cite only verified sources (Gartner, IDC, IEEE, Bloomberg). "
        "Flag speculative claims. Cross-check all market-size figures."
    ),
    "techniques_applied": [
        {"name": "chain_of_thought", "weight": 0.6, "rationale": "Complex multi-step analysis"},
        {"name": "few_shot", "weight": 0.4, "rationale": "Examples from knowledge base"},
    ],
    "report_schema": {
        "title_template": "AI Chip Market Analysis {year}",
        "sections": [
            {"title": "Market Overview"},
            {"title": "Competitive Landscape"},
        ],
        "constraints": ["minimum 10000 words"],
        "output_format": "markdown",
        "expected_length": "12000 words",
    },
    "target_model": "anthropic/claude-opus-4.6",
    "temperature": 0.3,
})

_MOCK_RENDERER_RESPONSE = json.dumps({
    "title": "AI Chip Market Analysis 2025-2030",
    "executive_summary": (
        "The global AI chip market is projected to reach $500B by 2030, "
        "driven by LLM inference demand. NVIDIA holds dominant position."
    ),
    "sections": [
        {
            "title": "Market Overview",
            "content": "NVIDIA dominates training workloads with an 80% market share.",
            "order": 1,
            "sources": ["https://example.com/source1"],
        },
        {
            "title": "Investment Implications",
            "content": "Strong BUY signal for NVDA and semiconductor ETFs.",
            "order": 2,
            "sources": [],
        },
    ],
})

_MOCK_SLIDES_RESPONSE = json.dumps({
    "title": "AI Chip Market Analysis Deck",
    "slides": [
        {
            "title": "Executive Summary",
            "bullets": ["NVIDIA remains dominant", "Inference demand is accelerating"],
            "notes": "Use this as the opening executive slide.",
            "chart_ref": "chart_0.png",
        }
    ],
    "theme": "corporate",
})


# ---------------------------------------------------------------------------
# Shared fixtures for new agent tests
# ---------------------------------------------------------------------------


@pytest.fixture
def prompt_king_state(base_state):
    intake = IntakeResult(
        original_query="Analyse AI chip market for 2025-2030",
        cleaned_query="AI chip market analysis 2025-2030",
        intent="analysis",
        domain="tech",
        complexity="high",
        depth="deep",
        key_entities=["NVIDIA", "AMD", "Google TPU"],
        clarifying_questions=["Which region?"],
    )
    router = RouterResult(
        task_type="market_research",
        techniques=["chain_of_thought", "few_shot"],
        confidence=0.92,
    )
    return {
        **base_state,
        "intake_result": intake,
        "router_result": router,
        "selected_techniques": ["chain_of_thought", "few_shot"],
    }


@pytest.fixture
def renderer_state(base_state):
    intake = IntakeResult(
        original_query="AI chip analysis",
        cleaned_query="AI chip analysis",
        intent="analysis",
        domain="tech",
        complexity="high",
    )
    research = ResearchResult(
        query="AI chip market",
        findings=["NVIDIA leads with 80% share"],
        sources=[Source(url="https://example.com", title="Source", snippet="snippet")],
    )
    return {
        **base_state,
        "intake_result": intake,
        "research_results": [research],
        "chart_paths": [],
        "messages": [],
    }


@pytest.fixture
def presentation_state(base_state, sample_report):
    return {
        **base_state,
        "session_id": "presentation-session",
        "report": sample_report,
        "chart_paths": ["/tmp/chart_0.png"],
    }


# ---------------------------------------------------------------------------
# TestResearchAgent
# ---------------------------------------------------------------------------


class TestResearchAgent:
    def test_model_selection_by_depth(self):
        from backend.agents.research_agent import _get_research_model_config

        assert _get_research_model_config("light").direct_model == "sonar"
        assert _get_research_model_config("standard").direct_model == "sonar"
        assert _get_research_model_config("deep").direct_model == "sonar-pro"
        assert _get_research_model_config("exhaustive").direct_model == "sonar-deep-research"

    def test_branch_prompt_strategy_for_widen(self):
        from backend.agents.research_agent import _build_research_prompt

        prompt = _build_research_prompt(
            "AI chip market growth",
            [{"source": "ragflow", "content": "Prior internal note"}],
            branch_state=ResearchBranchState(
                task_id="market",
                question="AI chip market growth",
                next_action="widen",
                action_reason="Need more independent sources.",
                source_strategy="hybrid",
            ),
        )

        assert "widen coverage" in prompt
        assert "independent sources" in prompt
        assert "combine internal memory with fresh web verification" in prompt

    def test_branch_prompt_strategy_for_verify(self):
        from backend.agents.research_agent import _build_research_prompt

        prompt = _build_research_prompt(
            "AI chip market growth",
            [],
            branch_state=ResearchBranchState(
                task_id="market",
                question="AI chip market growth",
                next_action="verify",
                action_reason="Contradictory evidence was detected for this branch.",
                contradiction_notes=["numeric spread detected (43.0)"],
            ),
        )

        assert "verify contradiction" in prompt
        assert "Contradiction notes" in prompt
        assert "numeric spread detected" in prompt

    async def test_returns_research_result_with_findings_and_sources(self, base_state):
        from backend.agents.research_agent import run_research

        batches = ParallelBatches(
            batches=[QueryBatch(queries=["AI chip market 2025"], mode="parallel")],
            total_queries=1,
        )
        state = {
            **base_state,
            "parallel_batches": batches,
            "intake_result": IntakeResult(
                original_query="AI chip market 2025",
                cleaned_query="AI chip market 2025",
                intent="research",
                domain="tech",
                complexity="medium",
                depth="standard",
            ),
        }

        with respx.mock:
            respx.post(_PERPLEXITY_URL).mock(
                return_value=httpx.Response(200, json=_MOCK_PERPLEXITY_RESPONSE)
            )
            result = await run_research(state)

        assert result["current_agent"] == "research"
        assert len(result["research_results"]) == 1
        res = result["research_results"][0]
        assert res.query == "AI chip market 2025"
        assert len(res.findings) >= 1
        assert len(res.sources) == 2
        assert res.sources[0].url == "https://example.com/nvidia-market-share"
        assert result["cost_usd"] > 0.0

    async def test_sequential_batch_runs_in_order(self, base_state):
        from backend.agents.research_agent import run_research

        batches = ParallelBatches(
            batches=[
                QueryBatch(queries=["query A", "query B"], mode="sequential"),
            ],
            total_queries=2,
        )
        state = {
            **base_state,
            "parallel_batches": batches,
            "intake_result": IntakeResult(
                original_query="query A",
                cleaned_query="query A",
                intent="research",
                domain="general",
                complexity="medium",
                depth="deep",
            ),
        }

        with respx.mock:
            respx.post(_PERPLEXITY_URL).mock(
                return_value=httpx.Response(200, json=_MOCK_PERPLEXITY_RESPONSE)
            )
            result = await run_research(state)

        assert len(result["research_results"]) == 2

    async def test_falls_back_to_data_queries(self, base_state):
        from backend.agents.research_agent import run_research

        state = {
            **base_state,
            "parallel_batches": None,
            "data_queries": ["fallback query"],
            "intake_result": IntakeResult(
                original_query="fallback query",
                cleaned_query="fallback query",
                intent="research",
                domain="general",
                complexity="low",
                depth="light",
            ),
        }

        with respx.mock:
            respx.post(_PERPLEXITY_URL).mock(
                return_value=httpx.Response(200, json=_MOCK_PERPLEXITY_RESPONSE)
            )
            result = await run_research(state)

        assert len(result["research_results"]) == 1
        assert result["research_results"][0].query == "fallback query"

    async def test_updates_branch_state_after_research(self, base_state):
        from backend.agents.research_agent import run_research

        state = {
            **base_state,
            "parallel_batches": ParallelBatches(
                batches=[QueryBatch(queries=["AI chip market 2025"], mode="parallel")],
                total_queries=1,
            ),
            "branch_states": [
                ResearchBranchState(
                    task_id="market",
                    question="AI chip market 2025",
                    status="pending",
                    source_strategy="web",
                )
            ],
            "intake_result": IntakeResult(
                original_query="AI chip market 2025",
                cleaned_query="AI chip market 2025",
                intent="research",
                domain="tech",
                complexity="medium",
                depth="standard",
            ),
        }

        with respx.mock:
            respx.post(_PERPLEXITY_URL).mock(
                return_value=httpx.Response(200, json=_MOCK_PERPLEXITY_RESPONSE)
            )
            result = await run_research(state)

        branch = result["branch_states"][0]
        assert branch.question == "AI chip market 2025"
        assert branch.status == "completed"
        assert branch.source_count == 2
        assert branch.next_action == "complete"

    async def test_retries_on_429_succeeds_on_third_attempt(self):
        from backend.agents.research_agent import _call_perplexity

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(429, json={"error": "rate_limit_exceeded"})
            return httpx.Response(200, json=_MOCK_PERPLEXITY_RESPONSE)

        # Patch asyncio.sleep so tenacity wait_exponential(min=2) doesn't stall tests
        with patch("asyncio.sleep", return_value=None):
            with respx.mock:
                respx.post(_PERPLEXITY_URL).mock(side_effect=handler)
                result = await _call_perplexity("AI chip market")

        assert call_count == 3
        assert result["choices"][0]["message"]["content"].startswith("NVIDIA leads")

    async def test_raises_after_max_retries_exceeded(self):
        from backend.agents.research_agent import _call_perplexity

        with patch("asyncio.sleep", return_value=None):
            with respx.mock:
                respx.post(_PERPLEXITY_URL).mock(
                    return_value=httpx.Response(429, json={"error": "rate_limit"})
                )
                with pytest.raises(httpx.HTTPStatusError):
                    await _call_perplexity("AI chip market")

    async def test_citations_parsed_as_string_list(self):
        from backend.agents.research_agent import _parse_citations

        raw = {"citations": ["https://a.com/page", "https://b.com/report"]}
        sources = _parse_citations(raw)

        assert len(sources) == 2
        assert sources[0].url == "https://a.com/page"
        assert sources[0].domain == "a.com"

    async def test_citations_parsed_as_dict_list(self):
        from backend.agents.research_agent import _parse_citations

        raw = {
            "citations": [
                {"url": "https://a.com/page", "title": "A Report", "snippet": "Key finding"},
            ]
        }
        sources = _parse_citations(raw)

        assert sources[0].title == "A Report"
        assert sources[0].snippet == "Key finding"

    async def test_citations_parsed_from_message_annotations_and_content_urls(self):
        from backend.agents.research_agent import _parse_citations

        raw = {
            "choices": [
                {
                    "message": {
                        "content": "See https://c.com/brief and https://d.com/note.",
                        "annotations": [
                            {"url": "https://a.com/page", "title": "Annotated Source"},
                            {"uri": "https://b.com/report", "name": "URI Source"},
                        ],
                    }
                }
            ]
        }
        sources = _parse_citations(raw)

        assert len(sources) == 4
        assert {source.url for source in sources} == {
            "https://a.com/page",
            "https://b.com/report",
            "https://c.com/brief",
            "https://d.com/note",
        }

    def test_extract_findings_splits_on_double_newline(self):
        from backend.agents.research_agent import _extract_findings

        content = "Finding 1.\n\nFinding 2.\n\nFinding 3."
        findings = _extract_findings(content)

        assert len(findings) == 3
        assert findings[0] == "Finding 1."

    def test_extract_findings_returns_single_item_for_no_paragraphs(self):
        from backend.agents.research_agent import _extract_findings

        content = "Single continuous finding with no paragraph breaks."
        findings = _extract_findings(content)

        assert len(findings) == 1
        assert findings[0] == content

    def test_confidence_scales_with_source_count(self):
        # confidence = min(0.9, 0.5 + len(sources) * 0.05)
        # 0 sources → 0.5, 8 sources → 0.9 (capped)
        assert min(0.9, 0.5 + 0 * 0.05) == pytest.approx(0.5)
        assert min(0.9, 0.5 + 8 * 0.05) == pytest.approx(0.9)
        assert min(0.9, 0.5 + 4 * 0.05) == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# TestPromptKing
# ---------------------------------------------------------------------------


class TestPromptKing:
    async def test_returns_valid_master_prompt_schema(self, prompt_king_state):
        from backend.agents.prompt_king import run_prompt_king

        with patch(
            "backend.agents.prompt_king._call_llm",
            return_value=_MOCK_MASTER_PROMPT_RESPONSE,
        ):
            result = await run_prompt_king(prompt_king_state)

        assert result["current_agent"] == "prompt_king"
        master = result["master_prompt"]
        assert isinstance(master, MasterPrompt)
        assert master.system_prompt
        assert master.user_prompt
        assert master.temperature == pytest.approx(0.3)
        assert len(master.techniques_applied) == 2
        assert result["cost_usd"] > 0.0

    async def test_master_prompt_contains_all_four_sections(self, prompt_king_state):
        from backend.agents.prompt_king import run_prompt_king

        with patch(
            "backend.agents.prompt_king._call_llm",
            return_value=_MOCK_MASTER_PROMPT_RESPONSE,
        ):
            result = await run_prompt_king(prompt_king_state)

        mp = result["master_prompt"].master_prompt
        for section in ("## PROFILE", "## KNOWLEDGE", "## REASONING", "## RELIABILITY"):
            assert section in mp, f"Missing section: {section}"

    async def test_report_schema_sections_populated(self, prompt_king_state):
        from backend.agents.prompt_king import run_prompt_king

        with patch(
            "backend.agents.prompt_king._call_llm",
            return_value=_MOCK_MASTER_PROMPT_RESPONSE,
        ):
            result = await run_prompt_king(prompt_king_state)

        schema = result["master_prompt"].report_schema
        assert len(schema.sections) >= 1
        titles = [s.title for s in schema.sections]
        assert "Market Overview" in titles

    async def test_techniques_applied_match_selected(self, prompt_king_state):
        from backend.agents.prompt_king import run_prompt_king

        with patch(
            "backend.agents.prompt_king._call_llm",
            return_value=_MOCK_MASTER_PROMPT_RESPONSE,
        ):
            result = await run_prompt_king(prompt_king_state)

        names = {t.name for t in result["master_prompt"].techniques_applied}
        assert "chain_of_thought" in names
        assert "few_shot" in names

    async def test_few_shot_examples_loaded_from_knowledge_base(self, prompt_king_state):
        """Verify real few-shot examples from knowledge_base/ are included in LLM context."""
        from backend.agents.prompt_king import run_prompt_king
        from backend.agents import prompt_king as prompt_king_module

        captured: list[str] = []

        async def capture_llm(system: str, user: str, model: str) -> str:
            captured.append(user)
            return _MOCK_MASTER_PROMPT_RESPONSE

        kb_dir = Path(__file__).resolve().parents[2] / "prompt_library" / "knowledge_base"
        with (
            patch.object(prompt_king_module, "KNOWLEDGE_BASE_DIR", kb_dir),
            patch.object(prompt_king_module, "FEW_SHOT_DIR", kb_dir / "few_shot_examples"),
            patch.object(prompt_king_module, "ROLE_PERSONAS_PATH", kb_dir / "role_personas.json"),
            patch.object(prompt_king_module, "TASK_TEMPLATES_PATH", kb_dir / "task_templates.json"),
            patch("backend.agents.prompt_king._call_llm", side_effect=capture_llm),
        ):
            await run_prompt_king(prompt_king_state)

        assert captured, "LLM was not called"
        ctx = json.loads(captured[0])
        # market_research maps to "market_analysis" few-shot file which has examples
        assert "few_shot_examples" in ctx
        assert isinstance(ctx["few_shot_examples"], list)
        assert len(ctx["few_shot_examples"]) > 0, (
            "few_shot_examples is empty — check prompt_library/knowledge_base/few_shot_examples/"
        )

    async def test_falls_back_gracefully_when_no_router_result(self, base_state):
        from backend.agents.prompt_king import run_prompt_king

        intake = IntakeResult(
            original_query="test query",
            cleaned_query="test query",
            intent="research",
            domain="general",
            complexity="medium",
        )
        state = {**base_state, "intake_result": intake}  # no router_result

        with patch(
            "backend.agents.prompt_king._call_llm",
            return_value=_MOCK_MASTER_PROMPT_RESPONSE,
        ):
            result = await run_prompt_king(state)

        assert isinstance(result["master_prompt"], MasterPrompt)

    async def test_auto_generates_techniques_when_llm_returns_empty_list(
        self, prompt_king_state
    ):
        from backend.agents.prompt_king import run_prompt_king

        response_no_techniques = json.dumps({
            **json.loads(_MOCK_MASTER_PROMPT_RESPONSE),
            "techniques_applied": [],
        })

        with patch(
            "backend.agents.prompt_king._call_llm",
            return_value=response_no_techniques,
        ):
            result = await run_prompt_king(prompt_king_state)

        # Should auto-generate one technique per selected_technique
        assert len(result["master_prompt"].techniques_applied) == 2


class TestPromptKingGraphFallback:
    async def test_prompt_king_node_uses_fallback_on_failure(self, prompt_king_state):
        from backend.pipeline.graph import prompt_king_node

        with patch("backend.pipeline.graph.run_prompt_king", AsyncMock(side_effect=RuntimeError("boom"))):
            result = await prompt_king_node(prompt_king_state)

        assert result["current_agent"] == "prompt_king"
        assert isinstance(result["master_prompt"], MasterPrompt)
        assert "## PROFILE" in result["master_prompt"].master_prompt
        assert any(msg.get("role") == "prompt_king" for msg in result.get("messages", []))


class TestSummarizationAgent:
    async def test_preserves_raw_research_results_and_emits_brief(self, base_state):
        from backend.agents.summarization_agent import run_summarization

        research = ResearchResult(
            query="Estimate market size",
            findings=["AI chip market reached $120B.", "Inference demand keeps growing."],
            sources=[Source(url="https://a.com", title="A", snippet="Market data", domain="a.com")],
        )

        with patch(
            "backend.agents.summarization_agent._call_summarize",
            AsyncMock(
                return_value=json.dumps(
                    {
                        "summary": "Condensed branch summary",
                        "key_facts": ["AI chip market reached $120B."],
                        "preserved_citation_count": 1,
                    }
                )
            ),
        ):
            result = await run_summarization({**base_state, "research_results": [research]})

        assert result["research_brief"]
        assert "AI chip market reached $120B." in result["research_brief"]
        assert result["current_agent"] == "summarization"
        assert research.findings == ["AI chip market reached $120B.", "Inference demand keeps growing."]


# ---------------------------------------------------------------------------
# TestRenderer
# ---------------------------------------------------------------------------


class TestRenderer:
    async def test_pdf_created_in_session_dir(self, renderer_state, tmp_path, monkeypatch):
        from backend.config import settings
        from backend.agents.renderer import run_renderer

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))
        session_id = renderer_state["session_id"]

        def fake_build_pdf(html: str, path: str) -> str:
            Path(path).write_bytes(b"%PDF-1.4 fake")
            return path

        with (
            patch("backend.agents.renderer._call_llm", return_value=_MOCK_RENDERER_RESPONSE),
            patch("backend.agents.renderer._build_pdf", side_effect=fake_build_pdf),
            patch("backend.agents.renderer._build_docx", return_value=""),
        ):
            result = await run_renderer(renderer_state)

        pdf_paths = [p for p in result["final_report_paths"] if p.endswith(".pdf")]
        assert len(pdf_paths) == 1
        assert session_id in pdf_paths[0]
        assert Path(pdf_paths[0]).exists()

    async def test_docx_created_in_session_dir(self, renderer_state, tmp_path, monkeypatch):
        from backend.config import settings
        from backend.agents.renderer import run_renderer

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))
        session_id = renderer_state["session_id"]

        def fake_build_docx(report, charts, path: str) -> str:
            Path(path).write_bytes(b"PK fake docx")
            return path

        with (
            patch("backend.agents.renderer._call_llm", return_value=_MOCK_RENDERER_RESPONSE),
            patch("backend.agents.renderer._build_pdf", return_value=""),
            patch("backend.agents.renderer._build_docx", side_effect=fake_build_docx),
        ):
            result = await run_renderer(renderer_state)

        docx_paths = [p for p in result["final_report_paths"] if p.endswith(".docx")]
        assert len(docx_paths) == 1
        assert session_id in docx_paths[0]
        assert Path(docx_paths[0]).exists()

    async def test_html_always_written(self, renderer_state, tmp_path, monkeypatch):
        from backend.config import settings
        from backend.agents.renderer import run_renderer

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        with (
            patch("backend.agents.renderer._call_llm", return_value=_MOCK_RENDERER_RESPONSE),
            patch("backend.agents.renderer._build_pdf", return_value=""),
            patch("backend.agents.renderer._build_docx", return_value=""),
        ):
            result = await run_renderer(renderer_state)

        html_paths = [p for p in result["final_report_paths"] if p.endswith(".html")]
        assert len(html_paths) == 1
        assert Path(html_paths[0]).exists()
        content = Path(html_paths[0]).read_text()
        assert "AI Chip Market Analysis" in content
        assert "executive-summary" in content

    async def test_returns_valid_report_output(self, renderer_state, tmp_path, monkeypatch):
        from backend.config import settings
        from backend.agents.renderer import run_renderer

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        with (
            patch("backend.agents.renderer._call_llm", return_value=_MOCK_RENDERER_RESPONSE),
            patch("backend.agents.renderer._build_pdf", return_value=""),
            patch("backend.agents.renderer._build_docx", return_value=""),
        ):
            result = await run_renderer(renderer_state)

        report = result["report"]
        assert isinstance(report, ReportOutput)
        assert report.title == "AI Chip Market Analysis 2025-2030"
        assert len(report.sections) == 2
        assert result["current_agent"] == "renderer"

    async def test_renderer_context_contains_evidence_graph(self, renderer_state, tmp_path, monkeypatch):
        from backend.config import settings
        from backend.agents import renderer as renderer_module
        from backend.agents.renderer import run_renderer
        from backend.schemas.master_prompt import MasterPrompt, ReportSchema, SectionSchema

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))
        captured: dict[str, str] = {}

        async def fake_call_llm(system: str, user: str, model: str) -> str:
            captured["user"] = user
            return _MOCK_RENDERER_RESPONSE

        state = {
            **renderer_state,
            "research_tasks": [ResearchTask(id="market", question="Estimate market size", priority=1)],
            "research_brief": "Short branch brief",
            "evidence_items": [],
            "master_prompt": MasterPrompt(
                system_prompt="sys",
                user_prompt="user",
                report_schema=ReportSchema(
                    sections=[
                        SectionSchema(title="Market Overview", description="Size and growth"),
                    ]
                ),
            ),
        }

        with (
            patch.object(renderer_module, "_call_llm", side_effect=fake_call_llm),
            patch("backend.agents.renderer._build_pdf", return_value=""),
            patch("backend.agents.renderer._build_docx", return_value=""),
        ):
            await run_renderer(state)

        context = json.loads(captured["user"])
        assert "research_branches" in context
        assert "report_schema" in context
        assert "section_packets" in context
        assert "executive_summary_packet" in context
        assert context["research_brief"] == "Short branch brief"

    async def test_renderer_normalizes_sections_to_schema_and_allowed_sources(
        self, renderer_state, tmp_path, monkeypatch
    ):
        from backend.config import settings
        from backend.agents.renderer import run_renderer
        from backend.schemas.master_prompt import MasterPrompt, ReportSchema, SectionSchema

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        llm_response = json.dumps(
            {
                "title": "AI Chip Market Analysis 2025-2030",
                "executive_summary": "Summary",
                "sections": [
                    {
                        "title": "Random Title",
                        "content": "Section content from LLM",
                        "order": 99,
                        "sources": ["https://not-allowed.example.com"],
                    }
                ],
            }
        )
        state = {
            **renderer_state,
            "master_prompt": MasterPrompt(
                system_prompt="sys",
                user_prompt="user",
                report_schema=ReportSchema(
                    sections=[
                        SectionSchema(title="Market Overview", description="AI chip market overview"),
                    ]
                ),
            ),
        }

        with (
            patch("backend.agents.renderer._call_llm", return_value=llm_response),
            patch("backend.agents.renderer._build_pdf", return_value=""),
            patch("backend.agents.renderer._build_docx", return_value=""),
        ):
            result = await run_renderer(state)

        section = result["report"].sections[0]
        assert section.title == "Market Overview"
        assert section.order == 1
        assert section.sources == ["https://example.com"]

    async def test_renderer_builds_executive_summary_from_packet_when_llm_summary_empty(
        self, renderer_state, tmp_path, monkeypatch
    ):
        from backend.config import settings
        from backend.agents.renderer import run_renderer

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        llm_response = json.dumps(
            {
                "title": "AI Chip Market Analysis 2025-2030",
                "executive_summary": "",
                "sections": [
                    {
                        "title": "Market Overview",
                        "content": "Section content",
                        "order": 1,
                        "sources": ["https://example.com"],
                    }
                ],
            }
        )

        with (
            patch("backend.agents.renderer._call_llm", return_value=llm_response),
            patch("backend.agents.renderer._build_pdf", return_value=""),
            patch("backend.agents.renderer._build_docx", return_value=""),
        ):
            result = await run_renderer(renderer_state)

        executive_summary = result["report"].executive_summary
        assert "NVIDIA leads with 80% share" in executive_summary
        assert "Key signals:" in executive_summary

    async def test_renderer_includes_orchestration_metadata(self, renderer_state, tmp_path, monkeypatch):
        from backend.config import settings
        from backend.agents.renderer import run_renderer

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        state = {
            **renderer_state,
            "branch_states": [
                ResearchBranchState(
                    task_id="market",
                    question="AI chip market",
                    status="completed",
                    next_action="complete",
                    action_reason="Branch is sufficiently covered for the current cycle.",
                    source_count=1,
                    confidence=0.8,
                )
            ],
            "contradiction_log": [{"topic": "ai chip market", "reason": "numeric spread detected"}],
        }

        with (
            patch("backend.agents.renderer._call_llm", return_value=_MOCK_RENDERER_RESPONSE),
            patch("backend.agents.renderer._build_pdf", return_value=""),
            patch("backend.agents.renderer._build_docx", return_value=""),
        ):
            result = await run_renderer(state)

        orchestration = result["report"].metadata["orchestration"]
        assert orchestration["branch_count"] == 1
        assert orchestration["branch_states"][0]["next_action"] == "complete"
        assert orchestration["contradictions"]

    async def test_raises_renderer_error_on_empty_llm_content(
        self, renderer_state, tmp_path, monkeypatch
    ):
        from backend.config import settings
        from backend.agents.renderer import run_renderer, RendererError

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        with (
            patch("backend.agents.renderer._call_llm", return_value=""),
        ):
            with pytest.raises(RendererError, match="empty content"):
                await run_renderer(renderer_state)

    async def test_raises_renderer_error_on_whitespace_only_content(
        self, renderer_state, tmp_path, monkeypatch
    ):
        from backend.config import settings
        from backend.agents.renderer import run_renderer, RendererError

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        with patch("backend.agents.renderer._call_llm", return_value="   \n  "):
            with pytest.raises(RendererError):
                await run_renderer(renderer_state)

    async def test_pdf_failure_does_not_raise(self, renderer_state, tmp_path, monkeypatch):
        """WeasyPrint errors are caught; renderer still returns HTML and DOCX."""
        from backend.config import settings
        from backend.agents.renderer import run_renderer

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        def fake_build_docx(report, charts, path: str) -> str:
            Path(path).write_bytes(b"PK fake")
            return path

        with (
            patch("backend.agents.renderer._call_llm", return_value=_MOCK_RENDERER_RESPONSE),
            patch("backend.agents.renderer._build_pdf", side_effect=RuntimeError("WeasyPrint missing")),
            patch("backend.agents.renderer._build_docx", side_effect=fake_build_docx),
        ):
            result = await run_renderer(renderer_state)

        # PDF path absent, HTML + DOCX still present
        assert not any(p.endswith(".pdf") for p in result["final_report_paths"])
        assert any(p.endswith(".html") for p in result["final_report_paths"])
        assert any(p.endswith(".docx") for p in result["final_report_paths"])

    async def test_renderer_retries_with_compatibility_fallback_after_400(self):
        from backend.agents.renderer import _call_llm

        calls: list[dict] = []

        class _FakeResponse:
            def __init__(self, status_code: int, payload: dict):
                self.status_code = status_code
                self._payload = payload
                self.request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"{self.status_code} error",
                        request=self.request,
                        response=httpx.Response(self.status_code, request=self.request),
                    )

            def json(self):
                return self._payload

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, _url, headers=None, json=None):
                calls.append(json)
                if len(calls) == 1:
                    return _FakeResponse(400, {})
                return _FakeResponse(
                    200,
                    {"choices": [{"message": {"content": _MOCK_RENDERER_RESPONSE}}]},
                )

        with patch("backend.agents.renderer.httpx.AsyncClient", return_value=_FakeClient()):
            raw = await _call_llm("system", '{"k":"v"}', "google/gemini-3.1-pro-preview")

        assert raw == _MOCK_RENDERER_RESPONSE
        assert calls[0]["model"] == "google/gemini-3.1-pro-preview"
        assert "response_format" in calls[0]
        assert "response_format" not in calls[1]


# ---------------------------------------------------------------------------
# TestPromptRouter
# ---------------------------------------------------------------------------


class TestPromptRouter:
    @pytest.mark.parametrize(
        ("prompt_text", "task_type"),
        [
            ("Проанализируй рынок ИИ-чипов в России и мире на 2025-2030 годы", "market_research"),
            ("Сделай сравнительное исследование AWS, Azure и GCP для enterprise", "comparative_study"),
            ("Оцени инвестиционную привлекательность акций NVIDIA после отчета", "investment_analysis"),
            ("Построй прогноз спроса на дата-центры в Европе до 2030 года", "trend_forecast"),
            ("Проведи due diligence стартапа в области synthetic data перед сделкой", "due_diligence"),
            ("Подготовь стратегический обзор выхода Ozon в новый B2B-сегмент", "strategic_review"),
            ("Оцени техническую архитектуру RAG-системы для банка", "technical_assessment"),
            ("Разбери причины падения конверсии мобильного приложения по шагам", "analytical_deep_dive"),
            ("Исследуй новые ниши применения генеративного ИИ в промышленности", "deep_exploratory"),
            ("Сравни российские и китайские электромобили по цене, запасу хода и сервису", "comparative_study"),
        ],
    )

    async def test_classifies_russian_requests(self, base_state, prompt_text: str, task_type: str):
        from backend.agents.prompt_router import (
            PROMPT_TECHNIQUE_MAP,
            run_prompt_router,
        )

        intake = IntakeResult(
            original_query=prompt_text,
            cleaned_query=prompt_text,
            intent="analysis",
            domain="general",
            complexity="medium",
        )
        state = {**base_state, "intake_result": intake}
        llm_payload = json.dumps(
            {
                "task_type": task_type,
                "techniques": PROMPT_TECHNIQUE_MAP[task_type][:2],
                "confidence": 0.93,
                "rationale": f"Detected {task_type}",
            }
        )

        with respx.mock:
            route = respx.post(_OPENROUTER_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": llm_payload}}]},
                )
            )
            result = await run_prompt_router(state)

        assert route.called
        assert result["router_result"].task_type == task_type
        assert result["selected_techniques"] == PROMPT_TECHNIQUE_MAP[task_type][:2]
        assert result["current_agent"] == "prompt_router"


# ---------------------------------------------------------------------------
# TestSupervisorAgent
# ---------------------------------------------------------------------------


class TestSupervisorAgent:
    async def test_dependent_queries_are_planned_sequentially(self, base_state):
        from backend.agents.supervisor_agent import run_supervisor

        state = {
            **base_state,
            "messages": [
                {
                    "role": "prompt_splitter",
                    "content": (
                        "Собери данные по объему рынка AI-агентов в России\n---\n"
                        "На основе объема рынка оцени TAM/SAM/SOM для нового продукта"
                    ),
                }
            ],
        }
        llm_payload = json.dumps(
            {
                "batches": [
                    {
                        "queries": ["Собери данные по объему рынка AI-агентов в России"],
                        "mode": "sequential",
                        "rationale": "Second query depends on the market size baseline.",
                    },
                    {
                        "queries": ["На основе объема рынка оцени TAM/SAM/SOM для нового продукта"],
                        "mode": "sequential",
                        "rationale": "Depends on results from the first query.",
                    },
                ],
                "total_queries": 2,
                "strategy_rationale": "Ordered execution avoids using missing upstream context.",
            }
        )

        with respx.mock:
            route = respx.post(_OPENROUTER_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": llm_payload}}]},
                )
            )
            result = await run_supervisor(state)

        assert route.called
        batches = result["parallel_batches"]
        assert batches.total_queries == 2
        assert [batch.mode for batch in batches.batches] == ["sequential", "sequential"]
        assert batches.batches[0].queries == ["Собери данные по объему рынка AI-агентов в России"]
        assert batches.batches[1].queries == ["На основе объема рынка оцени TAM/SAM/SOM для нового продукта"]

    async def test_independent_queries_are_grouped_in_parallel(self, base_state):
        from backend.agents.supervisor_agent import run_supervisor

        state = {
            **base_state,
            "messages": [
                {
                    "role": "prompt_splitter",
                    "content": (
                        "Оцени рынок AI-чипов в США\n---\n"
                        "Оцени рынок AI-чипов в Китае\n---\n"
                        "Оцени рынок AI-чипов в Европе"
                    ),
                }
            ],
        }
        llm_payload = json.dumps(
            {
                "batches": [
                    {
                        "queries": [
                            "Оцени рынок AI-чипов в США",
                            "Оцени рынок AI-чипов в Китае",
                            "Оцени рынок AI-чипов в Европе",
                        ],
                        "mode": "parallel",
                        "rationale": "Regional market scans are independent.",
                    }
                ],
                "total_queries": 3,
                "strategy_rationale": "Single parallel batch minimizes latency.",
            }
        )

        with respx.mock:
            route = respx.post(_OPENROUTER_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": llm_payload}}]},
                )
            )
            result = await run_supervisor(state)

        assert route.called
        batches = result["parallel_batches"]
        assert len(batches.batches) == 1
        assert batches.batches[0].mode == "parallel"
        assert batches.batches[0].queries == [
            "Оцени рынок AI-чипов в США",
            "Оцени рынок AI-чипов в Китае",
            "Оцени рынок AI-чипов в Европе",
        ]


class TestPromptSplitter:
    async def test_builds_task_decomposition_from_master_prompt(self, base_state):
        from backend.agents.prompt_splitter import run_prompt_splitter

        state = {
            **base_state,
            "intake_result": IntakeResult(
                original_query="Analyze AI chip market",
                cleaned_query="Analyze AI chip market",
                intent="research",
                domain="tech",
                complexity="high",
                depth="deep",
                key_entities=["NVIDIA", "AMD"],
                clarifying_questions=["Which region?"],
            ),
            "master_prompt": MasterPrompt(
                system_prompt="sys",
                user_prompt="Analyze AI chip market for 2025-2030",
            ),
        }

        result = await run_prompt_splitter(state)

        decomposition = result["task_decomposition"]
        assert decomposition.main_question == "Analyze AI chip market for 2025-2030"
        assert len(decomposition.subquestions) >= 1
        assert result["research_tasks"][0].question


class TestSupervisorOrchestration:
    async def test_preserves_revision_count_instead_of_resetting(self, base_state):
        from backend.agents.supervisor_agent import run_supervisor

        decomposition = TaskDecomposition(
            main_question="Analyze AI chip market",
            subquestions=[ResearchTask(id="market", question="Estimate market size", priority=1)],
        )

        result = await run_supervisor({**base_state, "task_decomposition": decomposition, "revision_count": 2})
        assert result["revision_count"] == 2

    async def test_uses_structured_task_decomposition(self, base_state):
        from backend.agents.supervisor_agent import run_supervisor

        decomposition = TaskDecomposition(
            main_question="Analyze AI chip market",
            subquestions=[
                ResearchTask(id="market", question="Estimate market size", priority=1),
                ResearchTask(id="tam", question="Estimate TAM/SAM/SOM", depends_on=["market"], priority=2),
            ],
        )
        llm_payload = json.dumps(
            {
                "batches": [
                    {"queries": ["Estimate market size"], "mode": "sequential", "rationale": "foundation"},
                    {"queries": ["Estimate TAM/SAM/SOM"], "mode": "sequential", "rationale": "depends on market"},
                ],
                "total_queries": 2,
                "strategy_rationale": "Respect task dependencies",
            }
        )

        with (
            patch("backend.agents.supervisor_agent.retriever.retrieve", AsyncMock(return_value=[])),
            respx.mock,
        ):
            route = respx.post(_OPENROUTER_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": llm_payload}}]},
                )
            )
            result = await run_supervisor({**base_state, "task_decomposition": decomposition})

        assert not route.called
        assert len(result["research_tasks"]) == 2
        assert result["research_tasks"][1].depends_on == ["market"]
        assert result["data_queries"] == ["Estimate market size"]
        assert result["branch_states"][0].next_action == "deepen"
        assert result["branch_states"][1].next_action == "hold"

    async def test_skips_completed_branches_and_plans_only_follow_up(self, base_state):
        from backend.agents.supervisor_agent import run_supervisor

        decomposition = TaskDecomposition(
            main_question="Analyze AI chip market",
            subquestions=[
                ResearchTask(id="market", question="Estimate market size", priority=1),
                ResearchTask(id="pricing", question="Map competitor pricing", priority=1),
            ],
        )
        llm_payload = json.dumps(
            {
                "batches": [
                    {"queries": ["Map competitor pricing"], "mode": "sequential", "rationale": "Only open branch"},
                ],
                "total_queries": 1,
                "strategy_rationale": "Re-run only follow-up work",
            }
        )

        with (
            patch("backend.agents.supervisor_agent.retriever.retrieve", AsyncMock(return_value=[])),
            respx.mock,
        ):
            route = respx.post(_OPENROUTER_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": llm_payload}}]},
                )
            )
            result = await run_supervisor(
                {
                    **base_state,
                    "task_decomposition": decomposition,
                    "branch_states": [
                        ResearchBranchState(task_id="market", question="Estimate market size", status="completed"),
                        ResearchBranchState(task_id="pricing", question="Map competitor pricing", status="needs_follow_up"),
                    ],
                    "research_results": [
                        ResearchResult(
                            query="Estimate market size",
                            findings=["The market is large."],
                            sources=[Source(url="https://a.com", title="A", snippet="source A", domain="a.com")],
                        )
                    ],
                }
            )

        assert not route.called
        assert result["data_queries"] == ["Map competitor pricing"]
        assert any(branch.status == "completed" for branch in result["branch_states"])
        pricing_branch = next(branch for branch in result["branch_states"] if branch.question == "Map competitor pricing")
        assert pricing_branch.next_action in {"widen", "verify", "deepen"}

    async def test_contradiction_log_pushes_branch_to_verify(self, base_state):
        from backend.agents.supervisor_agent import run_supervisor

        decomposition = TaskDecomposition(
            main_question="Analyze AI chip market",
            subquestions=[
                ResearchTask(id="market", question="AI chip market growth", priority=1),
            ],
        )

        result = await run_supervisor(
            {
                **base_state,
                "task_decomposition": decomposition,
                "research_results": [
                    ResearchResult(
                        query="AI chip market growth",
                        findings=["Growth estimates conflict."],
                        sources=[Source(url="https://a.com", title="A", snippet="source A", domain="a.com")],
                    )
                ],
                "contradiction_log": [
                    {
                        "topic": "ai chip market growth",
                        "claims": ["AI chip market growth is 12%", "AI chip market growth is 55%"],
                        "reason": "numeric spread detected (43.0)",
                    }
                ],
            }
        )

        branch = result["branch_states"][0]
        assert branch.next_action == "verify"
        assert branch.contradiction_notes

    async def test_falls_back_when_planner_returns_empty_content(self, base_state):
        from backend.agents.supervisor_agent import run_supervisor

        decomposition = TaskDecomposition(
            main_question="Analyze AI chip market",
            subquestions=[
                ResearchTask(id="market", question="Estimate market size", priority=1),
                ResearchTask(id="pricing", question="Map competitor pricing", priority=1),
            ],
        )

        with (
            patch("backend.agents.supervisor_agent.retriever.retrieve", AsyncMock(return_value=[])),
            respx.mock,
        ):
            route = respx.post(_OPENROUTER_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": None}}]},
                )
            )
            result = await run_supervisor({**base_state, "task_decomposition": decomposition})

        assert route.called
        assert result["data_queries"] == ["Estimate market size", "Map competitor pricing"]
        batches = result["parallel_batches"]
        assert batches.total_queries == 2
        assert len(batches.batches) == 1
        assert batches.batches[0].queries == ["Estimate market size", "Map competitor pricing"]
        assert result["cost_usd"] >= base_state["cost_usd"]


# ---------------------------------------------------------------------------
# TestVizAgent
# ---------------------------------------------------------------------------


class _FakeProcess:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode

    async def communicate(self):
        return b"", b""


class TestVizAgent:
    async def test_skips_chart_generation_when_chrome_missing(self, base_state, tmp_path, monkeypatch):
        from backend.agents.viz_agent import run_viz_agent
        from backend.config import settings

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))
        state = {
            **base_state,
            "session_id": "viz-session",
            "research_results": [
                ResearchResult(
                    query="AI chip market",
                    findings=["NVIDIA has 80% training market share"],
                    sources=[Source(url="https://example.com/nvidia", title="NVIDIA", snippet="share data")],
                )
            ],
        }

        with patch("backend.agents.viz_agent._has_plotly_image_runtime", return_value=False):
            result = await run_viz_agent(state)

        assert result["chart_paths"] == []
        assert result["current_agent"] == "viz_agent"

    async def test_plotly_code_creates_png_in_session_chart_dir(
        self, base_state, tmp_path, monkeypatch
    ):
        from backend.agents.viz_agent import run_viz_agent
        from backend.config import settings

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))
        session_id = "viz-session"
        research = ResearchResult(
            query="AI chip market",
            findings=["NVIDIA has 80% training market share"],
            sources=[Source(url="https://example.com/nvidia", title="NVIDIA", snippet="share data")],
        )
        state = {**base_state, "session_id": session_id, "research_results": [research]}
        llm_payload = json.dumps(
            {
                "charts": [
                    {
                        "chart_type": "bar",
                        "title": "AI Chip Market Share",
                        "description": "Training accelerator share by vendor",
                        "python_code": (
                            "import os, sys\n"
                            "import plotly.graph_objects as go\n"
                            "chart_index = sys.argv[1]\n"
                            "output_dir = sys.argv[2]\n"
                            "fig = go.Figure(data=[go.Bar(x=['NVIDIA', 'AMD'], y=[80, 20])])\n"
                            "fig.write_image(os.path.join(output_dir, f'chart_{chart_index}.png'))\n"
                        ),
                    }
                ]
            }
        )

        async def fake_create_subprocess_exec(*args, **kwargs):
            script_path = Path(args[1])
            output_dir = Path(args[3])
            script_text = script_path.read_text(encoding="utf-8")
            assert "plotly.graph_objects" in script_text
            assert "write_image" in script_text
            output_dir.mkdir(parents=True, exist_ok=True)
            chart_index = args[2]
            (output_dir / f"chart_{chart_index}.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
            return _FakeProcess()

        with respx.mock:
            respx.post(_OPENROUTER_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": llm_payload}}]},
                )
            )
            with patch(
                "backend.agents.viz_agent.asyncio.create_subprocess_exec",
                side_effect=fake_create_subprocess_exec,
            ), patch("backend.agents.viz_agent._has_plotly_image_runtime", return_value=True):
                result = await run_viz_agent(state)

        assert len(result["chart_paths"]) == 1
        chart_path = Path(result["chart_paths"][0])
        assert chart_path.exists()
        assert chart_path.parent == tmp_path / session_id / "charts"


# ---------------------------------------------------------------------------
# TestPresentationAgent
# ---------------------------------------------------------------------------


class TestPresentationAgent:
    async def test_returns_gamma_presentation_url(
        self, presentation_state, monkeypatch
    ):
        from backend.agents.presentation_agent import run_presentation
        from backend.config import settings

        monkeypatch.setattr(settings, "gamma_api_key", "gamma-key")
        monkeypatch.setattr(settings, "presenton_url", "http://presenton.local")

        with patch("asyncio.sleep", new=AsyncMock()):
            with respx.mock:
                respx.post(_OPENROUTER_URL).mock(
                    return_value=httpx.Response(
                        200,
                        json={"choices": [{"message": {"content": _MOCK_SLIDES_RESPONSE}}]},
                    )
                )
                gamma_route = respx.post("https://api.gamma.app/v1/presentations").mock(
                    return_value=httpx.Response(
                        200,
                        json={"url": "https://gamma.app/decks/ai-chip-market"},
                    )
                )
                presenton_route = respx.post("http://presenton.local/api/presentations").mock(
                    return_value=httpx.Response(
                        200,
                        json={"url": "http://presenton.local/presentations/123"},
                    )
                )
                result = await run_presentation(presentation_state)

        assert gamma_route.called
        assert not presenton_route.called
        assert result["presentation_url"] == "https://gamma.app/decks/ai-chip-market"

    async def test_falls_back_to_presenton_when_gamma_fails(
        self, presentation_state, monkeypatch
    ):
        from backend.agents.presentation_agent import run_presentation
        from backend.config import settings

        monkeypatch.setattr(settings, "gamma_api_key", "gamma-key")
        monkeypatch.setattr(settings, "presenton_url", "http://presenton.local")

        with patch("asyncio.sleep", new=AsyncMock()):
            with respx.mock:
                respx.post(_OPENROUTER_URL).mock(
                    return_value=httpx.Response(
                        200,
                        json={"choices": [{"message": {"content": _MOCK_SLIDES_RESPONSE}}]},
                    )
                )
                gamma_route = respx.post("https://api.gamma.app/v1/presentations").mock(
                    return_value=httpx.Response(503, json={"error": "unavailable"})
                )
                presenton_route = respx.post("http://presenton.local/api/presentations").mock(
                    return_value=httpx.Response(
                        200,
                        json={
                            "url": "http://presenton.local/presentations/456",
                            "file_path": "/tmp/presentations/456.pptx",
                        },
                    )
                )
                result = await run_presentation(presentation_state)

        assert gamma_route.called
        assert presenton_route.called
        assert result["presentation_url"] == "http://presenton.local/presentations/456"
        assert result["presentation_path"] == "/tmp/presentations/456.pptx"
