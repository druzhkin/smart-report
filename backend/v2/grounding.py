from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from backend.v2.models import ClaimRecord


_NUMERIC_FACT_RE = re.compile(
    r"(?P<prefix>[$€£])?\s*(?P<number>\d{1,4}(?:[.,]\d+)?)\s*(?P<unit>%|percent|usd|eur|rub|руб|ms|millisecond(?:s)?|sec(?:ond)?s?|minute(?:s)?|hour(?:s)?|day(?:s)?|week(?:s)?|month(?:s)?|year(?:s)?|k|m|b|million|billion|tokens?|requests?|queries?|rpm|rps|qps|ctx|stars?|forks?|contributors?|maintainers?|issues?|commits?|pull requests?)?",
    flags=re.IGNORECASE,
)

_GENERIC_STOPWORDS = {
    "this",
    "that",
    "with",
    "from",
    "have",
    "will",
    "into",
    "their",
    "about",
    "which",
    "where",
    "what",
    "using",
    "than",
    "between",
    "across",
    "through",
    "enterprise",
    "market",
    "intelligence",
    "architecture",
    "decision",
    "around",
    "roughly",
    "about",
    "closer",
    "comparable",
    "current",
    "stack",
    "report",
    "model",
    "models",
    "pro",
    "api",
    "ai",
    "benchmark",
    "benchmarks",
    "score",
    "scores",
    "pricing",
    "price",
    "description",
    "tool",
    "tools",
    "search",
    "diamond",
    "verified",
    "epoch",
    "scale",
    "smart",
    "default",
}

_UNIT_TOKENS = {
    "%",
    "percent",
    "usd",
    "eur",
    "rub",
    "руб",
    "ms",
    "millisecond",
    "milliseconds",
    "sec",
    "second",
    "seconds",
    "minute",
    "minutes",
    "hour",
    "hours",
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",
    "year",
    "years",
    "k",
    "m",
    "b",
    "million",
    "billion",
    "token",
    "tokens",
    "request",
    "requests",
    "query",
    "queries",
    "rpm",
    "rps",
    "qps",
    "ctx",
    "star",
    "stars",
    "fork",
    "forks",
    "contributors",
    "maintainers",
    "issues",
    "commits",
    "pull",
    "requests",
}

_QUALIFIER_MARKERS = {
    "input",
    "output",
    "prompt",
    "completion",
    "read",
    "write",
    "ingest",
    "search",
    "extract",
    "crawl",
    "hosted",
    "self-hosted",
    "cloud",
    "api",
    "managed",
    "context",
    "window",
    "latency",
    "throughput",
    "benchmark",
    "mmlu",
    "gpqa",
    "swe",
    "livecodebench",
    "query",
    "queries",
    "request",
    "requests",
}

_MODEL_VERSION_MARKERS = {
    "claude",
    "deepseek",
    "llama",
    "mistral",
    "gpt",
    "gemini",
    "opus",
    "sonnet",
    "haiku",
    "mixtral",
}

_METRIC_MARKERS = {
    "$",
    "%",
    "price",
    "pricing",
    "priced",
    "per token",
    "per million",
    "per query",
    "latency",
    "context",
    "window",
    "benchmark",
    "score",
    "reports/month",
    "report",
    "month",
    "months",
    "year",
    "years",
    "week",
    "weeks",
    "day",
    "days",
    "hour",
    "hours",
    "minute",
    "minutes",
    "second",
    "seconds",
    "tokens",
    "query",
    "queries",
}

_GROUNDING_FAMILIES = {
    "money",
    "ratio",
    "latency",
    "context_window",
    "throughput",
    "benchmark",
}

_IGNORED_CONTRADICTION_FAMILIES = {"repo_signal"}


@dataclass(frozen=True)
class NumericFact:
    value: float
    family: str
    raw: str
    subjects: frozenset[str] = field(default_factory=frozenset)
    context_tokens: frozenset[str] = field(default_factory=frozenset)
    qualifier_tokens: frozenset[str] = field(default_factory=frozenset)


def _replace_markdown_links(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)


def _strip_markup(text: str) -> str:
    cleaned = _replace_markdown_links(text)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"\[Evidence:[^\]]+\]", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"`[^`]+`", " ", cleaned)
    cleaned = re.sub(r"^\s*#+\s+.*$", " ", cleaned, flags=re.MULTILINE)
    return cleaned


def _tokenize_words(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-zА-Яа-я][A-Za-zА-Яа-я0-9.+_-]{2,}", text)]


def _subject_tokens(text: str) -> frozenset[str]:
    branded: set[str] = set()
    generic: set[str] = set()
    for raw in re.findall(r"[A-Za-zА-Яа-я][A-Za-zА-Яа-я0-9.+_-]{2,}", text):
        token = raw.strip(".,:;()[]{}<>\"'`").lower()
        if not token or token in _GENERIC_STOPWORDS or token in _UNIT_TOKENS:
            continue
        if any(character.isupper() for character in raw) or any(character.isdigit() for character in raw) or "-" in raw or "." in raw:
            branded.add(token)
        elif len(token) >= 4:
            generic.add(token)
    if branded:
        return frozenset(branded)
    return frozenset(sorted(generic)[:6])


def _fact_subject_tokens(source_text: str, number_start: int, number_end: int) -> frozenset[str]:
    global_subjects = _subject_tokens(source_text)
    model_subjects = frozenset(
        subject
        for subject in global_subjects
        if any(marker in subject for marker in _MODEL_VERSION_MARKERS)
    )
    model_families = {
        marker
        for subject in model_subjects
        for marker in _MODEL_VERSION_MARKERS
        if marker in subject
    }
    lowered_source = source_text.lower()
    if len(model_families) == 1 and model_subjects:
        return model_subjects
    if len(model_families) > 1 and any(
        marker in lowered_source
        for marker in (" vs ", " versus ", " outperform", " behind ", " ahead of ", " compared to ", " compared with ", " than ")
    ):
        return frozenset()
    windows = (
        source_text[max(0, number_start - 28) : min(len(source_text), number_end + 28)],
        source_text[max(0, number_start - 48) : min(len(source_text), number_end + 18)],
    )
    for window in windows:
        subjects = _subject_tokens(window)
        if not subjects:
            continue
        model_families = {
            marker
            for subject in subjects
            for marker in _MODEL_VERSION_MARKERS
            if marker in subject
        }
        if len(model_families) > 1:
            return frozenset()
        return subjects
    return frozenset()


def _context_tokens(snippet: str, subjects: frozenset[str]) -> frozenset[str]:
    tokens = {
        token
        for token in _tokenize_words(snippet)
        if token not in _GENERIC_STOPWORDS and token not in _UNIT_TOKENS and token not in subjects
    }
    return frozenset(sorted(tokens)[:8])


def _qualifier_tokens(snippet: str) -> frozenset[str]:
    tokens = {token for token in _tokenize_words(snippet) if token in _QUALIFIER_MARKERS}
    return frozenset(tokens)


def _parse_numeric_value(number_text: str, unit: str) -> float | None:
    try:
        value = float(number_text.replace(",", "."))
    except ValueError:
        return None
    multiplier = {
        "k": 1_000.0,
        "m": 1_000_000.0,
        "b": 1_000_000_000.0,
        "million": 1_000_000.0,
        "billion": 1_000_000_000.0,
    }.get(unit.lower(), 1.0)
    return value * multiplier


def _infer_family(snippet: str, prefix: str, unit: str) -> str | None:
    lowered = snippet.lower()
    normalized_unit = unit.lower()
    if normalized_unit in {"%", "percent"} or any(token in lowered for token in ("percent", "percentage", "share", "roi", "cagr", "margin")):
        return "ratio"
    if prefix or any(token in lowered for token in (" price", "pricing", "priced", "cost per", "per token", "per million", "per query", "per search", "credits", "usd", "eur", "rub", "руб")):
        return "money"
    if any(token in lowered for token in ("mmlu", "gpqa", "swe-bench", "livecodebench", "benchmark", "leaderboard", "accuracy", "score", "pass@")):
        return "benchmark"
    if re.search(r"\b(latency|response time|p95|p99|ms|millisecond(?:s)?|seconds?|sec)\b", lowered):
        return "latency"
    if re.search(r"\b(context window|context|token limit|max tokens|long context)\b", lowered):
        return "context_window"
    if re.search(r"\b(rpm|rps|qps|throughput|requests per|queries per)\b", lowered):
        return "throughput"
    if re.search(r"\b(months?|years?|weeks?|days?|hours?|minutes?)\b", lowered):
        return "time"
    if re.search(r"\b(stars?|forks?|contributors?|maintainers?|issues?|commits?|pull requests?)\b", lowered):
        return "repo_signal"
    return None


def _looks_like_model_version(source_text: str, number_start: int, number_end: int, prefix: str, unit: str) -> bool:
    if prefix or unit:
        return False
    immediate_left = source_text[max(0, number_start - 12) : number_start].lower()
    if re.search(r"(?:gpt|claude|gemini|deepseek|glm|grok|qwen|llama|mistral|opus|sonnet|haiku|r1|v)\s*[-.]?$", immediate_left):
        return True
    if number_start > 0 and source_text[number_start - 1] in {"-", "v", "V"}:
        return True
    local = source_text[max(0, number_start - 18) : min(len(source_text), number_end + 18)].lower()
    if not any(marker in local for marker in _MODEL_VERSION_MARKERS):
        return False
    return not any(marker in local for marker in _METRIC_MARKERS)


def extract_numeric_facts(text: str, *, strip_markup: bool = False) -> list[NumericFact]:
    source_text = _strip_markup(text) if strip_markup else text
    facts: list[NumericFact] = []
    for match in _NUMERIC_FACT_RE.finditer(source_text):
        prefix = match.group("prefix") or ""
        number_text = match.group("number") or ""
        unit = (match.group("unit") or "").strip()
        if not number_text:
            continue
        tail = source_text[match.end() : min(len(source_text), match.end() + 2)].lower()
        head = source_text[max(0, match.start() - 1) : match.start()].lower()
        if not prefix and not unit and (tail.startswith("-") or tail.startswith("x") or (head == "-" and tail.startswith("x"))):
            continue
        if _looks_like_model_version(source_text, match.start("number"), match.end("number"), prefix, unit):
            continue
        value = _parse_numeric_value(number_text, unit)
        if value is None:
            continue
        if not prefix and not unit and 1900 <= value <= 2100 and float(value).is_integer():
            continue
        snippet = source_text[max(0, match.start() - 28) : min(len(source_text), match.end() + 28)]
        family = _infer_family(snippet, prefix, unit)
        if not family:
            continue
        subjects = _fact_subject_tokens(source_text, match.start(), match.end())
        facts.append(
            NumericFact(
                value=value,
                family=family,
                raw=match.group(0).strip(),
                subjects=subjects,
                context_tokens=_context_tokens(snippet, subjects),
                qualifier_tokens=_qualifier_tokens(snippet),
            )
        )
    return facts


def _has_subject_overlap(left: NumericFact, right: NumericFact) -> bool:
    if left.subjects and right.subjects:
        return bool(left.subjects & right.subjects)
    if left.subjects or right.subjects:
        return False
    return True


def _has_context_overlap(left: NumericFact, right: NumericFact) -> bool:
    overlap = len(left.context_tokens & right.context_tokens)
    qualifier_overlap = bool(left.qualifier_tokens & right.qualifier_tokens)
    if left.qualifier_tokens and right.qualifier_tokens and not qualifier_overlap:
        return False
    if left.family in {"money", "ratio", "benchmark"}:
        return overlap >= 1 or qualifier_overlap
    return overlap >= 1 or qualifier_overlap


def _materially_divergent(left: NumericFact, right: NumericFact) -> bool:
    low = min(left.value, right.value)
    high = max(left.value, right.value)
    if low <= 0:
        return False
    ratio = high / low
    if left.family == "ratio":
        return ratio >= 1.4 and (high - low) >= 10.0
    if left.family == "benchmark":
        return ratio >= 1.15 and (high - low) >= 5.0
    if left.family in {"money", "latency", "context_window", "throughput", "time"}:
        return ratio >= 1.5
    return ratio >= 1.8


def detect_contradictions(claims: list[ClaimRecord]) -> list[str]:
    notes: list[str] = []
    grouped: dict[str, list[ClaimRecord]] = defaultdict(list)
    claim_facts = {claim.claim_id: extract_numeric_facts(claim.statement) for claim in claims}
    for claim in claims:
        grouped[claim.question_id].append(claim)
    for question_id, group in grouped.items():
        for index, left_claim in enumerate(group):
            for right_claim in group[index + 1 :]:
                for left_fact in claim_facts.get(left_claim.claim_id, []):
                    if left_fact.family in _IGNORED_CONTRADICTION_FAMILIES:
                        continue
                    for right_fact in claim_facts.get(right_claim.claim_id, []):
                        if left_fact.family != right_fact.family:
                            continue
                        if right_fact.family in _IGNORED_CONTRADICTION_FAMILIES:
                            continue
                        if not _has_subject_overlap(left_fact, right_fact):
                            continue
                        if not _has_context_overlap(left_fact, right_fact):
                            continue
                        if not _materially_divergent(left_fact, right_fact):
                            continue
                        shared_subjects = sorted(left_fact.subjects & right_fact.subjects)
                        subject_label = f" for {'/'.join(shared_subjects[:2])}" if shared_subjects else ""
                        note = (
                            f"Question {question_id} has materially divergent {left_fact.family} claims"
                            f"{subject_label} ({left_fact.value:g} vs {right_fact.value:g})."
                        )
                        if note not in notes:
                            notes.append(note)
                        if note not in left_claim.contradiction_notes:
                            left_claim.contradiction_notes.append(note)
                        if note not in right_claim.contradiction_notes:
                            right_claim.contradiction_notes.append(note)
    return notes


def _close_value(left: float, right: float) -> bool:
    if left == right:
        return True
    baseline = max(abs(left), abs(right), 1.0)
    return abs(left - right) / baseline <= 0.05


def find_unsupported_precise_numbers(report_text: str, claim_texts: list[str]) -> list[str]:
    report_facts = [fact for fact in extract_numeric_facts(report_text, strip_markup=True) if fact.family in _GROUNDING_FAMILIES]
    supported_facts = [
        fact
        for claim_text in claim_texts
        for fact in extract_numeric_facts(claim_text)
        if fact.family in _GROUNDING_FAMILIES
    ]
    unsupported: list[str] = []
    seen: set[str] = set()
    for report_fact in report_facts:
        supported = any(
            report_fact.family == claim_fact.family
            and _close_value(report_fact.value, claim_fact.value)
            and (
                not report_fact.subjects
                or not claim_fact.subjects
                or bool(report_fact.subjects & claim_fact.subjects)
            )
            and (
                not report_fact.qualifier_tokens
                or not claim_fact.qualifier_tokens
                or bool(report_fact.qualifier_tokens & claim_fact.qualifier_tokens)
            )
            for claim_fact in supported_facts
        )
        if supported:
            continue
        marker = f"{report_fact.raw} ({report_fact.family})"
        if marker not in seen:
            seen.add(marker)
            unsupported.append(marker)
    return unsupported
