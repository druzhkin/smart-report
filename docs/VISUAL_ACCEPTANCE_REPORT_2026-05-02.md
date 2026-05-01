# Visual Acceptance Report - 2026-05-02

## Scope

Reviewed real/local PDF artifacts for the premium report track:

- `output/doc/premium_rebuild_20260501_102308/publication_grade_report.pdf`
- `tmp/storyboard_quality_acceptance/storyboard_quality_report.pdf`

Rendered pages with Poppler `pdftoppm` and inspected representative pages.

## Result

Status: not accepted for client/public delivery.

The current pipeline is materially better than the earlier table-only and
text-only drafts, but visual acceptance is not yet at consulting-publication
standard. The gate correctly rejects the older real PDF. The newer storyboard
sample passes structural artifact QA, but manual review still finds content and
layout maturity gaps that should block public BCG/McKinsey-grade delivery.

## Artifact Findings

### `publication_grade_report.pdf`

Automated artifact QA: failed.

Observed metrics:

- pages: 28
- landscape pages: none
- thin pages after cover: none
- max dense text streak after cover: 27
- missing cover brand marker
- missing publication marker
- missing exhibit pages marker
- source notes present

Manual visual review:

- Page 8 is much improved versus the user's screenshot: it now has a right rail
  with chapter sense, KPI cards, and a verification callout.
- Page 10 has a chart and table, and is visually closer to a report page.
- Page 12 still reads as a dense narrative page with KPI rail, not enough exhibit
  pacing for a long-form publication.
- The file as a whole remains too text-streaked. It should not be client-delivered.

Decision: rejected.

### `storyboard_quality_report.pdf`

Automated artifact QA: passed.

Observed metrics:

- pages: 20
- landscape pages: none
- thin pages after cover: none
- max dense text streak after cover: 0
- cover brand marker present
- publication marker present
- exhibit pages present
- source notes present

Manual visual review:

- Cover has a strong first-viewport brand signal and portrait format.
- Exhibit pages have clear headers, source notes, footer, and visual hierarchy.
- Page 8 has a readable scenario matrix and interpretation/callout rhythm.
- Page 10 is too sparse: the central framed text block has low analytical value
  and too much empty space.
- Some content is still generic or demo-like, including `example.com` sources and
  English placeholder-style prose in a Russian report.

Decision: structurally improved, but not accepted as final public delivery.

## Acceptance Bar

A report can be accepted only when all are true:

- PDF artifact QA passes.
- Rendered pages show portrait-only layout, no clipped text, no overlapping
  components, no blank or underwritten pages, and no long streaks of dense text.
- Every narrative chapter is paired with at least one meaningful visual, table,
  KPI strip, or decision callout that supports the text.
- Visuals use real source-backed data, not placeholder or generic values.
- Russian reports do not contain English placeholder prose unless it is a source
  name, product name, or direct source artifact.
- Pages balance text and exhibits: no page should feel like a slide with one
  sentence, and no sequence should feel like a manuscript dump.
- Source notes are human-readable and traceable.

## Follow-Up Requirements

- Raise visual QA beyond structural checks: detect sparse framed pages and
  placeholder/example sources.
- Add content-depth checks for exhibit pages: an exhibit page needs analytical
  interpretation, not only a chart/table shell.
- Add language consistency checks for Russian reports.
- Generate acceptance fixtures from a real report data pack, not only synthetic
  smoke data.
- Keep rejecting `publication_grade_report.pdf` until dense-text streak and
  exhibit-marker failures are gone.
