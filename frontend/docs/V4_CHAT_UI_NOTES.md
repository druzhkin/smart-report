# V4 Chat UI — design notes

Replaces the 6-screen wizard (`/v4/new → /v4/session/[id]/prompt → upload →
analysis → dobor → report`) with a single-route **full chat** experience
(`/v4/chat` + `/v4/chat/[id]`). State-machine and backend APIs unchanged; the
chat renders whatever `getSession()` returns and drives mutations through
the same `lib/apiV4.ts` functions.

## Design direction

**Direction 1 — Warm Paper Mono.** Calm, spacious, digital-premium.
Reference: Valyu.network, Claude.ai, Linear, Vercel dashboard. No serif,
no amber accent, no editorial ornaments — all of those were rejected by
the user ("too newspaper, not digital").

### Tokens (scoped under `.v4-chat`)

```
--vc-bg        : #FAFAF9   warm paper
--vc-surface   : #FFFFFF   card/message background
--vc-surface-2 : #F5F4F2   code, nested chips
--vc-text      : #1A1A1A   near-black ink
--vc-muted     : #6B6B6B   meta copy
--vc-subtle    : #9A9A97   hint/placeholder
--vc-border    : rgba(0,0,0,0.08)
--vc-border-s  : rgba(0,0,0,0.12)
--vc-accent    : #2E2E2E   near-black buttons (no color accent)
--vc-user      : #F0EFEC   user bubble background
```

No color accent — buttons are near-black on paper. Only single restrained
danger red for error state. Stub-mode banner is muted mono.

### Typography

- **Body:** Inter (loaded via `<link>` in `app/layout.tsx`, same as the rest
  of the app). Chosen over Geist to avoid adding a dep for one route.
- **Mono:** JetBrains Mono (already loaded).
- **No serif** anywhere in v4-chat — Spectral / Newsreader are stripped from
  this scope. They remain in place for `.v4` (wizard) and for v2/v3/report
  routes; only v4-chat drops them.
- Sizes:  15px body / 13px meta / 17px subhead / 22px section heading /
  32px page title (capped). Nothing 56pt.
- Line-height: 1.55 body, 1.3 headings. Letter-spacing -0.005em ... -0.02em.
- Weights: 400 base, 500 medium, 600 headings. No 700.

### Spacing / rhythm

- Chat column max-width: **760px** centered.
- Between message groups: 40px. Within a group: 16–24px.
- Bubble padding: 16/20. Border-radius: 14px. (User bubble has one
  squared corner, assistant the opposite — subtle conversational cue.)
- Composer padding: 12–16px, wrapped in a 16px radius wrapper with textarea
  + 40×40 submit pill.
- Icons: 13–16px. No decorative glyphs.

### Motion

- `vc-reveal` — 320ms opacity + 4px rise on every new chat block. Delays
  (0/40/80/120ms) available for staggered reveals.
- `vc-dot` — 3-dot loader used in StatusBar + Thinking bubble.
- No parallax, no floating backgrounds, no shimmer.

## Components (all under `components/v4/chat/`)

| File                 | Responsibility                                                 |
| -------------------- | -------------------------------------------------------------- |
| `StatusBar.tsx`      | 48px sticky header · stage · loader dots · cost · new-research |
| `MessageBubble.tsx`  | Generic user/assistant/system bubble + `Thinking` loader       |
| `PromptBlock.tsx`    | Assistant card: prompt <pre>, copy, reasoning collapsible, 3 tool cards, continue CTA |
| `CritiqueBlock.tsx`  | Compact stats row, quality notes, 4 collapsible sections, followup <pre> |
| `UploadComposer.tsx` | Drop zone styled as composer; detects tool by filename; list of file rows; skip option |
| `Composer.tsx`       | Auto-growing textarea (max 6 rows) + Cmd/Ctrl+Enter + round submit |
| `FinalReportBlock.tsx` | Full-width report: title, exec summary, key numbers, ranking bar, Q→A, synthesis, sources, export menu |

## Routes

| Route                | Purpose                                                                       |
| -------------------- | ----------------------------------------------------------------------------- |
| `/v4/chat`           | Empty canvas + single input. On submit: `createSession(q)` → `/v4/chat/[id]`. |
| `/v4/chat/[id]`      | Resumable conversation. Wraps `ChatView.tsx` in a fresh `CostProvider`.       |
| `/v4/new`            | **Redirect** → `/v4/chat` (preserves `?q=`).                                  |
| `/v4/session/[id]/*` | Old wizard — untouched (fallback).                                            |

## State → message mapping

`ChatView.tsx` re-renders from server state every time `session` updates.
Nothing is stored in a local turn counter — users arriving mid-flow (or
resuming after reload) see exactly the right messages.

| Session fields                                      | Rendered chat blocks                              |
| --------------------------------------------------- | ------------------------------------------------- |
| `raw_question` present                              | user bubble with the question                     |
| no `research_prompt` + busy === "prompt"            | Thinking("Собираю research-промт…")               |
| `research_prompt` present                           | `PromptBlock` assistant card                      |
| `source_reports.length > 0`                         | user bubble "Загрузил N отчётов: a.md, b.md"      |
| busy === "analyze"                                  | Thinking("Анализирую…")                           |
| `analysis` present                                  | `CritiqueBlock` with `followup_prompt` or first MUST from legacy list |
| `followup_reports.length > 0`                       | user bubble "Загрузил N доборных отчётов"         |
| skippedFollowup && no followup_reports && no final  | user bubble "Собрать синтез без добора"           |
| busy === "synthesize"                               | Thinking("Собираю синтез…")                       |
| `final_report` present                              | `FinalReportBlock` (full width, within 760px wrap)|

## Composer slot mapping

| Condition                                                | Composer shown                 |
| -------------------------------------------------------- | ------------------------------ |
| busy !== null                                            | **none** (hide during thinking)|
| session missing raw_question + research_prompt           | `Composer` (text input)        |
| research_prompt present && no source_reports             | `UploadComposer` (reports)     |
| analysis present && no followup_reports && !skipped      | `UploadComposer` (followup)    |
| final_report present                                     | "Новое исследование" row       |

## Followup compatibility (per sibling `followup-single`)

`CritiqueBlock` reads `analysis.followup_prompt` first (v4.1+ canonical
single prompt). Falls back to `followup_prompts[0]` filtered by
`priority === "must"`, else to `followup_prompts[0]` as last resort.

## Cost tracking (per sibling `cost-tracking`)

StatusBar consumes `useCost()` and shows `{cost} ₽` only when cost > 0.
Every mutation re-fetches `getSession()` and calls `setCost()`.
CostProvider is mounted independently in both chat pages to avoid
depending on V4Shell / AppShell state.

## Layout isolation

Chat uses `.v4-chat-host` (`position: fixed; inset: 0; z-index: 50`) to
overlay the AppShell sidebar and old Masthead. No layout changes to the
global `AppShell` or `app/v4/layout.tsx` — means zero risk to v2/v3/old-v4.

## What was stripped

- `.v4-display-l`, `.v4-display-xl` — all giant serif type.
- `.c-tl`, `.c-br`, `.v4-corners` — corner marks.
- `SectionKicker § NN` — replaced with lowercase mono labels
  (`research-prompt`, `главные выводы`, etc.).
- Drop-cap — exec summary is clean 17px prose.
- Amber `#d97706` / `#b8862e` — gone, only neutral ink.
- Double-rule Masthead — replaced with flat 48px StatusBar.

## Constraint audit

- [x] No changes to `lib/apiV4.ts` or `lib/apiV4Stubs.ts`.
- [x] No changes to `:root` tokens — only append-only `.v4-chat` scope.
- [x] v2/v3/library/settings/report routes untouched.
- [x] Old `/v4/session/[id]/*` pages still resolve.
- [x] `/v4/new` redirects to `/v4/chat`.
- [x] User arriving mid-flow renders correctly — state comes from session.
- [x] STUB_MODE works end-to-end.
- [x] `npx tsc --noEmit` passes.
- [x] `npm run build` passes.
- [x] Error state: in-line danger box + "Повторить" button.
- [x] `/v4/chat` is a Suspense-wrapped Client Component (uses `useSearchParams`).

## Baseline restoration commit

The `fix/cost-tracking` branch referenced 7 components and 230 lines of CSS
that were **never committed** (files only existed in someone's working tree).
The first commit on `design/chat-ui` restores them exactly as they lived on
disk so `tsc --noEmit` can succeed against the v4 wizard pages. No behavior
change — just paperwork.

## Open questions

1. **Inter vs Geist.** Task asked for a one-shot pick. Picked Inter because
   it was already loaded in `app/layout.tsx` for the rest of the product and
   adding `geist` npm would touch deps. If we want the subtle Geist warmth,
   swap the `--vc-f-sans` stack and ship.
2. **Footer CTAs inside PromptBlock / CritiqueBlock.** Kept them because
   users otherwise scroll without a clear next action. If parent bottom
   composer should be the only CTA channel, remove `onContinue` usage — it
   currently just autoscrolls, not mutation.
3. **Server-rendered V4Shell.** The v4 layout still mounts the old Masthead
   behind our fixed overlay. It's invisible but adds DOM. If we want to
   strip it, extend `AppShell` to treat `/v4/chat` as a full-viewport route
   and drop the wrapper entirely.
