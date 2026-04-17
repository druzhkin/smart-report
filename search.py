"""Perplexity primary search; Firecrawl fallback (live web + markdown + Claude synth).

Fallback chain: Firecrawl /v1/search (preferred) → DuckDuckGo HTML SERP (last resort).
Firecrawl returns already-scraped markdown so no second fetch round-trip is needed."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from html import unescape
from typing import Any
from urllib.parse import unquote

import httpx

from config import perplexity_model_for, settings
from llm import account_provider

log = logging.getLogger("search")


def _pplx_cost() -> float:
    m = perplexity_model_for()
    usd = settings.perplexity_usd_sonar_pro if "pro" in m.lower() else settings.perplexity_usd_sonar
    return usd * settings.usd_to_credits

PPLX_URL = "https://api.perplexity.ai/chat/completions"
TAVILY_URL = "https://api.tavily.com/search"
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
JINA_READER_BASE = "https://r.jina.ai/"
JINA_SEARCH_BASE = "https://s.jina.ai/"
OPENALEX_URL = "https://api.openalex.org/works"
CROSSREF_URL = "https://api.crossref.org/works"
S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_URL = "https://export.arxiv.org/api/query"
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
EUROPEPMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DOAJ_URL = "https://doaj.org/api/search/articles"
CORE_URL = "https://api.core.ac.uk/v3/search/works"
ACADEMIC_UA = "smart-report-mvp/1.0 (mailto:research@smart-report.local)"
ACADEMIC_TIMEOUT = 15.0
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)


def _strip_html(html: str) -> str:
    html = _SCRIPT_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", unescape(text)).strip()


def _clean_ddg_url(href: str) -> str:
    m = re.search(r"uddg=([^&]+)", href)
    if m:
        return unquote(m.group(1))
    return href


async def _ddg_search(http: httpx.AsyncClient, query: str, k: int = 6) -> list[dict[str, str]]:
    r = await http.post(
        DDG_HTML_URL,
        data={"q": query, "kl": "ru-ru"},
        headers={"User-Agent": UA, "Accept": "text/html"},
    )
    r.raise_for_status()
    out: list[dict[str, str]] = []
    for m in _RESULT_RE.finditer(r.text):
        url = _clean_ddg_url(m.group(1))
        if not url.startswith("http"):
            continue
        title = _strip_html(m.group(2))
        snippet = _strip_html(m.group(3))
        out.append({"url": url, "title": title, "snippet": snippet})
        if len(out) >= k:
            break
    return out


async def _fetch_page(http: httpx.AsyncClient, url: str, max_chars: int = 6000) -> str:
    if settings.use_jina_reader:
        try:
            r = await http.get(
                JINA_READER_BASE + url,
                headers={"User-Agent": UA, "Accept": "text/plain"},
                follow_redirects=True,
                timeout=25,
            )
            if r.status_code < 400 and r.text:
                return r.text[:max_chars]
        except Exception:
            pass
    try:
        r = await http.get(url, headers={"User-Agent": UA}, follow_redirects=True, timeout=20)
        if r.status_code >= 400 or "text" not in r.headers.get("content-type", ""):
            return ""
        return _strip_html(r.text)[:max_chars]
    except Exception:
        return ""


async def _brave_search(http: httpx.AsyncClient, query: str, k: int = 8) -> list[dict[str, str]]:
    if not settings.brave_api_key:
        return []
    try:
        r = await http.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": k, "safesearch": "moderate"},
            headers={
                "X-Subscription-Token": settings.brave_api_key,
                "Accept": "application/json",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for item in ((data.get("web") or {}).get("results") or [])[:k]:
        url = item.get("url") or ""
        if not url.startswith("http"):
            continue
        out.append({
            "url": url,
            "title": item.get("title") or url,
            "snippet": item.get("description") or "",
        })
    if out:
        account_provider("brave", 0.003 * settings.usd_to_credits)
    return out


async def _openalex_search(query: str, k: int = 5) -> list[dict[str, Any]]:
    """OpenAlex: free peer-reviewed works API, no key required. Returns primary academic sources."""
    try:
        async with httpx.AsyncClient(timeout=ACADEMIC_TIMEOUT) as http:
            r = await http.get(
                OPENALEX_URL,
                params={
                    "search": query,
                    "per-page": k,
                    "select": "id,doi,title,publication_year,cited_by_count,abstract_inverted_index,primary_location,authorships",
                    "sort": "relevance_score:desc",
                },
                headers={"User-Agent": "smart-report-mvp/1.0 (mailto:research@smart-report.local)"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []
    items = []
    for w in (data.get("results") or [])[:k]:
        doi = w.get("doi") or w.get("id") or ""
        title = w.get("title") or ""
        year = w.get("publication_year")
        cites = w.get("cited_by_count", 0)
        # reconstruct abstract from inverted index
        inv = w.get("abstract_inverted_index") or {}
        abs_text = ""
        if inv:
            pos_word = [(p, w_) for w_, ps in inv.items() for p in ps]
            pos_word.sort()
            abs_text = " ".join(w_ for _, w_ in pos_word)[:1500]
        loc = (w.get("primary_location") or {}).get("source") or {}
        venue = loc.get("display_name", "")
        authors = [a.get("author", {}).get("display_name", "") for a in (w.get("authorships") or [])[:3]]
        items.append({
            "url": doi,
            "title": title,
            "year": year,
            "venue": venue,
            "citations": cites,
            "authors": authors,
            "abstract": abs_text,
        })
    return items


async def _crossref_search(query: str, k: int = 3) -> list[dict[str, Any]]:
    """Crossref REST API: free, DOI-backed primary metadata."""
    try:
        async with httpx.AsyncClient(timeout=ACADEMIC_TIMEOUT) as http:
            r = await http.get(
                CROSSREF_URL,
                params={"query": query, "rows": k, "select": "DOI,title,issued,is-referenced-by-count,container-title,author"},
                headers={"User-Agent": "smart-report-mvp/1.0 (mailto:research@smart-report.local)"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []
    items = []
    for w in (data.get("message", {}).get("items") or [])[:k]:
        doi = w.get("DOI") or ""
        url = f"https://doi.org/{doi}" if doi else ""
        title_list = w.get("title") or []
        title = title_list[0] if title_list else ""
        issued_parts = (w.get("issued") or {}).get("date-parts") or [[None]]
        year = issued_parts[0][0] if issued_parts and issued_parts[0] else None
        cites = w.get("is-referenced-by-count", 0)
        container = (w.get("container-title") or [""])[0]
        authors = [
            f"{a.get('given','')} {a.get('family','')}".strip()
            for a in (w.get("author") or [])[:3]
        ]
        items.append({
            "url": url,
            "title": title,
            "year": year,
            "venue": container,
            "citations": cites,
            "authors": authors,
            "abstract": "",
        })
    return items


async def _semantic_scholar_search(query: str, k: int = 3) -> list[dict[str, Any]]:
    """Semantic Scholar Graph API: free, optional key bumps rate limit."""
    headers = {"User-Agent": ACADEMIC_UA}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
    try:
        async with httpx.AsyncClient(timeout=ACADEMIC_TIMEOUT) as http:
            r = await http.get(
                S2_URL,
                params={
                    "query": query,
                    "limit": k,
                    "fields": "title,year,citationCount,authors,abstract,externalIds,venue",
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []
    items = []
    for w in (data.get("data") or [])[:k]:
        ext = w.get("externalIds") or {}
        doi = ext.get("DOI", "")
        url = f"https://doi.org/{doi}" if doi else (f"https://www.semanticscholar.org/paper/{w.get('paperId','')}" if w.get("paperId") else "")
        items.append({
            "url": url,
            "title": w.get("title") or "",
            "year": w.get("year"),
            "venue": w.get("venue") or "",
            "citations": w.get("citationCount", 0),
            "authors": [a.get("name", "") for a in (w.get("authors") or [])[:3]],
            "abstract": (w.get("abstract") or "")[:1500],
        })
    return items


async def _arxiv_search(query: str, k: int = 3) -> list[dict[str, Any]]:
    """arXiv native Atom API: preprints across STEM."""
    try:
        async with httpx.AsyncClient(timeout=ACADEMIC_TIMEOUT) as http:
            r = await http.get(
                ARXIV_URL,
                params={"search_query": f"all:{query}", "max_results": k, "sortBy": "relevance"},
                headers={"User-Agent": ACADEMIC_UA},
            )
            r.raise_for_status()
            body = r.text
    except Exception:
        return []
    items = []
    entry_re = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
    tag_re = lambda t: re.compile(rf"<{t}[^>]*>(.*?)</{t}>", re.DOTALL)
    for m in entry_re.finditer(body):
        chunk = m.group(1)
        t = tag_re("title").search(chunk)
        s = tag_re("summary").search(chunk)
        p = tag_re("published").search(chunk)
        id_m = tag_re("id").search(chunk)
        authors = [a.group(1).strip() for a in tag_re("name").finditer(chunk)][:3]
        year = None
        if p:
            y = re.match(r"(\d{4})", p.group(1).strip())
            if y:
                year = int(y.group(1))
        items.append({
            "url": (id_m.group(1).strip() if id_m else ""),
            "title": _WS_RE.sub(" ", (t.group(1) if t else "")).strip(),
            "year": year,
            "venue": "arXiv",
            "citations": 0,
            "authors": authors,
            "abstract": _WS_RE.sub(" ", (s.group(1) if s else "")).strip()[:1500],
        })
        if len(items) >= k:
            break
    return items


async def _pubmed_search(query: str, k: int = 3) -> list[dict[str, Any]]:
    """PubMed E-utilities: esearch → esummary. Biomedical primary sources."""
    try:
        async with httpx.AsyncClient(timeout=ACADEMIC_TIMEOUT) as http:
            params_s: dict[str, Any] = {"db": "pubmed", "term": query, "retmax": k, "retmode": "json"}
            if settings.pubmed_api_key:
                params_s["api_key"] = settings.pubmed_api_key
            r = await http.get(PUBMED_ESEARCH, params=params_s, headers={"User-Agent": ACADEMIC_UA})
            r.raise_for_status()
            ids = ((r.json().get("esearchresult") or {}).get("idlist")) or []
            if not ids:
                return []
            params_u: dict[str, Any] = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
            if settings.pubmed_api_key:
                params_u["api_key"] = settings.pubmed_api_key
            r2 = await http.get(PUBMED_ESUMMARY, params=params_u, headers={"User-Agent": ACADEMIC_UA})
            r2.raise_for_status()
            result = (r2.json().get("result") or {})
    except Exception:
        return []
    items = []
    for pid in ids:
        w = result.get(pid) or {}
        if not w:
            continue
        pubdate = w.get("pubdate") or ""
        y = re.match(r"(\d{4})", pubdate)
        year = int(y.group(1)) if y else None
        items.append({
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
            "title": w.get("title") or "",
            "year": year,
            "venue": w.get("fulljournalname") or w.get("source") or "PubMed",
            "citations": 0,
            "authors": [a.get("name", "") for a in (w.get("authors") or [])[:3]],
            "abstract": "",
        })
    return items


async def _europe_pmc_search(query: str, k: int = 3) -> list[dict[str, Any]]:
    """Europe PMC REST API: free, includes preprints + biomedical literature."""
    try:
        async with httpx.AsyncClient(timeout=ACADEMIC_TIMEOUT) as http:
            r = await http.get(
                EUROPEPMC_URL,
                params={"query": query, "format": "json", "pageSize": k, "resultType": "core"},
                headers={"User-Agent": ACADEMIC_UA},
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []
    items = []
    for w in ((data.get("resultList") or {}).get("result") or [])[:k]:
        doi = w.get("doi") or ""
        pmid = w.get("pmid") or ""
        url = f"https://doi.org/{doi}" if doi else (f"https://europepmc.org/article/MED/{pmid}" if pmid else "")
        year = None
        pub_year = w.get("pubYear")
        if pub_year:
            try:
                year = int(pub_year)
            except Exception:
                pass
        author_str = w.get("authorString") or ""
        authors = [a.strip() for a in author_str.split(",")[:3] if a.strip()]
        items.append({
            "url": url,
            "title": w.get("title") or "",
            "year": year,
            "venue": w.get("journalTitle") or w.get("source") or "Europe PMC",
            "citations": w.get("citedByCount", 0),
            "authors": authors,
            "abstract": (w.get("abstractText") or "")[:1500],
        })
    return items


async def _doaj_search(query: str, k: int = 3) -> list[dict[str, Any]]:
    """DOAJ: Directory of Open Access Journals, free API."""
    try:
        from urllib.parse import quote
        async with httpx.AsyncClient(timeout=ACADEMIC_TIMEOUT) as http:
            r = await http.get(
                f"{DOAJ_URL}/{quote(query)}",
                params={"pageSize": k},
                headers={"User-Agent": ACADEMIC_UA},
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []
    items = []
    for hit in (data.get("results") or [])[:k]:
        bib = hit.get("bibjson") or {}
        doi_link = ""
        for ident in (bib.get("identifier") or []):
            if ident.get("type", "").lower() == "doi" and ident.get("id"):
                doi_link = f"https://doi.org/{ident['id']}"
                break
        if not doi_link:
            for link in (bib.get("link") or []):
                if link.get("url"):
                    doi_link = link["url"]
                    break
        year_raw = bib.get("year")
        try:
            year = int(year_raw) if year_raw else None
        except Exception:
            year = None
        authors = [a.get("name", "") for a in (bib.get("author") or [])[:3]]
        journal = (bib.get("journal") or {}).get("title", "DOAJ")
        items.append({
            "url": doi_link,
            "title": bib.get("title") or "",
            "year": year,
            "venue": journal,
            "citations": 0,
            "authors": authors,
            "abstract": (bib.get("abstract") or "")[:1500],
        })
    return items


async def _core_search(query: str, k: int = 3) -> list[dict[str, Any]]:
    """CORE API: aggregates open-access research. Requires CORE_API_KEY."""
    if not settings.core_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=ACADEMIC_TIMEOUT) as http:
            r = await http.get(
                CORE_URL,
                params={"q": query, "limit": k},
                headers={"Authorization": f"Bearer {settings.core_api_key}", "User-Agent": ACADEMIC_UA},
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []
    items = []
    for w in (data.get("results") or [])[:k]:
        doi = w.get("doi") or ""
        url = f"https://doi.org/{doi}" if doi else (w.get("downloadUrl") or "")
        year = w.get("yearPublished")
        try:
            year = int(year) if year else None
        except Exception:
            year = None
        authors = [a.get("name", "") for a in (w.get("authors") or [])[:3]]
        items.append({
            "url": url,
            "title": w.get("title") or "",
            "year": year,
            "venue": w.get("publisher") or "CORE",
            "citations": 0,
            "authors": authors,
            "abstract": (w.get("abstract") or "")[:1500],
        })
    return items


SOURCE_DB_MAP = {
    "openalex.org": "openalex",
    "doi.org": "crossref",
    "semanticscholar.org": "semantic_scholar",
    "arxiv.org": "arxiv",
    "pubmed.ncbi.nlm.nih.gov": "pubmed",
    "europepmc.org": "europe_pmc",
    "doaj.org": "doaj",
    "core.ac.uk": "core",
}


def _tag_source_db(items: list[dict[str, Any]], db: str) -> list[dict[str, Any]]:
    for it in items:
        it["source_db"] = db
    return items


async def _academic_fetch_all(query: str) -> list[dict[str, Any]]:
    """Single fanout across all academic sources. Returns deduped, ranked list tagged with source_db."""
    results = await asyncio.gather(
        _openalex_search(query, k=5),
        _crossref_search(query, k=3),
        _semantic_scholar_search(query, k=3),
        _arxiv_search(query, k=3),
        _pubmed_search(query, k=3),
        _europe_pmc_search(query, k=3),
        _doaj_search(query, k=2),
        _core_search(query, k=2),
        return_exceptions=True,
    )
    db_labels = ["openalex", "crossref", "semantic_scholar", "arxiv", "pubmed", "europe_pmc", "doaj", "core"]
    papers: list[dict[str, Any]] = []
    for res, label in zip(results, db_labels):
        if isinstance(res, list):
            papers.extend(_tag_source_db(res, label))
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for p in papers:
        key = (p.get("url") or p.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    uniq.sort(key=lambda p: (0 if p.get("abstract") else 1, -int(p.get("citations") or 0)))
    return uniq[:12]


async def _academic_bundle(query: str) -> tuple[str, list[dict[str, str]]]:
    items = await _academic_fetch_all(query)
    return _academic_bundle_from_items(items)


def _academic_bundle_from_items(uniq: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
    if not uniq:
        return "", []
    lines = ["=== ACADEMIC PRIMARY SOURCES (OpenAlex / Crossref / S2 / arXiv / PubMed / Europe PMC / DOAJ / CORE) ==="]
    citations: list[dict[str, str]] = []
    for i, p in enumerate(uniq[:12], 1):
        auth = ", ".join(p.get("authors") or []) or "—"
        venue = p.get("venue") or "—"
        year = p.get("year") or "n/a"
        cites = p.get("citations", 0)
        url = p.get("url", "")
        title = p.get("title", "")
        abs_ = p.get("abstract", "")
        lines.append(
            f"[A{i}] {title} — {auth} ({venue}, {year}, cited {cites}×) {url}"
            + (f"\n    {abs_[:600]}" if abs_ else "")
        )
        citations.append({"url": url, "title": f"{title} ({year})"})
    return "\n".join(lines), citations


def _parse_tavily_whitelist() -> list[str]:
    raw = (settings.tavily_include_domains or "").strip()
    if not raw:
        return []
    return [d.strip() for d in raw.split(",") if d.strip()]


async def _tavily_search(query: str, k: int = 6, include_domains: list[str] | None = None) -> dict[str, Any] | None:
    """Tavily /search: returns LLM answer + raw content of top-k results. Fast + cheap.
    Pass include_domains (or rely on TAVILY_INCLUDE_DOMAINS env) to whitelist trusted sources."""
    if not settings.tavily_api_key:
        return None
    domains = include_domains if include_domains is not None else _parse_tavily_whitelist()
    try:
        body: dict[str, Any] = {
            "api_key": settings.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": k,
            "include_raw_content": True,
            "include_answer": True,
        }
        if domains:
            body["include_domains"] = domains
        async with httpx.AsyncClient(timeout=45) as http:
            r = await http.post(TAVILY_URL, json=body)
            r.raise_for_status()
            data = r.json()
        answer = (data.get("answer") or "").strip()
        results = data.get("results") or []
        if not results:
            return None
        account_provider("tavily", settings.tavily_usd_per_query * settings.usd_to_credits)
        citations = [{"url": r.get("url", ""), "title": r.get("title") or r.get("url", "")} for r in results]
        # Build a dense text: Tavily answer + per-source bullets.
        bullets: list[str] = []
        for i, r in enumerate(results, 1):
            snippet = (r.get("raw_content") or r.get("content") or "")[:1200]
            bullets.append(f"[{i}] {r.get('title','')} — {r.get('url','')}\n{snippet}")
        text = (answer + "\n\n" if answer else "") + "\n\n".join(bullets)
        tag = "tavily_whitelist" if domains else "tavily"
        return {"text": text, "citations": citations, "query": query, "fallback": tag, "source_db": tag}
    except Exception:
        return None


async def _firecrawl_search(http: httpx.AsyncClient, query: str, k: int = 6) -> list[dict[str, str]]:
    """Firecrawl /v1/search: returns SERP with pre-scraped markdown (no second fetch needed)."""
    if not settings.firecrawl_api_key:
        return []
    try:
        r = await http.post(
            FIRECRAWL_SEARCH_URL,
            json={
                "query": query,
                "limit": k,
                "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
            },
            headers={
                "Authorization": f"Bearer {settings.firecrawl_api_key}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        out: list[dict[str, str]] = []
        for item in (data.get("data") or [])[:k]:
            url = item.get("url") or ""
            if not url.startswith("http"):
                continue
            md = item.get("markdown") or ""
            out.append({
                "url": url,
                "title": item.get("title") or url,
                "snippet": item.get("description") or "",
                "body": md[:6000],
            })
        if out:
            account_provider(
                "firecrawl",
                settings.firecrawl_usd_per_result * settings.usd_to_credits * len(out),
                calls=1,
            )
        return out
    except Exception:
        return []


async def _jina_search(http: httpx.AsyncClient, query: str, k: int = 6) -> list[dict[str, str]]:
    """Jina Search s.jina.ai (requires JINA_API_KEY). Returns pre-scraped SERP."""
    if not settings.jina_api_key:
        return []
    from urllib.parse import quote
    try:
        r = await http.get(
            JINA_SEARCH_BASE + quote(query),
            headers={
                "Accept": "application/json",
                "User-Agent": UA,
                "Authorization": f"Bearer {settings.jina_api_key}",
            },
            timeout=45,
            follow_redirects=True,
        )
        if r.status_code >= 400:
            return []
        data = r.json()
    except Exception:
        return []
    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: list[dict[str, str]] = []
    for it in items[:k]:
        url = it.get("url") or ""
        if not url.startswith("http"):
            continue
        body = it.get("content") or it.get("description") or ""
        out.append({
            "url": url,
            "title": it.get("title") or url,
            "snippet": (it.get("description") or "")[:400],
            "body": body[:6000],
        })
    return out


async def _hn_algolia_search(http: httpx.AsyncClient, query: str, k: int = 5) -> list[dict[str, str]]:
    """HackerNews Algolia search: free, no key. Surfaces SaaS/startup/tech discussions with real numbers.
    For each story, we attempt a cheap Jina-reader fetch of the URL to capture content."""
    # HN Algolia uses AND semantics — long queries return 0 hits. Try progressively shorter variants.
    words = [w for w in re.split(r"\s+", query) if len(w) > 2]
    candidates = [query] + [" ".join(words[:n]) for n in (4, 3, 2) if len(words) > n]
    hits: list[dict] = []
    try:
        for q in candidates:
            r = await http.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": q, "tags": "story", "hitsPerPage": k * 2},
                headers={"User-Agent": UA},
                timeout=15,
            )
            if r.status_code >= 400:
                continue
            hits = (r.json().get("hits") or [])
            if hits:
                break
    except Exception:
        return []
    picks = []
    for h in hits:
        url = h.get("url") or ""
        if not url.startswith("http"):
            continue
        picks.append(h)
        if len(picks) >= k:
            break
    if not picks:
        return []
    async def _grab(h: dict) -> dict[str, str] | None:
        body = await _fetch_page(http, h["url"], max_chars=4000)
        if not body:
            body = (h.get("story_text") or h.get("comment_text") or h.get("title") or "")[:4000]
        if not body.strip():
            return None
        return {
            "url": h["url"],
            "title": f"{h.get('title','')} (HN · {h.get('points',0)}pts)",
            "snippet": (h.get("title") or "")[:400],
            "body": body,
        }
    results = await asyncio.gather(*[_grab(h) for h in picks])
    return [x for x in results if x]


async def _wikipedia_search(http: httpx.AsyncClient, query: str, k: int = 4) -> list[dict[str, str]]:
    """Wikipedia search+extract API: free, no key, returns dense article intros with facts.
    Tries ru.wikipedia first (Russian goals), then en.wikipedia."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for lang in ("ru", "en"):
        try:
            r = await http.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrlimit": k,
                    "prop": "extracts|info",
                    "inprop": "url",
                    "exintro": "1",
                    "explaintext": "1",
                    "exchars": 1200,
                },
                headers={"User-Agent": "smart-report-mvp/1.0 research@smart-report.local"},
                timeout=15,
            )
            if r.status_code >= 400:
                continue
            pages = ((r.json().get("query") or {}).get("pages") or {})
        except Exception:
            continue
        for p in pages.values():
            url = p.get("fullurl") or ""
            if not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            title = p.get("title") or ""
            extract = (p.get("extract") or "").strip()
            if not extract:
                continue
            out.append({
                "url": url,
                "title": f"{title} (Wikipedia {lang})",
                "snippet": extract[:400],
                "body": extract[:6000],
            })
            if len(out) >= k:
                return out
        if len(out) >= k:
            break
    return out


_RU_RE_KEYWORDS = re.compile(
    r"недвижим|жил|квартир|жилья|новострой|жк|residential|real.?estate|property",
    re.IGNORECASE,
)
_RU_RE_DOMAINS = [
    "domclick.ru", "cian.ru", "avito.ru/nedvizhimost",
    "domrf.ru", "rosreestr.gov.ru", "metrium.ru",
    "nedvizhimost.ru", "knightfrank.ru", "cbre.ru", "savills.ru",
]

# (focus_keyword, disallowed_snippet_markers)
_RELEVANCE_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (
        re.compile(r"недвижим|жил|квартир|residential|real.?estate|property|housing", re.I),
        ["oncology", "clinical", "pubmed", "cancer", "patient", "trial", "NCT0",
         "tumor", "chemotherapy", "randomized controlled"],
    ),
    (
        re.compile(r"финанс|econom|market|рынок|коммерч", re.I),
        ["astro-ph", "hep-th", "quant-ph", "gr-qc", "cond-mat", "nucl-", "astrophys"],
    ),
]


def _normalize_citations(raw: Any) -> list[dict[str, str]]:
    """Coerce heterogeneous citation items to {url,title,...} dicts.
    Perplexity returns bare URL strings; gpt-researcher returns dicts; academic returns dicts."""
    if not raw:
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({"url": item, "title": item})
    return out


def filter_irrelevant(results: list[dict[str, Any]], query: str, focus: str) -> list[dict[str, Any]]:
    """Drop results with strong off-topic markers based on focus domain heuristics."""
    combined = f"{query} {focus}"
    applicable_rules = [(fp, markers) for fp, markers in _RELEVANCE_RULES if fp.search(combined)]
    if not applicable_rules:
        return results
    out: list[dict[str, Any]] = []
    for r in results:
        haystack = f"{r.get('title','')} {r.get('snippet','') or r.get('abstract','') or ''} {r.get('url','')}".lower()
        drop = False
        for _, markers in applicable_rules:
            if any(m.lower() in haystack for m in markers):
                drop = True
                break
        if not drop:
            out.append(r)
    return out


async def _ru_niche_realestate_probe(http: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
    """Parallel DDG site: queries against Russian real-estate niche domains."""
    tasks = [
        _ddg_search(http, f"site:{domain} {query}", k=3)
        for domain in _RU_RE_DOMAINS
    ]
    batches = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[dict[str, Any]] = []
    for batch in batches:
        if isinstance(batch, list):
            results.extend(batch)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in results:
        key = r.get("url", "").lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped[:12]


async def _fallback(query: str, focus: str = "") -> dict[str, Any]:
    """Live-web fallback: Firecrawl search+scrape → DDG SERP + fetch → Claude synth."""
    from llm import call_text

    try:
        async with httpx.AsyncClient(timeout=90) as http:
            wiki_task = asyncio.create_task(_wikipedia_search(http, query, k=4))
            hn_task = asyncio.create_task(_hn_algolia_search(http, query, k=4))
            # RU niche real-estate sources — first shot before generic providers
            niche_items: list[dict[str, Any]] = []
            if _RU_RE_KEYWORDS.search(f"{query} {focus}"):
                niche_items = await _ru_niche_realestate_probe(http, query)
            brave = await _brave_search(http, query, k=6)
            if brave:
                results = brave
                pages = await asyncio.gather(*[_fetch_page(http, r["url"]) for r in results[:5]])
                source_tag = "brave+jina+claude"
            else:
                fc = await _firecrawl_search(http, query, k=6)
                if fc:
                    results = fc
                    pages = [r.get("body", "") for r in fc]
                    source_tag = "firecrawl+claude"
                else:
                    js = await _jina_search(http, query, k=6)
                    if js:
                        results = js
                        pages = [r.get("body", "") for r in js]
                        source_tag = "jina-search+claude"
                    else:
                        results = await _ddg_search(http, query, k=6)
                        pages = (
                            await asyncio.gather(*[_fetch_page(http, r["url"]) for r in results[:5]])
                            if results else []
                        )
                        source_tag = "ddg+jina+claude" if results else "wiki-only+claude"
            if niche_items:
                results = list(niche_items) + list(results)
                pages = [n.get("body", n.get("snippet", "")) for n in niche_items] + list(pages)
                source_tag = "ru-niche+" + source_tag
            wiki_items, hn_items = await asyncio.gather(wiki_task, hn_task)
            if hn_items:
                results = list(hn_items) + list(results)
                pages = [h.get("body", "") for h in hn_items] + list(pages)
                source_tag = source_tag + "+hn"
            if wiki_items:
                results = list(wiki_items) + list(results)
                pages = [w.get("body", "") for w in wiki_items] + list(pages)
                source_tag = source_tag + "+wiki"
            if not results:
                return {"text": f"[fallback: no results for '{query}']",
                        "citations": [], "query": query, "fallback": True}

        corpus_parts: list[str] = []
        citations: list[dict[str, str]] = []
        for i, (r, body) in enumerate(zip(results, list(pages) + [""] * (len(results) - len(pages))), 1):
            citations.append({"url": r["url"], "title": r["title"]})
            chunk = body or r.get("snippet", "")
            corpus_parts.append(f"[{i}] {r['title']} — {r['url']}\n{chunk}")
        corpus = "\n\n---\n\n".join(corpus_parts)[:30000]

        system = (
            "You are a research analyst. Synthesize a dense, fact-rich answer to the user's query "
            "using ONLY the provided web sources. Cite sources inline as [n] matching the numbered list. "
            "Prefer concrete numbers, dates, named entities. If sources disagree, say so. "
            "Russian output if the query is in Russian."
        )
        user = f"Query: {query}\n\nWeb sources:\n{corpus}\n\nWrite the synthesis now."
        text = await call_text(
            model=settings.scout_model,
            system=system,
            user=user,
            temperature=0.2,
            max_tokens=3000,
        )
        return {
            "text": text,
            "citations": citations,
            "query": query,
            "fallback": source_tag,
        }
    except Exception as err:
        return {"text": f"[search+fallback failed: {err}]", "citations": [], "query": query}


async def _perplexity_raw(query: str) -> dict[str, Any] | None:
    """Pure Perplexity call — no composition, no fallback. Returns None on failure."""
    if not settings.perplexity_api_key:
        return None
    payload = {
        "model": perplexity_model_for(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a research assistant. Answer the user's query with concrete facts, "
                    "numbers and named sources. Prefer primary sources (official statistics, "
                    "regulators, peer-reviewed, company filings). Keep it dense, no fluff."
                ),
            },
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.perplexity_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=90) as http:
        for attempt in range(3):
            try:
                r = await http.post(PPLX_URL, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                citations = data.get("citations") or data.get("search_results") or []
                account_provider("perplexity", _pplx_cost())
                return {"text": text, "citations": citations, "query": query, "source_db": "perplexity"}
            except (httpx.HTTPError, KeyError):
                if attempt == 2:
                    return None
                await asyncio.sleep(1.5 * (attempt + 1))
    return None


async def _gpt_researcher_call(query: str) -> dict[str, Any] | None:
    """Call gpt-researcher backend if installed. Lazy import so a missing dep doesn't break prod."""
    try:
        from search_gptr import gpt_researcher_search
    except ImportError:
        log.warning("search: gpt_researcher backend enabled but search_gptr missing")
        return None
    try:
        res = await gpt_researcher_search(query)
        if not res.get("text") or res.get("fallback") == "gpt_researcher_failed":
            return None
        res["source_db"] = "gpt_researcher"
        return res
    except Exception as err:
        log.warning("search: gpt_researcher error: %s", err)
        return None


async def _web_only(query: str) -> dict[str, Any]:
    """Perplexity-only pipeline (no academic bundle). Same fallback chain."""
    pp = await _perplexity_raw(query)
    if pp is not None:
        pp["academic_items"] = []
        return pp
    if settings.use_tavily:
        tav = await _tavily_search(query)
        if tav is not None:
            tav["academic_items"] = []
            return tav
    fb = await _fallback(query)
    fb["academic_items"] = []
    fb.setdefault("source_db", fb.get("fallback") or "cheap_web")
    return fb


async def search(query: str, focus: str = "general", search_type: str = "both") -> dict[str, Any]:
    """Run one search query. Routes by search_type: web | academic | both. Returns {text, citations, academic_items}."""
    t0 = time.time()
    try:
        result = await _search_impl(query, focus, search_type)
    except Exception as err:
        log.error("search FAIL type=%s q=%r after %.1fs: %s", search_type, query[:80], time.time() - t0, err)
        raise
    log.info(
        "search ok type=%s %.1fs cites=%d acad=%d q=%r",
        search_type, time.time() - t0,
        len(result.get("citations") or []),
        len(result.get("academic_items") or []),
        query[:80],
    )
    return result


async def _academic_branch(query: str, focus: str) -> tuple[str, list[dict[str, str]], list[dict[str, Any]]]:
    """Run academic stack if enabled. Returns (text, citations, items) or ("", [], [])."""
    if not settings.use_academic:
        return "", [], []
    items = await _academic_fetch_all(query)
    items = filter_irrelevant(items, query, focus)
    text, cites = _academic_bundle_from_items(items)
    return text, cites, items


async def _search_impl(query: str, focus: str, search_type: str) -> dict[str, Any]:
    """Composable multi-backend search. Each backend is gated by its own settings flag.
    Runs enabled backends in parallel and concatenates their output. The bench harness
    toggles flags at runtime to isolate individual backends."""
    # Academic-only shortcut keeps the old contract for search_type='academic' callers.
    if search_type == "academic":
        text, cites, items = await _academic_branch(query, focus)
        if not items:
            return {"text": f"[no academic results for '{query}']", "citations": [],
                    "query": query, "academic_items": [], "source_db": "academic_empty"}
        return {"text": text, "citations": cites, "query": query,
                "academic_items": items, "source_db": "academic"}

    include_academic = (search_type == "both") and settings.use_academic
    web_tasks: list[tuple[str, Any]] = []
    if settings.use_perplexity and settings.perplexity_api_key:
        web_tasks.append(("perplexity", _perplexity_raw(query)))
    if settings.use_gpt_researcher:
        web_tasks.append(("gpt_researcher", _gpt_researcher_call(query)))
    if settings.use_tavily and settings.tavily_api_key:
        web_tasks.append(("tavily", _tavily_search(query)))

    academic_coro = _academic_branch(query, focus) if include_academic else None
    gathered = await asyncio.gather(
        *(coro for _, coro in web_tasks),
        academic_coro if academic_coro is not None else asyncio.sleep(0, result=("", [], [])),
        return_exceptions=True,
    )
    web_results = list(gathered[:-1])
    academic_text, academic_cites, academic_items = gathered[-1] if include_academic else ("", [], [])

    text_parts: list[str] = []
    all_citations: list[dict[str, str]] = []
    source_dbs: list[str] = []
    if academic_text:
        text_parts.append(academic_text)
        all_citations.extend(_normalize_citations(academic_cites))
        source_dbs.append("academic")
    for (label, _coro), res in zip(web_tasks, web_results):
        if isinstance(res, Exception) or not isinstance(res, dict):
            continue
        txt = (res.get("text") or "").strip()
        if not txt:
            continue
        text_parts.append(f"=== WEB SYNTHESIS ({label.upper()}) ===\n{txt}")
        all_citations.extend(_normalize_citations(res.get("citations")))
        source_dbs.append(res.get("source_db") or label)

    if text_parts:
        return {
            "text": "\n\n".join(text_parts),
            "citations": filter_irrelevant(all_citations, query, focus),
            "query": query,
            "academic_items": academic_items,
            "source_db": "+".join(source_dbs) or "composite",
        }

    # No primary backend produced text — fall back to cheap-web chain if allowed.
    if settings.use_cheap_web:
        fb = await _fallback(query, focus)
        fb["citations"] = filter_irrelevant(
            _normalize_citations(academic_cites) + _normalize_citations(fb.get("citations")),
            query, focus,
        )
        if academic_text:
            fb["text"] = f"{academic_text}\n\n=== WEB SYNTHESIS (cheap_web) ===\n{fb.get('text','')}"
        fb["academic_items"] = academic_items
        fb.setdefault("source_db", fb.get("fallback") or "cheap_web")
        return fb
    return {
        "text": academic_text or f"[no backend enabled returned results for '{query}']",
        "citations": academic_cites,
        "query": query,
        "academic_items": academic_items,
        "source_db": "empty",
    }
