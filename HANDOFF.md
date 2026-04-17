# HANDOFF — Smart Report MVP v3, night 01

**Session:** 2026-04-18, 01:46 → 03:00 (~75 min real, parallel across 4 agents)
**Total spent:** ~$1.66 (of $20 cap) — $0.10 Track B + $1.08 Track C + $0.48 Track D + $0 Track A
**Status:** all four tracks DoD green. Tests pass. Dry-run works. Zero reference-pack/hallucination shortcuts shipped.

---

## Главный вопрос сессии — ОТВЕТ

> **«Где сидит главный разрыв между нами и OpenAI DR — в ретривале, декомпозиции, синтезе или бисоциации?»**

**В РЕТРИВАЛЕ.** Эмпирически подтверждено Track B: на диагностической задаче OpenAI DR нашёл 4/4 точных числа ЕРЗ по топ-5 девелоперам (Донстрой 0%, MR 5.65%, Level 8.67%, Эталон 35.46%). Лучшая из пяти наших стратегий (B2 — sonar-pro + `search_domain_filter=['erzrf.ru']`) дала **1/4 accurate** — и то нестабильно (повтор дал 0/4). B3 parallel decomposition без anti-hallucination guard оказалась **хуже наивной B1**: hit rate вырос до 2/5, но accuracy упала до 0/4 — модель начала выдумывать правдоподобные проценты. erzrf.ru — Angular SPA, B4 direct fetch бесполезен без JS-render.

**Следствие:** утром в первую очередь подключаем второй слой поиска — Firecrawl с JS-render на обнаруженных URL. Без этого нет смысла прогонять полный end-to-end — получим v2-подобный артефакт с «нет данных» на цифрах.

---

## Что лежит в репо

### Commits на `main`

```
6372919 feat(d): role prompts v1 + planner iteration
020e6d4 feat(c): baseline eval on 3 reports × 5 metrics
8f855d3 feat(b): scout bakeoff — 5 retrieval strategies on ЕРЗ task
55dac6d feat(a): skeleton — async pipeline, pydantic v2 models, dry-run mocks
24d1ae3 chore: initialize v3 repo with references and skeleton directories
```

### Track A — skeleton (green)

- `smart_report/` — 11 модулей, async, max 154 строк
- `tests/` — 9/9 passed (pydantic validation + e2e dry-run + no-network guard)
- `run.py --dry-run "..."` → валидный Report JSON с 4 блоками + 2 cross-links
- LLM/search wrappers готовы, **реальные вызовы НЕ подключены** — в dry-run всё идёт через `_stub_data.py`
- На Windows: `PYTHONUTF8=1 python run.py ...` обязательно для cyrillic argv

### Track B — scout bakeoff

- `eval/scout_bakeoff.md` — таблица 5 стратегий × 5 метрик + verdict
- `scripts/scout_bakeoff/` — 5 исполняемых стратегий (b1..b5) + runner + raw JSON
- Ground truth из `reference/openai_dr_report.md`: Донстрой 0%, MR 5.65%, Level 8.67%, Эталон 35.46%
- **Рекомендация для v3 default:** B2 (sonar-pro + domain filter) как baseline, **ОБЯЗАТЕЛЬНО** добавить Firecrawl JS-render на URL'ы из B2 перед тем как класть результат в Finding
- Стоимость полного прогона: $0.10

### Track C — baseline eval

- `eval/baseline.md` — таблица 3×5 + пустой 4-й столбец для нас
- `scripts/baseline_eval/{judge,run_baseline}.py` + `manual_checks.md`
- LLM-judge: Sonnet 4.6, 15 structured calls × $0.07 avg, $1.08 total
- Calibration: 3/3 manual spot-checks PASS (2 URL via WebFetch + 1 grep на v2)

**Aggregate scores (Perplexity / OpenAI DR / v2):**

| Metric | Perplexity | OpenAI DR | v2 |
| --- | --- | --- | --- |
| Coverage /10 | 7 | **10** | 1 |
| Groundedness % | **80** | **80** | 5 |
| Honesty /100 | **82** | 72 | 52 |
| Non-triviality (lower=better) | **5** | 7 | 18 |
| Cross-domain | 5 | **9** | 4 |

**Surprise:** v2 honesty = 52 несмотря на постоянный рефрен «отсутствуют данные» — judge справедливо наказал паттерн «признать отсутствие данных, а потом выдумать коэффициент 0.5-0.7 из международного базиса». Вот ровно то, что мы должны не повторить.

### Track D — promptcraft

- `prompts/{planner,scout,analyst,bisociator}.md` — 4 финальных черновика с обязательными anti-patterns (verbatim из v2)
- `prompts/_history/planner_v{1,2}.md` + raw outputs — оба прогона Opus на эталонном вопросе
- `prompts/PROMPT_NOTES.md` — разбор v1 vs v2
- **Verdict:** Planner v2 лучше. 7 доменов × 14 ячеек, конкретные numeric queries (HHI, NPS, LTV, absorption rate, средняя задержка в мес., стоимость машиноместа в млн ₽). v1 был vendor-heavy (Knight Frank/Metrium дублировались) + два `buyer/*` слоя схлопывались в один опрос.
- Встроенный в Planner anti-pattern: нельзя делать домены как `бренд/скорость/продукт` — это ленивое повторение вопроса
- Встроенный в Bisociator anti-pattern: `shared_variable` должна быть измеримой переменной с числом в обоих блоках, иначе нет CrossLink
- Стоимость: $0.48 (2 Opus run'а по ~6300 токенов)

---

## Утром: первые три шага (приоритетный порядок)

### Шаг 1 — Wire real calls in `smart_report/orchestrator.py` (~30 min)

Сейчас `orchestrator.run(..., dry_run=False)` технически существует, но не прогонялся на живых API. Нужно:
1. В `llm.py`: убрать `mock=True` shortcuts, оставить реальный OpenRouter httpx-вызов. Логирование в `runs/<ts>/llm_log.jsonl` уже готово.
2. В `search.py`: аналогично убрать mock-ветку. Перевести default на B2 стратегию из bakeoff (sonar-pro + `search_domain_filter`).
3. Убедиться что Semaphore(4) держит параллелизм на Analyst'е.
4. Прогнать: `python run.py "Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?"` — без `--dry-run`.

### Шаг 2 — Добавить Firecrawl JS-render layer в Scout (~45 min)

Критично для numeric queries. Без этого erzrf.ru цифры не вытащим, и нас разгромит повтор bakeoff'а.

1. Добавить `firecrawl-py` в `pyproject.toml` deps.
2. `smart_report/search.py`: после Perplexity B2 вызова — взять URL'ы из findings, прогнать через Firecrawl scrape с `js_render=true`, доставать `{claim,number,verbatim_quote}` из отрендеренного HTML.
3. 2-pass consensus: если B2 вернул число X, проверить на странице через Firecrawl. Если совпадает → high confidence, если нет → `"нет данных"`, а не компромисс.
4. Бюджет: Firecrawl ~$0.005/scrape × 10 URL/запрос × 14 cells = ~$0.70/run.

### Шаг 3 — Первый full end-to-end + закрыть столбец 4 в baseline.md (~45 min)

После Шагов 1-2:
1. `python run.py "Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?"`
2. Ожидаемый cost: ~$3-5 (Planner Opus $1-2, 14 × Scout sonar-pro $0.20, 14 × Analyst Sonnet $1-2, Bisociator Opus $1, Firecrawl $0.70).
3. Прочитать `runs/<ts>/report.md`, прогнать то же `scripts/baseline_eval/run_baseline.py` на нашем отчёте → заполнить `_TBD_` столбец в `eval/baseline.md`.
4. Если Coverage < 6 или Groundedness < 50% → проблема в Planner (не те домены) или Scout (Firecrawl не сработал) — смотреть логи.

### Шаг 4+ (после baseline сравнения)

- Если мы обгоняем v2 по всем метрикам и подбираемся к OpenAI DR на Coverage/Groundedness — идём вглубь по Bisociator (это наш единственный принципиальный differentiator; OpenAI DR его не делает).
- Если мы не отрываемся от v2 на Groundedness — добавляем второй источник (Tavily или Brave SERP API) параллельно Perplexity. Firecrawl-слоя может быть недостаточно.
- Если Coverage проседает — итерируем Planner промпт (v3, v4).

---

## Сюрпризы и риски на утро

1. **Python 3.11, не 3.12.** Track A установил `requires-python = ">=3.11"`. Код 3.11-compatible, но если где-то всплывёт `type | None` в runtime (не только annotation) — может стрельнуть. Тесты все зелёные, но под нагрузкой смотреть.

2. **Windows cyrillic argv.** `click` на Windows читает argv как mbcs. Фикс: `PYTHONUTF8=1 python run.py ...` или запуск через Python API. Файлы на диске всегда UTF-8 (verified).

3. **Perplexity нестабильна на повторе.** Track B обнаружил: `search_domain_filter=['erzrf.ru']` на одном и том же запросе дал разные результаты (1→0 accurate). Требует 2-pass consensus или явного retry-with-validation.

4. **erzrf.ru — Angular SPA.** Без JS-render сайт выдаёт пустой скелет. Firecrawl-слой критичен, не опционально.

5. **B3 parallel decomposition без guard опаснее B1 наивной.** Урок для Planner: scout-задания должны быть достаточно конкретны, чтобы Scout сразу говорил «нет данных», а не выдумывал.

6. **Track C LLM-judge калиброван на 3/3 spot-checks**, но выборка мала. При заполнении столбца 4 для v3 прогнать calibration ещё раз, особенно на Groundedness — это метрика, где judge может быть обманут красиво оформленной hallucination.

---

## Бюджет на утро (прикидка)

| Шаг | Cost estimate |
| --- | --- |
| Wire real calls + smoke | $0.10 (1-2 тестовых вызова) |
| Firecrawl layer + retest | $0.70 (Firecrawl) + $0.10 (Perplexity) |
| First full end-to-end | $3-5 |
| Baseline eval на v3 | $1.08 (тот же скрипт что Track C) |
| **Итого утром** | **~$5-7** |

Осталось от $20 ночного бюджета: $18.34. На утро с запасом.

---

## Что НЕ сделано (отложено сознательно)

- Фронтенд — не трогали, по брифу отложено
- Экспорт в DOCX — позже, после первых честных end-to-end
- Bisociator на реальных данных — нужны настоящие блоки, появятся после Шага 3
- Интерактивный редактор матрицы — по брифу, на v2.0 продукта
- Полный end-to-end с реальным ответом — Шаг 3 утром
- Tavily/Brave второй source — подключим только если Firecrawl не закроет Groundedness

---

## Ссылки на ключевые артефакты

- `eval/scout_bakeoff.md` — ответ на главный вопрос сессии
- `eval/baseline.md` — таблица, где мы пока с пустым столбцом
- `prompts/planner.md` — лучший из двух Planner draft'ов
- `prompts/PROMPT_NOTES.md` — история итерации
- `reference/openai_dr_report.md` — эталон, который обгоняем
- `tests/` — 9/9 green, `PYTHONUTF8=1 python -m pytest tests/ -q`
- `runs/` — gitignore'd, появится когда прогоним реальный end-to-end

Удачи утром.
