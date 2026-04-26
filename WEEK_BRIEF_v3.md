# WEEK BRIEF v3 — Valyu-first architecture + Exa/Tavily augmentation + Run 2 + Phase 4 prep

**Заменяет:** WEEK_BRIEF_VALYU.md (v1), WEEK_BRIEF_v2_VALYU_EXA_TAVILY.md (v2). Этот документ — единственный источник истины на неделю.

**Срок:** 7 дней автономной работы. Заказчик недоступен. Спорные вопросы решаешь сам по правилу «consistency over guess» и пишешь blocker в `BLOCKERS.md`.

---

## 0. Главный принцип архитектуры (read first)

**Valyu — БАЗОВЫЙ сервис, а не один из четырёх равных backend'ов.**

Это не маркетинговая формулировка, это архитектурная инвариант'а:

1. На любом домене, который Valyu покрывает (финансы / регуляторы / медицина / наука / EU+US правовая база) — Valyu — это **primary всегда**. Не «predпочтительно», а **always**.
2. Tavily, Exa, Perplexity — это **augmentation layer**, а не замена. Их роль:
   - Заполнить дыры там, где Valyu объективно слаб (русский локальный контекст — Perplexity).
   - Дать дешёвый general web там, где proprietary корпуса не нужны (Tavily basic).
   - Дать semantic search + structured grounded JSON там, где это экономит LLM-вызовы (Exa с `outputSchema`).
3. **Запрет на отказ от Valyu закреплён в коде.** Тест `test_valyu_is_primary_for_covered_domains` падает, если кто-то (агент, ИИ, человек) меняет matrix так, что Valyu перестаёт быть primary на покрываемых доменах. Этот тест НЕЛЬЗЯ удалять/мутировать ради «прохождения».
4. **Если Valyu API down — система деградирует, но не выкидывает Valyu из конфига.** Используется secondary как augment, в DOCX генерируется явный warning «Valyu unavailable during this run, results may lack proprietary corpus coverage». Не молчаливая подмена.

Любая работа на этой неделе должна оцениваться по вопросу «делает ли это Valyu-coverage сильнее». Если коммит этого не делает или ослабляет — он не попадает в `origin/v4.5`.

---

## 1. Контекст

Закрыта Phase 3. Главный win — STRONG distribution flip: Q1 EV 0→37, Q2 Moscow RE 0→24, Q3 EU DAC 23→64. Тесты 522 passed, 0 регрессий. Ветка `v4.5`, 10 коммитов поверх Phase 3 запушены в `origin/v4.5`.

OpenRouter остаток: **$18.50**. Backends — отдельный биллинг.

**Что НЕ сделано:**

1. **Run 2 — Qualitative Comparison** на Q1/Q2/Q3 — Phase 3 показала числовой сдвиг, но никто не читал DOCX глазами.
2. **Phase 4 brief** — пишется по итогам Run 2.

**Что добавляется этой неделей:**

3. **Valyu — глубокая интеграция как фундамент** (proprietary корпусы для финансы/мед/наука/регуляторов).
4. **Tavily** — drop-in cheap general web search для general/news доменов (там где Valyu не покрывает).
5. **Exa** — semantic backend с `outputSchema` для structured grounded ответов на технических/научных запросах (augment Valyu, не замена).

---

## 2. Credentials и режимы

(API keys стерты при сохранении в репо — см. .env)

### 2.1 Valyu (БАЗОВЫЙ)

```
API key:  $VALYU_API_KEY (in .env)
MCP URL:  https://mcp.valyu.ai/mcp?valyuApiKey=$VALYU_API_KEY
SDK:      pip install valyu (валидируй текущую версию)
Endpoint: /deepresearch (async, webhook или polling)
```

| Режим | Цена | Использование |
|---|---|---|
| Fast | $0.10 | Все продакт-вызовы и эксперименты |
| Standard | $0.25 | **РОВНО ОДИН РАЗ** — recon (день 1) |
| Heavy | $1.00 | НЕ ИСПОЛЬЗУЕТСЯ |
| Max | $15.00 | НЕ ИСПОЛЬЗУЕТСЯ. Жёсткий запрет. |

### 2.2 Exa (AUGMENT)

```
API key:  $EXA_API_KEY (in .env)
MCP URL:  https://mcp.exa.ai/mcp?exaApiKey=$EXA_API_KEY
REST:     POST https://api.exa.ai/search  (header: x-api-key)
SDK:      pip install exa-py
```

| Type | Использование |
|---|---|
| `auto` | Default для большинства вызовов |
| `fast` / `instant` | Скорость > глубина |
| `deep-lite` | Только если outputSchema нужен и auto не справляется |
| `deep` | НЕ ИСПОЛЬЗУЕТСЯ массово, только recon |
| `deep-reasoning` | НЕ ИСПОЛЬЗУЕТСЯ |
| `deep_researcher_start/check` MCP-тулзы | НЕ ИСПОЛЬЗУЮТСЯ — это agentic polling, дорого |

Ключевой use-case Exa: `outputSchema` на `/search` — грунтованный JSON в `output.content` + citations в `output.grounding`. Это **augment** к Valyu для случаев, когда synthesizer ждёт structured data.

Канонический референс: https://docs.exa.ai/reference/search-api-guide-for-coding-agents

Грабли:
- Python SDK — snake_case, JSON — camelCase. Внутри проекта Python → snake_case.
- `contents.text.max_characters` — обязательный cap, иначе блует контекст.
- `contents.highlights` (а не top-level), `contents.text` (а не top-level).
- Deprecated: `useAutoprompt`, `includeUrls/excludeUrls`, `numSentences`, `highlightsPerUrl`, `tokensNum`, `livecrawl: "always"`.

### 2.3 Tavily (AUGMENT)

```
API key:  $TAVILY_API_KEY (in .env)
MCP URL:  https://mcp.tavily.com/mcp/?tavilyApiKey=$TAVILY_API_KEY
REST:     POST https://api.tavily.com/search
SDK:      pip install tavily-python
```

| `search_depth` | Использование |
|---|---|
| `basic` | Default. Дёшево, для general/news доменов где Valyu не нужен |
| `advanced` | Важные general-запросы; **никогда** не вместо Valyu на его доменах |

---

## 3. Архитектура

### 3.1 Абстрактный интерфейс

`backend/v2/sources/base.py`:

```python
class SearchBackend(Protocol):
    name: str  # "valyu" | "exa" | "tavily" | "perplexity"
    is_primary_capable: bool  # True только для Valyu

    def search(
        self,
        query: str,
        *,
        domain_hint: Optional[str] = None,
        max_results: int = 10,
        cost_budget_usd: Optional[float] = None,
    ) -> SearchResult: ...

    @property
    def cost_per_call(self) -> CostEstimate: ...
```

`SearchResult` — общий dataclass: `findings`, `sources`, `raw_metadata`, `cost_usd`, `latency_ms`. Source-quality classifier из Phase 3.3 применяется к `Source` объектам **после** маппинга — единообразно по всем backend'ам.

### 3.2 Routing matrix — Valyu-first

`backend/v2/research/routing.py`:

| Detected domain | Primary | Augment (если Valyu empty/down) | Notes |
|---|---|---|---|
| `financial_us` | **Valyu** | Tavily advanced | SEC, FRED, BLS, earnings |
| `financial_global` | **Valyu** | Tavily advanced | глобальные финансы |
| `regulatory_eu` | **Valyu** | Tavily advanced | DAC, MiCA, AIA |
| `regulatory_us` | **Valyu** | Tavily advanced | FDA, FCC, FTC |
| `medical_clinical` | **Valyu** | Exa | ClinicalTrials, PubMed |
| `scientific` | **Valyu** | Exa | arXiv, ChEMBL |
| `legal` | **Valyu** | Exa | UK law, patents |
| `technical_research` | **Valyu** → Exa* | Tavily advanced | * см. § 3.3 |
| `russian_market` | Perplexity | Tavily basic | Valyu не покрывает |
| `realtime_news` | Tavily basic | Perplexity | Valyu не специализируется |
| `general` | Tavily basic | Perplexity | Valyu overkill для general |

**Жёсткое правило:** на доменах помеченных **Valyu** — Valyu **обязан** быть вызван первым. Augment включается **только если Valyu вернул empty/error**, и тогда работает как добор, а не замена.

### 3.3 Особый случай: technical_research

Здесь возможны два подхода, какой эффективнее — покажет A/B day 5:

**Вариант B (default):** Valyu primary, Exa augment.
**Вариант D (опциональный):** Valyu primary + параллельно Exa с `outputSchema` для получения structured JSON напрямую (экономит LLM synthesis call).

Решение по варианту D принимаешь после A/B анализа. Если экономия LLM перекрывает Exa-вызовы → standardize. Если нет → остаётся вариант B.

### 3.4 Failover: деградация, не подмена

Когда Valyu primary падает (timeout / 5xx / empty), pipeline:

1. Логирует degradation event (для audit'а).
2. Вызывает augment backend.
3. **В DOCX рендерится явный warning** в начале раздела: «⚠️ Valyu corpus недоступен для этого запроса в момент исполнения; результаты основаны на augment-источниках и могут не содержать proprietary данные SEC/FRED/PubMed/etc. Рекомендуется перепрогнать запрос.»
4. В JSON-метаданных: `valyu_status: "degraded", reason: "<reason>", augment_used: "<backend>"`.

Этот warning **нельзя подавлять** конфигом. Он либо есть в DOCX, либо Valyu отработал нормально.

### 3.5 Защитный тест (must-have)

`tests/test_routing_invariants.py::test_valyu_is_primary_for_covered_domains`:

```python
COVERED_DOMAINS = [
    "financial_us", "financial_global",
    "regulatory_eu", "regulatory_us",
    "medical_clinical", "scientific",
    "legal", "technical_research",
]

def test_valyu_is_primary_for_covered_domains():
    for domain in COVERED_DOMAINS:
        primary, _ = ROUTING_MATRIX[domain]
        assert primary == "valyu", (
            f"Valyu MUST be primary for {domain}. "
            f"This invariant is non-negotiable per WEEK_BRIEF_v3."
        )
```

Этот тест нельзя skip'нуть, удалить или модифицировать. Любой PR, делающий это — invalid.

---

## 4. Hard rules на неделю

**Никогда:**

- Valyu Heavy/Max — запрещено.
- Valyu Standard — ровно один раз (recon, день 1).
- Exa `deep` / `deep-reasoning` — только recon.
- Exa `deep_researcher_start/check` — никогда.
- **Не делать Tavily/Exa/Perplexity primary на доменах, помеченных Valyu в § 3.2.**
- **Не подавлять degradation warning в DOCX.**
- Не пушить broken state в `origin/v4.5`.
- Не удалять/мутировать существующие 522 теста или новый invariant test ради «прохождения».
- Не запускать full A/B без push текущего состояния перед запуском.

**Всегда:**

- Valyu — primary на covered domains. Augment — только при failure Valyu.
- Push после каждого закрытого блока.
- Атомарные коммиты, формат `<scope>: <what>`.
- Перед прогоном с реальными деньгами — строка в `BUDGET.md`: `<date> <task> <expected_cost> <budget_left>`.
- Каждый вечер — `daily/<n>.md`.
- Source-quality classifier (Phase 3.3) применяется одинаково ко всем backend'ам — никаких пассивных bonus'ов.

**Бюджет:**

| Категория | Soft cap | Hard cap |
|---|---|---|
| OpenRouter (Run 2 + A/B + synthesis) | $12 | $14 |
| Valyu (1× standard + ~25× fast) | $3 | $5 |
| Exa (recon + ~30× auto/fast) | $1.5 | $2.5 |
| Tavily (~40× basic, ~5× advanced) | $0.5 | $1 |
| **Итого неделя** | **$17** | **$22.50** |

При приближении к hard cap по любой категории → стоп, push, daily отчёт.

---

## 5. Daily plan

(Original §5 verbatim — Day 1 triple recon, Day 2 base + Valyu, Day 3 Tavily + Exa,
Day 4 routing + invariant + degradation, Day 5 A/B, Day 6 Phase 4 brief, Day 7 closing.
See user-provided brief for full §5 — saved in conversation history.)

---

## 6-9. (Acceptance, Stop conditions, Don'ts, Priority order)

See user-provided brief for full text — saved in conversation history.

---

**Конец брифа. Приступай.**
