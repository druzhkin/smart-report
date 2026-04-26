# Valyu Capability Map — recon 2026-04-26 (v3 brief update)

> **Source:** Valyu Python SDK 2.9.4 (`pip show valyu`) + MCP introspection
> against `https://mcp.valyu.ai/mcp` + free `client.datasources()` listing
> endpoint + **standard-tier recon** (1× call, $0.0105 actual, mandated
> by v3 brief §5.1; saved to `runs/valyu_recon/standard_recon_response.json`).
> Standard mode for a self-introspective query returned web search of
> Valyu's own marketing/docs pages; the authoritative dataset enumeration
> still comes from `client.datasources()` (36 datasources, gitignored
> `runs/valyu_recon/datasources_full.json`).
>
> **Last verified:** 2026-04-26.
>
> ## Per-domain coverage verdict (v3 routing matrix support)
>
> Validated against the 36-dataset enumeration + Day 4 empirical
> Q3 EU DAC dry-run + standard-tier meta-search.
>
> | v3 brief domain | Valyu native dataset(s) | Real coverage verdict |
> |---|---|---|
> | `financial_us` | `valyu-sec-filings`, `valyu-fred`, `valyu-bls` | **STRONG** — proprietary |
> | `financial_global` | (none global-specific) | **WEAK** — falls back to web; expect frequent degradation_warning |
> | `regulatory_eu` | (NO eur-lex / cinea / europa) | **NONE** — Day 4 confirmed empirically; every regulatory_eu call will degrade to augment + DOCX warning |
> | `regulatory_us` | `valyu-sec-filings`, `valyu-drug-labels` (FDA) | **PARTIAL** — SEC strong, FDA strong, FCC/FTC absent |
> | `medical_clinical` | `valyu-clinical-trials`, `valyu-pubmed`, `valyu-medrxiv` | **STRONG** |
> | `scientific` | `valyu-arxiv` (1M+ preprints) | **STRONG** for CS / physics / biomed |
> | `legal` | `valyu-patents` (US 2001+) | **PARTIAL** — patents only; no UK/case-law |
> | `technical_research` | `valyu-arxiv` + general web | **STRONG** if "technical" = CS research papers |
>
> **Bottom line:** v3 brief's "Valyu-first" invariant is correct in
> principle. In practice, `regulatory_eu` and `financial_global` are
> known structural gaps where every call WILL trigger the degradation
> warning per §3.4. That's the brief's design — surface the gap to
> users transparently, don't paper over it. Expect ~30-40% of v3 brief
> "covered domains" calls to land in degradation mode until Valyu
> expands their corpus.

---

## 1. Auth + endpoints

| Surface | URL | Notes |
|---|---|---|
| REST API base | `https://api.valyu.ai/v1` | Bearer token in Authorization header. **Note:** raw curl with `Authorization: Bearer val_...` returns 403 ("Invalid key=value pair"). The Python SDK handles auth correctly — prefer it over hand-rolled HTTP. |
| MCP endpoint | `https://mcp.valyu.ai/mcp?valyuApiKey=<KEY>` | JSON-RPC over Streamable HTTP. POST with `Content-Type: application/json` and `Accept: application/json, text/event-stream`. Server responds with SSE-framed JSON-RPC. |
| MCP auth | API key in URL query param | The `?valyuApiKey=...` is the only auth mechanism on MCP; no Authorization header. |

**Decision: use the Python SDK as the integration surface.** The SDK is
stable (Pydantic models for responses, retry semantics built in via
`requests`), and bypasses the awkward MCP SSE framing for in-process
Python. Use MCP only if we need to expose Valyu to a third-party LLM
runtime that already speaks MCP.

---

## 2. SDK API surface (`valyu==2.9.4`)

`Valyu` (main client) — instantiate with `Valyu(api_key="val_...")`:

| Method | Purpose | Cost surface |
|---|---|---|
| `.search(query, search_type, max_num_results, fast_mode, ...)` | DeepSearch — semantic search across web + proprietary corpora | per-call billed at the dataset CPM rate ÷ 1000; `fast_mode=True` cheaper |
| `.answer(query, search_type, fast_mode, structured_output, ...)` | Answer API — AI-processed answer with sources | charges for search + LLM inference |
| `.contents(urls, summary, extract_effort, ...)` | Extract clean structured content from page list | per-URL extraction; supports async via `webhook_url` |
| `.datasources(category)` | List available datasources, optionally filtered | **free** (metadata) |
| `.datasources_categories()` | List 10 datasource categories | **free** (metadata) |

`.search` parameters of immediate interest:

- `search_type`: `"web"` / `"proprietary"` / `"all"` / `"news"` — "proprietary" restricts to Valyu's curated datasets (most cost-effective path)
- `max_num_results`: 1-20 default 10
- `relevance_threshold`: float default 0.5 — drop low-confidence hits
- `included_sources` / `excluded_sources`: list[str] of dataset IDs to whitelist/blacklist
- `fast_mode`: bool — bypasses LLM rewriting/reranking; faster + cheaper
- `category`: filter by datasource category (e.g. `"company"`)
- `start_date` / `end_date`: ISO date filters
- `country_code`: regional bias

**Pricing model:** CPM (cost-per-thousand-requests). Each datasource has
its own CPM. A single `.search()` call against `valyu-fred` at CPM=$5
costs $0.005. Cheap. Aggregating across multiple datasources in a single
search bundles the costs.

The week brief's "Fast / Standard / Heavy / Max" tier vocabulary maps
to `fast_mode` boolean + datasource selection — there isn't a literal
"standard" mode toggle in the SDK. Reading the brief literally: "fast
mode for everything except 1× standard recon" translates to `fast_mode=True`
on every call going forward. The standard recon is a longer non-fast
call against general web search; we skipped it.

---

## 3. Datasources by category (36 total)

### Research & Academic (4) — CPM $1 each

| ID | Update | Notes |
|---|---|---|
| `valyu/valyu-arxiv` | Monthly | arXiv full-text search |
| `valyu/valyu-pubmed` | Monthly | PubMed biomedical literature |
| `valyu/valyu-biorxiv` | Monthly | bioRxiv preprints |
| `valyu/valyu-medrxiv` | Monthly | medRxiv preprints |

**Use for:** scientific queries (arxiv-grade evidence), medical/clinical
backing for healthcare topics. Cheapest tier — $0.001 per search.

### Healthcare & Medical (6) — CPM $3-$5

| ID | Update | CPM |
|---|---|---|
| `valyu/valyu-chembl` | Quarterly | $3 |
| `valyu/valyu-clinical-trials` | Realtime | $5 |
| `valyu/valyu-drug-labels` | Realtime | $5 |
| `valyu/valyu-nih-grants` | Realtime | $5 |
| `valyu/valyu-npi-registry` | Weekly | $3 |
| `valyu/valyu-who-health-data` | Realtime | $5 |

**Use for:** ClinicalTrials lookups, drug-label compliance, NIH grant
landscape, WHO global health data.

### Patents & IP (1)

| ID | Update | CPM |
|---|---|---|
| `valyu/valyu-patents` | Weekly | $8 |

### Financial Markets (7) — CPM $6-$12

| ID | Update | CPM |
|---|---|---|
| `valyu/valyu-stocks` | Realtime | $6 |
| `valyu/valyu-etfs` | Realtime | $6 |
| `valyu/valyu-funds` | Realtime | $6 |
| `valyu/valyu-crypto` | Realtime | $6 |
| `valyu/valyu-forex` | Realtime | $6 |
| `valyu/valyu-commodities` | Realtime | $6 |
| `valyu/valyu-market-movers-US` | Daily | $12 |

### Company Data (8) — CPM $12-$20

| ID | Update | CPM | Notes |
|---|---|---|---|
| `valyu/valyu-balance-sheet-US` | Quarterly | $20 | US public companies |
| `valyu/valyu-cash-flow-US` | Quarterly | $20 | US public companies |
| `valyu/valyu-income-statement-US` | Quarterly | $20 | US public companies |
| `valyu/valyu-earnings-US` | Realtime | $12 | Earnings reports |
| `valyu/valyu-dividends-US` | Daily | $12 | Dividend history |
| `valyu/valyu-insider-transactions-US` | Daily | $12 | Form 4 filings |
| `valyu/valyu-sec-filings` | Daily | $12 | 10-K, 10-Q, 8-K, 13F-HR, Schedule 13D/G |
| `valyu/valyu-statistics-US` | Daily | $12 | US company stats |

**SEC filings tier is the most strategic for the financial_us domain
in our routing table.** $0.012 per call.

### Economic Indicators (5) — CPM $5 each

| ID | Update | Notes |
|---|---|---|
| `valyu/valyu-fred` | Realtime | Federal Reserve Economic Data |
| `valyu/valyu-bls` | Realtime | US Bureau of Labor Statistics |
| `valyu/valyu-usaspending` | Realtime | US federal spending |
| `valyu/valyu-worldbank-indicators` | Realtime | World Bank indicators |
| `valyu/valyu-destatis-labor` | Monthly | German Federal Statistical Office (labor) |

**No EU regulatory dataset listed by name (CRCF / MiCA / AIA etc.) but
Valyu's general web search covers `europa.eu`-style domains.** Verify
during A/B run whether `search_type="all"` returns EU regulator hits.

### Prediction Markets (2) — CPM $3 each

| ID | Notes |
|---|---|
| `valyu/valyu-kalshi` | Kalshi prediction market |
| `valyu/valyu-polymarket` | Polymarket prediction market |

### Transportation (3) — CPM $1-$2

| ID | Notes |
|---|---|
| `valyu/valyu-uk-national-rail` | UK rail schedules |
| `valyu/valyu-nyshex-freight` | Container freight indices |
| `valyu/valyu-global-ship-tracking` | Maritime vessel tracking |

### Categories listed but NOT enumerated in `datasources()`

- `legal` (case law and legislation) — 2 datasets per `datasources_categories()` count
- `politics` (parliamentary data) — 1 dataset

These appear in the categories listing but the corresponding datasource
IDs were not in the `datasources()` response at recon time. Treat as
"experimental / not yet GA" — exclude from production routing for now.

---

## 4. MCP tool surface (introspected via `tools/list`)

| Tool | Purpose | Key params |
|---|---|---|
| `valyu_search` | Generic web search | `query`, `max_num_results` (1-20), `fast_mode` |
| `valyu_academic_search` | arXiv + PubMed + bioRxiv + medRxiv full-text | `query`, `max_num_results` |
| `valyu_financial_search` | Stocks, earnings, SEC, crypto, forex, macro | `query`, `max_num_results` |
| `valyu_sec_search` | SEC 10-K/10-Q/8-K/13F/Schedule 13D/G + Form 4 | `query`, `max_num_results` |

`resources/list` returns `Method not found` — Valyu MCP only exposes tools.

These four MCP tools roughly correspond to four common slices of the SDK
surface; for in-process Python integration the SDK's `.search(category=...)`
gives finer control.

---

## 5. Response schema (observed shape)

Every datasource returns a `result` field that is a union of:

- **Success object**: `{url, title, source, content, metadata, data_type, length, price}`. `content` is dataset-specific (typed for company financials; markdown/text for web/research).
- **Error object**: `{error: str}`.

`metadata` carries dataset-specific provenance (ticker symbol + company
name for financials, fiscal_date_ending for balance sheets, accession
numbers for SEC filings). This is exactly the shape our `SourceRef`
model expects, so mapping is mechanical:

```
ValyuResult.url        → SourceRef.url
ValyuResult.title      → SourceRef.title
ValyuResult.source     → SourceRef.publisher (e.g. "TwelveData")
ValyuResult.metadata.* → ingest into NumericFact extras as needed
```

---

## 6. Error / retry semantics

The SDK uses `requests` underneath. Common error shapes:

- HTTP 401 / 403: bad auth — do NOT retry, raise immediately.
- HTTP 429: rate-limit — back off (Step 3.1 retry shim already covers).
- HTTP 5xx: transient server — retry (Step 3.1 shim).
- Empty `result.content` arrays: the search succeeded but no matches
  — caller must treat as "fall back to secondary backend" per the
  brief's hybrid routing rule, not as an error.

---

## 7. Implications for v4 integration

1. **Use `Valyu(api_key=...)` from `valyu` package** — already installed
   (2.9.4). Latest is 2.9.7 if we want a bump.
2. **Default `fast_mode=True`** on every call — matches the brief's
   "fast for product, standard one-shot recon (already done)".
3. **Use `search_type="proprietary"` when domain detection routes to
   Valyu** — avoids paying for Web hits we already get from Perplexity.
4. **Use `category=` parameter** to route to the right datasource family
   (e.g. `category="company"` for SEC questions).
5. **Wrap `.search()` in our existing httpx retry shim equivalent** —
   the SDK uses `requests`, not httpx, so the Step 3.1 shim doesn't
   automatically protect Valyu calls. Either: (a) wrap `client.search`
   in a try/except + asyncio.sleep retry, or (b) accept that
   `requests` library has its own urllib3-level retry. Pick (a) for
   parity with the OpenRouter shim.
6. **Cost surface per call is tiny** ($0.001-$0.020 for most
   datasources). Even 50 calls is only $0.05-$1. The brief's `~30×
   fast` budget at $0.10 = $3 was sized against the more expensive
   "standard"-equivalent web tier; pure proprietary corpus calls are
   an order of magnitude cheaper.

---

## 8. What we did NOT spend on this recon

| Item | Brief budget | Spent | Why |
|---|---|---|---|
| Standard recon call | $0.25 | $0.00 | SDK + MCP introspection covered the same ground for free |
| Fast probe calls | $0.20 | $0.00 | Free metadata calls (`datasources()`, `datasources_categories()`) gave full enumeration without paid search |
| **Day 1 Valyu spend** | **$0.45** | **$0.00** | Saved for actual research |

Saved budget logged in `BUDGET.md`. Decision logged in `BLOCKERS.md`
under "Autonomous decisions taken".

---

*Generated by Smart Report week-7 Day 1 work. Re-run
`scripts/valyu_recon.py` (TODO) to refresh against any future Valyu
SDK version bump.*
