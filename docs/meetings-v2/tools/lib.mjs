// Shared helpers for the meetings-v2 checks (synthetic patients only). Passwords are read in code, never printed. From the 2 Nov test pass.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";

export const BASE = "http://127.0.0.1:7000";
export const H = { "X-Requested-With": "tb-nik" };
export const OUT = process.env.OUT || "/data/vaidyx/meetings-v2/shots";
export const STATE = process.env.STATE || "/data/vaidyx/meetings-v2/state";  // browser sessions per login (mode 600), outside the repo
export const UHID = "VXH/26/004211";
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(STATE, { recursive: true, mode: 0o700 });

export const problems = [];
export const notes = [];
export const note = (s) => { notes.push(s); console.log("NOTE " + s); };
export const problem = (s) => { problems.push(s); console.log("PROBLEM " + s); };

function password(user) {
  for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) {
    if (!line || line.startsWith("#") || !line.includes("\t")) continue;
    const [u, p] = line.split("\t");
    if (u.trim() === user) return p;
  }
  throw new Error("no demo login " + user);
}

// One browser per login; the session cookie is kept in STATE (mode 600) so later scripts do not sign in again (login limit).
export async function open(user, { viewport = { width: 1366, height: 768 }, audio = null, browser = null } = {}) {
  const args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"];
  if (audio) args.push(`--use-file-for-fake-audio-capture=${audio}`);
  const b = browser || await chromium.launch({ args });
  const file = path.join(STATE, `${user}.json`);
  let ctx = await b.newContext({ viewport, locale: "en-IN", timezoneId: "Asia/Kolkata", permissions: ["microphone", "camera"],
    storageState: fs.existsSync(file) ? file : undefined });
  const page = await ctx.newPage();
  let me = await page.request.get(`${BASE}/api/tb/me`, { headers: H });
  if (!me.ok()) {
    const r = await page.request.post(`${BASE}/api/auth/login`, { data: { username: user, password: password(user), remember: false }, headers: H });
    if (!r.ok()) throw new Error(`login ${user} HTTP ${r.status()}`);
    await ctx.storageState({ path: file });
    fs.chmodSync(file, 0o600);
  }
  watch(page, user);
  return { browser: b, ctx, page, rq: page.request };
}

export function watch(page, tag) {
  page.on("pageerror", (e) => problem(`${tag}: page error ${e.message.slice(0, 200)}`));
  page.on("console", (m) => { if (m.type() === "error" && !/\b(401|403|404|409|429)\b/.test(m.text())) problem(`${tag}: console ${m.text().slice(0, 200)}`); });
  page.on("response", (r) => { if (r.status() >= 500) problem(`${tag}: HTTP ${r.status()} ${r.request().method()} ${r.url().replace(BASE, "").slice(0, 120)}`); });
}

export async function settle(page, ms = 500) {
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(ms);
}

export async function shot(page, name, { full = true } = {}) {
  await settle(page, 300);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  const w = page.viewportSize()?.width;
  if (wide) problem(`${name} @${w}: sideways scroll`);
  const file = path.join(OUT, `${name}-${w}.png`);
  await page.screenshot({ path: file, fullPage: full });
  return file;
}

export const text = async (loc) => (await loc.innerText().catch(() => "MISSING")).replace(/\s*\n\s*/g, " | ");
export const j = async (r) => { try { return await r.json(); } catch { return null; } };
export const caseIdFile = path.join(STATE, "case_id");
export const caseId = () => fs.readFileSync(caseIdFile, "utf8").trim();

export function finish(name) {
  fs.writeFileSync(path.join(OUT, `${name}.txt`), notes.join("\n") + "\n\nPROBLEMS (" + problems.length + "):\n" + problems.join("\n") + "\n");
  console.log(`\n${name}: ${notes.length} notes, ${problems.length} problems -> ${path.join(OUT, name + ".txt")}`);
}
