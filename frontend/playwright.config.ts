import { defineConfig, devices } from "@playwright/test"

// Ports apart from the dev servers' (Vite :5173, uvicorn :8000), so a run
// never reuses an app you have open. They must match
// backend/tests/e2e/server.py.
const APP_URL = "http://localhost:5174"
const API_URL = "http://127.0.0.1:8001"

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: APP_URL,
    trace: "retain-on-failure",
  },
  // Chromium only: the session cookies are Secure, and it's the browser that
  // treats http://localhost as a secure context for them.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // The real API on a throwaway database, with fake OAuth providers.
      command: "uv run python -m tests.e2e.server",
      cwd: "../backend",
      url: `${API_URL}/health/live`,
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: "pnpm exec vite --port 5174 --strictPort",
      url: APP_URL,
      env: { API_PROXY_TARGET: API_URL },
      reuseExistingServer: false,
    },
  ],
})
