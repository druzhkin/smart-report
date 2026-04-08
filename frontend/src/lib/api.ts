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
  output_package: string[];
  max_budget_usd: number;
  answers: Record<string, string>;
  allow_perplexity_handoff: boolean;
  material_ids: string[];
}

export interface CreateReportRequest {
  request: string;
  depth?: "light" | "standard" | "deep" | "exhaustive";
  output_formats?: string[];
  perplexity_handoff_enabled?: boolean;
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
  handoff_prompts: PerplexityHandoffPrompt[];
}

export interface PricingTier {
  depth: "light" | "standard" | "deep" | "exhaustive";
  label: string;
  tagline: string;
  description: string;
  estimated_time_minutes: number;
  public_price_usd: number;
  internal_budget_usd: number;
  initial_research_branches: number;
  adjacent_research_branches: number;
  validation_research_branches: number;
  quality_max_rounds: number;
  observed_sample_size: number;
  observed_completed_runs: number;
  observed_released_runs: number;
  observed_median_cost_usd: number | null;
  observed_p90_cost_usd: number | null;
  observed_last_cost_usd: number | null;
  observed_release_rate: number | null;
}

export interface DepthProfile {
  name: string;
  label: string;
  description: string;
  research_depth: string;
  initial_research_branches: number;
  source_limit: number;
  adjacent_question_limit: number;
  adjacent_research_branches: number;
  validation_research_branches: number;
  stack_backfill_limit: number;
  quality_revision_target: number;
  quality_max_rounds: number;
  prefer_perplexity_writer: boolean;
}

export interface SpendEntry {
  entry_id: string;
  timestamp: string;
  category: string;
  stage: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  pricing_basis: string;
  notes: string;
}

export interface MaterialRecord {
  material_id: string;
  kind: string;
  title: string;
  filename: string;
  stored_filename: string;
  text_filename: string;
  media_type: string;
  size_bytes: number;
  text_length: number;
  excerpt: string;
  uploaded_at: string;
}

export interface PerplexityHandoffPrompt {
  prompt_id: string;
  stage: string;
  title: string;
  rationale: string;
  prompt: string;
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
  depth_profile?: DepthProfile | null;
  spend_breakdown?: SpendEntry[];
  materials?: MaterialRecord[];
  handoff_prompts?: PerplexityHandoffPrompt[];
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
  material_files?: string[];
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

export async function resumeReport(sessionId: string): Promise<{ session_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/reports/${sessionId}/resume`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to resume report: ${res.status}`);
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

export async function addTextMaterial(
  sessionId: string,
  payload: { title: string; content: string; kind?: "note" | "external_research" },
): Promise<{ run_id: string; material: MaterialRecord; materials: MaterialRecord[] }> {
  const res = await fetch(`${API_BASE}/reports/${sessionId}/materials/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to add text material: ${res.status}`);
  return res.json();
}

export async function uploadMaterial(
  sessionId: string,
  file: File,
  options?: { title?: string; kind?: "user_upload" | "external_research" },
): Promise<{ run_id: string; material: MaterialRecord; materials: MaterialRecord[] }> {
  const formData = new FormData();
  formData.append("file", file);
  if (options?.title) formData.append("title", options.title);
  if (options?.kind) formData.append("kind", options.kind);
  const res = await fetch(`${API_BASE}/reports/${sessionId}/materials/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`Failed to upload material: ${res.status}`);
  return res.json();
}

export function getStreamUrl(id: string): string {
  return `${API_BASE}/reports/${id}/stream`;
}

export function getDownloadUrl(id: string, format: string): string {
  return `${API_BASE}/reports/${id}/download/${format}`;
}
