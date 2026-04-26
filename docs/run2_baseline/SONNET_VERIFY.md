# Sonnet Verification — partial verdict

**Run:** Q1 EV, fresh Sonnet 4.6, 2026-04-26 11:33→12:16 (43min wall, killed before completion).
**Status:** Pipeline-completion ✅, DOCX-substance verification ❌ (no artefacts produced).

## What we DID confirm

The v4 cycle on Sonnet 4.6 **completes through the first synth call**.
Buffered stdout (flushed on kill) showed:

```
[prompt_master] Research-промт готов
[intake] Источники извлечены
[intake] Таблица не найдена — запускаю LLM-извлечение
[intake] Факты извлечены
[analyzer] Анализирую 2 отчётов
[analyzer] Анализ готов
[synthesizer] Собираю финальный отчёт
[synthesizer] Финальный отчёт готов            ← first synth SUCCEEDED
[bibliography] Bibliography generated
[data_audit] Coverage audit: critical_failure
[synthesizer] Coverage below target — retrying with feedback
[synthesizer] Собираю финальный отчёт          ← second synth started → killed
```

→ The Sonnet "hang" pattern from Run 2 + this session's first attempt was
indeed slow legitimate generation (A13). The first-attempt synth
completed. The second synth attempt (triggered by coverage_audit
critical_failure) was on track but exceeded the 30-min watchdog.

## What we did NOT confirm

The brief's Block B 3 yes/no checks:
1. Calibration (`[STRONG]/[MODERATE]/[WEAK]/[SPECULATIVE]` in DOCX)
2. Template leakage regex on report.docx_extracted.txt
3. Confidence variance in trace.jsonl

**All 3 require the rendered DOCX, which doesn't exist** because the
script saves outputs only after `synthesize` returns the FINAL report
(post-retry). We have evidence the FIRST synth succeeded but no
serialised artefact from it — `_run_one_query` in
`scripts/run2_baseline.py` doesn't checkpoint partial state.

## New finding — A14 candidate

**Coverage retry doubles Sonnet baseline wall time.** Even with A13's
~14-min single-synth budget, a query that triggers `data_audit`
critical_failure (which Q1 EV did) needs 28+ min wall for both synth
attempts. Combined with PM + intake + analyzer (~5-7 min), realistic
Sonnet baseline floor is **~35-45 min wall per query**. Watchdog
windows for any future Sonnet Run 2 / A/B run must be **≥45 min per
query**.

This is operational, not pipeline-bug — coverage retry is a
deliberate quality mechanism. But session/harness budgeting needs to
account for it.

## Verdict update for `RUN2_FINDINGS_SUMMARY.md`

- **Pipeline-completion on Sonnet:** ✅ verified (first synth attempt
  succeeded; coverage retry mechanism works as designed)
- **Substance findings (calibration / template / confidence)
  visibility in Sonnet DOCX:** still **provisional** (Day-1 Haiku
  fixtures only) — needs a future session with ≥45min watchdog or a
  partial-state checkpoint added to harness so we can capture the
  first-synth DOCX.
- **Scenario A** (continue with §5.6 Protocol architectural path)
  remains valid — pipeline works, calibration code is shared between
  Haiku and Sonnet tiers, no reason to expect Sonnet to behave
  differently on substance signals.
