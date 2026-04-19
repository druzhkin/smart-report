// v4 API client — talks to the v3 FastAPI (/api/v4/* endpoints).
// Stub mode: set NEXT_PUBLIC_V4_STUB=1 to walk the UI without a backend.

const V4_BASE =
  process.env.NEXT_PUBLIC_V4_API_BASE ||
  process.env.NEXT_PUBLIC_V3_API_BASE ||
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
  const body = modelPreference ? JSON.stringify({ model_preference: modelPreference }) : undefined;
  return jv4<AnalysisOutput>(
    `/api/v4/sessions/${encodeURIComponent(id)}/analyze`,
    { method: "POST", body }
  );
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
  const body = modelPreference ? JSON.stringify({ model_preference: modelPreference }) : undefined;
  return jv4<FinalReport>(
    `/api/v4/sessions/${encodeURIComponent(id)}/synthesize`,
    { method: "POST", body }
  );
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

export function exportUrl(id: string, format: string): string {
  return `${V4_BASE}/api/v4/sessions/${encodeURIComponent(id)}/export?format=${encodeURIComponent(format)}`;
}

export const STUB_ENABLED = STUB;
