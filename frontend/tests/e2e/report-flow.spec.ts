import { expect, test, type Page, type Route } from "@playwright/test";

const MOCK_SESSION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

const MOCK_REQUEST_SPEC = {
  request_id: "req-1",
  original_query: "Evaluate LLM observability platforms for an enterprise document workflow product.",
  language: "en",
  report_type: "vendor_evaluation",
  goal: "Produce an evidence-backed analytical report for a real decision.",
  subject: "LLM observability platforms",
  decision_context: "Support a concrete vendor or platform choice.",
  target_audience: "operator",
  time_horizon: "current",
  geography: "global",
  quality_target: "decision-grade",
  budget_tier: "standard",
  missing_critical_fields: [],
};

const MOCK_CLARIFICATION_PACK = {
  run_id: MOCK_SESSION_ID,
  request_spec: MOCK_REQUEST_SPEC,
  questions: [
    {
      question_id: "decision-context",
      field: "decision_context",
      prompt: "What concrete decision should this report support?",
      rationale: "The report should optimize for a decision, not generic research.",
      placeholder: "Choose a platform for a six-month rollout",
      required: true,
    },
    {
      question_id: "dimensions",
      field: "evaluation_dimensions",
      prompt: "Which evaluation dimensions matter most?",
      rationale: "Dimensions should be explicit before research planning.",
      placeholder: "trace depth, evaluation tooling, self-hosting, governance",
      required: true,
    },
    {
      question_id: "geography",
      field: "geography",
      prompt: "Should this stay global or focus on a specific region?",
      rationale: "Geography changes source targeting and freshness requirements.",
      placeholder: "global / US / Europe",
      required: false,
    },
    {
      question_id: "budget",
      field: "budget",
      prompt: "Are there hard constraints on cost, licensing, or privacy?",
      rationale: "Constraints belong in TaskSpec, not buried in free text.",
      placeholder: "open-source preferred, privacy-sensitive",
      required: false,
    },
  ],
};

const MOCK_TASK_SPEC = {
  task_id: "task-1",
  success_criteria: [
    "Every recommendation must be tied to evidence.",
    "Weak-source discovery hints cannot dominate the recommendation.",
  ],
  evaluation_dimensions: ["trace depth", "evaluation tooling", "self-hosting", "governance"],
  constraints: ["privacy-sensitive deployment"],
  must_cover_questions: [
    "Which platform is strongest for traceability and evals?",
    "Which options fit privacy-sensitive deployments?",
    "Which tools are best for fast operator debugging?",
  ],
  max_budget_usd: 2,
  answers: {
    "decision-context": "Choose an observability stack for a privacy-sensitive launch.",
  },
};

const MOCK_ANALYSIS_BRIEF = {
  title: "LLM observability platforms: Decision Brief",
  executive_summary:
    "LLM observability platforms: coverage 3/3 primary questions, 4 recommendation-safe claims, contradiction count 0.",
  decision_context: "Choose an observability stack for a privacy-sensitive launch.",
  recommendation_posture: "evidence_backed_recommendations_allowed",
  key_findings: [
    "LangSmith is strongest when trace inspection and regression measurement matter. [Evidence: E-1, E-2]",
    "Langfuse is the most attractive self-hosting path in the public source set. [Evidence: E-3, E-4]",
  ],
  key_risks: ["Buyer still needs workload-specific validation."],
  limitations: ["No workload-specific benchmark from the buyer was provided."],
  uncertainty_statement: "Evidence quality is sufficient for a directional recommendation, but local validation is still advised.",
  chart_candidates: ["evidence_coverage"],
};

const MOCK_COVERAGE_REPORT = {
  total_questions: 3,
  covered_questions: 3,
  coverage_ratio: 1,
  strong_source_ratio: 1,
  contradiction_count: 0,
  questions: [
    {
      question_id: "q1",
      question: "Which platform is strongest for traceability and evals?",
      evidence_count: 3,
      source_count: 2,
      status: "covered",
    },
    {
      question_id: "q2",
      question: "Which options fit privacy-sensitive deployments?",
      evidence_count: 2,
      source_count: 2,
      status: "covered",
    },
    {
      question_id: "q3",
      question: "Which tools are best for fast operator debugging?",
      evidence_count: 2,
      source_count: 2,
      status: "covered",
    },
  ],
  gaps: [],
};

const MOCK_AUDIT_SUMMARY = {
  release_status: "released",
  checks_passed: 7,
  checks_failed: 0,
  failures: [],
  warnings: [],
};

const MOCK_REPORT = {
  id: MOCK_SESSION_ID,
  title: MOCK_ANALYSIS_BRIEF.title,
  executive_summary: MOCK_ANALYSIS_BRIEF.executive_summary,
  sections: [
    {
      title: "Decision Context",
      content: MOCK_ANALYSIS_BRIEF.decision_context,
      order: 1,
      sources: ["https://www.langchain.com/langsmith"],
    },
    {
      title: "Key Findings",
      content: MOCK_ANALYSIS_BRIEF.key_findings.join("\n"),
      order: 2,
      sources: ["https://langfuse.com/docs", "https://www.helicone.ai/docs"],
    },
  ],
  status: "completed",
  created_at: new Date().toISOString(),
  total_cost_usd: 0,
  metadata: {
    analysis_brief: MOCK_ANALYSIS_BRIEF,
    coverage_report: MOCK_COVERAGE_REPORT,
    audit_summary: MOCK_AUDIT_SUMMARY,
  },
};

const MOCK_SESSION_META = {
  session_id: MOCK_SESSION_ID,
  status: "completed",
  cost_usd: 0,
  tokens_used: 0,
  report_urls: {
    html: `/api/reports/${MOCK_SESSION_ID}/download/html`,
    pdf: `/api/reports/${MOCK_SESSION_ID}/download/pdf`,
    docx: `/api/reports/${MOCK_SESSION_ID}/download/docx`,
    json: `/api/reports/${MOCK_SESSION_ID}/download/json`,
  },
  report: MOCK_REPORT,
  created_at: new Date().toISOString(),
  title: MOCK_ANALYSIS_BRIEF.title,
  request_spec: MOCK_REQUEST_SPEC,
  task_spec: MOCK_TASK_SPEC,
  analysis_brief: MOCK_ANALYSIS_BRIEF,
  coverage_report: MOCK_COVERAGE_REPORT,
  audit_summary: MOCK_AUDIT_SUMMARY,
};

const MOCK_EVIDENCE = {
  run_id: MOCK_SESSION_ID,
  claim_table: [
    {
      claim_id: "C-01",
      statement: "LangSmith focuses on trace inspection, dataset-backed evaluation, prompt comparisons, and production monitoring.",
      question_id: "q1",
      supporting_evidence_ids: ["E-01", "E-02"],
      source_ids: ["S-01"],
      confidence: 0.93,
      contradiction_notes: [],
      recommendation_safe: true,
    },
  ],
  evidence_ledger: [
    {
      evidence_id: "E-01",
      question_id: "q1",
      source_id: "S-01",
      claim: "LangSmith focuses on trace inspection, dataset-backed evaluation, prompt comparisons, and production monitoring.",
      snippet: "LangSmith focuses on trace inspection, dataset-backed evaluation, prompt comparisons, and production monitoring.",
      confidence: 0.93,
      extraction_method: "heuristic",
      supports: [],
    },
  ],
  coverage_report: MOCK_COVERAGE_REPORT,
};

const MOCK_SOURCES = {
  run_id: MOCK_SESSION_ID,
  sources: [
    {
      source_id: "S-01",
      url: "https://www.langchain.com/langsmith",
      title: "LangSmith overview",
      domain: "langchain.com",
      source_type: "vendor_page",
      publisher: "LangChain",
      published_at: "2025-01-14",
      reliability_score: 0.85,
      selection_reason: "Matched search query for q1",
      question_links: ["q1"],
    },
    {
      source_id: "S-02",
      url: "https://langfuse.com/docs",
      title: "Langfuse documentation",
      domain: "langfuse.com",
      source_type: "official_documentation",
      publisher: "Langfuse",
      published_at: "2025-01-10",
      reliability_score: 0.95,
      selection_reason: "Matched search query for q2",
      question_links: ["q2"],
    },
  ],
};

const MOCK_ARTIFACTS = {
  run_id: MOCK_SESSION_ID,
  artifacts: ["request_spec.json", "task_spec.json", "claim_table.json", "coverage_report.json"],
  package_files: ["report.md", "report.html", "sources.json", "claim_table.json", "analysis_brief.json"],
};

const SSE_EVENTS = [
  { step: "planning", status: "started", message: "Building research plan", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  { step: "planning", status: "done", message: "Research plan ready", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  { step: "search", status: "started", message: "Selecting sources", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  { step: "search", status: "done", message: "Selected 3 sources", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  { step: "evidence", status: "started", message: "Building evidence ledger", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  { step: "evidence", status: "done", message: "Built 4 claims", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  { step: "report", status: "started", message: "Rendering report", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  { step: "report", status: "done", message: "Report package compiled", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  { step: "audit", status: "started", message: "Running release gate", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  { step: "audit", status: "done", message: "released", cost_usd: 0, tokens_used: 0, timestamp: new Date().toISOString() },
  {
    step: "complete",
    status: "done",
    message: "Report ready",
    cost_usd: 0,
    tokens_used: 0,
    timestamp: new Date().toISOString(),
    report_urls: MOCK_SESSION_META.report_urls,
  },
];

async function mockBackendRoutes(page: Page) {
  let scoped = false;

  await page.route("**/api/reports/pricing", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        tiers: [
          {
            depth: "standard",
            label: "Standard",
            tagline: "Balanced research",
            description: "Mainstream choice for most business questions and decision memos.",
            estimated_time_minutes: 8,
            public_price_usd: 2,
            internal_budget_usd: 2,
          },
        ],
      }),
    });
  });

  await page.route("**/api/reports", async (route: Route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: MOCK_SESSION_ID,
          estimated_time_minutes: 8,
          request_spec: MOCK_REQUEST_SPEC,
          status: "awaiting_scope",
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(`**/api/reports/${MOCK_SESSION_ID}/clarify`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_CLARIFICATION_PACK),
    });
  });

  await page.route(`**/api/reports/${MOCK_SESSION_ID}/scope`, async (route: Route) => {
    scoped = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session_id: MOCK_SESSION_ID,
        status: "running",
        task_spec: MOCK_TASK_SPEC,
      }),
    });
  });

  await page.route(`**/api/reports/${MOCK_SESSION_ID}/stream`, async (route: Route) => {
    const sseBody = SSE_EVENTS.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: {
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
      body: sseBody,
    });
  });

  await page.route(`**/api/reports/${MOCK_SESSION_ID}/evidence`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_EVIDENCE),
    });
  });

  await page.route(`**/api/reports/${MOCK_SESSION_ID}/sources`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_SOURCES),
    });
  });

  await page.route(`**/api/reports/${MOCK_SESSION_ID}/artifacts`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_ARTIFACTS),
    });
  });

  await page.route(`**/api/reports/${MOCK_SESSION_ID}/download/*`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/plain",
      body: "mock-file",
    });
  });

  await page.route(`**/api/reports/${MOCK_SESSION_ID}`, async (route: Route) => {
    const payload = scoped ? MOCK_SESSION_META : { ...MOCK_SESSION_META, status: "awaiting_scope", report: null };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}

test.describe("Smart Report v2 flow", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackendRoutes(page);
  });

  test("creates a report through task, scope, questions, evidence, and report", async ({ page }) => {
    await page.goto("/app/new");

    await expect(page.getByRole("heading", { name: "Task" })).toBeVisible();
    await page
      .getByPlaceholder(/Evaluate LLM observability platforms/i)
      .fill("Evaluate LLM observability platforms for an enterprise document workflow product.");
    await page.getByRole("button", { name: /Create scope draft/i }).click();

    await expect(page.getByRole("heading", { level: 1, name: "Scope" })).toBeVisible();
    await expect(page.getByText(/LLM observability platforms/i)).toBeVisible();
    await page.getByRole("button", { name: /Continue to questions/i }).click();

    await expect(page.getByRole("heading", { level: 1, name: "Questions" })).toBeVisible();
    await page.getByPlaceholder(/Choose a platform for a six-month rollout/i).fill(
      "Choose an observability stack for a privacy-sensitive launch.",
    );
    await page.getByRole("button", { name: /^Next$/i }).click();
    await page.getByRole("button", { name: /^Skip$/i }).click();
    await page.getByRole("button", { name: /^Skip$/i }).click();
    await page.getByRole("button", { name: /Skip & Start/i }).click();

    await expect(page.getByRole("heading", { name: /Evidence|Report/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Open report workspace/i })).toBeVisible({ timeout: 10_000 });
    await page.getByRole("link", { name: /Open report workspace/i }).click();

    await expect(
      page.getByRole("heading", { level: 1, name: /LLM observability platforms: Decision Brief/i }),
    ).toBeVisible();
    await expect(page.getByRole("tab", { name: /Brief/i })).toBeVisible();
  });

  test("shows evidence-first tabs on the report page", async ({ page }) => {
    await page.goto(`/app/reports/${MOCK_SESSION_ID}`);

    await expect(
      page.getByRole("heading", { level: 1, name: /LLM observability platforms: Decision Brief/i }),
    ).toBeVisible();
    await expect(page.getByRole("tab", { name: /Brief/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /^Report$/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Evidence/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Sources/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Gaps & Risks/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Data/i })).toBeVisible();

    await page.getByRole("tab", { name: /Evidence/i }).click();
    await expect(page.getByText(/LangSmith focuses on trace inspection/i)).toBeVisible();

    await page.getByRole("tab", { name: /Sources/i }).click();
    await expect(page.getByRole("link", { name: /LangSmith overview/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Langfuse documentation/i })).toBeVisible();
  });
});
