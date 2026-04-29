// v4 API client — talks to the v3 FastAPI (/api/v4/* endpoints).
// Stub mode: set NEXT_PUBLIC_V4_STUB=1 to walk the UI without a backend.

// `??` not `||` — Dockerfile sets NEXT_PUBLIC_V4_API_BASE="" at build time
// so prod uses same-origin relative URLs (handled by Next.js catch-all
// proxy at /api/[...path]). Empty string is falsy under `||`, which would
// fall through to the localhost default and try to fetch from the *user's*
// machine in prod — that's where "Failed to fetch" came from in the field.
const V4_BASE =
  process.env.NEXT_PUBLIC_V4_API_BASE ??
  process.env.NEXT_PUBLIC_V3_API_BASE ??
  "http://localhost:8010";

const STUB = process.env.NEXT_PUBLIC_V4_STUB === "1";

// -- Types (mirrored from spec §4 Track A+B) ------------------------------

export type V4SessionStatus =
  | "created"
  | "prompt_ready"
  | "reports_uploaded"
  | "analyzed"
  | "dobor_uploaded"
  | "synthesized";

export type ResearchPrompt = {
  full_prompt: string;
  reasoning: string;
  expected_structure: string[];
  key_entities: string[];
  tips_for_search: string;
};

export type DetectedTool = "perplexity" | "openai_dr" | "claude" | "other" | null;

export type UploadedMarkdown = {
  filename: string;
  content: string;
  detected_tool: DetectedTool;
  word_count: number;
};

export type ConsensusClaim = {
  claim: string;
  supporting_sources: string[];
  confidence: "high" | "medium" | "low";
};

export type Conflict = {
  topic: string;
  source_a: string;
  claim_a: string;
  source_b: string;
  claim_b: string;
  resolution_hint: string;
  importance: "critical" | "material" | "minor";
};

export type Gap = {
  topic: string;
  why_critical: string;
  what_to_find: string;
  candidate_sources: string[];
};

export type UnverifiedNumber = {
  value: string;
  metric: string;
  subject: string;
  source_tool: string;
  why_unverified: string;
};

export type FollowupPrompt = {
  prompt_id: string;
  intent: "fill_gap" | "verify_number" | "resolve_conflict";
  prompt: string;
  target_info: string;
  suggested_tool: "perplexity" | "openai_dr" | "claude";
  suggested_source_site: string;
  priority: "must" | "nice";
  linked_to: string;
};

export type SourceSummary = {
  detected_tool: string;
  filename: string;
  main_claims: string[];
  strengths: string;
  weaknesses: string;
};

export type AnalysisOutput = {
  per_source_summary: SourceSummary[];
  consensus: ConsensusClaim[];
  conflicts: Conflict[];
  gaps: Gap[];
  unverified_numbers: UnverifiedNumber[];
  quality_notes: string;
  /** Canonical single consolidated followup prompt (v4.1+). One DR run closes all gaps. */
  followup_prompt: FollowupPrompt | null;
  /** Legacy list kept for backward-compat. Shim: [followup_prompt] when new field present. */
  followup_prompts: FollowupPrompt[];
};

export type KeyNumber = {
  value: string;
  metric: string;
  source: string;
};

export type ExecutiveSummary = {
  main_answer: string;
  ranking: string | null;
  top_findings: string[];
  key_numbers: KeyNumber[];
  confidence_note: string;
  what_meta_adds: string;
};

export type FinalSource = {
  url: string;
  title: string;
  origin: string;
};

export type FinalReport = {
  session_id: string;
  question: string;
  research_prompt_used: string;
  executive_summary: ExecutiveSummary;
  main_synthesis: string;
  consensus_section: string;
  conflicts_section: string;
  gaps_filled_section: string;
  all_sources: FinalSource[];
  metadata: Record<string, unknown>;
};

export type PendingDRJob = {
  task_id: string;
  service: string;            // "valyu" | "tavily" | "exa" | "openai" | "perplexity"
  mode: string;
  state?: string;             // "running" | "interrupted_with_partial" | "failed" | "cancelled"
  cost_usd?: number;
  cost_rub?: number;
  submitted_at?: number;
  partial_content?: string;
  partial_chars?: number;
  last_progress_at?: number;
  interrupted_at?: number;
  error?: string;
  resumed_from?: string;
};

export type LongTaskPhase = "analyze" | "synthesize" | "export-pptx";
export type LongTaskState = "running" | "completed" | "failed";

export type LongTaskOut = {
  task_id: string;
  phase: LongTaskPhase;
  state: "running";
  started_at: string;
};

export type LongTaskStatusOut = {
  task_id: string;
  phase: LongTaskPhase;
  state: LongTaskState;
  started_at: string;
  completed_at: string | null;
  error: string | null;
};

export type PendingLongTask = {
  task_id: string;
  phase: LongTaskPhase;
  state: LongTaskState;
  started_at: string;
  completed_at?: string | null;
  error?: string | null;
  model_preference?: string | null;
};

export type FinalReportOut = {
  final_report: FinalReport;
  total_cost_rub: number;
  status: V4SessionStatus;
};

export type V4Session = {
  session_id: string;
  raw_question: string;
  research_prompt: ResearchPrompt | null;
  source_reports: UploadedMarkdown[];
  analysis: AnalysisOutput | null;
  followup_reports: UploadedMarkdown[];
  final_report: FinalReport | null;
  status: V4SessionStatus;
  created_at: string;
  total_cost_rub: number;
  pending_dr_jobs?: PendingDRJob[];
  pending_long_tasks?: PendingLongTask[];
};

export type V4Event = {
  seq: number;
  phase:
    | "status"
    | "prompt_master"
    | "external_research"
    | "analyzer"
    | "synthesizer"
    | "done"
    | "error";
  message: string;
  data: Record<string, unknown> | null;
  ts: number;
};

export type V4EventsResponse = {
  events: V4Event[];
  cursor: number;
  status: "pending" | "running" | "done" | "error";
  error: string | null;
};

// -- Fetch helpers --------------------------------------------------------

async function jv4<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${V4_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

// -- Stub fixtures --------------------------------------------------------
// Data for demo mode lives in ./apiV4Stubs to keep this file under 400 lines.

import {
  stubSession,
  stubFinalReport,
  detectTool,
  STUB_PROMPT,
  STUB_ANALYSIS,
} from "./apiV4Stubs";

// -- API functions --------------------------------------------------------

export async function createSession(
  question: string
): Promise<{ session_id: string }> {
  if (STUB) {
    const id = `stub-${Date.now().toString(36)}`;
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(
        `v4:${id}`,
        JSON.stringify(stubSession(id, question))
      );
    }
    return { session_id: id };
  }
  return jv4<{ session_id: string }>("/api/v4/sessions", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export async function generatePrompt(id: string, modelPreference?: "sonnet" | "opus"): Promise<ResearchPrompt> {
  if (STUB) {
    await new Promise((r) => setTimeout(r, 600));
    const key = `v4:${id}`;
    if (typeof window !== "undefined") {
      const raw = window.sessionStorage.getItem(key);
      if (raw) {
        const s: V4Session = JSON.parse(raw);
        s.research_prompt = STUB_PROMPT;
        s.status = "prompt_ready";
        window.sessionStorage.setItem(key, JSON.stringify(s));
      }
    }
    return STUB_PROMPT;
  }
  const body = modelPreference ? JSON.stringify({ model_preference: modelPreference }) : undefined;
  return jv4<ResearchPrompt>(
    `/api/v4/sessions/${encodeURIComponent(id)}/generate-prompt`,
    { method: "POST", body }
  );
}

export async function uploadReports(
  id: string,
  files: File[]
): Promise<UploadedMarkdown[]> {
  if (STUB) {
    const uploaded: UploadedMarkdown[] = await Promise.all(
      files.map(async (f) => ({
        filename: f.name,
        content: await f.text().catch(() => ""),
        detected_tool: detectTool(f.name),
        word_count: 0,
      }))
    );
    const key = `v4:${id}`;
    if (typeof window !== "undefined") {
      const raw = window.sessionStorage.getItem(key);
      if (raw) {
        const s: V4Session = JSON.parse(raw);
        s.source_reports = uploaded;
        s.status = "reports_uploaded";
        window.sessionStorage.setItem(key, JSON.stringify(s));
      }
    }
    return uploaded;
  }
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const res = await fetch(
    `${V4_BASE}/api/v4/sessions/${encodeURIComponent(id)}/upload-reports`,
    { method: "POST", body: fd }
  );
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// -- Long-task primitives (fire+poll for /analyze, /synthesize) -----------
// Backend returns 202 + task_id; the actual LLM call runs in a background
// task on the server. Frontend polls /long-task-status until terminal,
// then re-fetches the session to read the real payload.

export async function startAnalyze(
  id: string, modelPreference?: "sonnet" | "opus",
): Promise<LongTaskOut> {
  const body = modelPreference
    ? JSON.stringify({ model_preference: modelPreference })
    : undefined;
  return jv4<LongTaskOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/analyze`,
    { method: "POST", body },
  );
}

export async function startSynthesize(
  id: string, modelPreference?: "sonnet" | "opus",
): Promise<LongTaskOut> {
  const body = modelPreference
    ? JSON.stringify({ model_preference: modelPreference })
    : undefined;
  return jv4<LongTaskOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/synthesize`,
    { method: "POST", body },
  );
}

export async function pollLongTaskStatus(
  id: string, taskId: string,
): Promise<LongTaskStatusOut> {
  return jv4<LongTaskStatusOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/long-task-status?task_id=${encodeURIComponent(taskId)}`,
  );
}

/** Submit a long task and resolve when it terminates.
 *
 * Polls every `intervalMs` (default 5s). Caps at `timeoutMs` (default 1h)
 * to prevent runaway loops if a task gets stuck — at which point it
 * throws so the UI can show a recovery banner. Server-side state is
 * preserved in `session.pending_long_tasks` so an F5 reload during a
 * long task picks up where polling left off.
 *
 * On 409 from the start endpoint (task already running for this phase),
 * extracts the existing task_id from the error detail and polls that
 * instead of failing.
 */
async function _runLongTask(
  start: () => Promise<LongTaskOut>,
  poll: (taskId: string) => Promise<LongTaskStatusOut>,
  opts: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<LongTaskStatusOut> {
  const intervalMs = opts.intervalMs ?? 5_000;
  const timeoutMs = opts.timeoutMs ?? 3_600_000; // 1h

  let taskId: string;
  try {
    const submitted = await start();
    taskId = submitted.task_id;
  } catch (e: unknown) {
    // Resume an in-flight task on 409 — backend embeds task_id in detail.
    const msg = e instanceof Error ? e.message : String(e);
    const match = msg.match(/task_id=([0-9a-f]{32})/i);
    if (msg.includes("409") && match) {
      taskId = match[1];
    } else {
      throw e;
    }
  }

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await poll(taskId);
    if (status.state === "completed" || status.state === "failed") {
      return status;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`long task ${taskId} did not terminate within ${timeoutMs}ms`);
}

export async function analyze(id: string, modelPreference?: "sonnet" | "opus"): Promise<AnalysisOutput> {
  if (STUB) {
    await new Promise((r) => setTimeout(r, 1200));
    const key = `v4:${id}`;
    if (typeof window !== "undefined") {
      const raw = window.sessionStorage.getItem(key);
      if (raw) {
        const s: V4Session = JSON.parse(raw);
        s.analysis = STUB_ANALYSIS;
        s.status = "analyzed";
        s.total_cost_rub = 18;
        window.sessionStorage.setItem(key, JSON.stringify(s));
      }
    }
    return STUB_ANALYSIS;
  }
  const status = await _runLongTask(
    () => startAnalyze(id, modelPreference),
    (tid) => pollLongTaskStatus(id, tid),
  );
  if (status.state !== "completed") {
    throw new Error(status.error || `analyze ${status.task_id} failed`);
  }
  const session = await getSession(id);
  if (!session.analysis) {
    throw new Error(`analyze ${status.task_id} completed but session.analysis is null`);
  }
  return session.analysis;
}

export async function uploadFollowup(
  id: string,
  files: File[]
): Promise<UploadedMarkdown[]> {
  if (STUB) {
    const uploaded: UploadedMarkdown[] = await Promise.all(
      files.map(async (f) => ({
        filename: f.name,
        content: await f.text().catch(() => ""),
        detected_tool: detectTool(f.name),
        word_count: 0,
      }))
    );
    const key = `v4:${id}`;
    if (typeof window !== "undefined") {
      const raw = window.sessionStorage.getItem(key);
      if (raw) {
        const s: V4Session = JSON.parse(raw);
        s.followup_reports = uploaded;
        s.status = "dobor_uploaded";
        window.sessionStorage.setItem(key, JSON.stringify(s));
      }
    }
    return uploaded;
  }
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const res = await fetch(
    `${V4_BASE}/api/v4/sessions/${encodeURIComponent(id)}/upload-followup`,
    { method: "POST", body: fd }
  );
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export async function synthesize(id: string, modelPreference?: "sonnet" | "opus"): Promise<FinalReport> {
  if (STUB) {
    await new Promise((r) => setTimeout(r, 1500));
    const key = `v4:${id}`;
    let question = "Stub session";
    if (typeof window !== "undefined") {
      const raw = window.sessionStorage.getItem(key);
      if (raw) {
        const s: V4Session = JSON.parse(raw);
        question = s.raw_question;
      }
    }
    const fr: FinalReport = stubFinalReport(id, question);
    if (typeof window !== "undefined") {
      const raw = window.sessionStorage.getItem(key);
      if (raw) {
        const s: V4Session = JSON.parse(raw);
        s.final_report = fr;
        s.status = "synthesized";
        s.total_cost_rub = 42;
        window.sessionStorage.setItem(key, JSON.stringify(s));
      }
    }
    return fr;
  }
  const status = await _runLongTask(
    () => startSynthesize(id, modelPreference),
    (tid) => pollLongTaskStatus(id, tid),
  );
  if (status.state !== "completed") {
    throw new Error(status.error || `synthesize ${status.task_id} failed`);
  }
  const final = await getFinalReport(id);
  if (!final.final_report) {
    throw new Error(`synthesize ${status.task_id} completed but session.final_report is null`);
  }
  return final.final_report;
}

export async function getSession(id: string): Promise<V4Session> {
  if (STUB) {
    if (typeof window !== "undefined") {
      const raw = window.sessionStorage.getItem(`v4:${id}`);
      if (raw) return JSON.parse(raw);
    }
    return stubSession(id, "");
  }
  return jv4<V4Session>(`/api/v4/sessions/${encodeURIComponent(id)}`);
}

export async function getFinalReport(id: string): Promise<FinalReportOut> {
  if (STUB) {
    const session = await getSession(id);
    if (!session.final_report) {
      throw new Error(`session ${id} has no final_report yet`);
    }
    return {
      final_report: session.final_report,
      total_cost_rub: session.total_cost_rub,
      status: session.status,
    };
  }
  return jv4<FinalReportOut>(`/api/v4/sessions/${encodeURIComponent(id)}/final-report`);
}

export async function getEvents(
  id: string,
  since: number,
  timeout = 25
): Promise<V4EventsResponse> {
  if (STUB) {
    return { events: [], cursor: since, status: "done", error: null };
  }
  return jv4<V4EventsResponse>(
    `/api/v4/sessions/${encodeURIComponent(id)}/events?since=${since}&timeout=${timeout}`
  );
}

// -- Quality grade --------------------------------------------------------

export type QualityGrade = {
  grade: "A" | "B" | "C" | "N/A";
  score: number;
  strong_count: number;
  moderate_count: number;
  weak_count: number;
  unique_domains: number;
  total_sources: number;
  consensus_count: number;
  conflict_count: number;
  gap_count: number;
  unverified_number_count: number;
  summary: string;
};

export async function getQualityGrade(id: string): Promise<QualityGrade> {
  if (STUB) {
    return {
      grade: "B", score: 0.62,
      strong_count: 3, moderate_count: 4, weak_count: 1,
      unique_domains: 7, total_sources: 8,
      consensus_count: 5, conflict_count: 1, gap_count: 2,
      unverified_number_count: 0,
      summary: "Стаб: достаточно — 3/8 STRONG.",
    };
  }
  return jv4<QualityGrade>(`/api/v4/sessions/${encodeURIComponent(id)}/quality`);
}

// -- Session list ---------------------------------------------------------

export type SessionListItem = {
  session_id: string;
  raw_question: string;
  status: V4SessionStatus | "cancelled";
  created_at: string;
  total_cost_rub: number;
  has_final_report: boolean;
};

export async function listSessions(): Promise<SessionListItem[]> {
  if (STUB) return [];
  return jv4<SessionListItem[]>("/api/v4/sessions");
}

// -- Cancel + Delete ------------------------------------------------------

export async function cancelSession(id: string): Promise<{ session_id: string; status: string }> {
  if (STUB) {
    return { session_id: id, status: "cancelled" };
  }
  return jv4(`/api/v4/sessions/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
  });
}

export async function deleteSession(id: string): Promise<void> {
  if (STUB) return;
  const res = await fetch(`${V4_BASE}/api/v4/sessions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) {
    throw new Error(`${res.status} ${await res.text().catch(() => "")}`);
  }
}

// -- Auto-DR (server-side Deep Research) ----------------------------------

export type AutoDRService = "valyu" | "tavily" | "exa" | "perplexity" | "openai" | "claude" | "gemini";
export type ValyuResearchMode = "fast" | "standard" | "heavy" | "max";

export type AutoDROut = {
  service: string;
  filename: string;
  word_count: number;
  source_count: number;
  cost_usd: number;
  cost_rub: number;
  notes: string;
  task_id: string | null;
};

export type AutoDRAsyncOut = {
  service: string;
  // Free-form: valyu uses fast/standard/heavy/max, tavily uses mini/pro/auto,
  // exa uses fast/standard/pro. Backend validates per-service.
  mode: string;
  task_id: string;
  cost_usd: number;
  cost_rub: number;
  eta_min_low: number;
  eta_min_high: number;
  message: string;
};

export type AutoDRAnyOut = AutoDROut | AutoDRAsyncOut;

export function isAsyncOut(o: AutoDRAnyOut): o is AutoDRAsyncOut {
  return (o as AutoDRAsyncOut).task_id !== undefined && (o as AutoDRAsyncOut).task_id !== null
    && !!(o as AutoDRAsyncOut).mode;
}

export type AutoDRStatusOut = {
  task_id: string;
  state: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress_pct: number | null;
  message: string | null;
  filename: string | null;
  word_count: number | null;
  source_count: number | null;
  cost_usd: number | null;
  cost_rub: number | null;
  error: string | null;
};

export async function runAutoDR(
  id: string,
  service: AutoDRService,
  opts: { prompt?: string; domain_hint?: string; mode?: string } = {}
): Promise<AutoDRAnyOut> {
  if (STUB) {
    await new Promise((r) => setTimeout(r, 1200));
    if (opts.mode && service === "valyu") {
      return {
        service: "valyu",
        mode: opts.mode,
        task_id: `stub-task-${Date.now()}`,
        cost_usd: 0.50, cost_rub: 37.7,
        eta_min_low: 10, eta_min_high: 20,
        message: "Stub: Valyu Research (standard) ~10–20 мин",
      } as AutoDRAsyncOut;
    }
    return {
      service, filename: `auto_dr_${service}.md`,
      word_count: 1234, source_count: 7,
      cost_usd: 0.012, cost_rub: 0.9, notes: "stub",
      task_id: null,
    };
  }
  return jv4<AutoDRAnyOut>(`/api/v4/sessions/${encodeURIComponent(id)}/auto-dr`, {
    method: "POST",
    body: JSON.stringify({
      service,
      prompt: opts.prompt,
      domain_hint: opts.domain_hint,
      mode: opts.mode,
    }),
  });
}

export async function cancelAutoDR(id: string, taskId: string): Promise<{ task_id: string; state: string }> {
  if (STUB) return { task_id: taskId, state: "cancelled" };
  return jv4(
    `/api/v4/sessions/${encodeURIComponent(id)}/auto-dr-cancel?task_id=${encodeURIComponent(taskId)}`,
    { method: "POST" }
  );
}

export async function acceptPartialAutoDR(
  id: string, taskId: string,
): Promise<{ task_id: string; ok: boolean }> {
  if (STUB) return { task_id: taskId, ok: true };
  return jv4(
    `/api/v4/sessions/${encodeURIComponent(id)}/auto-dr-accept-partial?task_id=${encodeURIComponent(taskId)}`,
    { method: "POST" }
  );
}

export async function resumeAutoDR(
  id: string, taskId: string,
): Promise<AutoDRAsyncOut> {
  if (STUB) {
    return {
      service: "openai", mode: "mini",
      task_id: `stub-resumed-${Date.now()}`,
      cost_usd: 0.50, cost_rub: 37.7,
      eta_min_low: 5, eta_min_high: 10,
      message: "Stub: resumed",
    };
  }
  return jv4(
    `/api/v4/sessions/${encodeURIComponent(id)}/auto-dr-resume?task_id=${encodeURIComponent(taskId)}`,
    { method: "POST" }
  );
}

export async function runAutoFollowup(
  id: string,
  opts: { service?: "valyu" | "exa"; mode?: string } = {}
): Promise<AutoDRAsyncOut> {
  if (STUB) {
    return {
      service: opts.service || "valyu",
      mode: opts.mode || "standard",
      task_id: `stub-fu-${Date.now()}`,
      cost_usd: 0.50, cost_rub: 37.7,
      eta_min_low: 15, eta_min_high: 30,
      message: "Stub: followup standard ~15-30 мин",
    };
  }
  return jv4<AutoDRAsyncOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/auto-followup`,
    {
      method: "POST",
      body: JSON.stringify({
        service: opts.service || "valyu",
        mode: opts.mode || "standard",
      }),
    }
  );
}

export async function pollAutoDRStatus(id: string, taskId: string): Promise<AutoDRStatusOut> {
  if (STUB) {
    return {
      task_id: taskId, state: "completed",
      progress_pct: 100, message: null,
      filename: "stub_research.md", word_count: 2000, source_count: 12,
      cost_usd: 0.50, cost_rub: 37.7, error: null,
    };
  }
  return jv4<AutoDRStatusOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/auto-dr-status?task_id=${encodeURIComponent(taskId)}`
  );
}

export function exportUrl(id: string, format: string): string {
  return `${V4_BASE}/api/v4/sessions/${encodeURIComponent(id)}/export?format=${encodeURIComponent(format)}`;
}

// -- Gamma PPTX (Gamma API integration, replaces stub) --------------------
// Real PPTX generation: 1-3 min. Uses the long-task pattern.

export async function startExportGammaPptx(id: string): Promise<LongTaskOut> {
  if (STUB) {
    return {
      task_id: `stub-gamma-${Date.now()}`,
      phase: "export-pptx",
      state: "running",
      started_at: new Date().toISOString(),
    };
  }
  return jv4<LongTaskOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/export-gamma-pptx`,
    { method: "POST" },
  );
}

/** Submit a Gamma PPTX generation and resolve when the file is ready.
 *
 * Returns the absolute download URL. Caller should `window.open()` or
 * `<a href>` it. On Gamma failure (no API key, no credits, etc.) the
 * underlying long-task transitions to `failed` and this throws with
 * the recorded error message.
 */
export async function generateGammaPptx(id: string): Promise<string> {
  if (STUB) {
    await new Promise((r) => setTimeout(r, 800));
    return exportUrl(id, "gamma-pptx-real");
  }
  const status = await _runLongTask(
    () => startExportGammaPptx(id),
    (tid) => pollLongTaskStatus(id, tid),
    { intervalMs: 5000, timeoutMs: 600_000 },
  );
  if (status.state !== "completed") {
    throw new Error(status.error || `gamma-pptx ${status.task_id} failed`);
  }
  return exportUrl(id, "gamma-pptx-real");
}

export const STUB_ENABLED = STUB;
