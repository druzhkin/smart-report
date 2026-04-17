# Scratchpad — night 01 (2026-04-18)

Каждый трек дописывает снизу одну строку каждые ~20 минут:
`[HH:MM] Track X: <status>, <finding>`

Критичные находки жирно.

---
[01:46] Orchestrator: repo initialized, references copied, 4 tracks spawning in parallel.
[01:52] Track D: started, references read, verbatim anti-patterns grepped (lines 115/126/469 of v2_output). Drafting planner_v1.
[01:58] Track B: scaffolding done (b1..b5 + _common), ground truth extracted (Донстрой 0%, MR 5.65%, Level 8.67%, Эталон 35.46%, Sminex N/A). Starting live runs.
[02:05] Track C: scripts/baseline_eval scaffolded (judge.py + run_baseline.py). Launching 15 sonnet-4.6 calls.
[02:25] Track C: **15/15 calls green, $1.08 (<$3 cap)**. eval/baseline.md written. **OpenAI DR wins Coverage (10/10) + Cross-domain (9); Perplexity wins Honesty (82) + lowest triviality (5); v2 wins nothing.** Judge calibrated (2/2 URL spot-checks via WebFetch PASS, v2 coverage=1 manually confirmed).
[01:53] Track A: skeleton complete, 9/9 tests green, --dry-run produces valid Report JSON (4 blocks + 2 cross-links). Files: 16, max 154 lines. No real LLM calls. $0 spent.
[02:08] Track B: bake-off done. 5 strategies × 5 devs, $0.10 total. **B2 (sonar-pro + domain filter) is best** — 1/5 hits, 1/4 accurate vs OpenAI DR 4/4. **Scout IS the main blocker for numeric tasks**: PPLX unstable (B2 rerun 1→0 accurate), B3 hallucinates 19%/30% instead of 0%/8.67%, erzrf.ru is Angular SPA — static fetch useless. v3 needs B2 + Firecrawl JS-render layer.
