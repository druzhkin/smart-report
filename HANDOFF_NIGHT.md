# Night Upgrade Handoff — 2026-04-19

## Один ответ на один вопрос

> **Может ли пользователь показать финальный отчёт акционеру без стыда?**

**Пока нет.** Но дельта огромна: было 0 таблиц и 0 графиков → стало 5 таблиц и 3 embedded chart'а, cover page, Q&A со всеми 5 подвопросами закрытыми, 7 key numbers с источниками, 8-пунктовый ranking с весами. DoD всех трёх треков выполнен. Почему не «да» — прямо ниже.

## Что сделано за ночь

Три параллельных трека, все три зелёные, все коммиты на v4 локально:

**Track A — Synthesizer structured output.** Branch `night/track-a` (2 commits). Расширен `FinalReport` 7 опциональными полями (`qa_section`, `ranking`, `tables`, `charts`, `callouts`, `key_numbers_highlight`, `cover_image_prompt`), переписан `prompts/synthesizer.md` под structured output с few-shot примерами и антипаттернами, обновлён `synthesizer.py` с JSON coercers + graceful degradation. +34 теста, $0 (все итерации на моках).

**Track B — DOCX consulting renderer.** Branch `night/track-b` (1 commit). Новый файл `smart_report/exporters/docx_v4_consulting.py` (1182 строки). Cover page с accent bar, exec summary с Q&A + key numbers grid + ranking bars, TOC через Word field code, 11 главы из main_synthesis, hairline-таблицы с zebra, callouts с border-left, embedded chart PNGs, sources grouped by tool, footer с page numbers. +25 тестов, $0.

**Track C — Chart renderer.** Branch `night/track-c` (1 commit). `smart_report/exporters/chart_renderer.py` с `render_chart(spec, path)` — все 6 chart_type'ов (bar, line, pie donut, stacked_bar, waterfall, scatter) в editorial стилизации (amber + neutrals, no grid, spines cleaned, source micro-text). +14 тестов, $0.

**Merge:** все три branches → v4, auto-merged через ort strategy (models.py от Track A перекрыл Track B's дубликат), **158/158 тестов зелёные**.

**Final prod run:** session `ea96c376232c`, 3 Opus-4.7 вызова:
- generate-prompt: 46s, 5982 chars
- analyze: 126s → 4 conflicts, 6 gaps, 8 followups
- synthesize: 231s → qa=5, tables=3, charts=4, callouts=5, key_nums=7, ranking=8

Рендер: `consulting.docx` 341 KB с 3 embedded chart PNG, `legacy.docx` 48 KB для контраста.

## Что не сделано и почему

1. **Chart 3 упал.** `chart_renderer` ожидает `data.series` для stacked_bar/waterfall, Synthesizer на этом прогоне вернул другой ключ. Контракт data-shape между Synthesizer prompt и chart_renderer не формализован в тестах — это регрессионная дыра.

2. **Cost tracking всё ещё сломан.** `total_cost_rub = 0.0` после 3 успешных Opus. `_accumulate_cost` написан, но не подключен в `v4_orchestrator.py`. Это отдельный заявленный бэклог (см. memory `project_real_cost_tracking_broken.md`).

3. **LibreOffice / soffice не в PATH** — нельзя было headless convert → PDF → PNG preview. Пользователь должен открыть DOCX вручную.

4. **Критично: методология пользователя пришла в конце прогона.** `reference/DOCX_METHODOLOGY.md` (Node.js + docx-js, палитра navy+gold, Calibri, KPI 48pt, система цитирования `[N]`, модульная структура). Текущий python-docx renderer её **не реализует**: используется Georgia + amber, нет цитат `[N]`, нет 3-файловой модульности, нет KPI 48pt. **Track B в текущем виде — прокси, не финальная реализация.**

5. **Визуальный page count не измерен** (без Word/LibreOffice). DoD 15-50 страниц не проверен numerically.

## Следующий шаг если результат хорош

Маловероятно, что пользователь скажет «хорошо» — он открыто прислал методологию, которая задаёт более высокую планку. Если всё же результат устроит:
- Доделать cost tracking (1-2 часа).
- Зафиксировать chart_renderer data-shape contract в тестах (1 час).
- Поправить UI-масthead для отображения реальной `total_cost_rub`.

## Следующий шаг если результат плох (вероятный)

**Track D — DOCX Redux по user-методологии.** Ночная задача ~4-6 часов:

1. `docx_v4_consulting.py` → legacy-plus fallback, не основной путь.
2. Новый рендер на **Node.js + docx-js** в директории `smart_report/exporters/docx_js/`:
   - `part1_core.js` — palette `{ primary, primaryDark, accent, accentSoft, textDark, textMuted, bgLight, bgCallout, bgTable, border, success, danger }` по §4 методологии; хелперы `P/R/H1/H2/H3/caption/spacer/hr/callout/kpiCard/kpiRow/dataTable/bullet/numbered`.
   - `part2_sections_1_8.js`, `part3_sections_9_15.js` — группы глав.
   - `main.js` — sections, styles, numbering.config, colontituly, export.
3. **Citation system `[N]`** — разметка источников в Synthesizer output (новое поле `FinalReport.citations: list[Source]`? Или использовать existing `all_sources`?).
4. **Python bridge**: `smart_report/exporters/docx_js_bridge.py` — subprocess `node main.js <final_report.json> <output.docx>`.
5. **Calibri** вместо Georgia, US Letter, поля 1440 DXA.
6. **Валидация** docx через python-docx readback после генерации.

Стоимость Track D: $0 (чистая рендер-работа, никаких LLM).

## Другие открытые беклоги из memory

Проверьте `C:\Users\rodina-adm\.claude\projects\C--Users-rodina-adm-Documents-dev-smart-report-mvp-v3\memory\MEMORY.md`:

- `feedback_v4_design_not_final.md` — фронт UI pure-white+amber тоже нужно переделывать; не закрыто
- `project_real_cost_tracking_broken.md` — cost accumulator не подключен в оркестраторе
- `project_followups_single_prompt.md` — Analyzer должен возвращать один сводный followup, не 5 отдельных
- `project_prompt_page_tool_modes.md` — на экране промта добавить инструкции какой Deep Research режим включать в каждом инструменте

Ни один из этих четырёх беклогов эта ночь не закрывает. Track D (выше) добавляет пятый.

## Artefacts

```
runs/night_upgrade/20260419T075849Z/
├── EVAL.md                        # детальная оценка
├── research_prompt.json           # Opus-4.7 #1
├── analysis_output.json           # Opus-4.7 #2
├── final_report.json              # Opus-4.7 #3, structured
├── session.json
├── session_id.txt
├── final_report_consulting.docx   # 341 KB, python-docx Track B
├── final_report_legacy.docx       # 48 KB, старый pipeline
└── charts/chart_0{0,1,2}.png

NIGHT_UPGRADE_BRIEF.md             # полный спек ночной задачи
SCRATCHPAD_NIGHT.md                # live-координация треков
reference/DOCX_METHODOLOGY.md      # пользовательская методология для Track D (Node.js)
```

## Git state (не пушено, ветка v4)

```
v4 branch: 
  HEAD: merge(v4): Track B ...
  158/158 tests pass
  fresh uncommitted artefacts in runs/night_upgrade/ and on disk
  3 merge commits + 4 feature commits from tracks
Pre-night baseline: 664b67a
Not pushed to any remote.
```

## Honest self-assessment

Если бы это был work product от младшего аналитика: **средний, ближе к хорошему**. Структура выдерживает brief, DoD пройден, но Track B выбрал стек (python-docx) против которого пользователь параллельно прислал альтернативный (Node.js docx-js) с деталями, которые наша реализация не повторяет. Без applying user-методологии — докум останется «лучше, чем было» вместо «то, чего ждали».
