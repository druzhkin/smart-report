"""B1 — Perplexity naive. One short Russian query, default params, model=sonar."""
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
    "Перенос срока сдачи у топ-5 девелоперов бизнес-класса Москвы: "
    "Донстрой, MR Group, Level Group, Эталон, Sminex. Проценты по ЕРЗ."
)


def run(run_tag: str = "b1") -> dict:
    t0 = time.time()
    resp = pplx_chat("sonar", QUERY, max_tokens=1000)
    save_raw(run_tag, resp)
    text = extract_text(resp)
    cites = extract_citations(resp)
    scored = score_text_against_truth(text)
    agg = summarise_scores(scored)
    return {
        "name": "B1 — Perplexity naive",
        "model": "sonar",
        "query": QUERY,
        "latency_s": resp.get("_latency_s", round(time.time() - t0, 2)),
        "cost_usd": PRICE["sonar"],
        "status": resp.get("_status"),
        "hits": agg["hits"],
        "accurate": agg["accurate"],
        "off_topic": is_off_topic(text, cites),
        "citations": cites[:12],
        "per_dev": scored,
        "text_preview": text[:500],
    }


if __name__ == "__main__":
    import json, sys
    res = run(sys.argv[1] if len(sys.argv) > 1 else "b1")
    print(json.dumps(res, ensure_ascii=False, indent=2))
