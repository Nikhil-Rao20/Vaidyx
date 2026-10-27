// The voice check in the browser (night-v3 item 4.5, docs/night-v3/research/08_voice.md section 8.2): the microphone and speaker
// buttons on the real screens, with Chromium's fake microphone.
//  - TBNIK_MOCK=1: the mock server of e2e/support plus mocked /api/tb/audio/status, /stt and /tts answers (a small WAV made in code).
//    Screenshots of voice off, voice on, listening and transcribing, the microphone errors, the speaker and the service errors.
//  - real (default): the app on :7000 with the audio service. A fixed synthetic sentence is spoken by the service's /tts, resampled
//    here to 48,000 Hz mono 16-bit PCM with one second of silence before and after, and fed to Chromium as the microphone
//    (--use-file-for-fake-audio-capture=<file>%noloop). The login is the demo coordinator (tb-mdt), read from
//    ~/vaidyx/.tb_v2_demo_logins in code (TBNIK_USER / TBNIK_PASSWORD override it); nothing secret is printed. It asks one real
//    question in one demo Case File (TBNIK_VOICE_CASE, default TB-2026-0005) and changes nothing else.
// TBNIK_VOICE_STATIC=<folder>: serve the built site from that folder instead of static/tb-nik (a build made with
// `npx vite build --outDir <folder> --emptyOutDir` before the app's own build is refreshed); the API stays the real one.
// Run (from web/tb-nik, one Playwright process at a time):
//   LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts e2e/shots/voice.spec.ts
//   LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib npx playwright test -c e2e/playwright.config.ts e2e/shots/voice.spec.ts
// Files: docs/ui/build/shots/voice-<state>-<theme>-<width>.png (TBNIK_SHOTS moves them). The microphone WAV is written under
// os.tmpdir(), never in the repository or data/.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, expect, test, type Browser, type BrowserContext, type Locator, type Page, type Route } from "@playwright/test";
import { MOCK, SHOTS, SIZES, prepare, shoot, watchConsole } from "../support/helpers";
import { CID, MID, caseFileUnsent, meetingState, routeCaseFile, routeMeetings } from "../support/f2";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../../../..");
const LAPTOP = SIZES[0];
const PHONE = SIZES[2];
const LAPTOP_PHONE = [LAPTOP, PHONE];
const STATIC_DIR = process.env.TBNIK_VOICE_STATIC ? path.resolve(process.env.TBNIK_VOICE_STATIC) : "";
const BASE = process.env.TBNIK_BASE_URL || "http://127.0.0.1:7000";
const AUDIO_URL = (process.env.TB_AUDIO_URL || "http://127.0.0.1:7120").replace(/\/$/, "");
const TOKEN_FILE = process.env.TB_AUDIO_TOKEN_FILE || path.join(REPO, "data/tumour_board/audio_token.json");
const AUDIT_FILE = path.join(process.env.TB_DATA_ROOT || path.join(REPO, "data/tumour_board"), "org_audit.jsonl");
const REAL_CASE = process.env.TBNIK_VOICE_CASE || "TB-2026-0005";
// Synthetic, no patient data: the words the fake microphone says, and the number that must come back exactly.
const SENTENCE = "What did the HPE report say about the margins, and is the tumour size of 2.8 cm noted?";
const NUMBERS = ["2.8"];
const DICTATED = "Is ECOG noted in the HPE report?";

// The sentences the controls show (web/tb-nik/src/lib/voice.ts VOICE_TEXT), copied so a change of wording is seen here.
const T = {
  heard: "Heard this. Check it before you send.",
  blocked: "The microphone is blocked. Allow the microphone for this site in the address bar, then try again.",
  noMic: "No microphone found. Plug one in or choose one in your system settings.",
  inUse: "The microphone is in use or not working. Close other apps that use it and try again.",
  insecure: "The microphone needs a secure connection. Open Vaidyx through localhost or https.",
  busy: "Too many voice requests. Wait a minute, or type.",
  unavailable: "Voice is not available right now. You can type instead.",
  allowVoices: "Tap to allow agent voices",
  stopReading: "Stop reading",
};

// ------------------------------------------------------------------------------------------------------------------ WAV

/** A mono 16-bit PCM WAV from samples in [-1, 1]. */
function wav(samples: Float32Array, rate: number, channels = 1): Buffer {
  const n = samples.length;
  const buf = Buffer.alloc(44 + n * 2 * channels);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 2 * channels, 4); buf.write("WAVE", 8); buf.write("fmt ", 12);
  buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(channels, 22); buf.writeUInt32LE(rate, 24);
  buf.writeUInt32LE(rate * 2 * channels, 28); buf.writeUInt16LE(2 * channels, 32); buf.writeUInt16LE(16, 34); buf.write("data", 36);
  buf.writeUInt32LE(n * 2 * channels, 40);
  for (let i = 0; i < n; i++) {
    const v = Math.round(Math.max(-1, Math.min(1, samples[i])) * 32767);
    for (let c = 0; c < channels; c++) buf.writeInt16LE(v, 44 + (i * channels + c) * 2);
  }
  return buf;
}

/** The samples and rate of a PCM 16-bit WAV (the first channel), read chunk by chunk. */
function readWav(data: Buffer): { samples: Float32Array; rate: number } {
  if (data.toString("ascii", 0, 4) !== "RIFF" || data.toString("ascii", 8, 12) !== "WAVE") throw new Error("not a WAV");
  let off = 12; let rate = 0; let channels = 1; let bits = 16;
  while (off + 8 <= data.length) {
    const id = data.toString("ascii", off, off + 4);
    let size = data.readUInt32LE(off + 4);
    const body = off + 8;
    if (id === "fmt ") { channels = data.readUInt16LE(body + 2); rate = data.readUInt32LE(body + 4); bits = data.readUInt16LE(body + 14); }
    if (id === "data") {
      if (bits !== 16) throw new Error("only 16-bit PCM");
      if (size === 0xffffffff || body + size > data.length) size = data.length - body; // a streamed header
      const frames = Math.floor(size / (2 * channels));
      const out = new Float32Array(frames);
      for (let i = 0; i < frames; i++) out[i] = data.readInt16LE(body + i * 2 * channels) / 32768;
      return { samples: out, rate };
    }
    off = body + size + (size % 2);
  }
  throw new Error("no data chunk");
}

/** Linear interpolation to another rate (enough for speech made at 24 kHz and played at 48 kHz). */
function resample(x: Float32Array, from: number, to: number): Float32Array {
  const n = Math.round((x.length * to) / from);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const t = (i * from) / to;
    const a = Math.floor(t);
    const b = Math.min(a + 1, x.length - 1);
    out[i] = x[a] + (x[b] - x[a]) * (t - a);
  }
  return out;
}

function padded(x: Float32Array, rate: number, seconds = 1): Float32Array {
  const pad = Math.round(rate * seconds);
  const out = new Float32Array(x.length + 2 * pad);
  out.set(x, pad);
  return out;
}

/** A short tone as speech for the mocked speaker (seconds long, 16 kHz). */
function toneWav(seconds: number): Buffer {
  const rate = 16000;
  const x = new Float32Array(Math.round(seconds * rate));
  for (let i = 0; i < x.length; i++) x[i] = 0.2 * Math.sin((2 * Math.PI * 440 * i) / rate);
  return wav(x, rate);
}

/** The fake microphone's file: the service speaks SENTENCE, here resampled to 48 kHz mono (or 44.1 kHz stereo). */
async function microphoneFile(kind: "48k-mono" | "44k-stereo" = "48k-mono"): Promise<{ file: string; seconds: number }> {
  let token = "";
  try { token = String(JSON.parse(fs.readFileSync(TOKEN_FILE, "utf8")).token || "").trim(); } catch { /* checked below */ }
  if (!token) throw new Error("The audio token file is missing or unreadable.");
  const r = await fetch(`${AUDIO_URL}/tts`, { method: "POST", headers: { "Content-Type": "application/json", "X-Audio-Token": token }, body: JSON.stringify({ text: SENTENCE, voice: "af_heart" }) });
  if (!r.ok) throw new Error(`The audio service answered ${r.status} to /tts.`);
  const { samples, rate } = readWav(Buffer.from(await r.arrayBuffer()));
  const [to, channels] = kind === "48k-mono" ? [48000, 1] : [44100, 2];
  const x = padded(resample(samples, rate, to), to);
  const dir = path.join(os.tmpdir(), "tbnik-voice");
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const file = path.join(dir, `question-${kind}.wav`);
  fs.writeFileSync(file, wav(x, to, channels), { mode: 0o600 });
  return { file, seconds: x.length / to };
}

// ------------------------------------------------------------------------------------------------------------- routes

const STATIC_TYPES: Record<string, string> = { ".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".png": "image/png", ".json": "application/json", ".webmanifest": "application/manifest+json" };

/** With TBNIK_VOICE_STATIC, the site's files come from that build folder (registered last, so it runs first). */
async function serveBuild(page: Page) {
  if (!STATIC_DIR) return;
  await page.route((u) => u.pathname.startsWith("/static/tb-nik/") || u.pathname === "/tb-nik" || (u.pathname.startsWith("/tb-nik/") && !u.pathname.startsWith("/tb-nik/api/")), (route) => {
    const p = new URL(route.request().url()).pathname;
    const file = p.startsWith("/static/tb-nik/") ? path.join(STATIC_DIR, decodeURIComponent(p.slice("/static/tb-nik/".length))) : path.join(STATIC_DIR, "index.html");
    if (!file.startsWith(STATIC_DIR) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return route.fulfill({ status: 404, body: "" });
    return route.fulfill({ status: 200, contentType: STATIC_TYPES[path.extname(file)] ?? "application/octet-stream", body: fs.readFileSync(file) });
  });
}

type Reply = { status: number; body: unknown };
type VoiceOptions = { enabled?: boolean; sttDelayMs?: number; stt?: Reply; tts?: Reply | "wav"; ttsParts?: number; ttsSeconds?: number };
type Counts = { stt: number; tts: number; ttsBodies: unknown[] };

const STATUS_ON = { enabled: true, stt: "ready", tts: "ready", limits: { stt_seconds: 60, stt_bytes: 4194304, tts_chars: 2000 }, cohere: false, voices: ["af_heart", "bf_emma", "am_michael"] };
const STATUS_OFF = { enabled: false, stt: "off", tts: "off", limits: { stt_seconds: 60, stt_bytes: 4194304, tts_chars: 2000 }, cohere: false, voices: [] };

/** Mocked answers of the app's voice routes; returns live counters of the dictation and speech requests. */
async function voiceRoutes(page: Page, o: VoiceOptions = {}): Promise<Counts> {
  const counts: Counts = { stt: 0, tts: 0, ttsBodies: [] };
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/tb/audio/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    const m = route.request().method();
    if (p.endsWith("/audio/status") && m === "GET") return json(route, o.enabled === false ? STATUS_OFF : STATUS_ON);
    if (p.endsWith("/audio/stt") && m === "POST") {
      counts.stt += 1;
      if (o.sttDelayMs) await new Promise((r) => setTimeout(r, o.sttDelayMs));
      const r = o.stt ?? { status: 200, body: { text: DICTATED, segments: [], duration: 3.1, engine: "whisper-large-v3-turbo", took_ms: 140, code: null } };
      return json(route, r.body, r.status).catch(() => undefined);
    }
    if (p.endsWith("/audio/tts") && m === "POST") {
      counts.tts += 1;
      let b: unknown = null;
      try { b = JSON.parse(route.request().postData() || "null"); } catch { b = null; }
      counts.ttsBodies.push(b);
      const t = o.tts ?? "wav";
      if (t !== "wav") return json(route, t.body, t.status);
      const part = (b && typeof b === "object" && "part" in b ? Number((b as { part: unknown }).part) : 0) || 0;
      return route.fulfill({ status: 200, contentType: "audio/wav", headers: { "X-Parts": String(o.ttsParts ?? 1), "X-Part": String(part) }, body: toneWav(o.ttsSeconds ?? 0.4) }).catch(() => undefined);
    }
    return json(route, { detail: "Not Found" }, 404);
  });
  return counts;
}

/** Counts the Ask requests (POST /chats) and keeps their bodies; the request still goes to the mock or the app. */
async function countAsks(page: Page, caseId: string): Promise<{ n: number; bodies: string[] }> {
  const asks = { n: 0, bodies: [] as string[] };
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (r.method() === "POST" && u.pathname === `/api/tb/cases/${caseId}/chats`) { asks.n += 1; asks.bodies.push(r.postData() || ""); }
  });
  return asks;
}

async function openCase(page: Page, voice: VoiceOptions, sub = "") {
  await prepare(page, { role: "treating" });
  await routeCaseFile(page, { caseFile: caseFileUnsent() });
  const counts = await voiceRoutes(page, voice);
  await serveBuild(page);
  await page.goto(`/tb-nik/cases/${CID}${sub}`);
  await page.getByTestId("casefile-page").first().waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  return counts;
}

async function openAsk(page: Page) {
  await page.getByTestId("ask-bubble").click();
  const panel = page.getByTestId("side-panel").getByTestId("ask-panel");
  await expect(panel).toBeVisible();
  return panel;
}

const micIn = (scope: Locator | Page) => scope.getByRole("button", { name: /^Dictate/ });

/** The wrapper of a dictation button (it carries data-state: idle, asking, listening, transcribing, added, error). */
const micWrap = (scope: Locator) => scope.locator("span[data-state]:has(> span > button[aria-label^='Dictate'])").first();

/** The light theme for the single screenshots taken after helpers.shoot (which leaves the last theme it drew, dark). */
async function light(page: Page) {
  await page.evaluate(() => { document.documentElement.setAttribute("data-theme", "light"); try { localStorage.setItem("tbnik.theme", "light"); } catch { /* none */ } });
}

function words(s: string): string[] {
  return s.toLowerCase().replace(/[^a-z0-9.\s]/g, " ").replace(/\.(?!\d)/g, " ").split(/\s+/).filter(Boolean);
}

// ===================================================================================================== mocked mode

// The mocked tests use Chromium's fake microphone (a beep); the real run launches its own browser with the speech file.
test.use({ launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] }, permissions: ["microphone"] });

test.describe("voice, mocked", () => {
  test.skip(!MOCK, "the mocked screens run with TBNIK_MOCK=1");

  test("1. voice off: no microphone or speaker on the Ask box, the question step, the decision form", async ({ page }) => {
    const errors = watchConsole(page);
    await openCase(page, { enabled: false });
    const panel = await openAsk(page);
    await expect(panel.locator("#ask-input")).toBeVisible();
    await expect(micIn(panel)).toHaveCount(0);
    await expect(panel.getByRole("button", { name: /^(Read aloud.*|Read back|Stop reading)$/ })).toHaveCount(0);
    await shoot(page, "voice", "off-ask", { sizes: LAPTOP_PHONE, themes: ["light"], fullPage: false });

    await page.goto(`/tb-nik/cases/${CID}/question`);
    await expect(page.getByTestId("question-input")).toBeVisible();
    await expect(micIn(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^(Read aloud.*|Read back)$/ })).toHaveCount(0);

    await page.unrouteAll({ behavior: "ignoreErrors" });
    await prepare(page, { role: "coordinator" });
    await routeCaseFile(page);
    await routeMeetings(page, { state: meetingState("in_session") });
    await voiceRoutes(page, { enabled: false });
    await serveBuild(page);
    await page.goto(`/tb-nik/meetings/${MID}`);
    await page.getByTestId("control-view").first().waitFor({ timeout: 20_000 });
    await page.getByRole("tab", { name: "Decision" }).click();
    await expect(page.getByTestId("decision-form")).toBeVisible();
    await expect(micIn(page.getByTestId("decision-form"))).toHaveCount(0);
    await expect(page.getByTestId("decision-form").getByRole("button", { name: /^(Read aloud.*|Read back)$/ })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("2. voice on: the Ask box shows the microphone; idle, listening and transcribing", async ({ page }) => {
    const errors = watchConsole(page);
    const counts = await openCase(page, { sttDelayMs: 4000 });
    const asks = await countAsks(page, CID);
    const panel = await openAsk(page);
    const mic = micIn(panel);
    await expect(mic).toBeVisible();
    await expect(mic).toHaveAttribute("title", /Ctrl\+Alt\+M/);
    await shoot(page, "voice", "on-ask", { sizes: LAPTOP_PHONE, fullPage: false });
    await page.setViewportSize(LAPTOP);
    await light(page);
    await mic.click();
    await expect(micWrap(panel)).toHaveAttribute("data-state", "listening");
    await expect(panel.getByText(/^Listening \d+:\d\d of 1:00$/)).toBeVisible();
    await expect(panel.locator("[role='meter']")).toHaveCount(1);
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(SHOTS, "voice-listening-light-1366.png") });
    await mic.click();
    await expect(micWrap(panel)).toHaveAttribute("data-state", "transcribing");
    await expect(panel.getByText("Transcribing", { exact: true }).first()).toBeVisible();
    await page.screenshot({ path: path.join(SHOTS, "voice-transcribing-light-1366.png") });
    await expect(panel.locator("#ask-input")).toHaveValue(DICTATED, { timeout: 10_000 });
    await expect(panel.getByTestId("ask-heard")).toHaveText(T.heard);
    await page.screenshot({ path: path.join(SHOTS, "voice-heard-light-1366.png") });
    expect(counts.stt).toBe(1);
    expect(asks.n).toBe(0); // the words heard are never sent by themselves
    expect(errors).toEqual([]);
  });

  test("4. Esc while listening: nothing is sent and the box is unchanged", async ({ page }) => {
    const counts = await openCase(page, {});
    const panel = await openAsk(page);
    await panel.locator("#ask-input").fill("Typed first. ");
    await micIn(panel).click();
    await expect(micWrap(panel)).toHaveAttribute("data-state", "listening");
    await page.waitForTimeout(800);
    await page.keyboard.press("Escape");
    await expect(micWrap(panel)).toHaveAttribute("data-state", "idle");
    await page.waitForTimeout(800);
    expect(counts.stt).toBe(0);
    await expect(panel.locator("#ask-input")).toHaveValue("Typed first. ");
    await expect(page.getByTestId("side-panel")).toBeVisible(); // Esc stopped the dictation, not the panel
  });

  const permissionCases: Array<[string, string]> = [["NotAllowedError", T.blocked], ["NotFoundError", T.noMic], ["NotReadableError", T.inUse]];
  for (const [name, sentence] of permissionCases) {
    test(`5. microphone error ${name}: its plain sentence`, async ({ page }) => {
      await page.addInitScript((n) => {
        if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("test", n));
      }, name);
      const counts = await openCase(page, {});
      const panel = await openAsk(page);
      await micIn(panel).click();
      await expect(panel.getByRole("alert").filter({ hasText: sentence })).toBeVisible();
      await expect(micWrap(panel)).toHaveAttribute("data-state", "error");
      expect(counts.stt).toBe(0);
      if (name === "NotAllowedError") await shoot(page, "voice", "mic-blocked", { sizes: LAPTOP_PHONE, fullPage: false });
    });
  }

  test("5. no mediaDevices (not a secure connection): the secure-connection sentence", async ({ page }) => {
    await page.addInitScript(() => { Object.defineProperty(Navigator.prototype, "mediaDevices", { get: () => undefined, configurable: true }); });
    await openCase(page, {});
    const panel = await openAsk(page);
    await micIn(panel).click();
    await expect(panel.getByRole("alert").filter({ hasText: T.insecure })).toBeVisible();
  });

  test("6. edit then send: the Ask request carries the edited text", async ({ page }) => {
    await openCase(page, {});
    const asks = await countAsks(page, CID);
    const panel = await openAsk(page);
    const mic = micIn(panel);
    await mic.click();
    await expect(micWrap(panel)).toHaveAttribute("data-state", "listening");
    await page.waitForTimeout(600);
    await mic.click();
    const box = panel.locator("#ask-input");
    await expect(box).toHaveValue(DICTATED);
    expect(asks.n).toBe(0);
    await box.press("End");
    await box.pressSequentially(" Quote the line.");
    await panel.getByRole("button", { name: /^Ask$/ }).click();
    await expect.poll(() => asks.n).toBe(1);
    expect(JSON.parse(asks.bodies[0]).question).toBe(`${DICTATED} Quote the line.`);
  });

  test("7. speaker: one play per sentence, Stop reading stops the rest, a blocked play offers the tap", async ({ page }) => {
    await page.addInitScript(() => {
      const w = window as unknown as { __plays: string[] };
      w.__plays = [];
      const orig = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function (this: HTMLMediaElement) { w.__plays.push(this.src); return orig.call(this); };
    });
    const counts = await openCase(page, { ttsParts: 3, ttsSeconds: 0.6 });
    const panel = await openAsk(page);
    const speak = panel.getByTestId("chat-thread").first().getByRole("button", { name: /^Read aloud/ });
    await expect(speak).toBeVisible();
    await shoot(page, "voice", "speaker-idle", { sizes: LAPTOP_PHONE, fullPage: false });
    await page.setViewportSize(LAPTOP);
    await light(page);
    const playsBefore = await page.evaluate(() => (window as unknown as { __plays: string[] }).__plays.length);
    await speak.click();
    await expect(panel.getByTestId("chat-thread").first().getByRole("button", { name: T.stopReading })).toBeVisible();
    await page.screenshot({ path: path.join(SHOTS, "voice-speaker-reading-light-1366.png") });
    await expect(panel.getByTestId("chat-thread").first().getByRole("button", { name: /^Read aloud/ })).toBeVisible({ timeout: 15_000 });
    // the silent unlock inside the click, then one play per sentence, in order
    const plays = await page.evaluate((n) => (window as unknown as { __plays: string[] }).__plays.slice(n), playsBefore);
    expect(plays.length).toBe(1 + 3);
    expect(counts.tts).toBe(3);
    expect(counts.ttsBodies.map((b) => (b as { part: number }).part)).toEqual([0, 1, 2]);

    // Stop reading after the first sentence: no more sentences are fetched or played
    const ttsBefore = counts.tts;
    const playsMid = await page.evaluate(() => (window as unknown as { __plays: string[] }).__plays.length);
    await panel.getByTestId("chat-thread").first().getByRole("button", { name: /^Read aloud/ }).click();
    const stop = panel.getByTestId("chat-thread").first().getByRole("button", { name: T.stopReading });
    await expect(stop).toBeVisible();
    await stop.click();
    await expect(panel.getByTestId("chat-thread").first().getByRole("button", { name: /^Read aloud/ })).toBeVisible();
    await page.waitForTimeout(1500);
    expect(counts.tts - ttsBefore).toBeLessThanOrEqual(2); // the first and at most the one fetched ahead
    const after = await page.evaluate(() => (window as unknown as { __plays: string[] }).__plays.length);
    expect(after - playsMid).toBeLessThanOrEqual(2); // the unlock and the first sentence, nothing after the stop
  });

  test("7. speaker: a play() refused with NotAllowedError shows the tap to allow", async ({ page }) => {
    await page.addInitScript(() => {
      HTMLMediaElement.prototype.play = function () { return Promise.reject(new DOMException("test", "NotAllowedError")); };
    });
    await openCase(page, { ttsParts: 2 });
    const panel = await openAsk(page);
    await panel.getByTestId("chat-thread").first().getByRole("button", { name: /^Read aloud/ }).click();
    await expect(panel.getByRole("button", { name: T.allowVoices })).toBeVisible();
    await shoot(page, "voice", "speaker-blocked", { sizes: [LAPTOP], fullPage: false });
  });

  const serviceCases: Array<[number, string, string]> = [[429, "rate_limited", T.busy], [503, "voice_unavailable", T.unavailable]];
  for (const [status, code, sentence] of serviceCases) {
    test(`8. service answers ${status}: its plain sentence, the typed text kept`, async ({ page }) => {
      const counts = await openCase(page, { stt: { status, body: { detail: { message: "test", code } } } });
      const panel = await openAsk(page);
      const box = panel.locator("#ask-input");
      await box.fill("My own words");
      await box.press("End");
      const mic = micIn(panel);
      await mic.click();
      await expect(micWrap(panel)).toHaveAttribute("data-state", "listening");
      await page.waitForTimeout(600);
      await mic.click();
      await expect(panel.getByRole("alert").filter({ hasText: sentence })).toBeVisible();
      await expect(box).toHaveValue("My own words");
      expect(counts.stt).toBe(1);
      if (status === 429) await shoot(page, "voice", "service-busy", { sizes: LAPTOP_PHONE, fullPage: false });
    });
  }
});

// ======================================================================================================= real mode

function demoPassword(user: string): string {
  const file = path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins");
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    if (!line || line.startsWith("#")) continue;
    const [u, p] = line.split("\t");
    if (u === user && p) return p;
  }
  throw new Error(`No demo login for ${user}`);
}

test.describe("voice, real app with a fake microphone", () => {
  test.skip(MOCK, "the real run needs the app on :7000 and the audio service");
  test.describe.configure({ mode: "serial" });
  let browser: Browser;
  let context: BrowserContext;
  let mic: { file: string; seconds: number };
  let startedAt = 0;

  test.beforeAll(async () => {
    test.setTimeout(120_000);
    mic = await microphoneFile(process.env.TBNIK_VOICE_WAV === "44k-stereo" ? "44k-stereo" : "48k-mono");
    browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-audio-capture=${mic.file}%noloop`] });
    context = await browser.newContext({ baseURL: BASE, viewport: LAPTOP, locale: "en-IN", timezoneId: "Asia/Kolkata", reducedMotion: "reduce", permissions: ["microphone"] });
    const user = process.env.TBNIK_USER || "tb-mdt";
    const password = process.env.TBNIK_PASSWORD || demoPassword(user);
    const r = await context.request.post("/api/auth/login", { data: { username: user, password, remember: false }, headers: { "X-Requested-With": "tb-nik" } });
    if (!r.ok()) throw new Error(`Sign-in failed with HTTP ${r.status()}`);
  });

  test.afterAll(async () => { await context?.close(); await browser?.close(); });

  async function openReal(): Promise<{ page: Page; panel: Locator; stt: { n: number }; asks: { n: number; bodies: string[] }; errors: string[] }> {
    const page = await context.newPage();
    const errors = watchConsole(page);
    await page.route("**/api/tb/me", async (route) => {
      const res = await route.fetch();
      if (res.status() !== 200) return route.fulfill({ response: res });
      return route.fulfill({ response: res, json: { ...(await res.json()), must_change_password: false, setup_needed: false } });
    });
    const stt = { n: 0 };
    // the real dictation request, held 1.5 s so "Transcribing" can be seen, then sent on to the app unchanged
    await page.route("**/api/tb/audio/stt", async (route) => {
      stt.n += 1;
      await new Promise((r) => setTimeout(r, 1500));
      const res = await route.fetch();
      return route.fulfill({ response: res });
    });
    await serveBuild(page);
    const asks = await countAsks(page, REAL_CASE);
    await page.goto(`/tb-nik/cases/${REAL_CASE}`);
    await page.getByTestId("casefile-page").first().waitFor({ timeout: 30_000 });
    await page.waitForLoadState("networkidle").catch(() => {});
    const panel = await openAsk(page);
    return { page, panel, stt, asks, errors };
  }

  test("3, 6 and 9. dictate a question with the fake microphone, edit it, send it; the audit line holds no words", async () => {
    test.setTimeout(300_000);
    const { page, panel, stt, asks, errors } = await openReal();
    const micBtn = micIn(panel);
    await expect(micBtn, "the Ask box has no microphone yet: is the site built with item 4.4?").toBeVisible();
    startedAt = Date.now();
    await micBtn.click();
    await expect(micWrap(panel)).toHaveAttribute("data-state", "listening", { timeout: 15_000 });
    await expect(panel.getByText(/^Listening \d+:\d\d of 1:00$/)).toBeVisible();
    // the meter moves while the file plays
    let peak = 0;
    for (let i = 0; i < 12; i++) {
      await page.waitForTimeout(250);
      const v = Number(await panel.locator("[role='meter']").getAttribute("aria-valuenow").catch(() => "0"));
      peak = Math.max(peak, v || 0);
    }
    expect(peak, "the level meter never moved").toBeGreaterThan(0);
    await page.screenshot({ path: path.join(SHOTS, "voice-real-listening-light-1366.png") });
    await page.waitForTimeout(Math.max(0, mic.seconds * 1000 - 3000 + 1200));
    await micBtn.click();
    await expect(micWrap(panel)).toHaveAttribute("data-state", "transcribing");
    await expect(panel.getByText("Transcribing", { exact: true }).first()).toBeVisible();
    const box = panel.locator("#ask-input");
    await expect(box).not.toHaveValue("", { timeout: 60_000 });
    const heard = await box.inputValue();
    const want = words(SENTENCE);
    const got = new Set(words(heard));
    const share = want.filter((w) => got.has(w)).length / want.length;
    test.info().annotations.push({ type: "heard", description: `${Math.round(share * 100)} percent of the expected words` });
    expect(share, `heard: ${heard}`).toBeGreaterThanOrEqual(0.8);
    for (const n of NUMBERS) expect(words(heard), `the number ${n} must come back exactly`).toContain(n);
    await expect(panel.getByTestId("ask-heard")).toHaveText(T.heard);
    expect(stt.n).toBe(1);
    expect(asks.n, "the words heard were sent by themselves").toBe(0);
    await page.screenshot({ path: path.join(SHOTS, "voice-real-heard-light-1366.png") });

    // 9. the newest audio_transcribed line of the audit holds no word of the sentence
    await expect.poll(() => fs.readFileSync(AUDIT_FILE, "utf8").split("\n").filter((l) => l.includes('"audio_transcribed"')).length, { timeout: 10_000 }).toBeGreaterThan(0);
    const lines = fs.readFileSync(AUDIT_FILE, "utf8").split("\n").filter((l) => l.includes('"audio_transcribed"'));
    const last = lines[lines.length - 1];
    const entry = JSON.parse(last);
    const at = Date.parse(entry.at || entry.time || entry.ts || "");
    if (Number.isFinite(at)) expect(at).toBeGreaterThanOrEqual(startedAt - 60_000);
    const lower = last.toLowerCase();
    const leaked = [...new Set([...words(SENTENCE), ...words(heard)])].filter((w) => w.length >= 4 && lower.includes(w));
    expect(leaked, "the audit line must hold no dictated words").toEqual([]);
    for (const k of ["text", "audio", "transcript"]) expect(entry).not.toHaveProperty(k);

    // 6. edit then send: the request carries the edited text (one real question to the model)
    await box.press("End");
    await box.pressSequentially(" Quote the line.");
    const edited = await box.inputValue();
    const resp = page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === `/api/tb/cases/${REAL_CASE}/chats`, { timeout: 240_000 });
    await panel.getByRole("button", { name: /^Ask$/ }).click();
    await expect.poll(() => asks.n).toBe(1);
    expect(JSON.parse(asks.bodies[0]).question).toBe(edited.trim());
    await resp.catch(() => undefined); // let the answer finish so nothing is left half done
    expect(errors).toEqual([]);
    await page.close();
  });

  test("4. Esc while listening (real microphone path): nothing is sent, the box is unchanged", async () => {
    const { page, panel, stt } = await openReal();
    const micBtn = micIn(panel);
    await expect(micBtn).toBeVisible();
    const box = panel.locator("#ask-input");
    await box.fill("Typed first. ");
    await micBtn.click();
    await expect(micWrap(panel)).toHaveAttribute("data-state", "listening", { timeout: 15_000 });
    await page.waitForTimeout(1500);
    await page.keyboard.press("Escape");
    await expect(micWrap(panel)).toHaveAttribute("data-state", "idle");
    await page.waitForTimeout(2000);
    expect(stt.n).toBe(0);
    await expect(box).toHaveValue("Typed first. ");
    await page.close();
  });
});
