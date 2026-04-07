# Smart Report V2 Test Strategy

## Goals

- Verify typed contracts and deterministic business logic
- Verify API behavior for the v2 report flow
- Verify generated artifacts, not just code paths
- Verify the frontend shell still supports the main user journey

## Test layers

### Unit tests

- task classification
- semantic clarification
- source scoring
- evidence extraction
- contradiction detection
- recommendation authority gate
- audit rules

### API tests

- create report
- clarify pack
- scope submission
- report retrieval
- SSE progress stream
- evidence and sources endpoints
- artifact download

### Report-result tests

- banned phrase detection
- duplicate section detection
- recommendation evidence linkage
- non-empty source pack
- successful HTML/PDF generation
- audit summary generation

### Golden evals

At least five canonical public-information tasks are run against the deterministic seeded provider to guard against regressions in:

- task typing
- clarification dimensions
- must-cover questions
- evidence coverage
- fail-closed behavior

### Frontend tests

- dashboard smoke
- new report flow
- report viewer tabs
- failed run state

## Validation scripts

- `scripts/run_full_validation.py`
- `scripts/run_golden_evals.py`
- `scripts/audit_report_package.py`

## Acceptance standard

The overnight slice is considered valid only when:

- backend tests pass;
- golden evals pass;
- sample report packages are generated;
- audits for the sample packages are saved;
- the frontend shell loads and exercises the main flow.
