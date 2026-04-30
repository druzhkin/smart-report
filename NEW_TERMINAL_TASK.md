# Task for New Codex Terminal

## Context

Repository: `C:\Users\rodina-adm\Documents\dev\smart-report-mvp-v3`

The user wants Codex to continue working on the Smart Report project with access to local repo context, Notion project notes, and Railway.

## Already Done

- Created `AGENTS.md` contributor guide in the repo root.
- Connected to Notion using the provided Notion token for read-only exploration.
- Found the central Notion page: `Smart Report`
  - Page ID: `34acc3c3-18f2-8198-a045-c88aa01d557b`
  - URL: `https://app.notion.com/p/Smart-Report-34acc3c318f28198a045c88aa01d557b`
- Read recent Notion context. Current project direction:
  - Old 13-month master plan is cancelled.
  - New roadmap is 4 phases / 10 weeks.
  - Critical architecture focus is C2 Query Decomposition and C6 Gap Detection with Iterative Retrieval.
  - Speculative items removed from core path: ACH, GraphRAG core, multi-agent architecture, Bisociator, Best-of-N.
- Stored local secrets in `.env`, which is ignored by Git:
  - `NOTION_API_KEY`
  - `NOTION_TOKEN`
  - `RAILWAY_TOKEN`

Do not commit `.env`.

## Important Notion Findings

Current Smart Report status as of April 28, 2026:

- Working:
  - MVP v4.5 pipeline: generate-prompt -> analyze -> synthesize.
  - Broad pytest coverage.
  - DOCX renderer v2.
  - Cost tracking.
  - Frontend `/v4/chat`.
  - Consistency critic and language lint.
  - Auto-followup flow.
  - Cost accuracy and synth retry improvements.
- Not done / broken:
  - No true iterative research loop yet.
  - Long POST requests hit proxy timeouts.
  - Need background-task pattern: `POST 202 + task_id`, polling status like `/auto-dr`.
  - Synthesizer does not reliably generate tables/charts/callouts.
  - PPTX export is still incomplete/stub-like.
  - Railway env may still lack `OPENAI_API_KEY`.
  - Valyu webhooks are not implemented.

## Suggested First Steps

1. Start Codex with full access if the user wants unrestricted local work:

   ```powershell
   codex --dangerously-bypass-approvals-and-sandbox --enable rmcp_client
   ```

2. Confirm local secrets are visible:

   ```powershell
   Get-Content .env | ForEach-Object {
     if ($_ -match '^\s*#' -or $_ -notmatch '=') { $_ } else { ($_.Split('=',2)[0] + '=***') }
   }
   ```

3. Re-read central Notion page and latest Smart Report child pages if needed.

4. Inspect the backend API around long-running endpoints:

   - `smart_report/api/v4_endpoints.py`
   - `smart_report/api/jobs.py`
   - `smart_report/api/reports.py`
   - frontend callers under `frontend/app/v4/` and `frontend/lib/`

5. Likely implementation priority:

   Convert long `/analyze` and `/synthesize` flows to a background-task pattern so Cloudflare/Railway proxy timeouts do not break user-facing requests.

## Working Rules

- Do not write secrets to Notion.
- Do not commit `.env`.
- Prefer repo patterns over new abstractions.
- Be critical: if the user's requested plan is risky or confused, say so directly and propose the better path.
