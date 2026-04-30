# Universal 10k Report Pipeline: non-breaking architecture plan

## Цель

Построить универсальный слой генерации отчетов уровня 10 000 рублей, который работает на любой теме и любом запросе:

- рыночный анализ;
- инвестиционный memo;
- конкурентный анализ;
- due diligence;
- продуктовая стратегия;
- технический аудит;
- юридический/регуляторный обзор;
- исследовательская записка.

Ключевое ограничение: **не ломать существующий pipeline**. Все улучшения должны быть additive: новые модули, новые форматы, новые quality gates, новые renderers. Старые `md`, `json`, `docx`, `pptx`, `onepager`, `data-pack`, `audit-json` должны продолжить работать как раньше.

## Что нельзя делать

1. Нельзя хардкодить конкретные темы: Москва, недвижимость, Метриум, ЦБ, девелоперы.
2. Нельзя менять существующий `v4_to_report_dict` так, чтобы сломать старые renderers.
3. Нельзя переписывать `render.py` как единственный новый pipeline.
4. Нельзя делать premium-отчет как ручной кастомный скрипт под одну тему.
5. Нельзя выпускать клиентский артефакт без визуального QA.
6. Нельзя считать презентацию отчетом. Отчет и презентация - разные артефакты.

## Правильная архитектура

### Существующий слой остается

Текущий контракт:

```text
FinalReport -> v4_to_report_dict -> render.py writers
```

Оставить как compatibility layer.

### Новый слой добавляется рядом

Новый контракт:

```text
FinalReport + AnalysisOutput + Evidence -> PremiumReportPlan
PremiumReportPlan -> PremiumReportDocument
PremiumReportDocument -> DOCX/PDF report
PremiumReportDocument -> PPTX/PDF deck
PremiumReportDocument -> QA audit
```

Новые модули должны быть отдельными:

```text
smart_report/exporters/premium/
  __init__.py
  models.py
  planner.py
  evidence.py
  scoring.py
  report_renderer.py
  deck_renderer.py
  qa.py
```

## Универсальные структуры

### PremiumReportPlan

План отчета, независимый от темы:

- `report_type`: market / investment / strategy / technical / legal / competitive / due_diligence / general
- `audience`: buyer / investor / executive / analyst / developer / operator / general
- `decision_context`: what the client needs to decide
- `minimum_pages`
- `required_sections`
- `required_visuals`
- `required_appendices`
- `quality_bar`

### PremiumReportDocument

Содержательная модель отчета:

- `cover`
- `executive_summary`
- `decision_summary`
- `methodology`
- `evidence_base`
- `analysis_sections`
- `model_or_framework`
- `scenarios`
- `recommendations`
- `risk_register`
- `monitoring_plan`
- `appendices`
- `sources`
- `qa_metadata`

### Universal blocks

Блоки, которые renderer может использовать в любой теме:

- `KpiGrid`
- `EvidenceTable`
- `SourceQualityTable`
- `Timeline`
- `ScenarioMatrix`
- `SensitivityTable`
- `DecisionMatrix`
- `RiskRegister`
- `MarketMap`
- `CompetitiveMatrix`
- `IssueSeverityTable`
- `MethodologyBox`
- `AppendixTable`

## Типы отчетов и минимальная структура

### Market report

- market definition;
- historical dynamics;
- demand drivers;
- supply drivers;
- regulation;
- consensus / conflicts;
- scenarios;
- recommendations;
- monitoring dashboard.

### Investment memo

- investment thesis;
- entry conditions;
- valuation / price logic;
- downside risk;
- upside scenario;
- sensitivity;
- liquidity / exit;
- decision thresholds.

### Competitive analysis

- market map;
- competitor profiles;
- differentiation;
- pricing;
- feature / capability matrix;
- strategic gaps;
- recommendations.

### Technical audit

- system map;
- risk register;
- code / architecture findings;
- severity;
- remediation plan;
- verification plan.

### Strategy report

- current state;
- strategic options;
- trade-offs;
- decision matrix;
- roadmap;
- risks;
- operating metrics.

## Отчет vs презентация

### Report

Формат: A4 portrait.
Размер: 20-35 страниц для paid client quality.
Назначение: глубина, доказательства, детали, источники, приложения.

Обязательные элементы:

- титул;
- executive summary;
- содержание;
- методология;
- разделы анализа;
- визуальные таблицы и графики;
- рекомендации;
- ограничения;
- приложения;
- источники.

### Deck

Формат: 16:9.
Размер: 10-14 слайдов.
Назначение: защита выводов и продажа решения.

Обязательные элементы:

- главный вывод;
- 3-5 ключевых фактов;
- 2-4 сильных визуала;
- сценарии;
- decision slide;
- next steps.

## Design system

Дизайн должен быть универсальным, не тематическим.

### Report design

- A4 portrait;
- editorial research style;
- строгая сетка;
- короткие колонтитулы;
- номера страниц;
- сдержанная палитра;
- минимум декоративности;
- много аккуратных таблиц;
- источники под таблицами и графиками.

### Deck design

- 16:9;
- один тезис на слайд;
- крупные графики;
- меньше текста;
- больше whitespace;
- визуальная иерархия как у consulting deck.

### Palette

Базовая универсальная палитра:

- deep navy / graphite для заголовков;
- warm white для фона;
- muted gold или teal для акцента;
- neutral gray для линий и вторичного текста;
- red / green только для рисков и решений.

## Quality gates

Новый premium export не должен выпускаться, если:

- меньше заданного минимума страниц;
- меньше минимального числа источников;
- нет evidence table;
- нет source quality table;
- нет actionable recommendations;
- нет хотя бы 3 визуальных элементов;
- есть внутренние токены;
- есть mojibake или replacement characters;
- есть markdown-мусор в финальном DOCX/PDF;
- не выполнен visual render check.

## Non-breaking rollout

### Phase 1: documentation and models

- добавить premium models;
- добавить planner без подключения к API;
- добавить unit tests на структуры.

### Phase 2: premium QA gate

- добавить `assess_premium_readiness`;
- не менять существующий `assess_client_readiness`;
- добавить отдельные tests.

### Phase 3: premium report renderer

- новый формат `premium-report`;
- старые форматы не трогать;
- если premium renderer падает, обычные exports должны продолжать работать.

### Phase 4: premium deck renderer

- новый формат `premium-deck`;
- deck строится из той же `PremiumReportDocument`.

### Phase 5: frontend opt-in

- добавить новые кнопки экспорта;
- не менять старые кнопки;
- premium export может требовать `allow_draft=true` или readiness pass.

## Acceptance criteria

Pipeline считается готовым, когда на трех разных темах:

1. отчет содержит 20+ страниц;
2. deck содержит 10+ слайдов;
3. evidence coverage выше 80%;
4. визуальный QA проходит без дефектов;
5. старые export tests продолжают проходить;
6. premium layer можно отключить без влияния на основной pipeline.

## Главный принцип

**Premium layer enriches, never replaces.**

Существующий pipeline остается фундаментом. Новый слой превращает результат в дорогой клиентский пакет, но не меняет базовые контракты и не ломает уже построенную систему.
