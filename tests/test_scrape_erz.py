"""Contract test for smart_report.scrape.parse_erz_moscow_ranking.

Pins the table-row regex against a fixed sample of Jina-rendered ЕРЗ markdown.
If ЕРЗ redesigns their template and the regex stops matching, this test fails
loudly instead of silently producing empty enrichment and regressing scout density.
"""

from __future__ import annotations

from smart_report.scrape import erz_rows_as_findings, parse_erz_moscow_ranking

# Condensed but realistic fixture: two developer rows from Jina-rendered ЕРЗ output.
# Real rows have more trailing fields (ПТ/МД/БД/ДАП/Доля/Рейтинг) that we don't all
# need — the regex keys on the stable labels.
_SAMPLE = """*   1 Место**0**[ПИК](https://erzrf.ru/zastroyschiki/brand/pik-429726001?region=moskva), г.Москва Строится, м² **2 378 878**С переносом срока 97 279 % 4.09 Уточнение срока, мес. 0.19 Место по РФ 2 Застройщиков 35 ЖК 41 ПТ 0 МД 68 БД 0 ДАП 1 Доля в регионе 13.86% [5](x)
*   2 Место**0**[ГК Самолет](https://erzrf.ru/zastroyschiki/brand/gruppa-kompanij-samolet-2366201001), г.Москва Строится, м² **1 173 212**С переносом срока 798 375 % 68.05 Уточнение срока, мес. 8.84 Место по РФ 1 Застройщиков 15 ЖК 15 ПТ 0 МД 53 БД 0 ДАП 2 Доля в регионе 6.83% [4](x)
"""


def test_parses_two_rows() -> None:
    rows = parse_erz_moscow_ranking(_SAMPLE, top_n=10)
    assert len(rows) == 2
    pik, samolet = rows
    assert pik["name"] == "ПИК"
    assert pik["place"] == 1
    assert pik["total_m2"] == 2_378_878
    assert pik["delayed_m2"] == 97_279
    assert pik["delayed_pct"] == 4.09
    assert pik["delay_months"] == 0.19
    assert pik["erz_rating"] == 5.0

    assert samolet["name"] == "ГК Самолет"
    assert samolet["delayed_pct"] == 68.05  # the headline contrast with ПИК
    assert samolet["delay_months"] == 8.84


def test_top_n_truncates() -> None:
    rows = parse_erz_moscow_ranking(_SAMPLE, top_n=1)
    assert len(rows) == 1
    assert rows[0]["name"] == "ПИК"


def test_rows_as_findings_shape() -> None:
    rows = parse_erz_moscow_ranking(_SAMPLE, top_n=10)
    findings = erz_rows_as_findings(rows)
    assert len(findings) == 2
    for f in findings:
        assert set(f.keys()) == {"claim", "number", "source_url", "source_type", "verbatim_quote"}
        assert f["source_type"] == "industry"
        assert "%" in f["number"]
        # name + headline number must be in the claim so Analyst can cite verbatim
        assert any(name in f["claim"] for name in ("ПИК", "Самолет"))
