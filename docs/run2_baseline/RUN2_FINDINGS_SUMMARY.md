# Run 2 Baseline — Findings Summary

**Session:** 2026-04-26
**Authoring note:** Block A (3 fresh Sonnet runs) **failed** due to A12
(Sonnet 4.6 broken on OpenRouter today, 3/3 hang attempts). Block B + C
pivoted to use the existing Day-1 reviews of the Step 3.3 acceptance
fixtures (Haiku tier, same `origin/v4.5` code path) as substance basis.
The calibration / template / confidence findings transfer cleanly between
Haiku and Sonnet because all three signals come from the same shared
code (source-quality classifier, intake, synth instructions). Sonnet
re-run scheduled when OpenRouter recovers.

---

## TL;DR (5 строк)

- Phase 3 калибровка дошла до DOCX: **✅ все 3 query** — через inline
  `[STRONG]/[MODERATE]/[WEAK]/[SPECULATIVE]` префиксы на каждом claim
  (Q1: 19/4/5/9, Q2: 17/14/0/6, Q3: 44/0/1/1).
- Template leakage closed: **✅** — regex sweep `\{[^}]+\}` дал 0 hits
  на всех 3 fixtures.
- Confidence хардкод 0.82 closed: **✅** — distributions вариативны на
  каждом query, SPECULATIVE-доля 16-19% (Q1, Q2) показывает что модель
  честно отделяет авторские проекции.
- Главный bottleneck сейчас: **source coverage** (RU regulator,
  Минпромторг/Росстат/CBR; EU regulatory primary docs eur-lex/cinea) —
  НЕ synthesizer и не pipeline. Phase 3 substance wins держатся.
- Рекомендация на следующую сессию: **Scenario A — §5.6 Protocol**
  (architectural path), без synth-fix urgency. Закрытые баги остались
  закрытыми; новый прирост придёт от backend coverage.

---

## Cross-query patterns

### Что улучшилось от Phase 3 (видно в DOCX, не только в логах)

1. **Каждый claim в visible тексте имеет grade prefix** (Phase 3.3
   Step output). Аналитик видит «По данным РБК [MODERATE]» вместо
   нейтрального утверждения. Q2 Moscow RE — самый чистый кейс: RBC
   корректно ушёл из STRONG (где был на Step 3.2) в MODERATE.
2. **Source-quality classifier honest на adversarial input** (Day 4
   урок): когда Valyu вернул arxiv preprints вместо EU regulatory
   primary docs, классификатор честно выставил WEAK/SPECULATIVE
   вместо STRONG. Это в Run 2 не воспроизводилось напрямую (нет
   adversarial Sonnet runs), но Day 4 Q3 dry-run это подтвердил.
3. **Per-domain authoritative registry работает на per-query routing**
   (Phase 3.2): Q1 routes ru_automotive, Q2 ru_real_estate, Q3
   eu_regulatory — все три корректно. ru_automotive registry поднял
   zr.ru/strategy.ru до STRONG, RU RE registry поднял Yakov Partners
   до STRONG.
4. **Distribution informativeness:** Q1 показывает 47 tagged claims
   с 4 distinct grade levels — для аналитика signal-to-noise высокий.

### Что НЕ улучшилось (closed-помеченные баги, всё ещё видны)

**Ничего из помеченных как closed не вернулось.** Список confirmed:

- ❌ Template leakage (Phase 3 finding 5) — 0 hits на всех 3 fixtures.
- ❌ Hardcoded confidence 0.82 (Phase 3 finding 6) — distributions
  honestly varied.

**Но появились новые наблюдения, не closed-bugs, а improvement gaps:**

- `all_sources[].reliability` (HIGH/MEDIUM/LOW из Step 3.3 self-assess)
  **не рендерится в DOCX**. Аналитик видит inline grade на claim, но
  не видит «почему именно [WEAK]». Раздел «Источники с уровнем
  доверия» в DOCX отсутствует.
- `evidence_gaps[]` массив **не доходит до DOCX когда query идёт
  через template path** (Q2 RU RE → strategic template → пустой
  sub_questions → gap_detector не запускается). Архитектурно
  корректное поведение Step 2.1, но для аналитика «почему нет
  источников по X» — пустота.
- ~21% claims на Q1 EV не имеют grade tag вообще (Q2: ниже, Q3: ~3%).
  Это либо короткие connecting phrases, либо forgotten-grading.
  Phase 4 territory.

### Per-query substance grades

| Query | Grade | Топ-проблема | Топ-улучшение |
|---|---|---|---|
| Q1 EV | 6/10 | RU regulatory coverage (Минпромторг отсутствует ни в Perplexity strong sources, ни в Valyu) | inline grades + ru_automotive registry дали 19 STRONG (был 0 на Run 1) |
| Q2 Moscow RE | 7/10 | RU primary statistics (Росстат/Минстрой/CBR/MOEX отсутствуют в Valyu, цитируются через RBC) | RBC честно опущен из STRONG в MODERATE → 14 MODERATE из 37 tags = самый информативный distribution |
| Q3 EU DAC | 5/10 | degenerate distribution (96% STRONG) — calibration проигрывает когда input уже homogeneous primary; eur-lex отсутствует в Valyu (Day 5) | evidence_quality flipped LOW→OK через EU registry tier |

---

## Backend prioritization (по итогам review)

### Valyu — ожидаемый lift по query

- **Q1 EV: medium-low** — `valyu-fred` + `valyu-bls` могут дать
  battery commodities (lithium/cobalt prices). `valyu-sec-filings`
  для китайских (BYD/Geely/Chery) IPO/M&A — partial win. RU
  Минпромторг полностью отсутствует. Net: ~30% sub_questions
  выиграют.
- **Q2 Moscow RE: none** — Valyu не покрывает Росстат/Минстрой/ДОМ.РФ/
  CBR/MOEX. Brief routing `russian_market → Perplexity primary,
  Valyu n/a` корректно зафиксировал. A/B B vs A для Q2 покажет
  минимальную разницу.
- **Q3 EU DAC: none** — Day 5 capability map подтвердил отсутствие
  eur-lex / cinea / europa в Valyu corpus. Day 4 dry-run эмпирически
  показал что `proprietary` mode возвращает arxiv для EU regulatory
  query. v3 brief routing matrix `regulatory_eu → Valyu primary`
  будет триггерить degradation_warning на каждом вызове (это by
  design v3 §3.4).
- **Сколько раз mentioned в reviews:** 4 (Q1 commodities, Q1 Chinese
  SEC, Q2 noted as zero, Q3 noted as zero per Day 4)

### Exa — ожидаемый lift по query

- **Q1 EV: medium** — semantic search для «similar to BYD India market
  expansion analysis» / Chinese OEM strategic positioning. `outputSchema`
  для structured cost/specs comparison.
- **Q2 Moscow RE: low-medium** — semantic для «similar to Yakov Partners
  market segmentation» в смежных EU/CIS markets. Но primary need это
  RU statistics, не аналитика.
- **Q3 EU DAC: medium** — semantic для CRCF / MiCA / AIA related
  regulatory comparison; `outputSchema` для structured subsidy
  rates / per-tonne pricing.
- **Mentioned:** 3 (Q1 Chinese strategy, Q3 CRCF semantic, Q3
  outputSchema)

### Tavily — ожидаемый lift по query

- **Q1 EV: low** — general news о автопроме России мы уже получаем
  через Perplexity достаточно. Tavily basic не добавит signal.
- **Q2 Moscow RE: medium** — RBC realty news / Kommersant updates
  можно дешевле через Tavily basic чем через Perplexity. Routing
  domain `russian_market → Tavily basic как augment` это покрывает.
- **Q3 EU DAC: medium** — общие EU climate policy news (которые
  Perplexity иногда хорошо индексирует); EU Commission press releases.
- **Mentioned:** 4 (Q2 RBC, Q3 EU news × 2, Q1 noted as low value)

---

## Decision input для следующей сессии

### Сценарий A — Continue with §5.6 Protocol (architectural path) ✅ ВЫБРАН

**Применим, потому что:**

1. ✅ Calibration дошла до DOCX (видна на всех 3 query через
   inline grade prefixes)
2. ✅ Template leakage и confidence хардкод **остаются closed**
   (regex sweep + distribution-vary check)
3. ✅ Главное узкое место — coverage источников (RU regulators,
   EU primary docs), а это **именно то, что § 5.6+ должен решать**:
   abstraction для подключения новых backends, маршрутизация по
   domain, augment-on-failure.

**Обоснование (3-5 строк):** Phase 3 substance wins **держатся в
DOCX** — нет повода тормозить архитектурную работу для synth-fix
urgency. Известные improvement gaps (reliability в DOCX,
evidence_gaps на template path, untagged claims) — кандидаты в
Phase 4 brief, не блокеры. Backend coverage — главный bottleneck,
который v3 architecture именно и адресует. Day 5 уже заложил
routing_matrix + invariant test; следующая сессия логично
продолжает с §5.6 SearchBackend Protocol → §5.7-5.10 clients →
§5.13 orchestrator rewrite.

**Не применим Scenario B** (synthesizer fix first) — нет
обнаруженных regression bug'ов в синтезаторе.

**Не применим Scenario C** (hybrid) — ничего из closed не вернулось.

---

## Phase 4 brief — кандидаты в Step'ы

Не пишем сам brief в этой сессии — это Day 6 v3 после A/B run.
Здесь — только заготовки findings:

1. **DOCX render `all_sources[].reliability`** — добавить раздел
   «Источники: уровень доверия и обоснование» в DOCX, чтобы
   аналитик видел ПОЧЕМУ конкретный grade. Inline grade без
   per-source rationale = signal без объяснения. → Step:
   `feat(docx): источники-таблица с reliability + classification reason`
2. **evidence_gaps на template path** — когда query идёт через
   strategic template (Q2 RU RE), `gap_detector` не запускается
   (нет sub_questions). Реализовать template-aware gap detection
   на final_report level. → Step: `feat(gaps): post-synth gap pass
   for template-path queries`
3. **RU regulatory backend** — Valyu не покрывает Росстат/Минстрой/CBR/
   MOEX, и Perplexity на этих доменах даёт через RBC, не первичные
   данные. Distinct backend (Rosstat API + EISJS + CBR statistics
   + MOEX SmartLab) — отдельная ветка backend integration. →
   Step: `feat(sources): Russian regulatory backend (Rosstat/CBR/MOEX)`
4. **Untagged claims** — Q1 показывает ~21% claims без grade
   prefix. Либо короткие связки (нормально), либо synthesizer
   забыл отгрейдить. Audit run + lint check. → Step:
   `feat(synthesizer): warn on untagged claim ratio > 15%`
5. **regulatory_eu degradation pattern** (Day 5 + Day 4 finding) —
   v3 brief routing будет триггерить degradation_warning на каждом
   eu_regulatory вызове (eur-lex отсутствует в Valyu). v3 §3.4
   design это by-design, но нужен метрик: сколько % runs реально
   degrade, и есть ли паттерны. → Step: `feat(observability): per-domain
   degradation rate dashboard`
6. **Sonnet 4.6 reliability** (Run 2 session A12 finding) — pipeline
   зависает silent при OpenRouter Sonnet проблемах; 3/3 attempts
   сегодня умерли без exception. Нужен httpx-уровневый watchdog +
   chat preflight smoke-check. → Step: `feat(observability): LLM
   health check + httpx hang detection`

---

## Открытые вопросы для заказчика

1. **Sonnet 4.6 hang reproducibly today** (A12) — Run 2 fresh
   baseline runs on Sonnet impossible. Когда вернёмся к попытке?
   Хотим preflight smoke test перед каждым --live? Готовы переключиться
   на Haiku до восстановления Sonnet (Day-1 reviews показывают что
   Haiku даёт substance того же качества для review purposes)?
2. **Day-1 review basis для SUMMARY вместо fresh Sonnet** — этот
   SUMMARY основан на Step 3.3 Haiku fixtures, не fresh Sonnet
   runs (которые были задачей этой сессии, но провалились). Substance
   findings (calibration в DOCX, template/confidence closed) переносятся
   между моделями (общий код), но prose-quality / reasoning depth
   differences между Haiku и Sonnet здесь не зафиксированы. Если это
   критично — нужно пересоздать сессию когда OpenRouter Sonnet
   восстановится. Если acceptable substance-only — проводим §5.6+
   на этих findings.
3. **Phase 4 priority order** — 6 candidate Step'ов выше. Какие
   важнее для Phase 4 brief на Day 6 v3? RU regulatory backend
   (3) и DOCX reliability rendering (1) — обе значимые, но
   разные по scope. Рекомендация по очерёдности?
