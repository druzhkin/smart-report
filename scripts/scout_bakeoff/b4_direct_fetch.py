"""B4 — Direct fetch. Hit likely erzrf.ru developer pages via WebFetch-style HTTP.

Strategy:
  1. For each developer, try a small list of candidate URL patterns on erzrf.ru.
  2. Use requests (with a realistic UA) — the site is public.
  3. Look for "перенос" / "%" patterns near the page body.
  4. If the developer page is reachable, score hit/accuracy like other strategies.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from ._common import (
    DEV_VARIANTS,
    GROUND_TRUTH,
    RAW_DIR,
    find_percent_near,
    save_raw,
)

# Known ERZ developer slug candidates. ERZ uses /zastroyschiki/brand/<slug>-<id>
# The slug is in transliterated Russian (donstroj, not donstroy). Real URLs probed 2026-04-18:
#   https://erzrf.ru/zastroyschiki/brand/donstroj-430278001 -> 200 (but JS-rendered)
#   https://erzrf.ru/zastroyschiki/brand/461175001         -> 200 (Sminex numeric-only)
CANDIDATES: dict[str, list[str]] = {
    "Донстрой": [
        "https://erzrf.ru/zastroyschiki/brand/donstroj-430278001",
        "https://erzrf.ru/zastroyschiki/brand/donstroj",
    ],
    "MR Group": [
        "https://erzrf.ru/zastroyschiki/brand/mr-group-461170001",
        "https://erzrf.ru/zastroyschiki/brand/mr-group",
    ],
    "Level Group": [
        "https://erzrf.ru/zastroyschiki/brand/level-group-461174001",
        "https://erzrf.ru/zastroyschiki/brand/level-group",
    ],
    "Эталон": [
        "https://erzrf.ru/zastroyschiki/brand/gruppa-etalon-430279001",
        "https://erzrf.ru/zastroyschiki/brand/gruppa-etalon",
    ],
    "Sminex": [
        "https://erzrf.ru/zastroyschiki/brand/461175001",
        "https://erzrf.ru/zastroyschiki/brand/sminex",
    ],
}

SEARCH_TEMPLATE = "https://erzrf.ru/search?q={q}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.8",
}


def _try_url(url: str, timeout: int = 15) -> tuple[int, str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        return r.status_code, r.text or ""
    except Exception as e:
        return 0, f"ERR: {e}"


_PERENOS_RE = re.compile(
    r"(?:перенос(?:[\s\w]{0,20})?сро(?:ка|ков)[^0-9]{0,60})(\d{1,2}(?:[.,]\d{1,2})?)\s*%",
    re.IGNORECASE | re.DOTALL,
)

_CSS_TAG_RE = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)


def _strip_js_css(html: str) -> str:
    """Remove <style> and <script> blocks (CSS keyframes would otherwise pollute %-matches)."""
    return _CSS_TAG_RE.sub(" ", html)


def _extract_perenos_pct(html: str) -> list[float]:
    """Look for '% переноса' style phrases in non-CSS HTML. Returns candidate floats."""
    if not html:
        return []
    clean = _strip_js_css(html)
    out = []
    # 1) direct "перенос срок ... N%"
    for m in _PERENOS_RE.finditer(clean):
        try:
            out.append(float(m.group(1).replace(",", ".")))
        except ValueError:
            pass
    # 2) Look near word "перенос" in any case (in cleaned HTML only)
    for m in re.finditer(r"перенос", clean, re.IGNORECASE):
        window = clean[m.start(): m.start() + 400]
        for pm in re.finditer(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%", window):
            try:
                out.append(float(pm.group(1).replace(",", ".")))
            except ValueError:
                pass
    return out


def _one(dev: str) -> dict:
    info: dict = {
        "dev": dev,
        "tried": [],
        "reached_url": None,
        "status": None,
        "bytes": 0,
        "candidates": [],
        "best": None,
        "truth": GROUND_TRUTH[dev],
        "hit": False,
        "accurate": False,
        "error_modes": [],
    }
    for url in CANDIDATES[dev]:
        status, body = _try_url(url)
        info["tried"].append({"url": url, "status": status, "bytes": len(body)})
        if status == 200 and len(body) > 2000:
            info["reached_url"] = url
            info["status"] = status
            info["bytes"] = len(body)
            # save snippet
            (RAW_DIR / f"b4_{dev}.html").write_text(body[:60000], encoding="utf-8", errors="ignore")
            cands = _extract_perenos_pct(body)
            if not cands:
                clean_body = _strip_js_css(body)
                cands = find_percent_near(clean_body, DEV_VARIANTS[dev], window=500)
            info["candidates"] = cands
            if not cands and ("перенос" not in _strip_js_css(body).lower()):
                info["error_modes"].append(f"200:{url}:JS-rendered (no static перенос data)")
            truth = GROUND_TRUTH[dev]
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
        if status in (403, 404, 429, 0):
            info["error_modes"].append(f"{status}:{url}")
    if not info["reached_url"]:
        # Fallback: search endpoint (html scrape)
        q = dev.replace(" ", "+")
        url = SEARCH_TEMPLATE.format(q=q)
        status, body = _try_url(url)
        info["tried"].append({"url": url, "status": status, "bytes": len(body)})
        if status == 200:
            info["reached_url"] = url
            info["status"] = status
            info["bytes"] = len(body)
    return info


def run(run_tag: str = "b4") -> dict:
    t0 = time.time()
    per_dev_full = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_one, d): d for d in GROUND_TRUTH.keys()}
        for fut in as_completed(futures):
            info = fut.result()
            per_dev_full[info["dev"]] = info
    dt = round(time.time() - t0, 2)
    hits = sum(1 for v in per_dev_full.values() if v["hit"])
    accurate = sum(1 for v in per_dev_full.values() if v["accurate"])
    errs = [e for v in per_dev_full.values() for e in v["error_modes"]]
    reached = sum(1 for v in per_dev_full.values() if v["reached_url"])
    save_raw(run_tag, per_dev_full)
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
        "name": "B4 — Direct fetch erzrf.ru",
        "model": "requests (no LLM)",
        "query": "GET /zastroyschiki/brand/<slug>",
        "latency_s": dt,
        "cost_usd": 0.0,
        "status": f"reached={reached}/5, errors={len(errs)}",
        "hits": hits,
        "accurate": accurate,
        "off_topic": False,
        "citations": [v["reached_url"] for v in per_dev_full.values() if v["reached_url"]],
        "per_dev": flat,
        "per_dev_full": per_dev_full,
        "error_modes": errs,
    }


if __name__ == "__main__":
    import json, sys
    res = run(sys.argv[1] if len(sys.argv) > 1 else "b4")
    print(json.dumps(res, ensure_ascii=False, indent=2))
