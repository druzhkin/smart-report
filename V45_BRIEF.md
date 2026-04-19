# Smart Report v4.5 — Семантический слой (полный брифинг для агентов)

См. полный текст спецификации в user-message (скопирован ниже полностью).

---

## 0. Почему это критично

v4 ночной upgrade дал визуальный скачок (23 стр, KPI grid, ranking, графики), но при content review обнаружены 4 провала:

1. **Английские слова** повсюду в русском отчёте (ranking, MANDATORY, Outdoor-стек, wine room).
2. **Внутренние противоречия** между секциями (стр. 4: бассейн 22% важен / стр. 5: бассейн 8% низкий приоритет / стр. 9: бассейн EXCLUDE).
3. **Потеря 80% источников** (155+ URL в исходниках → 20 в финале, 0% inline citations).
4. **Потеря 70% данных** (~1384 numeric facts в исходниках → ~410 в финале; ratio 0.30).

До исправления этих четырёх — никакой работы над типографикой.

## Главный вопрос

> **Может ли акционер прочитать отчёт и для ЛЮБОГО утверждения проследить источник за 1 клик, ВИДИТ ВСЕ ЦИФРЫ И ФАКТЫ из исходников релевантные его вопросу, и НИ ОДНО утверждение в одной секции не противоречит утверждению в другой?**

## Целевые метрики

| Метрика | Текущее (v4 night) | Целевое (v4.5) |
|---|---|---|
| Source count в bibliography | 20 | 80+ |
| Citation coverage (numeric claims) | ~0% | >85% |
| **Numeric fact retention** | **~30%** | **>75%** |
| **Numeric facts total in final** | **~410** | **1000+** |
| Language warnings (non-whitelist EN) | ~30 | <5 |
| Critical consistency issues | 3 | 0 |

## Стартовый датасет

`runs/night_upgrade/fixtures/`:
- `deep-research-report-1.md` (63 KB, Perplexity/OpenAI формат)
- `deep-research-report-2.md` (30 KB)
- `amenities-main.md` (116 KB, главный, 126 URL, формат `[[N]](url)`)
- `amenities-methodology.md` (46 KB, 29 URL)

Cached:
- `runs/night_upgrade/cache_analysis.json` — AnalysisOutput из v4 ночного прогона (использовать для Synthesizer iterations)
- `runs/night_upgrade/cache_final.json` — текущий плохой FinalReport (для сравнения)
- `runs/night_upgrade/20260419T075849Z/final_report_consulting.docx` — текущий плохой docx

Эталонный вопрос: «мне нужен полный глубокий обзор по бизнес и премиум новостройкам москвы...» (см. `scripts/night_upgrade_prod_run.py` QUESTION constant).

## Координация

- **Трек 1+4 объединены** — schema expansion (citations + fact preservation) делается одной командой
- Трек 2 (Critic) и Трек 3 (Language) — независимы и параллельны
- Shared state: `SCRATCHPAD_V45.md`, обновления каждые 30 мин

## Hard rules

1. FinalReport backward-compatible на уровне рендера (старый код без CitedText должен работать)
2. Source preservation > text aesthetics
3. Critic loop max 1 retry
4. Не делать full pipeline на каждую итерацию — использовать cached AnalysisOutput
5. LLM-вызовы → `runs/v4_5/<ts>/llm_log.jsonl`
6. Старые 193 теста должны остаться зелёными
7. Отдельная ветка на трек (`v4.5/schema-pipeline`, `v4.5/consistency`, `v4.5/language`)
8. Не пушить

## Stop criteria (per трек)

- citation_coverage < 60% после 3 итераций промпта → стоп, документировать схему
- fact_retention < 50% после 3 итераций → стоп, предложить chunked synthesis
- Critic FP > 50% → стоп, промпт требует переписи с пользователем
- Language lint FP → фиксить детектор
- $25 бюджет исчерпан до финального прогона → стоп
- docx renderer ломается на CitedText → significant refactor

## Финальный прогон (~$5-8)

После merge всех треков:
1. Cached Intake+Analyzer re-run только если Intake схема фундаментально изменилась (добавление NumericFact требует нового прогона Intake)
2. Synthesizer + Critic loop на свежих данных
3. Post-processing: bibliography + coverage audit + language lint
4. Render `after.docx`, скопировать night docx → `before.docx`
5. PDF preview первых 5 страниц (если LibreOffice доступен)
6. EVAL.md + HANDOFF_V45.md по шаблону в спеке
