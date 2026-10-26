// Screenshot helpers. Two modes:
//  - real (default): the running app (baseURL, :7000). login() posts /api/auth/login with TBNIK_USER / TBNIK_PASSWORD from the
//    environment (never written in code or logs). GET /api/tb/me is passed through with the forced set-up steps switched off,
//    so a demo login shows the page asked for rather than /welcome.
//  - mock (TBNIK_MOCK=1): nothing is sent anywhere. The built site (static/tb-nik) and the fonts are served from disk and every
//    /api call is answered from fixtures.ts (synthetic). Used to check layouts before the backend is restarted.
// Failure states use overrides: { "GET /api/tb/case-list": { status: 500 } } or { ...: { body: { cases: [] } } }.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Page, Route } from "@playwright/test";
import * as fx from "./fixtures";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../../../..");
const STATIC = path.join(REPO, "static");
// TBNIK_SHOTS moves the pictures elsewhere (the night-v3 baseline: /data/vaidyx/night-v3/baseline/<label>).
export const SHOTS = process.env.TBNIK_SHOTS || path.join(REPO, "docs/ui/build/shots");
export const MOCK = process.env.TBNIK_MOCK === "1";

export const SIZES = [
  { width: 1366, height: 768 },
  { width: 1920, height: 1080 },
  { width: 390, height: 844 },
];
export const THEMES = ["light", "dark"] as const;

export type Override = { status?: number; body?: unknown; delayMs?: number };
export type Overrides = Record<string, Override>;

const TYPES: Record<string, string> = { ".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".png": "image/png", ".json": "application/json", ".webmanifest": "application/manifest+json" };

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function serveFile(route: Route, file: string) {
  if (!file.startsWith(STATIC) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return route.fulfill({ status: 404, body: "" });
  return route.fulfill({ status: 200, contentType: TYPES[path.extname(file)] ?? "application/octet-stream", body: fs.readFileSync(file) });
}

function mockAnswer(method: string, p: string, role: fx.Role): { status: number; body: unknown } {
  const ok = (body: unknown) => ({ status: 200, body });
  if (method !== "GET") {
    if (p === "/api/auth/login") return ok({ ok: true });
    if (p === "/api/tb/cases/from-his") return ok({ case: { case_id: "TB-2026-0032" }, job: "J1a2b3c4d", total: 9 });
    if (p.endsWith("/team/code")) return ok({ code: "482913", expires_at: new Date(Date.now() + 864e5).toISOString() });
    return ok({ ok: true });
  }
  if (p === "/api/tb/me") return ok(fx.me(role));
  if (p === "/api/tb/case-list") return ok(fx.caseList);
  if (p === "/api/tb/waiting") return ok(fx.waiting);
  if (p === "/api/tb/notifications") return ok(fx.notifications);
  if (p === "/api/tb/inbox") return ok(fx.inbox);
  if (p === "/api/tb/meetings" || p === "/api/tb/meetings/open") return ok(fx.meetings);  // /open: the send dialog's open meetings (night-v3 item 1.6)
  if (p === "/api/tb/org") return ok(fx.org);
  if (p === "/api/tb/protocols") return ok(fx.protocols);
  if (p.startsWith("/api/tb/protocols/")) return ok(fx.protocols.protocols.find((x) => x.id === p.split("/").pop()) ?? {});
  if (p === "/api/tb/his/lookup") return ok(fx.hisLookup);
  if (p.startsWith("/api/tb/jobs/")) return ok(fx.job("running"));
  if (p === "/api/tb/setup") return ok(fx.setup);
  if (p === "/api/tb/accounts") return ok(fx.accounts);
  if (p.startsWith("/api/tb/departments/")) return ok(fx.people);
  if (p === "/api/tb/me/notifications") return ok(fx.notificationPrefs);
  if (p === "/api/tb/me/activity" || p === "/api/tb/activity") return ok(fx.activity);
  if (p === "/api/tb/push/key") return ok({ public_key: null, enabled: false });
  if (p === "/api/auth/2fa/status") return ok({ enabled: false });
  return { status: 404, body: { detail: "Not Found" } };
}

/** Installs the routes for one page: mock answers (mock mode), the /me pass-through (real mode) and the overrides. */
export async function prepare(page: Page, { role = "treating", overrides = {}, signedOut = false }: { role?: fx.Role; overrides?: Overrides; signedOut?: boolean } = {}) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    const key = `${method} ${url.pathname}`;
    const o = overrides[key];
    if (o) {
      if (o.delayMs) await new Promise((r) => setTimeout(r, o.delayMs));
      if (o.status !== undefined || o.body !== undefined) return json(route, o.body ?? { detail: { message: "The server could not answer (test).", code: "test" } }, o.status ?? 200);
    }
    if (MOCK) {
      if (url.pathname.startsWith("/api/")) {
        if (signedOut && url.pathname === "/api/tb/me") return json(route, { detail: "Not authenticated" }, 401);
        const a = mockAnswer(method, url.pathname, role);
        return json(route, a.body, a.status);
      }
      if (url.pathname.startsWith("/tb-nik/api/")) return json(route, { ok: true, sent: true, id: "mock" });
      if (url.pathname.startsWith("/static/")) return serveFile(route, path.join(STATIC, decodeURIComponent(url.pathname.slice("/static/".length))));
      if (url.pathname === "/tb-nik" || url.pathname.startsWith("/tb-nik/")) return serveFile(route, path.join(STATIC, "tb-nik/index.html"));
      return route.fulfill({ status: 404, body: "" });
    }
    if (!signedOut && method === "GET" && url.pathname === "/api/tb/me") {
      const res = await route.fetch();
      if (res.status() !== 200) return route.fulfill({ response: res });
      const me = await res.json();
      return json(route, { ...me, must_change_password: false, setup_needed: false });
    }
    return route.continue();
  });
}

/** Signs in with the environment's login (real mode); a no-op in mock mode. */
export async function login(page: Page) {
  if (MOCK) return;
  const username = process.env.TBNIK_USER;
  const password = process.env.TBNIK_PASSWORD;
  if (!username || !password) throw new Error("Set TBNIK_USER and TBNIK_PASSWORD (or TBNIK_MOCK=1) to take the screenshots.");
  const r = await page.request.post("/api/auth/login", { data: { username, password, remember: false }, headers: { "X-Requested-With": "tb-nik" } });
  if (!r.ok()) throw new Error(`Sign-in failed with HTTP ${r.status()}`);
}

async function settle(page: Page) {
  await page.waitForLoadState("networkidle", { timeout: 3000 }).catch(() => {});
  await page.evaluate(() => document.fonts?.ready).catch(() => {});
  await page.waitForTimeout(350);
}

/** Every width, light and dark: docs/ui/build/shots/<page>-<state>-<theme>-<width>.png. `before` runs after each resize. */
export async function shoot(page: Page, name: string, state: string, opts: { before?: (page: Page) => Promise<void>; sizes?: typeof SIZES; fullPage?: boolean; themes?: readonly ("light" | "dark")[] } = {}) {
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const size of opts.sizes ?? SIZES) {
    await page.setViewportSize(size);
    for (const theme of opts.themes ?? THEMES) {
      await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch { /* none */ } }, theme);
      await settle(page);
      if (opts.fullPage ?? true) await page.evaluate(() => window.scrollTo(0, 0));
      if (opts.before) await opts.before(page);
      const file = path.join(SHOTS, `${name}-${state}-${theme}-${size.width}.png`);
      if (size.width < 1024) {
        // A phone: the screen as seen (with the Dock), and the whole page with the fixed Dock hidden so it does not float mid-page.
        await page.screenshot({ path: file, fullPage: false });
        if (opts.fullPage ?? true) {
          const css = await page.addStyleTag({ content: "nav[aria-label='Main'].fixed{display:none!important}" });
          await page.screenshot({ path: file.replace(/\.png$/, "-full.png"), fullPage: true });
          await css.evaluate((el) => el.remove());
        }
      } else {
        await page.screenshot({ path: file, fullPage: opts.fullPage ?? true });
      }
    }
  }
}

/** Collects console errors so a spec can assert none happened. */
export function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|status of 40[134]|status of 50\d/.test(m.text())) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

/** The role a spec is for: mock mode runs every role; real mode only the one the signed-in login has (TBNIK_ROLE, default treating). */
export function runsFor(role: string): boolean {
  return MOCK || (process.env.TBNIK_ROLE || "treating") === role;
}

/** Prepare, sign in, open the page and wait for it to settle. */
export async function visit(page: Page, to: string, opts: { role?: fx.Role; overrides?: Overrides; signedOut?: boolean } = {}) {
  await prepare(page, opts);
  if (!opts.signedOut) await login(page);
  await page.goto(`/tb-nik${to}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
}
