// Real-mode journeys: the running app on :7000, the demo logins (SYNTHETIC roles), every role, desktop and phone.
// Run (from web/tb-nik, app up on :7000):
//   LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib npx playwright test -c e2e/playwright.config.ts real
// Options: TBNIK_REAL_ROLES=treating,coordinator (a subset), TBNIK_ASK=1 (types one question in the Ask box; a model call,
// slow), TBNIK_REWELCOME=1 (shoots the welcome stepper again for accounts already set up), TBNIK_REAL_LOG=<file> (the
// network, console and overflow log, JSON lines; default <tmp>/tbnik-real-log.jsonl; axe findings go to <log>-axe.jsonl).
// Passwords are read here from ~/vaidyx/.tb_v2_demo_logins (tab separated: username, password, ...) and never printed.
// One sign-in per role and run (the login rate limit is 15 a minute): the session is kept in <tmp>/tbnik-real-state.
// Each account starts with the welcome stepper the first time; the journey completes it (the intended first-login flow).
// The resident role has no demo login: TBNIK_RESIDENT_USER / TBNIK_RESIDENT_PASSWORD name one (made by
// docs/night-v3/tools/ensure_resident.py); its tests are skipped when they are unset.
// Files: docs/ui/build/shots/real-<role>-<page>-<state>-<theme>-<width>.png (TBNIK_SHOTS moves them). Skipped in mock mode (TBNIK_MOCK=1).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test, type Page, type Response } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { MOCK, SHOTS, SIZES } from "../support/helpers";

type RoleKey = "treating" | "coordinator" | "supporting" | "supporting-head" | "dept-admin" | "root-admin" | "resident";
// The resident login comes from the environment (never written in code or logs).
const RESIDENT_USER = (process.env.TBNIK_RESIDENT_USER || "").trim();
const RESIDENT_PASSWORD = process.env.TBNIK_RESIDENT_PASSWORD || "";
const ACCOUNTS: Record<RoleKey, string> = {
  treating: "tb-breast-doc",
  coordinator: "tb-mdt",
  supporting: "tb-rad-doc",
  "supporting-head": "tb-path-head",
  "dept-admin": "tb-breast-admin",
  "root-admin": "tb-root",
  resident: RESIDENT_USER,
};
const WANTED = (process.env.TBNIK_REAL_ROLES || "").split(",").map((s) => s.trim()).filter(Boolean);
const STATE_DIR = path.join(os.tmpdir(), "tbnik-real-state");
const LOG = process.env.TBNIK_REAL_LOG || path.join(os.tmpdir(), "tbnik-real-log.jsonl");
const AXE_LOG = LOG.replace(/\.jsonl$/, "") + "-axe.jsonl";
const [LAPTOP, WIDE, PHONE] = SIZES;
const ALL = SIZES;
const LAPTOP_PHONE = [LAPTOP, PHONE];
const THEMES_BOTH = ["light", "dark"] as const;
const LIGHT = ["light"] as const;
const MEETING_ROOM_NAME = "UI review";
// Answers a sign-in journey expects: the signed-out check before signing in, and the wrong login typed on purpose.
const SIGNED_OUT = [/GET \/api\/tb\/me -> 401/, /POST \/api\/auth\/login -> 401/];
// Case Files named in the brief (synthetic demo cases).
const P19 = "TB-DEMO-P19";
const P18A = "TB-DEMO-P18A";
const TB001 = "TB-001";

function stateDir() {
  fs.mkdirSync(STATE_DIR, { recursive: true, mode: 0o700 });
  return STATE_DIR;
}

/** Saves the session cookies of a role, readable by this user only. */
async function saveState(page: Page, file: string) {
  await page.context().storageState({ path: file });
  fs.chmodSync(file, 0o600);
}

// The real patient's Case File must never appear in a screenshot (the shots are committed). The demo logins can see it
// in some lists, so every JSON answer is filtered here before the page draws it: any list item that mentions it goes.
// Protected (real patient) Case Files never appear in a screenshot: filtered by case id (the server also hides them from demo logins).
const REAL_CASE = new RegExp((process.env.TB_PROTECTED_CASES || "TB-2026-bharath").split(",").map((s) => s.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).filter(Boolean).join("|"), "i");
const guarded = new WeakSet<Page>();

function prune(v: unknown): unknown {
  // Inner lists first, so a department or a group is kept and only the items that name the real case go.
  if (Array.isArray(v)) return v.map(prune).filter((x) => !REAL_CASE.test(JSON.stringify(x) ?? ""));
  if (v && typeof v === "object") {
    const o: Record<string, unknown> = {};
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) o[k] = prune(x);
    if (Array.isArray(o.cases) && typeof o.total === "number") o.total = (o.cases as unknown[]).length;
    return o;
  }
  return v;
}

/** Any word left outside a list (a count line, a title) is blanked too. */
function redact(v: unknown): unknown {
  if (typeof v === "string") return REAL_CASE.test(v) ? "(hidden)" : v;
  if (Array.isArray(v)) return v.map(redact);
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v as Record<string, unknown>).map(([k, x]) => [k, redact(x)]));
  return v;
}

const scrub = (v: unknown) => redact(prune(v));

async function guardRealCase(page: Page) {
  if (guarded.has(page)) return;
  guarded.add(page);
  await page.route("**/api/**", async (route) => {
    const u = new URL(route.request().url());
    if (REAL_CASE.test(decodeURIComponent(u.pathname + u.search))) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not shown in the screenshot run" }) });
    if (route.request().method() !== "GET") return route.continue();
    let res;
    try { res = await route.fetch(); } catch { return route.abort("connectionrefused").catch(() => {}); }
    const ct = res.headers()["content-type"] || "";
    if (!ct.includes("application/json")) return route.fulfill({ response: res });
    const text = await res.text();
    if (!REAL_CASE.test(text)) return route.fulfill({ response: res, body: text });
    let body: unknown;
    try { body = JSON.parse(text); } catch { return route.fulfill({ response: res, body: text }); }
    return route.fulfill({ response: res, body: JSON.stringify(scrub(body)) });
  });
}

function password(user: string): string {
  if (RESIDENT_USER && user === RESIDENT_USER) {
    if (RESIDENT_PASSWORD) return RESIDENT_PASSWORD;
    throw new Error("Set TBNIK_RESIDENT_PASSWORD for the resident login");
  }
  const file = path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins");
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    if (!line || line.startsWith("#")) continue;
    const [u, p] = line.split("\t");
    if (u === user && p) return p;
  }
  throw new Error(`No demo login for ${user} in ~/vaidyx/.tb_v2_demo_logins`);
}

function log(entry: Record<string, unknown>) {
  fs.appendFileSync(LOG, JSON.stringify({ at: new Date().toISOString(), ...entry }) + "\n");
}

/** Every 4xx / 5xx answer and failed request, and every console error, logged with the test name. `planned` are allowed. */
function watch(page: Page, name: string, planned: RegExp[] = []) {
  const bad: string[] = [];
  page.on("response", (r: Response) => {
    const u = new URL(r.url());
    if (r.status() >= 400 && u.pathname.startsWith("/api/")) {
      const line = `${r.request().method()} ${u.pathname}${u.search} -> ${r.status()}`;
      const ok = planned.some((p) => p.test(line));
      log({ test: name, kind: ok ? "planned" : "http", line });
      if (!ok) bad.push(line);
    }
  });
  page.on("requestfailed", (r) => {
    const f = r.failure()?.errorText || "";
    if (/ERR_ABORTED|NS_BINDING_ABORTED/.test(f)) return;
    log({ test: name, kind: "failed", line: `${r.method()} ${r.url()} ${f}` });
  });
  page.on("console", (m) => { if (m.type() === "error") log({ test: name, kind: "console", line: m.text().slice(0, 400) }); });
  page.on("pageerror", (e) => { log({ test: name, kind: "pageerror", line: String(e).slice(0, 400) }); bad.push(String(e)); });
  return bad;
}

async function appUp(page: Page) {
  for (let i = 0; i < 40; i++) {
    try { const r = await page.request.get("/api/health", { timeout: 5000 }); if (r.status() < 500) return; } catch { /* down */ }
    await page.waitForTimeout(3000);
  }
}

/** Opens a page of the new site, waiting out a brief restart of the app. */
async function go(page: Page, to: string) {
  for (let i = 0; i < 5; i++) {
    try {
      const r = await page.goto(`/tb-nik${to}`, { waitUntil: "domcontentloaded" });
      if (r && r.status() < 500) break;
    } catch { /* app restarting */ }
    await appUp(page);
  }
  await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
}

/** Reuses the saved session of the role; signs in through the API once when there is none (one login per run). */
async function session(page: Page, role: RoleKey) {
  await guardRealCase(page);
  stateDir();
  const file = path.join(STATE_DIR, `${role}.json`);
  if (fs.existsSync(file)) {
    const state = JSON.parse(fs.readFileSync(file, "utf8"));
    await page.context().addCookies(state.cookies || []);
    await appUp(page);
    const r = await page.request.get("/api/tb/me");
    if (r.ok()) return (await r.json()) as Me;
    await page.context().clearCookies();
  }
  await appUp(page);
  const r = await page.request.post("/api/auth/login", { data: { username: ACCOUNTS[role], password: password(ACCOUNTS[role]), remember: false }, headers: { "X-Requested-With": "tb-nik" } });
  if (!r.ok()) throw new Error(`Sign-in for ${role} failed with HTTP ${r.status()}`);
  await saveState(page, file);
  return (await (await page.request.get("/api/tb/me")).json()) as Me;
}

interface Me { setup_needed?: boolean; must_change_password?: boolean; display_name?: string; roles: Record<string, unknown> }

async function settle(page: Page) {
  await page.waitForLoadState("networkidle", { timeout: 4000 }).catch(() => {});
  await page.evaluate(() => document.fonts?.ready).catch(() => {});
  await page.waitForTimeout(400);
}

/** Screenshots at the given widths and themes. Phone: the screen as seen (with the Dock) and the whole page (Dock hidden). */
async function snap(page: Page, role: RoleKey, name: string, state: string, opts: { sizes?: typeof SIZES; themes?: readonly ("light" | "dark")[]; full?: boolean; before?: (p: Page) => Promise<void> } = {}) {
  fs.mkdirSync(SHOTS, { recursive: true });
  for (const size of opts.sizes ?? ALL) {
    await page.setViewportSize(size);
    for (const theme of opts.themes ?? THEMES_BOTH) {
      await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch { /* none */ } }, theme);
      await settle(page);
      if (opts.before) await opts.before(page);
      else await page.evaluate(() => window.scrollTo(0, 0));
      const file = path.join(SHOTS, `real-${role}-${name}-${state}-${theme}-${size.width}.png`);
      const full = opts.full ?? true;
      // A live meeting join code is a short-lived key: it is masked in every committed picture.
      const mask = [page.getByTestId("meeting-code")];
      if (theme === "light") {
        // Sideways scrolling of the whole page is a layout break: logged with the shot name.
        const wide = await page.evaluate(() => document.documentElement.scrollWidth);
        if (wide > size.width + 1) log({ test: `${role}: ${name} ${state}`, kind: "overflow", line: `page is ${wide} px wide at ${size.width}` });
      }
      if (size.width < 1024) {
        await page.screenshot({ path: file, fullPage: false, mask });
        if (full) {
          const css = await page.addStyleTag({ content: "nav[aria-label='Main'].fixed{display:none!important}" });
          await page.screenshot({ path: file.replace(/\.png$/, "-full.png"), fullPage: true, mask });
          await css.evaluate((el) => el.remove());
        }
      } else {
        await page.screenshot({ path: file, fullPage: full, mask });
      }
    }
  }
  await page.setViewportSize(LAPTOP);
  await page.evaluate(() => { document.documentElement.setAttribute("data-theme", "light"); try { localStorage.setItem("tbnik.theme", "light"); } catch { /* none */ } });
}

/** axe-core on the page as it is (light, laptop); serious and critical issues are logged and returned. */
async function axe(page: Page, role: RoleKey, name: string) {
  await settle(page);
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  for (const v of bad) fs.appendFileSync(AXE_LOG, JSON.stringify({ role, page: name, id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 6).map((n) => ({ target: n.target, summary: (n.failureSummary || "").slice(0, 300) })) }) + "\n");
  return bad.map((v) => `${v.id} (${v.nodes.length})`);
}

/** The Dock on a phone: visible, its items reachable. */
async function checkDock(page: Page) {
  await page.setViewportSize(PHONE);
  await settle(page);
  const dock = page.locator("nav[aria-label='Main'].fixed, nav[aria-label='Main']:visible").last();
  await expect(dock).toBeVisible();
  const links = dock.getByRole("link");
  expect(await links.count()).toBeGreaterThan(0);
  const box = await dock.boundingBox();
  expect(box && box.y + box.height <= PHONE.height + 1).toBeTruthy();
  await page.setViewportSize(LAPTOP);
}

/** The welcome stepper of a first sign-in: one shot per step, then it is finished (the intended first-login flow). */
async function welcome(page: Page, role: RoleKey, doctor: boolean, name?: string) {
  await expect(page.getByRole("heading", { name: "Make it yours" })).toBeVisible({ timeout: 20_000 });
  const nameBox = page.locator("#name");
  // `name`: typed over what the account came with (the resident's placement name has brackets, which the profile refuses).
  if (name) await nameBox.fill(name);
  else if (!(await nameBox.inputValue()).trim()) await nameBox.fill(`Demo ${role}`);
  if (doctor) { const reg = page.locator("#reg"); if (!(await reg.inputValue()).trim()) await reg.fill("TNMC 10001"); }
  await snap(page, role, "welcome", "1-you", { sizes: LAPTOP_PHONE, themes: LIGHT });
  const next = page.getByRole("button", { name: /^(Next|Continue)$/ });
  await next.click();
  await expect(page.getByText("How it looks")).toBeVisible();
  await snap(page, role, "welcome", "2-look", { sizes: LAPTOP_PHONE, themes: LIGHT });
  await next.click();
  await expect(page.getByText("Where you start and how to reach you")).toBeVisible();
  await snap(page, role, "welcome", "3-start", { sizes: LAPTOP_PHONE, themes: LIGHT });
  await next.click();
  await snap(page, role, "welcome", "4-last", { sizes: LAPTOP_PHONE, themes: LIGHT });
  await page.getByRole("button", { name: "Go to Home" }).click();
  await page.waitForURL((u) => !u.pathname.endsWith("/welcome"), { timeout: 20_000 });
}

/** First test of every role: the sign-in page (UI), the welcome stepper on the first time, the start page. */
async function signInJourney(page: Page, role: RoleKey, opts: { doctor: boolean; shootSignIn?: boolean; name?: string }) {
  await guardRealCase(page);
  stateDir();
  const file = path.join(STATE_DIR, `${role}.json`);
  await appUp(page);
  if (opts.shootSignIn) {
    await go(page, "/sign-in");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await snap(page, role, "sign-in", "empty", { sizes: ALL });
    // A wrong login on an account that does not exist (no lockout of a real account).
    await page.locator("#email").fill("nobody@vxh.example");
    await page.locator("#password").fill("not-a-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await snap(page, role, "sign-in", "wrong-password", { sizes: LAPTOP_PHONE, themes: LIGHT });
  }
  let me: Me;
  const saved = fs.existsSync(file);
  if (!saved) {
    await go(page, "/sign-in");
    await page.locator("#email").fill(ACCOUNTS[role]);
    await page.locator("#password").fill(password(ACCOUNTS[role]));
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL((u) => !u.pathname.endsWith("/sign-in"), { timeout: 20_000 });
    await saveState(page, file);
    me = (await (await page.request.get("/api/tb/me")).json()) as Me;
  } else {
    me = await session(page, role);
  }
  if (me.setup_needed) {
    await go(page, "/home");
    await welcome(page, role, opts.doctor, opts.name);
  } else if (process.env.TBNIK_REWELCOME === "1") {
    // Shots of the welcome stepper again for an account already set up (each step re-saves the same values).
    await go(page, "/welcome");
    await welcome(page, role, opts.doctor, opts.name);
  }
  await go(page, "/home");
  await page.waitForTimeout(800);
}

function forRole(role: RoleKey) {
  return !MOCK && (!WANTED.length || WANTED.includes(role));
}

// ----------------------------------------------------------------------------------------------------------------------
test.describe.configure({ mode: "default" });
test.skip(MOCK, "real mode only");

test.describe("treating doctor (tb-breast-doc)", () => {
  const role: RoleKey = "treating";
  test.skip(!forRole(role), "role not selected");

  test("sign in, welcome, home", async ({ page }) => {
    const bad = watch(page, `${role}: sign-in`, SIGNED_OUT);
    await signInJourney(page, role, { doctor: true, shootSignIn: true });
    await expect(page.getByRole("heading").first()).toBeVisible();
    await snap(page, role, "home", "list");
    await checkDock(page);
    // The search bar (UHID, name, commands) and the bell, open.
    await page.getByRole("combobox", { name: /Search Case Files/ }).first().fill("VXH/26");
    await page.waitForTimeout(800);
    await snap(page, role, "home", "search-open", { sizes: [LAPTOP], themes: LIGHT, full: false, before: async () => {} });
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /^Notifications/ }).first().click();
    await expect(page.locator("[data-slot=popover-content]").first()).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(800);
    await snap(page, role, "home", "bell-open", { sizes: [LAPTOP], themes: LIGHT, full: false, before: async () => {} });
    await page.keyboard.press("Escape");
    log({ test: `${role}: home`, kind: "axe", line: (await axe(page, role, "home")).join(", ") });
    expect(bad).toEqual([]);
  });

  test("Case File TB-DEMO-P19: the guided Case File, Overview and each section", async ({ page }) => {
    const bad = watch(page, `${role}: casefile P19`);
    await session(page, role);
    // The guided Case File opens on Overview: the header, what is left to do, the patient at a glance.
    await go(page, `/cases/${P19}`);
    await expect(page.getByTestId("casefile-page")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("case-header")).toContainText("Priya Venkatesan");
    await expect(page.getByTestId("section-overview")).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "casefile-p19", "overview");
    log({ test: `${role}: casefile`, kind: "axe", line: (await axe(page, role, "casefile")).join(", ") });
    // Each section has its own address.
    for (const slug of ["question", "reports", "check", "pre-authorization", "summary"]) {
      await go(page, `/cases/${P19}/${slug}`);
      await expect(page.getByTestId(`section-${slug}`)).toBeVisible({ timeout: 20_000 });
      await snap(page, role, "casefile-p19", slug, { sizes: LAPTOP_PHONE, themes: THEMES_BOTH });
    }
    // Reports: the values read from the first report.
    await go(page, `/cases/${P19}/reports`);
    await expect(page.getByTestId("section-reports")).toBeVisible({ timeout: 20_000 });
    const read = page.getByTestId("values-read").first();
    if (await read.count()) {
      await read.click();
      await expect(page.getByTestId("values-list").first()).toBeVisible();
      await snap(page, role, "casefile-p19", "reports-values", { sizes: [LAPTOP], themes: LIGHT, full: false, before: async (p) => { await p.getByTestId("values-list").first().scrollIntoViewIfNeeded(); } });
    } else log({ test: `${role}: casefile P19`, kind: "note", line: "no values read on the first report" });
    // Check: the report beside the value, with the quote marked (laptop).
    await go(page, `/cases/${P19}/check`);
    await expect(page.getByTestId("section-check")).toBeVisible({ timeout: 20_000 });
    const source = page.getByTestId("check-source").getByTestId("source-viewer");
    if (await page.getByTestId("check-source").count()) {
      await expect(source).toBeVisible({ timeout: 20_000 });
      await page.waitForTimeout(1500);
      await snap(page, role, "casefile-p19", "source-viewer", { sizes: [LAPTOP, WIDE], themes: LIGHT, full: false });
    } else log({ test: `${role}: casefile P19`, kind: "note", line: "no report beside the Check section" });
    // One click away: the team and the board form.
    for (const panel of ["team", "board"]) {
      await go(page, `/cases/${P19}/${panel}`);
      await expect(page.getByTestId("side-panel").or(page.getByRole("dialog")).first()).toBeVisible({ timeout: 20_000 });
      await snap(page, role, "casefile-p19", panel, { sizes: LAPTOP_PHONE, themes: LIGHT, full: false });
    }
    // The phone: the sections as chips.
    await page.setViewportSize(PHONE);
    await go(page, `/cases/${P19}`);
    await expect(page.getByTestId("section-chips")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("section-chips").getByRole("button", { name: "Check", exact: false }).first().click();
    await expect(page.getByTestId("section-check")).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "casefile-p19", "phone-check", { sizes: [PHONE], themes: THEMES_BOTH });
    expect(bad).toEqual([]);
  });

  test("Ask box: one question (TBNIK_ASK=1)", async ({ page }) => {
    test.skip(process.env.TBNIK_ASK !== "1", "set TBNIK_ASK=1 to ask one question (a model call)");
    test.setTimeout(600_000);
    const bad = watch(page, `${role}: ask`);
    await session(page, role);
    // The guided Case File: /ask opens the Overview with "Ask about this patient" in the side panel.
    await go(page, `/cases/${P19}/ask`);
    const ask = page.getByTestId("ask-panel");
    await expect(ask).toBeVisible({ timeout: 30_000 });
    await page.locator("#ask-input").fill("What did the histopathology report say about the margins?");
    await snap(page, role, "casefile-p19", "ask-typed", { sizes: [LAPTOP], themes: LIGHT, full: false });
    await ask.getByRole("button", { name: "Ask" }).click();
    await expect(ask.getByText("Reading the records")).toBeVisible();
    await snap(page, role, "casefile-p19", "ask-waiting", { sizes: [LAPTOP], themes: LIGHT, full: false });
    await expect(ask.getByText("Reading the records")).toHaveCount(0, { timeout: 540_000 });
    await snap(page, role, "casefile-p19", "ask-answered", { sizes: [LAPTOP, PHONE], themes: LIGHT, full: false });
    expect(bad).toEqual([]);
  });

  test("Case File TB-DEMO-P18A (another department) and TB-001 (no access)", async ({ page }) => {
    const bad = watch(page, `${role}: casefile P18A, TB-001`, [/\/api\/tb\/cases\/TB-001\b.* -> 403/]);
    await session(page, role);
    await go(page, `/cases/${P18A}`);
    await expect(page.getByTestId("casefile-page").or(page.getByTestId("casefile-error")).first()).toBeVisible({ timeout: 30_000 });
    await snap(page, role, "casefile-p18a", "summary", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await go(page, `/cases/${TB001}`);
    await expect(page.getByText("You do not have access to this Case File")).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "casefile-tb001", "no-access", { sizes: LAPTOP_PHONE, themes: LIGHT, full: false });
    expect(bad).toEqual([]);
  });

  test("New Case File up to the last step (nothing created)", async ({ page }) => {
    const bad = watch(page, `${role}: new case`);
    await session(page, role);
    await go(page, "/cases/new");
    await expect(page.getByText("Find the patient")).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "newcase", "1-empty", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await page.locator("#identifier").fill("VXH/26/004219");
    await page.getByRole("button", { name: "Look up" }).click();
    await expect(page.getByLabel("Registration found")).toBeVisible({ timeout: 30_000 });
    await snap(page, role, "newcase", "1-found", { sizes: ALL, themes: THEMES_BOTH });
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByText("Which cancer")).toBeVisible();
    await snap(page, role, "newcase", "2-cancer", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await page.getByRole("radiogroup", { name: "Cancer" }).getByRole("radio").filter({ hasText: "Breast" }).first().click();
    await expect(page.getByLabel("Checklist and setting")).toBeVisible();
    await page.locator("[id^='setting-']").first().click();
    await snap(page, role, "newcase", "2-cancer-picked", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByText("Filled in with the usual choices")).toBeVisible();
    await snap(page, role, "newcase", "3-logistics", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await page.getByRole("radiogroup", { name: "Urgency" }).getByRole("radio").nth(2).click();
    await snap(page, role, "newcase", "3-logistics-ready", { sizes: [LAPTOP], themes: LIGHT });
    // Stop here: "Create and fetch records" is not pressed.
    expect(bad).toEqual([]);
  });

  test("meetings: list, agenda, member view, join by code", async ({ page }) => {
    const bad = watch(page, `${role}: meetings`, [/\/api\/tb\/meetings\/join -> 404/]);
    await session(page, role);
    await go(page, "/meetings");
    await expect(page.getByTestId("meetings-page")).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "meetings", "list");
    const list = await (await page.request.get("/api/tb/meetings")).json();
    const live = (list.meetings || []).find((m: { status: string; current?: string }) => m.status === "in_session" && m.current === P19) || (list.meetings || []).find((m: { status: string }) => m.status === "in_session");
    const review = (list.meetings || []).find((m: { room?: string; title?: string }) => (m.room || m.title || "").includes(MEETING_ROOM_NAME));
    if (review) {
      await go(page, `/meetings/${review.id}`);
      await expect(page.getByTestId("meeting-page").or(page.getByTestId("control-view")).first()).toBeVisible({ timeout: 20_000 });
      await snap(page, role, "meeting-ui-review", "agenda-doctor", { sizes: LAPTOP_PHONE, themes: LIGHT });
    }
    if (live) {
      await go(page, `/meetings/${live.id}/member`);
      await page.waitForTimeout(2500);
      await snap(page, role, "meeting-demo", "member-view", { sizes: ALL, themes: THEMES_BOTH, full: false });
    }
    await go(page, "/meetings/join");
    await expect(page.getByTestId("join-page")).toBeVisible();
    await snap(page, role, "meetings-join", "empty", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await page.locator("#join-code").fill("000000");
    await page.getByTestId("join-submit").click();
    await expect(page.getByRole("alert").first()).toBeVisible({ timeout: 15_000 });
    await snap(page, role, "meetings-join", "wrong-code", { sizes: LAPTOP_PHONE, themes: LIGHT });
    expect(bad).toEqual([]);
  });

  test("settings and activity", async ({ page }) => {
    const bad = watch(page, `${role}: settings`);
    await session(page, role);
    await go(page, "/settings");
    await expect(page.getByRole("heading", { name: "Settings" }).first()).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "settings", "page");
    log({ test: `${role}: settings`, kind: "axe", line: (await axe(page, role, "settings")).join(", ") });
    await go(page, "/activity");
    await expect(page.getByRole("heading").first()).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "activity", "mine", { sizes: LAPTOP_PHONE, themes: LIGHT });
    expect(bad).toEqual([]);
  });
});

// ----------------------------------------------------------------------------------------------------------------------
test.describe("MDT Coordinator (tb-mdt)", () => {
  const role: RoleKey = "coordinator";
  test.skip(!forRole(role), "role not selected");

  test("sign in, welcome, home", async ({ page }) => {
    const bad = watch(page, `${role}: sign-in`, SIGNED_OUT);
    await signInJourney(page, role, { doctor: false });
    await snap(page, role, "home", "list");
    await checkDock(page);
    log({ test: `${role}: home`, kind: "axe", line: (await axe(page, role, "home")).join(", ") });
    expect(bad).toEqual([]);
  });

  test("meetings: list, UI review meeting, agenda, room screen, live meeting control", async ({ page }) => {
    const bad = watch(page, `${role}: meetings`);
    await session(page, role);
    await go(page, "/meetings");
    await expect(page.getByTestId("meetings-page")).toBeVisible({ timeout: 20_000 });
    let list = await (await page.request.get("/api/tb/meetings")).json();
    let review = (list.meetings || []).find((m: { room?: string; title?: string }) => (m.room || m.title || "").includes(MEETING_ROOM_NAME));
    // The new meeting dialog is always shot; the meeting is created only when the UI review meeting does not exist yet.
    await page.getByTestId("new-meeting").click();
    await expect(page.getByTestId("new-meeting-dialog")).toBeVisible();
    const d = new Date(Date.now() + 7 * 864e5);
    await page.locator("#nm-date").fill(`${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`);
    await page.locator("#nm-time").fill("16:00");
    await page.locator("#nm-room").fill(MEETING_ROOM_NAME);
    await page.locator("#nm-room").press("Tab");
    await snap(page, role, "meetings", "new-meeting", { sizes: LAPTOP_PHONE, themes: LIGHT, full: false, before: async () => {} });
    if (!review) {
      await page.getByTestId("new-meeting-dialog").getByRole("button", { name: /Create/ }).click();
      await page.waitForTimeout(2000);
      list = await (await page.request.get("/api/tb/meetings")).json();
      review = (list.meetings || []).find((m: { room?: string; title?: string }) => (m.room || m.title || "").includes(MEETING_ROOM_NAME));
    } else {
      await page.getByTestId("new-meeting-dialog").getByRole("button", { name: "Cancel" }).click();
    }
    await go(page, "/meetings");
    await snap(page, role, "meetings", "list");
    log({ test: `${role}: meetings`, kind: "axe", line: (await axe(page, role, "meetings")).join(", ") });
    expect(review, "the UI review meeting exists").toBeTruthy();
    await go(page, `/meetings/${review.id}`);
    await expect(page.getByTestId("meeting-page")).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "meeting-ui-review", "agenda");
    log({ test: `${role}: agenda`, kind: "axe", line: (await axe(page, role, "agenda")).join(", ") });
    // The join code: made here when the meeting has none yet (the coordinator's button), then kept for the join test.
    if (!(await page.getByTestId("meeting-code").count()) && (await page.getByTestId("new-code").count())) {
      await page.getByTestId("new-code").click();
      await expect(page.getByTestId("meeting-code")).toBeVisible({ timeout: 15_000 });
      await snap(page, role, "meeting-ui-review", "join-code", { sizes: [LAPTOP], themes: LIGHT, full: false });
    }
    const code = (await page.getByTestId("meeting-code").count()) ? ((await page.getByTestId("meeting-code").textContent({ timeout: 5000 })) || "") : "";
    if (code.trim()) fs.writeFileSync(path.join(STATE_DIR, "meeting-code.txt"), `${review.id}\t${code.replace(/\D/g, "")}`, { mode: 0o600 });
    if (await page.getByTestId("add-case").count()) {
      await page.getByTestId("add-case").click();
      await expect(page.getByTestId("add-case-dialog")).toBeVisible();
      await snap(page, role, "meeting-ui-review", "add-case", { sizes: LAPTOP_PHONE, themes: LIGHT, full: false });
      await page.keyboard.press("Escape");
    }
    await go(page, `/meetings/${review.id}/room`);
    await expect(page.getByTestId("room-screen")).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "meeting-ui-review", "room-waiting", { sizes: [LAPTOP, WIDE], themes: LIGHT, full: false });
    // The demo meeting in session (current case TB-DEMO-P19): control view and room screen, looked at only.
    const live = (list.meetings || []).find((m: { status: string; current?: string }) => m.status === "in_session" && m.current === P19) || (list.meetings || []).find((m: { status: string }) => m.status === "in_session");
    if (live) {
      await go(page, `/meetings/${live.id}`);
      await expect(page.getByTestId("control-view").or(page.getByTestId("meeting-page")).first()).toBeVisible({ timeout: 20_000 });
      await snap(page, role, "meeting-demo", "control", { sizes: ALL, themes: THEMES_BOTH });
      await go(page, `/meetings/${live.id}/room`);
      await expect(page.getByTestId("room-screen")).toBeVisible({ timeout: 20_000 });
      await page.waitForTimeout(2500);
      await snap(page, role, "meeting-demo", "room", { sizes: [LAPTOP, WIDE], themes: THEMES_BOTH, full: false });
    }
    expect(bad).toEqual([]);
  });

  test("Case Files: P19 board form, TB-001 summary", async ({ page }) => {
    const bad = watch(page, `${role}: casefiles`);
    await session(page, role);
    await go(page, `/cases/${P19}/board`);
    await expect(page.getByTestId("casefile-page")).toBeVisible({ timeout: 30_000 });
    await snap(page, role, "casefile-p19", "board", { sizes: LAPTOP_PHONE, themes: LIGHT, full: false });
    await go(page, `/cases/${TB001}`);
    await expect(page.getByTestId("casefile-page")).toBeVisible({ timeout: 30_000 });
    await snap(page, role, "casefile-tb001", "summary", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await go(page, `/cases/${P18A}/team`);
    await expect(page.getByTestId("casefile-page")).toBeVisible({ timeout: 30_000 });
    await snap(page, role, "casefile-p18a", "team", { sizes: [LAPTOP], themes: LIGHT, full: false });
    expect(bad).toEqual([]);
  });

  test("settings and activity", async ({ page }) => {
    const bad = watch(page, `${role}: settings`);
    await session(page, role);
    await go(page, "/settings");
    await snap(page, role, "settings", "page", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await go(page, "/activity");
    await expect(page.getByRole("heading").first()).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "activity", "page", { sizes: ALL, themes: THEMES_BOTH });
    log({ test: `${role}: activity`, kind: "axe", line: (await axe(page, role, "activity")).join(", ") });
    await page.getByRole("tab", { name: "Full log" }).click();
    await page.waitForTimeout(1500);
    await snap(page, role, "activity", "full-log", { sizes: [LAPTOP], themes: LIGHT, before: async () => {} });
    expect(bad).toEqual([]);
  });
});

// ----------------------------------------------------------------------------------------------------------------------
for (const role of ["supporting", "supporting-head"] as const) {
  test.describe(`supporting doctor (${ACCOUNTS[role]})`, () => {
    test.skip(!forRole(role), "role not selected");

    test("sign in, welcome, request cards", async ({ page }) => {
      const bad = watch(page, `${role}: sign-in`, SIGNED_OUT);
      await signInJourney(page, role, { doctor: true });
      await snap(page, role, "home", "requests");
      await checkDock(page);
      log({ test: `${role}: home`, kind: "axe", line: (await axe(page, role, "requests")).join(", ") });
      expect(bad).toEqual([]);
    });

    test("requests page, a Case File, meetings, settings", async ({ page }) => {
      const bad = watch(page, `${role}: pages`, [/\/api\/tb\/cases\/[^/]+(\/[a-z-]+)? -> 403/]);
      await session(page, role);
      await go(page, "/requests");
      await snap(page, role, "requests", "open", { sizes: LAPTOP_PHONE, themes: LIGHT });
      await page.getByRole("tab", { name: "Done" }).click();
      await page.waitForTimeout(500);
      await snap(page, role, "requests", "done", { sizes: LAPTOP_PHONE, themes: LIGHT, before: async () => {} });
      await go(page, `/cases/${P19}`);
      await expect(page.getByTestId("casefile-page").or(page.getByTestId("casefile-error")).first()).toBeVisible({ timeout: 30_000 });
      await snap(page, role, "casefile-p19", "view", { sizes: LAPTOP_PHONE, themes: LIGHT });
      await go(page, "/meetings");
      await snap(page, role, "meetings", "list", { sizes: LAPTOP_PHONE, themes: LIGHT });
      await go(page, "/settings");
      await snap(page, role, "settings", "page", { sizes: [LAPTOP], themes: LIGHT });
      expect(bad).toEqual([]);
    });
  });
}

// ----------------------------------------------------------------------------------------------------------------------
test.describe("department admin (tb-breast-admin)", () => {
  const role: RoleKey = "dept-admin";
  test.skip(!forRole(role), "role not selected");

  test("sign in, welcome, people", async ({ page }) => {
    const bad = watch(page, `${role}: sign-in`, SIGNED_OUT);
    await signInJourney(page, role, { doctor: false });
    await go(page, "/people");
    await expect(page.getByRole("heading").first()).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "people", "list");
    await checkDock(page);
    log({ test: `${role}: people`, kind: "axe", line: (await axe(page, role, "people")).join(", ") });
    expect(bad).toEqual([]);
  });

  test("activity and settings", async ({ page }) => {
    const bad = watch(page, `${role}: pages`);
    await session(page, role);
    await go(page, "/activity");
    await snap(page, role, "activity", "page", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await go(page, "/settings");
    await snap(page, role, "settings", "page", { sizes: LAPTOP_PHONE, themes: LIGHT });
    expect(bad).toEqual([]);
  });
});

// ----------------------------------------------------------------------------------------------------------------------
test.describe("root admin (tb-root)", () => {
  const role: RoleKey = "root-admin";
  test.skip(!forRole(role), "role not selected");

  test("sign in, welcome, admin set-up", async ({ page }) => {
    const bad = watch(page, `${role}: sign-in`, SIGNED_OUT);
    await signInJourney(page, role, { doctor: false });
    await go(page, "/admin");
    await expect(page.getByRole("heading").first()).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "admin", "setup");
    await checkDock(page);
    log({ test: `${role}: admin`, kind: "axe", line: (await axe(page, role, "admin")).join(", ") });
    // Only the first step is shot here: moving between steps saves the step being left (the set-up saves as you go),
    // and this run must not change the hospital's set-up. Every step is in the mock-mode shots (admin-setup-*).
    expect(bad).toEqual([]);
  });

  test("people, activity, settings", async ({ page }) => {
    const bad = watch(page, `${role}: pages`);
    await session(page, role);
    await go(page, "/people");
    await snap(page, role, "people", "list", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await go(page, "/activity");
    await snap(page, role, "activity", "mine", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await page.getByRole("tab", { name: "Full log" }).click();
    await page.waitForTimeout(1500);
    await snap(page, role, "activity", "full-log", { sizes: LAPTOP_PHONE, themes: LIGHT, before: async () => {} });
    await go(page, "/settings");
    await snap(page, role, "settings", "page", { sizes: [LAPTOP], themes: LIGHT });
    expect(bad).toEqual([]);
  });
});

// ----------------------------------------------------------------------------------------------------------------------
// A resident of Breast Surgery (on the team of TB-DEMO-P19 after docs/night-v3/tools/ensure_resident.py): browsing only.
test.describe("resident (TBNIK_RESIDENT_USER)", () => {
  const role: RoleKey = "resident";
  test.skip(!forRole(role), "role not selected");
  test.skip(!RESIDENT_USER || !RESIDENT_PASSWORD, "set TBNIK_RESIDENT_USER and TBNIK_RESIDENT_PASSWORD (docs/night-v3/tools/ensure_resident.py)");

  test("sign in, welcome, home, Case Files list", async ({ page }) => {
    const bad = watch(page, `${role}: sign-in`, SIGNED_OUT);
    await signInJourney(page, role, { doctor: true, name: "Meera Demo-Resident" });
    await expect(page.getByRole("heading").first()).toBeVisible();
    await snap(page, role, "home", "list", { sizes: LAPTOP_PHONE });
    await checkDock(page);
    log({ test: `${role}: home`, kind: "axe", line: (await axe(page, role, "home")).join(", ") });
    await go(page, "/cases");
    await expect(page.getByRole("heading").first()).toBeVisible({ timeout: 20_000 });
    await snap(page, role, "cases", "list", { sizes: LAPTOP_PHONE });
    expect(bad).toEqual([]);
  });

  test("the Case File the resident is on: overview and summary step", async ({ page }) => {
    const bad = watch(page, `${role}: casefile`);
    await session(page, role);
    const list = await (await page.request.get("/api/tb/case-list")).json();
    const ids: string[] = (list.cases || []).map((c: { case_id?: string }) => c.case_id || "").filter((id: string) => id && !REAL_CASE.test(id));
    const cid = ids.includes(P19) ? P19 : ids[0];
    log({ test: `${role}: casefile`, kind: "note", line: cid ? `Case File shown: ${cid}${cid === P19 ? "" : " (not on TB-DEMO-P19)"}` : "the resident is on no Case File" });
    expect(cid, "the resident is on a Case File").toBeTruthy();
    const shot = `casefile-${cid.toLowerCase().replace(/^tb-demo-/, "")}`;
    // The guided Case File: it opens on Overview; the Summary step has its own address.
    await go(page, `/cases/${encodeURIComponent(cid)}`);
    await expect(page.getByTestId("casefile-page")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("section-overview")).toBeVisible({ timeout: 20_000 });
    await snap(page, role, shot, "overview", { sizes: LAPTOP_PHONE });
    await go(page, `/cases/${encodeURIComponent(cid)}/summary`);
    await expect(page.getByTestId("section-summary")).toBeVisible({ timeout: 20_000 });
    await snap(page, role, shot, "summary", { sizes: LAPTOP_PHONE });
    log({ test: `${role}: casefile`, kind: "axe", line: (await axe(page, role, "casefile")).join(", ") });
    expect(bad).toEqual([]);
  });
});

// ----------------------------------------------------------------------------------------------------------------------
// After the coordinator made the UI review meeting: the treating doctor joins it with its code (waiting room).
test.describe("join the UI review meeting by its code", () => {
  test.skip(!forRole("treating") || !forRole("coordinator"), "needs the treating and coordinator roles");
  test("waiting room", async ({ page }) => {
    const codeFile = path.join(STATE_DIR, "meeting-code.txt");
    test.skip(!fs.existsSync(codeFile), "no UI review meeting code yet");
    const bad = watch(page, "treating: join");
    const [mid, code] = fs.readFileSync(codeFile, "utf8").trim().split("\t");
    await session(page, "treating");
    await go(page, "/meetings/join");
    await page.locator("#join-code").fill(code);
    await page.getByTestId("join-submit").click();
    await expect(page.getByTestId("waiting-room").or(page.getByTestId("member-view")).first()).toBeVisible({ timeout: 20_000 });
    await snap(page, "treating", "meetings-join", "waiting-room", { sizes: LAPTOP_PHONE, themes: LIGHT });
    await go(page, `/meetings/${mid}/member`);
    await page.waitForTimeout(2000);
    await snap(page, "treating", "meeting-ui-review", "member-view", { sizes: LAPTOP_PHONE, themes: LIGHT, full: false });
    expect(bad).toEqual([]);
  });
});
