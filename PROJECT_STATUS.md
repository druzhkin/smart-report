# Smart Report — статус проекта

_Срез на 2026-04-15. Живой документ — обновлять при значимых изменениях._

---

## 1. Что это

Deep-research SaaS. Пользователь вводит цель («как ИИ изменит персональную медицину в ближайшие 5 лет»), система запускает multi-agent пайплайн на Claude, собирает источники через Perplexity/Firecrawl, и выдаёт структурированный отчёт в `md / docx / pptx / json`.

Позиционирование: **«Perplexity-on-steroids»** — не одна LLM-выжимка, а матрица доменов × слоёв, с bisociation (кроссовыми связями между блоками) и честной картой пробелов/допущений.

Репозиторий `smart-report-mvp` — чистый переписанный MVP после того, как v2 (`smart-report`) стал un-fixable.

---

## 2. Архитектура

### 2.1 Backend (Python 3.12)

Монолитный async-оркестратор без фреймворков. Плоские файлы, без `pyproject.toml`.

```
cli.py              # локальный запуск: python cli.py "цель" → отчёт в reports/
run_overnight.py    # пачка задач + авто-эвалуация через evaluator.py
orchestrator.py     # planner → scouts → analysts → bisociator → summarizer
                    # + deepen_cell / add_domain / connect / dismiss
models.py           # pydantic: Matrix, CellPlan, ScoutTask, Block, Connection, Report
agents/             # 6 промпт-агентов (planner, scout, analyst, bisociator,
                    #                     summarizer, deepener, domain_expander)
prompts/            # .md системные промпты для каждого агента
search.py           # Perplexity → Firecrawl → DDG chain
llm.py              # AWstore клиент (OpenAI SDK, base_url=api.awstore.cloud)
                    # + cost meter (token accounting)
evaluator.py        # 7-метрик автоэвалуация отчёта
api/main.py         # FastAPI: /api/research (POST+SSE), /api/reports,
                    #         /api/research/{id}/(deepen|add-domain|connect|dismiss|export/*)
export_docx.py      # docx-рендер с вшитой матрицей, heatmap, графом связей
export_pptx.py      # pptx-презентация по тем же данным
infographics.py     # matplotlib: матрица, heatmap, граф связей → PNG
```

### 2.2 Frontend (Next.js 14, React 18, Tailwind 3)

```
frontend/app/
  layout.tsx            # Sidebar aura (Inter + Newsreader serif)
  new/page.tsx          # Intake: textarea + depth picker + examples
  report/[id]/page.tsx  # Viewer с матрицей, блоками, connections
  library/page.tsx      # Список прошлых отчётов
  globals.css           # zinc-палитра + design tokens
frontend/components/    # ExecutiveSummary, BlockCard, ConnectionsGraph (d3),
                        # MatrixEditor, HeatmapMatrix, DeepenForm, AddDomainForm…
frontend/lib/
  api.ts                # thin fetch-клиент
  useSSE.ts             # progress stream subscriber
frontend/design/
  aura-reference.html   # живой референс визуального стиля
```

### 2.3 Деплой

- **Railway** project `df6c3087-599f-4a6b-819f-28fda05dfba0`, production.
- Dual-process Dockerfile: `uvicorn api.main:app` на `:8000` + `next start` на `$PORT` (8080).
- **Volume** `smart-report-volume` смонтирован в `/app/reports` — отчёты и `{id}.status.json` sidecars переживают рестарт контейнера.
- URL: `https://smart-report-production.up.railway.app`.

---

## 3. Пайплайн: как рождается отчёт

```
goal
  │
  ▼
planner (opus-4.5)           → Matrix: 3–5 доменов × 2–4 слоёв + CellPlan per cell
  │                            (каждый с query_focus + source_hints)
  ▼
scouts (haiku-4.5) ×N        → для каждой ячейки: N параллельных поисковых запросов
  │                            через Perplexity/Firecrawl → ScoutResult[findings]
  ▼
analysts (sonnet-4.5) ×cells → синтез per-cell: Block{findings, gaps, key_entities,
  │                            assumptions}
  ▼
bisociator (opus-4.5)        → пары блоков → Connection[domains, shared_entity,
  │                            nature, anchors, novelty]
  ▼
summarizer (sonnet-4.5)      → Executive Summary + matrix_table_md +
  │                            top_findings, top_connections, key_gaps
  ▼
render                       → md / json / docx / pptx + инфографика (matrix, heatmap,
                               connection graph)
```

**Стоимость** одного отчёта в Standard-глубине: **$6–8 USD-list** / **≈$2–3 реально** (AWstore = 3× дешевле).

**Длительность**: 60–120 минут на Standard (планер 1 цель × 12 ячеек × 3 scouts ≈ 130 LLM-вызовов).

---

## 4. Что работает

### 4.1 Полный pipeline локально (через `cli.py` и `run_overnight.py`)
- Overnight запуск из 3-х задач 15 апреля: **все 3 успешно отрендерены** (`reports/`).
- Конкретно сохранены: `20260415-world-trends-housing`, `20260415-analytical-engine`, `20260415-premium-buyer-values` — каждая в 4 форматах + 4 инфографики (matrix/graph/metrics/heatmap PNG).

### 4.2 Рендер
- Newsreader-serif docx с вшитой матрицей, heatmap, связями. Выглядит editorial.
- PPTX с развернутой структурой, не «буллет-слайды».
- PNG-инфографика через matplotlib (матрица × heatmap × network graph).

### 4.3 LLM стек
- **AWstore** как Anthropic-прокси: стабильно, opus-4.5 / sonnet-4.5 / haiku-4.5 доступны. 3× дешевле официалки.
- Token accounting в `llm.py::meter_snapshot()` — по каждому run видим реальный cost.

### 4.4 Search
- **Perplexity sonar-pro** — primary, работает отлично, возвращает LLM-синтез с citations.
- **Firecrawl `/v1/search`** — только что добавили как fallback. Даёт SERP + предварительно отскрейпленный markdown в одном вызове, локально протестировано (коммит `2046ebf`).
- **DDG HTML** — last-resort fallback. Хрупкий (rate-limits), но работает когда остальное упало.

### 4.5 API
- FastAPI + SSE streaming прогресса. Фронт подписывается через `useSSE` и обновляет экран в реальном времени.
- Status sidecar pattern: `{id}.status.json` на Volume переживает рестарт — GET по id возвращает актуальный статус даже если in-memory `JOBS` dict пуст.

### 4.6 Production деплой
- Railway build проходит стабильно, контейнер поднимается за 190ms.
- `PYTHONUNBUFFERED=1` — uvicorn и worker логи приходят в deploymentLogs без задержки (коммит `04178f8`).
- Volume-persistence: отчёты не теряются при редеплое.
- Health-check `/api/health` — зелёный.

### 4.7 Автоэвалуация
- `evaluator.py` — 7 метрик (exec_summary, concreteness, depth, bisociation, gaps, assumptions, banality) через Claude-judge.
- Последние скоры из overnight-прогона (15 апреля):
  - `world-trends-housing`: **41/70**
  - `analytical-engine`: **43/70**
  - `premium-buyer-values`: не посчитан в overnight_summary.json, но файл есть

### 4.8 Новый UI (aura)
- `/new` перенесён на editorial aura: depth 4-picker, Newsreader serif, zinc-палитра, ⌘+Enter submit. (коммит `163762d`, в билде на Railway).

---

## 5. Что **не** работает / работает плохо

### 5.1 Качество отчёта (главное)
- **exec_summary = 2/10** стабильно. Summarizer даёт воду вместо топ-менеджерского резюме.
- **concreteness = 5/10**. Мало цифр per-claim, хотя прописано требование.
- **depth = 6/10**. Analyst часто пересказывает один источник вместо синтеза 2+.
- **bisociation = 3–4/10**. Bisociator находит поверхностные связи (общая сущность ≠ настоящая новая идея).
- **gaps/assumptions = 9/10** — хорошо, честно признаёт пробелы.
- **banality = 7–8/10** — умеренно, но «тренд X растёт»-уровня выводов много.

### 5.2 Прогресс и долгие задачи
- Прогоны в prod занимают **30–120 минут** — пользователь не готов столько ждать без видимого прогресса.
- SSE работает, но стадии *внутри* scout/analyst не стримятся (нет progress-событий per-cell).
- **Sidecar status не детектит stuck jobs.** Если контейнер убили посреди работы (редеплой), в `.status.json` навсегда остаётся `running`. Нужен heartbeat + `abandoned` детект.

### 5.3 Upload материалов
- Кнопка «Прикрепить PDF/TXT» на `/new` **disabled** — endpoint не реализован. Пользователь не может подсунуть свои документы.

### 5.4 Viewer отчёта
- `report/[id]/page.tsx` — 274 строки со старого UI (матрица + блоки + connection graph). **Ещё не переведён на aura**. Выглядит как админка, не как editorial reader.
- Нет table-of-contents, нет citation chips с hover-preview источника, нет reading progress.
- Export-кнопки работают, но без dropdown-группировки.

### 5.5 Источники данных
- Подключены только 3 (Perplexity, Firecrawl, DDG). Для deep/exhaustive-tier этого мало.
- **Нет academic** (Semantic Scholar, arXiv, CORE) — при запросе «исследования X» возвращаются блог-посты вместо peer-review.
- **Нет primary stats** (Росстат, SEC EDGAR, Eurostat, WHO) — поэтому `concreteness` страдает.
- **Нет news API** — актуальность проседает на быстро меняющихся темах.
- **Нет патентов** (Google Patents / Lens.org) — для tech-trends критично.

### 5.6 Депth-tiers
- В UI есть 4 варианта (`light/standard/deep/exhaustive`), но **backend не различает их** — `startResearch(goal)` не принимает depth-параметр. Бюджет scout'ов фиксирован в `config.py`.

### 5.7 Cost control
- Нет бюджетного guard'а. Если планер построит 6×4 матрицу, прогон сожрёт $15+ без предупреждения.
- Нет UI-показателя «потрачено/осталось», хотя данные в `meter_snapshot()` есть.

### 5.8 Тесты
- Тестов **нет**. `_smoke_test.py` — просто запуск cli на одной цели. Нет unit-тестов ни на валидацию pydantic, ни на search fallback chain, ни на API-роуты.

### 5.9 Множественные пользователи
- Нет auth. Нет изоляции `reports/` по юзеру. Любой получает любой отчёт по id (id легко угадывается — `YYYYMMDDTHHMMSS-slug`).

### 5.10 Cancel/cleanup
- Нет способа отменить запущенный job. Pипуск в API → Volume заполняется мусором.
- Нет retention policy.

---

## 6. Метрики и стоимость (фактические)

| Задача | Длительность | LLM-cost (list) | LLM-cost (AWstore real) | Eval score |
|---|---|---|---|---|
| world-trends-housing | 72 мин | $8.15 | ~$2.72 | 41/70 |
| analytical-engine | 66 мин | $6.64 | ~$2.21 | 43/70 |
| premium-buyer-values | ~65 мин | $7.63 | ~$2.54 | — |

**Средняя экономика:** $2.5 real / отчёт. Ценообразование при 3× наценке = **$7.50** / отчёт, при 10× = **$25**. Perplexity Pro = $20/мес безлимитно, ChatGPT Deep Research = $20/мес + глубокие исследования. Чтобы выигрывать — нужно либо сильно качественнее, либо нишевать (corporate research, consulting).

---

## 7. Куда развивать (приоритеты)

### 🔥 Критичные — без них продукт не продаётся

1. **Качество отчётов +30%**
   - Переписать `summarizer.md` с жёстким шаблоном (3 тренда / 2 риска / 1 императив, строго < 300 слов).
   - В `analyst.md` — hard constraint: каждое утверждение = ≥2 независимых источника или помечать как «single-source claim».
   - В `scout.md` — требовать минимум 3 количественных факта с прямой ссылкой на первичный источник.
   - В `bisociator.md` — фильтр «поверхностные связи отклоняются», пример-few-shot с сильными vs слабыми bisociations.

2. **Прогресс-UX**
   - Стадийный SSE (planner_done, 12/24 scouts, 3/12 analysts, synthesizing) — уже знаем как.
   - Live preview исполнительного резюме по мере готовности, не ждать всей матрицы.
   - Heartbeat в sidecar + детект abandoned jobs (3 мин без update → `failed`).

3. **Depth tiers реально работают**
   - Прокинуть `depth` в `POST /api/research` → в `planner` (управляет размером матрицы) → в `_bounded_gather` (scouts per cell).
   - Бюджеты: light $1 / standard $3 / deep $8 / exhaustive $20 — с cost_guard перед запуском.

4. **Upload материалов**
   - `POST /api/materials` принимает PDF/TXT/URL.
   - Для URL → Firecrawl `/scrape`. Для файла → `pypdf` extract + chunk.
   - Материалы становятся источниками с приоритетом перед web.

### 🎯 Важные — кратно улучшают продукт

5. **Подключить primary-sources**
   - Semantic Scholar API (бесплатно, rate-limited) → `search_academic()`.
   - SEC EDGAR (бесплатно, для US-company research).
   - Росстат HTTP (для русскоязычных экономических запросов).
   - Роутинг в `planner`: по теме решает какой источник релевантен.

6. **Report viewer → aura**
   - Editorial рендер: Newsreader serif, sticky ToC, citation chips с hover-preview, source cards с domain favicon + date.
   - Reading progress bar.
   - Inline expand-research ("выбрать кусок текста → углубить").

7. **Multi-user**
   - Хотя бы Magic-link (одно поле email). Postgres для users + reports.isolation.
   - id'шники отчётов не guessable (добавить nanoid-суффикс).

### 💡 Дифференциаторы — конкурентное преимущество

8. **Библиотека шаблонов отчётов**
   - «Анализ конкурентов», «Market sizing», «Regulatory landscape», «Tech trends в индустрии». Каждый = планер-preset + рендер-шаблон.

9. **Continuous research**
   - Отчёт с подпиской: раз в неделю догоняет новые источники и выдаёт diff-апдейт «что нового с прошлой недели».

10. **API для B2B**
    - Consulting/research компании → платят $500/мес за 50 отчётов через API, встраивают в свой workflow.

11. **Explainability**
    - Каждая claim в отчёте → клик → цепочка «scout query → source chunk → analyst синтез». Доверие > красота для B2B.

### 🔧 Гигиена

12. **Тесты**
    - Unit: валидация pydantic-схем, search fallback chain (mock httpx), API-routes happy path.
    - Integration: один полный pipeline через `USE_MOCK_SEARCH`... ах нет, моки запрещены. Через реальный Perplexity с минимальным matrix (1 домен × 1 слой).
    - Eval-regression: CI запускает `run_overnight.py` на 3 заморозенных задачах, алертит если eval_total проседает >5 пунктов.

13. **Retention + cancel**
    - `DELETE /api/research/{id}` + `cancel`-событие в orchestrator.
    - Чистка `reports/` старше 30 дней (если нет auth — вообще 24 часа).

14. **Мониторинг cost**
    - Live `total_usd` в header во время работы job.
    - Алерт если отчёт стоит >2× медианы по его depth-tier.

---

## 8. Что делать следующим ходом

Если надо выбрать **одну вещь** — это **#1 (качество)**. Никакой UX и никакие источники не спасут отчёт который пишет банальности.

Конкретный первый шаг: прогнать golden-set из 5 задач через текущую систему + записать eval-скоры как baseline, переписать `summarizer.md` + `analyst.md` с более жёсткими constraints, прогнать тот же набор, сравнить. Цикл: 1 день.

Если готов потратить неделю — сделать **#1 + #3 + #5** параллельно: качество промптов + честные depth-tiers + 2 primary-source коннектора (Semantic Scholar + SEC). Это превращает MVP в что-то, что можно показать первым платящим.
