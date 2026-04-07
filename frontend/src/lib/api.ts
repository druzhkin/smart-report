const API_BASE = "/api";

export interface RequestSpec {
  request_id: string;
  original_query: string;
  language: string;
  report_type: string;
  goal: string;
  subject: string;
  decision_context: string;
  target_audience: string;
  time_horizon: string;
  geography: string;
  quality_target: string;
  budget_tier: string;
  missing_critical_fields: string[];
}

export interface ClarificationQuestion {
  question_id: string;
  field: string;
  prompt: string;
  rationale: string;
  placeholder?: string;
  required: boolean;
}

export interface ClarificationPack {
  run_id: string;
  request_spec: RequestSpec;
  questions: ClarificationQuestion[];
}

export interface TaskSpec {
  task_id: string;
  success_criteria: string[];
  evaluation_dimensions: string[];
  constraints: string[];
  must_cover_questions: string[];
  max_budget_usd: number;
  answers: Record<string, string>;
}

export interface CreateReportRequest {
  request: string;
  depth?: "light" | "standard" | "deep" | "exhaustive";
  output_formats?: string[];
}

export interface CreateReportResponse {
  session_id: string;
  estimated_time_minutes: number;
  request_spec: RequestSpec | null;
  status: string;
}

export interface ScopeReportRequest {
  answers: Record<string, string>;
}

export interface ScopeReportResponse {
  session_id: string;
  status: string;
  task_spec: TaskSpec;
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

export interface AnalysisBrief {
  title: string;
  executive_summary: string;
  decision_context: string;
  recommendation_posture: string;
  key_findings: string[];
  key_risks: string[];
  limitations: string[];
  uncertainty_statement: string;
  chart_candidates: string[];
}

export interface CoverageQuestionStatus {
  question_id: string;
  question: string;
  evidence_count: number;
  source_count: number;
  status: string;
}

export interface CoverageReport {
  total_questions: number;
  covered_questions: number;
  coverage_ratio: number;
  strong_source_ratio: number;
  contradiction_count: number;
  questions: CoverageQuestionStatus[];
  gaps: string[];
}

export interface AuditSummary {
  release_status: string;
  checks_passed: number;
  checks_failed: number;
  failures: string[];
  warnings: string[];
}

export interface EvidenceRecord {
  evidence_id: string;
  question_id: string;
  source_id: string;
  claim: string;
  snippet: string;
  confidence: number;
  extraction_method: string;
  supports: string[];
}

export interface ClaimRecord {
  claim_id: string;
  statement: string;
  question_id: string;
  supporting_evidence_ids: string[];
  source_ids: string[];
  confidence: number;
  contradiction_notes: string[];
  recommendation_safe: boolean;
}

export interface SourceLedgerEntry {
  source_id: string;
  url: string;
  title: string;
  domain: string;
  source_type: string;
  publisher: string;
  published_at: string;
  reliability_score: number;
  selection_reason: string;
  question_links: string[];
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
  title?: string;
  request_spec?: RequestSpec | null;
  task_spec?: TaskSpec | null;
  analysis_brief?: AnalysisBrief | null;
  coverage_report?: CoverageReport | null;
  audit_summary?: AuditSummary | null;
}

export interface EvidenceResponse {
  run_id: string;
  claim_table: ClaimRecord[];
  evidence_ledger: EvidenceRecord[];
  coverage_report: CoverageReport;
}

export interface SourcesResponse {
  run_id: string;
  sources: SourceLedgerEntry[];
}

export interface ArtifactsResponse {
  run_id: string;
  artifacts: string[];
  package_files: string[];
}

export interface SSEEvent {
  event_id?: string;
  step: string;
  status: "started" | "done" | "error";
  message: string;
  cost_usd: number;
  tokens_used: number;
  timestamp: string;
  report_urls?: Record<string, string>;
}

export async function createReport(payload: CreateReportRequest): Promise<CreateReportResponse> {
  const res = await fetch(`${API_BASE}/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to create report: ${res.status}`);
  return res.json();
}

export async function getClarificationPack(sessionId: string): Promise<ClarificationPack> {
  const res = await fetch(`${API_BASE}/reports/${sessionId}/clarify`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to load clarification pack: ${res.status}`);
  return res.json();
}

export async function getClarifyingQuestions(payload: CreateReportRequest): Promise<ClarificationPack> {
  const res = await fetch(`${API_BASE}/reports/clarify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to get clarifying questions: ${res.status}`);
  return res.json();
}

export async function scopeReport(sessionId: string, payload: ScopeReportRequest): Promise<ScopeReportResponse> {
  const res = await fetch(`${API_BASE}/reports/${sessionId}/scope`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to scope report: ${res.status}`);
  return res.json();
}

export async function getReportPricing(): Promise<PricingTier[]> {
  const res = await fetch(`${API_BASE}/reports/pricing`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to get pricing: ${res.status}`);
  const data = (await res.json()) as { tiers: PricingTier[] };
  return data.tiers;
}

export async function getReport(id: string): Promise<SessionMeta> {
  const res = await fetch(`${API_BASE}/reports/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to get report: ${res.status}`);
  return res.json();
}

export async function getReportEvidence(id: string): Promise<EvidenceResponse> {
  const res = await fetch(`${API_BASE}/reports/${id}/evidence`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to get evidence: ${res.status}`);
  return res.json();
}

export async function getReportSources(id: string): Promise<SourcesResponse> {
  const res = await fetch(`${API_BASE}/reports/${id}/sources`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to get sources: ${res.status}`);
  return res.json();
}

export async function getReportArtifacts(id: string): Promise<ArtifactsResponse> {
  const res = await fetch(`${API_BASE}/reports/${id}/artifacts`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to get artifacts: ${res.status}`);
  return res.json();
}

export function getStreamUrl(id: string): string {
  return `${API_BASE}/reports/${id}/stream`;
}

export function getDownloadUrl(id: string, format: string): string {
  return `${API_BASE}/reports/${id}/download/${format}`;
}
