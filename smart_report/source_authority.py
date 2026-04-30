"""Source-authority heuristics used by delivery readiness gates.

The analyzer's reliability labels are useful but not sufficient: older saved
runs can mark official domains as "medium", while some domains are visibly
primary/regulatory from their URL or bibliography confidence. These helpers are
deliberately conservative and domain-neutral.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .models import FinalReport, Source, SourceRef

_OFFICIAL_DOMAIN_HINTS = (
    ".gov",
    ".gov.",
    "gov.",
    "europa.eu",
    "europarl.europa.eu",
    "ec.europa.eu",
    "cbr.ru",
    "nalog.gov.ru",
    "minfin.gov.ru",
    "mos.ru",
    "dom.rf",
    "xn--d1aqf.xn--p1ai",
)

_OFFICIAL_TITLE_HINTS = (
    "official",
    "government",
    "ministry",
    "central bank",
    "european commission",
    "european parliament",
    "regulator",
    "commission adopts",
)


def count_authoritative_sources(report: FinalReport) -> int:
    seen: set[str] = set()
    for source in report.all_sources or []:
        if is_authoritative_source(source):
            seen.add(source.url or source.title)
    for item in report.bibliography or []:
        ref = item.source_ref
        if is_authoritative_ref(ref):
            seen.add(ref.url or ref.title or str(item.number))
    return len({value for value in seen if value})


def is_authoritative_source(source: Source) -> bool:
    if source.reliability == "high":
        return True
    return _looks_official(source.url, source.title)


def is_authoritative_ref(ref: SourceRef) -> bool:
    if ref.confidence == "primary":
        return True
    return _looks_official(ref.url, ref.title or ref.publisher or "")


def _looks_official(url: str, title: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    text = f"{host} {title or ''}".lower()
    return any(hint in text for hint in _OFFICIAL_DOMAIN_HINTS + _OFFICIAL_TITLE_HINTS)
