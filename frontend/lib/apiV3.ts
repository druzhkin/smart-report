// v3 API client — speaks directly to smart-report-mvp-v3 FastAPI.
// Uses absolute URLs (bypasses next.config.mjs rewrite) so v3 and v2 can coexist.

const V3_BASE =
  process.env.NEXT_PUBLIC_V3_API_BASE || "http://localhost:8010";

export type V3Question = { text: string; id: string };

export type V3Finding = {
  claim: string;
  number: string | null;
  source_url: string;
  source_type: "academic" | "official" | "industry" | "media" | "other";
  verbatim_quote: string | null;
};

export type V3ScoutTask = {
  cell_id: string;
  query: string;
  target_sources: string[];
  strategy: "search" | "extract";
  target_urls: string[];
};

export type V3Cell = {
  id: string;
  domain: string;
  layer: string;
  scout_task: V3ScoutTask;
};

export type V3Matrix = {
  question_id: string;
  domains: string[];
  cells: V3Cell[];
};

export type V3Block = {
  cell_id: string;
  conclusion: string;
  strongest_number: string | null;
  gap: string | null;
  key_assumptions: string[];
  entities: string[];
  variables: string[];
  findings: V3Finding[];
};

export type V3CrossLink = {
  cell_a: string;
  cell_b: string;
  shared_variable: string;
  type: "paradox" | "causal_chain" | "shared_mechanism" | "unexpected_confirmation";
  insight: string;
  evidence_pointers: string[];
};

export type V3TopNumber = {
  value: string;
  context: string;
  source_url: string;
};

export type V3KeyTension = {
  tension: string;
  pole_a: string;
  pole_b: string;
};

export type V3ExecutiveSummary = {
  main_finding: string;
  top_numbers: V3TopNumber[];
  key_tensions: V3KeyTension[];
  open_questions: string[];
};

export type V3Report = {
  question: V3Question;
  matrix: V3Matrix;
  blocks: V3Block[];
  cross_links: V3CrossLink[];
  summary: V3ExecutiveSummary | null;
  metadata: Record<string, unknown>;
};

export type V3Event = {
  seq: number;
  phase:
    | "status"
    | "planner"
    | "scout"
    | "analyst"
    | "bisociator"
    | "summarizer"
    | "done"
    | "error";
  message: string;
  data: Record<string, unknown> | null;
  ts: number;
};

export type V3JobResponse = {
  id: string;
  status: "pending" | "running" | "done" | "error";
  error: string | null;
  report: V3Report | null;
  source: "memory" | "disk";
};

export type V3EventsResponse = {
  events: V3Event[];
  cursor: number;
  status: "pending" | "running" | "done" | "error";
  error: string | null;
};

export type V3JobSummary = {
  id: string;
  question: string;
  status: string;
  created_at: number;
  finished_at: number | null;
  error: string | null;
};

async function jv3<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${V3_BASE}${path}`, {
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

export const v3StartResearch = (question: string) =>
  jv3<{ id: string; status: string }>("/api/research", {
    method: "POST",
    body: JSON.stringify({ question, dry_run: false }),
  });

export const v3GetEvents = (id: string, since: number, timeout = 25) =>
  jv3<V3EventsResponse>(
    `/api/research/${id}/events?since=${since}&timeout=${timeout}`
  );

export const v3GetReport = (id: string) =>
  jv3<V3JobResponse>(`/api/research/${id}`);

export const v3ListReports = () => jv3<V3JobSummary[]>("/api/reports");

export const v3Health = () => jv3<{ status: string }>("/health");
