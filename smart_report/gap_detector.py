"""Per-sub-question evidence-adequacy detector (v4.5 Phase 2 Step 2.3).

After the Analyzer produces an AnalysisOutput, this module:

  1. Walks every SubQuestion produced by the Step 2.2 planner (or
     domain template) and matches retrieved sources to it.
  2. Counts authoritative-domain hits using the Step 1.2 RU RE
     registry (smart_report.authoritative_sources).
  3. Mutates the SubQuestion in place with bibliography_refs,
     authoritative_source_count, and evidence_status.
  4. Emits an EvidenceGap for every SubQuestion below the
     authoritative-source threshold (default 2).

The resulting list is sorted critical-first so downstream renderers
can foreground the most damaging gaps without re-sorting.

Source-to-sub-question matching is deliberately a small, transparent
heuristic (token overlap on the sub_question text + suggested_sources
hints, against source URL + title). This is the rough proxy that lets
us deliver Step 2.3 today; semantic matching with embeddings is a
Phase 3 follow-up if the heuristic proves under-precise on live runs.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .authoritative_sources import (
    is_authoritative_url,
    is_authoritative_url_for_domain,
)
from .domain_detector import QueryDomain

if TYPE_CHECKING:
    from .models import AnalysisOutput, EvidenceGap, SubQuestion


_DEFAULT_AUTHORITATIVE_THRESHOLD = 2

# Min number of token overlaps for a source to be considered as covering a
# sub_question. Below 2 the match is too noisy (single domain word like
# "ru" or "com" matches everything); 2 catches a domain word + a topic
# word, which is the minimum signal worth trusting from a 2-line URL.
_MIN_TOKEN_OVERLAP = 2


# Stopwords drop the common procedural words that would otherwise drive
# the overlap count regardless of topic. Mixed RU/EN to match both kinds
# of sub_questions (Step 2.1 RU RE template stays Russian; Step 2.2 LLM
# planner mirrors the input language).
_STOPWORDS: frozenset[str] = frozenset({
    # Russian
    "что", "как", "и", "в", "на", "по", "из", "от", "с", "к", "у", "о",
    "при", "за", "или", "но", "то", "это", "этот", "эта", "эти", "тот",
    "та", "те", "для", "ли", "не", "ни", "был", "была", "было", "были",
    "есть", "будет", "будут", "может", "могут", "должен", "должна",
    "также", "ещё", "уже", "только", "один", "одна", "одно", "два",
    "две", "три",
    "какие", "какой", "какая", "какое", "сколько", "почему", "когда",
    "где", "зачем", "тренды", "тренд", "тренды", "влияет", "влияют",
    "анализ", "сравни", "сравнение", "оцени", "оценка", "прогноз",
    "риск", "риски", "перспективы", "сценарий", "выбор", "стратег",
    "лидер", "успех",
    # English
    "the", "a", "an", "of", "for", "in", "on", "to", "and", "or", "is",
    "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "should", "could", "may",
    "might", "this", "that", "these", "those", "with", "from", "by",
    "as", "at", "into", "out", "up", "down", "over", "under",
    "what", "which", "who", "whom", "whose", "where", "when", "why",
    "how", "compare", "trend", "trends", "impact", "forecast", "risk",
    "scenario", "strategy", "analysis", "evaluate", "evaluation",
    "drivers", "outlook",
    # Generic web noise
    "https", "http", "www", "html", "htm", "pdf", "ru", "com", "org",
    "gov", "net", "page", "ref", "id",
})


# Hyphens deliberately split tokens. URL slugs use hyphens as separators
# ("biznes-zhilyo-developer-2025" → 4 tokens), and Russian compounds like
# "бизнес-сегмент" still survive as two meaningful tokens after the
# split. Keeping hyphens inside would let any single hyphenated URL slug
# become one over-long opaque token that never matches a sub_question.
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я][A-Za-zА-Яа-я0-9_]{2,}")


def _tokenize(text: str) -> set[str]:
    """Lowercase tokens of length ≥3 with stopwords stripped."""
    if not text:
        return set()
    return {t.lower() for t in _TOKEN_RE.findall(text)} - _STOPWORDS


def _collect_analysis_sources(analysis: "AnalysisOutput") -> list[dict]:
    """Flatten every source-bearing field of *analysis* into url/title pairs.

    Walks numeric facts and qualitative facts; per_source_summary is
    not used here because its ``source`` field carries a tool-name
    (e.g. "perplexity_dr_1"), not a URL.
    """
    seen: dict[str, str] = {}
    for fact in (*analysis.all_numeric_facts, *analysis.all_qualitative_facts):
        for src in fact.sources:
            url = (src.url or "").strip()
            if not url or url.startswith("opaque:"):
                continue
            # Keep first-seen title (URLs may show up many times)
            seen.setdefault(url, src.title or "")
    return [{"url": u, "title": t} for u, t in seen.items()]


def _tokens_match(a: str, b: str) -> bool:
    """Loose Russian-morphology-tolerant comparison.

    Russian word forms differ in case ("Москва" / "Москве" / "Москвы"),
    number ("ипотека" / "ипотеки"), and gender — a strict equality
    check loses every case-shift between sub_question text and source
    title. Compromise: tokens match if their common prefix is ≥4 chars
    (catches "ипотек-а" vs "ипотек-и") OR ≥3 chars when one token is a
    morphology shift of the other (e.g. "цен" / "цены").

    The 3-char carve-out keeps false-positive risk low because most
    truly-short Russian function words are in _STOPWORDS already, so
    they never reach this matcher.
    """
    if a == b:
        return True
    if not a or not b:
        return False
    common = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            common += 1
        else:
            break
    return common >= 4 or (common >= 3 and abs(len(a) - len(b)) <= 2)


def _count_token_overlap(sq_tokens: set[str], src_tokens: set[str]) -> int:
    """Count distinct sq_tokens that have at least one matching src_token."""
    if not sq_tokens or not src_tokens:
        return 0
    matched_sq = 0
    for s_t in sq_tokens:
        if any(_tokens_match(s_t, t) for t in src_tokens):
            matched_sq += 1
    return matched_sq


def _match_sources_to_sub_question(
    sq: "SubQuestion", sources: Iterable[dict]
) -> list[str]:
    """Return URLs from *sources* that share ≥2 distinct sub_question
    tokens with the source URL + title (with morphology tolerance).

    Deliberately rough: a precision/recall trade-off chosen for live
    transparency, not absolute accuracy. The downstream gap detector
    is robust to over-matching (only authoritative-count drives
    severity), and under-matching surfaces as a "critical" gap that
    the follow-up prompter can still address.
    """
    sq_tokens = _tokenize(sq.text)
    sq_tokens |= _tokenize(" ".join(sq.suggested_sources))
    if not sq_tokens:
        return []
    matched: set[str] = set()
    for src in sources:
        src_tokens = _tokenize(src["url"] + " " + src["title"])
        if _count_token_overlap(sq_tokens, src_tokens) >= _MIN_TOKEN_OVERLAP:
            matched.add(src["url"])
    return sorted(matched)


def _classify_evidence_status(
    matched_count: int, authoritative_count: int, threshold: int
) -> str:
    if authoritative_count >= threshold:
        return "answered"
    if matched_count > 0:
        return "partial"
    return "unanswered"


# Domain-specific reason text for the "moderate" branch — names the
# right registry to the analyst rather than always citing RU RE.
_MODERATE_REASON_BY_DOMAIN: dict[QueryDomain, str] = {
    QueryDomain.RU_REAL_ESTATE: (
        "Росстат, Минстрой, ДОМ.РФ, ЕГРЮЛ, ЕРЗ, крупные международные "
        "консалтинги по недвижимости"
    ),
    QueryDomain.RU_AUTOMOTIVE: (
        "Минпромторг, Автостат, АЕБ, ASM Holding и профильная "
        "автомобильная пресса (За рулём, Auto Review)"
    ),
    QueryDomain.RU_TECH_SAAS: (
        "TAdviser, IKS Media, CNews, RusBase и профильные RU технологические "
        "аналитические агентства"
    ),
    QueryDomain.EU_REGULATORY: (
        "EU institutions (europa.eu, ec.europa.eu, eur-lex), EU regulators "
        "(EEA, EBA, ESMA), and trusted EU policy trackers"
    ),
    QueryDomain.GLOBAL_TECH: (
        "arXiv, ACM, IEEE, GitHub, OpenReview и крупные международные "
        "tech-издания"
    ),
    QueryDomain.GENERIC: (
        "первичные регуляторы, отраслевая статистика и крупные "
        "международные консалтинги"
    ),
}


def _build_gap(
    sq: "SubQuestion",
    *,
    threshold: int,
    query_domain: QueryDomain = QueryDomain.RU_REAL_ESTATE,
) -> "EvidenceGap | None":
    """Return an EvidenceGap for *sq* if below threshold, else None."""
    from .models import EvidenceGap  # local to avoid circular at import time

    if sq.authoritative_source_count >= threshold:
        return None
    registry_label = _MODERATE_REASON_BY_DOMAIN.get(
        query_domain, _MODERATE_REASON_BY_DOMAIN[QueryDomain.GENERIC]
    )
    if not sq.bibliography_refs:
        severity = "critical"
        reason = (
            "Не найдено ни одного источника, покрывающего этот под-вопрос. "
            "Аналитику стоит прогнать целевой DR-запрос по этой теме."
        )
    elif sq.authoritative_source_count == 0:
        severity = "moderate"
        reason = (
            f"Найдено {len(sq.bibliography_refs)} источников, но ни один "
            f"не из авторитетного реестра ({registry_label}). Выводы по "
            f"этому под-вопросу опираются только на вторичные источники."
        )
    else:  # exactly 1 authoritative source
        severity = "minor"
        reason = (
            f"Найден только {sq.authoritative_source_count} авторитетный "
            f"источник из требуемых {threshold}. Подтверждение из второго "
            f"первичного источника усилит надёжность."
        )
    return EvidenceGap(
        sub_question_id=sq.id,
        sub_question_text=sq.text,
        severity=severity,
        reason=reason,
        suggested_search_directions=list(sq.suggested_sources),
    )


_SEVERITY_ORDER = {"critical": 0, "moderate": 1, "minor": 2}


async def detect_gaps(
    sub_questions: list["SubQuestion"],
    analysis: "AnalysisOutput",
    *,
    authoritative_threshold: int = _DEFAULT_AUTHORITATIVE_THRESHOLD,
    query_domain: QueryDomain = QueryDomain.RU_REAL_ESTATE,
) -> list["EvidenceGap"]:
    """Walk *sub_questions* against *analysis* sources and emit gaps.

    Mutates *sub_questions* in place: populates ``bibliography_refs``,
    ``authoritative_source_count``, and ``evidence_status`` on every
    SubQuestion based on the matching pass. This means callers get
    both an EvidenceGap list and an enriched SubQuestion list; storing
    the latter on the V4Session preserves the per-sub-question
    coverage trace for the frontend and any subsequent iteration.

    Returns gaps sorted critical → moderate → minor so renderers can
    foreground the most damaging items without re-sorting.

    Async signature is intentional even though the current
    implementation does no I/O — keeping the door open for the
    embedding-based semantic matcher (Phase 3) to slot in without
    every caller needing to switch sync/async.
    """
    if not sub_questions:
        return []

    sources = _collect_analysis_sources(analysis)
    gaps: list = []

    for sq in sub_questions:
        matched_urls = _match_sources_to_sub_question(sq, sources)
        sq.bibliography_refs = matched_urls
        # Step 3.2: count authoritative sources against the per-domain
        # registry. RU_REAL_ESTATE default keeps backwards compat —
        # callers that haven't been migrated still hit the old set.
        sq.authoritative_source_count = sum(
            1 for url in matched_urls
            if is_authoritative_url_for_domain(url, query_domain)
        )
        sq.evidence_status = _classify_evidence_status(
            matched_count=len(matched_urls),
            authoritative_count=sq.authoritative_source_count,
            threshold=authoritative_threshold,
        )
        gap = _build_gap(
            sq, threshold=authoritative_threshold, query_domain=query_domain
        )
        if gap is not None:
            gaps.append(gap)

    gaps.sort(key=lambda g: _SEVERITY_ORDER[g.severity])
    return gaps


def gap_count_by_severity(gaps: list["EvidenceGap"]) -> dict[str, int]:
    """Tally for FinalReport.metadata. All three keys always present."""
    counts = {"critical": 0, "moderate": 0, "minor": 0}
    for g in gaps:
        counts[g.severity] += 1
    return counts
