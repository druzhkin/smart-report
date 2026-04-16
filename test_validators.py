"""Unit tests for validators.py — run with: python -m pytest test_validators.py -v"""
from __future__ import annotations

from models import Block, Finding
from validators import (
    Number,
    extract_numbers,
    fuzzy_match,
    stamp_block,
    validate_block_numbers,
)


def _f(claim: str, numeric_values: list[str], quote: str = "") -> Finding:
    return Finding(
        claim=claim,
        source="https://example.com",
        source_type="secondary",
        has_numbers=bool(numeric_values),
        numeric_values=numeric_values,
        verbatim_quote=quote or None,
    )


def _block(summary: str, findings: list[Finding]) -> Block:
    return Block(
        cell="Test / Layer",
        summary=summary,
        findings=findings,
        gaps=[],
        key_entities=[],
        assumptions=[],
    )


# ─── extract_numbers ────────────────────────────────────────────────────────


def test_extract_percent():
    nums = extract_numbers("Рост составил 42% год к году")
    assert any(n.unit == "percent" and n.value == 42.0 for n in nums)


def test_extract_currency_prefix_suffix():
    nums = extract_numbers("Рынок $2.4B. Инвестиции 500 млн ₽")
    units = {(n.unit, int(n.value)) for n in nums}
    assert ("currency_usd", 2_400_000_000) in units
    assert ("currency_rub", 500_000_000) in units


def test_extract_n_equals():
    nums = extract_numbers("Выборка n=1842 респондентов")
    assert any(n.unit == "count_n" and n.value == 1842 for n in nums)


def test_extract_year_not_mixed_with_plain():
    nums = extract_numbers("В 2023 году выручка 150 млн")
    years = [n for n in nums if n.unit == "year"]
    counts = [n for n in nums if n.unit == "count"]
    assert years and years[0].value == 2023
    assert counts and counts[0].value == 150_000_000


def test_extract_multiple():
    nums = extract_numbers("Рост в 3.2x за квартал")
    assert any(n.unit == "multiple" and abs(n.value - 3.2) < 1e-6 for n in nums)


# ─── fuzzy_match ────────────────────────────────────────────────────────────


def test_fuzzy_percent_matches_ratio():
    """42% должен матчить 0.42 (одно и то же значение в разных юнитах)."""
    a = Number(42.0, "percent", "42%")
    b = Number(0.42, "ratio", "0.42")
    assert fuzzy_match(a, b)


def test_fuzzy_percent_pp_boundary():
    """42% vs 46% — 4pp разницы, не матчится (tolerance 2.0pp)."""
    a = Number(42.0, "percent", "42%")
    b = Number(46.0, "percent", "46%")
    assert not fuzzy_match(a, b)


def test_fuzzy_percent_within_pp_tolerance():
    """42% vs 43.5% — 1.5pp, матчится."""
    a = Number(42.0, "percent", "42%")
    b = Number(43.5, "percent", "43.5%")
    assert fuzzy_match(a, b)


def test_fuzzy_currency_scale_equivalence():
    """$1.1B ≈ $1,127M (разница <5%, матч)."""
    a = Number(1.1e9, "currency_usd", "$1.1B")
    b = Number(1.127e9, "currency_usd", "$1,127M")
    assert fuzzy_match(a, b)


def test_fuzzy_currency_beyond_tolerance():
    """$1.1B vs $1.3B — 18% разницы, не матчится."""
    a = Number(1.1e9, "currency_usd", "$1.1B")
    b = Number(1.3e9, "currency_usd", "$1.3B")
    assert not fuzzy_match(a, b)


def test_fuzzy_year_exact_only():
    a = Number(2023, "year", "2023")
    b = Number(2024, "year", "2024")
    assert not fuzzy_match(a, b)
    c = Number(2023, "year", "2023")
    assert fuzzy_match(a, c)


def test_fuzzy_currency_cross_family_no_match():
    """USD и EUR — разные валюты, не матчатся даже при равных value."""
    a = Number(1000.0, "currency_usd", "$1000")
    b = Number(1000.0, "currency_eur", "€1000")
    assert not fuzzy_match(a, b)


def test_fuzzy_percent_currency_never():
    a = Number(42.0, "percent", "42%")
    b = Number(42.0, "currency_usd", "$42")
    assert not fuzzy_match(a, b)


# ─── validate_block_numbers ─────────────────────────────────────────────────


def test_verified_summary_passes():
    """Все числа summary находятся в findings — unverified пуст."""
    findings = [
        _f("Рынок $2.4B", ["$2.4B"], quote="market grew to $2.4B"),
        _f("Доля 42%", ["42%"], quote="share reached 42%"),
    ]
    block = _block("Рынок достиг $2.4B, доля 42%.", findings)
    assert validate_block_numbers(block) == []


def test_unverified_synthesized_number():
    """Число в summary, которого нет ни в одном finding → unverified."""
    findings = [
        _f("Выручка Q1 $500M", ["$500M"]),
        _f("Выручка Q2 $600M", ["$600M"]),
    ]
    block = _block("Совокупная выручка $1.2B за полугодие.", findings)
    unv = validate_block_numbers(block)
    assert any("1.2" in x for x in unv)


def test_unverified_rounding_still_matches():
    """$1.1B в summary должен матчиться с $1,127M в finding (fuzzy 5%)."""
    findings = [_f("Выручка $1,127M", ["$1,127M"], quote="revenue of $1,127M")]
    block = _block("Выручка около $1.1B за год.", findings)
    assert validate_block_numbers(block) == []


def test_unverified_percent_unit_fuzz():
    """42% в summary ↔ 0.42 в finding — разные юниты, но матч."""
    findings = [_f("Доля 0.42", ["0.42"], quote="the fraction was 0.42")]
    block = _block("Доля рынка — 42%.", findings)
    assert validate_block_numbers(block) == []


def test_unverified_pp_drift_reported():
    """Summary говорит 46%, finding — 42%; 4pp разницы → unverified."""
    findings = [_f("Доля 42%", ["42%"], quote="share was 42%")]
    block = _block("Доля рынка составила 46%.", findings)
    unv = validate_block_numbers(block)
    assert any("46" in x for x in unv)


def test_year_not_reported_as_unverified():
    """Год 2023 в summary — не сигнальный юнит, не попадает в unverified."""
    findings = [_f("Рынок $2B", ["$2B"])]
    block = _block("В 2023 рынок достиг $2B.", findings)
    assert validate_block_numbers(block) == []


def test_plain_noise_not_reported():
    """Голое число 5 (перечисление) — не сигнальный юнит."""
    findings = [_f("Доля 42%", ["42%"])]
    block = _block("Выделено 5 тезисов. Доля 42%.", findings)
    assert validate_block_numbers(block) == []


def test_duplicate_unverified_deduped():
    findings = [_f("Доля 42%", ["42%"])]
    block = _block("Выручка $900M. Выручка $900M повторно.", findings)
    unv = validate_block_numbers(block)
    assert len(unv) == 1


# ─── stamp_block ────────────────────────────────────────────────────────────


def test_stamp_block_sets_field():
    findings = [_f("Рынок $2.4B", ["$2.4B"])]
    block = _block("Рынок достиг $2.4B; агрегированная оценка $5B.", findings)
    stamped = stamp_block(block)
    assert stamped.unverified_numerics
    assert any("5" in x for x in stamped.unverified_numerics)


def test_stamp_block_clean_summary():
    findings = [_f("Рынок $2.4B", ["$2.4B"], quote="market reached $2.4B")]
    block = _block("Рынок достиг $2.4B.", findings)
    stamped = stamp_block(block)
    assert stamped.unverified_numerics == []
