// Screenshot run for the new interface (docs/ui/build/shots). Real mode needs the app on :7000 and TBNIK_USER / TBNIK_PASSWORD in
// the environment; TBNIK_MOCK=1 serves the build and synthetic answers from disk (e2e/support). Browsers: npx playwright install chromium.
//   cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts
import os from "node:os";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./shots",
  timeout: 180_000,
  fullyParallel: false,
  workers: 2,
  retries: 0,
  reporter: [["list"]],
  outputDir: path.join(os.tmpdir(), "tbnik-playwright-results"),
  use: {
    baseURL: process.env.TBNIK_BASE_URL || "http://127.0.0.1:7000",
    actionTimeout: 30_000,  // a click or fill that waits longer is a hang: fail fast instead of eating the 180 s test timeout (night-v3 item 1.10)
    headless: true,
    viewport: { width: 1366, height: 768 },
    colorScheme: "light",
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
    reducedMotion: "reduce",
    trace: "off",
    screenshot: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 768 } } }],
});
