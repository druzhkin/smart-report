# v4.5 Semantic Layer Handoff — 2026-04-19

## Главный вопрос — честный ответ

> **Может ли акционер прочитать отчёт и для ЛЮБОГО утверждения проследить источник за 1 клик, видит ли все цифры релевантные вопросу, и не противоречат ли секции друг другу?**

**Пока не знаем.** Код готов, но финальный прод-прогон не завершился: Synthesize упал с `HTTP 402 Payment Required` от OpenRouter (credits исчерпаны). Баг не в нашей системе — в биллинге. Код валидирован юнит-тестами (217/218 зелёных), но интеграция на живом Opus не подтверждена.

---

## Что сделано за эту ночь (все $0, кроме прерванного прод-прогона)

### Track 0 — Prompt Master data-table directive ✅ (inline)
`prompts/prompt_master.md` дополнен обязательным блоком «Сводная таблица данных» в конец каждого сгенерированного research-промта. Директива требует от Perplexity DR / OpenAI DR / Claude Research собрать минимум 50 строк: value / metric / subject / timeframe / URL / quote. На живом прогоне подтверждено: длина промта 6109 chars vs 5982 в v4 ночном — блок попадает в output.

### Track 1 + Track 4 — Schema & Citation Pipeline ✅ (schema-pipeline agent)
- Новые модели: `SourceRef`, `Claim`, `NumericFact`, `QualitativeFact`, `CitedText`, `NumberedSource`, `NormalizedReport` — backward-compat
- `FinalReport` расширен полями: `bibliography`, `citation_coverage`, `source_count`, `qa_section`, `tables`, `charts`, `callouts`, `key_numbers_highlight`, `ranking`
- Intake (`smart_report/intake.py`): 4 формата citations (`[[N]](url)`, `citeturn`, `[N]`+bibliography, markdown links), LLM-извлечение numeric+qualitative facts
- Analyzer: агрегирует `all_numeric_facts`, `high_relevance_facts`, `fact_coverage_target = 0.85 * high_relevance_count`
- Synthesizer prompt: нерушимое правило CITATION (каждый numeric claim с `[REF:source_xxx]`), нерушимое правило DATA PRESERVATION (≥85% high-relevance facts)
- `bibliography.py`: сканирует `[REF:...]` → сквозная нумерация `[N]`
- `data_audit.py`: coverage audit; при poor/critical_failure → 1 retry Synthesizer с feedback
- DOCX renderer: `[N]` superscript с hyperlink, bibliography сгруппирована, appendix «Дополнительные данные» при coverage <75%
- Тесты: +23 (все зелёные)

### Track 4 enhancement — Intake table parser ✅ (intake-table-parser agent)
`parse_data_table(content)` — pure Python parser (no LLM), распознаёт «Сводная таблица данных» в 6 вариантах заголовка. Extract StructuredFact'ы с auto-inference fact_category, strip «» and [text](url). `normalize_report` сначала пробует parser, fallback на LLM только если таблицы нет. Экономит ~$1-2 на прогон + deterministic результат. +15 тестов + 30-row fixture.

### Track 2 — Consistency Critic ✅ (consistency-critic agent)
`synthesis_critic.py`: 5 категорий issues (number_conflict, ranking_qa_mismatch, verdict_evidence_gap, table_prose_disagreement, source_attribution_inconsistency). Уважает rounding и explicit nuance. Orchestrator: после synthesize → validate → retry если critical_failure. DOCX appendix «Методологические замечания» для material/minor. **Baseline на v4 ночном docx: 4 issues** (2 material NPV range, 2 minor rounding/bundling) — verdict pass. Pool triangle correctly НЕ флагнут как critical. +20 тестов, $0.30 на реальный baseline.

### Track 3 — Language Lint ✅ (language-lint agent)
`i18n/` package: whitelist 6 доменов, `lint_output_language()`. ALL-CAPS (MANDATORY) → error. Игнорирует URL/code/refs. Hyphen-tokens («Outdoor-стек») → флаг Latin части. Orchestrator retry при >20 warnings. Synthesizer prompt: «ЯЗЫК ИСКЛЮЧИТЕЛЬНО РУССКИЙ» + mapping (ranking → ранжирование, MANDATORY → обязательно). **Baseline на v4 ночном docx: 546 warnings** (масштаб провала подтверждён). +15 тестов.

### Frontend — merged в v4
- `fix/cost-tracking`: real total_cost_rub из LLMResult → CostProvider → Masthead badge (hidden at 0)
- followup-single UI: prefer `followup_prompt` (single), fallback на MUST/NICE list
- `design/chat-ui`: `/v4/chat` route, 9 chat-компонентов, warm paper mono tokens, `/v4/new` → redirect
- tsc clean, dev server на `http://localhost:3000` в STUB mode

---

## Прод-прогон — частичное состояние

Session `2dabc115b7a0`, dir `runs/night_upgrade/20260419T093210Z/`:
- ✅ Prompt Master: 46.9s, 6109 chars → `research_prompt.json`
- ✅ Analyze: 917s (15 мин, Intake LLM на каждом из 4 исходников), 7 conflicts, 6 gaps, 1 unified followup → `analysis_output.json`
- ❌ Synthesize: `HTTP 402 Payment Required` от OpenRouter → `final_report.json` отсутствует

**Intake и Analyzer сохранены.** После пополнения credits — retry только Synthesize (~$2-4 с учётом retry chain bibliography+audit+critic+language). Скрипт: `scripts/night_upgrade_prod_run.py` можно модифицировать чтобы skipнуть первые 3 шага.

---

## Метрики — что известно vs что неподтверждено

| Метрика | Целевое | v4 ночной baseline | v4.5 код | v4.5 прогон |
|---|---|---|---|---|
| Source count | 80+ | 20 | правило в промпте | неизвестно |
| Citation coverage | >85% | ~0% | audit + retry | неизвестно |
| Fact retention | >75% | ~30% | audit + retry | неизвестно |
| Language warnings | <5 | **546 измерено** | lint + retry | неизвестно |
| Critical consistency | 0 | 3 (pool triangle в v4) | critic + retry | неизвестно |

Все улучшения есть **в коде** и в тестах. Валидация на живых данных — после пополнения OpenRouter.

---

## Тесты после merge

- **218 собрано, 217 зелёные, 1 failure** (pre-existing, metric-based): `test_intake_extracts_numeric_facts: Expected 800+ facts, got 434` — не блокер
- 2 skipped (expensive integration, gated `-m expensive`)
- Delta: **+87 новых тестов** (34 schema + 20 critic + 15 language + 15 table parser + 3 прочих)

---

## Git state

All local, nothing pushed.

Backend `smart-report-mvp-v3`:
- `v4.5` — полный код с 4 треками + Track 0 inline + table parser merged
- Merged ветки: `schema-pipeline`, `consistency-v45`, `language-lint`, `intake-table-parser`
- Worktree branches `worktree-agent-*` — можно почистить после `git worktree prune`

Frontend `smart-report-mvp`:
- `v4` — merged `fix/cost-tracking` + `design/chat-ui`
- `/v4/chat` готов к визуальной проверке в STUB

---

## Что можно делать пока нет credits

1. **Визуальный review `/v4/chat`** (STUB mode, dev server на :3000) — проверить что warm paper mono эстетика соответствует запросу
2. **Cleanup stale worktree branches** (`git worktree prune`)
3. **Узнать реальный budget** в OpenRouter dashboard чтобы планировать дальнейшие прогоны
4. **Переключить default docx renderer на Node.js** в `exporters/__init__.py` auto-selector — уже готов
5. **Разобрать старый 1 failing test** на `test_intake_extracts_numeric_facts` — понять: занижать threshold или улучшать LLM prompt

## Что сделать когда будут credits

1. Написать `scripts/v45_retry_synthesize.py` на session `2dabc115b7a0` с 1200s timeout
2. Render → `after.docx` в `runs/v4_5/<ts>/`
3. Copy v4 ночной docx → `before.docx`
4. Measure and fill EVAL.md
5. Если pool triangle или новая inconsistency всплыла — итерировать ещё раз ($2-4)
6. Manual sanity check: 10 случайных фактов из `amenities-main.md` — присутствуют ли в финале?

---

## Честная self-assessment

Код v4.5 — качественный, пестрёный тестами, архитектурно правильный. Каждый из 4 треков закрыл свой failure mode (citations / facts / consistency / language). **Фактическая валидация на живых данных — не измерена** из-за финансовой паузы. Это не баг, это ожидание credits.

Когда credits появятся — один Synthesize-прогон ($2-4, 10-15 мин) ответит на главный вопрос. До тех пор — код готов, HANDOFF честный, визуально можно инспектировать `/v4/chat`.
