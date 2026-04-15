export type Finding = {
  claim: string;
  source: string;
  source_type: string;
  has_numbers: boolean;
  entities: string[];
};

export type Block = {
  cell: string;
  summary: string;
  findings: Finding[];
  gaps: string[];
  key_entities: string[];
  assumptions: string[];
};

export type Connection = {
  domains: string[];
  shared_entity: string;
  nature: string;
  description: string;
  strength: string;
  anchors: string[];
  novelty?: string | null;
};

export type BlockHeader = {
  cell: string;
  one_liner: string;
  strongest_number: string;
  main_gap: string;
  priority: "high" | "medium" | "low" | string;
  score_novelty: number;
  score_concreteness: number;
  score_applicability: number;
};

export type Layer = { name: string; description: string };
export type Domain = { name: string; rationale: string; layers: Layer[] };
export type Matrix = { goal: string; domains: Domain[]; cell_plans: any[] };

export type ExecutiveSummary = {
  goal_restate: string;
  matrix_table_md: string;
  top_findings: { headline: string; block_cell: string }[];
  top_connections: { headline: string; domains: string[] }[];
  key_gaps: string[];
};

export type Report = {
  goal: string;
  matrix: Matrix;
  blocks: Block[];
  connections: Connection[];
  exec_summary: ExecutiveSummary | null;
  block_headers: BlockHeader[];
};

export type ReportListItem = {
  id: string;
  goal: string;
  created_at: string;
  blocks_count: number;
  connections_count: number;
  top_findings_preview: string[];
};

async function j<T = any>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
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

export type Depth = "light" | "standard" | "deep" | "exhaustive";

export const startResearch = (goal: string, depth: Depth = "standard") =>
  j<{ id: string; status: string; depth?: Depth }>("/api/research", {
    method: "POST",
    body: JSON.stringify({ goal, depth }),
  });

export const getReport = (id: string) =>
  j<{
    id: string;
    status: string;
    error: string | null;
    report: Report;
    dismissed: string[];
  }>(`/api/research/${id}`);

export const listReports = () => j<ReportListItem[]>("/api/reports");

export const deepenCell = (id: string, cell: string, focus: string) =>
  j(`/api/research/${id}/deepen`, {
    method: "POST",
    body: JSON.stringify({ cell, focus }),
  });

export const addDomain = (
  id: string,
  payload: { name?: string; layers?: string[]; freetext?: string }
) =>
  j(`/api/research/${id}/add-domain`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const connectBlocks = (id: string, a: string, b: string) =>
  j(`/api/research/${id}/connect`, {
    method: "POST",
    body: JSON.stringify({ block_a_cell: a, block_b_cell: b }),
  });

export const dismissCell = (id: string, cell: string) =>
  j(`/api/research/${id}/dismiss`, {
    method: "POST",
    body: JSON.stringify({ cell }),
  });

export const exportUrl = (id: string, fmt: "docx" | "pptx" | "md" | "json") =>
  `/api/research/${id}/export/${fmt}`;
