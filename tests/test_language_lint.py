"""Tests for the language lint module (Track 3 — v4.5 Language).

Tests cover:
- Detection of non-whitelisted English tokens
- Whitelist pass-through for financial, brand-name, and tech terms
- Severity classification (error vs warn)
- Edge cases: URLs, code blocks, hybrid tokens
- Regression fixture: baseline warning count on the cached v4 night report
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from smart_report.i18n.language_lint import lint_output_language

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKTREE_ROOT = Path(__file__).parent.parent
CACHE_FINAL_PATH = (
    Path(__file__).parents[4]  # up from worktree to smart-report-mvp-v3
    / "runs"
    / "night_upgrade"
    / "cache_final.json"
)


def _tokens(warnings):
    return {w.token for w in warnings}


# ---------------------------------------------------------------------------
# Core detection tests
# ---------------------------------------------------------------------------


def test_lint_catches_outdoor_stek():
    """Hybrid tokens like 'Outdoor-стек' should be caught — Latin part is flagged."""
    warnings = lint_output_language("Outdoor-стек и Arrival-стек показывают 22%")
    assert len(warnings) == 2, f"Expected 2 warnings, got {len(warnings)}: {[w.token for w in warnings]}"
    tokens = _tokens(warnings)
    assert "Outdoor" in tokens
    assert "Arrival" in tokens


def test_lint_allows_financial():
    """CAPEX, NPV, ROI — all whitelisted; no warnings expected."""
    warnings = lint_output_language("CAPEX 380 млн руб., NPV +120 млн при ROI 18%")
    assert warnings == [], f"Unexpected warnings: {[w.token for w in warnings]}"


def test_lint_allows_brand_names():
    """Multi-word brand names Knight Frank and JLL should be whitelisted."""
    warnings = lint_output_language(
        "Согласно отчёту Knight Frank и JLL премия составляет 15%"
    )
    assert warnings == [], f"Unexpected warnings: {[w.token for w in warnings]}"


def test_lint_flags_mandatory_as_error():
    """ALL-CAPS non-whitelisted token longer than 3 chars → severity 'error'."""
    warnings = lint_output_language("MANDATORY для премиум-класса")
    assert len(warnings) == 1, f"Expected 1 warning, got {len(warnings)}: {[w.token for w in warnings]}"
    assert warnings[0].severity == "error"
    assert warnings[0].token == "MANDATORY"


def test_lint_skips_urls():
    """Tokens inside URLs must not trigger warnings."""
    warnings = lint_output_language(
        "Смотри https://knightfrank.com/research для подробностей"
    )
    assert warnings == [], f"Unexpected warnings: {[w.token for w in warnings]}"


def test_lint_skips_code_blocks():
    """Tokens inside fenced code blocks must not trigger warnings."""
    warnings = lint_output_language("```python\nMANDATORY = True\n```\nтекст после")
    assert warnings == [], f"Unexpected warnings: {[w.token for w in warnings]}"


def test_lint_hybrid_tokens():
    """'бизнес-класс' is whitelisted; 'Outdoor-стек' is not.
    Cyrillic token 'бизнес' alone should not appear in warnings."""
    warnings = lint_output_language("бизнес-класс имеет Outdoor-стек")
    tokens = _tokens(warnings)
    assert "Outdoor" in tokens, "Outdoor should be flagged"
    assert "бизнес" not in tokens, "Cyrillic 'бизнес' must not appear in warnings"


def test_lint_allows_esg_certifications():
    """Certification terms LEED, BREEAM, WELL, ESG must be whitelisted."""
    warnings = lint_output_language(
        "Проект получил сертификат LEED Gold и соответствует BREEAM Excellent. "
        "ESG-рейтинг высокий."
    )
    tokens = _tokens(warnings)
    assert "LEED" not in tokens
    assert "BREEAM" not in tokens
    assert "ESG" not in tokens


def test_lint_flags_wine_room():
    """'wine room' tokens — 'wine' and 'room' are not whitelisted."""
    warnings = lint_output_language("в жилом комплексе предусмотрена wine room")
    tokens = _tokens(warnings)
    assert "wine" in tokens or "room" in tokens, (
        f"Expected 'wine' or 'room' to be flagged, got: {tokens}"
    )


def test_lint_flags_ranking():
    """'ranking' — not in whitelist — should produce a warning."""
    warnings = lint_output_language("ranking amenities по важности для покупателей")
    assert any(w.token == "ranking" for w in warnings), (
        f"Expected 'ranking' warning, got: {[w.token for w in warnings]}"
    )


def test_lint_allows_tech_abbreviations():
    """API, SaaS, CRM, BIM — all whitelisted tech abbreviations."""
    warnings = lint_output_language(
        "Система интеграции через API, поддержка CRM и BIM для управления проектом."
    )
    tokens = _tokens(warnings)
    assert "API" not in tokens
    assert "CRM" not in tokens
    assert "BIM" not in tokens


def test_lint_context_window_populated():
    """LanguageWarning.location_context must be a non-empty string."""
    warnings = lint_output_language("текст MANDATORY слово")
    assert warnings, "Expected at least one warning"
    assert len(warnings[0].location_context) > 0


def test_lint_inline_code_skipped():
    """Tokens in inline backtick code should be skipped."""
    warnings = lint_output_language(
        "используй `MANDATORY` только в коде, в тексте — запрещено"
    )
    # 'MANDATORY' inside backticks must not be flagged
    tokens = _tokens(warnings)
    assert "MANDATORY" not in tokens, "Inline code tokens must be skipped"


def test_lint_severity_warn_for_short_mixed_case():
    """Short or mixed-case non-whitelisted tokens get 'warn', not 'error'."""
    warnings = lint_output_language("outdoor зона отдыха")
    assert warnings, "Expected warning for 'outdoor'"
    # 'outdoor' is lowercase, so should be 'warn' not 'error'
    for w in warnings:
        if w.token == "outdoor":
            assert w.severity == "warn"


# ---------------------------------------------------------------------------
# Regression fixture: baseline warning count on the cached v4 night report
# ---------------------------------------------------------------------------


def _extract_text_from_cache_final(data: dict) -> str:
    """Extract prose text fields from the cached FinalReport JSON."""
    parts: list[str] = []

    es = data.get("executive_summary", {})
    if es.get("main_answer"):
        parts.append(es["main_answer"])
    parts.extend(es.get("top_findings", []))
    if es.get("confidence_note"):
        parts.append(es["confidence_note"])
    if es.get("what_meta_adds"):
        parts.append(es["what_meta_adds"])

    for field in ("main_synthesis", "consensus_section", "conflicts_section", "gaps_filled_section"):
        if data.get(field):
            parts.append(data[field])

    for item in data.get("qa_section", []):
        if item.get("question"):
            parts.append(item["question"])
        if item.get("answer"):
            parts.append(item["answer"])

    for item in data.get("ranking", []):
        if item.get("label"):
            parts.append(item["label"])
        if item.get("rationale"):
            parts.append(item["rationale"])

    for table in data.get("tables", []):
        if table.get("title"):
            parts.append(table["title"])
        parts.extend(table.get("columns", []))
        for row in table.get("rows", []):
            parts.extend(str(c) for c in row)

    for callout in data.get("callouts", []):
        if callout.get("title"):
            parts.append(callout["title"])
        if callout.get("body"):
            parts.append(callout["body"])

    for knh in data.get("key_numbers_highlight", []):
        if knh.get("label"):
            parts.append(knh["label"])

    return "\n".join(p for p in parts if p)


@pytest.mark.skipif(
    not CACHE_FINAL_PATH.exists(),
    reason=f"cache_final.json not found at {CACHE_FINAL_PATH}",
)
def test_lint_on_cached_final_baseline():
    """Regression fixture: v4 night report should have >20 language warnings.

    This documents the problem that Track 3 is fixing.  Once a post-fix
    Synthesizer run is done the target is <5, but this test deliberately
    asserts the *old* high count to confirm the detector works on real data.
    """
    data = json.loads(CACHE_FINAL_PATH.read_text(encoding="utf-8"))
    text = _extract_text_from_cache_final(data)
    assert text, "cache_final.json yielded no text — check _extract_text_from_cache_final"
    warnings = lint_output_language(text)
    warning_count = len(warnings)
    tokens_found = [w.token for w in warnings]
    # The known bad tokens from the spec: ranking, MANDATORY, Outdoor, Arrival,
    # Fitness, Tech, wine, room, dedicated, cinema, service, charge, ...
    assert warning_count > 20, (
        f"Expected >20 language warnings on v4 night cache_final (baseline regression), "
        f"got {warning_count}. Tokens: {tokens_found}"
    )
