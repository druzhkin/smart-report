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
from .config import models_for_preference
from .data_audit import CoverageReport, audit_fact_coverage, build_retry_feedback
from .intake import normalize_all_reports
from .prompt_master import generate_research_prompt
from .gap_detector import detect_gaps, gap_count_by_severity
from .synthesis_critic import ConsistencyReport, validate_consistency
from .synthesizer import full_report_text, synthesize_final_report
from .i18n import lint_output_language

if TYPE_CHECKING:  # pragma: no cover
    pass


# Track 3 (Language Lint) retry threshold — number of non-whitelisted Latin
# tokens above which the orchestrator retries the Synthesizer with a feedback
# pass. Live Acceptance Run 1 measured 100-310 warnings on realistic Russian
# RE reports because 5-20 mentions of international consultancies (JLL, CBRE,
# Knight Frank, Cushman & Wakefield, etc.) each emit several lint hits even
# when the brand itself is whitelisted (article fragments around the brand
# trip the Latin-token regex). Threshold of 20 made every such run pay 3×
# Synthesizer cost. 100 still catches the genuine "report half in English"
# bad case (which produces 1000+ warnings) while letting realistic
# Russian-language reports complete in one pass.
LINT_WARNING_RETRY_THRESHOLD = 100


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
        self, session_id: str, question: str | None = None, model_preference: str | None = None
    ) -> ResearchPrompt:
        session = self.store.get(session_id)
        q = question if question is not None else session.raw_question
        models = models_for_preference(model_preference)
        prompt, cost_rub = await generate_research_prompt(
            q,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
            model=models["prompt_master"],
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
        model_preference: str | None = None,
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

        # v4.5: normalize each source report (extract citations + numeric/qualitative facts)
        research_prompt_text = (
            session.research_prompt.full_prompt if session.research_prompt else session.raw_question
        )
        normalized_reports = await normalize_all_reports(
            session.source_reports,
            research_prompt=research_prompt_text,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
        )
        session.normalized_reports = normalized_reports

        models = models_for_preference(model_preference)
        analysis, cost_rub = await analyze_reports(
            question=session.raw_question,
            research_prompt=session.research_prompt,
            source_reports=session.source_reports,
            normalized_reports=normalized_reports,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
            model=models["analyzer"],
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
        model_preference: str | None = None,
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
        models = models_for_preference(model_preference)
        final, cost_rub = await synthesize_final_report(
            session,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
            model=models["synthesizer"],
        )
        session = self._accumulate_cost(session, cost_rub)

        # Step 3b: bibliography post-processing
        final, _ = generate_bibliography(final)

        # Step 3b.1 (Phase 2 Step 2.3 — C6 degraded): per-sub-question
        # evidence-adequacy detection. Mutates session.research_prompt
        # SubQuestions in place with bibliography_refs / status, and
        # surfaces gaps via final.metadata + confidence_note. Fires
        # only when the planner produced sub_questions (RU RE template
        # path also populates inline SubQuery dicts but those use a
        # different schema and are out of scope for the C6 detector).
        if session.research_prompt and session.research_prompt.sub_questions:
            await _attach_evidence_gaps(
                final,
                session.research_prompt.sub_questions,
                session.analysis,
                emitter=self.emitter,
            )
            self.store.update(session)  # SubQuestions mutated in place

        # COMMIT the first-pass result IMMEDIATELY so downstream retry failures
        # (coverage/consistency/language) don't lose the report we already paid for.
        # Any subsequent retries mutate `final` in-place and re-commit.
        session.final_report = final
        session.status = "synthesized"
        self.store.update(session)
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

        # Step 3d: one retry on coverage failure (best-effort — don't nuke first pass)
        if coverage_report.verdict in ("poor", "critical_failure") and not self.mock:
            feedback = build_retry_feedback(coverage_report)
            if feedback and session.analysis.high_relevance_facts:
                self.emitter.emit(
                    "synthesizer",
                    "Coverage below target — retrying with feedback",
                    data={"verdict": coverage_report.verdict},
                )
                session.analysis.quality_notes = (
                    (session.analysis.quality_notes or "") + "\n\n" + feedback
                )
                try:
                    final_retry, cost_rub_retry = await synthesize_final_report(
                        session,
                        emitter=self.emitter,
                        log_dir=self.log_dir,
                        mock=self.mock,
                        model=models["synthesizer"],
                    )
                    session = self._accumulate_cost(session, cost_rub_retry)
                    final_retry, _ = generate_bibliography(final_retry)
                    coverage_report = audit_fact_coverage(session.analysis, final_retry)
                    final = final_retry
                    session.final_report = final
                    self.store.update(session)
                except Exception as e:
                    self.emitter.emit("synthesizer", f"Coverage retry failed: {e!r} — keeping first pass", data={})

        final.metadata["coverage_audit"] = {
            "coverage_pct": coverage_report.coverage_pct,
            "facts_in_final": coverage_report.facts_in_final,
            "high_relevance_total": coverage_report.high_relevance_total,
            "verdict": coverage_report.verdict,
            "detail": coverage_report.detail,
        }
        self.store.update(session)

        # Step 3e: Consistency Critic loop (max 1 retry, best-effort)
        try:
            consistency = await validate_consistency(
                final,
                emitter=self.emitter,
                log_dir=self.log_dir,
                mock=self.mock,
                model=models["critic"],
            )
            if consistency.overall_verdict == "critical_failure":
                try:
                    final, cost_rub_c = await synthesize_final_report(
                        session,
                        emitter=self.emitter,
                        log_dir=self.log_dir,
                        mock=self.mock,
                        consistency_feedback=consistency,
                        model=models["synthesizer"],
                    )
                    session = self._accumulate_cost(session, cost_rub_c)
                    final, _ = generate_bibliography(final)
                    consistency = await validate_consistency(
                        final,
                        emitter=self.emitter,
                        log_dir=self.log_dir,
                        mock=self.mock,
                        model=models["critic"],
                    )
                    session.final_report = final
                    self.store.update(session)
                except Exception as e:
                    self.emitter.emit("synthesizer", f"Consistency retry failed: {e!r} — keeping current", data={})
            final.metadata["consistency_check"] = consistency.model_dump()
        except Exception as e:
            self.emitter.emit("critic", f"Consistency check failed: {e!r} — skipping", data={})
            final.metadata["consistency_check"] = {"error": str(e), "overall_verdict": "skipped"}
        self.store.update(session)

        # Step 3f: Language lint (Track 3) — retry above LINT_WARNING_RETRY_THRESHOLD, best-effort
        lint_warnings = lint_output_language(full_report_text(final))
        if len(lint_warnings) > LINT_WARNING_RETRY_THRESHOLD and not self.mock:
            self.emitter.emit(
                "orchestrator",
                f"Language lint: {len(lint_warnings)} warnings — retrying Synthesizer",
                data={"warnings_count": len(lint_warnings)},
            )
            try:
                final_l, cost_rub_l = await synthesize_final_report(
                    session,
                    emitter=self.emitter,
                    log_dir=self.log_dir,
                    mock=self.mock,
                    language_feedback=[w.model_dump() for w in lint_warnings],
                    model=models["synthesizer"],
                )
                session = self._accumulate_cost(session, cost_rub_l)
                final_l, _ = generate_bibliography(final_l)
                lint_warnings = lint_output_language(full_report_text(final_l))
                final = final_l
                session.final_report = final
                self.store.update(session)
            except Exception as e:
                self.emitter.emit("orchestrator", f"Language retry failed: {e!r} — keeping current", data={})

        final.metadata["language_lint"] = {
            "warnings_count": len(lint_warnings),
            "warnings": [w.model_dump() for w in lint_warnings[:20]],
        }

        session.final_report = final
        session.status = "synthesized"
        self.store.update(session)
        return final

    # --- gap detection helper exposed at module level for cleaner testing ---
    # See _attach_evidence_gaps below.

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


# ---------------------------------------------------------------------------
# Phase 2 Step 2.3 — Gap detection helper
# ---------------------------------------------------------------------------


_SEVERITY_LABEL_RU = {
    "critical": "Критично",
    "moderate": "Умеренно",
    "minor": "Незначительно",
}


def _format_gap_warning_for_confidence_note(gaps: list) -> str:
    """Render gaps as a Cyrillic warning for executive_summary.confidence_note.

    Same anti-lint-retry discipline as Step 1.2: zero Latin-script
    sentinels in the visible string (paid lesson 7.2). The
    machine-readable list — including sub_question ids and API endpoint
    references — lives in metadata["evidence_gaps"]; this is the
    human-facing summary, kept in pure Cyrillic so it never trips the
    language linter and never costs a Track 3 retry.
    """
    if not gaps:
        return ""
    counts = gap_count_by_severity(gaps)
    header = (
        f"⚠ Пробелы в доказательной базе: найдено {len(gaps)} под-вопросов "
        f"с недостаточным покрытием (критичных: {counts['critical']}, "
        f"умеренных: {counts['moderate']}, незначительных: {counts['minor']})."
    )
    bullets = []
    for i, g in enumerate(gaps[:8], start=1):  # cap to keep note readable
        label = _SEVERITY_LABEL_RU.get(g.severity, g.severity)
        sq_text = g.sub_question_text
        if len(sq_text) > 120:
            sq_text = sq_text[:117] + "…"
        # Use Cyrillic ordinal "Под-вопрос N:" so the visible string
        # carries no Latin tokens; raw sub_question_id stays in metadata.
        bullets.append(f"• [{label}] Под-вопрос {i}: {sq_text}")
    if len(gaps) > 8:
        bullets.append(f"…и ещё {len(gaps) - 8} под-вопросов с пробелами.")
    suffix = (
        "Аналитику стоит прогнать целевые исследовательские запросы по "
        "этим темам и повторно загрузить новые отчёты в систему. "
        "Целевые промпты доступны через системный эндпоинт проверки "
        "пробелов (см. метаданные отчёта)."
    )
    return header + "\n\n" + "\n".join(bullets) + "\n\n" + suffix


async def _attach_evidence_gaps(
    final, sub_questions: list, analysis, *, emitter
) -> None:
    """Run gap detection and surface results on *final* in place.

    - final.metadata["evidence_gaps"]: list[dict] for downstream readers
    - final.metadata["gap_count_by_severity"]: tally
    - final.executive_summary.confidence_note: prefixed Cyrillic warning
      (preserves any existing note from Step 1.2 LOW_EVIDENCE_QUALITY
      or LLM-generated text)
    """
    gaps = await detect_gaps(sub_questions, analysis)
    final.metadata["evidence_gaps"] = [g.model_dump() for g in gaps]
    final.metadata["gap_count_by_severity"] = gap_count_by_severity(gaps)
    emitter.emit(
        "gap_detector",
        f"Gap detection: {len(gaps)} gaps across {len(sub_questions)} sub-questions",
        data=final.metadata["gap_count_by_severity"],
    )
    if gaps:
        warning = _format_gap_warning_for_confidence_note(gaps)
        prior_note = final.executive_summary.confidence_note
        merged_note = warning if not prior_note else f"{warning}\n\n{prior_note}"
        final.executive_summary = final.executive_summary.model_copy(
            update={"confidence_note": merged_note}
        )
