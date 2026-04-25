# REVIEW — Q1 EV (Run 2 baseline)

**Source fixture:** `tests/fixtures/comparison_runs/2026-04-25/q1_ev_smart_report_step33.json`
**Rendered DOCX:** `runs/run2_baseline/q1_ev_run2_baseline.docx` (35,852 bytes)
**Model:** Haiku 4.5 (every stage). Per `BLOCKERS.md` A2: this fixture is the
post-Phase-3 acceptance run, used as Run 2 baseline to save the
fresh-Sonnet $2.69/run cost. The Step 3.3 self-assessed source quality
patch is in this output.

---

## 1. Где видно Phase 3 калибровку?

**Видно — но не в DOCX, а в backend metadata.** Конкретные сигналы:

- `metadata.query_domain = "ru_automotive"` ✅ — Step 3.2 detection отработал
- `metadata.gap_count_by_severity = {critical: 4, moderate: 1, minor: 0}` ✅ —
  gap detector с RU_AUTOMOTIVE registry правильно посчитал, что autostat / aebrus
  не цитировались в uploaded markdowns
- Per-sub_question evidence_status проставлен (4 unanswered, 1 partial)

**В visible тексте отчёта** (main_synthesis + top_findings) tag distribution:
STRONG=19, MODERATE=4, WEAK=5, SPECULATIVE=9. Distribution есть, но:

- Все 19 STRONG-claim'ов идут с inline `[STRONG]` префиксом перед текстом —
  читатель **видит** какие источники надёжны, а какие нет
- Sample STRONG: «Электромобильный рынок России переживает переломный момент в
  апреле 2026 года, когда лидерство впервые перехвачено от импорта к локальному
  производству»
- Sample WEAK: «BYD официально не представлена на российском рынке и продаётся
  исключительно через параллельный импорт» — это уровень WEAK потому что
  отсутствие официального присутствия — секондарный signal
- Sample SPECULATIVE: «В оптимистичном сценарии Moskovich может достичь 25–35%
  рынка с объёмом 60–100 тыс.» — корректно помечен как авторская проекция

**Phase 3 self-assessed (Step 3.3) сработал**: zr.ru (За рулём) и strategy.ru —
два high-reliability источника, цитируются как STRONG в тексте; vendor блоги
типа autochinanet.ru / avtonovostidnya.ru проставлены medium reliability.
Эти reliability-метки попадают в `all_sources[]` метаданные — **в visible тексте
DOCX они не выводятся**. Аналитик увидит только inline `[STRONG]/[WEAK]` теги.

**Finding:** Reliability-уровень сорсов (high/medium/low) живёт в metadata
`all_sources[].reliability` и **не отрисовывается в DOCX**. Step 3.3 калибровка
визуально проявляется только через grade prefix на claims. Если хочется
показать аналитику почему именно [WEAK] — нужно отдельным разделом «Источники
с уровнем доверия» в DOCX, что сейчас отсутствует.

## 2. Где конкретно нужен Valyu?

Очень конкретно. Sub_questions Q1 EV, для которых gap detector нашёл critical gap:

1. **«Какие государственные субсидии и налоговые льготы для российских EV в 2026?»**
   — uploaded markdowns не цитируют Минпромторг напрямую. **Valyu здесь не
   поможет** — Минпромторг не в Valyu corpus (Valyu покрывает SEC/FRED/EU,
   не RU regulatory). Это критический разрыв: для RU automotive у нас нет
   ни Perplexity-strong source, ни Valyu source.

2. **«Какова доступность критических компонентов (батареи, полупроводники)
   для российских и китайских EV в условиях санкций?»** — Valyu
   `valyu-commodities` + `valyu-fred` + `valyu-bls` могут дать метрики цен
   на литий, никель, кобальт. **Реальный win Valyu здесь.**

3. **«Какова текущая доля рынка Москвича / АВТОВАЗа / Evolute и
   производственные мощности?»** — uploaded markdowns цитируют zr.ru
   (которое мы уже учитываем как HIGH reliability). Valyu не добавит
   ценности — нет российских автомобильных датасетов.

4. **«Какие технологические партнёрства / IPO / M&A объявлены 2024-2027?»**
   — Valyu `valyu-sec-filings` бесполезен для российских компаний (не на SEC).
   Для китайских BYD / Geely / Chery (которые публичны) Valyu может дать
   officials filings. **Партial win.**

**Net Valyu impact для Q1 EV:** ~30% sub_questions выиграют от Valyu
(commodities + китайские filings). Остальное — RU-specific, vне Valyu corpus.

## 3. Template leakage

**Нет detected.** Прогон через regex `\{\{[^}]+\}\}` / `\{[a-z_]+\}` /
`\$\{[^}]+\}` на main_synthesis: 0 hits. F-string обёртки и unfilled
placeholders не нашлись. Старый Run 1 finding не воспроизвёлся в этой
итерации.

## 4. Confidence варьируется?

**Да, варьируется** — больше нет хардкода 0.82. Distribution:
- STRONG: 19 (40% от 47 tagged claims)
- MODERATE: 4 (8%)
- WEAK: 5 (11%)
- SPECULATIVE: 9 (19%)
- Untagged: ~10 claims (21%)

**Сигнал честности:** SPECULATIVE > 15% — модель явно отделяет авторские
проекции (typeof "в оптимистичном сценарии..."). Это **то самое поведение
которое мы хотели** после Phase 3 Step 3.3.

**Один остающийся вопрос:** untagged claims (~21%). Это либо короткие
фразы-связки (не несущие фактического заявления), либо synthesis text
который модель забыла отгрейдить. Phase 4 territory.

---

## Quick stats

| Metric | Value |
|---|---|
| main_synthesis chars | 15,020 |
| all_sources | 18 |
| STRONG / MODERATE / WEAK / SPECULATIVE in visible text | 19 / 4 / 5 / 9 |
| evidence_quality flag | LOW_EVIDENCE_QUALITY |
| gap_count_by_severity | 4 critical + 1 moderate |
| Template leakage | none |
| Hardcoded 0.82 | none |
