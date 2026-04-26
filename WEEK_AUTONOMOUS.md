# 2-week autonomous run — work log + roadmap

**Started:** 2026-04-26 (user away 2 weeks, Notion MCP disconnected — log here)
**Mandate:** довести продукт до уровня топ-сервиса; стабильность, качество, эффективность, стоимость
**Bag:** Railway token, OpenRouter $58, Valyu ~$5.99, Tavily $1, Exa $2.5, OPENROUTER session cap $11/day operationally — all unpaid

## Critical state at session start (post 2c4f175 + 96b9618)

**Working in prod (verified e2e, $0.44/cycle, ~12min wall):**
- Auth (signup/login/me/logout)
- Per-user session isolation (user_email column, _get_owned, 403 on mismatch)
- Cost cap $1/user/30d + signup rate-limit 5/IP/h (51a5d52)
- /v4/chat → /api/v4/sessions → upload → analyze → synth → DOCX
- PostgreSQL persistence (sessions survive restart)
- Catch-all proxy for multipart + 10min Sonnet calls
- Frontend ↔ backend auth bridge (real cookies, no fake login)
- Phase 1-3 substance: inline grade tags, source-quality classifier, Valyu adapter

**Open critical gaps (from 2026-04-26 audit):**

1. **No real DR auto-launch** — user copies prompt manually, runs in OpenAI DR / Perplexity / etc, pastes back. Current task: integrated launcher with Valyu/Tavily/Exa.
2. **Workspace.tsx ↔ backend in browser** — verified via direct API curl, but UI flow may have edge cases. Need user manual test (in flight).
3. **Cancel mechanism** — synth runs 10min, user closes tab, backend keeps spending. No `/api/v4/sessions/{id}/cancel`.
4. **Real progress UI** — synth shows nothing for 10min. Events endpoint exists, frontend doesn't poll.
5. **Healthcheck doesn't probe LLM/DB connectivity** — Railway thinks "healthy" when product is broken.
6. **Legacy public sessions** — pre-isolation rows have user_email=NULL, readable by anyone. Need cleanup migration.
7. **No tests for real /sessions flow** — 621 unit tests don't cover end-to-end through TestClient.
8. **No DELETE /api/v4/sessions/{id}** — user can't clean up.
9. **Email verification + password reset** — none. For demo OK, for real users blocker.
10. **/api/lead, /app/dashboard.html, /api/v4/reports** — dead code from earlier experiments.

## 2-week prioritised plan

**Week 1: integrated DR + critical UX/safety**

Day 1 (today):
- [DONE] Tavily client + adapter — 9 mock tests, basic/advanced depth selection by domain hint
- [DONE] Exa client + adapter — 8 mock tests, semantic search via SDK `auto` type
- [DONE] Auto-DR backend module + endpoint `POST /api/v4/sessions/{id}/auto-dr` — dispatches to valyu/tavily/exa/perplexity, prepends result as UploadedMarkdown, charges user cost cap. 4 endpoint tests green.
- [DONE] Service picker UI: `frontend/app/v4/chat/DrPicker.tsx` (7 services: 4 integrated + 3 copy-launch with prices + when-to-use), wired into Workspace.tsx replacing the lone "Скопировать промт →" CTA.
- [PENDING] Real prod test of one auto-DR cycle (cheapest = Tavily basic ~$0.005), push, browser verify

Day 2-3:
- Cancel mechanism + DELETE session
- Frontend events polling for live progress

Day 4-5:
- Legacy session cleanup migration
- Integration test for real /sessions cycle (mocked LLMs)
- Healthcheck improvement (LLM ping + DB connectivity)

**Week 2: top-tier features**

Day 6-7:
- Saved sessions UI (/api/v4/sessions list endpoint already exists, wire frontend)
- Project organisation (group sessions by topic)

Day 8-9:
- Quality grade (post-run signal: STRONG distribution / source diversity / coverage)
- Per-claim explanation panel (why STRONG, why WEAK)

Day 10:
- Templates (preset prompts for common use cases — RU RE, financial, EU regulatory, etc)

Day 11-12:
- Export: Notion sync, Google Docs, Markdown bundle

Day 13-14:
- Polish, dead code cleanup, final HANDOFF for user return

## Cost budget (2 weeks)

| Item | Estimate |
|---|---|
| Live smoke tests (per new client/endpoint) | ~$0.50 |
| End-to-end prod verification cycles (~3-5) | ~$2.00 |
| Sonnet auto-DR test calls | ~$5.00 |
| Valyu/Tavily/Exa real calls | ~$2.00 |
| Opus gate-keeper if needed | ~$1.00 |
| **Total ceiling** | **~$10-15** |

Hard guardrails: stop deploying to prod if last 3 deploys broken; halt all paid LLM if cumulative > $20.

## Daily log (append below)

### 2026-04-26 (Day 1)

**Backend (DR launcher):**
- `smart_report/sources/tavily.py` + `tavily_adapter.py` — async Tavily SDK wrapper, retry shim (3 attempts, 1/2/4s backoff, 5xx + transport-only), `is_primary_capable=False`, basic→advanced depth promotion for regulatory_eu/regulatory_us/technical_research. Cost: $0.005 basic / $0.020 advanced.
- `smart_report/sources/exa.py` + `exa_adapter.py` — async Exa SDK wrapper, semantic search via `type='auto'`, highlights+text snippet preference. Cost: ~$0.012 midpoint.
- `smart_report/sources/auto_dr.py` — `run_auto_dr(service, question)` dispatches to right backend. For `perplexity`, calls `perplexity/sonar-pro` via OpenRouter (LLM-style DR with citations). Returns `AutoDRResult` with `UploadedMarkdown` ready to feed `session.source_reports`.
- `POST /api/v4/sessions/{id}/auto-dr` — owner-gated, cost-capped, persists result to session, emits `status` events. Returns service/cost/source_count/notes.
- 21 new tests: 9 Tavily adapter, 8 Exa adapter, 4 endpoint (mock backend, 502 surface, prompt fallback). All green.
- requirements.txt: `tavily-python>=0.5`, `exa-py>=1.0` (verified pip install).

**Frontend (chat picker):**
- `frontend/app/v4/chat/DrPicker.tsx` — 7-card grid with prices + when-to-use guidance:
  - Integrated: **Valyu** ($0.10, "🏆 для отчётности" — SEC/FRED/arxiv/pubmed) · **Tavily** ($0.005-0.020, "💰 самый дешёвый") · **Exa** ($0.012, semantic) · **Perplexity Sonar Pro** ($0.50-2, LLM с цитатами)
  - Copy-launch: **ChatGPT DR**, **Claude Research**, **Gemini DR** — copies prompt + opens new tab; user pays subscription, not us
  - "детали" toggle per card with longer description
  - "Уже запустил — загружу .md сам" skip footer
- Wired into `Workspace.tsx`: replaced lone copy-prompt CTA with `kind: "dr-picker"` message; `runIntegratedDr` calls `runAutoDR` API + auto-progresses to upload phase; `launchExternalDr` copies + opens.
- `lib/apiV4.ts`: new `runAutoDR(id, service, {prompt, domain_hint})` helper.
- `app/workspace.css`: scoped `.dr-picker / .dr-card` styles (warm-paper aesthetic, badges, busy state).

**Tests:** 68 backend tests still green (auth + sources + v4 endpoints).

**Git:** committing now, will push for Railway deploy.

**Cost spent:** $0 (mocks only this far). Live verification budget reserved for after deploy.

**Post-deploy live smoke (1eec948 deployed to prod):**
- `/health` 200, `/api/v4/sessions/{id}/auto-dr` route registered
- Real flow: signup new user → POST /sessions ("Что нового в OpenAI GPT-5 за последний месяц?") → POST /auto-dr {service:"tavily", prompt:"OpenAI GPT-5 release news 2026"}
- Result: HTTP 200 in 1.7s, 10 Tavily sources, **$0.005**, 553-word markdown persisted as `auto_dr_tavily.md`, session.status flipped to `reports_uploaded`, cost cap charged 0.377 rub
- Conclusion: integrated DR launcher works end-to-end in prod ✓
- One note: `print()` showed `—` (em-dash) escaped in console, but content is correct UTF-8 — purely a Windows-cp1251 console encoding quirk, not a server bug.

**Day 1 cost actual: $0.005 (one Tavily basic call, well under budget).**

### 2026-04-26 (Day 2 — same evening)

**Backend:**
- `V4Status` literal: added `"cancelled"`
- `V4SessionStore` + `PgV4SessionStore`: added `delete(session_id)` (idempotent, removes JSONB row)
- `_owned_with_cap`: now 409s if session is cancelled (no further LLM spending)
- `POST /api/v4/sessions/{id}/cancel` — flips status, emits status event, idempotent (re-cancel is no-op)
- `DELETE /api/v4/sessions/{id}` — owner-gated, removes from store + clears events + wakes long-pollers, returns 204; missing session → 404
- 5 new tests: cancel-marks+blocks, cancel-idempotent, delete-204, delete-404-on-missing, delete-403-on-not-owner. Full suite 73/73 green.

**Frontend:**
- `apiV4.ts`: `cancelSession(id)`, `deleteSession(id)` helpers
- `Workspace.tsx`:
  - Live events polling: `useEffect` long-polls `/events` while `pending && sessionId`, surfaces each backend event as a system message ("· …"). Stops on done/error/unmount.
  - `onCancel`: calls cancelSession, removes any active "thinking" placeholder, posts a "сессия отменена" notice, clears pending.
  - Composer button: when pending+sessionId, the "Отправить" button morphs into "Отменить" (warns the user that already-spent tokens are still billed).

**Status:** ready to push, will roll into prod alongside Day 1 work. Live verification of cancel deferred to actual long-running synth call (cheaper than Sonnet for verification — will piggy-back on the next end-to-end test).

### 2026-04-26 (Day 4-5 work — pulled forward)

**Deeper healthcheck:**
- `GET /health/deep` — probes DB connectivity (1 SELECT) + LLM gateway reachability (1 GET /models, free). Returns `{status: "ok"|"degraded", components: {database, llm_gateway}}`. Does NOT replace `/health` — Railway healthcheck still hits the cheap `/health`. Operators / external uptime monitors hit `/health/deep`.
- Verified locally: 200 with both components ok. Fast (sub-second).

**Legacy session cleanup:**
- `scripts/cleanup_legacy_sessions.py` — finds rows in `v4_sessions` where `payload->>'user_email' IS NULL` (pre-isolation bypass surface), prints them, optionally deletes with `--apply`. Default is dry-run.
- Will run against Railway PG once token + env access confirmed.

**Day 2 deploy status:** still building when we wrote this. Day 1 routes (auto-dr) confirmed live; Day 2 routes (cancel/DELETE) not yet — Railway Docker build pending.

### 2026-04-26 (Day 6-7 — pulled forward, still same evening)

**Saved sessions sidebar (frontend):**
- `lib/apiV4.ts`: `listSessions()` + `SessionListItem` type
- `Workspace.tsx`:
  - state `savedSessions: SessionListItem[]`, fetched on mount + on `sessionId|cost` change
  - `loadSavedSession(sid)` — hydrates promptData/analysisData/finalData from `getSession`, sets phase based on what's done, replaces chat with a single "Сессия восстановлена" line + reopens the most useful artifact (final → critique → prompt → none)
  - `deleteSavedSession(sid)` — confirm dialog → DELETE → optimistic list filter → if deleting current, clear local state and back to start
  - Sidebar render: rebuilt from "current-only stub" → real list with status badge (✓ done · · analyzed · ○ in progress · ✕ cancelled), date, cost, hover-revealed delete button, search-by-question filter
- `workspace.css`: split `.sb-session` into div container + `.sb-session-main` (click-to-load) + `.sb-session-del` (hover ✕). Added `.sb-session-meta` for date+cost.

**Trade-off note:** chat history is not persisted server-side, so loading a saved session shows a one-line "session restored" message instead of replaying every CTA/upload. The artifacts (prompt, analysis, final report) ARE restored from the JSONB payload — that's where the actual product value lives. Session-restore-with-full-chat-replay would require new backend storage; deferred.

### 2026-04-26 (Day 6-7 hotfix — caught a deploy regression)

**Discovery via Railway CLI:** the last 3 deploys (Day 2 / 4-5 / 6-7) all FAILED at the `npm run build` step. Auto-deploy was wired correctly all along — TypeScript strict mode caught a TDZ violation in my Day 2 `onCancel` callback that I missed locally because frontend/node_modules wasn't installed.

Error: `Block-scoped variable 'push' used before its declaration` (Workspace.tsx:367 — onCancel's deps array referenced `push` which is declared at line 370).

**Fix (`c8cf787`):** rewrote `onCancel` to call `setMessages` directly with an inline message shape, dropping the dep on `push`. All other new callbacks (`runIntegratedDr`, `launchExternalDr`, `loadSavedSession`, `deleteSavedSession`) verified to be either declared after `push` or to not reference it.

**Lesson learned:** install frontend deps locally before next push to catch this without a Railway round-trip. Or set up a CI step.

**Discovered via Railway:** project token can read deployment list + build logs (`railway deployment list --service smart-report` + `railway logs --service smart-report --build <ID>`) — invaluable for autonomous debugging. Saved to memory.

### 2026-04-26 (Day 8-9 — quality grade)

**Backend:**
- `smart_report/quality_grade.py` — `compute_quality_grade(session)` → `QualityGrade` dataclass with composite score in [0, 1] (50% strong-share + 30% domain diversity + 20% consensus coverage), bands A ≥ 0.75, B ≥ 0.55, C otherwise. Tolerates missing analysis/final → returns "N/A".
- `GET /api/v4/sessions/{id}/quality` — owner-gated, returns the dict including raw counts (STRONG/MODERATE/WEAK, unique domains, consensus/conflict/gap/unverified) so the UI doesn't re-derive client-side.
- 7 new tests covering all bands + edge cases (no final, no sources, www-prefix dedupe, www vs sec.gov collapsing). Suite 80/80 green.

**Frontend:**
- `lib/apiV4.ts`: `getQualityGrade(id)` + `QualityGrade` type
- `Workspace.tsx`: fetches grade when `finalData && sessionId`; renders a colored badge (A=green / B=accent gold / C=red) above the report artifact with score, one-line summary, and metric line ("STRONG 3/8 · доменов 7 · согл. 5 · конф. 1 · проб. 2")
- `workspace.css`: `.quality-grade` block with band-colored left border

**Push notes:** also queued a `next.config.mjs` fix that exposes `/health/deep` (Day 4-5 deep healthcheck couldn't reach the backend through the Next.js rewrite layer because the existing rule only matched exact `/health`).

**Live verification (post c8cf787 deploy):** cancel + DELETE + listSessions all work in prod. Day 1 (auto-dr) still solid. Pending verifications after next deploy: `/health/deep`, quality grade widget, full chat flow with picker.

### 2026-04-26 (Day 10 — preset templates)

Frontend-only. 5 template chips above the start-phase composer (RU developers, Tesla 10-K, EU AI Act, MoE scaling laws, OpenAI news). Click loads template into textarea; user can edit before sending. Auto-resizes textarea on insert. Hidden once a session starts.

**Verification of latest deploy (88b8c86c):**
- `/health/deep` → 200 with both DB + LLM components ok
- `/api/v4/sessions/{notfound}/quality` → 404 "session not found" (route registered, just no session)
- `/health` (cheap) still 200 — Railway healthcheck path unaffected
- Day 1, 2, 4-5, 6-7, 8-9 all live in prod simultaneously

### 2026-04-26 (Day 11-12 — polish)

Frontend-only:
- Report-artifact head: new "скопировать md" button — fetches `/export?format=md` and writes to clipboard. One-click full report copy for Notion/Slack paste-in.
- Cost-cap pre-warning: when `cost ≥ 60₽` (80% of $1/30d cap at 75₽/$ rate), shows a one-per-day toast warning. Suppresses repeats via `localStorage[sr-cost-warn-day]` keyed on today's date.

**Decisions deferred** (non-blocking, kept out of autonomous scope):
- Notion / Google Docs / Drive sync — needs per-user OAuth, too heavy without user input.
- Email verification + password reset — needs an email provider configured.
- Per-claim explanation drill-down — needs Source.quality_reason field added to the source-quality classifier output (not just tier).
- Dead-code removal of `/api/v4/reports` + `/app/dashboard.html` — still wired from `landing_a_sales.jsx → goDashboard()`. Half-migrated landing → don't touch unattended.

### 2026-04-27 (User-driven architecture switch — Valyu Research API)

User noticed two things in prod test:
1. «отчёта от валю не видно в окне» — clicking auto_dr_*.md didn't show content
2. «тавили вообще не сработал» — Tavily 502 «Query is too long. Max 400»
3. «а почему стоимость у валю 10 центов, если стандрат 25?» — pointed me to Valyu's published Research-mode pricing
4. «валю не может сразу отдавать данные, нужно хотя бы пять минут, а на фронте появилось сразу» — ah! I was using the wrong Valyu product entirely.

**Root cause:** I had wired `valyu.search()` (instant per-result web/data search, $0.001-0.005 per result) thinking it was Valyu's deep research. The actual product the user expected is `valyu.deepresearch.*` — proper async deep research with fixed-cost modes:

| Mode | Price | ETA | Best for |
|---|---|---|---|
| Fast | $0.10 | ~5 min | quick queries |
| Standard | $0.50 | 10-20 min | balanced (default) |
| Heavy | $2.50 | ~90 min | fact verification |
| Max | $15.00 | ~3 hours | exhaustive |

**Architectural switch (this commit):**

Backend:
- `smart_report/sources/valyu_deepresearch.py` — `ValyuResearchClient` wrapping `Valyu().deepresearch.create/status/get_assets/cancel`. Submits with mode, polls for state, fetches markdown asset on completion.
- `smart_report/sources/auto_dr.py` — added `submit_async_research`, `try_collect_async_research`, `cancel_async_research`. Sync path (Tavily/Exa/Perplexity, plus Valyu legacy search if no mode) unchanged.
- `V4Session.pending_dr_jobs: list[dict]` — tracks in-flight async jobs (task_id, service, mode, cost).
- `POST /api/v4/sessions/{id}/auto-dr` — when payload includes `mode`, submits async job, charges cost upfront, returns `AutoDRAsyncOut` with task_id + ETA.
- `GET /api/v4/sessions/{id}/auto-dr-status?task_id=X` — polls. On completion, fetches markdown asset, prepends to source_reports (idempotent — won't duplicate on subsequent polls), removes from pending.
- 4 new tests covering async submit/poll/complete/404. Suite 68/68 green.

Frontend:
- `lib/apiV4.ts` — `runAutoDR` returns union (sync `AutoDROut` | async `AutoDRAsyncOut`), `pollAutoDRStatus` helper, `isAsyncOut` type guard.
- `DrPicker.tsx` — Valyu card now exposes 4-mode submenu (Fast/Standard/Heavy/Max) with prices + ETAs; default Standard. Big price label updates per chosen mode.
- `Workspace.tsx` — `runIntegratedDr` accepts `{mode}`, branches on async; new `activeResearchTask` state + polling effect (15s for first 2 min, then 30s; up to 180 min for max mode); on completion auto-pushes success message + ref to session.
- New CSS for `.valyu-mode-chip` row.

Bonus fixes (same commit context, since user reported them together):
- Tavily client: defensive 380-char query truncation on word boundary (closes 502 «query too long»).
- Auto-DR ref-click now opens markdown content in artifact panel (was: stale "select files" placeholder).
- Picker copy: honest about which Valyu API tier we're using.

### 2026-04-26 (User-driven UX hotfix — chat message clarity)

User pinged mid-session: «он разместил запрос в валю или нет? написано так что нихера не понятно». Screenshot showed the auto-DR success message reading like a server log, not a confirmation. The integration was working — Valyu DID run the research, returned 10 sources, $0.0150, file persisted — but the wording made it look ambiguous.

**Fix (in progress, included in next push):**
- Replace `valyu: 10 источник(ов), $0.0150. Файл «auto_dr_valyu.md» добавлен в источники сессии.` with `✓ Valyu провёл исследование и вернул 10 источник(ов).\n\nСтоимость: $0.0150 (≈ ₽ 1.13). Результат сохранён как «auto_dr_valyu.md» — это готовый отчёт, его можно сразу анализировать.`
- Use display names (`Valyu`/`Tavily`/`Exa`/`Perplexity Sonar Pro`) instead of internal slugs
- Show ₽ alongside $ so user reads in their own currency
- CTA «Перейти к анализу →» → «Запустить анализ этого отчёта →» (action-oriented)
- Thinking traces also rewritten to plain language
- Error path: distinguishes upstream failure from our own; suggests next step

Saved feedback memory: `feedback_chat_messaging_clarity.md` — pattern for any future chat system message (✓/✗ + verb + human units + next step).
