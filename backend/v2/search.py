from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import httpx

from backend.v2.models import (
    ResearchPlan,
    SearchCandidate,
    SourceLedgerEntry,
    SourceSnapshot,
    SourceType,
)
from backend.v2.reference_data import REFERENCE_PACKS, ReferenceSource, match_reference_pack


_LOW_SIGNAL_PATTERNS = (
    "skip to content",
    "sign in",
    "watchers",
    "forks",
    "stars",
    "packages 0",
    "releases no releases",
    "footer ©",
    "github, inc",
    "cookie preferences",
    "all rights reserved",
    "privacy policy",
    "terms of service",
)

_WEAK_DOMAIN_TOKENS = (
    "substack.com",
    "dev.to",
    "leetcode.com",
    "marketgrowthreports",
    "marketresearchfuture",
    "cognitivemarketresearch",
    "thebusinessresearchcompany",
    "fortunebusinessinsights",
    "precedenceresearch",
    "imarcgroup",
    "openpr.com",
    "globenewswire.com",
    "einnews.com",
    "prnewswire.com",
    "businesswire.com",
    "thecmo.com",
    "generect.com",
    "segmentstream.com",
    "uxdesign.cc",
    "hellopm.co",
    "createbytes.com",
    "mantadesign.com",
)

_HIGH_QUALITY_SECONDARY_DOMAIN_TOKENS = (
    "researchandmarkets.com",
    "mordorintelligence.com",
    "grandviewresearch.com",
    "forrester.com",
    "gartner.com",
    "mckinsey.com",
    "bcg.com",
    "bain.com",
    "deloitte.com",
    "pwc.com",
)

_ACADEMIC_DOMAIN_TOKENS = (
    "cambridge.org",
    "sciencedirect.com",
    "springer.com",
    "tandfonline.com",
    "ieee.org",
    "acm.org",
    "designsociety.org",
    "asmedigitalcollection.asme.org",
)

_WEAK_PATH_TOKENS = (
    "/top-",
    "/best-",
    "best-open-source",
    "/list",
    "/guide",
    "/guides/",
    "/compare",
    "/comparison",
    "/repositories",
    "/trends",
    "/tools/",
    "/software/",
    "/platforms/",
)


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def normalize_source_url(raw_url: str) -> str | None:
    candidate = html.unescape(raw_url).strip()
    if not candidate:
        return None

    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    elif candidate.startswith("/"):
        candidate = urljoin("https://duckduckgo.com", candidate)

    parsed = urlparse(candidate)
    if parsed.netloc.lower().endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        if target:
            candidate = html.unescape(unquote(target)).strip()
            if candidate.startswith("//"):
                candidate = f"https:{candidate}"
            parsed = urlparse(candidate)

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def classify_source_type(url: str) -> SourceType:
    domain = _domain(url)
    parsed = urlparse(url)
    path = parsed.path.lower()
    host_prefix = domain.split(".")[0] if domain else ""

    if any(token in domain for token in _WEAK_DOMAIN_TOKENS):
        return SourceType.WEAK_SECONDARY

    if "community.openai.com" in domain:
        return SourceType.HIGH_QUALITY_SECONDARY

    if any(token in path for token in _WEAK_PATH_TOKENS):
        return SourceType.WEAK_SECONDARY

    if any(marker in path for marker in ("/blog/", "/articles/", "/guides/", "/resources/", "/news/")):
        return SourceType.HIGH_QUALITY_SECONDARY

    if any(token in domain for token in _HIGH_QUALITY_SECONDARY_DOMAIN_TOKENS):
        return SourceType.HIGH_QUALITY_SECONDARY

    if any(token in domain for token in _ACADEMIC_DOMAIN_TOKENS):
        return SourceType.RESEARCH_PAPER

    if "github.com" in domain:
        if "/topics/" in path or "awesome" in path or "case-stud" in path:
            return SourceType.WEAK_SECONDARY
        return SourceType.OFFICIAL_DOCUMENTATION

    if "huggingface.co" in domain:
        if path.startswith("/blog/") or path.startswith("/collections/"):
            return SourceType.HIGH_QUALITY_SECONDARY
        if "/spaces/" in path and "leaderboard" in path:
            return SourceType.BENCHMARK
        return SourceType.OFFICIAL_DOCUMENTATION

    if (
        host_prefix in {"docs", "developer", "developers", "api-docs"}
        or any(
            token in domain
            for token in (
                "playwright.dev",
                "platform.openai.com",
                "qwenlm.github.io",
                "ai.google.dev",
                "developers.googleblog.com",
                "anthropic.com",
                "openai.com",
                "mistral.ai",
                "meta.com",
                "ollama.com",
                "lmstudio.ai",
            )
        )
    ):
        return SourceType.OFFICIAL_DOCUMENTATION
    if any(
        token in domain
        for token in (
            "livebench",
            "leaderboard",
            "artificialanalysis",
            "paperswithcode",
            "swebench",
            "lmarena",
            "scale.com",
        )
    ):
        return SourceType.BENCHMARK
    if any(token in domain for token in ("gov", ".edu", "arxiv")):
        return SourceType.RESEARCH_PAPER
    if any(
        token in domain
        for token in (
            "medium.com",
            "reddit.com",
            "youtube.com",
            "t.me",
            "dzen.ru",
            "dtf.ru",
            "livejournal.com",
            "onedollarvps.com",
            "pikabu.ru",
        )
    ):
        return SourceType.WEAK_SECONDARY
    if any(
        token in domain
        for token in (
            "habr.com",
            "vc.ru",
            "tproger.ru",
            "unite.ai",
            "venturebeat.com",
            "techcrunch.com",
            "theverge.com",
            "semianalysis.com",
        )
    ):
        return SourceType.HIGH_QUALITY_SECONDARY
    return SourceType.VENDOR_PAGE


def score_source(url: str, source_type: SourceType, preferred_domains: list[str]) -> float:
    score = {
        SourceType.OFFICIAL_DOCUMENTATION: 0.95,
        SourceType.GOVERNMENT: 0.95,
        SourceType.RESEARCH_PAPER: 0.9,
        SourceType.BENCHMARK: 0.85,
        SourceType.VENDOR_PAGE: 0.78,
        SourceType.HIGH_QUALITY_SECONDARY: 0.68,
        SourceType.WEAK_SECONDARY: 0.25,
    }[source_type]
    if any(domain and domain in url for domain in preferred_domains):
        score += 0.05
    return min(score, 0.99)


def _candidate_quality_adjustment(candidate: SearchCandidate) -> float:
    title = candidate.title.lower()
    url = candidate.url.lower()
    adjustment = 0.0

    if any(token in title or token in url for token in ("leaderboard", "benchmark", "pricing", "api", "docs")):
        adjustment += 0.08
    if any(
        token in title or token in url
        for token in ("gpt-researcher", "llamaindex", "langchain", "haystack", "tavily", "searxng", "perplexity")
    ):
        adjustment += 0.06
    if any(token in title or token in url for token in ("awesome", "/topics/", "collection", "case stud", "case-stud", "top 10")):
        adjustment -= 0.18
    if any(token in title for token in ("welcome to", "updated", "best open-source", "awesome llm")):
        adjustment -= 0.08
    return adjustment


def _clean_extracted_text(text: str) -> str:
    chunks: list[str] = []
    for raw_chunk in re.split(r"[\r\n]+", text):
        normalized = " ".join(raw_chunk.split()).strip()
        if len(normalized) < 20:
            continue
        lowered = normalized.lower()
        if any(marker in lowered for marker in _LOW_SIGNAL_PATTERNS):
            continue
        chunks.append(normalized)
    joined = " ".join(chunks)
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined


def _strip_html_tags(body: str) -> str:
    without_scripts = re.sub(
        r"<script.*?</script>|<style.*?</style>|<!--.*?-->",
        " ",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html.unescape(re.sub(r"<[^>]+>", " ", without_scripts))


def _extract_preferred_html_region(url: str, body: str) -> str:
    lowered_url = url.lower()
    patterns = []
    if "github.com" in lowered_url:
        patterns.extend(
            [
                r'<article[^>]*markdown-body[^>]*>(.*?)</article>',
                r'<div[^>]*id="readme"[^>]*>(.*?)</div>',
                r'<main[^>]*>(.*?)</main>',
            ]
        )
    elif "huggingface.co" in lowered_url:
        patterns.extend(
            [
                r'<main[^>]*>(.*?)</main>',
                r'<article[^>]*>(.*?)</article>',
            ]
        )
    else:
        patterns.extend(
            [
                r'<article[^>]*>(.*?)</article>',
                r'<main[^>]*>(.*?)</main>',
            ]
        )

    for pattern in patterns:
        match = re.search(pattern, body, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1)
    return body


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, plan: ResearchPlan) -> list[SearchCandidate]:
        ...

    async def fetch(self, source: SourceLedgerEntry) -> SourceSnapshot:
        ...


@dataclass
class SeededSearchProvider:
    name: str = "seeded"

    async def search(self, query: str, plan: ResearchPlan) -> list[SearchCandidate]:
        pack = match_reference_pack(query)
        if not pack:
            return []
        candidates: list[SearchCandidate] = []
        question_id = plan.primary_questions[0].question_id if plan.primary_questions else "primary"
        for source in pack.sources:
            candidates.append(
                SearchCandidate(
                    question_id=question_id,
                    query=query,
                    url=source.url,
                    title=source.title,
                    snippet=source.excerpt,
                    domain=source.domain,
                    provider=self.name,
                )
            )
        return candidates

    async def fetch(self, source: SourceLedgerEntry) -> SourceSnapshot:
        matched: ReferenceSource | None = None
        for pack in REFERENCE_PACKS:
            matched = next((item for item in pack.sources if item.url == source.url), None)
            if matched:
                break
        return SourceSnapshot(
            source_id=source.source_id,
            url=source.url,
            title=source.title,
            content=matched.content if matched else source.selection_reason,
            excerpt=matched.excerpt if matched else source.selection_reason,
            provider=self.name,
            fetch_status="ok",
        )


@dataclass
class DuckDuckGoSearchProvider:
    name: str = "duckduckgo"

    async def search(self, query: str, plan: ResearchPlan) -> list[SearchCandidate]:
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "smart-report-v2"})
            response.raise_for_status()
        body = response.text
        matches = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, flags=re.IGNORECASE)
        question_id = plan.primary_questions[0].question_id if plan.primary_questions else "primary"
        candidates: list[SearchCandidate] = []
        for raw_url, raw_title in matches[:8]:
            normalized_url = normalize_source_url(raw_url)
            if not normalized_url:
                continue
            candidates.append(
                SearchCandidate(
                    question_id=question_id,
                    query=query,
                    url=normalized_url,
                    title=re.sub(r"<.*?>", "", html.unescape(raw_title)),
                    snippet="",
                    domain=_domain(normalized_url),
                    provider=self.name,
                )
            )
        return candidates

    async def fetch(self, source: SourceLedgerEntry) -> SourceSnapshot:
        normalized_url = normalize_source_url(source.url)
        if not normalized_url:
            return SourceSnapshot(
                source_id=source.source_id,
                url=source.url,
                title=source.title,
                content="Source URL could not be normalized into a fetchable http/https URL.",
                excerpt="Source URL could not be normalized.",
                provider=self.name,
                fetch_status="invalid_url",
            )

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                response = await client.get(normalized_url, headers={"User-Agent": "smart-report-v2"})
                response.raise_for_status()
            body = response.text
            preferred_region = _extract_preferred_html_region(normalized_url, body)
            text = _clean_extracted_text(_strip_html_tags(preferred_region))
            if len(text) < 400:
                text = _clean_extracted_text(_strip_html_tags(body))
            return SourceSnapshot(
                source_id=source.source_id,
                url=normalized_url,
                title=source.title,
                content=text[:12000],
                excerpt=text[:400],
                provider=self.name,
                fetch_status="ok",
            )
        except Exception as exc:
            message = f"Source fetch failed: {exc}"
            return SourceSnapshot(
                source_id=source.source_id,
                url=normalized_url,
                title=source.title,
                content=message,
                excerpt=message[:400],
                provider=self.name,
                fetch_status="error",
            )


def select_sources(candidates: list[SearchCandidate], plan: ResearchPlan) -> list[SourceLedgerEntry]:
    seen: set[str] = set()
    allowed_types = set(plan.required_source_mix)
    ranked_entries: list[tuple[float, SourceLedgerEntry]] = []
    for candidate in candidates:
        if candidate.url in seen:
            continue
        source_type = classify_source_type(candidate.url)
        if allowed_types and source_type not in allowed_types:
            continue
        seen.add(candidate.url)
        entry = SourceLedgerEntry(
            url=candidate.url,
            title=candidate.title,
            domain=candidate.domain,
            source_type=source_type,
            publisher=candidate.domain,
            reliability_score=score_source(candidate.url, source_type, plan.preferred_domains),
            selection_reason=(
                f"Matched search query '{candidate.query}' for question {candidate.question_id}; "
                f"quality adjustment {_candidate_quality_adjustment(candidate):+.2f}"
            ),
            question_links=[candidate.question_id],
        )
        ranked_entries.append((entry.reliability_score + _candidate_quality_adjustment(candidate), entry))
    ranked_entries.sort(key=lambda item: item[0], reverse=True)

    selected: list[SourceLedgerEntry] = []
    domain_counts: dict[str, int] = {}
    for _, entry in ranked_entries:
        if domain_counts.get(entry.domain, 0) >= 3:
            continue
        selected.append(entry)
        domain_counts[entry.domain] = domain_counts.get(entry.domain, 0) + 1
        if len(selected) >= 8:
            break
    return selected
