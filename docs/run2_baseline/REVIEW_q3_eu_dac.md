# REVIEW — Q3 EU DAC (Run 2 baseline)

**Source fixture:** `tests/fixtures/comparison_runs/2026-04-25/q3_eu_dac_smart_report_step33.json`
**Rendered DOCX:** `runs/run2_baseline/q3_eu_dac_run2_baseline.docx` (46,092 bytes)
**Model:** Haiku 4.5 (every stage). Same caveat as Q1 / Q2.

---

## 1. Где видно Phase 3 калибровку?

**Видно — самый чистый кейс.** Q3 — единственный из трёх запросов,
где Phase 3 fully closed Run 1 finding 3 (LOW_EVIDENCE_QUALITY → OK).

- `metadata.query_domain = "eu_regulatory"` ✅ — Step 3.2 detection
- `metadata.evidence_quality = "OK"` ✅ — EU registry tier из Step 3.1
  Task 1.2 теперь матчает europa.eu / cinea.ec.europa.eu / eur-lex /
  europarl. Run 1 этот же запрос флагал LOW.
- `metadata.gap_count_by_severity = {critical: 0, moderate: 0, minor: 1}` —
  один minor gap (1 authoritative source from threshold of 2). Sub_question
  evidence_status проставлен.

**В visible тексте** distribution radically asymmetric: STRONG=44 (96%),
WEAK=1, SPECULATIVE=1, MODERATE=0. Это потому что:

- 95% input markdown процитировал primary EU sources напрямую
  (climate.ec.europa.eu / europarl.europa.eu / cinea / carbongap.org)
- Step 3.3 классификатор пометил их все как primary_regulator → STRONG
- Synthesizer поверил override и применил [STRONG] на каждый claim

**Sample STRONG:** «Carbon Removals and Carbon Farming Regulation
(ЕС 2024/3012), принятая в декабре 2024 года и вступившая в силу в
начале апреля 2026 года, представляет первую в мире комплексную
добровольную систему сертификации удаления углерода» — корректно
анchored на eur-lex.europa.eu.

**Sample WEAK:** «**Добровольные углеродные кредиты:** DAC кредиты в
настоящее время торгуются по €200–800 за тонну CO₂ эквивалента, в
зависимости от специфичности проекта, строгости проверки и созревания
технологии» — это рыночный диапазон без primary source attribution,
правильно WEAK.

**Sample SPECULATIVE:** «**Интеграция рынка соответствия (перспективная):**
Обновление EU ETS Европейской комиссии в Q3 2026 определит, могут ли
CRUs генерировать или заменять разрешения на выбросы соответствия» —
авторская проекция вперёд по времени, корректно SPECULATIVE.

**Finding (positive):** Q3 показывает что **Phase 3 калибровка работает
в идеальных условиях** — когда input markdown сам цитирует regulatory
primary sources напрямую (что характерно для EU DAC темы благодаря
обилию официальной EU документации). На Q1 / Q2, где input
преимущественно через secondary RU media, эффект скромнее.

## 2. Где конкретно нужен Valyu?

**Именно здесь — самый сильный потенциальный win.** Q3 — главный
кандидат для A/B Valyu test (брифом и предписано: Day 4 dry-run на Q3).

- Сейчас input markdown цитирует eur-lex.europa.eu как secondary
  (через carbongap.org, circularecology.com, mdpi.com). Valyu имеет
  Worldbank indicators, FRED, BLS, USA Spending — но прямого EU
  regulatory dataset в Valyu corpus НЕТ. EU DAC регуляторика
  представлена только через generic web search.
- **Hypothesis для A/B run:** Valyu fast `search_type="all"` на
  «EU CRCF regulation Direct Air Capture certification 2026» может
  вернуть прямые ссылки на eur-lex, europarl, climate.ec.europa.eu —
  более авторитативные чем pre-collected DR markdown. Если так — это
  доказывает routing decision (`regulatory_eu → Valyu primary`).
- **Risk:** Valyu может вернуть тот же набор URLs что Perplexity DR
  уже дал. В этом случае A/B будет показывать минимальную разницу.
- **Rich-source check:** уже сейчас Q3 цитирует 29 source'ов с 9
  primary EU domains. Если Valyu добавит ещё 5-10 primary EU
  citations — STRONG count может вырасти ещё больше (хотя
  saturation эффект уже близок).

**Net Valyu impact для Q3 EU DAC:** ожидаемо **значимый**. A/B run
покажет magnitude. Уже сейчас Q3 — наша «success story» Phase 3.

## 3. Template leakage

**Нет detected.** Regex sweep чисто.

## 4. Confidence варьируется?

**Сильно skewed к STRONG (96%).** Это:

- Не хардкод (нет 0.82 anywhere)
- Не bug — input markdown реально опирается на primary EU sources,
  и Step 3.3 классификатор корректно их пометил
- Но структурно нездорово как pattern: 96% STRONG / 0% MODERATE /
  2% WEAK / 2% SPECULATIVE — это **bimodal degenerate distribution**

**Question for Phase 4:** должен ли synthesizer enforce'ить minimum
distribution (e.g. ≥10% MODERATE, ≥5% WEAK или SPECULATIVE)? Сейчас
если все source'ы primary, ВСЁ становится STRONG, что даёт reader'у
ложное чувство всеохватной certitude. Реалистично всегда есть
аспекты где данные тоньше.

**Альтернативное чтение:** если уже 64+ claim'ов опираются на primary
EU regulatory documents и регуляторика вступила в силу — distribution
действительно может быть скошен в сторону STRONG. Это не bug, это
nature of EU regulatory topic. Phase 4 acceptance critique должен это
оценить эмпирически (несколько high-quality non-regulatory queries),
не теоретически.

---

## Quick stats

| Metric | Value |
|---|---|
| main_synthesis chars | 22,747 (longest of 3 queries) |
| all_sources | 29 |
| STRONG / MODERATE / WEAK / SPECULATIVE in visible text | 44 / 0 / 1 / 1 |
| evidence_quality flag | OK ✅ (Run 1 finding 3 closed) |
| gap_count_by_severity | 0 critical + 0 moderate + 1 minor |
| Template leakage | none |
| Hardcoded 0.82 | none |
