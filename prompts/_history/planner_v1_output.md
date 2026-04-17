# Planner v1 — raw Opus output

- question: Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?
- elapsed: 126.8s
- tokens: prompt=2526 completion=2624

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
      "layer": "Ипотечная доступность и структура финансирования",
      "scout_task": {
        "cell_id": "macro-finance/mortgage-dynamics",
        "query": "доля ипотечных сделок в бизнес-классе Москвы 2023-2024, средняя ставка, процент семейной ипотеки, средний LTV",
        "target_sources": ["ЦБ РФ", "ДОМ.РФ", "Frank RG", "Метриум"]
      }
    },
    {
      "id": "macro-finance/escrow-cost",
      "domain": "Макро-финансы",
      "layer": "Стоимость проектного финансирования",
      "scout_task": {
        "cell_id": "macro-finance/escrow-cost",
        "query": "средняя ставка проектного финансирования для девелоперов бизнес-класса Москвы 2023-2024, доля собственных средств в проектах",
        "target_sources": ["отчёты Сбербанка", "ВТБ", "ДОМ.РФ", "РБК Недвижимость"]
      }
    },
    {
      "id": "buyer/decision-factors",
      "domain": "Покупатель",
      "layer": "Ключевые факторы выбора",
      "scout_task": {
        "cell_id": "buyer/decision-factors",
        "query": "опросы покупателей бизнес-класса Москвы 2023-2024: топ-5 факторов выбора девелопера с процентным распределением",
        "target_sources": ["NF Group", "Metrium", "Knight Frank", "ВЦИОМ"]
      }
    },
    {
      "id": "buyer/price-sensitivity",
      "domain": "Покупатель",
      "layer": "Ценовая чувствительность и премия за бренд",
      "scout_task": {
        "cell_id": "buyer/price-sensitivity",
        "query": "готовность переплачивать за известный бренд девелопера в бизнес-классе Москвы: процент покупателей и размер премии в рублях/м²",
        "target_sources": ["Est-a-Tet", "ЦИАН Аналитика", "Авито Недвижимость", "корпоративные исследования ПИК/Самолёт"]
      }
    },
    {
      "id": "construction-discipline/delay-statistics",
      "domain": "Стройдисциплина",
      "layer": "Статистика переносов сроков",
      "scout_task": {
        "cell_id": "construction-discipline/delay-statistics",
        "query": "процент проектов бизнес-класса Москвы с переносом срока ввода 2022-2024, средняя задержка в месяцах по топ-10 девелоперам",
        "target_sources": ["ЕРЗ.РФ", "наш.дом.рф", "Мосгосстройнадзор", "Единый ресурс застройщиков"]
      }
    },
    {
      "id": "construction-discipline/sales-velocity",
      "domain": "Стройдисциплина",
      "layer": "Скорость продаж на разных стадиях",
      "scout_task": {
        "cell_id": "construction-discipline/sales-velocity",
        "query": "средняя скорость продаж квартир бизнес-класса Москвы по стадиям строительства: котлован, монолит, отделка (квартир/месяц)",
        "target_sources": ["Бест-Новострой", "НДВ-Супермаркет недвижимости", "данные ПИК/Эталон", "ЦИАН Pro"]
      }
    },
    {
      "id": "location/transport-premium",
      "domain": "Локация",
      "layer": "Премия за транспортную доступность",
      "scout_task": {
        "cell_id": "location/transport-premium",
        "query": "разница цен бизнес-класса Москвы в зависимости от удаленности от метро: 5 мин пешком vs 15 мин, руб/м² и процент",
        "target_sources": ["ЦИАН Аналитика", "Яндекс.Недвижимость", "IRN.RU", "Индикаторы рынка недвижимости"]
      }
    },
    {
      "id": "location/district-dynamics",
      "domain": "Локация",
      "layer": "Динамика спроса по районам",
      "scout_task": {
        "cell_id": "location/district-dynamics",
        "query": "топ-10 районов Москвы по объему продаж бизнес-класса 2023-2024, темпы роста цен и скорость реализации",
        "target_sources": ["Росреестр", "Метриум", "ИНКОМ-Недвижимость", "Азбука Жилья"]
      }
    },
    {
      "id": "competition/market-concentration",
      "domain": "Конкуренция",
      "layer": "Концентрация рынка",
      "scout_task": {
        "cell_id": "competition/market-concentration",
        "query": "доля топ-5 девелоперов в новостройках бизнес-класса Москвы 2023-2024 по объему ввода м² и количеству проектов",
        "target_sources": ["Единый ресурс застройщиков", "РБК Недвижимость", "Ведомости", "отчёты Colliers"]
      }
    },
    {
      "id": "competition/pricing-spread",
      "domain": "Конкуренция",
      "layer": "Ценовой разброс между игроками",
      "scout_task": {
        "cell_id": "competition/pricing-spread",
        "query": "средняя цена м² бизнес-класса Москвы 2024 по девелоперам: ПИК, Самолёт, Эталон, Level Group, MR Group",
        "target_sources": ["официальные сайты девелоперов", "Новострой-М", "ЕМЛС", "Urban Group аналитика"]
      }
    },
    {
      "id": "regulation/architectural-requirements",
      "domain": "Регулирование",
      "layer": "Архитектурные требования и согласования",
      "scout_task": {
        "cell_id": "regulation/architectural-requirements",
        "query": "средний срок согласования АГР для проектов бизнес-класса Москвы 2023-2024, процент отказов и доработок",
        "target_sources": ["Москомархитектура", "Мосгосстройнадзор", "отчёты КГА", "публикации Архсовета"]
      }
    },
    {
      "id": "regulation/parking-norms",
      "domain": "Регулирование",
      "layer": "Нормативы по паркингу",
      "scout_task": {
        "cell_id": "regulation/parking-norms",
        "query": "требования к машиноместам для бизнес-класса Москвы 2024: минимум мест на квартиру, средняя обеспеченность в реальных проектах",
        "target_sources": ["ПЗЗ Москвы", "Градостроительный кодекс", "Метриум", "данные новостроек ЦИАН"]
      }
    },
    {
      "id": "operational-efficiency/construction-cost",
      "domain": "Операционная эффективность",
      "layer": "Себестоимость строительства",
      "scout_task": {
        "cell_id": "operational-efficiency/construction-cost",
        "query": "средняя себестоимость строительства м² бизнес-класса Москвы 2023-2024 с разбивкой: материалы, работа, инженерия",
        "target_sources": ["Минстрой РФ", "отчёты СРО", "данные тендеров госзакупок", "Knight Frank"]
      }
    },
    {
      "id": "operational-efficiency/digitalization",
      "domain": "Операционная эффективность",
      "layer": "Цифровизация продаж",
      "scout_task": {
        "cell_id": "operational-efficiency/digitalization",
        "query": "доля онлайн-бронирований и сделок в бизнес-классе Москвы 2023-2024, конверсия онлайн vs офлайн по девелоперам",
        "target_sources": ["отчёты ПИК Digital", "данные Самолёт Plus", "исследования PwC", "РБК Pro"]
      }
    }
  ]
}
```
```
