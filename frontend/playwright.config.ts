import { defineConfig, devices } from "@playwright/test";

process.env.NO_PROXY = [process.env.NO_PROXY, "127.0.0.1", "localhost"]
  .filter(Boolean)
  .join(",");
process.env.no_proxy = [process.env.no_proxy, "127.0.0.1", "localhost"]
  .filter(Boolean)
  .join(",");

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3027",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1200 } },
    },
  ],
  webServer: {
    command: "npm run dev -- -H 127.0.0.1 -p 3027",
    url: "http://127.0.0.1:3027/v4/chat",
    reuseExistingServer: true,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_V4_STUB: "1",
    },
  },
});
