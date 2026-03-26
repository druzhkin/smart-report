/**
 * E2E: Full report creation flow.
 *
 * Install Playwright before running:
 *   npx playwright install --with-deps
 *
 * Run:
 *   npx playwright test
 */
import { test, expect, Page, Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_SESSION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

const MOCK_REPORT = {
  id: MOCK_SESSION_ID,
  title: "Global AI Chip Market 2025-2030",
  executive_summary:
    "The AI chip market is projected to reach $500B by 2030, driven by LLM inference demand.",
  sections: [
    {
      title: "Market Overview",
      content: "The global AI chip market encompasses GPU, TPU, and custom ASICs...",
      order: 1,
      sources: ["https://example.com/report1", "https://example.com/report2"],
    },
    {
      title: "Key Players",
      content: "NVIDIA holds ~80% market share. AMD and Intel are closing the gap...",
      order: 2,
      sources: ["https://example.com/nvidia"],
    },
    {
      title: "Investment Implications",
      content: "Strong BUY signal for semiconductor ETFs based on forward P/E multiples...",
      order: 3,
      sources: [],
    },
  ],
  status: "completed",
  created_at: new Date().toISOString(),
  total_cost_usd: 1.23,
  metadata: { depth: "standard" },
};

const MOCK_SESSION_META = {
  session_id: MOCK_SESSION_ID,
  status: "completed",
  cost_usd: 1.23,
  tokens_used: 45000,
  report_urls: {
    pdf: `/api/reports/${MOCK_SESSION_ID}/download/pdf`,
    docx: `/api/reports/${MOCK_SESSION_ID}/download/docx`,
  },
  report: MOCK_REPORT,
  created_at: new Date().toISOString(),
};

const MOCK_PRICING = {
  tiers: [
    {
      depth: "light",
      label: "Light",
      tagline: "Quick overview",
      description: "Fast surface-level scan",
      estimated_time_minutes: 3,
      public_price_usd: 0.5,
      internal_budget_usd: 0.5,
    },
    {
      depth: "standard",
      label: "Standard",
      tagline: "Balanced",
      description: "Balanced market analysis",
      estimated_time_minutes: 8,
      public_price_usd: 2,
      internal_budget_usd: 2,
    },
  ],
};

// SSE events that simulate a completed pipeline run
const SSE_EVENTS = [
  { step: "intake", status: "done", message: "Intake & Analysis", cost_usd: 0.01, tokens_used: 500, timestamp: new Date().toISOString() },
  { step: "research", status: "done", message: "Research", cost_usd: 0.50, tokens_used: 20000, timestamp: new Date().toISOString() },
  { step: "summarization", status: "done", message: "Summarization", cost_usd: 0.20, tokens_used: 8000, timestamp: new Date().toISOString() },
  { step: "render_and_present", status: "done", message: "Rendering", cost_usd: 0.30, tokens_used: 10000, timestamp: new Date().toISOString() },
  { step: "qa", status: "done", message: "Quality Assurance", cost_usd: 0.22, tokens_used: 6500, timestamp: new Date().toISOString() },
  {
    step: "complete",
    status: "done",
    message: "Report generation complete",
    cost_usd: 1.23,
    tokens_used: 45000,
    timestamp: new Date().toISOString(),
    report_urls: {
      pdf: `/api/reports/${MOCK_SESSION_ID}/download/pdf`,
      docx: `/api/reports/${MOCK_SESSION_ID}/download/docx`,
    },
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function mockBackendRoutes(page: Page) {
  // POST /api/reports в†’ create session
  await page.route("**/api/reports", async (route: Route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: MOCK_SESSION_ID,
          estimated_time_minutes: 8,
        }),
      });
    } else if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    } else {
      await route.continue();
    }
  });

  await page.route("**/api/reports/pricing", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_PRICING),
    });
  });

  // GET /api/reports/:id в†’ session meta
  await page.route(
    `**/api/reports/${MOCK_SESSION_ID}`,
    async (route: Route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_SESSION_META),
        });
      } else {
        await route.continue();
      }
    }
  );

  // GET /api/reports/:id/stream в†’ SSE
  await page.route(
    `**/api/reports/${MOCK_SESSION_ID}/stream`,
    async (route: Route) => {
      const sseBody = SSE_EVENTS.map((ev) => `data: ${JSON.stringify(ev)}\n\n`).join("");
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: {
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        },
        body: sseBody,
      });
    }
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Report creation flow", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackendRoutes(page);
  });

  test("step 1: navigate to /app/new and enter request", async ({ page }) => {
    await page.goto("/app/new");

    // Page renders step 1 heading
    await expect(page.getByRole("heading", { name: /what should we research/i })).toBeVisible();

    // Textarea is present and accepts input
    const textarea = page.getByPlaceholder(/analyze the global ai chip/i);
    await expect(textarea).toBeVisible();
    await textarea.fill(
      "Analyze the global AI chip market opportunity for 2025-2030, including competitive landscape and investment implications."
    );

    // Character count updates
    await expect(page.getByText(/\d+ characters/)).toBeVisible();

    // Select "Deep" research depth
    await page.getByRole("button", { name: /deep/i }).click();

    // Uncheck DOCX, keep PDF
    const docxCheckbox = page.locator("label").filter({ hasText: /docx/i }).locator("button");
    if (await docxCheckbox.isChecked()) {
      await docxCheckbox.click();
    }

    // Continue button enabled once query is non-empty
    const continueBtn = page.getByRole("button", { name: /continue/i });
    await expect(continueBtn).toBeEnabled();
    await continueBtn.click();

    // Step 2 heading visible
    await expect(page.getByRole("heading", { name: /a few questions/i })).toBeVisible();
  });

  test("step 2: answer clarifying questions and proceed", async ({ page }) => {
    await page.goto("/app/new");

    // Fill step 1
    await page.getByPlaceholder(/analyze the global ai chip/i).fill("AI chip market analysis 2025-2030");
    await page.getByRole("button", { name: /continue/i }).click();

    // Step 2: clarifying questions
    await expect(page.getByText(/clarifying questions/i)).toBeVisible();
    await expect(page.getByText(/\(1\/5\)/i)).toBeVisible();

    // Answer first question
    const answerInput = page.getByPlaceholder(/your answer/i);
    await answerInput.fill("Enterprise and institutional investors");

    // Advance to next question
    await page.getByRole("button", { name: /^next$/i }).click();
    await expect(page.getByText(/2\//)).toBeVisible();

    // Skip Q1в†’Q2в†’Q3в†’Q4, then "Skip & Generate" on Q4 submits
    for (let i = 0; i < 4; i++) {
      await page.getByRole("button", { name: /skip/i }).click();
    }

    // Step 3: progress view
    await expect(
      page.getByRole("heading", { name: /generating report|report ready/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("step 2: skip all questions directly", async ({ page }) => {
    await page.goto("/app/new");

    await page.getByPlaceholder(/analyze the global ai chip/i).fill("Quick skip test query");
    await page.getByRole("button", { name: /continue/i }).click();

    await expect(page.getByText(/clarifying questions/i)).toBeVisible();

    // Skip all without answering
    for (let i = 0; i < 5; i++) {
      const skipBtn = page.getByRole("button", { name: /skip/i });
      if (await skipBtn.isVisible()) {
        await skipBtn.click();
      } else {
        break;
      }
    }

    // Should reach step 3
    await expect(
      page.getByRole("heading", { name: /generating report|report ready/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("step 3: progress screen shows pipeline steps", async ({ page }) => {
    await page.goto("/app/new");

    await page.getByPlaceholder(/analyze the global ai chip/i).fill("Progress screen test");
    await page.getByRole("button", { name: /continue/i }).click();
    // Skip Q0в†’Q1в†’Q2в†’Q3в†’Q4 (4 advances) then submit on Q4 = 5 clicks of /skip/
    for (let i = 0; i < 5; i++) {
      await page.getByRole("button", { name: /skip/i }).click();
    }

    // Progress card is visible
    await expect(page.locator(".space-y-6").first()).toBeVisible();

    await expect(page.getByText(/Pipeline Progress/i)).toBeVisible();
  });

  test("report view shows all 4 tabs", async ({ page }) => {
    // Navigate directly to a completed report page
    await page.goto(`/app/reports/${MOCK_SESSION_ID}`);

    // Wait for report to load (polls via useReport hook)
    await expect(page.getByRole("heading", { level: 1, name: /Global AI Chip Market/i })).toBeVisible({
      timeout: 15_000,
    });

    // All 4 tab triggers present
    await expect(page.getByRole("tab", { name: /document/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /slides/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /data/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /sources/i })).toBeVisible();
  });

  test("report document tab shows executive summary", async ({ page }) => {
    await page.goto(`/app/reports/${MOCK_SESSION_ID}`);

    await expect(page.getByRole("heading", { level: 1, name: /Global AI Chip Market/i })).toBeVisible({
      timeout: 15_000,
    });

    // Executive summary visible
    await expect(page.getByText(/executive summary/i).first()).toBeVisible();
    await expect(page.getByText(/projected to reach \$500B/i)).toBeVisible();

    await expect(page.getByRole("link", { name: /^PDF$/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^DOCX$/i })).toBeVisible();
  });

  test("report slides tab renders", async ({ page }) => {
    await page.goto(`/app/reports/${MOCK_SESSION_ID}`);
    await expect(page.getByRole("heading", { level: 1, name: /Global AI Chip Market/i })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole("tab", { name: /slides/i }).click();
    await expect(page.getByText(/Презентация|Presentation/i)).toBeVisible();
  });

  test("report data tab renders chart section", async ({ page }) => {
    await page.goto(`/app/reports/${MOCK_SESSION_ID}`);
    await expect(page.getByRole("heading", { level: 1, name: /Global AI Chip Market/i })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole("tab", { name: /data/i }).click();
    await expect(page.getByText(/Metadata|Orchestration Trace/i)).toBeVisible();
  });

  test("report sources tab lists unique sources", async ({ page }) => {
    await page.goto(`/app/reports/${MOCK_SESSION_ID}`);
    await expect(page.getByRole("heading", { level: 1, name: /Global AI Chip Market/i })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole("tab", { name: /sources/i }).click();

    await expect(page.getByRole("link", { name: /example\.com\/report1/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /example\.com\/nvidia/i })).toBeVisible();
  });

  test("download buttons present in document tab", async ({ page }) => {
    await page.goto(`/app/reports/${MOCK_SESSION_ID}`);
    await expect(page.getByRole("heading", { level: 1, name: /Global AI Chip Market/i })).toBeVisible({
      timeout: 15_000,
    });

    // PDF, DOCX, HTML download buttons
    await expect(page.getByRole("link", { name: /^pdf$/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^docx$/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^html$/i })).toBeVisible();
  });

  test("back button navigates to /app", async ({ page }) => {
    await page.goto(`/app/reports/${MOCK_SESSION_ID}`);
    await expect(page.getByRole("heading", { level: 1, name: /Global AI Chip Market/i })).toBeVisible({
      timeout: 15_000,
    });

    // Use main content area to avoid matching the sidebar Dashboard link
    await page.locator("main").locator('a[href="/app"]').click();
    await expect(page).toHaveURL(/\/app$/);
  });
});

