# Track C — Manual calibration notes

Judge: `anthropic/claude-sonnet-4.6` via OpenRouter, temperature 0.
15 calls total (3 reports × 5 metrics). Total cost: ~$1.08, 303K input / 11K output tokens.

## Why calibration matters

If the LLM-judge is miscalibrated, its numbers are worse than useless — they give a false sense of measurement. For each metric I either spot-checked the judge against manually-verifiable ground truth (URLs, quotes) or did an independent manual count.

## Cell 1 — Perplexity × groundedness = 80%

Judge sampled 10 numeric claims, said 8/10 had a real source + plausible number.

**Manual spot-check via WebFetch on 2 URLs cited in the judge's sample:**

1. `realty.rbc.ru/news/68ed17159a7947d8c8256134` — claim "57,2% of Q3 2025 MKAD new-build sales were business class" AND "business-class demand +23,2% YoY vs market +7,7%".
   - WebFetch result: both claims verbatim in the article. "на бизнес-класс пришлось 57,2% всего спроса в границах МКАД" and "Темпы роста сегмента составили 23,2% год к году, что в три раза превысило среднерыночный показатель по спросу (+7,7% за год)". **PASS.**

2. `nikoliersdom.ru/blog/...deficita...` — claim "by 2027 Moscow risks shortage, new launches not resumed before 2028".
   - WebFetch result: both phrases in source, incl. literal "более активный вывод новых проектов возобновится не ранее 2028 года". **PASS.**

Extrapolation: 2/2 verified, 0 fabrications. Judge's 80% is **consistent with spot-check** (judge flagged ~2/10 as unsourced/softer — e.g. "более половины покупателей", "бюджет 25-30 млн руб.", which are indeed in the report without inline citations). Calibration: **good**.

## Cell 2 — Smart Report v2 × coverage = 1/10

Judge says only the `location` domain has a usable number (Perovo 2243.8k m² housing fund, 20.2 m²/person), and this is a general-district number, not business-class.

**Manual check:** I read v2 through line 550+ (out of 644). I grepped for the markers `отсутств / нет данных` — 64 hits in v2 vs 1 in perplexity and 2 in openai_dr. Every section opens with "данные отсутствуют" followed by speculation. The "strongest number" ("сильнейшая цифра") for most blocks is literally stated as "Нет конкретных числовых данных" or "Найдена статья по физике элементарных частиц, нерелевантная теме."

There IS one other near-miss: Perplexity-report line 27 includes an "умный дом у 72% покупателей" number that is arguably a buyer-coverage signal, but v2 does NOT have any comparable number. So judge's score of 1/10 is **correct**. Calibration: **good**.

## Cell 3 — v2 × honesty = 52 (bonus manual check)

The judge gave v2 a middling honesty score despite its constant "отсутствуют данные" refrain. Why not higher? Because v2 simultaneously publishes unsourced numeric speculations ("premium 5%", "translation coefficient 0.6-0.7", "premium 2,25–9,75%") presented as findings, not hypotheses. I verified line 126: "сильный бренд девелопера… ценовую премию в диапазоне 5% и сокращать сроки… на 10%" — no source, no error bars, presented as a conclusion. Judge caught this pattern. Calibration: **good** — the honesty metric correctly penalizes "honest about missing data, then makes up numbers anyway".

## Overall verdict

Judge is **well-calibrated** for this eval. 3/3 spot-checks matched its scoring. Scores are usable as a v3 baseline target without prompt rewrites.

## Bias disclosures (confounders)

- **Perplexity (17K chars)** — short, focused, synthesized. Coverage 7/10 is partly a length limitation, not a quality floor.
- **OpenAI DR (28K chars)** — longer and denser; naturally covers more domains. Triviality count (7) is larger in absolute terms than Perplexity (5) but proportionally smaller. Non-triviality comparison across sizes is noisy.
- **Smart Report v2 (181K chars, truncated to 105K for judge)** — massive length means it has more absolute trivialities (18) but the per-char density of banalities is also higher. Truncation (dropped middle ~76K chars) may have missed some content; however, v2 is template-driven and the remaining sections are structurally representative.
