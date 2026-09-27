import { defineConfig, devices } from "@playwright/test";

/**
 * E2E specs live at apps/web/tests/e2e/ rather than the monorepo root
 * tests/e2e/ that Plan.md §3 sketches — Node's module resolution needs the
 * spec files to sit inside apps/web's own node_modules ancestry, since this
 * isn't set up as a hoisting npm workspace. Python tests still live at the
 * root tests/ exactly as Plan.md describes.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
