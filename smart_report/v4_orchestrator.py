"""v4 meta-analysis orchestrator — skeleton.

Three async entry-points map 1:1 to the three external-loop steps:

    1. generate_prompt  → calls Prompt Master (implemented, Track A)
    2. analyze          → calls Analyzer     (NotImplementedError — Track B fills)
    3. synthesize       → calls Synthesizer  (NotImplementedError — Track B fills)

Unlike v3's single run() that runs end-to-end, v4 is paused between each step
so the analyst can go paste prompts into external DR tools and upload results.
Session state between pauses lives in V4Session, held by V4SessionStore.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .events import EventEmitter, NullEmitter
from .models import (
    AnalysisOutput,
    FinalReport,
    NormalizedReport,
    ResearchPrompt,
    UploadedMarkdown,
    V4Session,
)
from .analyzer import analyze_reports
from .bibliography import generate_bibliography
from .data_audit import CoverageReport, audit_fact_coverage, build_retry_feedback
from .prompt_master import generate_research_prompt
from .synthesizer import synthesize_final_report

if TYPE_CHECKING:  # pragma: no cover
    pass


class V4SessionStore:
    """In-memory store of V4Session objects, keyed by session_id.

    Process-local — acceptable for MVP (v3's /api/research uses the same pattern).
    A future persistence layer would replace this class with a DB-backed one.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, V4Session] = {}

    def create(self, session_id: str, raw_question: str) -> V4Session:
        if session_id in self._sessions:
            raise ValueError(f"session {session_id!r} already exists")
        s = V4Session(
            session_id=session_id,
            raw_question=raw_question,
            status="created",
            created_at=datetime.now(timezone.utc),
        )
        self._sessions[session_id] = s
        return s

    def get(self, session_id: str) -> V4Session:
        s = self._sessions.get(session_id)
        if s is None:
            raise KeyError(session_id)
        return s

    def update(self, session: V4Session) -> V4Session:
        self._sessions[session.session_id] = session
        return session

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def all(self) -> list[V4Session]:
        return list(self._sessions.values())


class V4Orchestrator:
    """Three-step orchestrator; each step is an independent async call."""

    def __init__(
        self,
        session_store: V4SessionStore,
        emitter: EventEmitter | None = None,
        *,
        log_dir: Path | None = None,
        mock: bool = False,
    ) -> None:
        self.store = session_store
        self.emitter = emitter or NullEmitter()
        self.log_dir = log_dir
        self.mock = mock

    # --- step 1: Prompt Master ---
    async def generate_prompt(
        self, session_id: str, question: str | None = None
    ) -> ResearchPrompt:
        session = self.store.get(session_id)
        q = question if question is not None else session.raw_question
        prompt, cost_rub = await generate_research_prompt(
            q,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
        )
        session.research_prompt = prompt
        session.status = "prompt_ready"
        self.store.update(session)
        session = self._accumulate_cost(session, cost_rub)
        return prompt

    # --- step 2: Analyzer ---
    async def analyze(
        self,
        session_id: str,
        reports: list[UploadedMarkdown] | None = None,
    ) -> AnalysisOutput:
        session = self.store.get(session_id)
        if reports:
            session.source_reports = list(reports)
        if not session.source_reports:
            raise ValueError(
                f"session {session_id}: no source_reports to analyze — "
                "upload reports first"
            )
        session.status = "reports_uploaded"
        self.store.update(session)

        analysis, cost_rub = await analyze_reports(
            question=session.raw_question,
            research_prompt=session.research_prompt,
            source_reports=session.source_reports,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
        )
        session.analysis = analysis
        session.status = "analyzed"
        self.store.update(session)
        session = self._accumulate_cost(session, cost_rub)
        return analysis

    # --- step 3: Synthesizer ---
    async def synthesize(
        self,
        session_id: str,
        followup: list[UploadedMarkdown] | None = None,
    ) -> FinalReport:
        session = self.store.get(session_id)
        if followup:
            session.followup_reports = list(followup)
            session.status = "dobor_uploaded"
            self.store.update(session)
        if session.analysis is None:
            raise ValueError(
                f"session {session_id}: analyze must run before synthesize"
            )

        # Step 3a: first synthesis pass
        final, cost_rub = await synthesize_final_report(
            session,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
        )
        session = self._accumulate_cost(session, cost_rub)

        # Step 3b: bibliography post-processing
        final, coverage_pct = generate_bibliography(final)
        self.emitter.emit(
            "bibliography",
            "Bibliography generated",
            data={
                "source_count": final.source_count,
                "citation_coverage": final.citation_coverage,
            },
        )

        # Step 3c: data coverage audit
        coverage_report: CoverageReport = audit_fact_coverage(session.analysis, final)
        self.emitter.emit(
            "data_audit",
            f"Coverage audit: {coverage_report.verdict}",
            data={
                "coverage_pct": coverage_report.coverage_pct,
                "facts_in_final": coverage_report.facts_in_final,
                "high_relevance_total": coverage_report.high_relevance_total,
                "verdict": coverage_report.verdict,
            },
        )

        # Step 3d: one retry if coverage is poor/critical
        if coverage_report.verdict in ("poor", "critical_failure") and not self.mock:
            feedback = build_retry_feedback(coverage_report)
            if feedback and session.analysis.high_relevance_facts:
                self.emitter.emit(
                    "synthesizer",
                    "Coverage below target — retrying with feedback",
                    data={"verdict": coverage_report.verdict},
                )
                # Add feedback to session metadata so synthesizer sees it
                session.analysis.quality_notes = (
                    (session.analysis.quality_notes or "") + "\n\n" + feedback
                )
                final_retry, cost_rub_retry = await synthesize_final_report(
                    session,
                    emitter=self.emitter,
                    log_dir=self.log_dir,
                    mock=self.mock,
                )
                session = self._accumulate_cost(session, cost_rub_retry)
                # Re-run bibliography on retry result
                final_retry, _ = generate_bibliography(final_retry)
                coverage_report_retry = audit_fact_coverage(session.analysis, final_retry)
                # Always proceed after single retry
                final = final_retry
                coverage_report = coverage_report_retry
                self.emitter.emit(
                    "data_audit",
                    f"Post-retry coverage: {coverage_report.verdict}",
                    data={
                        "coverage_pct": coverage_report.coverage_pct,
                        "verdict": coverage_report.verdict,
                    },
                )

        # Save CoverageReport to metadata
        final.metadata["coverage_audit"] = {
            "coverage_pct": coverage_report.coverage_pct,
            "facts_in_final": coverage_report.facts_in_final,
            "high_relevance_total": coverage_report.high_relevance_total,
            "verdict": coverage_report.verdict,
            "detail": coverage_report.detail,
        }

        session.final_report = final
        session.status = "synthesized"
        self.store.update(session)
        return final

    # --- cost accounting ---
    def _accumulate_cost(self, session: V4Session, llm_result_cost_rub: float) -> V4Session:
        """Add a single LLM-call cost to the session total.

        llm.py currently logs cost per call into runs/<ts>/llm_log.jsonl but does
        not expose a process-level meter. Track B or a follow-up should wire the
        real value in; for now this helper is the single place where that
        integration lands, so callers already talk to the right API.
        """
        if llm_result_cost_rub and llm_result_cost_rub > 0:
            session.total_cost_rub = round(session.total_cost_rub + llm_result_cost_rub, 4)
            self.store.update(session)
        return session
