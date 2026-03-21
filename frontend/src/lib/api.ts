const API_BASE = "/api";

export interface CreateReportRequest {
  request: string;
  depth?: "light" | "standard" | "deep" | "exhaustive";
  output_formats?: string[];
}

export interface CreateReportResponse {
  session_id: string;
  estimated_time_minutes: number;
}

export interface PricingTier {
  depth: "light" | "standard" | "deep" | "exhaustive";
  label: string;
  tagline: string;
  description: string;
  estimated_time_minutes: number;
  public_price_usd: number;
  internal_budget_usd: number;
}

export interface ReportSection {
  title: string;
  content: string;
  order: number;
  sources: string[];
}

export interface ReportData {
  id: string;
  title: string;
  executive_summary: string;
  sections: ReportSection[];
  status: string;
  created_at: string;
  total_cost_usd: number;
  metadata: Record<string, unknown>;
}

export interface SessionMeta {
  session_id: string;
  status: string;
  cost_usd: number;
  tokens_used: number;
  report_urls: Record<string, string>;
  report: ReportData | null;
  created_at: string;
}

export interface SSEEvent {
  step: string;
  status: "started" | "done" | "error";
  message: string;
  cost_usd: number;
  tokens_used: number;
  timestamp: string;
  report_urls?: Record<string, string>;
}

export interface PushSubscriptionPayload {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
}

export async function createReport(
  payload: CreateReportRequest
): Promise<CreateReportResponse> {
  const res = await fetch(`${API_BASE}/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to create report: ${res.status}`);
  return res.json();
}

export async function getReportPricing(): Promise<PricingTier[]> {
  const res = await fetch(`${API_BASE}/reports/pricing`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to get pricing: ${res.status}`);
  const data = (await res.json()) as { tiers: PricingTier[] };
  return data.tiers;
}

export async function getReport(id: string): Promise<SessionMeta> {
  const res = await fetch(`${API_BASE}/reports/${id}`);
  if (!res.ok) throw new Error(`Failed to get report: ${res.status}`);
  return res.json();
}

export async function subscribeToReport(
  sessionId: string,
  subscription: PushSubscriptionPayload
): Promise<void> {
  const res = await fetch(`${API_BASE}/reports/${sessionId}/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription),
  });
  if (!res.ok) throw new Error(`Failed to subscribe: ${res.status}`);
}

export function getStreamUrl(id: string): string {
  return `${API_BASE}/reports/${id}/stream`;
}

export function getDownloadUrl(id: string, format: string): string {
  return `${API_BASE}/reports/${id}/download/${format}`;
}
