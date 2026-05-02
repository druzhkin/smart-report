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

export type DetectedTool = "perplexity" | "openai_dr" | "claude" | "paper_search_mcp" | "other" | null;

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

export type ReportActorRole = "analyst" | "editor" | "client_reviewer" | "quality_reviewer";
export type ReportArtifactFormat = "docx" | "pdf" | "pptx" | "gamma_pptx" | "html" | "data_pack";

export type StructuredReportBlock = {
  id: string;
  kind: "narrative" | "bullets" | "callout" | "chart" | "table" | "kpi_strip" | "source_note";
  title: string;
  content: string;
  bullets: string[];
  source_ids: string[];
};

export type StructuredReportSection = {
  id: string;
  title: string;
  summary: string;
  blocks: StructuredReportBlock[];
};

export type StructuredReportSource = {
  metadata: {
    report_id: string;
    title: string;
    subtitle: string;
    client_name: string;
    language: string;
    created_at: string;
    updated_at: string;
  };
  sections: StructuredReportSection[];
  sources: unknown[];
  research_coverage: {
    declared_domain: string;
    connectors_used: string[];
    scientific_or_primary_connectors: string[];
    known_coverage_gaps: string[];
  };
  versions: { version_id: string; actor_role: ReportActorRole; summary: string; source_hash: string; created_at: string }[];
};

export type ReportEditRequest = {
  actor_role: ReportActorRole;
  operation?: "replace" | "append";
  target_path: string;
  value: unknown;
  reason?: string;
};

export type ReportEditableField = {
  path: string;
  label: string;
  value_type: "string" | "string_list" | "table_rows" | "json";
  current_value: unknown;
  actor_roles: ReportActorRole[];
};

export type ReportQualityGate = {
  passed: boolean;
  score: number;
  issues: { code: string; severity: "critical" | "major" | "minor"; message: string; recommendation: string }[];
  checked_at: string;
};

export type PublicationQualityGate = {
  ready: boolean;
  score: number;
  issues: { code: string; severity: "critical" | "major" | "minor"; message: string; recommendation: string }[];
  metrics: Record<string, unknown>;
  remediation_plan?: {
    issue_code: string;
    severity: "critical" | "major" | "minor";
    priority: number;
    action: string;
    target: string;
    artifact: string;
    acceptance_criteria: string[];
    current_value?: unknown;
    target_value?: unknown;
  }[];
} | null;

export type ReportRegenerationPlan = {
  source_hash: string;
  requested_formats: ReportArtifactFormat[];
  default_word_artifact: "docx";
  quality_gate: ReportQualityGate;
  can_regenerate: boolean;
};

export type StructuredReportSourceOut = {
  source: StructuredReportSource;
  editable_fields?: ReportEditableField[];
  quality_gate: ReportQualityGate;
  regeneration_plan: ReportRegenerationPlan;
  publication_quality?: PublicationQualityGate;
};

export type StructuredReportAutoImproveOut = StructuredReportSourceOut & {
  iterations: {
    iteration: number;
    quality_gate_passed: boolean;
    quality_gate_score: number;
    publication_ready: boolean;
    publication_score?: number;
    remediation_count?: number;
    applied: boolean;
    version_count?: number;
    stop?: "ready" | "no_safe_remediation";
  }[];
  stopped_reason:
    | "ready"
    | "no_safe_remediation"
    | "no_structural_change"
    | "max_iterations_reached";
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
    | "analytic_depth"
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

export type AnalyticMethod =
  | "issue_tree"
  | "competing_hypotheses"
  | "key_assumptions_check"
  | "disconfirming_evidence"
  | "benchmarking"
  | "indicator_signpost"
  | "number_verification"
  | "source_triangulation";

export type ResearchLeadKind =
  | "close_gap"
  | "resolve_conflict"
  | "verify_number"
  | "explore_anomaly"
  | "find_benchmark"
  | "strengthen_source_base"
  | "support_claim"
  | "test_hypothesis"
  | "monitor_indicator";

export type ResearchService =
  | "valyu"
  | "paper_search"
  | "perplexity"
  | "openai"
  | "claude"
  | "exa"
  | "tavily"
  | "manual";

export type InquiryNode = {
  id: string;
  question: string;
  rationale: string;
  methods: AnalyticMethod[];
  parent_id: string | null;
  expected_output: string;
  children: InquiryNode[];
};

export type CompetingHypothesis = {
  id: string;
  statement: string;
  why_plausible: string;
  would_be_supported_by: string[];
  would_be_weakened_by: string[];
  current_confidence: "high" | "medium" | "low" | "unknown";
};

export type EvidenceProbe = {
  id: string;
  method: AnalyticMethod;
  target: string;
  question: string;
  expected_evidence: string;
  disconfirming: boolean;
};

export type ResearchLead = {
  id: string;
  kind: ResearchLeadKind;
  priority: "must" | "should" | "could";
  prompt: string;
  rationale: string;
  target_entities: string[];
  target_metrics: string[];
  candidate_sources: string[];
  recommended_service: ResearchService;
  recommended_mode: string | null;
  linked_to: string[];
};

export type AnalyticDepthPlan = {
  question: string;
  domain_hint: string;
  root: InquiryNode;
  hypotheses: CompetingHypothesis[];
  evidence_probes: EvidenceProbe[];
  research_leads: ResearchLead[];
  benchmark_questions: string[];
  monitoring_indicators: string[];
  method_notes: string[];
};

export type ClosureStatus = "closed" | "partial" | "not_closed" | "not_started";

export type LeadClosure = {
  lead_id: string;
  kind: string;
  priority: string;
  status: ClosureStatus;
  score: number;
  matched_reports: string[];
  evidence_signals: string[];
  missing_signals: string[];
  recommendation: string;
};

export type AnalyticClosureReport = {
  overall_score: number;
  closed: number;
  partial: number;
  not_closed: number;
  not_started: number;
  lead_count: number;
  followup_report_count: number;
  lead_closures: LeadClosure[];
  summary: string;
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
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed?.detail === "string") detail = parsed.detail;
    } catch {}
    if (res.status === 402) {
      throw new Error(
        `402 Payment Required: ${detail || "monthly spending limit reached"}. ` +
        "Повышен месячный лимит или повторите действие после обновления деплоя."
      );
    }
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
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

export async function getStructuredReportSource(id: string): Promise<StructuredReportSourceOut> {
  if (STUB) {
    const session = await getSession(id);
    const final = session.final_report ?? stubFinalReport(id, session.raw_question || "Stub report");
    const source = stubStructuredSource(final);
    return structuredSourceEnvelope(source);
  }
  return jv4<StructuredReportSourceOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/structured-source`
  );
}

export async function patchStructuredReportSource(
  id: string,
  edits: ReportEditRequest[],
): Promise<StructuredReportSourceOut> {
  if (STUB) {
    const current = await getStructuredReportSource(id);
    const source = structuredClone(current.source);
    for (const edit of edits) {
      if (edit.target_path === "metadata.title") {
        source.metadata.title = String(edit.value ?? "");
      }
      const match = edit.target_path.match(/^sections\.([^.]+)\.blocks\.([^.]+)\.content$/);
      if (match) {
        const section = source.sections.find((item) => item.id === match[1]);
        const block = section?.blocks.find((item) => item.id === match[2]);
        if (block) block.content = String(edit.value ?? "");
      }
    }
    source.versions = [
      ...source.versions,
      {
        version_id: `v_${Date.now().toString(36)}`,
        actor_role: edits.at(-1)?.actor_role ?? "editor",
        summary: "Stub structured edit",
        source_hash: `${Date.now()}`,
        created_at: new Date().toISOString(),
      },
    ];
    return structuredSourceEnvelope(source);
  }
  return jv4<StructuredReportSourceOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/structured-source`,
    { method: "PATCH", body: JSON.stringify({ edits }) },
  );
}

export async function regenerateStructuredReportPackage(
  id: string,
  opts: { requested_formats?: ReportArtifactFormat[]; allow_draft?: boolean } = {},
): Promise<Blob> {
  if (STUB) {
    return new Blob([`stub package for ${id}`], { type: "application/zip" });
  }
  const res = await fetch(`${V4_BASE}/api/v4/sessions/${encodeURIComponent(id)}/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      requested_formats: opts.requested_formats ?? ["docx", "pdf", "pptx"],
      allow_draft: opts.allow_draft ?? false,
    }),
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}: ${await res.text().catch(() => "")}`);
  }
  return res.blob();
}

export async function applyStructuredReportRemediation(
  id: string,
  remediationPlan?: NonNullable<PublicationQualityGate>["remediation_plan"],
): Promise<StructuredReportSourceOut> {
  if (STUB) {
    const current = await getStructuredReportSource(id);
    return structuredSourceEnvelope(withStubVisualEvidence(current.source));
  }
  return jv4<StructuredReportSourceOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/apply-remediation`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ remediation_plan: remediationPlan }),
    },
  );
}

export async function autoImproveStructuredReport(
  id: string,
  maxIterations = 3,
): Promise<StructuredReportAutoImproveOut> {
  if (STUB) {
    const current = await getStructuredReportSource(id);
    const source = withStubVisualEvidence(current.source);
    return {
      ...structuredSourceEnvelope(source),
      iterations: [
        {
          iteration: 1,
          quality_gate_passed: current.quality_gate.passed,
          quality_gate_score: current.quality_gate.score,
          publication_ready: false,
          publication_score: current.publication_quality?.score,
          remediation_count: 1,
          applied: true,
        },
        {
          iteration: 2,
          quality_gate_passed: true,
          quality_gate_score: 100,
          publication_ready: false,
          publication_score: 76,
          applied: false,
          stop: "no_safe_remediation",
        },
      ],
      stopped_reason: "no_safe_remediation",
    };
  }
  return jv4<StructuredReportAutoImproveOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/auto-improve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_iterations: maxIterations }),
    },
  );
}

function withStubVisualEvidence(source: StructuredReportSource): StructuredReportSource {
  if (source.sections.some((section) =>
    section.blocks.some((block) => ["chart", "table", "kpi_strip"].includes(block.kind)),
  )) {
    return source;
  }
  const next: StructuredReportSource = {
    ...source,
    sections: source.sections.map((section, index) =>
      index === 0
        ? {
            ...section,
            blocks: [
              ...section.blocks,
              {
                id: "block_stub_kpi",
                kind: "kpi_strip",
                title: "Stub evidence strip",
                content: "",
                bullets: ["1 source — demo evidence", "3 artifacts — DOCX/PDF/PPTX"],
                source_ids: [],
              },
            ],
          }
        : section,
    ),
    versions: [
      ...source.versions,
      {
        version_id: `v_${Date.now().toString(36)}_auto`,
        actor_role: "editor",
        summary: "Stub automatic remediation",
        source_hash: `${Date.now()}_auto`,
        created_at: new Date().toISOString(),
      },
    ],
  };
  return next;
}

function stubStructuredSource(final: FinalReport): StructuredReportSource {
  return {
    metadata: {
      report_id: `report_${final.session_id}`,
      title: final.question,
      subtitle: final.executive_summary.main_answer,
      client_name: "",
      language: "ru",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    sections: [
      {
        id: "executive_summary",
        title: "Executive summary",
        summary: final.executive_summary.main_answer,
        blocks: [
          {
            id: "block_main_answer",
            kind: "narrative",
            title: "Main answer",
            content: final.executive_summary.main_answer,
            bullets: [],
            source_ids: [],
          },
        ],
      },
    ],
    sources: [],
    research_coverage: {
      declared_domain: "stub",
      connectors_used: ["manual_source"],
      scientific_or_primary_connectors: [],
      known_coverage_gaps: [],
    },
    versions: [
      {
        version_id: "v_initial",
        actor_role: "analyst",
        summary: "Initial stub source",
        source_hash: "stub",
        created_at: new Date().toISOString(),
      },
    ],
  };
}

function structuredSourceEnvelope(source: StructuredReportSource): StructuredReportSourceOut {
  const hasVisual = source.sections.some((section) =>
    section.blocks.some((block) => ["chart", "table", "kpi_strip"].includes(block.kind)),
  );
  const issues = hasVisual
    ? []
    : [
        {
          code: "thin_visual_support",
          severity: "major" as const,
          message: "Report needs multiple charts, tables, or KPI blocks to support the text.",
          recommendation: "",
        },
      ];
  const gate: ReportQualityGate = {
    passed: issues.length === 0,
    score: issues.length === 0 ? 100 : 88,
    issues,
    checked_at: new Date().toISOString(),
  };
  return {
    source,
    quality_gate: gate,
    regeneration_plan: {
      source_hash: source.versions.at(-1)?.source_hash ?? "stub",
      requested_formats: ["docx", "pdf", "pptx"],
      default_word_artifact: "docx",
      quality_gate: gate,
      can_regenerate: gate.passed,
    },
    publication_quality: {
      ready: hasVisual,
      score: 76,
      issues: [
        {
          code: "storyboard_visual_ratio_low",
          severity: "major",
          message: "Only stub visuals are available in local demo data.",
          recommendation: "Add charts, KPI blocks, and source-backed exhibits before export.",
        },
      ],
      metrics: {
        page_count: 8,
        visual_ratio: hasVisual ? 0.7 : 0.2,
      },
      remediation_plan: [
        {
          issue_code: "storyboard_visual_ratio_low",
          severity: "major",
          priority: 20,
          action: "Добавить или объединить страницы так, чтобы минимум 65% страниц содержали содержательные визуалы.",
          target: "visual_storyboard",
          artifact: "charts_or_kpi_blocks",
          acceptance_criteria: ["visual_ratio >= 0.65"],
          current_value: hasVisual ? 0.7 : 0.2,
          target_value: 0.65,
        },
      ],
    },
  };
}

export async function getAnalyticDepthPlan(id: string): Promise<AnalyticDepthPlan> {
  if (STUB) {
    const session = await getSession(id);
    const question = session.raw_question || session.final_report?.question || "Build a premium analytical answer";
    return {
      question,
      domain_hint: "market_general",
      root: {
        id: "root",
        question,
        rationale: "Stub research map for the premium analytical layer.",
        methods: ["issue_tree"],
        parent_id: null,
        expected_output: "A visible map of the work before final synthesis.",
        children: [
          {
            id: "evidence_base",
            question: "Which facts are strong, weak, or missing?",
            rationale: "Paid reports need a fact map before narrative.",
            methods: ["source_triangulation", "number_verification"],
            parent_id: "root",
            expected_output: "Evidence table and source quality register.",
            children: [],
          },
          {
            id: "hypotheses",
            question: "Which competing explanations could be true?",
            rationale: "Competing hypotheses prevent shallow agreement.",
            methods: ["competing_hypotheses", "disconfirming_evidence"],
            parent_id: "root",
            expected_output: "Hypothesis matrix with disconfirming tests.",
            children: [],
          },
        ],
      },
      hypotheses: [
        {
          id: "h1",
          statement: "The current answer is directionally right but under-verified.",
          why_plausible: "The uploaded sources agree on the main direction.",
          would_be_supported_by: ["Independent primary-source confirmation."],
          would_be_weakened_by: ["Conflicting transaction data or benchmark failure."],
          current_confidence: "medium",
        },
      ],
      evidence_probes: [
        {
          id: "p1",
          method: "disconfirming_evidence",
          target: "main conclusion",
          question: "What would make the current likely answer wrong?",
          expected_evidence: "A credible primary source contradicting the central claim.",
          disconfirming: true,
        },
      ],
      research_leads: [
        {
          id: "lead1",
          kind: "resolve_conflict",
          priority: "must",
          prompt: "Resolve the strongest source conflict and explain which scope is correct.",
          rationale: "Conflicts create the highest value for the analyst to resolve.",
          target_entities: [],
          target_metrics: [],
          candidate_sources: ["primary sources", "industry reports"],
          recommended_service: "perplexity",
          recommended_mode: "deep",
          linked_to: ["conflict"],
        },
      ],
      benchmark_questions: ["What benchmark makes the answer decision-useful?"],
      monitoring_indicators: ["Source conflict count", "Unverified key number count"],
      method_notes: ["Issue tree, competing hypotheses, and disconfirming evidence are shown to make long work visible."],
    };
  }
  return jv4<AnalyticDepthPlan>(`/api/v4/sessions/${encodeURIComponent(id)}/analytic-depth`);
}

export async function getAnalyticClosureReport(id: string): Promise<AnalyticClosureReport> {
  if (STUB) {
    return {
      overall_score: 42,
      closed: 0,
      partial: 1,
      not_closed: 1,
      not_started: 2,
      lead_count: 4,
      followup_report_count: 1,
      summary: "Demo closure score 42/100 across 4 priority leads.",
      lead_closures: [
        {
          lead_id: "lead1",
          kind: "resolve_conflict",
          priority: "must",
          status: "partial",
          score: 55,
          matched_reports: ["demo_followup.md"],
          evidence_signals: ["url_citation", "numeric_evidence"],
          missing_signals: ["Conflict lead lacks explicit adjudication language."],
          recommendation: "Run one narrower follow-up focused on adjudication.",
        },
      ],
    };
  }
  return jv4<AnalyticClosureReport>(
    `/api/v4/sessions/${encodeURIComponent(id)}/analytic-closure`
  );
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

export type PremiumReadinessIssue = {
  code: string;
  severity: string;
  message: string;
  recommendation: string;
};

export type PremiumReadiness = {
  ready: boolean;
  score: number;
  issues: PremiumReadinessIssue[];
  strengths: string[];
};

export type EvidenceGraphOut = {
  summary: {
    score: number;
    claim_count: number;
    supported: number;
    partial: number;
    unsupported: number;
    linked_source_count: number;
    numeric_fact_links: number;
    qualitative_fact_links: number;
  };
  nodes: {
    claim_id: string;
    origin: string;
    claim: string;
    status: "supported" | "partial" | "unsupported";
    score: number;
    missing: string[];
  }[];
};

export type ResearchPolicyOut = {
  domain: string;
  recommended_services: string[];
  required_source_families: string[];
  tier1_count: number;
  tier2_count: number;
  total_sources: number;
  missing_source_families: string[];
  issues: string[];
};

export type PagePlanOut = {
  summary: {
    page_count: number;
    exhibit_pages: number;
    mixed_pages: number;
    text_only_pages: number;
    pages_with_issues: number;
    status: "ready" | "needs_work" | "blocked";
  };
  global_issues: string[];
};

export type BenchmarkEvalOut = {
  profile_id?: string;
  profile_label?: string;
  score: number;
  passed: boolean;
  criteria?: { code: string; label: string; passed: boolean; observed: unknown; target: unknown }[];
  evidence_score: number;
  research_policy_passed: boolean;
  page_plan_status: string;
  issues: { code: string; severity: string; message: string }[];
};

export type ConsultingEvalOut = {
  score: number;
  passed: boolean;
  verdict: "publishable" | "not_publishable";
  dimensions: { dimension: string; score: number; passed: boolean; rationale: string }[];
  issues: { code: string; severity: string; message: string; recommendation: string }[];
};

export type EnterpriseQualityOut = {
  score: number;
  passed: boolean;
  verdict: "publishable" | "needs_work" | "blocked";
  issues: { code: string; severity: "critical" | "major" | "minor"; message: string; recommendation: string }[];
  research_policy: {
    domain: string;
    recommended_services: string[];
    requires_academic_retrieval: boolean;
    academic_retrieval_satisfied: boolean;
    issues: string[];
  };
  claim_audit: {
    claim_count: number;
    supported_claim_count: number;
    unsupported_claim_count: number;
    support_ratio: number;
    unsupported_claims: string[];
  };
  visual_intelligence: {
    visual_count: number;
    useful_visual_count: number;
    weak_visual_count: number;
  };
  report_structure: {
    narrative_chars: number;
    section_count: number;
    text_visual_balance: string;
  };
  execution_trace?: {
    total_cost_rub: number;
    source_report_count: number;
    followup_report_count: number;
    pending_job_count: number;
    running_job_count: number;
    services_used: string[];
    paper_search_used: boolean;
  } | null;
};

export type RendererStatusOut = {
  default_pdf_backend: string;
  backends: {
    backend: string;
    format: string;
    available: boolean;
    blockers: string[];
    qa?: string[];
    secrets_present?: Record<string, boolean>;
  }[];
  routing: Record<string, string>;
};

export async function getPremiumReadiness(id: string): Promise<PremiumReadiness> {
  if (STUB) {
    return {
      ready: false,
      score: 72,
      issues: [
        {
          code: "premium_insufficient_numeric_facts",
          severity: "major",
          message: "Demo report needs a deeper numeric evidence base.",
          recommendation: "Run targeted follow-up research before premium export.",
        },
      ],
      strengths: ["Report/deck delivery plan is present."],
    };
  }
  return jv4<PremiumReadiness>(`/api/v4/sessions/${encodeURIComponent(id)}/premium-readiness`);
}

export async function getEvidenceGraph(id: string): Promise<EvidenceGraphOut> {
  return jv4<EvidenceGraphOut>(`/api/v4/sessions/${encodeURIComponent(id)}/evidence-graph`);
}

export async function getResearchPolicy(id: string): Promise<ResearchPolicyOut> {
  return jv4<ResearchPolicyOut>(`/api/v4/sessions/${encodeURIComponent(id)}/research-policy`);
}

export async function getPagePlan(id: string): Promise<PagePlanOut> {
  return jv4<PagePlanOut>(`/api/v4/sessions/${encodeURIComponent(id)}/page-plan`);
}

export async function getBenchmarkEval(id: string): Promise<BenchmarkEvalOut> {
  return jv4<BenchmarkEvalOut>(`/api/v4/sessions/${encodeURIComponent(id)}/benchmark-eval`);
}

export async function getConsultingEval(id: string): Promise<ConsultingEvalOut> {
  return jv4<ConsultingEvalOut>(`/api/v4/sessions/${encodeURIComponent(id)}/consulting-eval`);
}

export async function getEnterpriseQuality(id: string): Promise<EnterpriseQualityOut> {
  return jv4<EnterpriseQualityOut>(`/api/v4/sessions/${encodeURIComponent(id)}/enterprise-quality`);
}

export async function getRendererStatus(): Promise<RendererStatusOut> {
  return jv4<RendererStatusOut>("/api/v4/renderers");
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

export type AutoDRService =
  | "valyu"
  | "tavily"
  | "exa"
  | "paper_search"
  | "perplexity"
  | "openai"
  | "claude"
  | "gemini";
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

export type AutoDepthLeadOut = {
  lead_id: string;
  kind: string;
  priority: string;
  rationale?: string;
  candidate_sources?: string[];
  linked_to?: string[];
  service: string;
  mode: string;
  task_id: string;
  cost_usd: number;
  cost_rub: number;
  eta_min_low: number;
  eta_min_high: number;
  prompt_preview: string;
};

export type PremiumRefineOut = {
  action:
    | "wait_for_followups"
    | "submitted_followups"
    | "synthesize_started"
    | "ready_or_blocked";
  message: string;
  pending_task_ids: string[];
  submitted_leads: AutoDepthLeadOut[];
  synthesize_task: LongTaskOut | null;
  analytic_closure: AnalyticClosureReport | null;
  premium_readiness: PremiumReadiness | null;
};

export type PremiumRefinementStatusOut = {
  recommended_action:
    | "run_analysis"
    | "wait_for_followups"
    | "wait_for_synthesis"
    | "submit_followups"
    | "synthesize"
    | "inspect_blockers"
    | "ready";
  message: string;
  pending_followup_task_ids: string[];
  running_synthesize_task_id: string | null;
  final_report_needs_followup_resynthesis: boolean;
  analytic_closure: AnalyticClosureReport | null;
  premium_readiness: PremiumReadiness | null;
  next_research_leads: Array<{
    lead_id: string;
    kind: string;
    priority: string;
    status: string;
    service: string;
    mode: string;
    candidate_sources: string[];
    linked_to: string[];
    rationale: string;
    prompt_preview: string;
  }>;
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
  partial_chars?: number | null;
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

export async function runAutoDepthLeads(
  id: string,
  opts?: {
    max_leads?: number;
    include_priority?: "must" | "should" | "could" | "all";
    service_override?: "valyu" | "tavily" | "exa" | "paper_search" | "openai" | "perplexity";
    mode_override?: string;
  },
): Promise<AutoDepthLeadOut[]> {
  if (STUB) return [];
  return jv4<AutoDepthLeadOut[]>(
    `/api/v4/sessions/${encodeURIComponent(id)}/auto-depth-leads`,
    {
      method: "POST",
      body: JSON.stringify({
        max_leads: opts?.max_leads ?? 3,
        include_priority: opts?.include_priority ?? "must",
        service_override: opts?.service_override ?? null,
        mode_override: opts?.mode_override ?? null,
      }),
    },
  );
}

export async function runPremiumRefine(
  id: string,
  opts?: {
    max_leads?: number;
    include_priority?: "must" | "should" | "could" | "all";
    service_override?: "valyu" | "tavily" | "exa" | "paper_search" | "openai" | "perplexity";
    mode_override?: string;
    model_preference?: "sonnet" | "opus";
    auto_synthesize?: boolean;
  },
): Promise<PremiumRefineOut> {
  if (STUB) {
    return {
      action: "ready_or_blocked",
      message: "Stub: premium refinement is not available.",
      pending_task_ids: [],
      submitted_leads: [],
      synthesize_task: null,
      analytic_closure: null,
      premium_readiness: null,
    };
  }
  return jv4<PremiumRefineOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/premium-refine`,
    {
      method: "POST",
      body: JSON.stringify({
        max_leads: opts?.max_leads ?? 3,
        include_priority: opts?.include_priority ?? "must",
        service_override: opts?.service_override ?? null,
        mode_override: opts?.mode_override ?? null,
        model_preference: opts?.model_preference ?? null,
        auto_synthesize: opts?.auto_synthesize ?? true,
      }),
    },
  );
}

export async function getPremiumRefinementStatus(id: string): Promise<PremiumRefinementStatusOut> {
  if (STUB) {
    return {
      recommended_action: "inspect_blockers",
      message: "Stub: inspect premium readiness blockers.",
      pending_followup_task_ids: [],
      running_synthesize_task_id: null,
      final_report_needs_followup_resynthesis: false,
      analytic_closure: null,
      premium_readiness: null,
      next_research_leads: [],
    };
  }
  return jv4<PremiumRefinementStatusOut>(
    `/api/v4/sessions/${encodeURIComponent(id)}/premium-refinement-status`,
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

export function exportUrl(
  id: string,
  format: string,
  opts: { allowDraft?: boolean; visualReviewApproved?: boolean } = {},
): string {
  const params = new URLSearchParams({ format });
  if (opts.allowDraft) params.set("allow_draft", "true");
  if (opts.visualReviewApproved) params.set("visual_review_approved", "true");
  return `${V4_BASE}/api/v4/sessions/${encodeURIComponent(id)}/export?${params.toString()}`;
}

export function nextResearchBriefUrl(id: string): string {
  return `${V4_BASE}/api/v4/sessions/${encodeURIComponent(id)}/next-research-brief`;
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
