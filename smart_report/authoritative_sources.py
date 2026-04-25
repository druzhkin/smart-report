"""Source-adequacy heuristic (v4.5 Phase 1 Step 1.2).

Detects whether a synthesized report's source pool contains at least
*min_authoritative* domains from a curated list of Russian real-estate
authoritative publishers (state stat agencies, regulators, industry
data providers, top international consultancies operating in the RU
market).

Below the threshold, the pipeline marks the report with::

    metadata["evidence_quality"] = "LOW_EVIDENCE_QUALITY"
    metadata["evidence_warning"] = <human-readable Russian text>

…and the warning is prefixed onto ``executive_summary.confidence_note``
so it surfaces in every downstream renderer (DOCX, HTML, MD, JSON)
without each renderer needing to learn about the new field.

This is the "I don't know" pathway from the K-Dense Roadmap: when
secondary blogs and news re-tellings dominate the inputs, the report
must say so on its face rather than presenting findings with the same
visual weight as a Rosstat-grounded answer.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Source, SourceRef


# ---------------------------------------------------------------------------
# Authoritative domain registry
# ---------------------------------------------------------------------------
# Curated for Russian real-estate / development analytics. Membership criterion:
#   - State statistics agency, central regulator, or registry: STRONG by class
#   - International "Big-N" consultancy with active RU coverage: MODERATE-class
#     but counts as authoritative for adequacy threshold (these are the
#     industry primary sources in the RU RE segment)
#
# Cyrillic-IDN aliases are listed alongside the Latin form because some
# sources surface URLs with the Cyrillic domain (дом.рф) and others with
# the Punycode/transliterated form (dom.rf).

AUTHORITATIVE_RU_RE_DOMAINS: frozenset[str] = frozenset(
    {
        # State statistics & regulators
        "rosstat.gov.ru",
        "gks.ru",                # Rosstat legacy hostname, still resolves
        "minstroyrf.gov.ru",
        "minfin.gov.ru",
        "cbr.ru",                # Central Bank of Russia
        "nalog.gov.ru",
        "egrul.nalog.ru",
        "egrn.rosreestr.ru",
        "rosreestr.gov.ru",
        # State-affiliated housing data providers
        "дом.рф",
        "dom.rf",
        "наш.дом.рф",
        "наш.дом.рф",            # duplicate intentional — case folding upstream
        "spv.dom.rf",
        "erzrf.ru",              # ЕРЗ — primary new-build database
        # Industry data providers operating in RU
        "jllrussia.com",
        "jll.com",
        "cbre.ru",
        "cbre.com",
        "knightfrank.ru",
        "knightfrank.com",
        "colliers.com",
        "cushmanwakefield.com",
        "nfgroup.ru",            # NF Group (former Knight Frank Russia)
        "nikoliers.com",         # rebranded Colliers Russia
        "metrium.ru",
        "bnmap.pro",
        "dataflat.ru",
        "irn.ru",
        # International consultancies (occasional RU coverage)
        "mckinsey.com",
        "bcg.com",
        "pwc.com",
        "kpmg.com",
        "deloitte.com",
        # Federal law / standards portals
        "publication.pravo.gov.ru",
        "pravo.gov.ru",
    }
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_authoritative_url(url: str) -> bool:
    """Return True if *url* belongs to an authoritative domain (case-insensitive).

    Empty / opaque (``opaque:...``) / non-http URLs return False. Subdomains
    are matched: ``https://stat.minstroyrf.gov.ru/foo`` counts as a hit on
    ``minstroyrf.gov.ru``.
    """
    if not url:
        return False
    url_lower = url.lower()
    if url_lower.startswith("opaque:"):
        return False
    for domain in AUTHORITATIVE_RU_RE_DOMAINS:
        # Substring match on lowered URL handles subdomains and path noise.
        # We deliberately do NOT parse with urllib here — Cyrillic-IDN dom.рф
        # round-trips inconsistently across stdlib versions, and a substring
        # check is robust to that. False positives from query strings
        # containing a domain name are tolerated (extreme edge case).
        if domain in url_lower:
            return True
    return False


def count_authoritative_sources(sources: Iterable[object]) -> int:
    """Count items whose ``.url`` attribute (or ``["url"]`` key) is authoritative.

    Accepts a heterogeneous iterable: ``Source``, ``SourceRef``, or raw dicts
    with a ``url`` key. Items missing a URL contribute 0.
    """
    count = 0
    for item in sources:
        url = _extract_url(item)
        if url and is_authoritative_url(url):
            count += 1
    return count


def assess_evidence_quality(
    sources: Iterable[object], *, min_authoritative: int = 2
) -> tuple[str, str]:
    """Classify the source pool and return ``(quality_label, warning_text)``.

    ``quality_label`` is ``"LOW_EVIDENCE_QUALITY"`` when fewer than
    *min_authoritative* authoritative sources were found, otherwise
    ``"OK"``. ``warning_text`` is a Russian-language human-readable
    sentence ready for inline display, or empty string when quality is OK.
    """
    found = count_authoritative_sources(sources)
    if found >= min_authoritative:
        return "OK", ""

    # Visible warning is intentionally pure Cyrillic — every Latin token
    # would be flagged by the language linter and could push a borderline
    # report past the >20-warning retry threshold, doubling Synthesizer
    # cost on every low-quality run. The machine-readable sentinel
    # "LOW_EVIDENCE_QUALITY" stays in metadata["evidence_quality"] only.
    warning = (
        f"⚠ Низкое качество источников: найдено {found} авторитетных"
        f" источника из требуемого минимума {min_authoritative}"
        " (Росстат, Минстрой, ДОМ.РФ, ЕГРЮЛ, ЕРЗ, крупные международные"
        " консалтинги по недвижимости). Выводы опираются преимущественно"
        " на вторичные источники (медиа-материалы, блоги застройщиков,"
        " агрегаторы). Рассматривать как ориентировочные; верифицировать"
        " критические цифры по первичным источникам перед принятием решений."
    )
    return "LOW_EVIDENCE_QUALITY", warning


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_url(item: object) -> str:
    """Return the URL from a Source / SourceRef / dict / anything else."""
    url = getattr(item, "url", None)
    if isinstance(url, str):
        return url
    if isinstance(item, dict):
        v = item.get("url")
        if isinstance(v, str):
            return v
    return ""
