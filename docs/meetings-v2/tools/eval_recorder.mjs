// Item 5.5: the recorder and the notes on the real app with the real models. A scripted, synthetic board discussion about the synthetic
// patient Rekha Sharma (TB-2026-0011), voiced by Kokoro (made by the 2 Nov session into /data/vaidyx/meetings-v2/eval/, script.json),
// is sent through POST /meetings/{mid}/transcribe as the coordinator's browser would (one chunk per line, the speaker "room" or the
// Radiology doctor's login); then the notes are built and checked (speakers, every line's words found in what was said, no advice in
// Vaidyx's own voice); a decision is recorded, the case and the meeting end; the data folders are searched for any audio. Passwords are
// read in code (lib.mjs), never printed. Run: node docs/meetings-v2/tools/eval_recorder.mjs
import fs from "node:fs";
import path from "node:path";
import { BASE, H, open, j, note, problem, finish } from "./lib.mjs";

const CASE = "TB-2026-0011";
const EVAL = "/data/vaidyx/meetings-v2/eval";
const script = JSON.parse(fs.readFileSync(path.join(EVAL, "script.json"), "utf8"));
const startedAt = Date.now();
const today = new Date().toISOString().slice(0, 10);
const ADVICE = /\b(should|recommend|recommended|advise|indicated|must|needs? to|best option|consider)\b/i;

const mdt = await open("tb-mdt");
const rad = await open("tb-rad-doc");
let mid = "";
try {
  let r = await mdt.rq.post(`${BASE}/api/tb/meetings`, { headers: H, data: { date: today, time: "23:50", title: "Recorder evaluation (synthetic)", video: false } });
  mid = (await j(r))?.meeting?.id; note(`meeting ${mid} (${r.status()})`);
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/agenda/add`, { headers: H, data: { case_id: CASE, list: "discussion", reason: "recorder evaluation (synthetic)" } });
  note(`agenda add ${r.status()}`);
  const code = (await j(await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/code`, { headers: H, data: {} })))?.value;
  r = await rad.rq.post(`${BASE}/api/tb/meetings/join`, { headers: H, data: { code } }); note(`rad join ${r.status()}`);
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/admit`, { headers: H, data: { user: "tb-rad-doc" } }); note(`admit ${r.status()}`);
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/start`, { headers: H, data: {} }); note(`start ${r.status()}`);
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/current`, { headers: H, data: { case_id: CASE } }); note(`current ${r.status()}`);
  // a chunk before Record must be refused
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/transcribe`, { headers: H, multipart: { speaker: "room", started_ms: "0",
    audio: { name: "chunk.wav", mimeType: "audio/wav", buffer: fs.readFileSync(script[0].file) } } });
  if (r.status() !== 409) problem(`a chunk before Record answered ${r.status()} (expected 409)`); else note("a chunk before Record: 409");
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/recording`, { headers: H, data: { action: "start" } });
  note(`recording start ${r.status()} ${JSON.stringify((await j(r))?.recording?.state)}`);
  // a member may not send chunks
  r = await rad.rq.post(`${BASE}/api/tb/meetings/${mid}/transcribe`, { headers: H, multipart: { speaker: "tb-rad-doc", started_ms: "0",
    audio: { name: "chunk.wav", mimeType: "audio/wav", buffer: fs.readFileSync(script[1].file) } } });
  if (r.status() < 400) problem(`a member's chunk answered ${r.status()}`); else note(`a member's chunk: ${r.status()}`);
  for (const [i, l] of script.entries()) {
    const t0 = Date.now();
    r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/transcribe`, { headers: H, multipart: { speaker: l.speaker, started_ms: String(i * 20000),
      audio: { name: `chunk${i}.wav`, mimeType: "audio/wav", buffer: fs.readFileSync(l.file) } } });
    const b = await j(r);
    note(`chunk ${i} (${l.speaker}): ${r.status()} stored ${b?.stored} chars ${b?.segment?.chars} in ${Date.now() - t0} ms`);
    if (!r.ok() || !b?.stored) problem(`chunk ${i} not stored: ${r.status()} ${JSON.stringify(b).slice(0, 200)}`);
  }
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/cases/${CASE}/notes/build`, { headers: H, data: {} });
  const built = await j(r);
  note(`notes build ${r.status()}: ${built?.lines?.length} lines, dropped ${built?.dropped} ${JSON.stringify(built?.dropped_reasons || {})}, model ${built?.model_line || built?.model}`);
  // the member reads the notes
  const notes = await j(await rad.rq.get(`${BASE}/api/tb/meetings/${mid}/notes`, { headers: H }));
  const mine = (notes?.cases || []).find((c) => c.case_id === CASE);
  const said = script.map((l) => l.text.toLowerCase());
  for (const ln of mine?.lines || []) {
    const q = String(ln.said?.quote || "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
    note(`  line: ${ln.text}  [said by ${ln.said?.speaker_name}: "${ln.said?.quote}"]`);
    if (!ln.said?.quote) problem("a note line without its said words");
    const words = ln.text.replace(/"[^"]*"/g, " ");
    if (ADVICE.test(words)) problem(`advice-like words in Vaidyx's own voice: ${ln.text}`);
    if (q && !said.some((s) => s.replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").includes(q.split(" ").slice(0, 3).join(" ")))) note(`  (quote checked against the transcript by the server; the script wording differs after speech to text)`);
  }
  if (!(mine?.lines || []).length) problem("no note lines for the case");
  const speakers = new Set((mine?.lines || []).map((l) => l.said?.speaker));
  note(`speakers in the notes: ${[...speakers].join(", ")}`);
  if (!speakers.has("tb-rad-doc")) problem("no note line attributed to the Radiology doctor");
  // the decision, then the case and the meeting end
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/cases/${CASE}/decision`, { headers: H, data: { outcome: "deferred", awaited: "the signed biopsy report",
    awaited_from: "Pathology", decision_text: "Deferred until the signed biopsy report is available (synthetic evaluation).", members_present: ["Dr Radiology (demo)"] } });
  note(`decision ${r.status()} ${JSON.stringify((await j(r))?.detail || "").slice(0, 160)}`);
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/recording`, { headers: H, data: { action: "stop" } }); note(`recording stop ${r.status()}`);
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/cases/${CASE}/end`, { headers: H, data: {} }); note(`end case ${r.status()}`);
  r = await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/end`, { headers: H, data: {} }); note(`end meeting ${r.status()}`); mid = mid ? `${mid} (ended)` : mid;
} catch (e) {
  problem("stopped: " + String(e.message || e).slice(0, 300));
} finally {
  if (mid && !mid.endsWith("(ended)")) await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/end`, { headers: H, data: {} }).catch(() => {});
  // any audio on disk written since the start (the data folders of the app)
  const roots = ["/home/bharath.tangella/vaidyx/Vaidyx/data", "/tmp"];
  const found = [];
  const walk = (d) => { let es = []; try { es = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const e of es) { const p = path.join(d, e.name);
      if (e.isDirectory()) { if (!p.includes("/node_modules") && !p.includes("claude-1003")) walk(p); continue; }
      try { const st = fs.statSync(p); if (st.mtimeMs < startedAt) continue;
        const fd = fs.openSync(p, "r"); const b = Buffer.alloc(12); fs.readSync(fd, b, 0, 12, 0); fs.closeSync(fd);
        const h = b.toString("latin1");
        if (h.startsWith("RIFF") && h.slice(8, 12) === "WAVE" || h.startsWith("OggS") || b[0] === 0x1a && b[1] === 0x45 || /\.(wav|webm|ogg|opus|mp3|m4a)$/i.test(p)) found.push(p);
      } catch { /* unreadable: skip */ } } };
  for (const r of roots) walk(r);
  if (found.length) problem(`audio on disk: ${found.slice(0, 5).join(", ")}`); else note("no audio written to disk during the evaluation");
  await mdt.browser.close(); await rad.browser.close();
  finish("eval_recorder");
}
