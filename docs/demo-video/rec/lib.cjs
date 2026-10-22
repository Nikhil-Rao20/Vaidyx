// Recording kit for the Vaidyx-TB demo video. Every browser page is recorded with the Chrome DevTools screencast (sharp JPEG
// frames with their own time stamps, held until the next repaint), a drawn mouse pointer with a click ripple follows the real
// mouse, and the helpers move, click and type at a human pace. Passwords are read from the login files here and never printed.
// Run with NODE_PATH=<repo>/web/tb-nik/node_modules.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = "/data/vaidyx/demo_video";  // outputs; the scripts live in the repo, docs/demo-video/rec
const RUN = process.env.DEMO_RUN || "run1";
const RAW = path.join(ROOT, "raw", RUN);
fs.mkdirSync(RAW, { recursive: true });
const MARKS = path.join(RAW, "marks.jsonl");
const STATE = path.join(RAW, "state.json");
const V = "http://127.0.0.1:7000";
const H = "http://127.0.0.1:7130";

// Full scenes: 1440 x 810 CSS pixels at 4/3 = 1920 x 1080 frames. Split halves: 1080 x 1215 CSS = 1440 x 1620, scaled to 960 x 1080.
const DPR = 4 / 3;
const FULL = { width: 1440, height: 810 };
const HALF = { width: 1080, height: 1215 };

function now() { return Date.now() / 1000; }
function mark(label, extra = {}) {
  fs.appendFileSync(MARKS, JSON.stringify({ t: now(), label, ...extra }) + "\n");
  console.log(`[mark ${new Date().toISOString().slice(11, 19)}] ${label}`);
}
function state() { try { return JSON.parse(fs.readFileSync(STATE, "utf8")); } catch { return {}; } }
function save(patch) { const s = { ...state(), ...patch }; fs.writeFileSync(STATE, JSON.stringify(s, null, 1)); return s; }

function vaidyxPassword(user) {
  for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) {
    if (!line || line.startsWith("#")) continue;
    const [u, p] = line.split("\t");
    if (u === user && p) return p;
  }
  throw new Error(`no Vaidyx demo login for ${user}`);
}
function hisPassword(email) {
  for (const line of fs.readFileSync("/home/bharath.tangella/vaidyx/Vaidyx/data/his_mock/logins.tsv", "utf8").split("\n").slice(1)) {
    const [e, , p] = line.split("\t");
    if (e === email && p) return p.trim();
  }
  throw new Error(`no HIS login for ${email}`);
}

// The drawn pointer: an arrow that follows mousemove (kept across navigations in sessionStorage) and a teal ripple on mousedown.
const CURSOR_JS = `(() => {
  if (window.__demoCursor) return; window.__demoCursor = 1;
  const ARROW = '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="30" viewBox="0 0 26 30"><path d="M3 2 L3 23 L8.6 17.6 L12.4 26.4 L16.4 24.7 L12.7 16.1 L20.2 16.1 Z" fill="#0f172a" stroke="#ffffff" stroke-width="1.8" stroke-linejoin="round"/></svg>';
  let x = -60, y = -60;
  try { x = +(sessionStorage.getItem('__dmx') ?? -60); y = +(sessionStorage.getItem('__dmy') ?? -60); } catch (e) {}
  function el() {
    let c = document.getElementById('__demo_cursor');
    if (!c && document.documentElement) {
      c = document.createElement('div'); c.id = '__demo_cursor';
      const s = c.style; s.position = 'fixed'; s.left = '0px'; s.top = '0px'; s.width = '26px'; s.height = '30px'; s.zIndex = '2147483647';
      s.pointerEvents = 'none'; s.willChange = 'transform'; s.filter = 'drop-shadow(0 2px 3px rgba(0,0,0,.35))';
      c.innerHTML = ARROW; document.documentElement.appendChild(c);
    }
    return c;
  }
  function place() { const c = el(); if (c) c.style.transform = 'translate(' + (x - 3) + 'px,' + (y - 2) + 'px)'; }
  addEventListener('mousemove', (e) => { x = e.clientX; y = e.clientY; try { sessionStorage.setItem('__dmx', x); sessionStorage.setItem('__dmy', y); } catch (er) {} place(); }, true);
  addEventListener('mousedown', (e) => {
    const r = document.createElement('div'); const s = r.style;
    s.position = 'fixed'; s.left = (e.clientX - 20) + 'px'; s.top = (e.clientY - 20) + 'px'; s.width = '40px'; s.height = '40px'; s.borderRadius = '50%';
    s.border = '3px solid rgba(1,180,194,.95)'; s.background = 'rgba(1,203,211,.20)'; s.zIndex = '2147483646'; s.pointerEvents = 'none';
    s.transform = 'scale(.35)'; s.opacity = '1'; s.transition = 'transform .5s cubic-bezier(.2,.8,.2,1), opacity .5s ease-out';
    document.documentElement.appendChild(r);
    requestAnimationFrame(() => requestAnimationFrame(() => { s.transform = 'scale(1.3)'; s.opacity = '0'; }));
    setTimeout(() => r.remove(), 700);
  }, true);
  setInterval(place, 250);
  addEventListener('DOMContentLoaded', place);
})();`;

const browsers = [];
async function browser(opts = {}) {
  const args = ["--autoplay-policy=no-user-gesture-required", "--disable-features=Translate", "--hide-scrollbars", `--force-device-scale-factor=${opts.dsf || 1.3333333}`];
  if (opts.camera) args.push("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-video-capture=${opts.camera}`);
  if (opts.mic) args.push(`--use-file-for-fake-audio-capture=${opts.mic}`);
  const b = await chromium.launch({ headless: true, args });
  browsers.push(b);
  return b;
}

const recs = [];
/** A recorded page: its own browser context (cookies), the pointer, a screencast into raw/<run>/<name>/. */
async function session(name, { base = V, size = FULL, camera, mic, permissions, dsf, mobile } = {}) {
  const b = await browser({ camera, mic, dsf });
  const ctx = await b.newContext({
    viewport: size, deviceScaleFactor: dsf || DPR, isMobile: !!mobile, hasTouch: !!mobile, baseURL: base, bypassCSP: true, locale: "en-IN", timezoneId: "Asia/Kolkata",
    colorScheme: "light", acceptDownloads: true, permissions: permissions || (camera ? ["camera", "microphone"] : []),
  });
  await ctx.addInitScript(CURSOR_JS);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log(`[${name}] pageerror ${String(e).slice(0, 200)}`));
  const rec = await record(page, name);
  const s = { name, page, ctx, browser: b, rec, size };
  recs.push(s);
  return s;
}

async function record(page, name) {
  const dir = path.join(RAW, name);
  fs.mkdirSync(dir, { recursive: true });
  let n = fs.readdirSync(dir).filter((f) => f.endsWith(".jpg")).length;
  const idx = fs.openSync(path.join(dir, "frames.tsv"), "a");
  const cdp = await page.context().newCDPSession(page);
  let stopped = false;
  cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
    if (stopped) return;
    const f = `f${String(++n).padStart(7, "0")}.jpg`;
    fs.writeFileSync(path.join(dir, f), Buffer.from(data, "base64"));
    fs.writeSync(idx, `${(metadata && metadata.timestamp) || now()}\t${f}\n`);
    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: 1920, maxHeight: 1620, everyNthFrame: 1 });
  return { dir, async stop() { stopped = true; await cdp.send("Page.stopScreencast").catch(() => {}); fs.closeSync(idx); } };
}

async function resize(s, size) { await s.page.setViewportSize(size); s.size = size; mark(`resize:${s.name}`, size); await s.page.waitForTimeout(400); }

// Pointer and input at a human pace.
const pos = new WeakMap();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function moveTo(page, x, y, ms) {
  const vp = page.viewportSize();
  const p = pos.get(page) || { x: vp.width * 0.62, y: vp.height * 0.72 };
  const d = Math.hypot(x - p.x, y - p.y);
  const dur = ms ?? Math.min(950, Math.max(260, 220 + d * 0.75));
  const steps = Math.max(8, Math.round(dur / 16));
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    await page.mouse.move(p.x + (x - p.x) * e, p.y + (y - p.y) * e);
    await sleep(dur / steps);
  }
  pos.set(page, { x, y });
}
async function hover(page, loc, ms) {
  await loc.waitFor({ state: "visible", timeout: 60_000 });
  await loc.scrollIntoViewIfNeeded().catch(() => {});
  await sleep(150);
  const b = await loc.boundingBox();
  if (!b) throw new Error("no box for the element");
  await moveTo(page, b.x + Math.min(b.width / 2, 120), b.y + b.height / 2, ms);
}
async function click(page, loc, { pause = 260, after = 450, ms } = {}) {
  await hover(page, loc, ms);
  await sleep(pause);
  await loc.click({ timeout: 30_000 });
  await sleep(after);
}
async function type(page, loc, text, { delay = 42, clear = true, secret = false } = {}) {
  await click(page, loc, { after: 150 });
  if (clear) { await page.keyboard.press("Control+A"); await page.keyboard.press("Delete"); }
  await page.keyboard.type(text, { delay: secret ? 70 : delay });
  await sleep(250);
}
/** Smooth wheel scrolling by `px` CSS pixels (negative = up). */
async function scroll(page, px, { ms = 900 } = {}) {
  const steps = Math.max(6, Math.round(ms / 30));
  for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, px / steps); await sleep(ms / steps); }
  await sleep(250);
}
async function scrollTo(page, loc, { block = "center" } = {}) {
  await loc.waitFor({ state: "attached", timeout: 60_000 });
  await loc.evaluate((el, b) => el.scrollIntoView({ behavior: "smooth", block: b }), block);
  await sleep(900);
}

async function closeAll() {
  for (const s of recs) await s.rec.stop().catch(() => {});
  for (const b of browsers) await b.close().catch(() => {});
}

module.exports = { ROOT, RAW, V, H, DPR, FULL, HALF, mark, state, save, vaidyxPassword, hisPassword, session, record, resize, moveTo, hover, click, type, scroll, scrollTo, sleep, closeAll };
