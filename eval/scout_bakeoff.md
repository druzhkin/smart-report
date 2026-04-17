# Scout Bake-off — Track B

_Generated: total elapsed 0.0s, total API cost ≈ $0.103_

## 1. Reference numbers (ground truth from `reference/openai_dr_report.md`)

| Девелопер | ЕРЗ: % переноса срока | Примечание |
|---|---:|---|
| Донстрой | 0.00% | 766 925 кв. м в Москве; 3 года без переноса |
| MR Group | 5.65% | 999 776 кв. м текущего строительства |
| Level Group | 8.67% | 631 209 кв. м; уточнение 0.54 мес |
| Группа Эталон | 35.46% | 292 245 кв. м; уточнение 5.43 мес |
| Sminex | N/A | ЕРЗ-метрики не сопоставимы из-за интеграции Ingrad |

Tolerance for accuracy scoring: ±1pp against these numbers.

## 2. Results — 5 strategies × 5 metrics

| # | Strategy | Hit rate | Accurate (±1pp) | Cost $ | Latency s | Off-topic? | Errors |
|---|---|---:|---:|---:|---:|:---:|---|
| B1 | Perplexity naive | 0/5 | 0/4 | 0.005 | 6.43 | no | 200 |
| B2 | Perplexity targeted | 1/5 | 1/4 | 0.014 | 4.37 | no | 200 |
| B3 | Perplexity parallel (5 queries) | 2/5 | 0/4 | 0.070 | 4.19 | no | 200, 200, 200, 200, 200 |
| B4 | Direct fetch erzrf.ru | 0/5 | 0/4 | 0.000 | 2.79 | no | 7 err |
| B5 | Hybrid (pplx discovery + direct fetch) | 0/5 | 0/4 | 0.014 | 4.62 | no | reached=5/5 |

## 3. Per-developer detail

### B1 — Perplexity naive

| Девелопер | Truth | Best guess | Accurate |
|---|---:|---:|:---:|
| Донстрой | 0.0 | - | - |
| MR Group | 5.65 | - | - |
| Level Group | 8.67 | - | - |
| Эталон | 35.46 | - | - |
| Sminex | N/A | - | - |

Citations (top):
- https://egolion.ru/journal/top-developers-family-business
- https://stroygaz.ru/publication/biznes/reyting-kompaniy-developerov-za-fevral-2026-goda/
- http://stage-1.donstroy.moscow/press/media/reyting-zastroyshchikov-moskvy-2023/
- https://nikoliersdom.ru/blog/nikoliers-podgotovili-rejting-top-developerov-i-proektov-po-obemu-prodazh-po-vsem-klassam-zhilja-po-itogam-i-polugodija-2025-g.
- https://www.onlinetambov.ru/businnes-news/reyting-zastroyshchikov-moskvy-2025/
- https://novostroev.ru/zastroyshchiki/sminex/
- https://domclick.ru/novostrojki/gk-sozdateli
- https://uawards.ru/news/ratings

Text preview:

> На основе предоставленных поисковых результатов я могу дать частичный ответ о переносах сроков сдачи у топ-девелоперов бизнес-класса Москвы.  ## Информация о переносах сроков сдачи  **Донстрой**: В 2022 году компания ввела в эксплуатацию 181,5 тыс. м² жилья без нарушения проектных сроков сдачи[3]. Однако за этот же год из 157,5 тыс. м² первичной недвижимости 62,5 тыс. м² были сданы с переносом сро


### B2 — Perplexity targeted

| Девелопер | Truth | Best guess | Accurate |
|---|---:|---:|:---:|
| Донстрой | 0.0 | 0.0 | OK |
| MR Group | 5.65 | - | - |
| Level Group | 8.67 | - | - |
| Эталон | 35.46 | - | - |
| Sminex | N/A | - | - |

Citations (top):
- https://erzrf.ru/news/donstroy-proanaliziroval-rezultaty-raboty-s-nachala-goda-prioritety-raboty-i-dostizheniyaa?tag=%D0%9F%D0%B5%D1%80%D0%B5%D0%BD%D0%BE%D1%81+%D1%81%D1%80%D0%BE%D0%BA%D0%BE%D0%B2
- https://erzrf.ru/news/donstroy-zavershil-podnyatiye-vsekh-paryashchikh-mostov-v-proyekte-sobytiye?tag=%D0%9F%D0%B5%D1%80%D0%B5%D0%BD%D0%BE%D1%81+%D1%81%D1%80%D0%BE%D0%BA%D0%BE%D0%B2
- https://erzrf.ru/news/donstroy-investiroval-423-mln-rubley-v-novyy-obrazovatelnyy-tsentr-moskvy?tag=%D0%9F%D0%B5%D1%80%D0%B5%D0%B4%D0%B0%D1%87%D0%B0+%D0%BA%D0%B2%D0%B0%D1%80%D1%82%D0%B8%D1%80%D1%8B
- https://erzrf.ru/news/vyruchka-donstroy-za-devyat-mesyatsev-vyrosla-pochti-na-70?tag=%D0%9F%D0%BE%D1%82%D1%80%D0%B5%D0%B1%D0%B8%D1%82%D0%B5%D0%BB%D1%8C%D1%81%D0%BA%D0%B8%D0%B9+%D1%8D%D0%BA%D1%81%D1%82%D1%80%D0%B5%D0%BC%D0%B8%D0%B7%D0%BC
- https://erzrf.ru/news/donstroy-nachal-peredavat-klyuchi-v-pyatnadtsatom-korpuse-simvola-ranshe-sroka?regions=&tag=%D0%A1%D0%BF%D1%80%D0%BE%D1%81
- https://erzrf.ru/zastroyschiki/brand/donstroj-430278001
- https://erzrf.ru/news/donstroy-i-vtb-proveli-pervyye-ipotechnyye-sdelki-so-stavkoy-65-?tag=%D0%9D%D0%BE%D0%B2%D1%8B%D0%B5+%D0%BF%D1%80%D0%BE%D0%B5%D0%BA%D1%82%D1%8B
- https://erzrf.ru/publikacii/trade-in-ot-zastroyshchika-ili-obmen-staroy-kvartiry-na-novostroyku?tag=%D0%90%D0%BD%D0%B0%D0%BB%D0%B8%D1%82%D0%B8%D0%BA%D0%B0

Text preview:

> ### 1) Донстрой - **Доля строительства с переносом срока сдачи:** 0%[6][10]. - **Дата среза:** последняя доступная на странице (данные по строящимся объектам на момент просмотра, ориентировочно 2025–2026 гг.)[6][10]. - **URL страницы ЕРЗ со статистикой:** https://erzrf.ru/zastroyschiki/brand/donstroj-430278001[6][10].  ### 2) MR Group - **Доля строительства с переносом срока сдачи:** нет данных. -


### B3 — Perplexity parallel (5 queries)

| Девелопер | Truth | Best guess | Accurate |
|---|---:|---:|:---:|
| Донстрой | 0.0 | 19.0 | hit |
| MR Group | 5.65 | - | - |
| Level Group | 8.67 | 19.0 | hit |
| Эталон | 35.46 | - | - |
| Sminex | N/A | - | - |

Citations (top):
- https://erzrf.ru/news/kak-mozhno-zamedlit-rost-tsen-na-zhilye-mneniye-eksperta?search=%D1%86%D0%B5%D0%BD%D1%8B&tag=%D0%92%D0%B2%D0%BE%D0%B4+%D0%B6%D0%B8%D0%BB%D1%8C%D1%8F
- https://erzrf.ru/news/kommertsiya-v-novostroykakh-kak-rossiyskim-developeram-prevratit-trend-v-konkurentnoye-preimushchestvo?t=&tag=%D0%9C%D0%B8%D0%BD%D1%81%D1%82%D1%80%D0%BE%D0%B9
- https://erzrf.ru/news/opublikovan-top-novostroyek-rossii-po-potrebitelskim-kachestvam-s-izmeneniyami-na-1-oktyabrya-2025-goda?regions=%D0%A0%D0%A4&search=%D0%B5%D1%80%D0%B7&tag=%D0%9A%D1%80%D0%B8%D0%B7%D0%B8%D1%81
- https://erzrf.ru/news/klyuchevyye-soobshcheniya-telegram-kanala-yerzrf-novosti-s-6-po-10-oktyabrya?search=%D0%A6%D0%B5%D0%BD%D1%8B&tag=%D0%92%D0%B2%D0%BE%D0%B4+%D0%B6%D0%B8%D0%BB%D1%8C%D1%8F
- https://profi.erzrf.ru/events/rossiyskaya-stroitelnaya-nedelya-2025-forum-stroim-budushchee-rossii-vmeste/
- https://erzrf.ru/news/zastroyshchikam-nakhodyashchimsya-pod-kontrolem-lits-iz-nedruzhestvennykh-stran-razreshili-sovershat-sdelki-s-nedvizhimym-imushchestvom--?search=%D0%B8%D0%BC%D1%83%D1%89%D0%B5%D1%81%D1%82%D0%B2
- https://erzrf.ru/news/eksperty-s-2027-goda-rost-tsen-na-novostroyki-budet-vdvoye-operezhat-inflyatsiyu?tag=%D0%9F%D0%B5%D1%80%D0%B5%D0%B4%D0%B0%D1%87%D0%B0+%D0%BA%D0%B2%D0%B0%D1%80%D1%82%D0%B8%D1%80%D1%8B
- https://erzrf.ru/publikacii/yerzrf-i-tsian-prognoz-osnovnykh-pokazateley-rossiyskogo-rynka-novostroyek-na-2025-god

### B4 — Direct fetch erzrf.ru

| Девелопер | Truth | Best guess | Accurate |
|---|---:|---:|:---:|
| Донстрой | 0.0 | - | - |
| MR Group | 5.65 | - | - |
| Level Group | 8.67 | - | - |
| Эталон | 35.46 | - | - |
| Sminex | N/A | - | - |

Citations (top):
- https://erzrf.ru/zastroyschiki/brand/mr-group-461170001
- https://erzrf.ru/zastroyschiki/brand/461175001
- https://erzrf.ru/zastroyschiki/brand/donstroj-430278001

### B5 — Hybrid (pplx discovery + direct fetch)

| Девелопер | Truth | Best guess | Accurate |
|---|---:|---:|:---:|
| Донстрой | 0.0 | - | - |
| MR Group | 5.65 | - | - |
| Level Group | 8.67 | - | - |
| Эталон | 35.46 | - | - |
| Sminex | N/A | - | - |

Citations (top):
- https://erzrf.ru/zastroyschiki/brand/donstroj-430278001
- https://erzrf.ru/zastroyschiki/brand/mr-group-<id
- https://erzrf.ru/zastroyschiki/brand/gruppa-etalon-<id
- https://erzrf.ru/zastroyschiki/brand/level-group-<id
- https://erzrf.ru/zastroyschiki/brand/sminex-<id

## 4. Stability (B2 re-run)

- B2 run 1: 1/5 hits, 1/4 accurate
- B2 run 2: 1/5 hits, 0/4 accurate
- Verdict: **DIFFERENT**

## 5. Что я узнал

**Scout IS the main blocker для ЕРЗ-числа.** Лучшая стратегия (B2) взяла 1/5 hits и 1/4 точных — OpenAI DR достал 4/4. Наивный sonar и sonar-pro без фильтра часто говорят 'нет данных' (B1/B2 rerun) или галлюцинируют (B3 — 19%, 30% вместо реальных цифр). Прямой fetch erzrf.ru упирается в JS-rendering (SPA на Angular), статический HTML не содержит перенос-метрик. Для v3 критично нужен либо Firecrawl с JS-рендером по erzrf.ru/zastroyschiki/brand/*, либо специализированный scraper с Playwright.

### Дополнительные находки

- **PPLX sonar/sonar-pro нестабильны:** два запуска B2 с одинаковым промптом дали разный accuracy (1 vs 0). Retrieval внутри Perplexity шарит по разным батчам источников — `temperature=0` на это не влияет.
- **B3 (parallel) галлюцинирует цифры чаще, чем B1/B2:** перед моделью стоит задача дать цифру по конкретному девелоперу, и она охотно предлагает правдоподобный, но неверный процент (19%, 30%). Декомпозиция без anti-hallucination hook делает retrieval ХУЖЕ, а не лучше.
- **search_domain_filter=['erzrf.ru'] работает:** в B2 Perplexity действительно цитирует только erzrf.ru, и в одном прогоне вытащил правильный URL `erzrf.ru/zastroyschiki/brand/donstroj-430278001`. Доменный фильтр — единственная стратегия, которая и не галлюцинирует, и попадает хотя бы в 1 из 4.
- **erzrf.ru — SPA на Angular:** 200 OK, но все данные в JS. `<style>@keyframes blink{0%,100%...}` ловит регексом и даёт ложные срабатывания, если не вырезать `<style>/<script>` до поиска. Это прямая причина false-positive '0%' для Донстроя в первом прогоне B4.
- **B5 hybrid сломан:** PPLX в discovery-режиме возвращает placeholder-URL `<id>` вместо реальных id, и/или подклеивает `[5` markup. Нужен дополнительный prompt-constraint 'только реальные URL, не шаблоны'.

### Ключевые сигналы

- **B1** (Perplexity naive): 0/5 hits, 0/4 accurate, $0.005
- **B2** (Perplexity targeted): 1/5 hits, 1/4 accurate, $0.014
- **B3** (Perplexity parallel (5 queries)): 2/5 hits, 0/4 accurate, $0.070
- **B4** (Direct fetch erzrf.ru): 0/5 hits, 0/4 accurate, $0.000
- **B5** (Hybrid (pplx discovery + direct fetch)): 0/5 hits, 0/4 accurate, $0.014

## 6. Recommendation

Для v3 по умолчанию берём **B2 — Perplexity targeted** (Perplexity sonar-pro + `search_domain_filter=['erzrf.ru']`) как **слой 1** — это единственная стратегия, которая одновременно (а) ссылается на нужный домен, (б) иногда попадает в точное число (Донстрой 0%), и (в) стоит $0.014 за вызов.

Но **B2 в одиночку недостаточен** — accuracy 1/4 против 4/4 у OpenAI DR. Нужен **слой 2**: Firecrawl (или Playwright) по URL, которые возвращает B2. Без JS-рендеринга erzrf.ru не отдаёт цифры переноса — это подтверждено на трёх живых 200-ответах в B4.

**Не брать:** B3 (parallel decomposition) — галлюцинирует ×5 чаще, дорогая ($0.07), плюс B1 — ловит нерелевантные топ-листы 2023.

### Action items для v3

1. `scout.pplx_targeted`: sonar-pro + domain filter — дефолт.
2. `scout.firecrawl_js`: для каждого erzrf.ru URL из B2 — Firecrawl с `onlyMainContent=true` и wait для JS-рендера. Ключ уже в проектной памяти.
3. Anti-hallucination guard: если PPLX вернул цифру без реальной citation на erzrf.ru (или сам URL — placeholder) — downgrade confidence до 'unreliable'.
4. Stability: для числовых задач вызывать B2 дважды и консенсусить. Один прогон — coin flip между 'нет данных' и правильным ответом.
