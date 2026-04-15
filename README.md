# Smart Report MVP

Персональный аналитический движок: цель → матрица доменов → проработанные блоки → кросс-доменные связи → DOCX / MD / JSON.

Архитектура — четыре агента на чистом Python + asyncio, без фреймворков:

- **Planner** — цель → матрица доменов/слоёв + конкретные поисковые задания
- **Scout** (×N параллельно) — задание → сырые находки с источниками (Perplexity или mock)
- **Analyst** — находки по ячейке → мини-отчёт (ACH + Key Assumptions Check)
- **Bisociator** — блоки → кросс-доменные связи
- **Summarizer** — Executive Summary + приоритизированные шапки блоков

Поверх ядра — FastAPI и Next.js фронтенд для «дирижирования» исследованием в реальном времени.

## 1. Установка

```bash
cd smart-report-mvp

# Python-ядро
python -m venv .venv
source .venv/Scripts/activate          # Windows (bash / Git Bash)
# .venv\Scripts\activate               # Windows (cmd / PowerShell)
# source .venv/bin/activate            # Linux / macOS
pip install -r requirements.txt

# Ключи
cp .env.example .env
# в .env: OPENROUTER_API_KEY=...  и (опционально) PERPLEXITY_API_KEY=...
# Без PERPLEXITY_API_KEY или с USE_MOCK_SEARCH=1 поиск работает в mock-режиме.

# Фронтенд
cd frontend
npm install
cd ..
```

## 2. CLI

Один проход:

```bash
python cli.py "какие мировые тренды 2025-2030 повлияют на жилое строительство в России"
```

Результаты сохраняются в `output/<timestamp>-<slug>.{md,json,docx}`.

Второй проход (поверх уже сохранённого JSON):

```bash
python cli.py --from-json output/....json --deepen "Демография / Городское ядро" --focus "что именно не хватает в блоке"
python cli.py --from-json output/....json --add-domain "Логистика" --layers "Доставка, Склад, Город"
python cli.py --from-json output/....json --connect "Демография" "Технологии"
```

## 3. Веб-сервис

### 3.1 Backend (FastAPI)

```bash
# в корне smart-report-mvp, при активированном .venv
uvicorn api.main:app --reload --port 8000
```

Документация API: <http://localhost:8000/docs>

Основные эндпоинты:

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/research` | Старт исследования: `{goal}` → `{id}` (фоновая задача) |
| GET | `/api/research/{id}/stream` | SSE-стрим прогресса |
| GET | `/api/research/{id}` | Полный JSON отчёта + статус |
| POST | `/api/research/{id}/deepen` | `{cell, focus}` — углубить блок |
| POST | `/api/research/{id}/add-domain` | `{name, layers?}` или `{freetext}` |
| POST | `/api/research/{id}/connect` | `{block_a_cell, block_b_cell}` |
| POST | `/api/research/{id}/dismiss` | `{cell}` — скрыть блок |
| GET | `/api/research/{id}/export/{md\|docx\|pptx\|json}` | Скачать экспорт |
| GET | `/api/reports` | Список сохранённых отчётов |

Хранилище отчётов — JSON-файлы в `reports/{id}.json`. `id` — `YYYYmmddTHHMMSS-<slug>`. DOCX/PPTX эндпоинты отвечают 404 с понятным сообщением, пока файлы не сгенерированы соответствующим экспортером.

### 3.2 Frontend (Next.js)

```bash
cd frontend
npm run dev
# → http://localhost:3000
```

Фронт ходит в API через rewrite на `http://localhost:8000`. Переопределить можно переменной окружения `NEXT_PUBLIC_API_BASE` (берётся при сборке).

Страницы:

- `/` — лендинг.
- `/new` — новый запрос. Форма цели → запускает исследование и перебрасывает на `/report/[id]`.
- `/report/[id]` — главная страница: Executive Summary, Metrics Dashboard, тепловая карта матрицы, карточки блоков (сворачиваемые, с «Копай глубже» и «Не интересно»), кросс-доменные связи, правая панель с D3-графом связей и живым потоком SSE-событий. Кнопки «Добавить домен» и «Свяжи это с тем».
- `/library` — список всех сохранённых отчётов, поиск по цели.

Стек: Next.js 14 App Router, React 18, Tailwind, Framer Motion для анимаций, D3.js для графа связей, lucide-react для иконок. Светлая и тёмная темы (переключатель в хедере, предпочтение системы по умолчанию).

## 4. Переменные окружения (`.env`)

| Ключ | По умолчанию | Комментарий |
|---|---|---|
| `OPENROUTER_API_KEY` | — | обязательно для LLM-вызовов |
| `PERPLEXITY_API_KEY` | — | опционально, иначе работает mock-поиск |
| `USE_MOCK_SEARCH` | `0` | `1` — принудительно mock-режим |
| `PLANNER_MODEL` | `anthropic/claude-opus-4.1` | OpenRouter slug |
| `SCOUT_MODEL` | `anthropic/claude-haiku-4.5` | |
| `ANALYST_MODEL` | `anthropic/claude-sonnet-4.5` | |
| `BISOCIATOR_MODEL` | `anthropic/claude-opus-4.1` | |
| `SCOUTS_PER_CELL` | `3` | |
| `MAX_PARALLEL_SCOUTS` | `8` | |
| `MAX_PARALLEL_ANALYSTS` | `4` | |

## 5. Структура

```
smart-report-mvp/
├── prompts/              # главные поверхности итерации
├── agents/               # тонкие обёртки над LLM
├── models.py             # pydantic-контракты
├── orchestrator.py       # run_research / deepen_cell / add_domain / connect_domains
├── export.py             # md / json / docx (baseline)
├── search.py             # Perplexity + mock
├── llm.py                # OpenRouter клиент
├── cli.py                # CLI entry point
├── api/
│   └── main.py           # FastAPI обёртка, SSE-стриминг
├── frontend/             # Next.js + Tailwind + D3 + Framer Motion
│   ├── app/
│   │   ├── page.tsx
│   │   ├── new/page.tsx
│   │   ├── library/page.tsx
│   │   └── report/[id]/page.tsx
│   ├── components/
│   │   ├── BlockCard.tsx
│   │   ├── DeepenForm.tsx
│   │   ├── AddDomainForm.tsx
│   │   ├── ConnectionsGraph.tsx
│   │   ├── ConnectionCard.tsx
│   │   ├── ExecutiveSummary.tsx
│   │   ├── MetricsDashboard.tsx
│   │   ├── HeatmapMatrix.tsx
│   │   ├── MatrixEditor.tsx
│   │   ├── ExportButtons.tsx
│   │   └── ThemeToggle.tsx
│   └── lib/
│       ├── api.ts
│       └── useSSE.ts
├── reports/              # {id}.json (+ .docx / .pptx когда экспортёры готовы)
└── output/               # вывод CLI
```

## 6. Что НЕ делает MVP

Синтез цепочек логики, автоматический фильтр банальности, evaluate-петли над промптами, release gate.
Это — твоя ответственность; движок даёт материал, ты выбираешь что ценно и куда копать дальше.
