# Smart Report Premium Pipeline Handoff

Date: 2026-04-29

## Current Verdict

The product is meaningfully closer to a paid 10,000 RUB analytical package, but
it is not honestly "10/10" yet.

The core improvement is no longer cosmetic only. The system now has:

- a stricter paid-delivery readiness gate;
- a deep analytic map that can produce follow-up research leads;
- automatic analytic-depth follow-up jobs;
- a separate long-form premium DOCX report;
- a separate premium PPTX executive deck;
- a premium delivery ZIP package;
- a mission-control UI for long running research jobs.

The main remaining gap is visual QA and real-world report evaluation on several
golden tasks. The code can generate the artifacts, but the final bar needs
rendered-page review and content-quality evals on real research sessions.

## What Was Added

### Premium Analytical Layer

Files:

- `smart_report/analytic_depth.py`
- `docs/DEEP_ANALYTIC_LAYER_BLUEPRINT.md`
- `tests/test_analytic_depth.py`

Capabilities:

- infers broad research domain;
- creates an issue tree;
- generates competing hypotheses;
- identifies evidence probes and disconfirming probes;
- proposes benchmark questions;
- proposes prioritized research leads;
- emits analytic-depth events during v4 analysis;
- exposes `GET /api/v4/sessions/{id}/analytic-depth`.

### Executable Analytic Follow-Up

Files:

- `smart_report/api/v4_endpoints.py`
- `frontend/lib/apiV4.ts`
- `frontend/app/v4/chat/Workspace.tsx`
- `tests/test_v4_endpoints.py`

Capabilities:

- `POST /api/v4/sessions/{id}/auto-depth-leads`;
- turns selected analytic-depth research leads into async DR jobs;
- marks those jobs as follow-up, so results land in `followup_reports`;
- stores analytic lead metadata on pending jobs;
- v4 UI shows "Analytic-depth dobor" CTA after analysis;
- final synthesis waits until all parallel follow-up jobs finish.

### Analytic Closure Scoring

Files:

- `smart_report/analytic_closure.py`
- `tests/test_analytic_closure.py`
- `smart_report/api/v4_endpoints.py`

Endpoint:

- `GET /api/v4/sessions/{id}/analytic-closure`

Capabilities:

- scores whether follow-up reports appear to close analytic-depth leads;
- separates `closed`, `partial`, `not_closed`, and `not_started`;
- checks transparent signals instead of pretending to prove truth: topical
  overlap, URL citations, numeric evidence, source language, candidate-source
  matches, and conflict-adjudication language;
- included in `audit-json`, `data-pack`, and the premium delivery package as
  `06_analytic_closure.json`.
- exposed in the v4 final-report UI through the "Closure score" action next
  to the analytic map and export controls.

Limitation:

- this is a deterministic coverage heuristic. It proves that follow-up material
  addressed the lead enough to be reviewable; it does not replace analyst
  judgment or source-quality evaluation.

### Follow-Up Routing Fix

Files:

- `smart_report/sources/llm_deepresearch.py`
- `smart_report/api/v4_endpoints.py`
- `tests/test_openai_dr_responses_stream.py`

Fixed bug:

- completed follow-up LLM DR jobs were previously at risk of landing in
  `source_reports`;
- now `is_followup=True` routes them to `followup_reports`;
- pending DR jobs are upserted instead of duplicated, preserving streaming
  fields.

### Premium Readiness Gate

Files:

- `smart_report/exporters/premium/readiness.py`
- `frontend/lib/apiV4.ts`
- `frontend/app/v4/chat/Workspace.tsx`
- `tests/test_premium_readiness.py`

Capabilities:

- `GET /api/v4/sessions/{id}/premium-readiness`;
- stricter than normal client readiness;
- checks evidence volume, authoritative sources, numeric facts, consensus,
  conflicts, unresolved gaps, visual/delivery requirements, and client surface;
- visible beside the final report in the v4 UI;
- included in `audit-json` and `data-pack`.

### Premium DOCX Report

Files:

- `smart_report/exporters/premium/models.py`
- `smart_report/exporters/premium/planner.py`
- `smart_report/exporters/premium/document.py`
- `smart_report/exporters/premium/docx.py`
- `tests/test_premium_document.py`

Export:

- `GET /api/v4/sessions/{id}/export?format=premium-docx&allow_draft=true`

Capabilities:

- long-form report structure;
- cover;
- executive evidence scorecard;
- embedded premium readiness gate;
- report structure section;
- evidence tables;
- source quality tables;
- scenario/risk/decision blocks;
- appendices;
- document properties;
- Smart Report header/footer;
- page-number field;
- table padding and autofit.

Smoke artifacts produced:

- `output/doc/premium_design_smoke.docx`
- `output/doc/premium_readiness_smoke.docx`

### Premium PPTX Deck

Files:

- `smart_report/exporters/premium/pptx.py`
- `smart_report/exporters/premium/__init__.py`
- `smart_report/exporters/__init__.py`
- `tests/test_premium_document.py`

Export:

- `GET /api/v4/sessions/{id}/export?format=premium-pptx&allow_draft=true`

Capabilities:

- separate executive deck, not a renamed report;
- cover slide;
- executive answer slide;
- paid-readiness slide;
- evidence-base slide;
- section-level analytical slides;
- next-decisions close slide.

Smoke artifact produced:

- `output/doc/premium_deck_smoke.pptx`

### Premium Delivery Package

Files:

- `smart_report/api/v4_endpoints.py`
- `frontend/components/v4/ExportDropdownV4.tsx`
- `frontend/components/v4/chat/FinalReportBlock.tsx`
- `frontend/app/v4/doc/[id]/DocView.tsx`
- `frontend/app/v4/chat/Workspace.tsx`
- `tests/test_v4_endpoints.py`

Export:

- `GET /api/v4/sessions/{id}/export?format=premium-package&allow_draft=true`

ZIP contents:

- `00_manifest.json`
- `01_premium_report.docx`
- `02_premium_deck.pptx`
- `03_premium_readiness.json`
- `04_client_readiness.json`
- `05_audit.json`
- `06_analytic_closure.json`
- `07_artifact_qa.json`
- `08_sources.csv`
- `09_facts.csv`
- `10_data_pack.zip`

Note:

- `07_artifact_qa.json` is generated during premium package export. In an
  environment without LibreOffice/Poppler it will report structural QA passed
  and render QA blocked rather than pretending the artifact was visually
  inspected.

### Premium Artifact QA

Files:

- `scripts/premium_artifact_qa.py`
- `tests/test_premium_artifact_qa.py`

Command:

```powershell
python scripts\premium_artifact_qa.py --docx output\doc\premium_design_smoke.docx --pptx output\doc\premium_deck_smoke.pptx --out-dir tmp\premium_artifact_qa --json tmp\premium_artifact_qa\qa.json
```

Capabilities:

- opens generated DOCX and PPTX artifacts without changing them;
- checks structural delivery markers: cover brand, scorecard, readiness gate,
  report structure, slide count, table count, and text volume;
- detects internal marker leakage such as `[STRONG]`, `[REF:]`, and raw
  pipeline field names;
- attempts DOCX/PPTX -> PDF -> PNG visual rendering when `soffice` and
  `pdftoppm` are installed;
- returns `blocked` instead of pretending visual QA passed when render tools
  are missing.

Current local result:

- structural QA passed for `premium_design_smoke.docx` and
  `premium_deck_smoke.pptx`;
- visual render QA is blocked because `soffice` and `pdftoppm` are not in
  PATH;
- JSON report written to `tmp\premium_artifact_qa\qa.json`.

### Golden-Set Package Evaluation

Files:

- `scripts/premium_golden_eval.py`
- `tests/test_premium_golden_eval.py`

Command:

```powershell
python scripts\premium_golden_eval.py --label premium-smoke --docx output\doc\premium_design_smoke.docx --pptx output\doc\premium_deck_smoke.pptx --artifact-qa-json tmp\premium_artifact_qa\qa.json --json tmp\premium_artifact_qa\golden_eval.json --csv tmp\premium_artifact_qa\golden_eval.csv
```

Capabilities:

- produces a deterministic 10k-RUB scorecard without live LLM/provider calls;
- scores content depth, evidence, analytic closure, design package, and
  delivery safety;
- accepts DOCX/PPTX plus optional `audit-json` and artifact-QA JSON;
- writes comparable JSON/CSV outputs for golden-task tracking.

Current smoke result:

- verdict: `not_acceptable`;
- overall score: `33/100`;
- content/design structure is present, but evidence/closure/delivery safety
  are not proven for the smoke artifact;
- blockers: visual QA not passed, premium readiness not ready, client readiness
  not ready.

### Long-Running Research UX

Files:

- `frontend/app/v4/chat/Workspace.tsx`
- `frontend/app/workspace.css`
- `frontend/components/v4/chat/FinalReportBlock.tsx`
- `frontend/lib/apiV4.ts`

Capabilities:

- mission-control panel inside the DR progress artifact;
- shows all active research jobs in flight;
- displays service, mode, follow-up flag, state, percent/polling label, and
  elapsed time;
- user can switch the progress artifact between jobs.
- final report actions expose analytic map and closure score so long-running
  work becomes inspectable instead of invisible.

### Draft-Safe Export UX

Files:

- `frontend/lib/apiV4.ts`
- `frontend/components/v4/ExportDropdownV4.tsx`
- `frontend/components/v4/chat/FinalReportBlock.tsx`
- `frontend/app/v4/doc/[id]/DocView.tsx`
- `frontend/app/v4/chat/Workspace.tsx`

Behavior:

- v4 export menus explicitly pass `allow_draft=true`;
- backend readiness gate remains intact for direct API calls without
  `allow_draft=true`;
- the UI no longer opens raw 409 JSON when a user downloads a gated draft.

## Verification Already Run

Backend:

```powershell
pytest -q tests\test_v4_endpoints.py tests\test_premium_document.py tests\test_premium_readiness.py
```

Result:

- `41 passed`

Analytic closure:

```powershell
pytest -q tests\test_analytic_closure.py tests\test_analytic_depth.py tests\test_v4_endpoints.py
```

Result:

- `39 passed`

Golden evaluator:

```powershell
pytest -q tests\test_premium_golden_eval.py tests\test_premium_readiness.py tests\test_v4_endpoints.py
```

Result:

- `40 passed`

Readiness integration update:

- premium readiness now consumes analytic closure when must-priority leads
  exist;
- missing or low closure score blocks paid premium readiness.

Premium artifact QA:

```powershell
pytest -q tests\test_premium_artifact_qa.py tests\test_premium_document.py
python scripts\premium_artifact_qa.py --docx output\doc\premium_design_smoke.docx --pptx output\doc\premium_deck_smoke.pptx --out-dir tmp\premium_artifact_qa --json tmp\premium_artifact_qa\qa.json
```

Result:

- `6 passed`;
- structural QA passed;
- render QA status is `blocked` because LibreOffice/Poppler are missing.

Frontend:

```powershell
cd frontend
npm run build
```

Result:

- build passed

Latest frontend check after closure-score UI:

```powershell
cd frontend
npm run build
```

Result:

- build passed

Additional checks:

```powershell
git diff --check
```

Result:

- clean except expected CRLF warnings on Windows.

Dev server:

- existing port `3000` was occupied by another Node process and returned 404
  for `/v4/chat`;
- this repo frontend was started on `http://localhost:3010/v4/chat`;
- HTTP check returned 200.

## Remaining Blockers Before Honest 10/10

### 1. Visual QA is now operational locally

DOCX/PPTX artifacts were structurally opened and inspected via Python libraries,
and `scripts/premium_artifact_qa.py` now performs rendered-page review when
LibreOffice and Poppler are available. On this workstation both tools were
installed via `winget`, and strict render QA passes on the premium smoke
artifacts.

Verified command:

```powershell
python scripts\premium_artifact_qa.py --docx output\doc\premium_design_smoke.docx --pptx output\doc\premium_deck_smoke.pptx --out-dir tmp\premium_artifact_qa_rendered --json tmp\premium_artifact_qa_rendered\qa.json --strict
```

Result:

- status: `passed`;
- DOCX rendered to 14 PNG pages;
- PPTX rendered to 11 PNG slides;
- visual review index written to `tmp\premium_artifact_qa_rendered\index.html`;
- premium ZIP now includes `07_artifact_qa.json` plus rendered QA assets under
  `07_artifact_qa/` when render tools are present.
- premium ZIP also includes `11_evidence_audit.json`, a claim-level support
  audit for executive conclusions.

Remaining design work:

- inspect the rendered index manually for overflow, awkward tables, broken
  typography, headers/footers, and weak page breaks;
- raise the deck from "functional consulting" to "agency-grade" visual quality.

### 2. Golden-task evaluation is still needed

The code path is now instrumented with `scripts\premium_golden_eval.py`.
It supports both single-package evaluation and manifest-based leaderboard
evaluation across multiple golden tasks.

Commands:

```powershell
python scripts\premium_golden_eval.py --label premium-smoke --docx output\doc\premium_design_smoke.docx --pptx output\doc\premium_deck_smoke.pptx --artifact-qa-json tmp\premium_artifact_qa_rendered\qa.json --json tmp\premium_artifact_qa_rendered\golden_eval.json --csv tmp\premium_artifact_qa_rendered\golden_eval.csv
python scripts\premium_golden_eval.py --label premium-package --package-zip output\golden\market_forecast\premium_delivery_package.zip --json tmp\premium_package_eval.json --csv tmp\premium_package_eval.csv
python scripts\premium_golden_eval.py --manifest eval\premium_golden_tasks.example.json --json tmp\premium_golden_leaderboard.json --csv tmp\premium_golden_leaderboard.csv
```

The example manifest lives at `eval\premium_golden_tasks.example.json`.
It defines the minimum cross-domain set needed to avoid overfitting the
pipeline to one Moscow real-estate task. Manifest rows can now point directly
to `package_zip`; this is the preferred mode because it evaluates the same
premium ZIP the client would receive.

Still needed: enough real generated reports must be judged against the
paid-client rubric.

Needed golden tasks:

- Moscow primary real estate forecast;
- US public-company 10-K financial report;
- legal/regulatory report;
- technical audit report;
- competitive/strategy report.

For each task, collect:

- premium readiness score;
- client readiness status;
- number of sources;
- authoritative source count;
- numeric fact count;
- report length;
- table count;
- deck slide count;
- human verdict: would a client accept this for 10,000 RUB?

### 3. Draft exports are intentionally separate from client delivery

Users can still download drafts, but strict delivery is now a distinct export
path. The UI exposes:

- "Download draft";
- "Deliver to client";
- "Regenerate / run deeper research".

The `premium-client-package` endpoint returns HTTP 409 when client readiness,
premium readiness, artifact QA, analytic closure, or claim-support evidence
gates fail. Current weak smoke reports are blocked because readiness,
analytic closure, and/or claim-level evidence support are not good enough,
not because render tooling is missing.

### 4. Evidence-support audit now blocks unsupported conclusions

New module:

- `smart_report\evidence_audit.py`
- `smart_report\adjudication_audit.py`

Purpose:

- extracts visible client-facing conclusions from executive answer, top
  findings, ranking rationales, callouts, key numbers, and analysis consensus;
- scores each claim for inline citation markers, analysis-level supporting
  sources, and numeric fact matches;
- emits `supported`, `partial`, or `unsupported` per conclusion;
- feeds premium readiness and strict client-package gating.

This is intentionally heuristic. It does not prove that a claim is true; it
prevents paid delivery when important conclusions have no visible evidentiary
backing.

### 5. Conflict adjudication audit now blocks unresolved conflicts

New module:

- `smart_report\adjudication_audit.py`

Purpose:

- checks whether conflicts from `AnalysisOutput.conflicts` are visibly
  addressed in the client report;
- looks for both sides/sources, the conflict topic, analyzer resolution hints,
  adjudication language, and scope/limitation language;
- emits `resolved`, `bracketed`, or `unresolved` per conflict;
- blocks strict paid delivery when critical conflicts remain unresolved.

Premium ZIP now includes `12_adjudication_audit.json`. The golden evaluator
includes an `adjudication` subscore so a report cannot score as premium-ready
by having citations while still avoiding hard disagreements.

### 6. Manual visual review gate now exists

New module:

- `smart_report\visual_review.py`

Purpose:

- separates mechanical render success from actual paid-client visual quality;
- creates six manual review checks: overflow, tables, hierarchy, page/slide
  breaks, visual alignment, and overall polish;
- writes `13_visual_review.json` into premium ZIP;
- strict `premium-client-package` blocks with `visual_review_not_approved`
  until review is explicitly approved.

The export endpoint accepts `visual_review_approved=true`, but the frontend
does not pass it automatically. That is intentional: the user should inspect
`07_artifact_qa/index.html` before approving client delivery.

### 7. Fixture-based golden package baseline now exists

New script:

- `scripts\build_premium_golden_packages.py`

New fixture manifest:

- `eval\premium_golden_fixture_manifest.json`

Purpose:

- builds real premium ZIP packages from saved completed v4 fixtures without
  live model calls;
- evaluates each ZIP via `scripts\premium_golden_eval.py`;
- writes per-package `golden_eval.json` plus a summary JSON;
- keeps the golden flow universal: the fixture manifest can point at any
  completed Smart Report topic.

Current baseline on 2026-04-30:

- `ev-competitive-strategy`: 72/100, `strong_draft_not_paid_ready`;
- `moscow-real-estate-market`: 70/100, `strong_draft_not_paid_ready`;
- `eu-dac-regulatory`: 67/100, `useful_internal_draft`;
- average score: 69.7/100;
- paid-client-ready rate: 0%.

This is the honest product status. The premium report/deck package now passes
mechanical design/render QA on these fixtures, but it is still not worth
claiming as a 10/10 paid client artifact because analytic closure is open and
some client-facing conclusions lack enough evidence support.

### 8. Next Research Brief is now included in premium ZIP

Premium ZIP now includes:

- `14_next_research_brief.md`

Purpose:

- turns the analytic-depth plan into executable follow-up prompts;
- lists must/should leads, closure status, recommended service, rationale,
  target entities/metrics, candidate sources, missing closure signals,
  benchmark questions, and monitoring indicators;
- gives a concrete path from draft to paid-client-ready instead of only
  blocking export.

This does not lower the quality bar. It makes the bar operational.

### 9. Analytic-depth follow-up results now preserve lead lineage

New/updated behavior:

- completed `auto-depth-leads` follow-up reports receive a markdown metadata
  header with `lead_id`, `kind`, `priority`, rationale, candidate sources, and
  linked gaps/conflicts;
- interrupted LLM follow-up partials accepted through `auto-dr-accept-partial`
  now go to `followup_reports`, not `source_reports`;
- accepted partials also preserve the same analytic-depth lead marker;
- `analytic_closure` recognizes the marker and scores the relevant lead
  directly instead of guessing only by loose keyword overlap.

This is a core reliability fix for long-running research: even if the browser
or server loses the live task, recovered partial work can still close the
correct branch of the research tree.

### 10. Source-authority gate now recomputes official sources

New module:

- `smart_report\source_authority.py`

Purpose:

- counts high-reliability sources;
- recognizes conservative official/regulatory/government domains such as
  government sites, EU institutions, central banks, tax/ministry domains, and
  primary bibliography refs;
- prevents old fixture metadata from falsely blocking reports that clearly
  contain official primary sources.

Current effect: the EU DAC fixture moved to `client_ready=true`, while premium
delivery remains blocked by the real unresolved issues: analytic closure and
unsupported conclusions.

### 11. Evidence support now uses qualitative fact backing

New/updated behavior:

- evidence audit checks `AnalysisOutput.all_qualitative_facts` with source refs,
  not only inline citations and numeric facts;
- numeric matching handles CO2/CO2-style claims more robustly and avoids
  treating formula digits as standalone ordinary evidence tokens;
- regression tests cover sourced qualitative backing and CO2 numeric matching;
- fixture-golden average moved to 73.0/100: EV 74, Moscow 71, EU DAC 74.

This improves the gate without weakening it. Conclusions still fail when they
have no visible citation, no source-linked fact overlap, and no numeric support.

### 12. Analytic-depth progress is now visible in the UI

New/updated behavior:

- `/auto-depth-leads` returns lead rationale, candidate sources, and linked
  gaps/conflicts alongside the task id;
- the v4 chat progress panel shows a selected lead card with lead id, kind,
  priority, rationale, and candidate sources;
- old DR polling is preserved. The extra card appears only for analytic-depth
  follow-up jobs that carry lead metadata.

### 13. Synthesizer prompt now has a structured evidence contract

Added a mandatory instruction that every structured insight, especially
`ranking[].rationale`, must carry a concrete `[REF:url]` or an explicit
verification caveat. This targets the remaining unsupported-conclusion blocker
at generation time rather than relaxing downstream audits.

### 14. Analytic-depth now turns readiness blockers into executable leads

New lead types:

- `strengthen_source_base`: emitted when the report has too few authoritative
  sources. For Russian-market topics it points the runner toward CBR, DOM.RF,
  наш.дом.рф, mos.ru, ERZ, Metrium research, and Rosstat instead of accepting
  media-only evidence as paid-ready.
- `support_claim`: emitted for unsupported client-facing conclusions found by
  the evidence audit. The prompt asks the runner to support, qualify, or
  disprove the exact claim and recommend keep/soften/remove.

Current effect:

- Moscow fixture now starts the next-research brief with `authority_sources`
  and `support_ranking_4`.
- EU DAC fixture now starts with `support_ranking_*` leads for unsupported
  structured ranking claims.
- Golden score remains 73.0/100 because the fixture packages still have no
  executed follow-up reports. This is correct: planning a fix is not the same
  as closing the evidence.

### 15. Live frontend/backend smoke status

Verified on 2026-04-30:

- backend started on `127.0.0.1:8020` with
  `python -m uvicorn smart_report.api.main:app --host 127.0.0.1 --port 8020`;
- frontend dev server served `/v4/chat` on port `3001`;
- unauthenticated `/v4/chat` redirected to `/login?next=%2Fv4%2Fchat`;
- signup with a fresh local test account redirected into `/v4/chat`;
- browser console had no errors after backend was available.

Important finding:

- the earlier `/api/auth/me` failure was caused by frontend running without the
  backend API on `8020`, not by the v4 chat UI itself;
- this does not prove the product is paid-ready. It only proves the local
  authenticated workspace can load when the expected API process is running.

### 16. Contract tests for the next-research system

Added regression coverage that the premium package contains an actionable
`14_next_research_brief.md`, including priority leads, prompt text, rationale,
recommended service, and candidate sources.

Added regression coverage that `/auto-depth-leads` returns and stores the
metadata needed by the UI and follow-up collector:

- rationale;
- candidate sources;
- linked gaps/conflicts/claims;
- prompt preview;
- analytic-depth lead id on the pending job.

### 17. Main chat flow exposes analytic-depth follow-up

The primary post-upload analysis path now shows an additional CTA for
`Analytic-depth` follow-up research, matching the already-supported
analyze-existing-reports path.

This is additive:

- the legacy follow-up CTA remains available;
- the manual follow-up upload path remains available;
- no export path was removed or renamed.

### 18. Completed LLM follow-up jobs no longer look lost

Fixed the `/auto-dr-status` fallback for completed OpenAI/Perplexity jobs after
the streaming runner removes them from `pending_dr_jobs`.

Before:

- if a first-pass LLM DR job completed, the fallback could find the uploaded
  markdown in `source_reports`;
- if an analytic-depth follow-up LLM job completed, its result was correctly
  stored in `followup_reports`, but the fallback did not search that bucket;
- polling could return `404 task_id not found`, making the UI look stuck or
  disconnected even though the job had completed.

Now:

- the fallback searches both `source_reports` and `followup_reports`;
- it recognizes `auto_followup_openai_<id>.md` and
  `auto_followup_perplexity_<id>.md`;
- the UI can surface `completed` for already-promoted analytic-depth results.

Regression coverage:

- `test_auto_dr_status_finds_completed_llm_followup_after_pending_removed`
- focused suite: `91 passed`
- frontend production build: passed

### 19. Premium refinement orchestrator endpoint

Added `POST /api/v4/sessions/{session_id}/premium-refine`.

Purpose:

- give the UI a single safe "continue premium refinement" action;
- avoid forcing the user to know whether the next step is waiting for running
  follow-up jobs, launching analytic-depth leads, or resynthesizing after
  follow-up evidence arrives;
- keep all existing endpoints intact.

Decision order:

1. If follow-up jobs are already running, return `wait_for_followups` with task
   ids.
2. If analytic closure has open priority leads, submit selected analytic-depth
   follow-up jobs and return `submitted_followups`.
3. If follow-up reports exist and the current final report has not incorporated
   them, start `/synthesize` and return `synthesize_started`.
4. Otherwise return `ready_or_blocked` with current closure/readiness details.

Also added frontend API typing/helper:

- `runPremiumRefine()` in `frontend/lib/apiV4.ts`;
- `PremiumRefineOut` type;
- frontend `ResearchLeadKind` now includes `strengthen_source_base` and
  `support_claim`.

Safety fix:

- `_async_mode_for_lead()` now normalizes invalid provider modes. In particular,
  Perplexity leads no longer try to submit `mode=standard`; they fall back to
  `mode=deep`.

Regression coverage:

- `test_premium_refine_waits_for_running_followup_jobs`
- `test_premium_refine_submits_open_analytic_depth_leads`
- `test_premium_refine_starts_synthesis_after_followup_without_open_leads`
- focused suite: `94 passed`
- frontend production build: passed

Golden status remains unchanged at 73.0/100 because fixtures still contain no
executed follow-up reports. The orchestrator improves the path to closure; it
does not fabricate closure evidence.

### 20. Main UI now calls the premium refinement orchestrator

The main post-analysis CTA now calls `premium-refine` instead of directly
calling `auto-depth-leads`.

Behavior:

- if follow-up jobs are already running, the UI opens the DR progress panel;
- if the backend submits premium follow-up leads, the UI seeds the same live
  progress cards used by the manual analytic-depth flow;
- if follow-up evidence is already available and resynthesis is needed, the UI
  waits for the synthesis long task and opens the refreshed report;
- if no automatic step is available, it shows current closure/readiness scores.

The older `run-depth-leads` action remains implemented as a manual/fallback
path. This preserves the previous flow while making the primary CTA closer to
the promised "keep working until paid-ready" behavior.

Verification:

- frontend production build: passed;
- focused premium/v4/evidence suite: `96 passed`;
- `git diff --check`: no whitespace errors, CRLF warnings only.

### 21. Premium refinement status endpoint

Added a non-mutating status endpoint:

- `GET /api/v4/sessions/{session_id}/premium-refinement-status`

It returns the deterministic next step for a long premium run:

- `run_analysis`
- `submit_followups`
- `wait_for_followups`
- `wait_for_synthesis`
- `synthesize`
- `inspect_blockers`
- `ready`

This exists because premium runs can take 30-60 minutes. The frontend can now
explain whether the system is waiting for provider research, waiting for
synthesis, ready to submit the next analytic-depth branch, or blocked by
paid-delivery quality gates.

Also tightened provider mode normalization: invalid mode overrides fall back to
the safe provider default. Example: `perplexity + standard` becomes
`perplexity + deep`.

Coverage added:

- `test_premium_refinement_status_recommends_next_step`
- `test_async_mode_for_lead_rejects_invalid_provider_override`

Verification:

- `pytest -q tests\test_v4_endpoints.py -k "premium_refinement_status or premium_refine or async_mode"`
- `cd frontend && npm run build`
- expanded premium/v4/evidence suite: `96 passed`

### 22. Visible premium loop status card

The chat workspace now has a `premium-status` artifact view titled
`Premium Refinement Loop`.

It shows:

- backend-recommended next step;
- pending follow-up task count;
- whether resynthesis is still needed;
- analytic closure score and open lead counts;
- paid-delivery readiness score and first blocker.

This is a UX guard against the "it hangs" perception during 30-60 minute
research loops. It does not change the old DR progress card; when actual
follow-up jobs are submitted, the UI still opens the live DR progress panel.

The card now auto-refreshes every 15 seconds while it is open, so the user can
leave the inspector visible during a long run and still see whether the backend
has moved from waiting to synthesis or blocker inspection.

The final report header now also has a `premium status` action. This opens the
same inspector from the report view, so the user can see why a generated report
is not paid-ready without scrolling back through chat history.

Implementation:

- `frontend/app/v4/chat/types.ts`
- `frontend/app/v4/chat/Workspace.tsx`
- `frontend/app/workspace.css`
- `frontend/lib/apiV4.ts`

Verification:

- `cd frontend && npm run build`
- expanded premium/v4/evidence suite: `96 passed`
- focused status/refine contract tests: `5 passed`

### 23. Golden rebuild after status-card work

Golden package rebuild was run in two modes:

```powershell
python scripts\build_premium_golden_packages.py --fixture-manifest eval\premium_golden_fixture_manifest.json --out-root output\golden --summary-json output\golden\summary.json
python scripts\build_premium_golden_packages.py --fixture-manifest eval\premium_golden_fixture_manifest.json --out-root output\golden_visual_approved --summary-json output\golden_visual_approved\summary.json --visual-review-approved
```

Results:

- without manual visual approval: `65.3/100`, verdict
  `useful_internal_draft`;
- with visual approval flag: `73.0/100`, verdict
  `strong_draft_not_paid_ready`;
- per-task visual-approved scores remain EV `74`, Moscow `71`, EU DAC `74`.

Interpretation:

- the premium visual/structure package is strong enough for the evaluator's
  design metrics;
- the unapproved visual-review gate correctly keeps the package below
  paid-ready;
- the real product blocker is still analytic closure: saved fixtures have no
  executed follow-up research, so closure remains open and premium readiness
  remains red.

### 24. DOCX page-count metric for artifact QA

Added page-count metrics to:

- `scripts/premium_artifact_qa.py`
- `scripts/premium_golden_eval.py`

The artifact QA now records:

- `estimated_pages`: conservative fallback from DOCX text/table volume;
- `rendered_pages`: exact rendered DOCX page count when LibreOffice/Poppler
  conversion succeeds;
- `rendered_slides`: rendered PPTX slide count when conversion succeeds.

This matters because the product promise includes a 20+ page long-form report.
When rendered-page inspection is available, delivery gates use `rendered_pages`;
otherwise they fall back to `estimated_pages` instead of pretending exact page
count is known.

Verification:

- `pytest -q tests\test_premium_artifact_qa.py tests\test_premium_golden_eval.py`
- `python scripts\premium_artifact_qa.py --docx output\doc\premium_design_smoke.docx --pptx output\doc\premium_deck_smoke.pptx --out-dir tmp\premium_artifact_qa_current --json tmp\premium_artifact_qa_current\qa.json --strict`
- visual-approved golden rebuild remains `73.0/100`

### 25. Premium package gate blocks under-length reports

`premium-client-package` now checks the DOCX page-count metric from artifact
QA. It prefers exact `rendered_pages` and falls back to conservative
`estimated_pages`. If the long-form report is below 20 pages, the package gate
adds:

- `premium_report_below_20_pages`

This keeps the "20+ page report" promise in the client-delivery gate instead
of leaving it as a design aspiration. It deliberately lives at package-gate
level because only the rendered/inspected DOCX artifact can approximate actual
delivery length; raw `FinalReport` text is not the final long-form document.

Verification:

- `pytest -q tests\test_v4_endpoints.py -k "premium or full_flow"`
- page-count unit tests confirm `rendered_pages` overrides `estimated_pages`

Latest golden-package rebuild:

- EV competitive strategy: `rendered_pages=50`, `estimated_pages=31`;
- Moscow real estate market: `rendered_pages=40`, `estimated_pages=27`;
- EU DAC regulatory: `rendered_pages=37`, `estimated_pages=27`.

So the real fixture-generated premium packages clear the 20+ page promise. The
remaining golden blockers are analytic closure, readiness, visual approval, and
unsupported conclusions, not report length.

### 26. Multi-followup polling race fixed

Fixed a frontend race in the async DR polling loop. With several parallel
follow-up / analytic-depth jobs, each completed task previously checked a ref
that could still include another completed-but-not-yet-rendered task. In the
worst case, every task could decide that "another follow-up is still running",
so none of them would trigger final synthesis.

The completion path now updates `activeResearchTasksRef` synchronously before
checking remaining follow-up jobs. The last completed follow-up is therefore
the one that continues into synthesis.

Verification:

- `cd frontend && npm run build`
- `pytest -q tests\test_v4_endpoints.py -k "premium_refinement_status or premium_refine or auto_dr_status"` -> `9 passed`

### 27. Premium DOCX now has a client decision dashboard

Added a `Client Decision Dashboard` immediately after the cover page in the
premium DOCX renderer.

Purpose:

- give the client a fast one-page control panel before the long report;
- summarize executive answer, evidence depth, paid-delivery gate, and next
  action;
- make the document feel closer to a consulting report and less like a raw
  export.

Implementation:

- `smart_report/exporters/premium/docx.py`
- no legacy DOCX exporter changes;
- adds section divider rules before long-form sections.

Verification:

- `tests/test_premium_document.py` checks the dashboard text;
- premium document/artifact QA tests pass;
- focused suite: `99 passed`;
- frontend production build: passed.

Layout caveat:

- strict artifact QA now renders the smoke DOCX/PPTX in this environment;
- current smoke output renders to 14 DOCX pages and 11 PPTX slides;
- this is still below the paid-product 20+ page target for a client report, so
  real premium packages remain gated by the 20-page check.

### 28. Artifact QA now requires the DOCX decision dashboard

`scripts/premium_artifact_qa.py` now records `has_decision_dashboard` and fails
DOCX structural QA if `Client Decision Dashboard` is missing.

This makes the premium dashboard a protected delivery feature rather than a
best-effort renderer detail.

Verification:

- `tests/test_premium_artifact_qa.py`
- `tests/test_premium_document.py`
- focused suite: `99 passed`
- frontend production build: passed

### 29. Premium status now shows the next research leads

`GET /api/v4/sessions/{id}/premium-refinement-status` now returns a
`next_research_leads` preview. Each item includes:

- lead id;
- kind and priority;
- closure status;
- recommended service and mode;
- candidate sources;
- prompt preview.

The v4 premium status card renders these leads under `Next research leads`.
This makes the long-running premium loop inspectable: the user can see which
branches are still open before pressing `premium-refine`, instead of staring at
a generic "not ready" message.

Implementation:

- `smart_report/api/v4_endpoints.py`
- `frontend/lib/apiV4.ts`
- `frontend/app/v4/chat/Workspace.tsx`
- `frontend/app/workspace.css`
- `tests/test_v4_endpoints.py`

Verification:

- `pytest -q tests\test_v4_endpoints.py -k "premium_refinement_status or premium_refine or artifact_qa_docx_page_count"` -> `6 passed`;
- `cd frontend && npm run build` -> passed;
- expanded premium/v4/evidence suite -> `99 passed`.

### 30. Premium ZIP manifest now carries delivery QA summary

`00_manifest.json` in `premium-client-package` / `premium-package` now includes
the delivery metrics an auditor needs before opening nested JSON files:

- `artifact_qa_status`;
- `docx_pages`;
- `docx_pages_source`;
- `deck_slides`;
- `visual_review_status`;
- `analytic_closure_score`;
- `open_analytic_leads`;
- `unsupported_conclusions`;
- `unresolved_conflicts`;
- `critical_unresolved_conflicts`.

Latest visual-approved golden rebuild confirms the manifest is populated:

- EV: 50 rendered DOCX pages, 11 deck slides, 12 open analytic leads;
- Moscow: 40 rendered DOCX pages, 11 deck slides, 12 open analytic leads,
  1 unsupported conclusion;
- EU DAC: 37 rendered DOCX pages, 11 deck slides, 12 open analytic leads,
  3 unsupported conclusions.

Verification:

- `pytest -q tests\test_v4_endpoints.py -k "full_flow or artifact_qa_docx_page_count or premium_refinement_status"` -> `3 passed`;
- visual-approved golden rebuild -> `73.0/100`;
- expanded premium/v4/evidence suite -> `99 passed`;
- frontend production build -> passed.

### 31. Next Research Brief can be downloaded before final synthesis

Added a standalone next-research-brief download path:

- `GET /api/v4/sessions/{id}/next-research-brief`
- `GET /api/v4/sessions/{id}/export?format=next-research-brief&allow_draft=true`

The standalone endpoint requires `analysis`, but does not require
`final_report`. This is important for long runs: after the analytic-depth layer
has identified open leads, a human analyst or another research agent can
download the executable brief immediately, without waiting for a premium ZIP.

Frontend additions:

- export dropdown now includes `Next Research Brief MD`;
- the premium status artifact header has a `brief` action beside `continue`.

Verification:

- `pytest -q tests\test_v4_endpoints.py -k "next_research_brief or full_flow"` -> passed;
- `cd frontend && npm run build` -> passed.

### 32. DR waiting panel is now an operational research cockpit

The old DR waiting view was technically correct but psychologically weak: it
looked like a static polling panel, so a 10-30 minute research run could feel
stuck even when the backend was alive.

Added an additive v4 chat UI layer for `dr-progress` artifacts:

- research cockpit header with live polling indicator;
- queue metrics: running, completed, exceptions, elapsed;
- health strip: system signal, next check, current bottleneck;
- stage timeline: task accepted, provider polling, evidence capture,
  analytic synthesis;
- live feed based on provider progress messages;
- prompt preview inside analytic-depth lead cards;
- subtle progress scan animation on the existing progress bar.

This does not change DR execution semantics. It only makes long waits legible
and useful for the user while external providers run.

Verification:

- `cd frontend && npm run build` -> passed;
- `pytest -q tests\test_v4_endpoints.py -k "next_research_brief or premium_refinement_status"` -> `2 passed`;
- `git diff --check` -> clean except CRLF warnings.

### 33. Long-run chat now has a Research Command Center

Added a second, broader waiting-state layer in the main chat column. This is
different from the narrow DR artifact panel: it is visible during any pending
pipeline work or active DR tasks, so the user does not have to open the right
artifact panel to understand what is happening.

The command center is domain-neutral and derives its state from existing v4
signals:

- active DR tasks and `drProgress`;
- live `/events` stream;
- `analysis` outputs: source summaries, consensus, conflicts, gaps,
  unverified numbers;
- premium readiness and premium refinement status when available.

It renders:

- readiness label (`collecting evidence`, `analyst-grade draft`,
  `needs refinement`, `premium-grade`);
- active DR count, live event count, open risk count, current cost;
- research map rows for source base, consensus, conflicts, gaps, premium gate;
- current findings stream from provider messages and backend events;
- current bottleneck and provider state;
- `inspect` action to open the DR progress artifact or analysis artifact.

This turns the waiting state into product value: the user sees the analytical
work evolve instead of watching a long technical log.

Verification:

- `cd frontend && npm run build` -> passed;
- `pytest -q tests\test_v4_endpoints.py -k "next_research_brief or premium_refinement_status"` -> `2 passed`;
- `git diff --check` -> clean except CRLF warnings.

### 4. Premium deck design is functional, not yet agency-grade

The deck is separate and editable, but it is still a conservative native PPTX
layout. It is not yet visually comparable to top consulting decks.

Next design upgrade:

- stronger title-slide composition;
- better executive summary slide;
- native charts where data exists;
- visual status badges;
- diagram blocks for issue tree / scenario logic;
- rendered-slide QA.

### 5. The analytical layer now has closure scoring, but needs stricter evidence quality

Needed:

- connect completed async jobs to lead IDs when pending metadata is removed;
- combine closure score with source authority and contradiction checks;
- rerun premium readiness after closure;
- use closure score inside premium readiness, not only as an exposed audit.

## Recommended Next Tasks

1. Add golden-set evaluation command that runs multiple topics and writes a
   quality leaderboard.
2. Improve PPTX visual design after rendered-slide review.
3. Feed `premium-refinement-status` into a persistent visible progress card so
   a 30-60 minute run always has an explainable current state.
4. Add a UI flow for explicit visual approval after opening
   `07_artifact_qa/index.html`.
5. Run the five-task golden set and fix the lowest-scoring dimensions.

## Important Constraints Preserved

- Existing v4 exports remain available.
- Legacy `docx`, `pptx`, `md`, `json`, `onepager`, `data-pack`, `audit-json`
  are not removed.
- Premium pipeline is additive.
- The implementation remains domain-neutral; no Moscow-real-estate-specific
  logic is hard-coded into the premium renderer.
