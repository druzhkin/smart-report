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

---

## What changed in smoke 11 (2026-04-18, afternoon)

**Planner теперь явно выбирает retrieval-инструмент.** До этой итерации `orchestrator.py` содержал hardcoded enrichment gate (`_should_enrich_with_erz` + `_enrich_with_erz`), который подмешивал Jina Reader → ЕРЗ-парсер post-Scout только для ячеек, где target_sources содержат `erzrf.ru` И query упоминает `срок/перенос/ввод`. Это работало, но было скрытым контрактом: Planner по-прежнему думал, что единственный инструмент — `search`.

**Что теперь:**
- `ScoutTask` в `smart_report/models.py` получил `strategy: Literal["search", "extract"] = "search"` и `target_urls: list[str] = []`. `model_validator` запрещает `strategy="extract"` без URL.
- `smart_report/scrape.py` — публичная `extract_via_jina(target_urls, *, focus, cell_id, log_dir) -> list[Finding]`. Регистр source-specific парсеров через `_pick_parser(url)` (сейчас только `erzrf.ru` Moscow-top → ЕРЗ-regex). Остальные URL → generic-wrapper с первыми 2 KB markdown как `source_type="other"` finding.
- `smart_report/orchestrator.py` — `_gather_findings(cell)` маршрутизирует на `extract_via_jina` при `strategy="extract"`, иначе на `scout(task)`. Hardcoded ЕРЗ-gate удалён полностью, версия бампнута до 0.4.0.
- `smart_report/planner.py` — прокидывает `strategy`/`target_urls` из LLM JSON в `ScoutTask`. Если LLM эмитнул `strategy="extract"` без URL, спускаемся на `"search"` (soft-degrade вместо падения).
- `prompts/planner.md` — добавлены правило 9 (выбор стратегии с критериями a/b/c), нейтральный пример (market-cap сектора X), anti-patterns, обновлён output schema. В примере matrix у `construction/deadline-discipline` теперь `strategy="extract"` + `target_urls=[...]` как template.

**Контрактные тесты:** `tests/test_orchestrator_routing.py` — 4 теста (extract маршрутизирует на Jina, search — на Perplexity, валидатор модели ловит extract без URL, default search). Итого 29/29 green.

**Sanity run (`runs/20260418T140637Z-...`):**
- Planner emit'нул ровно одну extract-ячейку: `construction/deadline-discipline` с URL `https://erzrf.ru/top-zastroyshchikov/moskva?topType=0` — именно ту, для которой есть source-specific parser.
- **10/10 per-developer ЕРЗ findings landed** через общий `extract_via_jina` (не через гейт): ПИК 4.09%, Самолёт 68.05%, MR 5.65%, ДОНСТРОЙ 0%, ФСК 11.39%, А101 49.3%, Level 8.67%, АБСОЛЮТ 23.02%, ЛСР 25.65%, Страна 29.07%. Порог приёмки был ≥7, выдали 10.
- 13/14 ячеек остались на `strategy="search"` (Perplexity) — Planner НЕ злоупотребляет extract, как и хотели.
- Cross-links 2 (smoke 10 было 4) — Bisociator не трогали, флуктуация в рамках шума. Не регрессия по DoD.
- null strongest_number: 5/14 (smoke 10 было 4/14) — шум.

**Next natural step:** sanity-check универсальности на вопросе из другого домена (не про девелопмент), чтобы поймать скрытый подгон под ЕРЗ. Без этого механизм может работать только на той индустрии, где уже есть source-specific parser. Если generic-wrapper на произвольной странице даст хотя бы 50% цитируемости — значит обобщение честное.

**Backlog (не трогать до universality-check):**
- Bisociator top-K / prompt-тюнинг (вчера было 4 линка, сегодня 2 — сначала убедиться что это шум, не регрессия)
- A/B judge smoke 10 vs smoke 11 на 5 метрик baseline'а
- Регистр source-specific парсеров для второго URL (условно Rosstat / SimilarWeb / Crunchbase) — добавлять по мере появления доменных задач

---

## Завтра — universality check (smoke 12)

**Вопрос (выбран заранее, чтобы утреннее «я» не подбирало бессознательно близкий к недвижимости):**

> «Что сейчас происходит с рынком электросамокатов в российских городах-миллионниках?»

**Почему этот, а не два других кандидата.** Кикшеринг — это домен, где *одновременно* присутствует и нарративный срез (регуляторные конфликты, аварийность, отношения с мэриями), и потенциально-extract'абельный срез (Whoosh — публичный на MOEX, годовые отчёты содержат MAU, число поездок, unit-экономику). Это даёт проверку **обеих веток**: Planner должен выбрать `search` для нарративных ячеек (аварийность, регуляторика, конкуренция) И хотя бы одну `extract` для Whoosh reporting. Книжные магазины — почти чистый `search` (нет центрального реестра), стоматология — аналогично фрагментирована. Кикшеринг — единственный из трёх, который нагружает обе ветки routing'а.

**Порог приёмки (честный, калибровочный — НЕ «красиво»):**

1. **Planner sanity.** Матрица из 5–7 доменов, доменны ортогональны (не «Whoosh / Юрент / Яндекс.GO» — это эхо вопроса, как v2 делал с «бренд/скорость/продукт»). Каждая ячейка с числовой метрикой и единицей в query.
2. **Strategy split работает честно.** Planner выбирает `extract` минимум для одной ячейки, максимум для двух. Target_urls — конкретные URL, которые реально существуют (спот-чек 2 штуки). Если Planner выбрал `extract` для 0 или ≥3 ячеек — промпт-контракт не универсален, а подогнан под ЕРЗ.
3. **Retrieval приносит что-то осмысленное.** ≥ 7 из 14 ячеек (т.е. 50%) имеют `strongest_number != null` + валидный URL. Не требую 10/14 как на эталоне — домен мне хуже знаком, я не отличу «малодоступные данные» от «pipeline сломан». 50% — достаточный сигнал что механизм не завалился.
4. **Generic extract fallback отдаёт что-то.** Если Planner выбрал extract на non-erzrf URL, `_extract_generic` возвращает непустой snippet, Analyst его цитирует (source_type=other). Это валидация того, что registry-подход не хрупок.

**Если пороги не сходятся — диагностировать в таком порядке:**
1. Planner вернул бред → промпт под ЕРЗ заточён, обобщать.
2. Planner выбрал `search` везде → правило 9 слишком консервативно, ослабить критерии a/b/c.
3. Planner выбрал `extract` с фантомным URL → добавить в anti-patterns «не выдумывай URL, если не видел его в обучающих данных — предпочитай search».
4. Retrieval пустой у >50% ячеек → проблема не в pipeline, а в `target_sources` TLD для этого домена; выбранные TLD Perplexity не знает. Не регрессия split'а.

**Команда:**
```
PYTHONUTF8=1 REQUEST_TIMEOUT_S=240 python run.py "Что сейчас происходит с рынком электросамокатов в российских городах-миллионниках?" > runs/_smoke_12.log 2>&1
```

---

## Open question — после universality check, не раньше

**«Как мы узнаем, что Bisociator реально недо-селектит, а не просто работает на разреженном материале?»**

Висит с утра. Сейчас ответа нет, потому что у нас один прогон одного вопроса. Правильный момент задать этот вопрос — после smoke 12, когда будут два прогона на двух разных доменах. Диагностика:

- Если smoke 12 даёт 2–3 cross-links (как смоки 9/11 на девелоперах) — Bisociator упирается в потолок, top-K или prompt действительно нужен, это реальная задача.
- Если smoke 12 даёт 5–7 cross-links — текущая схема работает, 2–3 на девелоперах были специфичны для того насколько сильно пересекаются метрики между ячейками на том материале. Bisociator трогать не нужно.
- Промежуточный случай (4) — неопределённо, нужен третий домен.

Это решение зависит от цифры, которую получим завтра. Не тюнить Bisociator до этого момента.

---

## Step 1 — API + фронт-интеграция (2026-04-18)

**Что сделано:**

- **Part A — Summarizer (5-й агент).** `summarizer.py` + `prompts/summarizer.md`. Выход — `ExecutiveSummary {main_finding, top_numbers[], key_tensions[], open_questions[]}`. `Report.summary` заполняется в конце `orchestrator.run`. Экспорт в markdown рендерит summary над матрицей. Mock в `_stub_data.MOCK_EXECUTIVE_SUMMARY`.
- **Part B — EventEmitter.** `events.py` — Protocol + NullEmitter + ListEmitter. `orchestrator.run(..., emitter=...)` + `_cell_pipeline(..., emitter=...)` эмитят события на границах фаз. Сообщения совместимы с текущими regex фронта: scout `[cell_id] ...`, analyst `Блок ... готов`, bisociator `Найдено связей: N`. Фазы в whitelist: `status|planner|scout|analyst|bisociator|summarizer|done|error`.
- **Part C — FastAPI.** `smart_report/api/` — `main.py` + `jobs.py` + `models.py`. Эндпоинты: `POST /api/research`, `GET /events` (long-poll, clamped [0,30]s), `GET /stream` (SSE fallback), `GET /api/research/{id}` (с on-disk fallback), `GET /api/reports`, `GET /health`. Джобы в `dict[id, Job]` с `asyncio.Event` на каждую. CORS whitelist :3000-:3003.
- **Part D — Фронт.** В main-репе `smart-report-mvp`: `frontend/lib/apiV3.ts` (типы + fetch), `frontend/lib/useV3Events.ts` (long-poll hook), `frontend/app/v3/new/page.tsx` (форма), `frontend/app/v3/report/[id]/page.tsx` (live feed + render). Абсолютные URL к `NEXT_PUBLIC_V3_API_BASE` (default :8010) — не трогают `next.config.mjs` rewrite. Side-by-side с v2.
- **Part E — Smoke.** Эталонный вопрос («Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?») прошёл end-to-end за **209 s**: 7 доменов, 14 ячеек, 14 блоков, 83 находки суммарно, **2 cross-links**, executive summary с 5 top_numbers / 2 tensions / 5 open questions. Все 3 regex контракта зелёные (28 scout msgs, 28 analyst msgs, 2 bisoc msgs). Фронт-страницы `/v3/new` и `/v3/report/{id}` отдают 200 с корректным контентом.

**Тесты:** 47/47 green (6 API + 9 events + остальное).

**Commits:**
- v3: `daffbf1 feat(api+summarizer+events): Step 1 A+B+C`
- main: `1957557 feat(frontend): v3 API client + side-by-side /v3/* routes` + `CLAUDE.md`

**Known issues / punch list:**

1. **Bisociator всё ещё упирается в 2 cross-links** на этом материале. Это совпадает со «Смок 9/11 давали 2–3, ceiling?». Universality check не был частью Step 1 — нужен отдельный прогон на другом домене.
2. **2 дублирующих джоба** запустились из-за того что первая попытка скрипта упала на UnicodeEncodeError *после* POST, POST к API успел пройти. В отчёты попали оба. API не имеет cancel endpoint — backlog.
3. **Browser E2E** не сделан — проверил только через `curl` к фронт-страницам и прямые вызовы API. Страницы компилируются и отдают 200, но клик-флоу в реальном браузере Claude-у недоступен. Оставил HTML-snapshot'ы `_frontend_v3_new.html` и `_frontend_v3_report.html` в main-репе.
4. **Windows proxy-trap** — системный HTTP proxy перехватывает localhost. `curl --noproxy '*'` обходит. Добавил в `memory/windows_bash_utf8_curl_trap.md` ранее (трап для UTF-8), но proxy — отдельный. Фронт в Node не страдает, curl из bash — страдает.
5. **CORS** широкий (3000-3003) — для dev ок, для продакшна сузить.
6. **Frontend landed on :3003** — первый вакантный порт. `.env.local` с `NEXT_PUBLIC_V3_API_BASE=http://localhost:8010` для продакшна.

**Не сделано (из утреннего плана) и почему:**
- Step 2 (если был задуман) — не начат, Step 1 съел выделенный бюджет времени.
- Bisociator tuning — осознанно отложен до universality check на втором домене (см. Open question выше).

