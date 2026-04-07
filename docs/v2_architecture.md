# Smart Report V2 Architecture

## Core principle

V2 is an evidence-first analytical pipeline.
The system produces typed artifacts first and prose second.

## Runtime shape

1. `RequestSpec`
2. `ClarificationPack`
3. `TaskSpec`
4. `ResearchPlan`
5. `SourceLedger`
6. `SourceSnapshots`
7. `EvidenceLedger`
8. `ClaimTable`
9. `AnalysisBrief`
10. `CoverageReport`
11. `ReportPackage`
12. `AuditSummary`

## Main backend modules

- `backend/v2/models.py`
  Typed contracts for every artifact and API-facing object.
- `backend/v2/repository.py`
  File-backed run repository and event log.
- `backend/v2/reference_data.py`
  Curated deterministic public-source snapshots for golden cases and sample reports.
- `backend/v2/search.py`
  Pluggable search and fetch adapters.
- `backend/v2/pipeline.py`
  Bounded orchestration from scope to released report package.
- `backend/v2/audit.py`
  Report-package quality gate and fail-closed checks.

## Search strategy

- Default path: cheap recall URL search
- Deterministic source scoring and shortlist selection
- Direct fetch + extraction
- No deep-research loop by default
- Optional LLM synthesis only after evidence is structured

## Persistence

- Run summaries: `data/runs/<run_id>/run.json`
- Event log: `data/runs/<run_id>/events.jsonl`
- Artifact files: `data/runs/<run_id>/artifacts/*.json`
- Generated report package: `reports/generated/<run_id>/`
- Audits: `reports/audits/`

## Recommendation policy

Recommendations are allowed only when:

- coverage across required questions is adequate;
- source mix includes strong source classes;
- contradiction pressure is below threshold;
- claims are sufficiently linked to evidence.

Otherwise the system downgrades to bounded analysis and explicitly states uncertainty.

## Frontend slice

The shell remains Next.js-based, but the flow is re-framed as:

1. `Task`
2. `Scope`
3. `Questions`
4. `Evidence`
5. `Report`

The report view is re-framed as:

1. `Brief`
2. `Report`
3. `Evidence`
4. `Sources`
5. `Gaps & Risks`
6. `Data`
