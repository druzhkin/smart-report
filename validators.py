"""Post-hoc numeric validation for analyst summaries.

Extracts numbers-with-units from the summary text and matches them against
every finding's numeric_values / verbatim_quote using unit-aware fuzzy matching.
Returns the raw strings of summary numbers that cannot be traced back to any
finding — the UI marks these as "synthesized" (∑) so the reader knows the
aggregate may not appear verbatim in sources.

Tolerances:
- percent / ratio: absolute, 2.0 percentage points (42% ↔ 46% does NOT match)
- year:            exact match
- else (currency, count, multiple, n=): relative, 5%

Unit compatibility:
- percent ↔ ratio (42% matches 0.42)
- plain ↔ count / multiple / count_n (loose)
- never across currency boundaries, never percent ↔ currency
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from models import Block

logger = logging.getLogger(__name__)


Unit = str  # percent | ratio | currency_* | count | year | multiple | count_n | plain


@dataclass(frozen=True)
class Number:
    value: float
    unit: Unit
    raw: str


_SCALE: dict[str, float] = {
    "b": 1e9, "bn": 1e9, "млрд": 1e9,
    "m": 1e6, "mn": 1e6, "млн": 1e6,
    "k": 1e3, "тыс": 1e3,
    "t": 1e12, "trn": 1e12, "трлн": 1e12,
}

_CURRENCY: dict[str, Unit] = {
    "$": "currency_usd", "€": "currency_eur", "₽": "currency_rub",
    "£": "currency_gbp", "¥": "currency_jpy",
}

# Digit group with optional thousands separators and decimal part.
# First alternative requires at least one separator group (handles "1,500,000"),
# second catches bare integers and decimals ("1842", "2.4"). Order matters —
# without the "+", "1842" would be mis-consumed as "184".
_NUM = r"\d{1,3}(?:[ ,.]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"

_RE_PCT = re.compile(
    rf"({_NUM})\s*(?:%|процент(?:ов|а)?|процентных\s+пунктов|\bpp\b)",
    re.IGNORECASE | re.UNICODE,
)
_RE_CUR_PREFIX = re.compile(
    rf"([$€£¥₽])\s*({_NUM})\s*(B|M|K|T|bn|mn|trn|млрд|млн|тыс|трлн)?",
    re.IGNORECASE | re.UNICODE,
)
_RE_CUR_SUFFIX = re.compile(
    rf"({_NUM})\s*(B|M|K|T|bn|mn|trn|млрд|млн|тыс|трлн)?\s*([$€£¥₽])",
    re.IGNORECASE | re.UNICODE,
)
_RE_SCALE = re.compile(
    rf"({_NUM})\s*(B|M|K|T|bn|mn|trn|млрд|млн|тыс|трлн)\b",
    re.IGNORECASE | re.UNICODE,
)
_RE_MULT = re.compile(
    rf"({_NUM})\s*(?:x|×|fold|кратн[а-я]*|раз[а-я]*)\b",
    re.IGNORECASE | re.UNICODE,
)
_RE_N = re.compile(rf"[nN]\s*=\s*({_NUM})")
_RE_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_RE_PLAIN = re.compile(rf"(?<![\w.])({_NUM})(?![\w.])")


def _to_float(raw: str) -> float | None:
    s = raw.strip().replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit():
            s = parts[0] + parts[1]
        else:
            s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def extract_numbers(text: str) -> list[Number]:
    """Scan text and return all recognisable numbers with units."""
    if not text:
        return []

    out: list[Number] = []
    consumed: list[tuple[int, int]] = []

    def _overlaps(s: int, e: int) -> bool:
        return any(not (e <= cs or s >= ce) for cs, ce in consumed)

    def _add(m: re.Match, unit: Unit, value: float) -> None:
        s, e = m.span()
        if _overlaps(s, e):
            return
        consumed.append((s, e))
        out.append(Number(value=value, unit=unit, raw=m.group(0).strip()))

    for m in _RE_PCT.finditer(text):
        v = _to_float(m.group(1))
        if v is not None:
            _add(m, "percent", v)

    for m in _RE_CUR_PREFIX.finditer(text):
        v = _to_float(m.group(2))
        if v is None:
            continue
        scale = _SCALE.get((m.group(3) or "").lower(), 1.0)
        _add(m, _CURRENCY.get(m.group(1), "currency_other"), v * scale)

    for m in _RE_CUR_SUFFIX.finditer(text):
        v = _to_float(m.group(1))
        if v is None:
            continue
        scale = _SCALE.get((m.group(2) or "").lower(), 1.0)
        _add(m, _CURRENCY.get(m.group(3), "currency_other"), v * scale)

    for m in _RE_N.finditer(text):
        v = _to_float(m.group(1))
        if v is not None:
            _add(m, "count_n", v)

    for m in _RE_MULT.finditer(text):
        v = _to_float(m.group(1))
        if v is not None:
            _add(m, "multiple", v)

    for m in _RE_SCALE.finditer(text):
        v = _to_float(m.group(1))
        if v is None:
            continue
        scale = _SCALE[m.group(2).lower()]
        _add(m, "count", v * scale)

    for m in _RE_YEAR.finditer(text):
        v = _to_float(m.group(1))
        if v is not None:
            _add(m, "year", v)

    for m in _RE_PLAIN.finditer(text):
        v = _to_float(m.group(1))
        if v is None:
            continue
        if 0 < abs(v) < 1:
            _add(m, "ratio", v)
        elif 1 <= v < 1e12:
            _add(m, "plain", v)

    return out


_PCT_LIKE = {"percent", "ratio"}
_PLAIN_COMPAT = {"plain", "count", "year", "multiple", "count_n"}


def _compatible(u1: Unit, u2: Unit) -> bool:
    if u1 == u2:
        return True
    if u1 in _PCT_LIKE and u2 in _PCT_LIKE:
        return True
    if "plain" in (u1, u2):
        other = u2 if u1 == "plain" else u1
        return other in _PLAIN_COMPAT
    return False


def _pct_value(n: Number) -> float:
    return n.value if n.unit == "percent" else n.value * 100.0


def fuzzy_match(
    a: Number,
    b: Number,
    tolerance_abs_pp: float = 2.0,
    tolerance_rel: float = 0.05,
) -> bool:
    if not _compatible(a.unit, b.unit):
        return False
    if a.unit == "year" or b.unit == "year":
        return a.value == b.value
    if a.unit in _PCT_LIKE or b.unit in _PCT_LIKE:
        return abs(_pct_value(a) - _pct_value(b)) <= tolerance_abs_pp
    denom = max(abs(a.value), abs(b.value))
    return denom == 0 or abs(a.value - b.value) / denom <= tolerance_rel


# Only "signal" units get reported as unverified — years, ratios and bare plains
# are too noisy (list enumeration, prose stats) and would flood the UI.
_SIGNAL_UNITS = {
    "percent", "count", "count_n", "multiple",
    "currency_usd", "currency_eur", "currency_rub",
    "currency_gbp", "currency_jpy", "currency_other",
}


def validate_block_numbers(block: Block) -> list[str]:
    """Return raw strings of summary numbers with no fuzzy match in findings."""
    summary_nums = extract_numbers(block.summary)
    if not summary_nums:
        return []

    known: list[Number] = []
    for f in block.findings:
        for nv in f.numeric_values:
            known.extend(extract_numbers(nv))
        if f.verbatim_quote:
            known.extend(extract_numbers(f.verbatim_quote))

    seen: set[tuple[str, float]] = set()
    unverified: list[str] = []
    for sn in summary_nums:
        if sn.unit not in _SIGNAL_UNITS:
            continue
        if any(fuzzy_match(sn, kn) for kn in known):
            continue
        key = (sn.unit, round(sn.value, 4))
        if key in seen:
            continue
        seen.add(key)
        unverified.append(sn.raw)
    return unverified


def stamp_block(block: Block) -> Block:
    """Attach unverified_numerics to block and log any hits for audit."""
    unv = validate_block_numbers(block)
    block.unverified_numerics = unv
    if unv:
        total = sum(
            1 for n in extract_numbers(block.summary) if n.unit in _SIGNAL_UNITS
        )
        ratio = len(unv) / max(1, total)
        logger.info(
            "unverified_numerics cell=%r count=%d of %d (%.0f%%) nums=%s",
            block.cell, len(unv), total, ratio * 100, unv,
        )
        if ratio > 0.5:
            logger.warning(
                "unverified_numerics HIGH cell=%r ratio=%.0f%% — possible composition drift",
                block.cell, ratio * 100,
            )
    return block
