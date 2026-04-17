"""B2 — Perplexity targeted. Long query + source hints + search_domain_filter."""
from __future__ import annotations

import time

from ._common import (
    PRICE,
    extract_citations,
    extract_text,
    is_off_topic,
    pplx_chat,
    save_raw,
    score_text_against_truth,
    summarise_scores,
)

QUERY = (
    "По данным ЕРЗ (erzrf.ru), назови долю строительства с переносом срока сдачи "
    "(в процентах, последняя доступная дата 2025–2026) по каждому из 5 девелоперов "
    "бизнес-класса Москвы:\n"
    "1) Донстрой\n2) MR Group\n3) Level Group\n4) Группа Эталон\n5) Sminex\n"
    "Для каждого девелопера приведи: конкретный процент, дату среза, и прямой URL "
    "страницы ЕРЗ со статистикой застройщика. Ищи по site:erzrf.ru. "
    "Если цифры нет — честно пиши 'нет данных', не придумывай."
)


def run(run_tag: str = "b2") -> dict:
    t0 = time.time()
    resp = pplx_chat(
        "sonar-pro",
        QUERY,
        search_domain_filter=["erzrf.ru"],
        max_tokens=1600,
    )
    save_raw(run_tag, resp)
    text = extract_text(resp)
    cites = extract_citations(resp)
    scored = score_text_against_truth(text)
    agg = summarise_scores(scored)
    return {
        "name": "B2 — Perplexity targeted",
        "model": "sonar-pro",
        "query": QUERY,
        "latency_s": resp.get("_latency_s", round(time.time() - t0, 2)),
        "cost_usd": PRICE["sonar-pro"],
        "status": resp.get("_status"),
        "hits": agg["hits"],
        "accurate": agg["accurate"],
        "off_topic": is_off_topic(text, cites),
        "citations": cites[:12],
        "per_dev": scored,
        "text_preview": text[:800],
    }


if __name__ == "__main__":
    import json, sys
    res = run(sys.argv[1] if len(sys.argv) > 1 else "b2")
    print(json.dumps(res, ensure_ascii=False, indent=2))
