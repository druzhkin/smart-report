# Smart Report

## Current Product Decision

Smart Report must treat the structured report source as the single source of
truth. PDF, DOCX, PPTX/Gamma, HTML, and data packs are generated artifacts, not
editable masters.

The client edits structured fields and blocks: title, subtitle, section text,
bullets, callouts, chart captions, tables, and source notes. After edits, the
system runs enterprise quality gates and regenerates the deliverable package.

## Enterprise Report Contract

- Canonical model: `StructuredReportSource`.
- Default artifacts: DOCX, PDF, PPTX.
- DOCX is mandatory by default because it is the editable client artifact.
- PDF is the publication artifact.
- PPTX/Gamma is the executive presentation artifact.
- Version history is required for each structured source change.
- Roles: `analyst`, `editor`, `client_reviewer`, `quality_reviewer`.
- In scope now: structured editing, versions, strict gates, regeneration plan.
- Explicitly out of scope now: version comparison and approved-section locks.

## Quality Gates

The source cannot regenerate as client-ready if:

- the title is missing;
- the report has too few sections;
- DOCX is absent from default generation;
- the source registry is empty;
- research connector coverage is missing;
- internal pipeline markers leak into client text;
- authored narrative is too thin;
- visual support is too thin;
- version history is missing.

## Research Coverage

Research coverage must be recorded at the source level. Existing repo support
already includes Valyu, Exa, Tavily, Perplexity, uploaded sources, and manual
sources. Valyu has documented strong coverage for arXiv/PubMed-style research,
but this coverage has to be surfaced into the report contract and gates instead
of remaining an internal search detail.

Known gap: there is no direct Notion connector available in this agent session,
so this file is the local project-card source until the Notion card can be
updated through a configured integration.

## Next Implementation Steps

1. Persist `StructuredReportSource` per v4 session.
2. Add API endpoints for retrieving the source, applying edits, and requesting
   regeneration.
3. Wire the current premium DOCX/PDF/PPTX renderers to consume the canonical
   source or a deterministic source-to-document adapter.
4. Add frontend editing UI with field-level validation and quality gate status.
5. Add artifact QA after regeneration and show blockers before download.
