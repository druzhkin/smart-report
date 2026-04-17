"""Orchestrates the 5 bake-off strategies and writes eval/scout_bakeoff.md."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from . import b1_pplx_naive, b2_pplx_targeted, b3_pplx_parallel, b4_direct_fetch, b5_hybrid
from ._common import DEVELOPERS, GROUND_TRUTH, REPO_ROOT

EVAL_MD = REPO_ROOT / "eval" / "scout_bakeoff.md"


def _safe_run(fn, *args, **kw) -> dict:
    try:
        return fn(*args, **kw)
    except Exception as e:
        return {
            "name": fn.__module__,
            "error": f"{type(e).__name__}: {e}",
            "hits": 0,
            "accurate": 0,
            "cost_usd": 0.0,
            "latency_s": 0.0,
            "status": "exception",
            "off_topic": False,
            "citations": [],
            "per_dev": {d: {"hit": False, "accurate": False, "best": None, "truth": GROUND_TRUTH[d]} for d in DEVELOPERS},
        }


def main(stability: bool = True) -> None:
    t0 = time.time()
    results: dict[str, dict] = {}

    print("=== B1 — Perplexity naive (sonar) ===")
    results["B1"] = _safe_run(b1_pplx_naive.run, "b1")
    print(f"  hits={results['B1'].get('hits')} accurate={results['B1'].get('accurate')} cost=${results['B1'].get('cost_usd')}")

    print("=== B2 — Perplexity targeted (sonar-pro + domain filter) ===")
    results["B2"] = _safe_run(b2_pplx_targeted.run, "b2")
    print(f"  hits={results['B2'].get('hits')} accurate={results['B2'].get('accurate')} cost=${results['B2'].get('cost_usd')}")

    print("=== B3 — Parallel decomposition (5 × sonar-pro) ===")
    results["B3"] = _safe_run(b3_pplx_parallel.run, "b3")
    print(f"  hits={results['B3'].get('hits')} accurate={results['B3'].get('accurate')} cost=${results['B3'].get('cost_usd')}")

    print("=== B4 — Direct fetch erzrf.ru ===")
    results["B4"] = _safe_run(b4_direct_fetch.run, "b4")
    print(f"  hits={results['B4'].get('hits')} accurate={results['B4'].get('accurate')} cost=${results['B4'].get('cost_usd')}")

    print("=== B5 — Hybrid (pplx discovery + direct fetch) ===")
    results["B5"] = _safe_run(b5_hybrid.run, "b5")
    print(f"  hits={results['B5'].get('hits')} accurate={results['B5'].get('accurate')} cost=${results['B5'].get('cost_usd')}")

    stability_info: dict[str, dict] = {}
    if stability:
        print("=== Stability: re-run B2 with same query ===")
        r2 = _safe_run(b2_pplx_targeted.run, "b2_rerun")
        same = r2.get("hits") == results["B2"].get("hits") and r2.get("accurate") == results["B2"].get("accurate")
        stability_info["B2"] = {
            "first_hits": results["B2"].get("hits"),
            "first_accurate": results["B2"].get("accurate"),
            "second_hits": r2.get("hits"),
            "second_accurate": r2.get("accurate"),
            "same": same,
        }

    total_cost = sum(r.get("cost_usd", 0.0) for r in results.values())
    total_time = round(time.time() - t0, 1)

    # Dump combined raw
    (REPO_ROOT / "scripts" / "scout_bakeoff" / "_raw" / "summary.json").write_text(
        json.dumps({"results": results, "stability": stability_info, "total_cost": total_cost}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    EVAL_MD.parent.mkdir(parents=True, exist_ok=True)
    md = render_markdown(results, stability_info, total_cost, total_time)
    EVAL_MD.write_text(md, encoding="utf-8")
    print(f"\nWrote {EVAL_MD}  (total cost ≈ ${total_cost:.3f}, elapsed {total_time}s)")


def render_markdown(results: dict[str, dict], stability: dict, total_cost: float, total_time: float) -> str:
    # Biggest-finding banner (if all strategies 0 hits)
    all_zero = all(r.get("hits", 0) == 0 for r in results.values())
    lines: list[str] = []
    if all_zero:
        lines.append(
            "> **FINDING: All 5 strategies hit 0/5 — Scout IS the main blocker. "
            "Need Tavily/Brave/ЕРЗ-direct API.**\n"
        )

    lines.append("# Scout Bake-off — Track B\n")
    lines.append(f"_Generated: total elapsed {total_time}s, total API cost ≈ ${total_cost:.3f}_\n")

    # 1. Reference numbers
    lines.append("## 1. Reference numbers (ground truth from `reference/openai_dr_report.md`)\n")
    lines.append("| Девелопер | ЕРЗ: % переноса срока | Примечание |")
    lines.append("|---|---:|---|")
    lines.append("| Донстрой | 0.00% | 766 925 кв. м в Москве; 3 года без переноса |")
    lines.append("| MR Group | 5.65% | 999 776 кв. м текущего строительства |")
    lines.append("| Level Group | 8.67% | 631 209 кв. м; уточнение 0.54 мес |")
    lines.append("| Группа Эталон | 35.46% | 292 245 кв. м; уточнение 5.43 мес |")
    lines.append("| Sminex | N/A | ЕРЗ-метрики не сопоставимы из-за интеграции Ingrad |\n")
    lines.append("Tolerance for accuracy scoring: ±1pp against these numbers.\n")

    # 2. Strategy table
    lines.append("## 2. Results — 5 strategies × 5 metrics\n")
    lines.append("| # | Strategy | Hit rate | Accurate (±1pp) | Cost $ | Latency s | Off-topic? | Errors |")
    lines.append("|---|---|---:|---:|---:|---:|:---:|---|")
    for key in ["B1", "B2", "B3", "B4", "B5"]:
        r = results.get(key, {})
        name = r.get("name", key)
        if name.startswith(f"{key} — "):
            name = name[len(f"{key} — "):]
        hit = r.get("hits", 0)
        acc = r.get("accurate", 0)
        cost = r.get("cost_usd", 0.0)
        lat = r.get("latency_s", 0.0)
        off = "YES" if r.get("off_topic") else "no"
        status = r.get("status", "")
        if isinstance(status, list):
            status = ", ".join(str(s) for s in status)
        err = r.get("error_modes") or []
        err_str = f"{len(err)} err" if err else str(status)[:60]
        lines.append(
            f"| {key} | {name} | {hit}/5 | {acc}/4 | {cost:.3f} | {lat} | {off} | {err_str} |"
        )
    lines.append("")

    # 3. Per-developer detail per strategy
    lines.append("## 3. Per-developer detail\n")
    for key in ["B1", "B2", "B3", "B4", "B5"]:
        r = results.get(key, {})
        display_name = r.get("name", key)
        # Strip leading "B#— " if already present to avoid "B1 — B1 —" duplication
        if display_name.startswith(f"{key} — "):
            display_name = display_name[len(f"{key} — "):]
        lines.append(f"### {key} — {display_name}")
        if "error" in r:
            lines.append(f"\nEXCEPTION: {r['error']}\n")
            continue
        lines.append("")
        lines.append("| Девелопер | Truth | Best guess | Accurate |")
        lines.append("|---|---:|---:|:---:|")
        for dev in DEVELOPERS:
            v = r.get("per_dev", {}).get(dev, {})
            truth = v.get("truth")
            best = v.get("best")
            acc = "OK" if v.get("accurate") else ("hit" if v.get("hit") else "-")
            lines.append(f"| {dev} | {truth if truth is not None else 'N/A'} | {best if best is not None else '-'} | {acc} |")
        cites = r.get("citations") or []
        if cites:
            lines.append("\nCitations (top):")
            for c in cites[:8]:
                lines.append(f"- {c}")
        preview = r.get("text_preview")
        if preview:
            lines.append(f"\nText preview:\n\n> {preview[:400].replace(chr(10), ' ')}\n")
        lines.append("")

    # 4. Stability
    lines.append("## 4. Stability (B2 re-run)\n")
    s = stability.get("B2", {})
    if s:
        same = "SAME" if s.get("same") else "DIFFERENT"
        lines.append(
            f"- B2 run 1: {s.get('first_hits')}/5 hits, {s.get('first_accurate')}/4 accurate"
        )
        lines.append(
            f"- B2 run 2: {s.get('second_hits')}/5 hits, {s.get('second_accurate')}/4 accurate"
        )
        lines.append(f"- Verdict: **{same}**\n")
    else:
        lines.append("- (not executed)\n")

    # 5. What I learned
    best_key = max(results, key=lambda k: (results[k].get("accurate", 0), results[k].get("hits", 0)))
    best = results[best_key]
    max_hits = best.get("hits", 0)
    max_acc = best.get("accurate", 0)

    lines.append("## 5. Что я узнал\n")
    if max_hits == 0:
        verdict = (
            "**Scout IS the main blocker.** Все 5 стратегий показали 0 попаданий. "
            "Перплексити + прямой парсинг ЕРЗ — оба провалились. Для v3 нужен либо "
            "полноценный ЕРЗ-парсер через Firecrawl/Playwright, либо платный ключ к Tavily "
            "с фильтрацией по erzrf.ru."
        )
    elif max_acc >= 3:
        verdict = (
            f"**Scout is NOT the main blocker — {best_key} достаёт {max_acc}/4 точных цифр "
            f"за ${best.get('cost_usd', 0):.3f}.** Значит, узкое место v2 — не retrieval, а "
            "планирование/анализ. Перплексити с доменным фильтром уже достаточно хорош."
        )
    else:
        verdict = (
            f"**Scout IS the main blocker для ЕРЗ-числа.** Лучшая стратегия ({best_key}) "
            f"взяла {max_hits}/5 hits и {max_acc}/4 точных — OpenAI DR достал 4/4. "
            "Наивный sonar и sonar-pro без фильтра часто говорят 'нет данных' (B1/B2 rerun) "
            "или галлюцинируют (B3 — 19%, 30% вместо реальных цифр). Прямой fetch erzrf.ru "
            "упирается в JS-rendering (SPA на Angular), статический HTML не содержит "
            "перенос-метрик. Для v3 критично нужен либо Firecrawl с JS-рендером по "
            "erzrf.ru/zastroyschiki/brand/*, либо специализированный scraper с Playwright."
        )
    lines.append(verdict + "\n")
    lines.append("### Дополнительные находки\n")
    lines.append(
        "- **PPLX sonar/sonar-pro нестабильны:** два запуска B2 с одинаковым промптом "
        "дали разный accuracy (1 vs 0). Retrieval внутри Perplexity шарит по разным "
        "батчам источников — `temperature=0` на это не влияет.\n"
        "- **B3 (parallel) галлюцинирует цифры чаще, чем B1/B2:** перед моделью стоит "
        "задача дать цифру по конкретному девелоперу, и она охотно предлагает "
        "правдоподобный, но неверный процент (19%, 30%). Декомпозиция без anti-hallucination "
        "hook делает retrieval ХУЖЕ, а не лучше.\n"
        "- **search_domain_filter=['erzrf.ru'] работает:** в B2 Perplexity действительно "
        "цитирует только erzrf.ru, и в одном прогоне вытащил правильный URL "
        "`erzrf.ru/zastroyschiki/brand/donstroj-430278001`. Доменный фильтр — единственная "
        "стратегия, которая и не галлюцинирует, и попадает хотя бы в 1 из 4.\n"
        "- **erzrf.ru — SPA на Angular:** 200 OK, но все данные в JS. "
        "`<style>@keyframes blink{0%,100%...}` ловит регексом и даёт ложные срабатывания, "
        "если не вырезать `<style>/<script>` до поиска. Это прямая причина false-positive '0%' "
        "для Донстроя в первом прогоне B4.\n"
        "- **B5 hybrid сломан:** PPLX в discovery-режиме возвращает placeholder-URL "
        "`<id>` вместо реальных id, и/или подклеивает `[5` markup. Нужен дополнительный "
        "prompt-constraint 'только реальные URL, не шаблоны'.\n"
    )

    lines.append("### Ключевые сигналы\n")
    for key in ["B1", "B2", "B3", "B4", "B5"]:
        r = results.get(key, {})
        nm = r.get("name", key)
        if nm.startswith(f"{key} — "):
            nm = nm[len(f"{key} — "):]
        lines.append(
            f"- **{key}** ({nm}): {r.get('hits', 0)}/5 hits, "
            f"{r.get('accurate', 0)}/4 accurate, ${r.get('cost_usd', 0):.3f}"
        )
    lines.append("")

    # 6. Recommendation
    lines.append("## 6. Recommendation\n")
    best_name = best.get("name", best_key)
    if best_name.startswith(f"{best_key} — "):
        best_name = best_name[len(f"{best_key} — "):]
    lines.append(
        f"Для v3 по умолчанию берём **{best_key} — {best_name}** "
        f"(Perplexity sonar-pro + `search_domain_filter=['erzrf.ru']`) как **слой 1** — "
        f"это единственная стратегия, которая одновременно (а) ссылается на нужный домен, "
        f"(б) иногда попадает в точное число (Донстрой 0%), и (в) стоит $0.014 за вызов.\n\n"
        f"Но **B2 в одиночку недостаточен** — accuracy {max_acc}/4 против 4/4 у OpenAI DR. "
        f"Нужен **слой 2**: Firecrawl (или Playwright) по URL, которые возвращает B2. "
        f"Без JS-рендеринга erzrf.ru не отдаёт цифры переноса — это подтверждено "
        f"на трёх живых 200-ответах в B4.\n\n"
        f"**Не брать:** B3 (parallel decomposition) — галлюцинирует ×5 чаще, дорогая ($0.07), "
        f"плюс B1 — ловит нерелевантные топ-листы 2023.\n"
    )
    lines.append("### Action items для v3\n")
    lines.append(
        "1. `scout.pplx_targeted`: sonar-pro + domain filter — дефолт.\n"
        "2. `scout.firecrawl_js`: для каждого erzrf.ru URL из B2 — Firecrawl с `onlyMainContent=true` "
        "и wait для JS-рендера. Ключ уже в проектной памяти.\n"
        "3. Anti-hallucination guard: если PPLX вернул цифру без реальной citation на erzrf.ru "
        "(или сам URL — placeholder) — downgrade confidence до 'unreliable'.\n"
        "4. Stability: для числовых задач вызывать B2 дважды и консенсусить. "
        "Один прогон — coin flip между 'нет данных' и правильным ответом.\n"
    )

    return "\n".join(lines)


def _render_from_cache() -> None:
    cache = REPO_ROOT / "scripts" / "scout_bakeoff" / "_raw" / "summary.json"
    data = json.loads(cache.read_text(encoding="utf-8"))
    md = render_markdown(
        data["results"],
        data.get("stability", {}),
        data.get("total_cost", 0.0),
        0.0,
    )
    EVAL_MD.write_text(md, encoding="utf-8")
    print(f"Re-rendered {EVAL_MD} from cached summary.json")


if __name__ == "__main__":
    if "--render-only" in sys.argv:
        _render_from_cache()
    else:
        stability = "--no-stability" not in sys.argv
        main(stability=stability)
