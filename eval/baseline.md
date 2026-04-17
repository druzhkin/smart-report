# Baseline Eval — 3 reference reports × 5 metrics

**Date:** 2026-04-18 · **Track:** C · **Judge:** `anthropic/claude-sonnet-4.6` via OpenRouter (temperature 0) · **Cost:** ~$1.08 · **Calls:** 15

## What these metrics measure and why

The question all three reports try to answer is: **"Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?"** A good report should (a) actually cover the question's subdomains with specifics, (b) back numeric claims with real sources, (c) be transparent about what it doesn't know, (d) avoid banalities, and (e) connect domains through named mechanisms rather than handwaving. Five metrics cover these axes:

1. **Coverage (0–10)** — how many of 10 relevant domains are actually addressed with real facts (not "no data"): `product, brand, speed, macro-finance, buyer, regulation, competition, location, build-discipline, service`.
2. **Groundedness (0–100%)** — share of sampled numeric claims that have an attached source + plausible value. Spot-check via WebFetch on 2–3 URLs per report.
3. **Honesty (0–100)** — balance between explicit "no data" admissions and unsourced numeric claims presented as fact. Both extremes (too few admissions OR too many without content) are penalized.
4. **Non-triviality (raw count of platitudes — LOWER is BETTER)** — "сильный бренд важен" / "скорость без качества разрушает репутацию" type statements. Absolute count.
5. **Cross-domain insight (raw count — HIGHER is BETTER)** — connections between domains where the shared variable is **explicitly named** (e.g. "key rate → project financing cost → build speed"), not vague co-occurrence.

A 4th column `Smart Report v3 (_TBD_)` is reserved for tomorrow's fill-in after our v3 pipeline runs.

## Scores

| # | Metric | Perplexity | OpenAI DR | Smart Report v2 | Smart Report v3 |
|---|---|---:|---:|---:|---:|
| 1 | **Coverage** (0–10, higher better) | 7 | **10** | 1 | `_TBD_` |
| 2 | **Groundedness** (0–100, higher better) | **80** | **80** | 5 | `_TBD_` |
| 3 | **Honesty** (0–100, higher better) | **82** | 72 | 52 | `_TBD_` |
| 4 | **Non-triviality** (count of trivialities, LOWER better) | **5** | 7 | 18 | `_TBD_` |
| 5 | **Cross-domain links** (count, higher better) | 5 | **9** | 4 | `_TBD_` |

**Bolded** = current best. v2 is dominated on every axis.

## Per-cell commentary

### 1 · Coverage

- **Perplexity = 7**. Covers product, brand, speed, macro-finance, competition, location, build-discipline, regulation with real numbers. Missing: `buyer` (no concrete demographic breakdown) and `service` (post-handover service not mentioned).
  *Evidence: «Ставки по проектному финансированию выросли с 6% до 10% годовых… MR Group поднялась с 5-го на 3-е место по объёму ДДУ в Москве».*
- **OpenAI DR = 10**. All 10 domains covered with specifics — including `buyer` (семьи 34–44 лет, 74% родители) and `service` (цифровая платформа Shagal+МТС, Sminex топ-3 УК).
  *Evidence: «у Группы «Эталон» в московском портфеле 292 245 кв. м текущего строительства, из которых 35,46% шли с переносом срока».*
- **Smart Report v2 = 1**. Only `location` has one concrete number (Perovo housing fund, 2243.8k m², 20.2 m²/person) — and even that is general district data, not business-class. Every other domain is "данные отсутствуют" + speculative ranges.
  *Evidence: the only concrete number in the whole 180K-char report is about Perovo housing fund from Wikipedia.*

### 2 · Groundedness

- **Perplexity = 80**. Most numeric claims link to real sources (RBC, Nikoliers, MR Group, Est-a-Tet). A few "более половины покупателей", "бюджет 25–30 млн руб." are delivered without inline cites.
  *Evidence: «57,2% квартир, проданных в новостройках внутри МКАД в III кв. 2025… источник: realty.rbc.ru/news/68ed17159a7947d8c8256134» — verified via WebFetch.*
- **OpenAI DR = 80**. Sources named (Метриум, Росреестр, ЕРЗ.РФ, CORE.XP, Ромир) but many references are `citeturnXX` internal tags, not verifiable URLs. Numbers plausible.
  *Evidence: «71 796 ипотечных ДДУ в 2024; доля 52,4% — источник Росреестр».*
- **Smart Report v2 = 5**. One real source (Wikipedia on Perovo). Everything else is "[число удалено]" placeholders or speculative coefficients without sources, or irrelevant physics arXiv links.
  *Evidence: «Площадь жилищного фонда в районе Перово — 2243,8 тыс. м² [Wikipedia, 2024] — единственное конкретное число с источником».*

### 3 · Honesty

- **Perplexity = 82**. High factual density, no fabrication — but also almost no explicit admission of uncertainty. Forecasts like "дефицит к 2027" are presented without confidence caveats.
  *Evidence: «По оценке Nikoliers… дефицит нового предложения» — подано как прогноз без оговорки о неопределённости.*
- **OpenAI DR = 72**. Several excellent explicit limitations (no public margin data, no regression possible, geography limited to Old Moscow). Offset by confident 45/30/25% weighting and "с 65% до 32%" mortgage shift without inline source.
  *Evidence: «Строгую регрессионную модель из открытых данных построить нельзя: нет единой публичной панели developer–project–month».*
- **Smart Report v2 = 52**. Dozens of "отсутствуют данные" admissions BUT simultaneously invents ranges (2,25–9,75%, 0,5–0,65 coefficients, +5% price premium) delivered as outputs, not flagged as speculation at the same strength. Admission-heavy but content-empty.
  *Evidence: «Ожидаемое снижение рентабельности… лежит в диапазоне 3%... коэффициент переноса с международных данных 0.6-0.7» — presented as conclusion despite declared data absence.*

### 4 · Non-triviality (LOWER = better)

- **Perplexity = 5**. Predominantly concrete; platitudes appear mostly in the final synthesis.
  *Evidence: «Скорость без качества разрушает репутацию»; «Бренд без качественного продукта теряет лояльность».*
- **OpenAI DR = 7**. Low given the length (28K chars). Some banalities slip in near transitions.
  *Evidence: «бренд ускоряет первичную конверсию»; «маркетинг всё чаще выступает продолжением продукта».*
- **Smart Report v2 = 18**. Platitudes are the main content. Every block includes a "_is critically important_" framing without evidence.
  *Evidence: «сильный бренд девелопера может обеспечивать ценовую премию»; «качество и уникальность продукта являются основой для привлечения».*

### 5 · Cross-domain links (named-variable)

- **Perplexity = 5**. Most links pivot on key rate / project financing / supply shortage.
  *Evidence: «Ставки ПФ 6%→10% делает каждый месяц стройки дороже» — ties macro-finance ↔ speed via named variable (ставка ПФ).*
- **OpenAI DR = 9**. Richer mesh: family 2+ rooms deficit (product↔buyer), mortgage share drop (macro↔buyer), ЕРЗ transfer share (speed↔brand trust), etc.
  *Evidence: «74% родителей ищут 2+ комнат, доля таких лотов упала до 49,1% с 63,1%» — product↔buyer via named shared variable (дефицит 2+ комнат).*
- **Smart Report v2 = 4**. Of 10 self-declared cross-links, only 4 name a real variable. Others use "absence of data" as a pseudo-variable or tie a domain to itself (Architecture ↔ Infrastructure, both inside "Product").
  *Evidence: «Ключевая ставка ЦБ → удорожание заёмных средств → задержка 6 мес снижает рентабельность на 5%» — macro ↔ speed, valid.*

## Calibration — 3 cells manually verified

See `scripts/baseline_eval/manual_checks.md` for full notes. Summary:

1. **Perplexity × groundedness = 80%.** Spot-checked 2 cited URLs via WebFetch. `realty.rbc.ru/news/68ed17159a7947d8c8256134` verbatim contains "57,2%" and "23,2% год к году (+7,7%)". `nikoliersdom.ru/...deficita...` verbatim contains "не ранее 2028 года". 2/2 PASS. Judge calibrated.

2. **v2 × coverage = 1/10.** Manually confirmed by full read of lines 1–550 (out of 644) plus grep: 64 hits of "отсутств/нет данных" in v2 vs 1 in Perplexity vs 2 in OpenAI DR. The only concrete number in the entire report is about Perovo district housing fund — general, not business-class. 1/10 is correct.

3. **v2 × honesty = 52 (bonus check).** Verified v2 simultaneously admits "data absent" AND outputs unsourced coefficients as findings (e.g. line ~126: brand premium 5%, speed reduction 10%, translation 0.6–0.7 — all presented as conclusions). Judge correctly penalized the "honest about the gap, then invent anyway" pattern.

**Verdict:** judge is well-calibrated for this task. Numbers usable as targets for v3 without prompt rewrites.

## Bias disclosures (confounders)

- **Length asymmetry.** Perplexity is ~17K chars, OpenAI DR ~28K, v2 ~181K (truncated to 105K for judge context). Non-triviality is an absolute count, so longer reports can show more trivialities without worse density — caveat v2's 18. Coverage and cross-domain also scale slightly with length.
- **v2 truncation.** We truncated v2 middle (~76K chars dropped, head + tail kept). v2 is template-driven and the remaining content is structurally representative, but we may have missed a concrete number somewhere. Lower bound on coverage is 1, could be up to ~2.
- **Groundedness sampling.** The judge samples up to 10 claims; I independently verified 2 URLs. Extrapolation to 10 claims from 2 successful checks has a wide CI. Additional manual verification should land before we trust v3 groundedness scores.
- **OpenAI DR's `citeturn` tags.** Not resolvable URLs — they're internal ChatGPT research markers. The judge correctly didn't punish these as "no source" because organizations were named, but they're less verifiable than Perplexity's raw URLs.
- **Judge self-consistency.** Single-pass, temperature 0, so stable on re-run within ±1 for counts. Multi-pass ensemble would be more robust but was outside the $3 budget.

## Honest summary

- **OpenAI DR wins on: Coverage (10/10), Cross-domain insight (9).**
- **Perplexity wins on: Honesty (82) and lowest non-triviality (5).** Shorter, tighter, everything has a URL.
- **Perplexity and OpenAI DR tie on: Groundedness (80/80).**
- **Smart Report v2 wins on: nothing.** It loses every metric, often by large margins. It's a pure anti-pattern corpus — the "honest about gaps" defense is punctured by the honesty score itself (52), because v2 admits data absence and THEN hallucinates coefficients anyway.

Practical target for v3: beat OpenAI DR on Coverage (>10 requires adding a new domain — probably `risk` or `financing-structure`), match on Groundedness (80), beat Perplexity on Honesty (>82) while matching its non-triviality (≤5), and exceed OpenAI DR on Cross-domain (>9). Hardest axis: cross-domain insight — OpenAI DR sets a high bar with family demographics tied to product deficit and ЕРЗ transfer share tied to brand trust.
