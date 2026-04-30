from __future__ import annotations

from pathlib import Path
import html
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "doc"
OUT.mkdir(parents=True, exist_ok=True)
HTML_PATH = OUT / "moscow_primary_price_forecast_2026_2027_premium.html"
PDF_PATH = OUT / "moscow_primary_price_forecast_2026_2027_premium.pdf"


business = [
    ("H1 2023", 417.3),
    ("H1 2024", 471.2),
    ("Q3 2024", 472.7),
    ("Q4 2024", 461.3),
    ("H1 2025", 496.1),
    ("Q3 2025", 522.8),
    ("Q4 2025", 547.9),
    ("Q1 2026", 561.45),
]

premium = [
    ("H1 2024", 734.3),
    ("Q3 2024", 754.7),
    ("Q4 2024", 785.2),
    ("H1 2025", 778.3),
    ("Q3 2025", 818.3),
    ("Q4 2025", 866.5),
    ("Q1 2026", 887.78),
]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def line_chart(
    series: list[tuple[str, list[tuple[str, float]], str]],
    min_y: float,
    max_y: float,
    width: int = 980,
    height: int = 360,
) -> str:
    pad_l, pad_r, pad_t, pad_b = 72, 24, 28, 62
    labels = []
    for _, values, _ in series:
        for label, _ in values:
            if label not in labels:
                labels.append(label)

    x_pos = {
        label: pad_l + i * ((width - pad_l - pad_r) / max(1, len(labels) - 1))
        for i, label in enumerate(labels)
    }

    def y(v: float) -> float:
        return pad_t + (max_y - v) / (max_y - min_y) * (height - pad_t - pad_b)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">',
        '<rect x="0" y="0" width="100%" height="100%" fill="#fbfaf7"/>',
    ]
    for tick in range(int(min_y), int(max_y) + 1, 100):
        yy = y(tick)
        parts.append(
            f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width-pad_r}" y2="{yy:.1f}" '
            'stroke="#d8d2c5" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="18" y="{yy+4:.1f}" class="axis">{tick}</text>'
        )
    for label in labels:
        xx = x_pos[label]
        parts.append(
            f'<text x="{xx:.1f}" y="{height-28}" class="axis" text-anchor="middle">{esc(label)}</text>'
        )

    for name, values, color in series:
        pts = " ".join(f"{x_pos[label]:.1f},{y(val):.1f}" for label, val in values)
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="5" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        for label, val in values:
            xx, yy = x_pos[label], y(val)
            parts.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="6" fill="{color}"/>')
            parts.append(
                f'<text x="{xx:.1f}" y="{yy-12:.1f}" class="point" text-anchor="middle">{val:.0f}</text>'
            )
        last_label, last_val = values[-1]
        parts.append(
            f'<text x="{x_pos[last_label]-10:.1f}" y="{y(last_val)-24:.1f}" '
            f'class="legend" text-anchor="end" fill="{color}">{esc(name)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def scenario_chart() -> str:
    rows = [
        ("Бизнес", "Пессим.", 535, 570, "#a64232"),
        ("Бизнес", "База", 590, 625, "#1f6f78"),
        ("Бизнес", "Оптим.", 625, 690, "#2c8c59"),
        ("Премиум", "Пессим.", 850, 920, "#a64232"),
        ("Премиум", "База", 930, 1000, "#1f6f78"),
        ("Премиум", "Оптим.", 1000, 1100, "#2c8c59"),
    ]
    min_v, max_v = 500, 1120
    width, height = 980, 360
    left, top = 180, 32
    scale = (width - left - 48) / (max_v - min_v)
    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart">']
    parts.append('<rect width="100%" height="100%" fill="#fbfaf7"/>')
    for tick in range(500, 1150, 100):
        x = left + (tick - min_v) * scale
        parts.append(f'<line x1="{x:.1f}" y1="24" x2="{x:.1f}" y2="320" stroke="#ded8cc"/>')
        parts.append(f'<text x="{x:.1f}" y="342" text-anchor="middle" class="axis">{tick}</text>')
    for idx, (seg, scen, lo, hi, color) in enumerate(rows):
        y = top + idx * 48
        x1 = left + (lo - min_v) * scale
        x2 = left + (hi - min_v) * scale
        parts.append(f'<text x="24" y="{y+8}" class="axis strong">{esc(seg)}</text>')
        parts.append(f'<text x="98" y="{y+8}" class="axis">{esc(scen)}</text>')
        parts.append(
            f'<rect x="{x1:.1f}" y="{y-10}" width="{x2-x1:.1f}" height="22" rx="11" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{x2+8:.1f}" y="{y+7}" class="point">{lo}-{hi}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def table(headers: list[str], rows: list[list[str]], cls: str = "") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
        for cell in [[esc(x) for x in row]]
    )
    return f'<table class="data {cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


price_rows = [
    ["H1 2023", "417,3", "н/д", "полугодовая точка"],
    ["H1 2024", "471,2", "734,3", "полугодовая точка"],
    ["Q3 2024", "472,7", "754,7", "квартальная точка"],
    ["Q4 2024", "461,3", "785,2", "квартальная точка"],
    ["H1 2025", "496,1", "778,3", "полугодовая точка"],
    ["Q3 2025", "522,8", "818,3", "квартальная точка"],
    ["Q4 2025", "547,9", "866,5", "квартальная точка"],
    ["Q1 2026", "561,45", "887,78", "опорная база прогноза"],
]


html_doc = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<title>Прогноз цен первичного рынка Москвы 2026-2027</title>
<style>
@page {{ size: A4 landscape; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: #e7e2d8;
  color: #16242b;
  font-family: Arial, Helvetica, sans-serif;
}}
.page {{
  width: 297mm;
  height: 210mm;
  page-break-after: always;
  position: relative;
  overflow: hidden;
  background: #fbfaf7;
  padding: 16mm 18mm 14mm 18mm;
}}
.page.dark {{ background: #082f33; color: #f7f3e8; }}
.page.split {{ display: grid; grid-template-columns: 0.95fr 1.05fr; gap: 18mm; }}
.eyebrow {{ color: #16d58a; text-transform: uppercase; letter-spacing: .12em; font-size: 10px; font-weight: 700; }}
.kicker {{ color: #8c7b50; text-transform: uppercase; letter-spacing: .1em; font-size: 10px; font-weight: 700; margin-bottom: 4mm; }}
h1 {{ font-family: Georgia, 'Times New Roman', serif; font-size: 52px; line-height: 1.04; margin: 12mm 0 10mm; font-weight: 500; }}
h2 {{ font-family: Georgia, 'Times New Roman', serif; font-size: 34px; line-height: 1.08; margin: 0 0 8mm; color: #123a5a; font-weight: 500; }}
.dark h2, .dark h1 {{ color: #fffaf0; }}
h3 {{ font-size: 17px; margin: 0 0 3mm; color: #123a5a; }}
p {{ font-size: 13.4px; line-height: 1.48; margin: 0 0 4mm; }}
.large {{ font-size: 18px; line-height: 1.42; }}
.small {{ font-size: 10px; line-height: 1.35; color: #68757a; }}
.dark .small {{ color: #aac1bd; }}
.grid3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 5mm; }}
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; }}
.card {{
  border: 1px solid #d9d1c2;
  background: #fff;
  padding: 6mm;
  min-height: 28mm;
}}
.dark .card {{ background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.25); }}
.metric {{ font-family: Georgia, 'Times New Roman', serif; font-size: 34px; color: #123a5a; line-height: 1; }}
.dark .metric {{ color: #fff; }}
.label {{ font-size: 11px; color: #66747a; margin-top: 2mm; line-height: 1.32; }}
.dark .label {{ color: #c8d7d4; }}
.hero-grid {{
  position: absolute; right: 12mm; top: 18mm; width: 126mm; height: 174mm;
  display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 3mm;
}}
.tile {{ background: #dfeadf; position: relative; overflow: hidden; }}
.tile:before {{ content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 44%; background: repeating-linear-gradient(0deg,#082f33 0,#082f33 5px,#f0eadc 5px,#f0eadc 10px); }}
.building {{ position:absolute; bottom:44%; background:#6f9698; border-top: 4px solid #123a5a; }}
.b1 {{ left:12%; width:18%; height:44%; }} .b2 {{ left:36%; width:24%; height:58%; background:#c98863; }}
.b3 {{ left:64%; width:22%; height:34%; background:#e0bf73; }} .b4 {{ left:20%; width:56%; height:24%; background:#f1d3b6; }}
.cover-title {{ width: 130mm; position: relative; z-index: 2; }}
.rule {{ height: 3px; width: 70mm; background: #16d58a; margin: 10mm 0; }}
.footer {{ position: absolute; left: 18mm; right: 18mm; bottom: 7mm; display: flex; justify-content: space-between; border-top: 1px solid #d8d2c5; padding-top: 3mm; font-size: 9px; color: #6b7478; }}
.dark .footer {{ border-color: rgba(255,255,255,.25); color:#bcd0cc; }}
.toc {{ display:grid; grid-template-columns: 34mm 1fr; gap: 4mm 12mm; margin-top: 12mm; align-items: baseline; }}
.toc-num {{ color:#16d58a; font-size: 26px; font-family: Georgia, serif; text-align:right; }}
.toc-title {{ font-size: 16px; }}
.callout {{ border-left: 4px solid #c9a961; padding: 4mm 5mm; background: #f3eee3; margin: 4mm 0; }}
.tag {{ display:inline-block; padding: 1.5mm 3mm; border-radius: 999px; background:#e9efe9; color:#123a5a; font-size:10px; font-weight:700; margin-right:2mm; }}
.data {{ border-collapse: collapse; width: 100%; font-size: 10.5px; margin: 3mm 0 5mm; table-layout: fixed; }}
.data th {{ background:#123a5a; color:white; padding: 2.6mm; text-align:left; font-size:10px; }}
.data td {{ border:1px solid #d8d2c5; padding: 2.4mm; vertical-align: top; }}
.data tr:nth-child(even) td {{ background:#f3efe7; }}
.chart {{ width:100%; height:auto; border:1px solid #e2d9c9; }}
.axis {{ font-size: 13px; fill:#536066; }}
.axis.strong {{ font-weight:700; fill:#123a5a; }}
.point {{ font-size: 13px; fill:#213038; font-weight:700; }}
.legend {{ font-size: 14px; font-weight:700; }}
.two-col-text {{ columns: 2; column-gap: 9mm; }}
.bullets {{ margin: 0; padding-left: 5mm; }}
.bullets li {{ font-size: 13px; line-height: 1.42; margin-bottom: 2.5mm; }}
.source {{ font-size: 9px; color:#6e777b; margin-top: 1mm; }}
.section-number {{ font-family: Georgia, serif; font-size: 76px; color:#16d58a; line-height: .8; }}
.band {{ background:#082f33; color:#fff; padding: 8mm; margin: 4mm 0; }}
.band .metric {{ color:#fff; }}
.band .label {{ color:#d9e8e4; }}
</style>
</head>
<body>

<section class="page dark">
  <div class="cover-title">
    <div class="eyebrow">Москва | первичный рынок | бизнес и премиум</div>
    <h1>Прогноз цен на жилье 2026-2027</h1>
    <div class="rule"></div>
    <p class="large">Сценарный анализ, доказательная база и практические решения для покупателя, инвестора и девелопера.</p>
    <div class="grid3" style="margin-top:14mm;">
      <div class="card"><div class="metric">561 450</div><div class="label">руб./м2<br>бизнес-класс, Q1 2026</div></div>
      <div class="card"><div class="metric">887 780</div><div class="label">руб./м2<br>премиум-класс, Q1 2026</div></div>
      <div class="card"><div class="metric">14,5%</div><div class="label">ключевая ставка<br>Банк России, 24.04.2026</div></div>
    </div>
  </div>
  <div class="hero-grid">
    <div class="tile"><i class="building b1"></i><i class="building b2"></i><i class="building b3"></i></div>
    <div class="tile"><i class="building b2"></i><i class="building b4"></i><i class="building b1"></i></div>
    <div class="tile"><i class="building b3"></i><i class="building b1"></i><i class="building b2"></i></div>
    <div class="tile"><i class="building b4"></i><i class="building b3"></i><i class="building b1"></i></div>
  </div>
  <div class="footer"><span>Client report | version 29.04.2026</span><span>Smart Report</span></div>
</section>

<section class="page split">
  <div>
    <div class="kicker">Contents</div>
    <h2>Как читать отчет</h2>
    <div class="toc">
      <div class="toc-num">01</div><div class="toc-title">Ключевой вывод и решение</div>
      <div class="toc-num">02</div><div class="toc-title">Доказательная база цен</div>
      <div class="toc-num">03</div><div class="toc-title">Сценарный прогноз</div>
      <div class="toc-num">04</div><div class="toc-title">Спрос, ставка и ипотека</div>
      <div class="toc-num">05</div><div class="toc-title">Предложение и пайплайн</div>
      <div class="toc-num">06</div><div class="toc-title">Рекомендации и триггеры</div>
    </div>
  </div>
  <div>
    <div class="kicker">Executive answer</div>
    <h2>Это не рынок легкой доходности</h2>
    <p class="large">Базовый сценарий дает номинальный рост, близкий к инфляции. Деньги делаются не на покупке “среднего рынка”, а на выборе конкретного лота с дисконтом, ликвидной локацией и понятным выходом.</p>
    <div class="callout"><b>Главная правка:</b> 887-902 тыс. руб./м2 - это не бизнес-класс, а премиум. Корректная база бизнеса в Q1 2026 - 561 450 руб./м2.</div>
    <div class="grid2">
      <div class="card"><h3>Покупатель</h3><p>Покупать при личной потребности и скидке к прайсу. Ждать ставку можно, но ликвидные лоты уйдут первыми.</p></div>
      <div class="card"><h3>Инвестор</h3><p>Без дисконта и отдельного драйвера вход слабый: доходность близка к инфляции, а ликвидность ниже депозита.</p></div>
    </div>
  </div>
  <div class="footer"><span>01 | Executive summary</span><span>2</span></div>
</section>

<section class="page">
  <div class="kicker">Evidence base</div>
  <h2>Опорная линия: бизнес и премиум - разные рынки</h2>
  <div class="grid3">
    <div class="card"><div class="metric">+34,6%</div><div class="label">рост бизнеса с H1 2023 до Q1 2026</div></div>
    <div class="card"><div class="metric">+20,9%</div><div class="label">рост премиума с H1 2024 до Q1 2026</div></div>
    <div class="card"><div class="metric">2,41 млн</div><div class="label">высокобюджетный сегмент отдельно от премиума</div></div>
  </div>
  {line_chart([("Бизнес", business, "#1f6f78"), ("Премиум", premium, "#b36a42")], 400, 950)}
  <div class="source">Источник: Метриум PREMREPORT, H1 2023 - Q1 2026. Полугодовые точки помечены отдельно; их нельзя трактовать как точные квартальные значения.</div>
  <div class="footer"><span>02 | Базовая линия цен</span><span>3</span></div>
</section>

<section class="page">
  <div class="kicker">Price history</div>
  <h2>Квартальный ряд и надежность точек</h2>
  {table(["Период", "Бизнес, тыс. руб./м2", "Премиум, тыс. руб./м2", "Статус"], price_rows)}
  <div class="grid2">
    <div class="callout"><b>Сильная часть данных:</b> Q3 2024 - Q1 2026 дают последовательный ряд из одного источника и позволяют строить прогноз от сопоставимой базы.</div>
    <div class="callout"><b>Слабая часть данных:</b> Q1-Q4 2023 и Q1/Q2 2025 не раскрыты полностью в открытом доступе. Интерполяция допустима для графика, но не для инвестиционного решения.</div>
  </div>
  <div class="footer"><span>03 | Ряд цен и ограничения</span><span>4</span></div>
</section>

<section class="page">
  <div class="kicker">Scenarios</div>
  <h2>Сценарный коридор: конец 2026 года</h2>
  {scenario_chart()}
  <div class="grid3">
    <div class="card"><h3>Пессимистичный</h3><p>Ставка выше 15%, ипотека выше 18%, ДДУ падают более чем на 20% год к году.</p></div>
    <div class="card"><h3>Базовый</h3><p>Ставка снижается, но ипотека остается дорогой большую часть 2026 года.</p></div>
    <div class="card"><h3>Оптимистичный</h3><p>Ипотека ниже 15%, депозитная альтернатива слабеет, ликвидные лоты быстро вымываются.</p></div>
  </div>
  <div class="source">Диапазоны - авторский сценарный расчет от базы Q1 2026; не являются прямым прогнозом Метриума.</div>
  <div class="footer"><span>04 | Сценарный прогноз</span><span>5</span></div>
</section>

<section class="page split">
  <div>
    <div class="section-number">05</div>
    <h2>Спрос: ставка важна, но не одинаково</h2>
    <p>Бизнес-класс выигрывает от снижения ипотеки сильнее премиума: покупатель ближе к кредитной модели и чувствительнее к ежемесячному платежу.</p>
    <p>Премиум-класс живет по другой логике: депозиты, валютные ожидания, налоги и желание сохранить капитал в материальном активе.</p>
    <div class="band"><div class="metric">15%</div><div class="label">порог рыночной ипотеки, ниже которого спрос в бизнес-классе получает заметный импульс</div></div>
  </div>
  <div>
    <h2>Матрица поведения покупателя</h2>
    {table(["Условие", "Бизнес", "Премиум"], [
        ["Ипотека 18-20%", "покупатель откладывает сделку", "сделки идут только по лучшим лотам"],
        ["Ипотека ниже 15%", "возврат отложенного спроса", "умеренный плюс через снижение депозитов"],
        ["Рост скидок", "покупатель получает переговорную силу", "прайсы держатся, реальные сделки дешевеют"],
        ["Слабый рубль", "частично давит через себестоимость", "поддерживает защитный спрос"],
    ])}
  </div>
  <div class="footer"><span>05 | Спрос и ставки</span><span>6</span></div>
</section>

<section class="page">
  <div class="kicker">Supply and pipeline</div>
  <h2>Предложение поддерживает прайс, но не гарантирует ликвидность</h2>
  <div class="two-col-text">
    <p>Сокращение запусков и дорогой капитал помогают девелоперам удерживать цены предложения. Но дефицит предложения не равен дефициту ликвидности: если покупатель слабый, рынок может быть дорогим на витрине и вялым по сделкам.</p>
    <p>Пайплайн 2026-2027 в открытых источниках фрагментарен. Его нельзя использовать как полноценный supply forecast без проверки проектных деклараций, РНС и официальных анонсов девелоперов.</p>
  </div>
  {table(["Девелопер", "Что видно публично", "Как использовать"], [
      ["Capital Group", "отдельные премиальные/элитные проекты", "проверять проектные декларации и даты стартов"],
      ["Level Group", "проекты бизнес- и премиум-класса", "сверять сроки и классы по официальным данным"],
      ["Vesper / Coldy", "перспективные делюкс-старты", "выносить в appendix до подтверждения"],
      ["Forma / Insigma", "открытых данных недостаточно", "не включать в модель как факт"],
  ])}
  <div class="callout"><b>Правило качества:</b> РНС по сегментам в открытом доступе нет. Их нельзя заменять экспертной догадкой.</div>
  <div class="footer"><span>06 | Предложение и пайплайн</span><span>7</span></div>
</section>

<section class="page">
  <div class="kicker">Decision rules</div>
  <h2>Что делать: пороги решений</h2>
  <div class="grid3">
    <div class="card"><h3>Входить</h3><p>Дисконт к прайсу 7-10% в бизнесе или 10-15% в премиуме; сильная локация; стадия готовности снижает строительный риск.</p></div>
    <div class="card"><h3>Ждать</h3><p>Ставка выше 15%, ипотека выше 18%, продавец не дает индивидуальных условий, экспозиция растет.</p></div>
    <div class="card"><h3>Отказаться</h3><p>Проект продается дороже рынка без уникального драйвера; прогноз строится от цены экспозиции, а не сделки.</p></div>
  </div>
  {table(["Критерий", "Зеленый сигнал", "Красный сигнал"], [
      ["Цена", "ниже сопоставимых сделок", "только прайс-лист без скидок"],
      ["Локация", "ЦАО/ЗАО/САО или дефицитный кластер", "высокая конкуренция похожих ЖК"],
      ["Ставка", "ипотека ниже 15%", "ипотека выше 18%"],
      ["Ликвидность", "малый объем похожих лотов", "растущая экспозиция и скидки"],
      ["Девелопер", "сильная репутация и стадия готовности", "неясные сроки и слабая доказательная база"],
  ])}
  <div class="footer"><span>07 | Практические рекомендации</span><span>8</span></div>
</section>

<section class="page">
  <div class="kicker">Evidence discipline</div>
  <h2>Что еще нужно для инвестиционного меморандума</h2>
  <div class="grid2">
    <div>
      <h3>Нужно дособрать</h3>
      <ul class="bullets">
        <li>Q1-Q4 2023 по Метриуму или сопоставимому источнику.</li>
        <li>Реальные сделки или прокси по скидкам к прайсу.</li>
        <li>РНС/проектные декларации по конкретным проектам.</li>
        <li>Пайплайн с площадью, стадией, стартом продаж и источником.</li>
      </ul>
    </div>
    <div>
      <h3>Нельзя делать</h3>
      <ul class="bullets">
        <li>Смешивать бизнес, премиум и высокобюджетный сегмент.</li>
        <li>Выдавать цену экспозиции за цену сделки.</li>
        <li>Ссылаться на закрытые прогнозы без прямой цитаты.</li>
        <li>Достраивать отсутствующие кварталы как факт.</li>
      </ul>
    </div>
  </div>
  <div class="callout"><b>Итог:</b> текущая открытая база достаточна для качественного рыночного memo. Для полноценного investment memo нужна платная/закрытая верификация сделок и пайплайна.</div>
  {table(["Блок", "Текущий статус", "Что даст +ценность"], [
      ["Цены", "ряд из Метриума собран", "добавить page-level выписки из PDF"],
      ["Сделки", "нет закрытой базы реальных цен", "оценить дисконт и реальную ликвидность"],
      ["Пайплайн", "частичные публичные анонсы", "проверить РНС, проектные декларации, даты стартов"],
      ["Ставки", "есть рамка ЦБ", "добавить месячный мониторинг ипотечных ставок"],
  ])}
  <div class="footer"><span>08 | Доказательная дисциплина</span><span>9</span></div>
</section>

<section class="page">
  <div class="kicker">Sources</div>
  <h2>Источники и уровень доверия</h2>
  {table(["Источник", "Что подтверждает", "Уровень"], [
      ["Метриум PREMREPORT Q1 2026", "561 450, 887 780, 2,41 млн руб./м2", "Tier 1"],
      ["Метриум PREMREPORT 2024-2025", "исторический ценовой ряд", "Tier 1"],
      ["Банк России, 24.04.2026", "ключевая ставка 14,5%, рамка ставки 2026-2027", "Tier 1"],
      ["Коммерсантъ / NF Group", "контекст по элитному сегменту", "Tier 2"],
      ["Публичные анонсы девелоперов", "частичный pipeline", "Tier 3"],
  ])}
  <div class="grid2">
    <div>
      <h3>Прямые источники</h3>
      <ul class="bullets">
        <li>Метриум PREMREPORT Q1 2026: цены бизнеса, премиума и высокобюджетного сегмента.</li>
        <li>Банк России: ключевая ставка 14,5% и среднесрочная рамка 2026-2027.</li>
        <li>Исторические PREMREPORT 2024-2025: ряд для динамики цен.</li>
      </ul>
    </div>
    <div>
      <h3>Вторичные источники</h3>
      <ul class="bullets">
        <li>Коммерсантъ / NF Group: контекст по элитному рынку.</li>
        <li>Публичные сайты и подборки девелоперов: только как pipeline-сигналы.</li>
        <li>CBRE и Knight Frank использованы как визуальные ориентиры формата, не как источник московского прогноза.</li>
      </ul>
    </div>
  </div>
  <p class="small">Ключевые URL: metrium.ru/upload/iblock/fbe/vefbk6gf0xovrnnljxl9huzdsczmiwop.pdf; cbr.ru/press/keypr; cbr.ru/statistics/ddkp/mo_br; kommersant.ru/doc/8378272; kommersant.ru/doc/8365129.</p>
  <div class="footer"><span>09 | Источники</span><span>10</span></div>
</section>

</body>
</html>
"""


def main() -> None:
    HTML_PATH.write_text(html_doc, encoding="utf-8")
    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if not chrome.exists():
        raise SystemExit("Chrome not found")
    subprocess.run(
        [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--print-to-pdf={PDF_PATH}",
            "--print-to-pdf-no-header",
            str(HTML_PATH),
        ],
        check=True,
        cwd=ROOT,
    )
    print(HTML_PATH)
    print(PDF_PATH)


if __name__ == "__main__":
    main()
