// Live checks against the running app on :7000 with real logins and the self-hosted LiveKit: two people in one meeting with a fake
// camera and microphone (Chromium's test devices), screenshots of the call. Never in mock mode.
//   cd web/tb-nik && LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib npx playwright test -c e2e/live/playwright.live.config.ts
// Logins come from the demo login file (TBNIK_LOGINS, default ~/vaidyx/.tb_v2_demo_logins, tab-separated); nothing is printed.
import os from "node:os";
import path from "node:path";
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 240_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: path.join(os.tmpdir(), "tbnik-live-results"),
  use: {
    baseURL: process.env.TBNIK_BASE_URL || "http://127.0.0.1:7000",
    headless: true,
    viewport: { width: 1366, height: 768 },
    colorScheme: "light",
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
    trace: "off",
    screenshot: "off",
    permissions: ["camera", "microphone"],
    launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"] },
  },
  projects: [{ name: "chromium-live" }],
});
