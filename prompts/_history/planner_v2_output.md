# Planner v2 — raw Opus output

- question: Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?
- elapsed: 124.3s
- tokens: prompt=3728 completion=2677

---

```json
```json
{
  "question_id": "moscow-business-success-factors",
  "domains": [
    "Макро-финансы",
    "Покупатель",
    "Стройдисциплина",
    "Локация",
    "Конкуренция",
    "Регулирование",
    "Операционная эффективность"
  ],
  "cells": [
    {
      "id": "macro-finance/mortgage-dynamics",
      "domain": "Макро-финансы",
      "layer": "Ипотечное финансирование и ставки",
      "scout_task": {
        "cell_id": "macro-finance/mortgage-dynamics",
        "query": "доля ипотечных сделок в бизнес-классе Москвы 2023-2024 (%), средняя ставка по сегментам (%), доля льготных программ в выдачах",
        "target_sources": ["ЦБ РФ", "ДОМ.РФ", "Frank RG", "Росреестр"]
      }
    },
    {
      "id": "macro-finance/escrow-turnover",
      "domain": "Макро-финансы",
      "layer": "Оборачиваемость эскроу-счетов",
      "scout_task": {
        "cell_id": "macro-finance/escrow-turnover",
        "query": "средний срок раскрытия эскроу в бизнес-классе Москвы 2023-2024 (мес.), объём средств на эскроу топ-10 девелоперов (млрд ₽)",
        "target_sources": ["ЦБ РФ", "ЕРЗ.РФ", "годовые отчёты ПИК/Самолёт", "РБК Недвижимость"]
      }
    },
    {
      "id": "buyer/decision-factors",
      "domain": "Покупатель",
      "layer": "Факторы выбора и готовность платить",
      "scout_task": {
        "cell_id": "buyer/decision-factors",
        "query": "топ-5 факторов выбора ЖК бизнес-класса Москвы 2024: вес бренда/локации/планировок (%), готовность переплатить за бренд (₽/м²)",
        "target_sources": ["NF Group", "ВЦИОМ", "Metrium", "исследования Яндекс.Недвижимость"]
      }
    },
    {
      "id": "buyer/investment-share",
      "domain": "Покупатель",
      "layer": "Инвестиционный спрос",
      "scout_task": {
        "cell_id": "buyer/investment-share",
        "query": "доля инвестиционных сделок в бизнес-классе Москвы 2023-2024 (%), средняя доходность аренды (% годовых), payback период (лет)",
        "target_sources": ["ЦИАН Аналитика", "Авито Недвижимость", "Knight Frank", "ДОМ.РФ"]
      }
    },
    {
      "id": "construction/deadline-discipline",
      "domain": "Стройдисциплина",
      "layer": "Соблюдение сроков ввода",
      "scout_task": {
        "cell_id": "construction/deadline-discipline",
        "query": "процент проектов с переносом ввода среди топ-10 девелоперов бизнес-класса Москвы 2022-2024 (%), средняя задержка (мес.)",
        "target_sources": ["ЕРЗ.РФ", "наш.дом.рф", "Мосгосстройнадзор", "Единый ресурс застройщиков"]
      }
    },
    {
      "id": "construction/quality-claims",
      "domain": "Стройдисциплина",
      "layer": "Качество строительства и претензии",
      "scout_task": {
        "cell_id": "construction/quality-claims",
        "query": "количество претензий на 1000 квартир по топ-10 девелоперам Москвы 2023-2024, средний срок устранения дефектов (дней)",
        "target_sources": ["Роспотребнадзор", "Мосжилинспекция", "отзывы Правда.ру", "данные управляющих компаний"]
      }
    },
    {
      "id": "location/transport-premium",
      "domain": "Локация",
      "layer": "Транспортная доступность и премия",
      "scout_task": {
        "cell_id": "location/transport-premium",
        "query": "премия за близость к метро в бизнес-классе Москвы 2024: разница цен 5/10/15 мин пешком (₽/м² и %), влияние МЦД",
        "target_sources": ["ЦИАН Аналитика", "Яндекс.Недвижимость", "Est-a-Tet", "исследования ВШЭ"]
      }
    },
    {
      "id": "location/district-infrastructure",
      "domain": "Локация",
      "layer": "Инфраструктура района",
      "scout_task": {
        "cell_id": "location/district-infrastructure",
        "query": "рейтинг районов Москвы по инфраструктуре для бизнес-класса 2024: школы/парки/ТЦ на 1000 жителей, корреляция с ценой (R²)",
        "target_sources": ["Правительство Москвы", "Urban Index", "КБ Стрелка", "Институт Генплана"]
      }
    },
    {
      "id": "competition/market-concentration",
      "domain": "Конкуренция",
      "layer": "Концентрация рынка",
      "scout_task": {
        "cell_id": "competition/market-concentration",
        "query": "доля топ-5 девелоперов в новом предложении бизнес-класса Москвы 2023-2024 (%), HHI индекс, количество новых игроков",
        "target_sources": ["ЕРЗ.РФ", "Knight Frank", "CBRE", "Colliers"]
      }
    },
    {
      "id": "competition/brand-trust",
      "domain": "Конкуренция",
      "layer": "Доверие к брендам",
      "scout_task": {
        "cell_id": "competition/brand-trust",
        "query": "рейтинг доверия топ-10 девелоперов Москвы 2024 (%), NPS score, количество повторных покупок (%)",
        "target_sources": ["ВЦИОМ", "Romir", "NF Group", "отчёты девелоперов"]
      }
    },
    {
      "id": "regulation/architectural-requirements",
      "domain": "Регулирование",
      "layer": "Архитектурные требования",
      "scout_task": {
        "cell_id": "regulation/architectural-requirements",
        "query": "требования Москомархитектуры к бизнес-классу 2024: минимальная высота потолков (м), нормы инсоляции, плотность застройки",
        "target_sources": ["Москомархитектура", "СП 42.13330.2016", "постановления Правительства Москвы", "Градкодекс РФ"]
      }
    },
    {
      "id": "regulation/parking-norms",
      "domain": "Регулирование",
      "layer": "Парковочные нормативы",
      "scout_task": {
        "cell_id": "regulation/parking-norms",
        "query": "нормативы машиномест для бизнес-класса Москвы 2024 (м/м на квартиру), средняя обеспеченность в новых проектах, стоимость м/м (млн ₽)",
        "target_sources": ["ППМ 1521", "Мосгосстройнадзор", "ЦИАН Аналитика", "данные ПИК/Эталон"]
      }
    },
    {
      "id": "operations/sales-velocity",
      "domain": "Операционная эффективность",
      "layer": "Скорость продаж",
      "scout_task": {
        "cell_id": "operations/sales-velocity",
        "query": "средняя скорость продаж в бизнес-классе Москвы 2023-2024 (квартир/мес.), absorption rate (%), время экспозиции до 50% продаж (мес.)",
        "target_sources": ["ЕРЗ.РФ", "NF Group", "Metrium", "квартальные отчёты девелоперов"]
      }
    },
    {
      "id": "operations/marketing-efficiency",
      "domain": "Операционная эффективность",
      "layer": "Эффективность маркетинга",
      "scout_task": {
        "cell_id": "operations/marketing-efficiency",
        "query": "CAC (cost per acquisition) в бизнес-классе Москвы 2024 (₽/сделка), конверсия лидов (%), маркетинговые расходы топ-5 (% от выручки)",
        "target_sources": ["отчёты ПИК/Самолёт", "исследования PwC", "данные Яндекс.Метрика", "AdIndex"]
      }
    }
  ]
}
```
```
