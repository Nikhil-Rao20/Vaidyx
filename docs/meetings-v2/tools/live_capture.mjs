// Item 5.5, the browser half: the coordinator's real meeting screen records with Chromium's fake microphone (a synthetic board
// discussion voiced by Kokoro, /data/vaidyx/meetings-v2/eval/discussion.wav) in a meeting without video, so the screen uses the
// laptop microphone as the room. Record, about 45 s, Stop; then the stored segments and the notes are read back. Proves that the
// browser's WebM pieces are turned into text by the real speech service. Synthetic Case File TB-2026-0012 only; the meeting is ended.
// Run: node docs/meetings-v2/tools/live_capture.mjs
import path from "node:path";
import { BASE, H, OUT, open, j, settle, note, problem, finish } from "./lib.mjs";

const CASE = "TB-2026-0012";
const WAV = "/data/vaidyx/meetings-v2/eval/discussion.wav";
const today = new Date().toISOString().slice(0, 10);
const c = await open("tb-mdt", { audio: WAV });
let mid = "";
try {
  let r = await c.rq.post(`${BASE}/api/tb/meetings`, { headers: H, data: { date: today, time: "23:55", title: "Capture check (synthetic)", video: false } });
  mid = (await j(r))?.meeting?.id; note(`meeting ${mid} ${r.status()}`);
  await c.rq.post(`${BASE}/api/tb/meetings/${mid}/agenda/add`, { headers: H, data: { case_id: CASE, list: "discussion", reason: "capture check (synthetic)" } });
  note(`start ${(await c.rq.post(`${BASE}/api/tb/meetings/${mid}/start`, { headers: H, data: {} })).status()}`);
  note(`current ${(await c.rq.post(`${BASE}/api/tb/meetings/${mid}/current`, { headers: H, data: { case_id: CASE } })).status()}`);
  await c.page.goto(`${BASE}/tb-nik/meetings/${mid}`); await settle(c.page, 3000);
  const skip = c.page.getByRole("button", { name: /Join without video|Continue without|Skip/ }).first();
  if (await skip.count()) { await skip.click(); await settle(c.page, 1500); }
  await c.page.getByTestId("record").click();
  await c.page.getByTestId("recording-badge").first().waitFor({ timeout: 15000 }).catch(() => problem("no recording badge after Record"));
  note("recording on; letting the fake microphone play for 45 s");
  await c.page.waitForTimeout(45000);
  await c.page.screenshot({ path: path.join(OUT, "live-capture-recording-1366.png") });
  await c.page.getByTestId("record-stop").click();
  const confirm = c.page.getByTestId("confirm-stop-recording");
  if (await confirm.count()) await confirm.click();
  await c.page.waitForTimeout(12000);  // the last pieces post before stop
  const v = await j(await c.rq.get(`${BASE}/api/tb/meetings/${mid}`, { headers: H }));
  note(`recording after stop: ${JSON.stringify({ state: v?.recording?.state, chunks: v?.recording?.chunks, segments: v?.recording?.segments })}`);
  if (!(v?.recording?.segments > 0)) problem("no transcript segment stored from the browser's pieces");
  r = await c.rq.post(`${BASE}/api/tb/meetings/${mid}/cases/${CASE}/notes/build`, { headers: H, data: {} });
  const n = await j(r);
  note(`notes ${r.status()}: ${n?.lines?.length} lines, dropped ${n?.dropped}`);
  for (const l of (n?.lines || []).slice(0, 6)) note(`  - ${l.text} [${l.said?.speaker_name}]`);
} catch (e) {
  problem("stopped: " + String(e.message || e).slice(0, 300));
} finally {
  if (mid) note(`end ${(await c.rq.post(`${BASE}/api/tb/meetings/${mid}/end`, { headers: H, data: {} })).status()}`);
  await c.browser.close();
  finish("live_capture");
}
