"""Shared helpers for the scout bake-off (Track B)."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = Path(__file__).resolve().parent / "_raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(REPO_ROOT / ".env", override=True)

PPLX_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PPLX_URL = "https://api.perplexity.ai/chat/completions"

DEVELOPERS = ["Донстрой", "MR Group", "Level Group", "Эталон", "Sminex"]

# Ground truth from reference/openai_dr_report.md (ЕРЗ срез)
GROUND_TRUTH: dict[str, float | None] = {
    "Донстрой": 0.0,
    "MR Group": 5.65,
    "Level Group": 8.67,
    "Эталон": 35.46,
    "Sminex": None,  # "не до конца сопоставимо из-за интеграции Ingrad"
}

# Rough Perplexity pricing (USD) — conservative, per call
PRICE = {
    "sonar": 0.005,        # ~$5/1M input, short calls — treat as flat per call
    "sonar-pro": 0.014,    # ~$14/1M input + search fee
    "sonar-deep-research": 2.0,
}


def pplx_chat(
    model: str,
    user_msg: str,
    *,
    search_domain_filter: list[str] | None = None,
    max_tokens: int = 1200,
    timeout: int = 90,
) -> dict[str, Any]:
    """Hit Perplexity chat/completions. Returns parsed JSON (raw)."""
    if not PPLX_KEY:
        raise RuntimeError("PERPLEXITY_API_KEY is not set")
    headers = {
        "Authorization": f"Bearer {PPLX_KEY}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": user_msg}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "return_citations": True,
    }
    if search_domain_filter:
        body["search_domain_filter"] = search_domain_filter
    t0 = time.time()
    resp = requests.post(PPLX_URL, headers=headers, json=body, timeout=timeout)
    dt = time.time() - t0
    try:
        data = resp.json()
    except Exception:
        data = {"_raw_text": resp.text}
    data["_status"] = resp.status_code
    data["_latency_s"] = round(dt, 2)
    data["_model"] = model
    return data


def save_raw(name: str, payload: Any) -> Path:
    path = RAW_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def extract_text(resp: dict[str, Any]) -> str:
    try:
        return resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""


def extract_citations(resp: dict[str, Any]) -> list[str]:
    # Perplexity puts them at top level `citations` (list of URLs)
    cites = resp.get("citations") or []
    if isinstance(cites, list):
        return [c for c in cites if isinstance(c, str)]
    return []


_PCT_RE = re.compile(
    r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%"
)


def find_percent_near(text: str, name_variants: Iterable[str], window: int = 220) -> list[float]:
    """Find all % numbers within `window` chars of any name variant."""
    if not text:
        return []
    lower = text.lower()
    hits: list[float] = []
    for variant in name_variants:
        v = variant.lower()
        start = 0
        while True:
            idx = lower.find(v, start)
            if idx == -1:
                break
            lo = max(0, idx - window)
            hi = min(len(text), idx + len(variant) + window)
            snippet = text[lo:hi]
            for m in _PCT_RE.finditer(snippet):
                try:
                    hits.append(float(m.group(1).replace(",", ".")))
                except ValueError:
                    pass
            start = idx + len(variant)
    return hits


DEV_VARIANTS = {
    "Донстрой": ["Донстрой", "Donstroy", "ДОНСТРОЙ"],
    "MR Group": ["MR Group", "MR-Group", "МР Групп", "MR "],
    "Level Group": ["Level Group", "Level ", "Левел"],
    "Эталон": ["Эталон", "Etalon", "Группа Эталон"],
    "Sminex": ["Sminex", "Сминекс"],
}


def score_text_against_truth(text: str) -> dict[str, dict]:
    """For each developer: collected % candidates + best match vs ground truth (±1pp)."""
    result = {}
    for dev, variants in DEV_VARIANTS.items():
        cands = find_percent_near(text, variants)
        truth = GROUND_TRUTH[dev]
        best: float | None = None
        accurate = False
        if truth is not None and cands:
            # Prefer candidate closest to truth
            best = min(cands, key=lambda x: abs(x - truth))
            accurate = abs(best - truth) <= 1.0
        elif truth is None and cands:
            # Sminex — any plausible (<100%) percent counts as "hit" but not accuracy
            best = cands[0]
        result[dev] = {
            "candidates": cands,
            "best": best,
            "truth": truth,
            "hit": bool(cands),
            "accurate": accurate,
        }
    return result


def summarise_scores(scored: dict[str, dict]) -> dict[str, int]:
    hits = sum(1 for v in scored.values() if v["hit"])
    # Accuracy only counts developers with a known truth (4)
    accurate = sum(1 for v in scored.values() if v["accurate"])
    return {"hits": hits, "accurate": accurate}


def is_off_topic(text: str, cites: list[str]) -> bool:
    """Heuristic: no ЕРЗ reference + no target developer + foreign-domain citations only."""
    if not text:
        return True
    t = text.lower()
    dev_hit = any(v.lower() in t for vs in DEV_VARIANTS.values() for v in vs)
    erz_hit = "ерз" in t or "erzrf" in t
    return not (dev_hit or erz_hit)
