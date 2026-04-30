# Аудит уровня отчета для цены 10 000 рублей

Дата: 2026-04-29

## Verdict

Нет, текущий отчет нельзя честно считать продуктом уровня 10 000 рублей.

Текущая кодовая ветка улучшила упаковку экспортов и частично закрыла утечки
в новых client-facing exports, но качество самих аналитических отчетов все еще
ниже платного клиентского уровня. Главная проблема не в количестве тестов и не
в наличии DOCX, а в доказательной базе, полноте фактов, клиентской чистоте
артефактов и стабильности кодировки/языка.

## Что проверялось

- `runs/v4_cedc0f29e959/report.md`
- `runs/v4_cedc0f29e959/report.json`
- `runs/v4_cedc0f29e959/data_pack.zip`
- `docs/run2_baseline/q1_ev/report.docx`
- `docs/run2_baseline/q_fin_tesla_us/report.docx`
- старые baseline DOCX:
  - `docs/run2_baseline/q1_ev_run2_baseline.docx`
  - `docs/run2_baseline/q2_moscow_re_run2_baseline.docx`
  - `docs/run2_baseline/q3_eu_dac_run2_baseline.docx`

Визуальный рендер DOCX не выполнен: `soffice` в окружении не найден. DOCX
проверялись структурно через `python-docx`: текст, таблицы, маркеры, URL,
цитаты и служебные токены.

## Количественные сигналы

### Последний свежий export: `runs/v4_cedc0f29e959/report.md`

- Размер: 4 547 символов.
- Источники: 1 URL.
- Facts CSV: только заголовок, 0 фактов.
- Таблицы: 0.
- Цитаты вида `[1]`: 0.
- Внутренние leak-маркеры: 0.
- Data pack есть, но содержательно пустой для клиента.

Это технический smoke/test report, не коммерческий аналитический отчет.

### `docs/run2_baseline/q_fin_tesla_us/report.docx`

- Размер: 29 127 символов.
- Таблицы: 20.
- URL: 30.
- Citation markers `[N]`: 23.
- Evidence grade distribution по audit summary:
  - STRONG: 0
  - MODERATE: 0
  - WEAK: 16
  - SPECULATIVE: 9
- Release status: `degraded`.
- Evidence quality: `LOW_EVIDENCE_QUALITY`.
- Gaps: 1 critical, 4 moderate.
- Source count in final: 12.

Форма уже похожа на отчет, но доказательная база не выдерживает цену 10 000
рублей: по финансовой задаче с SEC/FRED/BLS все сильные источники отсутствуют,
а выводы построены на weak/speculative evidence.

### `docs/run2_baseline/q1_ev/report.docx`

- Размер: 39 987 символов.
- Таблицы: 21.
- URL: 83.
- Citation markers `[N]`: 81.
- Leak-маркеры:
  - `[STRONG]`: 12
  - `[MODERATE]`: 5
  - `[WEAK]`: 16
  - `[SPECULATIVE]`: 8
  - `[REF:]`: 27
  - `main_synthesis`: 6
  - `Perplexity`: 7
  - `OpenAI DR`: 8
- Release status: `degraded`.
- Evidence quality: `LOW_EVIDENCE_QUALITY`.
- Gaps: 2 critical, 3 moderate.

Этот отчет богаче по объему и структуре, но не client-ready: служебные
маркеры и tool-language прямо видны клиенту.

## Критические блокеры

### 1. Новые exports очищаются, но старые DOCX не client-clean

В старых baseline DOCX торчат `[STRONG]`, `[WEAK]`, `[REF:...]`,
`main_synthesis`, `Perplexity`, `OpenAI DR`. Это неприемлемо для платного
отчета. Клиент не должен видеть внутреннюю классификацию пайплайна и названия
инструментов как процессную кухню.

Недавний `client_view` sanitizer решает часть проблемы для новых экспортов,
но все коммерчески значимые артефакты надо регенерировать и проверить заново.

### 2. Evidence quality ниже коммерческого порога

Оба новых baseline-а (`q1_ev`, `q_fin_tesla_us`) имеют:

- `release_status: degraded`
- `evidence_quality: LOW_EVIDENCE_QUALITY`
- незакрытые critical/moderate gaps

Для отчета за 10 000 рублей это должно быть hard stop. Такой отчет можно
выдать только как черновой research memo с явной пометкой "не для принятия
решений".

### 3. Facts pipeline не дает полноценную таблицу фактов

В свежем `runs/v4_cedc0f29e959/facts.csv` нет ни одной строки фактов.
В коммерческом отчете data room должен содержать:

- все ключевые числовые факты;
- метрику;
- субъект;
- период;
- источник;
- цитату или пометку author synthesis;
- связь с выводом в отчете.

Без этого нельзя быстро проверить, откуда взялись цифры.

### 4. Последний свежий отчет слишком мал и слишком тестовый

`Q`, `Product > speed > brand`, один источник ERZ, 0 facts, 0 таблиц, 4.5k
символов. Это нормальный интеграционный тест, но не продукт.

### 5. Смешение языков и служебных фраз

Даже в свежем cleaned export остаются не клиентские формулировки:

- `Product > speed > brand`
- `medium`
- `resolved mortgage-share skew`
- `delivery open`

Это уже не leak sanitizer, а проблема synthesizer output policy. Клиентский
отчет должен писать на одном языке и в законченной деловой форме.

### 6. Metadata все еще выводится в Markdown

В `report.md` видна строка `_Метаданные:_ ... language_lint=...`. Для клиента
это мусор. Metadata должна быть только в audit/data-pack, не в основном
client report.

## Оценка по шкале 10 000 рублей

| Критерий | Вес | Оценка | Комментарий |
|---|---:|---:|---|
| Клиентская чистота текста | 20 | 8 для нового smoke export, 2 для baseline DOCX | Новые exports лучше, старые DOCX провалены |
| Доказательность | 25 | 3 | LOW_EVIDENCE_QUALITY и degraded |
| Полнота фактов/data room | 20 | 2 | свежий facts.csv пустой |
| Аналитическая глубина | 15 | 4 | baseline объемный, но gaps критичные |
| Формат DOCX/экспорт | 10 | 6 | структура есть, визуально не проверено |
| Язык и редактура | 10 | 3 | mixed language и процессные фразы |

Итог: примерно 4/10.

Коммерческий уровень 10 000 рублей начинается примерно с 8/10, при условии
что evidence quality не `LOW` и release status не `degraded`.

## Что нужно сделать, чтобы дойти до 10 000 рублей

1. Сделать `LOW_EVIDENCE_QUALITY` и `release_status=degraded` блокирующими для
   client export, либо маркировать отчет как draft.
2. Регенерировать DOCX через новый `sanitize_final_report` и проверить, что в
   DOCX нет `[STRONG]`, `[REF:]`, `main_synthesis`, tool names.
3. Убрать metadata из основного Markdown/HTML/DOCX, оставить ее только в
   `audit-json` и `data-pack`.
4. Починить facts extraction так, чтобы `facts.csv` был непустым на реальных
   отчетах и покрывал ключевые цифры.
5. Ввести hard acceptance gates:
   - минимум 2-3 authoritative sources для домена;
   - 0 critical gaps;
   - не менее 20 проверяемых numeric facts для аналитического отчета;
   - 0 client leaks;
   - 0 mixed-language lint warnings в executive summary.
6. Переписать synthesizer instructions: запретить фрагменты вида `medium`,
   `resolved ...`, `delivery open`, `all agree`.
7. Сделать visual QA DOCX после рендера, когда будет доступен LibreOffice или
   аналогичный renderer.

## Вывод

Текущая система стала ближе к клиентскому пакету за счет sanitized exports,
CSV и data-pack. Но сам отчет пока не на уровне 10 000 рублей. Это уровень
рабочего research draft / internal analyst memo. До платного уровня не хватает
главного: надежной доказательной базы, полноценной таблицы фактов, отсутствия
critical gaps и чистой редакторской подачи без следов пайплайна.
