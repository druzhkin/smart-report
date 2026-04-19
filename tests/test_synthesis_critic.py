"""Tests for Consistency Critic (Track 2 v4.5).

All LLM calls are mocked — no real API calls are made in this module.
The real critic pass on cache_final.json is a separate script (scripts/run_critic_baseline.py).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from smart_report.llm import LLMResult
from smart_report.models import (
    AnalysisOutput,
    CalloutBlock,
    ChartSpec,
    ExecutiveSummaryV4,
    FinalReport,
    KeyNumber,
    KeyNumberHighlight,
    QAItem,
    RankingItem,
    ResearchPrompt,
    Source,
    Table,
    UploadedMarkdown,
    V4Session,
)
from smart_report.synthesis_critic import (
    ConsistencyIssue,
    ConsistencyReport,
    _compute_verdict,
    _parse_issues,
    build_consistency_feedback_text,
    validate_consistency,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_final_report(
    *,
    main_answer: str = "Синтез готов.",
    qa_section: list[QAItem] | None = None,
    ranking: list[RankingItem] | None = None,
    top_findings: list[str] | None = None,
    key_numbers: list[KeyNumber] | None = None,
    main_synthesis: str = "",
    conflicts_section: str = "",
    consensus_section: str = "",
    tables: list[Table] | None = None,
    callouts: list[CalloutBlock] | None = None,
    key_numbers_highlight: list[KeyNumberHighlight] | None = None,
    metadata: dict | None = None,
) -> FinalReport:
    return FinalReport(
        session_id="test-session",
        question="Тест",
        research_prompt_used="",
        executive_summary=ExecutiveSummaryV4(
            main_answer=main_answer,
            top_findings=top_findings or [],
            key_numbers=key_numbers or [],
            confidence_note="",
            what_meta_adds="",
        ),
        main_synthesis=main_synthesis,
        consensus_section=consensus_section,
        conflicts_section=conflicts_section,
        gaps_filled_section="",
        all_sources=[],
        metadata=metadata or {},
        qa_section=qa_section or [],
        ranking=ranking or [],
        tables=tables or [],
        charts=[],
        callouts=callouts or [],
        key_numbers_highlight=key_numbers_highlight or [],
    )


def _pool_triangle_report() -> FinalReport:
    """Synthetic FinalReport with the exact pool 22%/8%/EXCLUDE pattern from v4 ночной."""
    return _make_final_report(
        main_answer=(
            "В Москве 2022-2025 устойчивую ценовую премию создают outdoor-стек, arrival, "
            "fitness-first wellness и tech-stack. Бассейн 25м + SPA в бизнес-классе имеют "
            "системно отрицательный NPV. Бассейн — exclude по умолчанию для бизнес-класса."
        ),
        top_findings=[
            "Бассейн 25м + SPA в бизнес-классе: exclude-решение по всем 4 источникам [консенсус]",
            "MR Group survey 2026: 22% покупателей называют бассейн существенным преимуществом",
        ],
        key_numbers=[
            KeyNumber(value="22%", metric="называют бассейн существенным преимуществом",
                      subject="опрос MR Group 2026", source_url=""),
        ],
        qa_section=[
            QAItem(
                question="Какие amenities реально пользуются спросом?",
                answer=(
                    "Доказанный спрос: закрытая территория, качественные МОПы, фитнес. "
                    "MR Group survey апрель 2026: 22% покупателей называют бассейн "
                    "существенным преимуществом при покупке, 74% считают близость спорта важной."
                ),
                details_ref="Раздел «Иерархия спроса на amenities»",
            ),
        ],
        ranking=[
            RankingItem(label="Закрытая охраняемая территория", weight=25,
                        rationale="Наибольшая ценовая премия (+7-12%)", evidence_strength="high"),
            RankingItem(label="Качественные МОПы", weight=22,
                        rationale="Первое что видит покупатель", evidence_strength="high"),
            RankingItem(label="Фитнес-центр", weight=18,
                        rationale="+3-5% к цене", evidence_strength="medium"),
            RankingItem(label="Благоустройство двора", weight=15,
                        rationale="Семейная аудитория", evidence_strength="high"),
            RankingItem(label="Консьерж-сервис", weight=10,
                        rationale="Дифференциатор", evidence_strength="medium"),
            RankingItem(label="Бассейн", weight=8,
                        rationale="Имиджевый актив, окупается только в ультра-премиум",
                        evidence_strength="medium"),
            RankingItem(label="Сигарная комната", weight=4,
                        rationale="Нишевый спрос", evidence_strength="low"),
        ],
        main_synthesis=(
            "## Позиция автора\n\nВ бизнес-классе Бассейн — exclude по умолчанию. "
            "CAPEX 120-180 млн руб., премия +2-4% не окупает.\n\n"
            "## Иерархия спроса\n\nFitness — must-have. Pool — exclude в бизнесе."
        ),
        conflicts_section="",  # NOTE: no explicit pool triangle resolution here
    )


def _clean_report() -> FinalReport:
    """Minimal FinalReport with no conflicts — everything aligned."""
    return _make_final_report(
        main_answer="Фитнес даёт +3-5% премию, подтверждён консенсусом трёх источников.",
        top_findings=["Фитнес — must-have с ценовой премией +3-5% [консенсус]"],
        qa_section=[
            QAItem(
                question="Что реально важно для покупателей?",
                answer=(
                    "Фитнес-центр в доме даёт ценовую премию +3-5% по данным консенсуса. "
                    "Это ROI-эффективный amenity с низким OPEX относительно бассейна."
                ),
                details_ref="Раздел «Иерархия спроса»",
            ),
        ],
        ranking=[
            RankingItem(label="Фитнес-центр", weight=18,
                        rationale="+3-5% к цене, высокий спрос 74% (MR Group), OPEX в 4× ниже бассейна",
                        evidence_strength="medium"),
        ],
        main_synthesis="## Фитнес\n\nФитнес входит в must-have стек: +3-5% премия, OPEX приемлемый.",
        conflicts_section=(
            "Бассейн: потребительский спрос 22% (MR Group 2026) vs экономическая "
            "целесообразность. Вердикт: спрос есть, но NPV отрицательный в бизнес-классе. "
            "В премиуме (GBA ≥30k м²) — include."
        ),
    )


def _explicit_nuance_report() -> FinalReport:
    """Report that mentions pool survey AND explicitly explains the nuance (importance ≠ ROI)."""
    return _make_final_report(
        main_answer=(
            "Бассейн важен на уровне потребительского спроса (22% MR Group), "
            "но экономически слаб (ROI 0.3, CAPEX 45M). Это не противоречие: "
            "потребительская важность ≠ ROI для застройщика."
        ),
        qa_section=[
            QAItem(
                question="Нужен ли бассейн в бизнес-классе?",
                answer=(
                    "Бассейн важен на уровне потребительского спроса (22%), "
                    "но экономически слаб из-за CAPEX/OPEX. "
                    "Правило: exclude в бизнес-классе, include в премиуме (GBA ≥30k м²)."
                ),
                details_ref="Conflicts Section",
            ),
        ],
        ranking=[
            RankingItem(label="Бассейн", weight=8,
                        rationale=(
                            "22% потребительского спроса (MR Group 2026), но ROI отрицательный "
                            "в бизнес-классе (CAPEX 120-180 млн, надбавка +2-4% не окупает). "
                            "Вес отражает ROI, не потребительскую важность."
                        ),
                        evidence_strength="medium"),
        ],
        conflicts_section=(
            "Pool-треугольник: 22% потребительский спрос vs 8% рейтинг vs EXCLUDE-вердикт. "
            "Разрешение: потребительская важность ≠ экономическая целесообразность. "
            "При CAPEX 120-180 млн и надбавке +2-4% NPV отрицателен. "
            "Вердикт: exclude для бизнес-класса, include для премиума (GBA ≥30k м²)."
        ),
    )


def _rounding_report() -> FinalReport:
    """Report with 'около 20%' in one place and '22%' in another — should NOT be flagged."""
    return _make_final_report(
        main_answer="Около 20% покупателей интересуются бассейном.",
        qa_section=[
            QAItem(
                question="Какой спрос на бассейн?",
                answer="22% покупателей называют бассейн существенным преимуществом (MR Group 2026).",
                details_ref="Main Synthesis",
            ),
        ],
        main_synthesis="Около 20% (точнее 22% по MR Group) упоминают бассейн.",
    )


# ---------------------------------------------------------------------------
# Unit tests: pure logic (no LLM)
# ---------------------------------------------------------------------------


class TestComputeVerdict:
    def test_no_issues_gives_pass(self):
        verdict, counts = _compute_verdict([])
        assert verdict == "pass"
        assert counts == {"critical": 0, "material": 0, "minor": 0}

    def test_one_critical_gives_needs_revision(self):
        issues = [
            ConsistencyIssue(
                severity="critical", category="verdict_evidence_gap",
                location_a="A", statement_a="X",
                location_b="B", statement_b="Y",
                why_inconsistent="conflict", suggested_fix="fix it",
            )
        ]
        verdict, counts = _compute_verdict(issues)
        assert verdict == "needs_revision"
        assert counts["critical"] == 1

    def test_three_critical_gives_critical_failure(self):
        issues = [
            ConsistencyIssue(
                severity="critical", category="verdict_evidence_gap",
                location_a="A", statement_a="X",
                location_b="B", statement_b="Y",
                why_inconsistent="conflict", suggested_fix="fix",
            )
        ] * 3
        verdict, counts = _compute_verdict(issues)
        assert verdict == "critical_failure"
        assert counts["critical"] == 3

    def test_two_critical_gives_needs_revision(self):
        issues = [
            ConsistencyIssue(
                severity="critical", category="number_conflict",
                location_a="A", statement_a="55%",
                location_b="B", statement_b="68%",
                why_inconsistent="different values", suggested_fix="fix",
            )
        ] * 2
        verdict, counts = _compute_verdict(issues)
        assert verdict == "needs_revision"

    def test_four_material_gives_needs_revision(self):
        issues = [
            ConsistencyIssue(
                severity="material", category="table_prose_disagreement",
                location_a="A", statement_a="X",
                location_b="B", statement_b="Y",
                why_inconsistent="disagree", suggested_fix="fix",
            )
        ] * 4
        verdict, counts = _compute_verdict(issues)
        assert verdict == "needs_revision"

    def test_one_minor_gives_pass(self):
        issues = [
            ConsistencyIssue(
                severity="minor", category="source_attribution_inconsistency",
                location_a="A", statement_a="X",
                location_b="B", statement_b="Y",
                why_inconsistent="minor", suggested_fix="fix",
            )
        ]
        verdict, _ = _compute_verdict(issues)
        assert verdict == "pass"


class TestParseIssues:
    def test_valid_issue_parsed(self):
        raw = [{
            "severity": "critical",
            "category": "verdict_evidence_gap",
            "location_a": "QA Section",
            "statement_a": "22% хотят бассейн",
            "location_b": "Ranking",
            "statement_b": "weight=8%",
            "why_inconsistent": "нет объяснения нюанса",
            "suggested_fix": "добавить в QA квалификатор",
        }]
        issues = _parse_issues(raw)
        assert len(issues) == 1
        assert issues[0].severity == "critical"
        assert issues[0].category == "verdict_evidence_gap"

    def test_invalid_severity_skipped(self):
        raw = [{
            "severity": "extreme",  # invalid
            "category": "verdict_evidence_gap",
            "location_a": "A", "statement_a": "x",
            "location_b": "B", "statement_b": "y",
            "why_inconsistent": "w", "suggested_fix": "f",
        }]
        assert _parse_issues(raw) == []

    def test_invalid_category_skipped(self):
        raw = [{
            "severity": "critical",
            "category": "unknown_category",  # invalid
            "location_a": "A", "statement_a": "x",
            "location_b": "B", "statement_b": "y",
            "why_inconsistent": "w", "suggested_fix": "f",
        }]
        assert _parse_issues(raw) == []

    def test_non_dict_entry_skipped(self):
        assert _parse_issues(["not_a_dict", 42, None]) == []

    def test_non_list_returns_empty(self):
        assert _parse_issues(None) == []
        assert _parse_issues("string") == []


class TestBuildFeedbackText:
    def test_no_critical_returns_empty(self):
        report = ConsistencyReport(
            issues=[
                ConsistencyIssue(
                    severity="minor", category="source_attribution_inconsistency",
                    location_a="A", statement_a="x",
                    location_b="B", statement_b="y",
                    why_inconsistent="minor", suggested_fix="fix",
                )
            ],
            severity_summary={"critical": 0, "material": 0, "minor": 1},
            overall_verdict="pass",
        )
        assert build_consistency_feedback_text(report) == ""

    def test_critical_issue_included_in_feedback(self):
        report = ConsistencyReport(
            issues=[
                ConsistencyIssue(
                    severity="critical", category="verdict_evidence_gap",
                    location_a="QA Section — qa_1_answer",
                    statement_a="22% хотят бассейн",
                    location_b="Main Synthesis — раздел Implications",
                    statement_b="бассейн EXCLUDE",
                    why_inconsistent="нет объяснения",
                    suggested_fix="добавить квалификатор в QA",
                )
            ],
            severity_summary={"critical": 1, "material": 0, "minor": 0},
            overall_verdict="needs_revision",
        )
        text = build_consistency_feedback_text(report)
        assert "КРИТИКОМ" in text
        assert "22% хотят бассейн" in text
        assert "EXCLUDE" in text
        assert "добавить квалификатор в QA" in text


# ---------------------------------------------------------------------------
# Tests with mocked LLM
# ---------------------------------------------------------------------------


def _make_critic_response(issues: list[dict]) -> str:
    """Build a JSON string as the critic LLM would return."""
    counts: dict[str, int] = {"critical": 0, "material": 0, "minor": 0}
    for i in issues:
        counts[i.get("severity", "minor")] = counts.get(i.get("severity", "minor"), 0) + 1

    n_crit = counts["critical"]
    if n_crit > 2:
        verdict = "critical_failure"
    elif n_crit >= 1 or counts["material"] > 3:
        verdict = "needs_revision"
    else:
        verdict = "pass"

    return json.dumps({
        "issues": issues,
        "severity_summary": counts,
        "overall_verdict": verdict,
    }, ensure_ascii=False)


_POOL_TRIANGLE_LLM_RESPONSE = _make_critic_response([
    {
        "severity": "critical",
        "category": "verdict_evidence_gap",
        "location_a": "QA Section — qa_1_answer",
        "statement_a": "22% покупателей называют бассейн существенным преимуществом",
        "location_b": "Ranking — ranking_6",
        "statement_b": "Бассейн weight=8%, rationale='Имиджевый актив, окупается только в ультра-премиум'",
        "why_inconsistent": (
            "22% потребительского спроса фиксируются в QA, но Ranking ставит бассейн низко "
            "без объяснения нюанса 'важность ≠ ROI'. Читатель видит противоречие."
        ),
        "suggested_fix": (
            "В [qa_1_answer] добавить: 'При этом экономически бассейн слаб для бизнес-класса: "
            "CAPEX 120-180 млн, NPV отрицательный — см. Ranking и Conflicts.'"
        ),
    },
    {
        "severity": "critical",
        "category": "ranking_qa_mismatch",
        "location_a": "Executive Summary — top_finding_1",
        "statement_a": "Бассейн: exclude-решение по всем 4 источникам [консенсус]",
        "location_b": "QA Section — qa_1_answer",
        "statement_b": "22% покупателей называют бассейн существенным преимуществом",
        "why_inconsistent": "Top Findings декларирует EXCLUDE, QA фиксирует 22% спроса без разрешения разрыва.",
        "suggested_fix": (
            "Перенести pool-противоречие в conflicts_section с явным разрешением: "
            "'Потребительский спрос (22%) vs NPV отрицательный: exclude для бизнеса, include для премиума.'"
        ),
    },
    {
        "severity": "critical",
        "category": "verdict_evidence_gap",
        "location_a": "Main Synthesis — Бассейн — exclude по умолчанию",
        "statement_a": "Бассейн — exclude по умолчанию для бизнес-класса",
        "location_b": "QA Section — qa_1_answer + Ranking — ranking_6",
        "statement_b": "22% спроса + weight=8% без связующей логики",
        "why_inconsistent": (
            "Треугольник: exclude + 22%-важен + 8%-низкий приоритет. "
            "Три сигнала без единого объединяющего объяснения."
        ),
        "suggested_fix": (
            "Создать единый параграф в conflicts_section: 'Pool-треугольник: 22% спрос vs 8% ранг vs "
            "EXCLUDE. Разрешение: важность ≠ ROI. CAPEX 120-180 млн при +2-4% надбавке = отрицательный NPV.'"
        ),
    },
])

_CLEAN_LLM_RESPONSE = _make_critic_response([])

_NUANCE_EXPLICIT_LLM_RESPONSE = _make_critic_response([])

_ROUNDING_LLM_RESPONSE = _make_critic_response([])


@pytest.mark.asyncio
async def test_critic_finds_pool_triangle():
    """Synthetic FinalReport with pool 22/8/EXCLUDE pattern → ≥1 critical issue."""
    report = _pool_triangle_report()

    with patch(
        "smart_report.synthesis_critic.call_json",
        new_callable=AsyncMock,
        return_value=LLMResult(text=_POOL_TRIANGLE_LLM_RESPONSE, cost_rub=0.0),
    ):
        result = await validate_consistency(report, mock=False)

    assert len(result.issues) >= 1
    critical_issues = [i for i in result.issues if i.severity == "critical"]
    assert len(critical_issues) >= 1

    # At least one should be in verdict_evidence_gap or ranking_qa_mismatch
    relevant_cats = {"verdict_evidence_gap", "ranking_qa_mismatch"}
    assert any(i.category in relevant_cats for i in critical_issues)

    assert result.overall_verdict in ("needs_revision", "critical_failure")


@pytest.mark.asyncio
async def test_critic_passes_clean_report():
    """Minimal FinalReport with no conflicts → issues == [], verdict == 'pass'."""
    report = _clean_report()

    with patch(
        "smart_report.synthesis_critic.call_json",
        new_callable=AsyncMock,
        return_value=LLMResult(text=_CLEAN_LLM_RESPONSE, cost_rub=0.0),
    ):
        result = await validate_consistency(report, mock=False)

    assert result.issues == []
    assert result.overall_verdict == "pass"


@pytest.mark.asyncio
async def test_critic_respects_explicit_nuance():
    """Report with explicit 'важность ≠ ROI' nuance → 0 critical issues."""
    report = _explicit_nuance_report()

    with patch(
        "smart_report.synthesis_critic.call_json",
        new_callable=AsyncMock,
        return_value=LLMResult(text=_NUANCE_EXPLICIT_LLM_RESPONSE, cost_rub=0.0),
    ):
        result = await validate_consistency(report, mock=False)

    critical_issues = [i for i in result.issues if i.severity == "critical"]
    assert len(critical_issues) == 0


@pytest.mark.asyncio
async def test_critic_respects_rounding():
    """'около 20%' vs '22%' should not trigger a critical issue."""
    report = _rounding_report()

    with patch(
        "smart_report.synthesis_critic.call_json",
        new_callable=AsyncMock,
        return_value=LLMResult(text=_ROUNDING_LLM_RESPONSE, cost_rub=0.0),
    ):
        result = await validate_consistency(report, mock=False)

    critical_issues = [i for i in result.issues if i.severity == "critical"]
    assert len(critical_issues) == 0


@pytest.mark.asyncio
async def test_retry_loop_reduces_issues():
    """Orchestrator retry loop: 3 critical first pass → 0 second pass → final verdict=pass."""
    from datetime import datetime, timezone
    from smart_report.v4_orchestrator import V4Orchestrator, V4SessionStore

    store = V4SessionStore()
    session = store.create("sess-retry", "Тест")
    session.source_reports = [
        UploadedMarkdown(filename="a.md", content="report A", detected_tool="perplexity"),
    ]
    session.analysis = AnalysisOutput()
    store.update(session)

    # First synthesizer call returns a report with the pool triangle
    pool_report_json = _pool_triangle_report().model_dump()
    pool_report_json["session_id"] = "sess-retry"

    # Second synthesizer call (retry) returns a clean report
    clean_report_json = _clean_report().model_dump()
    clean_report_json["session_id"] = "sess-retry"

    # Critic: first call returns 3 critical, second call returns 0
    synth_call_count = 0
    critic_call_count = 0

    async def mock_synthesize(session, *, emitter=None, log_dir=None, mock=False,
                               consistency_feedback=None):
        nonlocal synth_call_count
        synth_call_count += 1
        if synth_call_count == 1:
            return _pool_triangle_report(), 0.0
        else:
            return _clean_report(), 0.0

    async def mock_validate(report, *, emitter=None, log_dir=None, mock=False):
        nonlocal critic_call_count
        critic_call_count += 1
        if critic_call_count == 1:
            # 3 critical → critical_failure
            issues = [
                ConsistencyIssue(
                    severity="critical", category="verdict_evidence_gap",
                    location_a="A", statement_a="x",
                    location_b="B", statement_b="y",
                    why_inconsistent="conflict", suggested_fix="fix",
                )
            ] * 3
            _, severity_summary = _compute_verdict(issues)
            return ConsistencyReport(
                issues=issues,
                severity_summary=severity_summary,
                overall_verdict="critical_failure",
            )
        else:
            # 0 issues → pass
            return ConsistencyReport(
                issues=[],
                severity_summary={"critical": 0, "material": 0, "minor": 0},
                overall_verdict="pass",
            )

    orchestrator = V4Orchestrator(store, mock=False)

    with (
        patch("smart_report.v4_orchestrator.synthesize_final_report", side_effect=mock_synthesize),
        patch("smart_report.v4_orchestrator.validate_consistency", side_effect=mock_validate),
    ):
        final = await orchestrator.synthesize("sess-retry")

    # Synthesizer called exactly twice (first pass + retry)
    assert synth_call_count == 2
    # Critic called exactly twice (after first pass + after retry)
    assert critic_call_count == 2

    # Final report has consistency_check in metadata
    assert "consistency_check" in final.metadata
    cc = final.metadata["consistency_check"]
    assert cc["overall_verdict"] == "pass"
    assert cc["issues"] == []


@pytest.mark.asyncio
async def test_validate_consistency_mock_mode():
    """Mock mode returns empty pass report without hitting LLM."""
    report = _pool_triangle_report()
    result = await validate_consistency(report, mock=True)
    assert result.issues == []
    assert result.overall_verdict == "pass"
    assert result.severity_summary == {"critical": 0, "material": 0, "minor": 0}


@pytest.mark.asyncio
async def test_critic_handles_invalid_llm_json():
    """If LLM returns invalid JSON, critic raises after retries."""
    report = _clean_report()

    with patch(
        "smart_report.synthesis_critic.call_json",
        new_callable=AsyncMock,
        return_value=LLMResult(text="not json at all", cost_rub=0.0),
    ):
        with pytest.raises((ValueError, Exception)):
            await validate_consistency(report, mock=False)
