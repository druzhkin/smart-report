"""B5 — Hybrid: B2 for discovery (URLs), then B4-style direct fetch of those URLs."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from ._common import (
    DEV_VARIANTS,
    GROUND_TRUTH,
    PRICE,
    extract_citations,
    extract_text,
    find_percent_near,
    pplx_chat,
    save_raw,
)
from .b4_direct_fetch import HEADERS, _extract_perenos_pct, _strip_js_css

DISCOVERY_QUERY = (
    "Для каждого из 5 девелоперов бизнес-класса Москвы (Донстрой, MR Group, "
    "Level Group, Группа Эталон, Sminex) дай ТОЛЬКО прямые URL страниц застройщика "
    "на erzrf.ru (формат https://erzrf.ru/zastroyschiki/brand/<slug>-<id>). "
    "Формат ответа: <девелопер> -> <url>. Только 5 строк, без пояснений."
)


def _discover_urls() -> dict[str, list[str]]:
    resp = pplx_chat(
        "sonar-pro",
        DISCOVERY_QUERY,
        search_domain_filter=["erzrf.ru"],
        max_tokens=600,
    )
    save_raw("b5_discovery", resp)
    text = extract_text(resp)
    cites = extract_citations(resp)
    urls_by_dev: dict[str, list[str]] = {d: [] for d in GROUND_TRUTH}
    url_re2 = re.compile(r"https?://erzrf\.ru[^\s)\]\"'>\[\]]*", re.IGNORECASE)

    def _clean(u: str) -> str:
        u = u.rstrip(".,;:")
        # strip Perplexity citation markers like [1, [5, ^1, (c1)
        u = re.sub(r"\[\d+.*$", "", u)
        # drop known placeholder patterns
        if "<id>" in u or "{id}" in u or u.endswith("/"):
            return ""
        return u

    for dev, variants in DEV_VARIANTS.items():
        for line in text.splitlines():
            if any(v.lower() in line.lower() for v in variants):
                for m in url_re2.finditer(line):
                    u = _clean(m.group(0))
                    if u:
                        urls_by_dev[dev].append(u)
    # Fallback: add all citations that look like erzrf brand pages (shared pool)
    pool = [c for c in cites if "erzrf.ru" in c]
    for dev in urls_by_dev:
        if not urls_by_dev[dev]:
            # try to match dev name hints inside the URL
            for u in pool:
                low = u.lower()
                for v in DEV_VARIANTS[dev]:
                    token = v.lower().split()[0].strip()
                    if token and token in low:
                        urls_by_dev[dev].append(u)
    return urls_by_dev


def _fetch_and_score(dev: str, urls: list[str]) -> dict:
    truth = GROUND_TRUTH[dev]
    info = {
        "dev": dev,
        "urls": urls,
        "reached_url": None,
        "candidates": [],
        "best": None,
        "truth": truth,
        "hit": False,
        "accurate": False,
    }
    for url in urls[:4]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        except Exception:
            continue
        if r.status_code == 200 and len(r.text) > 2000:
            info["reached_url"] = url
            cands = _extract_perenos_pct(r.text)
            if not cands:
                cands = find_percent_near(_strip_js_css(r.text), DEV_VARIANTS[dev], window=500)
            info["candidates"] = cands
            if cands:
                if truth is not None:
                    best = min(cands, key=lambda x: abs(x - truth))
                    info["best"] = best
                    info["hit"] = True
                    info["accurate"] = abs(best - truth) <= 1.0
                else:
                    info["best"] = cands[0]
                    info["hit"] = True
            break
    return info


def run(run_tag: str = "b5") -> dict:
    t0 = time.time()
    urls_by_dev = _discover_urls()
    per_dev_full = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            ex.submit(_fetch_and_score, d, urls_by_dev.get(d, [])): d
            for d in GROUND_TRUTH
        }
        for fut in as_completed(futures):
            info = fut.result()
            per_dev_full[info["dev"]] = info
    dt = round(time.time() - t0, 2)
    hits = sum(1 for v in per_dev_full.values() if v["hit"])
    accurate = sum(1 for v in per_dev_full.values() if v["accurate"])
    cost = PRICE["sonar-pro"]  # one discovery call + free fetches
    save_raw(run_tag, {"urls_by_dev": urls_by_dev, "per_dev": per_dev_full})
    flat = {
        d: {
            "candidates": v["candidates"],
            "best": v["best"],
            "truth": v["truth"],
            "hit": v["hit"],
            "accurate": v["accurate"],
        }
        for d, v in per_dev_full.items()
    }
    return {
        "name": "B5 — Hybrid (pplx discovery + direct fetch)",
        "model": "sonar-pro + requests",
        "query": DISCOVERY_QUERY,
        "latency_s": dt,
        "cost_usd": cost,
        "status": f"reached={sum(1 for v in per_dev_full.values() if v['reached_url'])}/5",
        "hits": hits,
        "accurate": accurate,
        "off_topic": False,
        "citations": [v["reached_url"] for v in per_dev_full.values() if v["reached_url"]],
        "per_dev": flat,
        "per_dev_full": per_dev_full,
        "urls_by_dev": urls_by_dev,
    }


if __name__ == "__main__":
    import json, sys
    res = run(sys.argv[1] if len(sys.argv) > 1 else "b5")
    print(json.dumps(res, ensure_ascii=False, indent=2))
