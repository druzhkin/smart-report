# Deep Analytic Layer Blueprint

## Goal

Smart Report should not compete with Perplexity, OpenAI Deep Research, Claude,
or Valyu by producing another large summary. The defensible product edge is the
analytic layer that sits above them:

- decompose the client question into an issue tree;
- generate and test competing hypotheses;
- follow surprising numbers, terms, and contradictions sideways;
- deliberately search for disconfirming evidence;
- run targeted follow-up research where the first round is weak;
- convert the final synthesis into a report, deck, evidence appendix, and QA
  record.

This is the difference between "research aggregation" and "analytical work".

## Method Stack

The pipeline should combine two proven traditions.

### Intelligence tradecraft

Useful methods:

- Analysis of Competing Hypotheses: maintain multiple plausible explanations
  and test evidence against each instead of defending the first answer.
- Key assumptions check: make hidden assumptions explicit and test whether the
  answer collapses if one fails.
- Disconfirming evidence search: ask what would make the current answer wrong.
- Indicators and signposts: define what future evidence would switch the
  scenario or recommendation.

Reference anchors:

- CIA, Richards Heuer, *Psychology of Intelligence Analysis*:
  https://www.cia.gov/resources/csi/static/Pyschology-of-Intelligence-Analysis.pdf
- GovInfo mirror:
  https://www.govinfo.gov/content/pkg/GOVPUB-PREX3-PURL-LPS20028/pdf/GOVPUB-PREX3-PURL-LPS20028.pdf

### Consulting problem solving

Useful methods:

- issue trees / logic trees;
- MECE decomposition where it actually helps;
- hypothesis-driven analysis;
- benchmark and peer-set comparison;
- pyramid-style communication only after the underlying evidence is tested.

Reference anchors:

- Issue tree overview:
  https://en.wikipedia.org/wiki/Issue_tree
- MECE principle overview:
  https://en.wikipedia.org/wiki/MECE_principle

## Product Principle

Do not ask the LLM to "think like McKinsey" or "think like the CIA". That
creates style mimicry. Encode the methods as data structures and quality gates.

The new layer should produce inspectable artifacts:

```text
FinalReport + AnalysisOutput
  -> AnalyticDepthPlan
     - inquiry tree
     - competing hypotheses
     - evidence probes
     - research leads
     - benchmark questions
     - monitoring indicators
  -> targeted follow-up jobs
  -> PremiumReportDocument
  -> report + deck + evidence pack + QA
```

## Current Implementation

Added:

- `smart_report/analytic_depth.py`
- `tests/test_analytic_depth.py`

The module builds:

- `InquiryNode`: issue-tree nodes with methods and expected outputs.
- `CompetingHypothesis`: base and alternative explanations.
- `EvidenceProbe`: questions designed to verify or disconfirm claims.
- `ResearchLead`: executable research branches for follow-up.
- `AnalyticDepthPlan`: the full non-linear investigation plan.

It is additive. It does not mutate `FinalReport`, does not alter legacy exports,
and does not call external services directly.

## Routing Logic

Valyu is high-value where its proprietary datasets are structurally strong:

- US financials: SEC, FRED, BLS, company filings;
- biomedical / clinical: PubMed, clinical trials, FDA-related sources;
- scientific: arXiv and research corpora.

Valyu should not be forced as primary for Russian real estate, Russian market
research, or general Russian-language sources. For those, Perplexity/OpenAI DR
and targeted site search are usually better.

The analytic layer should recommend services per lead, not globally for the
whole report.

## Deep Follow-Up Pattern

A weak follow-up prompt says:

```text
Add more information about the market.
```

A strong follow-up lead says:

```text
Resolve this conflict with primary or highest-quality sources:
Price growth range. Source A says +3%; Source B says +12%.
Find which scope, date, definition, or source bias explains the divergence.
Return exact values, dates, source URLs, and the corrected interpretation.
```

The second form is executable. It can be sent to Valyu/OpenAI/Perplexity, and
the result can be audited.

## Quality Bar For The Analytical Layer

A report is not "deep" unless it contains:

- at least one issue-tree decomposition;
- explicit competing hypotheses or scenario alternatives;
- source triangulation for key claims;
- an evidence table, not just prose;
- a conflict resolution table where sources disagree;
- benchmark context for important numbers;
- disconfirming evidence search;
- a risk / indicator register showing what would change the conclusion;
- a documented list of unresolved limitations.

The presentation can be beautiful only after these exist. Design cannot rescue
a shallow analytical core.

## Next Implementation Steps

1. Connect `AnalyticDepthPlan` to premium readiness:
   - no premium export if there are no hypotheses, probes, or research leads.

2. Add a follow-up planner endpoint:
   - returns research leads as separate executable branches;
   - lets the user choose Valyu/OpenAI/Perplexity per branch;
   - keeps the current single follow-up prompt as legacy/simple mode.

3. Add result ingestion per lead:
   - each follow-up result should attach to a specific lead id;
   - the final synthesis can say which branch changed the answer.

4. Add analytics UI:
   - show the inquiry tree;
   - show unresolved hypotheses;
   - show "what would change our mind";
   - show recommended research branches.

5. Integrate with premium report assembly:
   - issue tree -> methodology section;
   - hypotheses -> scenario / alternatives section;
   - evidence probes -> appendix;
   - monitoring indicators -> risk dashboard.

## Non-Negotiable Constraint

The old pipeline remains intact. This layer enriches and audits the output; it
does not replace the existing v4 session, analyzer, synthesizer, or export
contracts.
