# Smart Report V2 — Полное Техническое Задание На Пересборку Продукта

## Статус документа

Это не заметки и не brainstorming.  
Это прямое производственное задание для нового чата, который должен автономно переписать продукт в этой же папке.

Цель не сохранить существующий пайплайн.  
Цель — построить новый продукт `Smart Report`, который:

1. генерирует действительно сильные аналитические отчеты;
2. делает это дешевле, быстрее и надежнее текущей версии;
3. не зависит от хрупкой длинной цепочки промптов;
4. умеет сам себя тестировать и аудировать;
5. к утру оставляет не “почти работающий прототип”, а внятный, запускаемый, проверяемый результат.

---

## 1. Главная цель

Построить новый `Smart Report` в текущем репозитории `C:\Users\rodina-adm\Documents\dev\smart-report`, используя только то, что реально помогает качеству, скорости и снижению себестоимости.

Продукт должен выдавать **decision-grade аналитический отчет** по публичным данным, с явной доказательной базой, с контролем уверенности, с сильным синтезом и без мусора вида:

1. служебные фразы модели в финальном документе;
2. повторяющиеся секции;
3. выдуманные или слабые источники;
4. рекомендации, не обеспеченные evidence;
5. зависание workflow в бесконечных циклах critique/revise.

---

## 2. Жесткий диагноз текущего проекта

Новый чат должен исходить из того, что текущая версия архитектурно несостоятельна как основа v2.

### Основные проблемы текущего решения

1. Продукт построен как длинная цепочка промптов, а не как система производства проверяемых артефактов.
2. Слишком много стадий-дубликатов: `prompt_router`, `prompt_king`, `prompt_splitter`, `reflect`, `research_critique`, `qa`, `synthesis_gate`.
3. Слишком мало жестких контрактов между этапами.
4. Clarify-flow неверно устроен: ответы на вопросы склеиваются обратно в текст запроса вместо формирования структурированного `TaskSpec`.
5. Слишком дорогой research-path: дорогой deep-search включается слишком рано и затем умножается revise-циклами.
6. Рендерер знает слишком много и на практике берет на себя генерацию смысла, что недопустимо.
7. UI показывает trace стадий, но не показывает пользователю evidence lifecycle и степень доказанности выводов.
8. RAGFlow используется расплывчато: как библиотека, память и квазиисточник одновременно.

### Критический вывод

Текущий backend разрешено снести почти полностью, если это самый быстрый путь к сильному v2.

---

## 3. Принципиальные правила нового проекта

### 3.1 Что важнее всего

Приоритеты идут строго в таком порядке:

1. достоверность;
2. полезность аналитического вывода;
3. трассируемость выводов к evidence;
4. низкая себестоимость;
5. скорость;
6. визуальная упаковка.

### 3.2 Что запрещено

Нельзя строить новый продукт вокруг:

1. roleplay multi-agent театра;
2. бесконтрольных planner/researcher/critic петель;
3. deep research как default-mode;
4. финального PDF как единственного артефакта;
5. RAGFlow как критического источника истины;
6. “модель сама разберется”.

### 3.3 Основной архитектурный принцип

Новый `Smart Report` должен быть не answer engine, а **evidence-first analytical pipeline**.

То есть сначала создаются и валидируются артефакты:

1. `RequestSpec`
2. `TaskSpec`
3. `ResearchPlan`
4. `SourceLedger`
5. `EvidenceLedger`
6. `ClaimTable`
7. `AnalysisBrief`
8. `ReportPackage`

И только потом делается финальный документ.

---

## 4. Прямое поручение новому чату

Ты не должен пытаться “починить старую систему”.

Твоя задача:

1. изучить существующий репозиторий;
2. принять самостоятельное решение, что сохранить, а что удалить;
3. сохранить все секреты и ключи;
4. при необходимости полностью заменить backend;
5. при возможности сохранить фронтовый shell и часть UI;
6. реализовать новый MVP v2 в этой же папке;
7. прогнать кодовые тесты, бизнес-тесты, фронтовые тесты и тесты качества отчетов;
8. оставить к утру рабочий и понятный результат с отчетом о проделанной работе.

Ты работаешь автономно.  
Не дергай пользователя по мелочам.  
Спрашивать можно только если решение реально блокируется отсутствием секрета или физически недоступным внешним ресурсом.

---

## 5. Что можно сохранить, а что можно уничтожить

### 5.1 Сохранить обязательно

1. Все `.env`, секреты, ключи, токены, Railway-конфиг.
2. Общую папку проекта и Git-историю.
3. Фронтовую оболочку, если это ускоряет запуск v2.
4. Полезные UI-компоненты:
   - `frontend/src/app/app/layout.tsx`
   - `frontend/src/app/app/page.tsx`
   - `frontend/src/app/app/new/page.tsx`
   - `frontend/src/app/app/reports/[id]/page.tsx`
   - `frontend/src/components/ReportProgress.tsx`
   - `frontend/src/components/ReportViewer.tsx`
   - `frontend/src/components/ClarifyingQuestions.tsx`
5. Полезные dev-инструменты и тестовые скрипты, если они не мешают.

### 5.2 Разрешено удалить или переписать целиком

1. Весь старый backend orchestration layer.
2. Весь старый prompt-pipeline.
3. Старые agent-модули, если они не ложатся в новую архитектуру.
4. Старые схемы данных, если они не отражают новый product model.
5. Старую knowledge-library логику.
6. Любой код, который усложняет build и не повышает качество.

### 5.3 Что сохранить только как reference

Существующий backend допустимо использовать только как источник идей, а не как фундамент:

1. старые API-paths;
2. методы рендера;
3. схемы хранения отчетов;
4. части UI-интеграции;
5. куски тестов.

---

## 6. Что нужно изучить перед началом пересборки

Новый чат обязан до серьезной реализации изучить:

### Frontend

1. [frontend/src/app/app/layout.tsx](C:/Users/rodina-adm/Documents/dev/smart-report/frontend/src/app/app/layout.tsx)
2. [frontend/src/app/app/page.tsx](C:/Users/rodina-adm/Documents/dev/smart-report/frontend/src/app/app/page.tsx)
3. [frontend/src/app/app/new/page.tsx](C:/Users/rodina-adm/Documents/dev/smart-report/frontend/src/app/app/new/page.tsx)
4. [frontend/src/app/app/reports/[id]/page.tsx](C:/Users/rodina-adm/Documents/dev/smart-report/frontend/src/app/app/reports/[id]/page.tsx)
5. [frontend/src/components/ClarifyingQuestions.tsx](C:/Users/rodina-adm/Documents/dev/smart-report/frontend/src/components/ClarifyingQuestions.tsx)
6. [frontend/src/components/ReportProgress.tsx](C:/Users/rodina-adm/Documents/dev/smart-report/frontend/src/components/ReportProgress.tsx)
7. [frontend/src/components/ReportViewer.tsx](C:/Users/rodina-adm/Documents/dev/smart-report/frontend/src/components/ReportViewer.tsx)
8. [frontend/src/lib/api.ts](C:/Users/rodina-adm/Documents/dev/smart-report/frontend/src/lib/api.ts)

### Backend / текущая логика

1. [backend/pipeline/graph.py](C:/Users/rodina-adm/Documents/dev/smart-report/backend/pipeline/graph.py)
2. [backend/api/routes/reports.py](C:/Users/rodina-adm/Documents/dev/smart-report/backend/api/routes/reports.py)
3. [backend/agents/research_agent.py](C:/Users/rodina-adm/Documents/dev/smart-report/backend/agents/research_agent.py)
4. [backend/agents/synthesis_agent.py](C:/Users/rodina-adm/Documents/dev/smart-report/backend/agents/synthesis_agent.py)
5. [backend/agents/renderer.py](C:/Users/rodina-adm/Documents/dev/smart-report/backend/agents/renderer.py)
6. [backend/schemas/report_schema.py](C:/Users/rodina-adm/Documents/dev/smart-report/backend/schemas/report_schema.py)
7. [backend/knowledge_library/retriever.py](C:/Users/rodina-adm/Documents/dev/smart-report/backend/knowledge_library/retriever.py)

После изучения нужно принять решение:

1. что будет salvaged;
2. что будет archived;
3. что будет rewritten from scratch.

Это решение должно быть задокументировано в `docs/rebuild_decisions.md`.

### 6.1 Обязательный внешний reference: проект `tripod`

Дополнительно нужно изучить репозиторий:

`C:\Users\rodina-adm\Documents\dev\tripod`

Цель не втащить `tripod` целиком в `Smart Report`, а использовать его как донор зрелых инженерных паттернов.

#### Обязательно изучить в `tripod`

1. [README.md](C:/Users/rodina-adm/Documents/dev/tripod/README.md)
2. [src/tripod/models.py](C:/Users/rodina-adm/Documents/dev/tripod/src/tripod/models.py)
3. [src/tripod/orchestrator.py](C:/Users/rodina-adm/Documents/dev/tripod/src/tripod/orchestrator.py)
4. [src/tripod/reasoning.py](C:/Users/rodina-adm/Documents/dev/tripod/src/tripod/reasoning.py)
5. [src/tripod/evidence_engine.py](C:/Users/rodina-adm/Documents/dev/tripod/src/tripod/evidence_engine.py)
6. [src/tripod/recommendation_authority.py](C:/Users/rodina-adm/Documents/dev/tripod/src/tripod/recommendation_authority.py)
7. [src/tripod/task_pack.py](C:/Users/rodina-adm/Documents/dev/tripod/src/tripod/task_pack.py)
8. [tests/test_tripod_vs_baseline.py](C:/Users/rodina-adm/Documents/dev/tripod/tests/test_tripod_vs_baseline.py)
9. [tests/test_authority_eval.py](C:/Users/rodina-adm/Documents/dev/tripod/tests/test_authority_eval.py)
10. [tests/test_user_facing_answer.py](C:/Users/rodina-adm/Documents/dev/tripod/tests/test_user_facing_answer.py)

#### Что разрешено заимствовать из `tripod`

1. принцип строгих pydantic-контрактов;
2. bounded orchestration;
3. stop-policy;
4. authority gate для рекомендаций;
5. deterministic evidence / precomputed facts;
6. runtime profiles / task packs;
7. eval-подход и сравнение против baseline;
8. user-facing answer tests;
9. acceptance-проверки не только кода, но и логики результата.

#### Что запрещено переносить как основу

1. весь `tripod` runtime целиком;
2. real-estate domain logic;
3. property/pricing-specific object taxonomy;
4. domain-specific synthesis policies;
5. любые hardcoded real-estate assumptions.

#### Жесткое правило

`Tripod` использовать как reference repo и донор паттернов.  
Не превращать `Smart Report` в форк `Tripod`.

---

## 7. Целевой продукт

### 7.1 Что это за продукт

`Smart Report V2` — это сервис, который принимает аналитическую задачу пользователя и производит пакет артефактов для принятия решений:

1. краткий executive brief;
2. полноценный отчет;
3. список и классификацию источников;
4. evidence ledger;
5. claim table;
6. список ограничений и зон неопределенности;
7. при необходимости charts и slides.

### 7.2 Что это не должно быть

Это не должно быть:

1. оболочкой над Perplexity;
2. PDF-генератором из веб-ответов;
3. чатиком с trace агентов;
4. витриной для “умных агентов”.

### 7.3 MVP-фокус

Первый v2 не должен пытаться быть универсальным для всех типов исследований.  
Нужно сознательно сузить scope.

Для MVP поддержать только публично проверяемые аналитические задачи, например:

1. comparison / vendor evaluation;
2. market landscape;
3. tool/model benchmarking summary;
4. strategic brief on public information;
5. structured competitive scan.

Не брать в MVP:

1. закрытые due diligence сценарии без данных;
2. финансовые модели с точными прогнозами;
3. медицинские и юридические high-stakes выводы;
4. темы, где почти нет reliable public sources.

---

## 8. Бизнес-логика нового workflow

Ниже описан обязательный целевой процесс.  
Именно его нужно реализовать.

### Этап 1. Intake

#### Вход

Свободный запрос пользователя.

#### Что делает система

1. понимает тип аналитической задачи;
2. выделяет объект анализа;
3. определяет, какое решение пользователь хочет принять;
4. понимает аудиторию отчета;
5. определяет допустимую глубину и бюджет;
6. выявляет, хватает ли постановки задачи для старта.

#### Выход

`RequestSpec`:

1. `request_id`
2. `original_query`
3. `language`
4. `report_type`
5. `goal`
6. `subject`
7. `decision_context`
8. `target_audience`
9. `time_horizon`
10. `geography`
11. `quality_target`
12. `budget_tier`
13. `missing_critical_fields`

Если `missing_critical_fields` не пустой, запускается semantic clarification.

### Этап 2. Semantic Clarification

#### Принцип

Вопросы нельзя задавать шаблонно.  
Они должны вытекать из смысла запроса.

#### Пример

Если запрос: “проведи анализ бесплатных LLM моделей”, система не должна спрашивать только “какой период”.

Она должна выяснять:

1. что считать бесплатным;
2. какие сценарии важны: чат, код, суммаризация, агенты;
3. нужны ли open-source/self-hosted варианты;
4. важны ли русский язык, скорость, размер контекста, лицензия;
5. нужен ли итоговый рейтинг или карта компромиссов.

#### Выход

`TaskSpec`:

1. `task_id`
2. `request_spec`
3. `success_criteria`
4. `evaluation_dimensions`
5. `constraints`
6. `must_cover_questions`
7. `allowed_source_types`
8. `blocked_source_types`
9. `output_package`
10. `max_budget_usd`

Важно: ответы пользователя не склеиваются назад в query-текст.  
Они становятся структурированными параметрами задачи.

### Этап 3. Research Planning

#### Что делает система

1. строит issue tree;
2. раскладывает задачу на исследовательские вопросы;
3. выделяет claims, которые надо подтвердить или опровергнуть;
4. задает приоритеты;
5. определяет, где нужен широкий поиск, а где vertical source targeting.

#### Выход

`ResearchPlan`:

1. `primary_questions`
2. `secondary_questions`
3. `claims_to_validate`
4. `claims_to_disprove`
5. `required_evidence_per_question`
6. `suggested_search_queries`
7. `preferred_domains`
8. `required_source_mix`
9. `chart_candidates`
10. `stop_conditions`

### Этап 4. Cheap Recall Search

#### Цель

Получить дешевый candidate set источников.  
Никакого дорогого deep research на этом этапе.

#### Правила

1. Использовать дешевые или already-available search providers.
2. Сначала искать URL-кандидаты, а не просить search engine сразу писать аналитику.
3. На каждый ключевой вопрос делать ограниченное число запросов.
4. Не дублировать одинаковые запросы.

#### Выход

`SearchCandidateSet`:

1. `query`
2. `question_id`
3. `source_candidates[]`
4. `provider`
5. `retrieved_at`

### Этап 5. Source Selection

#### Что делает система

Дешево и детерминированно отбирает лучшие URL:

1. dedup;
2. domain scoring;
3. freshness scoring;
4. source-type scoring;
5. blacklist weak sources;
6. ограничивает shortlist.

#### Выход

`SourceLedger`:

1. `source_id`
2. `url`
3. `title`
4. `domain`
5. `source_type`
6. `publisher`
7. `published_at`
8. `reliability_score`
9. `selection_reason`
10. `question_links[]`

### Этап 6. Fetch / Extraction

#### Что делает система

1. скачивает контент shortlisted sources;
2. извлекает читабельный основной текст;
3. сохраняет snapshot;
4. помечает fetch-failure и fallback status.

#### Выход

`SourceSnapshot`:

1. `source_id`
2. `fetch_status`
3. `http_status`
4. `content_type`
5. `text_content`
6. `raw_excerpt`
7. `snapshot_hash`
8. `fetch_timestamp`

### Этап 7. Evidence Extraction

#### Что делает система

Система еще не пишет финальные выводы.  
Она извлекает атомарные факты и утверждения.

#### Выход

`EvidenceLedger`:

1. `evidence_id`
2. `source_id`
3. `question_id`
4. `claim_text`
5. `normalized_claim`
6. `supporting_excerpt`
7. `entity_tags`
8. `metric_tags`
9. `freshness_score`
10. `confidence_score`
11. `is_quantitative`
12. `is_direct_statement`

### Этап 8. Claim Resolution

#### Что делает система

Собирает `ClaimTable` по ключевым аналитическим вопросам.

Для каждого вопроса должно быть видно:

1. что подтверждено;
2. что опровергнуто;
3. что противоречиво;
4. что остается недоказанным;
5. достаточно ли evidence для вывода.

#### Выход

`ClaimTable` и `CoverageReport`.

`CoverageReport` должен включать:

1. coverage per question;
2. contradiction count;
3. evidence strength;
4. unresolved gaps;
5. recommendation_allowed;
6. escalate_needed.

### Этап 9. Targeted Escalation

#### Принцип

Дорогой research нельзя включать по умолчанию.

Он включается только если:

1. критический вопрос не покрыт;
2. есть жесткие противоречия;
3. недостаточно authoritative sources;
4. без добора нельзя сделать полезный вывод.

#### Требование

Escalation делается точечно только по unresolved gaps, а не перезапуском всего pipeline.

#### Выход

Обновленные:

1. `SourceLedger`
2. `EvidenceLedger`
3. `ClaimTable`
4. `CoverageReport`

### Этап 10. Analysis Synthesis

#### Что делает система

На основе `ClaimTable` формирует уже не summary, а аналитическую логику:

1. ключевые выводы;
2. comparison matrix;
3. trade-offs;
4. сценарии;
5. practical recommendations;
6. ограничения и уровень уверенности.

#### Строгое правило

Если evidence слабый, система не имеет права выдавать уверенный рейтинг.  
Она должна честно выдать:

1. карту компромиссов;
2. частичные выводы;
3. список незакрытых вопросов.

#### Выход

`AnalysisBrief`:

1. `executive_summary`
2. `decision_recommendations`
3. `findings`
4. `tradeoffs`
5. `uncertainties`
6. `recommended_charts`
7. `appendix_requirements`

### Этап 11. Report Composition

#### Что делает система

Рендерер не создает новую аналитику.  
Он только упаковывает проверенный `AnalysisBrief` и `ClaimTable`.

#### Выход

`ReportPackage`:

1. `report.md`
2. `report.html`
3. `report.pdf`
4. `sources.json`
5. `claim_table.json`
6. `coverage_report.json`
7. `analysis_brief.json`
8. `slides.pptx` — опционально

### Этап 12. Release Gate

#### Что проверяется

1. нет ли служебных фраз модели;
2. нет ли дублей секций;
3. нет ли утверждений без evidence link;
4. нет ли broken source urls;
5. не превышает ли рекомендация доказательную базу;
6. есть ли executive summary, findings, risks, limitations;
7. нет ли смеси языка без явной причины;
8. нет ли пустых charts или битых файлов;
9. проходит ли report-level audit.

#### Выход

`release_status`:

1. `released`
2. `blocked`

Если `blocked`, финальный отчет не публикуется как successful result.

### Этап 13. Knowledge Writeback

#### Что сохранять

Сохранять не весь сырой мусор, а только:

1. verified claims;
2. нормализованные sources;
3. report summary;
4. metadata run;
5. reusable fact cards.

#### Важный принцип

Если RAGFlow недоступен, продукт все равно должен работать.  
RAGFlow не является критическим dependency.

---

## 9. Требования к стоимости

Это один из самых важных разделов.

### 9.1 Жесткое требование

Новый продукт не должен зависеть от `sonar-deep-research` как default engine.  
Это экономически неприемлемо.

### 9.2 Правильная cost-strategy

Нужно реализовать multi-tier research stack:

1. `cheap recall` — дешевые search queries для candidate URL set;
2. `source fetch` — прямое извлечение контента;
3. `claim extraction` — дешевые быстрые модели;
4. `final synthesis` — одна более сильная модель только на очищенных claims;
5. `deep escalation` — только по unresolved critical gaps.

### 9.3 Обязательные cost controls

1. Query dedup.
2. Source dedup.
3. Fetch cache.
4. Snapshot cache.
5. Query budget per report.
6. Escalation budget cap.
7. Token budget per stage.
8. Provider-level logging of spend.

### 9.4 Архитектурное требование

Search provider должен быть pluggable.

Нужен интерфейс вида:

1. `search(query, question_context) -> candidate urls`
2. `fetch(url) -> extracted content`
3. `escalate(query_bundle) -> richer search only if approved by gate`

### 9.5 Прямой продуктовый KPI

Нужно стремиться к такому blended economics:

1. cheap / standard отчеты — в основном без deep escalation;
2. deep escalation — только в небольшой доле run;
3. повторные запросы по похожим темам должны дешеветь за счет cache и knowledge reuse.

---

## 10. Рекомендованная техническая архитектура

### 10.1 Общий подход

Не надо строить это вокруг “армии агентов”.  
Нужно строить это вокруг:

1. четкого state machine / workflow;
2. типизированных stage contracts;
3. evidence artifacts;
4. audit/eval harness.

### 10.2 Предпочтительный backend

Разрешены два варианта:

#### Вариант A — прагматичный и быстрый

1. `FastAPI`
2. `Postgres`
3. `Redis` при необходимости для фоновых задач
4. явный Python workflow engine без лишней магии
5. `Pydantic` для строгих контрактов

#### Вариант B — более надежный long-running orchestration

1. `FastAPI`
2. `Temporal`
3. `Postgres`
4. `Pydantic`

### 10.3 Какой вариант выбрать

Если `Temporal` сильно тормозит автономный ночной билд, не тащить его ради красоты.  
Лучше сделать простой, ясный, надежный workflow на явных Python services и persisted run state.

### 10.4 Что не делать

1. Не делать новый core на `CrewAI`.
2. Не строить ядро вокруг role-based crews.
3. Не строить систему вокруг одного огромного LLM orchestration graph без строгих contracts.

---

## 11. Требования к frontend

### 11.1 Что можно сохранить

Сохранить текущий визуальный каркас, если это ускоряет delivery:

1. layout/sidebar;
2. dashboard shell;
3. report page shell;
4. базовые ui components;
5. tabs/viewer shell.

### 11.2 Что нужно изменить концептуально

#### Экран `New Report`

Сейчас он строится как:

1. Input
2. Clarify
3. Progress

Это слишком примитивно.  
Новый flow должен стать таким:

1. `Task`
2. `Scope`
3. `Questions`
4. `Evidence`
5. `Report`

#### Что должен видеть пользователь

Пользователь должен видеть:

1. как система поняла задачу;
2. какие смысловые слоты уточняются;
3. какие исследовательские вопросы зафиксированы;
4. какое покрытие по ним уже собрано;
5. где пробелы;
6. насколько сильны рекомендации.

### 11.3 Экран отчета

Нужно сделать табы не вокруг “что выгрузить”, а вокруг аналитической ценности:

1. `Brief`
2. `Report`
3. `Evidence`
4. `Sources`
5. `Gaps & Risks`
6. `Data / Charts`

### 11.4 Library

Текущая `Knowledge Library` почти пустая.  
Новый UI должен показывать:

1. saved reports;
2. source packs;
3. fact cards;
4. reusable domain collections;
5. refresh status.

### 11.5 Что нельзя показывать пользователю как primary UX

1. внутреннюю агентную кашу;
2. технические branch traces как главный value prop;
3. сырые prompt stages;
4. misleading verified badges без реальной проверки.

---

## 12. API-контракты v2

Разрешено сохранить старые URLs, если это уменьшает объем фронтовых правок.  
Но контракты нужно переработать под новый продукт.

### Основные endpoints

1. `POST /api/reports`
   - создать run
   - принять initial request

2. `POST /api/reports/{id}/clarify`
   - получить semantic clarification pack

3. `POST /api/reports/{id}/scope`
   - зафиксировать task spec

4. `GET /api/reports/{id}`
   - вернуть session meta + report meta + evidence progress

5. `GET /api/reports/{id}/stream`
   - SSE/stream статусов

6. `GET /api/reports/{id}/artifacts`
   - список артефактов run

7. `GET /api/reports/{id}/evidence`
   - claim/evidence summary

8. `GET /api/reports/{id}/sources`
   - sources list

9. `GET /api/reports/{id}/download/{format}`
   - pdf/html/docx/pptx/json

10. `GET /api/library`
11. `POST /api/library/refresh`
12. `GET /api/health`
13. `GET /api/evals`

---

## 13. Хранилище данных

### Нужно хранить отдельно

1. runs;
2. task specs;
3. research plans;
4. search queries;
5. source ledgers;
6. source snapshots;
7. evidence ledger;
8. claim tables;
9. analysis briefs;
10. report packages;
11. audit results;
12. cached normalized sources.

### Запрещено

Запихивать все в один бесформенный `metadata` JSON и надеяться, что потом кто-то разберется.

Допустимо использовать JSONB, но структура должна быть понятной и иметь устойчивые модели.

---

## 14. Требования к поиску и качеству источников

### Источники нужно классифицировать

Минимум по классам:

1. official documentation
2. vendor page
3. regulator / government
4. research paper
5. benchmark / leaderboard
6. high-quality secondary analysis
7. weak secondary / community

### Source policy

По умолчанию нельзя делать сильные рекомендации, опираясь в основном на:

1. Reddit
2. Medium
3. Telegram
4. YouTube
5. безымянные SEO-блоги
6. AI-generated агрегаторы

Такие источники можно использовать только как discovery hints, а не как core evidence.

---

## 15. Требования к report quality

### Финальный отчет обязан содержать

1. четкий title;
2. executive summary;
3. explicit decision context;
4. key findings;
5. comparison / analysis body;
6. limitations;
7. uncertainty statement;
8. source-backed claims;
9. appendix or source package.

### Финальный отчет не должен содержать

1. “I appreciate the detailed query”
2. “limitations of the search results”
3. технические куски промпта
4. внутренние self-critique формулировки
5. placeholder text
6. repeated sections
7. invented benchmarks or invented URLs

---

## 16. Требования к тестированию

Тестирование является частью core delivery, а не “если останется время”.

### 16.1 Кодовые тесты

Нужны:

1. unit tests;
2. integration tests;
3. API tests;
4. parser/validator tests;
5. storage/repository tests.

### 16.2 Бизнес-логика

Нужны тесты на:

1. classification of task type;
2. semantic clarification quality;
3. issue tree construction;
4. source scoring;
5. claim extraction;
6. contradiction detection;
7. recommendation gating;
8. fail-closed behavior.

### 16.3 Frontend

Нужны:

1. smoke tests for main pages;
2. create report flow e2e;
3. report viewer e2e;
4. failed report rendering e2e;
5. evidence tab visibility e2e.

### 16.4 Report Result Tests

Нужно обязательно реализовать тесты самого результата.

Минимум:

1. report does not contain banned meta phrases;
2. section dedup check;
3. every recommendation links to evidence or is downgraded;
4. no empty source pack;
5. no invalid output file references;
6. PDF/HTML generated successfully;
7. report-level audit summary produced.

### 16.5 Golden Evaluation Set

Нужно создать как минимум 5 публичных test cases, по которым продукт можно прогонять автоматически.

Каждый кейс должен включать:

1. prompt;
2. expected task type;
3. expected clarification dimensions;
4. must-have sections;
5. must-cover questions;
6. minimum evidence expectations;
7. pass/fail criteria.

---

## 17. Обязательный audit harness

Новый продукт обязан уметь аудировать не только код, но и generated output.

### Нужно создать

1. `scripts/run_full_validation.py`
2. `scripts/run_golden_evals.py`
3. `scripts/audit_report_package.py`

### Что должны делать эти скрипты

#### `run_full_validation.py`

Запускает:

1. backend tests;
2. frontend tests;
3. integration tests;
4. report generation smoke;
5. artifact checks.

#### `run_golden_evals.py`

Прогоняет набор canonical tasks и сохраняет результаты.

#### `audit_report_package.py`

Проверяет конкретный сгенерированный отчет:

1. структуру;
2. sources;
3. banned phrases;
4. evidence linkage;
5. duplicates;
6. completeness.

---

## 18. Автономный режим выполнения

Новый чат должен работать как инженер, а не как консультант.

### Обязательная тактика выполнения

1. Не писать длинные рассуждения вместо реализации.
2. Не делать масштабную перепись без thin end-to-end slice.
3. Сначала собрать тонкий вертикальный срез:
   - request -> clarify -> plan -> search -> evidence -> report -> audit
4. После прохождения thin slice расширять.
5. После каждого серьезного этапа прогонять тесты.

### Порядок работы на ночь

1. Изучить репозиторий.
2. Сформировать `docs/rebuild_decisions.md`.
3. Создать новый v2 architecture skeleton.
4. Реализовать thin slice end-to-end.
5. Подключить фронт к новому backend flow.
6. Реализовать report audit harness.
7. Прогнать golden cases.
8. Исправить критические сбои.
9. Сгенерировать итоговый `OVERNIGHT_STATUS.md`.

---

## 19. Deliverables к утру

К утру в репозитории должны быть:

1. новый backend или новая backend-core архитектура;
2. работающий основной пользовательский flow;
3. обновленный frontend, если нужно;
4. проходящий набор тестов;
5. скрипты аудита;
6. хотя бы 3 сгенерированных sample reports;
7. audit results для sample reports;
8. документ с решениями по архитектуре;
9. документ с итоговым статусом.

### Обязательные итоговые файлы

1. `docs/rebuild_decisions.md`
2. `docs/v2_architecture.md`
3. `docs/test_strategy.md`
4. `OVERNIGHT_STATUS.md`
5. `reports/samples/...`
6. `reports/audits/...`

---

## 20. Definition of Done

Работа считается выполненной только если одновременно соблюдены все условия:

1. пользователь может создать новый отчет через UI;
2. уточняющие вопросы задаются по смыслу, а не шаблонно;
3. pipeline строит evidence artifacts, а не сразу идет в prose;
4. expensive deep-search не является default path;
5. финальный отчет имеет evidence linkage;
6. продукт умеет fail closed;
7. тесты backend проходят;
8. тесты frontend проходят;
9. golden evals запускаются;
10. хотя бы один реальный end-to-end report package успешно сгенерирован и проаудирован;
11. нет служебного мусора в финальном документе;
12. сохранены секреты и ключи;
13. если старый backend убит, новый запуск и структура проекта понятны и документированы.

---

## 21. Прямые анти-паттерны, которые запрещено повторять

1. Сначала генерировать красивый текст, потом пытаться доказать, что он правдивый.
2. Ставить critique после того, как текст уже практически готов.
3. Перезапускать весь pipeline из-за локального evidence gap.
4. Использовать один и тот же дорогой research provider на все случаи.
5. Прятать ключевую логику в один giant renderer.
6. Считать citations достаточным признаком качества.
7. Делать продукт, который красиво выглядит, но не умеет честно говорить “данных недостаточно”.

---

## 22. Прямое решение по стэку

Если нужен быстрый и сильный результат за ночь, ориентироваться на:

1. `FastAPI`
2. `Pydantic`
3. `Postgres`
4. `Redis` только если реально нужен для worker queue
5. явный workflow orchestration layer
6. pluggable search interface
7. source fetching + extraction
8. evidence-first report generation
9. thin, predictable frontend adaptation

### Что не является целью этой ночи

1. супер-изящная агентная архитектура;
2. enterprise platform perfection;
3. максимальное количество провайдеров;
4. рекордное число функций.

### Что является целью этой ночи

1. правильная backbone-архитектура;
2. работающий vertical slice;
3. надежный quality gate;
4. контролируемая экономика;
5. понятный путь к дальнейшему развитию.

### 22.1 Что использовать из имеющихся проектов

При сборке нового `Smart Report V2` действовать так:

1. текущий `smart-report` frontend использовать как shell, если это экономит время;
2. текущий `smart-report` backend не жалеть, если его проще снести;
3. `tripod` использовать как донор:
   - authority gate,
   - bounded runtime,
   - deterministic evidence,
   - eval methodology;
4. не смешивать два проекта механически;
5. сначала собрать clean v2 core, потом адаптировать UI.

---

## 23. Последняя инструкция новому чату

Действуй как product+systems engineer.

Не пытайся сохранить старую архитектуру из вежливости.  
Если проще и правильнее вырезать старый backend почти полностью — вырезай.

Но:

1. не трогай секреты;
2. не ломай возможность локального запуска;
3. не оставляй проект в полуразобранном состоянии;
4. не рапортуй “готово”, если отчеты по сути все еще недостоверны.

Если выбор стоит между:

1. большим объемом переписанного кода;
2. меньшим объемом, но правильной архитектурой,

выбирай второе.

Если выбор стоит между:

1. красивой демонстрацией;
2. честно работающим evidence-first MVP,

выбирай второе.

Главная цель этой ночи — не впечатлить количеством изменений, а заложить **реально сильный аналитический продукт**.


