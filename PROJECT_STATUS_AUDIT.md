# Отчёт о состоянии проекта Smart Report MVP

**Дата:** 24 апреля 2026
**Ветка:** `v4.5` (актуальная разработка)
**Главные ветки:** `main` (стабильная), `v3` (legacy production-ready), `v4` (внешний DR-цикл), `v4.5` (семантический слой)
**Назначение документа:** передача на полный аудит — статус «MVP, активная разработка, прод-валидация прервана»

---

## 1. Что это за проект

Smart Report MVP — персональный аналитический движок, который превращает нетривиальный аналитический вопрос в структурированный отчёт уровня инвестиционного мемо. Целевой пользователь — аналитик девелопмента/строительства. На вход — вопрос вида *«что определяет успех девелопера в бизнес-сегменте Москвы»*; на выход — пакет (DOCX, PPTX, Markdown, JSON, HTML-onepager) с источниками, таблицами, графиками, чек-листом фактов и кросс-доменными бисоциациями.

**Стек:**
- Бэкенд: **Python 3.11 / FastAPI / asyncio**, **Pydantic v2**, **httpx**
- Фронтенд: **Next.js 14.2 / React 18 / Tailwind**
- DOCX-рендер: **Node.js 22 + docx-js@9.6.1** (через subprocess)
- LLM: **OpenRouter** (Opus 4.7 / Sonnet 4.6 / Haiku 4.5 / GPT-4o)
- Retrieval: **Perplexity sonar-pro**
- Web scrape: **Jina Reader** (бесплатный)

---

## 2. Архитектурные поколения

Проект прошёл три поколения, и **все три живут в кодбейзе одновременно** — это важный момент для аудитора.

### v3 — автономный пайплайн (стабилен, но не задеплоен)
`smart_report/orchestrator.py` (173 строки). Async-пайплайн **Planner → Scout → Analyst → Bisociator** с bounded parallelism по ячейкам матрицы. Полностью замкнутый цикл: вопрос → матрица доменов × слоёв → block per cell → cross-links. Использует Perplexity для retrieval. В коде есть, тестами покрыт, но **в прод не выкачен** (Railway-конфиг готов, но не активирован).

### v4 — meta-analysis с ручным DR-loop (стабилен, активно используется)
`smart_report/v4_orchestrator.py` (349 строк). Трёхшаговый сценарий: **generate-prompt → analyze → synthesize**. Между шагами — паузы: аналитик копирует сгенерированный промт во внешние Deep Research-инструменты (Perplexity DR, OpenAI DR, Claude Research), скачивает markdown-отчёты, заливает обратно. Это и есть рабочий режим v4.

### v4.5 — семантический слой поверх v4 (код готов, прод не валидирован)
Надстройка из 4 «треков» поверх v4-пайплайна:

- **Track 1 — Schema & Citations:** новые модели `SourceRef/Claim/NumericFact/CitedText/NormalizedReport`, `[REF:...]` через весь пайплайн, сквозная нумерация `[N]` через `bibliography.py`
- **Track 2 — Consistency Critic:** `synthesis_critic.py` — пост-валидация Synthesizer на 5 категорий внутренних противоречий (number_conflict, ranking_qa_mismatch, verdict_evidence_gap, table_prose_disagreement, source_attribution_inconsistency), 1 retry при `critical_failure`
- **Track 3 — Language Lint:** `i18n/` package — whitelist 6 доменов для допустимых англицизмов, retry при >20 нерусских токенов
- **Track 4 — Intake & Fact Preservation:** `intake.py` (987 строк) — нормализация исходников, fast-path **детерминированный парсер «Сводной таблицы данных»** (без LLM, экономит ~$1-2/прогон), LLM fallback на Haiku 4.5
- **Track 0 — Prompt Master directive (inline):** `prompts/prompt_master.md` обязывает DR-инструмент собрать ≥50 строк фактов в структурированную таблицу

---

## 3. Статус сделанного

### Полностью готово (код + тесты)

| Подсистема | Где | Статус |
|---|---|---|
| HTTP API v3 (REST + SSE + long-poll) | `api/main.py`, `api/jobs.py` | работает, single-worker, in-memory store |
| HTTP API v4 (трёхшаговая сессия + upload + export) | `api/v4_endpoints.py` (388 строк) | работает |
| CLI dry-run | `run.py` | работает |
| Async-пайплайн v3 | `orchestrator.py`, `planner/scout/analyst/bisociator.py` | работает |
| Async-пайплайн v4 + retry chain | `v4_orchestrator.py` | работает |
| Intake (детерминированный парсер таблиц + LLM fallback) | `intake.py`, 987 строк | работает |
| Schema/citations pipeline | `models.py`, `bibliography.py`, `data_audit.py` | работает |
| Consistency Critic | `synthesis_critic.py` (311 строк) | работает |
| Language Lint | `i18n/language_lint.py` | работает |
| Synthesizer + json-repair fallback | `synthesizer.py` (666 строк) | работает |
| Cost tracking | `LLMResult.cost_rub` через весь pipeline | работает, фронт через `costContext` |
| Single follow-up prompt (заменил массив из 5) | `AnalysisOutput.followup_prompt` + backward-compat shim | работает |
| DOCX renderer v2 (Node.js + docx-js) | `exporters/docx_js/`, `docx_js_bridge.py` | работает, navy/gold palette, KPI 48pt, `[N]` superscript-citations |
| DOCX renderer v1 (Python python-docx, legacy consulting style) | `exporters/docx_v4_consulting.py` (1515 строк) | работает, оставлен как fallback |
| Auto-selector DOCX | `exporters/__init__.py::render_docx` | переключается на Node.js если доступен |
| PPTX, Markdown, JSON, HTML-onepager экспорт | `exporters/render.py` | работает |
| Frontend `/v4/chat` (warm-paper-mono эстетика) | `smart-report-mvp/frontend/app/v4/chat/`, 9 чат-компонентов | merged в `v4`, dev :3000 OK |
| ModelPicker (Sonnet/Opus toggle) | топбар, прокидывает `model_preference` через все 3 endpoint | работает, бэк уважает в `models_for_preference()` |
| Frontend cost badge (скрыт при 0) | `CostBadge.tsx` + `CostProvider` | работает |
| Тестовая суита | 290 тестов на pytest | **288 passed / 2 skipped / 2 deselected (expensive), 0 failed** |

### Готово, но НЕ валидировано на живых данных

**v4.5 семантический слой** — код есть, тесты зелёные, но **финальный прод-прогон не завершён**:

- 19 апреля прогон `2dabc115b7a0` (`runs/night_upgrade/20260419T093210Z/`) дошёл до `Synthesize`, упал с **HTTP 402 Payment Required от OpenRouter** (credits исчерпаны).
- `Intake` (917s, 15 мин на 4 исходниках, 7 conflicts, 6 gaps) и `Analyzer` сохранены в `analysis_output.json`. **`final_report.json` отсутствует.**
- Последняя попытка retry (`runs/v4_5/20260419T163348Z/`) — пустая директория.
- Скрипт ретрая `scripts/v45_retry_synthesize.py` готов, но требует чтобы backend не перезапускался между Analyze и Synthesize (in-memory store, нет endpoint восстановления).

**Метрики, которые НЕ замерены на v4.5:**

| Метрика | Целевое | v4 ночной baseline | v4.5 |
|---|---|---|---|
| Source count | 80+ | 20 | **неизвестно** |
| Citation coverage | >85% | ~0% | **неизвестно** |
| Fact retention | >75% | ~30% | **неизвестно** |
| Language warnings | <5 | **546 измерено** | **неизвестно** |
| Critical consistency | 0 | 3 (pool triangle) | **неизвестно** |

**Главный неотвеченный вопрос v4.5:** «Может ли акционер для ЛЮБОГО утверждения отчёта проследить источник за 1 клик?» — пока нет ответа.

### Не сделано / отсутствует

- **Деплой.** v3 не выкачен в прод. Railway-конфиг (`railway.toml`) только во фронт-репо. Бэкенд бежит локально на `:8020` (а не `:8000`).
- **БД, объектное хранилище, CDN.** Не используются. Сессии — в памяти процесса (`_V4_SESSIONS: dict`), артефакты — на диске (`runs/`). При рестарте — потеря состояния.
- **CI/CD.** Не настроен. GitHub Actions нет.
- **Endpoint восстановления сессии** (`POST /admin/restore`) — упоминается в `v45_retry_synthesize.py` как `NotImplementedError`. Из-за этого retry Synthesize требует, чтобы backend жил с момента Analyze.
- **Auth.** Нет. `/login` и `/verify` страницы во фронте есть, но бэкенд их не обслуживает. CORS открыт только для `localhost:3000-3003`.
- **Мониторинг.** Только JSONL-лог LLM-вызовов на диск + stdout.
- **Один тест с pre-existing failure** (`test_intake_extracts_numeric_facts: Expected 800+ facts, got 434`) — был в HANDOFF_V45.md, сейчас в текущем прогоне его нет (290 собрано, 288 пройдено, 2 deselected). Видимо, переведён в `expensive` или починен — но регрессия по строгости порога не зафиксирована явно.

---

## 4. Что точно работает (можно показать сейчас)

1. **`pytest` локально** — 288 passed, 2 skipped, 2 deselected, 13.9s.
2. **CLI dry-run** — `python run.py --dry-run "..."` производит mock-отчёт без LLM-вызовов.
3. **FastAPI на :8020** — `/health`, `/api/research`, `/api/v4/sessions/*` отдают валидные ответы.
4. **Frontend на :3000** — `/v4/chat` рендерится в warm-paper-mono стиле.
5. **DOCX-рендер** — последний успешный прогон `runs/night_upgrade/20260419T075849Z/final_report_consulting.docx` существует.
6. **Bake-off артефакты** — три DOCX (sonnet-4.6 57KB, opus-4.7 55KB, gemini-3.1-pro 46KB) в `runs/v45_bakeoff/20260419T132541Z/synth_reports_v2/` для визуального спот-чека.

---

## 5. Что НЕ работает / риски

### Блокирующие

- **OpenRouter credits исчерпаны.** Любой реальный прогон сейчас падает на 402. Это блокер для финальной валидации v4.5. Не баг кода.
- **Synthesizer на Opus давал malformed JSON** (`JSONDecodeError на char 63713`) — починено через **переключение на Sonnet 4.6** (см. `config.py::ModelConfig.SYNTHESIZER_MODEL`) **+ json-repair Layer 4 fallback** (commit `2bb6d37`). Но если сделать форсированный возврат на Opus — баг вернётся.

### Архитектурные

- **In-memory session store.** Перезапуск сервера = потеря сессии = повторная оплата Intake/Analyzer ($0.5–1).
- **Нет горизонтального масштабирования.** FastAPI single worker. Сессии не переживают рестарт, не делятся между процессами.
- **subprocess для DOCX.** Каждый рендер = `node main.js`. Долго на холодном старте, надёжно, но не масштабируется.
- **Нет rate-limiting / auth.** Любой клиент может дёрнуть `/api/v4/sessions/*` и потратить чужие OpenRouter-токены.
- **CORS зашит на localhost.** На прод-домен не сконфигурирован.

### Качества кода

- **`docx_v4_consulting.py` — 1515 строк** одного файла. Legacy-renderer, теперь fallback. Кандидат на удаление после подтверждения, что Node.js renderer стабилен.
- **Две версии DOCX** (`render_docx_js` vs `render_consulting_docx`) с auto-selector — это хорошо для миграции, плохо для долгосрочной поддержки.
- **Backward-compat shim для `followup_prompts[]`** в моделях — оставлен, технический долг.
- **24 коммита на ветке v4.5 не запушены в origin** (вся работа только локально).
- **18+ открытых веток** локально (включая `worktree-agent-*`), нужна чистка.
- **Артефакты прогонов в `runs/`** — сотни директорий, есть смысл архивировать или вычистить.

### Документационные / операционные

- **Память в `MEMORY.md` устарела** на 3 дня — пишет про 217/218 тестов, реально 290 собрано / 288 passed.
- **`HANDOFF_V45.md` остаётся актуальным** как самый честный технический сводный документ. `ONEPAGER.md` был обновлён сегодня (24 апреля).
- **Нет интеграционных e2e тестов** на полный пайплайн — все expensive-тесты (`-m expensive`) пропускаются по умолчанию.
- **Нет SLA/SLO документа.** Стоимость прогона в README/ONEPAGER указана (~$2.7 winner / $3.1 opus-only), но без замеренного p95/p99 latency.

---

## 6. Бюджет / экономика прогона

Из `config.py::ModelConfig` и bake-off:

| Шаг | Модель | Стоимость/вызов | Заметки |
|---|---|---|---|
| §1 Prompt Master | GPT-4o | ~$0.02 | Bake-off winner: 100/100, в 9× дешевле Opus ($0.18) |
| §2 Intake (LLM fallback) | Haiku 4.5 | переменная | Сначала бежит детерминированный парсер таблиц (бесплатно) |
| §3 Analyzer | Opus 4.7 | дорогой | Только Opus прошёл floor 70/100 (Sonnet — 60) |
| §4 Synthesizer | Sonnet 4.6 | средний | Bake-off winner (88/100), 36% дешевле Opus, 2-3× быстрее |
| §5 Critic | Opus 4.7 | дорогой | Зафиксирован на Opus (FP-риск слишком высок) |

**Итого ~$2.69 winner-конфигурация / ~$3.06 Opus-everywhere**, разница 12% в пользу winner.

Драйверы переменной части — длина исходников, число retry в Critic-петле, выбор Opus-only через UI-тумблер.

---

## 7. Git state и ветки

```
* v4.5 (текущая, 24 коммита поверх v4, не запушено)
  v4 (16 коммитов поверх v3)
  v3 (legacy)
  + bakeoff-v45, fix-synth-400, language-lint, night/track-b, night/track-c,
    schema-pipeline, fix/cost-tracking, feat/analyzer-single-followup,
    feat/docx-js-renderer, feat/docx-js-renderer-v2, intake-table-parser,
    consistency-v45, synth-bakeoff, ... (18+ веток)
  + worktree-agent-* (5 веток для cleanup)
remotes/origin: main, v3, codex/* (отстают от локальных)
```

Untracked: `.claude/`, `0c577602-07b8-42af-9f22-c93d0b9f74b0.pdf`, `ONEPAGER.md`. ONEPAGER.md обновлён сегодня и НЕ в индексе git.

**Главный риск** — вся работа v4.5 живёт только в локальной рабочей копии. Бэкап / push в origin не сделан.

---

## 8. Состав файловой структуры

```
smart-report-mvp-v3/  (бэкенд, Python)
├── smart_report/            ~5630 строк core
│   ├── orchestrator.py       v3 pipeline
│   ├── v4_orchestrator.py    v4 pipeline + v4.5 retry chain
│   ├── intake.py             987 строк, парсер + LLM fallback
│   ├── synthesizer.py        666 строк
│   ├── models.py             513 строк (Pydantic v2)
│   ├── synthesis_critic.py   311 строк
│   ├── data_audit.py         229 строк
│   ├── bibliography.py       261 строка
│   ├── i18n/                 language lint
│   ├── api/                  FastAPI (608 строк всего)
│   └── exporters/            DOCX/PPTX/MD/HTML/JSON
│       ├── docx_js/          Node.js + docx-js@9.6.1
│       └── docx_v4_consulting.py  1515 строк legacy
├── prompts/                  редактируемые промты ролей (md)
├── tests/                    290 тестов
├── eval/                     bakeoff + baseline артефакты
├── reference/                BRAINSTORM + spec + reference-отчёты
├── runs/                     сотни прогонов (в .gitignore)
└── scripts/                  bakeoff, render, retry скрипты

smart-report-mvp/frontend/    (Next.js 14.2 + React 18 + Tailwind)
├── app/                      v3, v4, v4/chat, login, library, settings, ...
└── components/v4/            V4Shell, Masthead, ModelPicker, Workspace, ...
```

---

## 9. Что нужно сделать перед аудитом / для аудита

### Минимум для честного аудита

1. **Запушить v4.5 в origin** — backup + видимость для аудитора. Сейчас всё локально.
2. **Пополнить OpenRouter** ($5–10) и прогнать ОДИН полный v4.5-цикл, чтобы получить наконец `final_report.json` с замерами по 5 ключевым метрикам (citation coverage, fact retention, language warnings, critical consistency, source count). Без этих чисел утверждение «v4.5 работает» — гипотеза.
3. **Зафиксировать `MEMORY.md`** — сейчас память врёт про число тестов (217 vs 290). Не критично для аудитора, но красный флаг.
4. **Cleanup веток** — `git worktree prune` + удалить мёртвые `worktree-agent-*` и слитые feature-ветки.
5. **Прогон `pytest -m expensive`** хотя бы один раз, с реальными ключами, чтобы убедиться что 2 deselected теста живы.

### Желательно перед аудитом

6. **Удалить `docx_v4_consulting.py`** или явно пометить его deprecated — 1515 строк дублирующего кода.
7. **Архивировать `runs/`** — сейчас занимают много места, мусорят `git status`.
8. **Один e2e интеграционный тест** на полный v4-цикл с stub-LLM, чтобы регрессии ловились.
9. **Добавить минимальный README-раздел про deployment** (даже «не задеплоено, требует X, Y, Z»).

---

## 10. Резюме одной строкой

> **Код v4.5 готов и зелёный по тестам (288/290), но финальная валидация на живых LLM-данных не сделана из-за исчерпанных credits. Деплоя нет, БД нет, auth нет — это всё ещё MVP в активной разработке, не продакшн-сервис. Ветка `v4.5` содержит 24 коммита, не запушенных в origin — главный операционный риск.**
