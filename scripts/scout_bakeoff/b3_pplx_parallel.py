"""B3 — Parallel decomposition. 5 separate sonar-pro queries, one per developer."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ._common import (
    DEV_VARIANTS,
    GROUND_TRUTH,
    PRICE,
    extract_citations,
    extract_text,
    find_percent_near,
    is_off_topic,
    pplx_chat,
    save_raw,
)

DEVS = list(GROUND_TRUTH.keys())


def _query_for(dev: str) -> str:
    return (
        f"По данным ЕРЗ (erzrf.ru) — какая доля текущего строительства у застройщика "
        f"'{dev}' в Москве с переносом срока сдачи (в процентах)? "
        f"Нужна последняя доступная дата 2025–2026, конкретный процент и прямой URL "
        f"страницы застройщика на erzrf.ru. Если цифры нет — скажи 'нет данных'."
    )


def _one(dev: str) -> dict:
    q = _query_for(dev)
    resp = pplx_chat(
        "sonar-pro",
        q,
        search_domain_filter=["erzrf.ru"],
        max_tokens=900,
    )
    save_raw(f"b3_{dev}", resp)
    text = extract_text(resp)
    cites = extract_citations(resp)
    cands = find_percent_near(text, DEV_VARIANTS[dev])
    truth = GROUND_TRUTH[dev]
    best = None
    accurate = False
    if cands:
        if truth is not None:
            best = min(cands, key=lambda x: abs(x - truth))
            accurate = abs(best - truth) <= 1.0
        else:
            best = cands[0]
    return {
        "dev": dev,
        "query": q,
        "latency_s": resp.get("_latency_s"),
        "status": resp.get("_status"),
        "candidates": cands,
        "best": best,
        "truth": truth,
        "hit": bool(cands),
        "accurate": accurate,
        "off_topic": is_off_topic(text, cites),
        "citations": cites[:6],
        "text_preview": text[:400],
    }


def run(run_tag: str = "b3") -> dict:
    t0 = time.time()
    per_dev = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_one, d): d for d in DEVS}
        for fut in as_completed(futures):
            info = fut.result()
            per_dev[info["dev"]] = info
    dt = round(time.time() - t0, 2)
    hits = sum(1 for v in per_dev.values() if v["hit"])
    accurate = sum(1 for v in per_dev.values() if v["accurate"])
    cost = PRICE["sonar-pro"] * len(DEVS)
    # flatten into the common per_dev shape used by other strategies
    flat = {
        d: {
            "candidates": v["candidates"],
            "best": v["best"],
            "truth": v["truth"],
            "hit": v["hit"],
            "accurate": v["accurate"],
        }
        for d, v in per_dev.items()
    }
    return {
        "name": "B3 — Perplexity parallel (5 queries)",
        "model": "sonar-pro x5",
        "query": "(5 per-dev queries)",
        "latency_s": dt,
        "cost_usd": cost,
        "status": [v["status"] for v in per_dev.values()],
        "hits": hits,
        "accurate": accurate,
        "off_topic": any(v["off_topic"] for v in per_dev.values()),
        "citations": [c for v in per_dev.values() for c in v["citations"]][:15],
        "per_dev": flat,
        "per_dev_full": per_dev,
    }


if __name__ == "__main__":
    import json, sys
    res = run(sys.argv[1] if len(sys.argv) > 1 else "b3")
    print(json.dumps(res, ensure_ascii=False, indent=2))
