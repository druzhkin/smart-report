# Overnight Status

Generated on April 6, 2026 (Europe/Moscow).

## Outcome

Working v2 vertical slice is in place and wired through the main UI path:

`request -> clarify -> scope -> search -> evidence -> report -> audit`

The API entrypoint now serves the new v2 runtime, the frontend shell is connected to the new flow, audit harness scripts exist, golden evals run, and sample report packages plus audit outputs were generated.

## What Landed

1. New backend core under `backend/v2/` with typed request/task/evidence/audit contracts.
2. New report API flow in `backend/api/routes/reports.py`.
3. Evidence-first report generation with persisted artifacts:
   `request_spec.json`, `task_spec.json`, `research_plan.json`, `sources.json`, `source_snapshots.json`, `evidence_ledger.json`, `claim_table.json`, `analysis_brief.json`, `coverage_report.json`, `audit_summary.json`, `report.md`, `report.html`, `report.docx`, `report.pdf`.
4. Frontend v2 shell:
   task intake, semantic clarification, live progress, evidence/report workspace.
5. Audit harness scripts:
   `scripts/audit_report_package.py`
   `scripts/run_golden_evals.py`
   `scripts/run_full_validation.py`
6. Golden set:
   `reports/evals/golden_cases.json`
7. Sample reports and audits:
   `reports/samples/oss-coding-models`
   `reports/samples/llm-observability`
   `reports/samples/enterprise-rag`
   `reports/samples/browser-agents`
   `reports/samples/document-ai-workflows`
   `reports/audits/*.json`

## Validation

Latest successful runs:

1. `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_v2_intake.py backend/tests/test_v2_pipeline.py backend/tests/test_v2_api.py -q`
   Result: `7 passed`
2. `npm.cmd run build` in `frontend`
   Result: success
3. `npx.cmd playwright test tests/e2e/report-flow.spec.ts` in `frontend`
   Result: `2 passed`
4. `backend/.venv/Scripts/python.exe scripts/run_golden_evals.py`
   Result: `5/5` golden cases passed
5. `backend/.venv/Scripts/python.exe scripts/run_full_validation.py`
   Result: passed

Validation artifacts:

1. `reports/evals/latest.json`
2. `reports/evals/full_validation_latest.json`

## Important Notes

1. Secrets were preserved. `.env` was not rewritten.
2. I did not mass-delete the old backend files because the tree is already dirty and blunt deletion would risk removing user work. Instead, runtime entrypoints were switched to v2 and documented in `docs/rebuild_decisions.md`.
3. Push subscription wiring was intentionally disabled in the frontend shell because the old endpoint no longer matches the v2 API. Leaving the broken import in place would have kept the build red.
4. WeasyPrint native libraries are missing on this machine. To avoid silently dropping PDF output, v2 now falls back to a simple text-based PDF renderer. That means `report.pdf` exists, but its fidelity is lower than the HTML/DOCX output.

## Remaining Risks

1. Non-reference live-search runs still rely on a thin DuckDuckGo path. The deterministic seeded path is solid; the open-web path is still much less battle-tested.
2. The PDF fallback is functional, not polished. If presentation-grade PDF matters, install WeasyPrint native dependencies or replace the renderer.
3. Legacy modules are still present in the repo and should be cleaned up deliberately later, not by accidental blanket deletion.
