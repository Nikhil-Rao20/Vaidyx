// Phase 4 real-screen check: the voice buttons on the decision form (meeting control view), the guided question step and the
// Summary step, on the running app with the demo logins (read in code, never printed), laptop 1366 x 768 and phone 390 x 844, light and
// dark. Shots go to /data/vaidyx/night-v3/shots/phase4/. Reports page errors and sideways scroll. Run alone:
//   node docs/night-v3/tools/phase4_real_check.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";

const BASE = "http://127.0.0.1:7000";
const OUT = "/data/vaidyx/night-v3/shots/phase4";
fs.mkdirSync(OUT, { recursive: true });
const logins = Object.fromEntries(fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")
  .filter((l) => l.includes("\t") && !l.startsWith("#")).map((l) => l.split("\t")).map((c) => [c[0], c[1]]));
const findings = [];

async function login(ctx, user) {
  const r = await ctx.request.post(`${BASE}/api/auth/login`, { data: { username: user, password: logins[user], remember: true }, headers: { "X-Requested-With": "tb-nik" } });
  if (!r.ok()) throw new Error(`login ${user} ${r.status()}`);
}

async function shot(page, name) {
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false });
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  if (wide) findings.push(`${name}: sideways scroll`);
}

async function run(user, viewport, scheme, steps) {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport, colorScheme: scheme, locale: "en-IN", timezoneId: "Asia/Kolkata", reducedMotion: "reduce" });
  await login(ctx, user);
  const page = await ctx.newPage();
  const tag = `${viewport.width}-${scheme}`;
  page.on("pageerror", (e) => findings.push(`${user} ${tag}: page error ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|404|net::ERR_ABORTED/.test(m.text())) findings.push(`${user} ${tag}: console ${m.text().slice(0, 160)}`); });
  try { await steps(page, tag); } catch (e) { findings.push(`${user} ${tag}: ${e.message.split("\n")[0]}`); }
  await browser.close();
}

const VIEWS = [[{ width: 1366, height: 768 }, "light"], [{ width: 390, height: 844 }, "dark"], [{ width: 1366, height: 768 }, "dark"], [{ width: 390, height: 844 }, "light"]];

for (const [vp, scheme] of VIEWS) {
  // the treating consultant: the guided question step with its mic, the Summary step with its speakers, the Ask panel
  await run("tb-breast-doc", vp, scheme, async (page, tag) => {
    // the doctor's own Case File (the first row they own), never a hard-coded id of another department
    const list = await (await page.context().request.get(`${BASE}/api/tb/case-list`, { headers: { "X-Requested-With": "tb-nik" } })).json();
    const rows = list.rows || list.cases || [];
    const own = rows.find((r) => r.relation === "owner") || rows[0];
    const cid = own?.case_id || own?.id;
    if (!cid) throw new Error(`no Case File in the list (keys ${Object.keys(rows[0] || {}).join(",")})`);
    findings.push(`breast doctor's Case File: ${cid}`);
    await page.goto(`${BASE}/tb-nik/cases/${cid}/question`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    const mics = await page.getByRole("button", { name: /^Dictate/ }).count();
    findings.push(`question step ${tag}: ${mics} dictate buttons`);
    await shot(page, `question-${tag}`);
    await page.goto(`${BASE}/tb-nik/cases/${cid}/summary`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    const speakers = await page.getByRole("button", { name: /^Read aloud/ }).count();
    findings.push(`summary ${tag}: ${speakers} read-aloud buttons`);
    await shot(page, `summary-${tag}`);
    if (speakers && tag === "1366-light") {
      await page.getByRole("button", { name: /^Read aloud/ }).first().click();
      await page.waitForTimeout(1500);
      const stop = await page.getByRole("button", { name: /Stop reading/ }).count();
      findings.push(`summary read aloud clicked: ${stop ? "reading (Stop reading shown)" : "no Stop reading button"}`);
      await shot(page, `summary-reading-${tag}`);
      if (stop) await page.getByRole("button", { name: /Stop reading/ }).first().click();
    }
    await page.goto(`${BASE}/tb-nik/cases/${cid}/check`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1200);
    await shot(page, `check-${tag}`);
  });
  // the coordinator: the meeting control view's decision form with the mics and Read back
  await run("tb-mdt", vp, scheme, async (page, tag) => {
    await page.goto(`${BASE}/tb-nik/meetings/S20261016-a984`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    const dec = page.getByRole("tab", { name: "Decision" });
    if (await dec.count()) { await dec.first().click(); await page.waitForTimeout(800); }
    if (!(await page.locator("#d-text").count())) {  // this agenda case already has its decision recorded: try the previous case
      const prev = page.getByRole("button", { name: /^Previous$/ });
      if (await prev.count()) { await prev.first().click(); await page.waitForTimeout(1500); if (await dec.count()) { await dec.first().click(); await page.waitForTimeout(800); } }
    }
    const mics = await page.getByRole("button", { name: /^Dictate/ }).count();
    findings.push(`decision form ${tag}: ${mics} dictate buttons, read back ${await page.getByRole("button", { name: /^Read back$/ }).count()}`);
    await shot(page, `decision-${tag}`);
    const box = page.locator("#d-text");
    if (await box.count() && tag === "1366-light") {
      await box.fill("The board recommends completing the staging work-up before any treatment decision. Pre-Authorization under PM-JAY to be started.");
      await page.waitForTimeout(500);
      await shot(page, `decision-filled-${tag}`);
      const rb = page.getByRole("button", { name: /^Read back$/ });
      if (await rb.count()) { await rb.first().click(); await page.waitForTimeout(1500); findings.push(`read back clicked: stop shown ${await page.getByRole("button", { name: /Stop reading/ }).count()}`); await shot(page, `decision-readback-${tag}`); }
    }
    await page.goto(`${BASE}/tb-nik/requests`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1200);
    await shot(page, `requests-${tag}`);
  });
}
fs.writeFileSync(path.join(OUT, "findings.txt"), findings.join("\n") + "\n");
console.log(findings.join("\n"));
