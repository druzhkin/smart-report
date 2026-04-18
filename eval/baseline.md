# Baseline Eval — 3 reference reports × 5 metrics

**Date:** 2026-04-18 · **Track:** C · **Judge:** `anthropic/claude-sonnet-4.6` via OpenRouter (temperature 0) · **Cost:** ~$1.08 · **Calls:** 15

## What these metrics measure and why

The question all three reports try to answer is: **"Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?"** A good report should (a) actually cover the question's subdomains with specifics, (b) back numeric claims with real sources, (c) be transparent about what it doesn't know, (d) avoid banalities, and (e) connect domains through named mechanisms rather than handwaving. Five metrics cover these axes:

1. **Coverage (0–10)** — how many of 10 relevant domains are actually addressed with real facts (not "no data"): `product, brand, speed, macro-finance, buyer, regulation, competition, location, build-discipline, service`.
2. **Groundedness (0–100%)** — share of sampled numeric claims that have an attached source + plausible value. Spot-check via WebFetch on 2–3 URLs per report.
3. **Honesty (0–100)** — balance between explicit "no data" admissions and unsourced numeric claims presented as fact. Both extremes (too few admissions OR too many without content) are penalized.
4. **Non-triviality (raw count of platitudes — LOWER is BETTER)** — "сильный бренд важен" / "скорость без качества разрушает репутацию" type statements. Absolute count.
5. **Cross-domain insight (raw count — HIGHER is BETTER)** — connections between domains where the shared variable is **explicitly named** (e.g. "key rate → project financing cost → build speed"), not vague co-occurrence.

The 4th column `Smart Report v3` was filled on 2026-04-18 after a live smoke on the same reference question (run `20260418T070420Z`, `PERPLEXITY_MODEL=sonar-pro`, Track B winner).

## Scores

| # | Metric | Perplexity | OpenAI DR | Smart Report v2 | Smart Report v3 |
|---|---|---:|---:|---:|---:|
| 1 | **Coverage** (0–10, higher better) | 7 | **10** | 1 | 7 |
| 2 | **Groundedness** (0–100, higher better) | 80 | 80 | 5 | **90** |
| 3 | **Honesty** (0–100, higher better) | **82** | 72 | 52 | 78 |
| 4 | **Non-triviality** (count of trivialities, LOWER better) | **5** | 7 | 18 | **5** |
| 5 | **Cross-domain links** (count, higher better) | 5 | **9** | 4 | 2 |

**Bolded** = current best. v2 is dominated on every axis. v3 takes groundedness outright and ties Perplexity on non-triviality — but regresses on cross-domain (only 2 bisociations emitted).

## Per-cell commentary

### 1 · Coverage

- **Perplexity = 7**. Covers product, brand, speed, macro-finance, competition, location, build-discipline, regulation with real numbers. Missing: `buyer` (no concrete demographic breakdown) and `service` (post-handover service not mentioned).
  *Evidence: «Ставки по проектному финансированию выросли с 6% до 10% годовых… MR Group поднялась с 5-го на 3-е место по объёму ДДУ в Москве».*
- **OpenAI DR = 10**. All 10 domains covered with specifics — including `buyer` (семьи 34–44 лет, 74% родители) and `service` (цифровая платформа Shagal+МТС, Sminex топ-3 УК).
  *Evidence: «у Группы «Эталон» в московском портфеле 292 245 кв. м текущего строительства, из которых 35,46% шли с переносом срока».*
- **Smart Report v2 = 1**. Only `location` has one concrete number (Perovo housing fund, 2243.8k m², 20.2 m²/person) — and even that is general district data, not business-class. Every other domain is "данные отсутствуют" + speculative ranges.
  *Evidence: the only concrete number in the whole 180K-char report is about Perovo housing fund from Wikipedia.*
- **Smart Report v3 = 7**. Covers macro-finance, buyer (partially), competition, location, regulation, build-discipline (as empty gap), operational-efficiency — 7 of 10 domains with hard numbers. Missing as concrete: `product` (planning-standards only touches ceiling-height, 3m), `brand` (only rankings, no NPS/repeat-purchase), `speed` (sales-velocity but no per-developer breakdown), `service` (absent). The build-discipline cell is honest-empty (scout got irrelevant mintrans material, see calibration §6).
  *Evidence: «доля ипотечных сделок на первичном рынке бизнес-класса Москвы за 2024 год сократилась с 65% до 32%»; «топ-5 девелоперов по выручке (ПИК, Донстрой, MR Group, Level Group, ЛСР) контролируют 66,9% сделок по ДДУ».*

### 2 · Groundedness

- **Perplexity = 80**. Most numeric claims link to real sources (RBC, Nikoliers, MR Group, Est-a-Tet). A few "более половины покупателей", "бюджет 25–30 млн руб." are delivered without inline cites.
  *Evidence: «57,2% квартир, проданных в новостройках внутри МКАД в III кв. 2025… источник: realty.rbc.ru/news/68ed17159a7947d8c8256134» — verified via WebFetch.*
- **OpenAI DR = 80**. Sources named (Метриум, Росреестр, ЕРЗ.РФ, CORE.XP, Ромир) but many references are `citeturnXX` internal tags, not verifiable URLs. Numbers plausible.
  *Evidence: «71 796 ипотечных ДДУ в 2024; доля 52,4% — источник Росреестр».*
- **Smart Report v2 = 5**. One real source (Wikipedia on Perovo). Everything else is "[число удалено]" placeholders or speculative coefficients without sources, or irrelevant physics arXiv links.
  *Evidence: «Площадь жилищного фонда в районе Перово — 2243,8 тыс. м² [Wikipedia, 2024] — единственное конкретное число с источником».*
- **Smart Report v3 = 90**. Every numeric claim carries an inline URL, and those URLs resolve to real metrium/novostroy/stroygaz/uawards/fontanka pages with the exact figures quoted (spot-checked 5/5 verbatim — see §6). The 10-point drop-off from 100 reflects a few "[N]" perplexity-style citation tokens that leaked into scout output and some mixed-segment numbers (e.g. 37% installment share admits it mixes бизнес+премиум).
  *Evidence: «Доля ипотечных сделок на первичном рынке бизнес-класса Москвы за 2024 год сократилась с 65% до 32%» — verified verbatim on `metrium.ru/news/detail/itogi-2024-goda-…` via WebFetch.*

### 3 · Honesty

- **Perplexity = 82**. High factual density, no fabrication — but also almost no explicit admission of uncertainty. Forecasts like "дефицит к 2027" are presented without confidence caveats.
  *Evidence: «По оценке Nikoliers… дефицит нового предложения» — подано как прогноз без оговорки о неопределённости.*
- **OpenAI DR = 72**. Several excellent explicit limitations (no public margin data, no regression possible, geography limited to Old Moscow). Offset by confident 45/30/25% weighting and "с 65% до 32%" mortgage shift without inline source.
  *Evidence: «Строгую регрессионную модель из открытых данных построить нельзя: нет единой публичной панели developer–project–month».*
- **Smart Report v2 = 52**. Dozens of "отсутствуют данные" admissions BUT simultaneously invents ranges (2,25–9,75%, 0,5–0,65 coefficients, +5% price premium) delivered as outputs, not flagged as speculation at the same strength. Admission-heavy but content-empty.
  *Evidence: «Ожидаемое снижение рентабельности… лежит в диапазоне 3%... коэффициент переноса с международных данных 0.6-0.7» — presented as conclusion despite declared data absence.*
- **Smart Report v3 = 78**. Every cell carries an explicit `Gap:` block listing exactly what's missing (per-developer breakdowns, HHI, NPS, м² by stage of readiness). Two cells (`buyer/family-profile`, `construction/deadline-discipline`) honestly admit the scout returned unusable material rather than fabricating. 4 points below Perplexity because v3 occasionally lets a mixed-segment figure (37% installment share) sit in the findings without the caveat repeated at the conclusion level.
  *Evidence: «Данных по соблюдению сроков ввода объектов бизнес-класса в Москве не обнаружено. Scout принёс нерелевантный материал…» — explicit null rather than invented.*

### 4 · Non-triviality (LOWER = better)

- **Perplexity = 5**. Predominantly concrete; platitudes appear mostly in the final synthesis.
  *Evidence: «Скорость без качества разрушает репутацию»; «Бренд без качественного продукта теряет лояльность».*
- **OpenAI DR = 7**. Low given the length (28K chars). Some banalities slip in near transitions.
  *Evidence: «бренд ускоряет первичную конверсию»; «маркетинг всё чаще выступает продолжением продукта».*
- **Smart Report v2 = 18**. Platitudes are the main content. Every block includes a "_is critically important_" framing without evidence.
  *Evidence: «сильный бренд девелопера может обеспечивать ценовую премию»; «качество и уникальность продукта являются основой для привлечения».*
- **Smart Report v3 = 5**. The matrix-per-cell format (Conclusion / Strongest number / Gap / Findings with sources) forces every assertion to be either a cited fact or an explicit gap. Platitudes appear only in the two cross-link narrative strings.
  *Evidence: conclusions carry numbers or null-admissions; no "сильный бренд важен" type sentences survive the structure.*

### 5 · Cross-domain links (named-variable)

- **Perplexity = 5**. Most links pivot on key rate / project financing / supply shortage.
  *Evidence: «Ставки ПФ 6%→10% делает каждый месяц стройки дороже» — ties macro-finance ↔ speed via named variable (ставка ПФ).*
- **OpenAI DR = 9**. Richer mesh: family 2+ rooms deficit (product↔buyer), mortgage share drop (macro↔buyer), ЕРЗ transfer share (speed↔brand trust), etc.
  *Evidence: «74% родителей ищут 2+ комнат, доля таких лотов упала до 49,1% с 63,1%» — product↔buyer via named shared variable (дефицит 2+ комнат).*
- **Smart Report v2 = 4**. Of 10 self-declared cross-links, only 4 name a real variable. Others use "absence of data" as a pseudo-variable or tie a domain to itself (Architecture ↔ Infrastructure, both inside "Product").
  *Evidence: «Ключевая ставка ЦБ → удорожание заёмных средств → задержка 6 мес снижает рентабельность на 5%» — macro ↔ speed, valid.*
- **Smart Report v3 = 2**. Both links name real shared variables (`чувствительность к финансовым условиям покупки` and `цена м² (₽/м²)`) — no pseudo-variables, no self-links. But the bisociator only emits 2 despite a 14-cell matrix (~91 pair space), which is a serious shortfall vs OpenAI DR's 9. Diagnosis: bisociator was given 14 rich cells and returned only two — the architectural ceiling is clearly higher. Needs a pass over its selection prompt or a top-K enforcement.
  *Evidence: «Падение доли ипотеки до 32% означает, что покупатель бизнес-класса оплачивает вход преимущественно собственными средствами — это превращает репутацию застройщика из маркетингового атрибута в финансовую гарантию сохранности денег» — macro-finance ↔ buyer via named variable (чувствительность к финансовым условиям). Valid.*

## Calibration — 3 cells manually verified

See `scripts/baseline_eval/manual_checks.md` for full notes. Summary:

1. **Perplexity × groundedness = 80%.** Spot-checked 2 cited URLs via WebFetch. `realty.rbc.ru/news/68ed17159a7947d8c8256134` verbatim contains "57,2%" and "23,2% год к году (+7,7%)". `nikoliersdom.ru/...deficita...` verbatim contains "не ранее 2028 года". 2/2 PASS. Judge calibrated.

2. **v2 × coverage = 1/10.** Manually confirmed by full read of lines 1–550 (out of 644) plus grep: 64 hits of "отсутств/нет данных" in v2 vs 1 in Perplexity vs 2 in OpenAI DR. The only concrete number in the entire report is about Perovo district housing fund — general, not business-class. 1/10 is correct.

3. **v2 × honesty = 52 (bonus check).** Verified v2 simultaneously admits "data absent" AND outputs unsourced coefficients as findings (e.g. line ~126: brand premium 5%, speed reduction 10%, translation 0.6–0.7 — all presented as conclusions). Judge correctly penalized the "honest about the gap, then invent anyway" pattern.

4. **v3 × groundedness = 90% (2 URLs, 5 claims).** Spot-checked via WebFetch on 2026-04-18. `metrium.ru/news/detail/itogi-2024-goda-na-pervichnom-rynke-biznesklassa-staroy-moskvy/` verbatim contains "с 65% до 32%" and "сократилась на 34 п.п. и составила 36%". `novostroy-m.ru/analitika/biznesklass_u_metro_okt2024` verbatim contains "96 комплексов бизнес-класса", "69,6%", "463,2 тысяч рублей", "Level Академическая… 50 м". 5/5 PASS. Judge's 90 is credible — even the 10-point penalty may be slightly harsh, since all sampled claims verified.

5. **v3 × coverage = 7/10 (manual per-cell pass).** Read all 14 cells. 10/14 are strongly grounded (macro-finance/mortgage-mix, macro-finance/installment-terms, location/infrastructure, location/redevelopment, competition/brand-trust, competition/market-share, regulation/parking-norms, regulation/planning-standards, operational-efficiency/sales-velocity, operational-efficiency/price-premium). 2/14 are partial (`buyer/decision-factors` qualitative only, `construction/escrow-turnover` generic all-Russia number). 2/14 are honest-empty (`buyer/family-profile` mangled scout output, `construction/deadline-discipline` scout returned irrelevant mintrans material). The empty `construction/deadline-discipline` cell is the exact cell OpenAI DR nailed with "35,46% переноса у Эталона" — signal (a) from the handoff FAILED (0/5 developers have transfer-delay numbers). Root cause: Planner emitted `target_sources=["ЕРЗ.РФ", "наш.дом.рф", "Мосгосстройнадзор"]` — Cyrillic display names, not TLDs. New `_filter_to_domains` correctly stripped them, but that left Scout without any domain hint → irrelevant result.

6. **v3 × cross-domain = 2 (matches signal (c) but below expectation).** Signal (c) from the handoff asked whether bisociator returns links through named variables vs. "нет данных" fallback. ✅ PASS on quality (both links name a real shared variable). ❌ FAIL on quantity (2 vs 14-cell matrix → ~91 available pairs). Bisociator prompt underselects.

**Verdict:** judge still well-calibrated; numbers usable as targets. **Morning TODO:** fix Planner's `target_sources` to request actual TLDs (not display names), and audit bisociator prompt for selection rate.

## Bias disclosures (confounders)

- **Length asymmetry.** Perplexity is ~17K chars, OpenAI DR ~28K, v2 ~181K (truncated to 105K for judge context). Non-triviality is an absolute count, so longer reports can show more trivialities without worse density — caveat v2's 18. Coverage and cross-domain also scale slightly with length.
- **v2 truncation.** We truncated v2 middle (~76K chars dropped, head + tail kept). v2 is template-driven and the remaining content is structurally representative, but we may have missed a concrete number somewhere. Lower bound on coverage is 1, could be up to ~2.
- **Groundedness sampling.** The judge samples up to 10 claims; I independently verified 2 URLs. Extrapolation to 10 claims from 2 successful checks has a wide CI. Additional manual verification should land before we trust v3 groundedness scores.
- **OpenAI DR's `citeturn` tags.** Not resolvable URLs — they're internal ChatGPT research markers. The judge correctly didn't punish these as "no source" because organizations were named, but they're less verifiable than Perplexity's raw URLs.
- **Judge self-consistency.** Single-pass, temperature 0, so stable on re-run within ±1 for counts. Multi-pass ensemble would be more robust but was outside the $3 budget.

## Honest summary

- **OpenAI DR wins on: Coverage (10/10), Cross-domain insight (9).**
- **Perplexity wins on: Honesty (82).** Shorter, tighter, everything has a URL. Ties v3 on non-triviality (5).
- **Smart Report v3 wins on: Groundedness (90).** Structural forcing function (Conclusion / Strongest number / Gap / Findings) keeps every claim cited or explicitly null. Also ties Perplexity on non-triviality.
- **Smart Report v2 wins on: nothing.** It loses every metric, often by large margins. It's a pure anti-pattern corpus — the "honest about gaps" defense is punctured by the honesty score itself (52), because v2 admits data absence and THEN hallucinates coefficients anyway.

### v3 hit-rate vs the 3 handoff diagnostic signals

- **(a) Scout finds ЕРЗ transfer-delay numbers for ≥2 of 5 developers.** ❌ FAIL. 0/5. Root cause is upstream of scout: Planner emits Cyrillic display-name `target_sources` (`ЕРЗ.РФ`, `наш.дом.рф`), `_filter_to_domains` strips them as non-TLD, Scout runs without a domain hint and Perplexity returns an irrelevant mintrans.gov.ru infrastructure report.
- **(b) Planner matrix includes ≥1 cell outside {product, brand, speed}.** ✅ PASS, strongly. Matrix has 7 orthogonal domains × 14 cells (macro-finance, buyer, construction, location, competition, regulation, operational-efficiency).
- **(c) Bisociator returns links through named variables, not "нет данных".** ✅ PASS on quality (2/2 links name a real shared variable) but ❌ FAIL on quantity (2 vs ~91-pair space). Prompt underselects.

### Practical morning targets

- **Fix Planner `target_sources` contract**: emit actual TLDs (`erzrf.ru`, `dom.rf`, `stroi.mos.ru`) instead of display names. Unblocks signal (a) directly.
- **Audit bisociator prompt**: force top-K selection over the full pair space, not a free-form emission. Target ≥9 links to match OpenAI DR.
- **Cover missing domains** (`product`, `brand`, `speed`, `service`) to break through Coverage=10. Currently dispersed across adjacent cells but not called out as first-class domains — a Planner prompt change.
- **Practical target for v3**: beat OpenAI DR on Coverage (>10 requires adding a new domain), hold Groundedness≥85, beat Perplexity on Honesty (>82) while holding non-triviality ≤5, and exceed OpenAI DR on Cross-domain (>9).

## Iteration log (post-baseline)

Initial `Smart Report v3` column above was scored on **smoke 04** (run `20260418T070420Z`). Subsequent smokes revealed that the groundedness=90 figure was partly inflated by **fabricated URLs inside Sonar-pro's JSON body** — the model invents plausible paths like `irn.ru/news/2024-03-15/defekty-v-novostroykakh-moskvy-2023.html` that pass a surface-level judge check but don't resolve. The fix discipline landed three correctness improvements that trade score-board prettiness for honest output:

| smoke | commit at HEAD                                        | cov | ground | hon | nontriv | cross | notes |
|:-----:|:-----------------------------------------------------:|:---:|:------:|:---:|:-------:|:-----:|:------|
| 04    | `1175635` (baseline)                                  | 7   | **90** | 78  | 5       | 2     | Sonar URLs fabricated but well-formed, judge couldn't tell |
| 05    | `d18a88e` (Planner emits real TLDs)                   | 7   | 55     | 72  | 3       | 4     | Richer retrieval on `erzrf.ru/dom.rf/cbr.ru`; Analyst still forwarded Sonar's fabricated URLs |
| 06    | `c40a6f1` (code-fence strip + URL↔citation reconcile) | —   | —      | —   | —       | 0     | Aborted: Sonar-deep-research `.env` override (line 22 shadowing line 8) caused 13/14 cells to return `<think>` reasoning instead of JSON |
| 07    | `546c0d1` (`<think>` strip + citation salvage + .env) | 7   | 62     | 72  | 4       | 2     | Sonar-pro reinstated; 12/14 clean JSON parses, 2 citation-salvage placeholders; 2 cross-links on real data (387–583 k₽/m² locational spread; котлован vs готовое 9.7% discount) |

**What changed in the pipeline (upstream-first order):**
1. **Planner TLD contract** (`d18a88e`, `prompts/planner.md` rule 6 + 15-row mapping table): `target_sources` now always contains ASCII TLDs Perplexity's `search_domain_filter` accepts.
2. **URL↔citation reconciliation** (`c40a6f1`, `smart_report/search.py`): findings whose `source_url` is not in Perplexity's returned `citations` array get pinned to the first citation and downgraded to `source_type=other`. Code-fence stripping for ```json wrappers. `citations[]` now logged alongside `results[]` for audit.
3. **`<think>` handling + citation salvage** (`546c0d1`, same file): strip `<think>...</think>` blocks before JSON parse; when parse fails but retrieval returned ≥3 citations, emit one placeholder per top-5 citation so Analyst works with real URLs instead of a raw-text blob.
4. **`.env` cleanup**: commented out stale `PERPLEXITY_MODEL=sonar-deep-research` override at line 22 that shadowed the intended `sonar-pro` (commit `08f8943`). Dotenv's last-value-wins semantics had silently activated the reasoning model.

**Reading the regression honestly.** Smoke 04's groundedness=90 was partly a judging artifact — the judge's URL-spot-check couldn't distinguish a plausible-but-hallucinated path from a real one. Smoke 07 at groundedness=62 reflects a pipeline that ONLY narrates over URLs that Perplexity actually retrieved. Two cells still use placeholder findings because Sonar-pro returned prose instead of JSON for them; this is a Perplexity-side instability, not a pipeline bug, and the citation-salvage path at least preserves retrieval signal for the Analyst to acknowledge.

**Cross-domain dynamics.** 4→2 between smokes 05 and 07 is not a Bisociator regression — smoke 05's 4 links were partly built on Sonar-fabricated numbers (e.g., a `1990%` margin artifact that looked like a striking paradox). Smoke 07's 2 links both rest on real, verifiable numbers from Metrium/Donstroy pages that Perplexity actually cited. Quality traded against count.

**Next-step call:** the upstream-first rule still applies. Before touching Bisociator prompt (to push from 2 toward OpenAI DR's 9), the next bottleneck is Scout density — 7/14 blocks still report `strongest_number=null`. Improving that lifts the shared-variable pool Bisociator ranks over, and then a top-K prompt adjustment has calibrated input to respond to.

| smoke | commit at HEAD                                         | cov | ground | hon | nontriv | cross | notes |
|:-----:|:------------------------------------------------------:|:---:|:------:|:---:|:-------:|:-----:|:------|
| 08    | (stricter prompt — "return [] if nothing relevant")    | —   | —      | —   | —       | —     | **Regression**: 9/14 null sn (from 7), 9 cells emitted empty arrays. Prompt permission was abused. |
| 09    | `c9b4417` (balanced prompt, no "return []" permission) | —   | —      | —   | —       | 3     | **3/14 null sn** (-57% vs smoke 07); 0 prose-salvage; 3 cross-links all on real variables (эскроу↔sales, market-share↔redevelopment, brand↔velocity) |

**Density fix (commits `ea6fa75` + `c9b4417`).** Two separate Scout-side improvements landed after smoke 07:
- `ea6fa75`: zero-citation fabrication drop. When Perplexity retrieval returns 0 sources but Sonar still emits plausible JSON, collapse to a single honest no-retrieval marker instead of forwarding fabrications (bug was visible in smoke 07 `quality-control` cell: 0 citations, 5 invented URLs passed through).
- `c9b4417`: tightened system prompt. Explicit "JSON only — no prose, no fences, no <think>" plus "prefer surfacing partial/approximate data over returning nothing" and "emit one finding per retrieved source that's topically relevant". Previous wording was too terse and let Sonar drift into prose-salvage when the exact metric was absent.

**Honest caveat on signal (a).** ЕРЗ transfer-delay numbers: smoke 07's `deadline-discipline` hit 10 `erzrf.ru` citations (including the ratings methodology page) but in prose mode — numbers lost. Smoke 09's retrieval for the same cell returned **zero** citations, triggering the fabrication collapse. Perplexity retrieval on that specific query is non-deterministic; the ЕРЗ-numbers-per-developer signal remains blocked on a Firecrawl-style HTML extractor pass over known-good citation pages, not on prompt tuning.

**Signals (b) and (c) green on smoke 09.** Matrix includes `redevelopment-zones`, `parking-norms`, `planning-approvals`, `sales-velocity`, `margin-structure` — all outside `{product, brand, speed}`. All 3 Bisociator cross-links connect cells through named numeric variables (объём эскроу ↔ объём продаж; доля бизнес-класса ↔ доля редевелопмента; концентрация топ-10 ↔ объём продаж), not via topical surface matching.

| smoke | commit at HEAD                                                    | cov | ground | hon | nontriv | cross | notes |
|:-----:|:-----------------------------------------------------------------:|:---:|:------:|:---:|:-------:|:-----:|:------|
| 10    | `69878bd` (ERZ extraction via Jina Reader, orchestrator enrichment) | —   | —      | —   | —       | **4** | **Signal (a) GREEN**: `construction/deadline-discipline` strongest_number = `68,05% (Самолёт)`, 10 per-developer ЕРЗ findings (ПИК 4.09% / Самолёт 68.05% / ДОНСТРОЙ 0% / ФСК 11.39% / …). 2 of 4 cross-links fire directly off the new ЕРЗ material (паradox ДОНСТРОЙ 0% vs ПИК 4.09% vs sales-rankings; unexpected-confirmation Самолёт 68.05% × 8.84 мес. vs sales-velocity). Null sn: 4/14 (vs 3/14 on 09, within noise). |

**Targeted extraction unblocks signal (a) without Planner surgery.** Firecrawl key was out of credits (402) — used Jina Reader (`r.jina.ai/`) instead: free, no key, renders JS, stable markdown on erzrf.ru. New module `smart_report/scrape.py` exposes `fetch_erz_moscow_developer_rows` + `erz_rows_as_findings`. Orchestrator enrichment is gated (target_sources contains `erzrf.ru` AND query mentions `срок/перенос/ввод`) and failure-soft (exceptions logged as `kind=scrape_error`, returns `[]`, pipeline degrades to pure-Perplexity output). A regex contract test (`tests/test_scrape_erz.py`) pins ПИК and Самолёт row-parse so a ЕРЗ template change fails loudly instead of silently emptying the enrichment.

**On the organic Bisociator lift.** Smoke 09's 3 links → smoke 10's 4 links is the cheapest possible improvement: no prompt tuning, just richer Scout material. Both new links use the per-developer numeric spread as the shared variable, which would not have existed without the scrape. Confirms the "upstream-first" ordering: prompt-tuning Bisociator before Scout had good data would have forced synthetic cross-links; widening the input surface pulled real ones out for free.

**Deferred (not fixed this iteration).** Teaching the Planner to tag cells as "search" (Perplexity) vs "extract from known URL" (Firecrawl/Jina). Current orchestrator gate is hardcoded to ЕРЗ Moscow. Generalising to an extractor registry (per-cell `extract_targets: [{url, parser}]` in Matrix) is a follow-up once a second high-value URL (e.g., дом.рф reporting, Росреестр ДДУ dashboard) justifies the abstraction.
