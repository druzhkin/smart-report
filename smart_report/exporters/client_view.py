"""Client-facing report sanitization."""

from __future__ import annotations

import re
from typing import Any

from ..models import FinalReport, NumberedSource

_GRADE_TAG_RE = re.compile(r"\[(?:STRONG|MODERATE|WEAK|SPECULATIVE)\]\s*")
_REF_RE = re.compile(r"\[REF:([^\]]+)\]")

_INTERNAL_TERMS = (
    "первого раунда",
    "первый раунд",
    "добор-раунд",
    "добор раунд",
    "main_synthesis",
    "main synthesis",
    "coverage",
    "retry",
    "Perplexity",
    "OpenAI DR",
    "Claude",
    "STRONG источник",
    "MODERATE источник",
    "WEAK источник",
    "resolved mortgage-share skew",
    "delivery open",
)


def sanitize_final_report(report: FinalReport) -> FinalReport:
    """Return a client-facing copy of *report* without mutating persistence."""

    ref_map = _bibliography_ref_map(report.bibliography)
    data = report.model_dump(mode="json")
    sanitized = _sanitize_value(data, ref_map)
    # Client reports must not carry pipeline metadata. Audit/data-pack exports
    # retain the raw report separately.
    sanitized["metadata"] = {"client_view_sanitized": True}
    return FinalReport.model_validate(sanitized)


def contains_client_leak(report: FinalReport) -> list[str]:
    """Return human-readable leak markers still present in a report copy."""

    text = " ".join(_iter_string_values(report.model_dump(mode="json")))
    leaks: list[str] = []
    for pattern in ("[STRONG]", "[MODERATE]", "[WEAK]", "[SPECULATIVE]", "[REF:"):
        if pattern in text:
            leaks.append(pattern)
    for term in _INTERNAL_TERMS:
        if term.lower() in text.lower():
            leaks.append(term)
    return leaks


def sanitize_text(text: str, ref_map: dict[str, int] | None = None) -> str:
    ref_map = ref_map or {}
    out = _GRADE_TAG_RE.sub("", text)

    def _ref_sub(match: re.Match[str]) -> str:
        url = match.group(1).strip()
        number = ref_map.get(url)
        return f"[{number}]" if number else ""

    out = _REF_RE.sub(_ref_sub, out)
    out = _remove_internal_parentheticals(out)
    out = _remove_internal_sentences(out)
    out = _clean_internal_phrases(out)
    out = _clean_short_process_fragments(out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _iter_string_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_string_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_string_values(item)


_STRUCTURED_LITERAL_KEYS = {
    "reliability",
    "evidence_strength",
    "importance",
    "kind",
    "chart_type",
}


def _sanitize_value(value: Any, ref_map: dict[str, int], *, key: str | None = None) -> Any:
    if key in _STRUCTURED_LITERAL_KEYS:
        return value
    if isinstance(value, str):
        return sanitize_text(value, ref_map)
    if isinstance(value, list):
        return [_sanitize_value(v, ref_map) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_value(v, ref_map, key=k) for k, v in value.items()}
    return value


def _bibliography_ref_map(items: list[NumberedSource]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        url = item.source_ref.url.strip()
        if url and item.number:
            out[url] = item.number
    return out


def _remove_internal_parentheticals(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        body = match.group(0)
        return "" if _has_internal_term(body) else body

    return re.sub(r"\([^()]{0,260}\)", repl, text)


def _remove_internal_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text)
    kept = [part for part in parts if not _has_internal_term(part)]
    if len(kept) == len(parts):
        return text
    return " ".join(part.strip() for part in kept if part.strip())


def _clean_internal_phrases(text: str) -> str:
    replacements = {
        "как STRONG источнику": "как источнику",
        "как STRONG источник": "как источник",
        "STRONG источнику": "источнику",
        "STRONG источник": "источник",
        "MODERATE источник": "источник",
        "WEAK источник": "источник",
        "инвалидирующая ошибка": "существенная методологическая ошибка",
    }
    out = text
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def _clean_short_process_fragments(text: str) -> str:
    replacements = {
        "medium": "",
        "resolved mortgage-share skew": "",
        "delivery open": "Оставшиеся пробелы требуют дополнительной проверки.",
        "all agree on top-3.": "Источники сходятся по первым позициям.",
        "all agree on top-3": "Источники сходятся по первым позициям",
        "pick 55": "используем более консервативную оценку 55%",
    }
    stripped = text.strip()
    if stripped in replacements:
        return replacements[stripped]
    out = text
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def _has_internal_term(text: str) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in _INTERNAL_TERMS)
