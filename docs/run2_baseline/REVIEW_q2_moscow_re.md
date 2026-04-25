# REVIEW — Q2 Moscow RE (Run 2 baseline)

**Source fixture:** `tests/fixtures/comparison_runs/2026-04-25/q2_moscow_re_smart_report_step33.json`
**Rendered DOCX:** `runs/run2_baseline/q2_moscow_re_run2_baseline.docx` (40,442 bytes)
**Model:** Haiku 4.5 (every stage). Same caveat as Q1 — Step 3.3 fixture
reused as Run 2 baseline.

---

## 1. Где видно Phase 3 калибровку?

**Видно — но Q2 ушла через template path (RU RE strategic).** Это значит:

- `metadata.query_domain = "ru_real_estate"` ✅ — domain detection unconditional
  (Phase 3.2 пост-tweak) сработал
- `metadata.evidence_gaps` пуст — потому что template path не populates
  `sub_questions`, а gap_detector работает только когда они есть. Это
  корректное архитектурное поведение Step 2.1, но для Q2 значит, что
  per-sub_question gap reasoning **не доходит до DOCX**.
- `metadata.evidence_quality = "LOW_EVIDENCE_QUALITY"` — Step 1.2 global
  source-adequacy check сработал (на 46 source'ов pool недостаточно
  authoritative для бара).

**В visible тексте** распределение grade tags:
STRONG=17, MODERATE=14, SPECULATIVE=6 (WEAK=0). Это **самый информативный
результат** на трёх запросах:

- Yakov Partners + Moscow Times + RBC realty + Kommersant цитируются
  массово — Step 3.3 классификатор пометил их как trusted_media (MODERATE)
  или RU RE consultancy (STRONG). RBC `realty.rbc.ru` идёт как HIGH
  reliability в `all_sources` — то самое self-assessed override, которое
  было целью Step 3.3.
- Нулевой WEAK — потому что vendor blogs / random sources прошли через
  override и подтянулись либо к MODERATE (если попали в trusted_media
  registry), либо к STRONG (если registry-hit).
- 6 SPECULATIVE — авторские объяснения структурного сдвига рынка
  (например «Почему произошёл этот сдвиг? Себестоимость строительства
  растёт, но цены в эконом-сегменте упираются в платежеспособность»).

**Sample STRONG:** «Московский рынок жилого девелопмента переживает
структурную трансформацию в 2026–2027 годах, которая радикально
переформатирует стратегии разработчиков [1]» — bibliography ref [1] идёт
на yakovpartners.com (RU RE consultancy registry → STRONG).

**Sample MODERATE:** «Важный сдвиг в структуре спроса: при ставках ниже
14–15%, рынок ожидает всплеска спроса на вторичное жилье...» — цитирует
RBC, классифицирован как trusted_media.

**Sample SPECULATIVE:** «Это указывает на то, что консолидированные
девелоперы с мощным финансированием активно готовят земельный банк для
взрывного роста после снижения ставок» — авторская связка, корректно
помечена.

**Finding:** Phase 3 калибровка визуально проявляется чётко на Q2 —
больше всего из трёх query. Это потому что Q2 имеет самый большой
source pool (46) и большинство источников попадают в registry/media
tier'ы, не в unknown. На Q1 / Q3 эффект меньше потому что pool ýже.

## 2. Где конкретно нужен Valyu?

Q2 — самый сложный кейс для Valyu integration. **RU local context.**
Gap detector не флагает (template path), но если посмотреть глазами:

- **Росстат / Минстрой / ДОМ.РФ напрямую не цитируются.** Все цифры
  идут через RBC / Kommersant / Yakov Partners. То есть мы видим
  «по данным РБК, Росстат сообщил...» вместо первичного источника.
  **Valyu здесь не поможет** — у Valyu нет российских стат-агентств.
  Решение из брифа `russian_market → Perplexity primary, Valyu n/a`
  правильное. Phase 4 нужен другой механизм для прямого Росстат
  retrieval (вероятно, специализированный backend через
  Rosstat/EISJS API).
- **Девелоперы как public companies:** ПИК, MR Group, Самолёт
  торгуются на MOEX. Valyu `valyu-sec-filings` не покрывает MOEX.
  Phase 4 territory: специализированный MOEX/SmartLab backend.
- **Ипотека / процентные ставки макро:** ЦБ РФ. Valyu имеет FRED
  (US Fed) — структурно похоже, но российский эквивалент
  (`cbr.ru/statistics`) у Valyu отсутствует.

**Net Valyu impact для Q2 RE:** **0%.** Brief routing table это
правильно зафиксировал. Q2 в A/B тесте будет показывать минимальную
разницу между config A и B — это ожидаемо.

## 3. Template leakage

**Нет detected.** Regex sweep дал 0 hits. (Q2 пошла через RU RE
domain template Phase 2 Step 2.1, но это другое «template» — он
производит markdown-guidance в research_prompt, а не leak'ает
шаблонные плейсхолдеры в final.)

## 4. Confidence варьируется?

**Да** — distribution: STRONG 17 (45%) / MODERATE 14 (38%) / WEAK 0 /
SPECULATIVE 6 (16%) из 37 tagged claims. WEAK = 0 нужно объяснить:

- На вчерашней Step 3.2 pre-Step-3.3 run Q2 показывал 50 STRONG / 1
  MODERATE / 0 WEAK / 1 SPECULATIVE — то есть Haiku сильно завышал
  STRONG из-за пассивного echo'инга input markdown'а.
- Сегодня (Step 3.3 fixture) — 17 / 14 / 0 / 6, RBC переклассифицирован
  с STRONG → MODERATE, что есть **honest self-assessment**.

WEAK = 0 это означает: ни один цитированный источник не попал в
forum_or_aggregator / unknown tier. Все источники в pool — либо RE
consultancy / trusted media (RBC, Vedomosti, Moscow Times) / Yakov.
Это правда о составе input markdown'ов от user'а; output корректно
отражает.

---

## Quick stats

| Metric | Value |
|---|---|
| main_synthesis chars | 13,342 |
| all_sources | 46 |
| STRONG / MODERATE / WEAK / SPECULATIVE in visible text | 17 / 14 / 0 / 6 |
| evidence_quality flag | LOW_EVIDENCE_QUALITY |
| evidence_gaps | empty (template path) |
| Template leakage | none |
| Hardcoded 0.82 | none |
