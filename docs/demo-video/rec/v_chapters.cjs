// Chapters in Vaidyx-TB (:7000/tb-nik). Sessions are created per chapter and kept in SESS so later chapters can reuse them
// within one run of run.cjs.
const L = require("./lib.cjs");
const { mark, save, state, click, type, sleep, hover, scroll, scrollTo } = L;

const SESS = {};
const TODAY = (() => { const d = new Date(); return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`; })();

async function vLogin(s, user) {
  const page = s.page;
  mark(`v-login:${s.name}:${user}`);
  await page.goto(L.V + "/tb-nik/sign-in");
  await page.getByLabel("Email or login name").waitFor({ timeout: 30_000 });
  await sleep(1200);
  await type(page, page.getByLabel("Email or login name"), user);
  await type(page, page.getByLabel("Password", { exact: true }), L.vaidyxPassword(user), { secret: true });
  await click(page, page.getByRole("button", { name: "Sign in" }), { after: 200 });
  mark(`v-entrance:${s.name}`);
  await page.waitForURL(/\/tb-nik\/(cases|meetings|requests|admin|welcome)/, { timeout: 45_000 });
  await sleep(6500); // the entrance plays, then the mark glides into the top bar
}

async function get(name, opts = {}) {
  if (SESS[name]) return SESS[name];
  SESS[name] = await L.session(name, opts);
  return SESS[name];
}

async function soft(label, fn) {
  try { await fn(); } catch (e) { mark(`skip:${label}`, { error: String(e).slice(0, 200) }); console.log(`[skip] ${label}: ${String(e).slice(0, 160)}`); }
}

/** The treating doctor creates the Case File from the hospital system and reads the Board brief. */
async function casefile() {
  const st = state();
  const s = await get("doc");
  const page = s.page;
  mark("ch:casefile");
  await vLogin(s, "tb-breast-doc");
  await sleep(1500);
  await click(page, page.getByRole("link", { name: "New Case File" }).or(page.getByRole("button", { name: "New Case File" })).first());
  await page.getByLabel("UHID, IP No., OP No. or ABHA").waitFor();
  await sleep(1000);
  mark("casefile:lookup");
  await type(page, page.getByLabel("UHID, IP No., OP No. or ABHA"), st.uhid, { delay: 70 });
  await click(page, page.getByRole("button", { name: "Look up" }));
  await page.getByRole("region", { name: "Registration found" }).waitFor({ timeout: 30_000 });
  await sleep(1200);
  await hover(page, page.getByRole("region", { name: "Registration found" }));
  await sleep(2200);
  await click(page, page.getByRole("button", { name: "Continue" }));
  await sleep(1200);
  mark("casefile:cancer");
  await click(page, page.getByRole("radiogroup", { name: "Cancer" }).getByRole("radio").filter({ hasText: "Breast" }).first());
  await sleep(900);
  await click(page, page.getByRole("radio", { name: "Early (operable), as recorded" }));
  await sleep(900);
  await click(page, page.getByRole("button", { name: "Continue" }));
  await sleep(1200);
  mark("casefile:logistics");
  await type(page, page.getByRole("textbox", { name: /Board date/ }), TODAY, { delay: 80 });
  await page.keyboard.press("Tab");
  await sleep(500);
  await click(page, page.getByRole("radio", { name: "Urgency 4, urgent" }));
  await sleep(600);
  await scrollTo(page, page.getByRole("region", { name: "Read-back" }));
  await hover(page, page.getByRole("region", { name: "Read-back" }));
  await sleep(2200);
  mark("casefile:create");
  await click(page, page.getByRole("button", { name: "Create and fetch records" }));
  await page.waitForURL((u) => /\/tb-nik\/cases\/[^/]+$/.test(u.pathname) && !/\/cases\/new$/.test(u.pathname), { timeout: 60_000 });
  const caseId = decodeURIComponent(page.url().split("/cases/")[1].split(/[?#]/)[0]);
  save({ caseId });
  mark("casefile:created", { caseId });
  // the records arrive and are read: wait for the summary, at most 8 minutes
  await page.getByRole("heading", { name: "Board brief" }).waitFor({ timeout: 120_000 });
  mark("casefile:processing");
  const t0 = Date.now();
  while (Date.now() - t0 < 480_000) {
    const ready = await page.getByRole("heading", { name: "Summary", exact: true }).count() && await page.locator('[data-testid="quote-chip"]').count();
    if (ready) break;
    await sleep(3000);
  }
  mark("casefile:processed", { seconds: Math.round((Date.now() - t0) / 1000) });
  await sleep(2500);
  await page.screenshot({ path: `${L.RAW}/check-casefile.png` });
  // the brief: what is still open
  await soft("still-open", async () => { await scrollTo(page, page.getByRole("heading", { name: "Still open" }), { block: "start" }); await sleep(3500); });
  await soft("summary", async () => {
    mark("casefile:summary");
    await scrollTo(page, page.getByRole("heading", { name: "Summary", exact: true }), { block: "start" });
    await sleep(2500);
    await scroll(page, 380, { ms: 1400 }); await sleep(2000);
  });
  await soft("quote-chip", async () => {
    mark("casefile:source");
    const chip = page.locator('[data-testid="quote-chip"]').first();
    await click(page, chip);
    await page.getByTestId("source-viewer").waitFor({ timeout: 20_000 });
    await sleep(4500);
    await page.keyboard.press("Escape");
    await sleep(1200);
  });
  mark("casefile:end");
}


async function apiLogin(s, user) {
  const r = await s.page.request.post(L.V + "/api/auth/login", { data: { username: user, password: L.vaidyxPassword(user), remember: false }, headers: { "X-Requested-With": "tb-nik" } });
  if (!r.ok()) throw new Error(`sign-in failed for ${user}: ${r.status()}`);
}
async function openCase(s) {
  const st = state();
  await s.page.goto(`${L.V}/tb-nik/cases/${encodeURIComponent(st.caseId)}`);
  await s.page.getByRole("heading", { name: "Board brief" }).waitFor({ timeout: 60_000 });
  await sleep(1500);
}
const IHC = { "Oestrogen receptor (ER)": "Positive (Allred score 8/8, 90% nuclear staining)", "Progesterone receptor (PR)": "Positive (Allred score 6/8, 40% nuclear staining)",
  "HER2/neu (IHC score)": "1+ (Negative)", "Ki-67 labelling index": "22%" };

/** Split screen: the surgeon asks Pathology (left), the Pathology head acknowledges (left), the pathologist reports the IHC in the
 * hospital system (right), the Case File re-fetches and the item closes (left). */
async function request() {
  const st = state();
  const H = require("./his_chapters.cjs");
  const doc = await get("doc", { size: L.HALF });
  const his = await get("his2", { base: L.H, size: L.HALF });
  await apiLogin(doc, "tb-breast-doc");
  await openCase(doc);
  await his.page.goto(L.H + "/his/login");
  await sleep(1500);
  mark("split:start");
  // the surgeon: the receptor results are not in the file; one click asks Pathology
  const er = doc.page.locator("div").filter({ has: doc.page.getByText("Estrogen receptor (ER)", { exact: true }) }).filter({ has: doc.page.getByRole("button", { name: "Ask Pathology" }) }).last();
  await scrollTo(doc.page, doc.page.getByText("Receptor status (ER / PR / HER2)").first(), { block: "start" });
  await sleep(2500);
  mark("split:ask");
  await soft("ask-er", async () => { await click(doc.page, er.getByRole("button", { name: "Ask Pathology" }), { ms: 700 }); });
  await sleep(4000);
  // the Pathology head signs in and finds the request
  const head = await get("pathhead", { size: L.HALF });
  mark("split:head-login");
  await vLogin(head, "tb-path-head");
  if (!/\/requests/.test(head.page.url())) { await head.page.goto(L.V + "/tb-nik/requests"); }
  await head.page.getByRole("article").first().waitFor({ timeout: 30_000 });
  await sleep(2500);
  const card = head.page.getByRole("article").filter({ hasText: "Anjali Nair" }).first();
  await hover(head.page, card);
  await sleep(2500);
  mark("split:ack");
  await soft("acknowledge", async () => { await click(head.page, card.getByRole("button", { name: "Acknowledge" })); await sleep(2000); });
  const link = card.getByRole("link", { name: "Open order in HIS" });
  const href = await link.getAttribute("href");
  await hover(head.page, link);
  await sleep(1200);
  mark("split:open-his", { href });
  // the hospital system: the deep link asks for a sign-in, then opens the order
  const url = new URL(href, L.H); url.protocol = "http:"; url.host = "127.0.0.1:7130";
  await his.page.goto(url.toString());
  await sleep(1500);
  if (await his.page.getByLabel("Email").count()) {
    await type(his.page, his.page.getByLabel("Email"), "pathologist@vaidyx-demo.invalid");
    await type(his.page, his.page.getByLabel("Password"), L.hisPassword("pathologist@vaidyx-demo.invalid"), { secret: true });
    await click(his.page, his.page.getByRole("button", { name: "Sign in" }));
    await his.page.waitForLoadState("domcontentloaded");
    await sleep(1500);
  }
  if (!/pathology\/orders/.test(his.page.url())) { await his.page.goto(`${L.H}/his/pathology/orders/${st.accessions["IHC: ER, PR, HER2, Ki-67"].toLowerCase().replace(/\//g, "-")}`); await sleep(1200); }
  mark("split:his-order");
  const recv = his.page.getByRole("button", { name: "Receive specimen" });
  if (await recv.count()) { await click(his.page, recv); await his.page.waitForLoadState("domcontentloaded"); await sleep(1200); }
  for (const [label, value] of Object.entries(IHC)) {
    const f = his.page.getByLabel(new RegExp("^" + label.replace(/[()/]/g, "\\$&"))).first();
    await scrollTo(his.page, f);
    await type(his.page, f, value, { delay: 26 });
  }
  mark("split:his-sign");
  await click(his.page, his.page.getByRole("button", { name: "Sign final" }));
  await his.page.waitForLoadState("domcontentloaded");
  await sleep(2500);
  mark("split:his-signed");
  // back in the Case File: re-fetch from the hospital system; the receptor results arrive with their quotes
  await scrollTo(doc.page, doc.page.getByRole("button", { name: "Re-fetch now" }), { block: "center" });
  await sleep(800);
  mark("split:refetch");
  await click(doc.page, doc.page.getByRole("button", { name: "Re-fetch now" }));
  const t0 = Date.now();
  while (Date.now() - t0 < 240_000) {
    const txt = await doc.page.locator("main").innerText();
    if (/IMMUNOHISTOCHEMISTRY|Immunohistochemistry/.test(txt) && !/ER, PR, HER2, Ki-67, no report yet/.test(txt)) break;
    await sleep(3000);
  }
  mark("split:refetched", { seconds: Math.round((Date.now() - t0) / 1000) });
  await sleep(2000);
  await scrollTo(doc.page, doc.page.getByRole("heading", { name: "Still open" }), { block: "start" });
  await sleep(3500);
  await soft("receptor-found", async () => { await scrollTo(doc.page, doc.page.getByText(/Receptor status|Estrogen receptor/).first(), { block: "center" }); await sleep(3000); });
  // the request closed itself: the Pathology inbox
  mark("split:inbox-again");
  await head.page.reload(); await sleep(2500);
  await soft("done-tab", async () => { await click(head.page, head.page.getByRole("tab", { name: /Done/ })); await sleep(2500); });
  mark("split:end");
  await doc.page.screenshot({ path: `${L.RAW}/check-split-doc.png` });
}

/** The surgeon settles what is open, asks the Case File a question, marks ready; the summary and the specialty briefs follow. */
async function prepare() {
  const doc = await get("doc");
  const page = doc.page;
  await apiLogin(doc, "tb-breast-doc");
  await openCase(doc);
  mark("prep:start");
  await scrollTo(page, page.getByRole("heading", { name: "Still open" }), { block: "start" });
  await sleep(2000);
  // a value that differs between two reports: the doctor reads the difference
  await soft("review", async () => {
    mark("prep:review");
    await click(page, page.getByRole("button", { name: "Review" }).first());
    const panel = page.getByRole("complementary").or(page.getByRole("dialog")).filter({ hasText: "Review" }).first();
    await panel.waitFor({ timeout: 15_000 });
    await sleep(3500);
    await type(page, panel.getByRole("textbox").first(), "Mammogram size used; 1.6 cm in the CT is the axillary node.", { delay: 22 });
    await click(page, panel.getByRole("button", { name: /Noted, I read the difference/ }));
    await sleep(2500);
  });
  // a value no report holds: the doctor enters it
  await soft("menopausal", async () => {
    mark("prep:menopausal");
    const row = page.locator("dd, div").filter({ has: page.getByRole("button", { name: "Enter a value" }) }).filter({ hasText: "Not in the file" }).first();
    await click(page, page.getByRole("button", { name: "Enter a value" }).first());
    const combo = page.getByRole("combobox", { name: "Menopausal status" });
    await hover(page, combo); await combo.selectOption("premenopausal"); await sleep(600);
    await click(page, page.getByRole("button", { name: "Save" }).first());
    await sleep(2500);
  });
  // Ask this Case File
  await soft("ask", async () => {
    mark("prep:ask");
    const box = page.getByPlaceholder(/Ask about the records/);
    await scrollTo(page, box, { block: "center" });
    await type(page, box, "What are the ER, PR, HER2 and Ki-67 results, and which report gives them?", { delay: 30 });
    await click(page, page.getByRole("button", { name: "Ask", exact: true }));
    const t0 = Date.now();
    while (Date.now() - t0 < 120_000) { if (await page.getByRole("region", { name: "Ask this Case File" }).getByText(/Allred|Ki-67|Ki 67|HER2/).count()) break; await sleep(1500); }
    mark("prep:answered", { seconds: Math.round((Date.now() - t0) / 1000) });
    await sleep(5000);
    await soft("answer-chip", async () => { const chip = page.getByRole("region", { name: "Ask this Case File" }).getByRole("button", { name: /Immunohistochemistry report/ }).first(); await click(page, chip); await page.getByTestId("source-viewer").waitFor({ timeout: 15_000 }); await sleep(4500); await page.keyboard.press("Escape"); await sleep(1000); });
  });
  // Mark ready: the read-back, then the summary and the briefs are prepared
  mark("prep:ready");
  await scrollTo(page, page.getByRole("heading", { level: 1 }), { block: "start" });
  await click(page, page.getByRole("button", { name: "Mark ready" }));
  const dlg = page.getByRole("dialog", { name: /Mark ready/ });
  await dlg.waitFor({ timeout: 15_000 });
  await sleep(1500);
  await type(page, dlg.getByRole("textbox").first(), "Biopsy, IHC and staging CT complete. For discussion on 20/10.", { delay: 24 });
  await click(page, dlg.getByRole("button", { name: /^Mark ready/ }));
  await sleep(3000);
  mark("prep:marked");
  // the summary: written now from the verified lines
  await scrollTo(page, page.getByRole("heading", { name: "Summary", exact: true }), { block: "start" });
  const t1 = Date.now();
  while (Date.now() - t1 < 300_000) { if (await page.getByTestId("prose-section").getByRole("button", { name: /p\. \d/ }).count()) break; await sleep(3000); }
  mark("prep:summary-ready", { seconds: Math.round((Date.now() - t1) / 1000) });
  await sleep(1500);
  await scrollTo(page, page.getByRole("heading", { name: "Summary", exact: true }), { block: "start" });
  await sleep(3000);
  await scroll(page, 450, { ms: 2200 }); await sleep(3000);
  await scroll(page, 450, { ms: 2200 }); await sleep(3000);
  // a specialty brief
  await soft("helper", async () => {
    mark("prep:helper");
    await scrollTo(page, page.getByRole("heading", { level: 1 }), { block: "start" });
    await click(page, page.getByRole("button", { name: /Specialty helpers/ }));
    const panel = page.getByRole("complementary", { name: "Specialty helpers" });
    await panel.waitFor();
    await sleep(1500);
    const t2 = Date.now();
    while (Date.now() - t2 < 300_000) { if (!(await panel.getByText("not prepared").count()) && !(await panel.getByText(/preparing/i).count())) break; await sleep(3000); }
    mark("prep:helpers-ready", { seconds: Math.round((Date.now() - t2) / 1000) });
    await click(page, panel.getByRole("button", { name: /Pathology records check/ }));
    await sleep(4000);
    await scroll(page, 350, { ms: 1500 }); await sleep(3000);
    await page.keyboard.press("Escape"); await sleep(1000);
  });
  mark("prep:end");
  await page.screenshot({ path: `${L.RAW}/check-prepare.png` });
}

/** The summary written at the ready mark, and one specialty brief. */
async function brief() {
  const doc = await get("doc");
  const page = doc.page;
  await apiLogin(doc, "tb-breast-doc");
  await openCase(doc);
  mark("brief:start");
  await sleep(1500);
  await scrollTo(page, page.getByRole("heading", { name: "Summary", exact: true }), { block: "start" });
  await sleep(3500);
  mark("brief:summary");
  await scroll(page, 380, { ms: 2600 }); await sleep(3500);
  await scroll(page, 380, { ms: 2600 }); await sleep(3500);
  await soft("summary-chip", async () => {
    const chip = page.getByTestId("prose-section").getByRole("button", { name: /p\. \d/ }).nth(2);
    await click(page, chip); await page.getByTestId("source-viewer").waitFor({ timeout: 15_000 }); await sleep(5000); await page.keyboard.press("Escape"); await sleep(1200);
  });
  mark("brief:helpers");
  await scrollTo(page, page.getByRole("heading", { level: 1 }), { block: "start" });
  await sleep(800);
  await click(page, page.getByRole("button", { name: /Specialty helpers/ }));
  const panel = page.getByRole("complementary", { name: "Specialty helpers" });
  await panel.waitFor();
  await sleep(2500);
  await soft("pathology-brief", async () => {
    await click(page, panel.getByRole("button", { name: /Pathology records check/ }));
    await sleep(4500);
    mark("brief:pathology");
    await scroll(page, 380, { ms: 2000 }); await sleep(3500);
    await scroll(page, 380, { ms: 2000 }); await sleep(3000);
  });
  await page.keyboard.press("Escape"); await sleep(1200);
  mark("brief:end");
  await page.screenshot({ path: `${L.RAW}/check-brief.png` });
}

const CAM = (k) => `/data/vaidyx/demo_video/assets/cams/${k}.y4m`;
/** A meeting member who is not filmed: own browser with its test camera, signed in by API, joins with the code. */
async function silentMember(user, cam, code, mid, mdt) {
  const { chromium } = require("playwright");
  const b = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-video-capture=${CAM(cam)}`, "--autoplay-policy=no-user-gesture-required"] });
  const ctx = await b.newContext({ viewport: { width: 1280, height: 720 }, baseURL: L.V, permissions: ["camera", "microphone"] });
  const page = await ctx.newPage();
  const r = await page.request.post("/api/auth/login", { data: { username: user, password: L.vaidyxPassword(user), remember: false }, headers: { "X-Requested-With": "tb-nik" } });
  if (!r.ok()) throw new Error(`sign-in ${user} ${r.status()}`);
  await page.request.post("/api/tb/meetings/join", { data: { code }, headers: { "X-Requested-With": "tb-nik" } });
  await mdt.page.request.post(`${L.V}/api/tb/meetings/${mid}/admit`, { data: { user }, headers: { "X-Requested-With": "tb-nik" } });
  await page.goto(`/tb-nik/meetings/${mid}/member`);
  await page.getByTestId("prejoin").waitFor({ timeout: 40_000 });
  await page.getByTestId("prejoin-join").click();
  await page.getByTestId("member-view").waitFor({ timeout: 40_000 });
  return { b, page };
}
async function giveCard(page) {
  const agree = page.getByTestId("card-agree");
  await agree.waitFor({ timeout: 30_000 });
  await agree.click(); await sleep(400);
  await page.getByTestId("card-send").click();
}

/** The meeting: the coordinator creates it, adds the Case File, sends the agenda and starts; the board joins with their
 * cameras; the room screen shows the slide, the report and the images; the decision is recorded; cards; the meeting ends. */
async function meeting() {
  const st = state();
  const mdt = await get("mdt", { camera: CAM("mdt") });
  const p = mdt.page;
  mark("meet:login");
  await vLogin(mdt, "tb-mdt");
  await click(p, p.getByRole("link", { name: "Meetings" }).first());
  await p.getByTestId("meetings-page").waitFor({ timeout: 30_000 });
  await sleep(2500);
  let mid = st.mid;
  let resume = false;
  if (mid) {
    const m = await (await p.request.get(`${L.V}/api/tb/meetings/${mid}`, { headers: { "X-Requested-With": "tb-nik" } })).json().catch(() => ({}));
    resume = ((m.meeting || m).status === "planned");
  }
  if (resume) {
    await p.goto(`${L.V}/tb-nik/meetings/${mid}`);
  } else {
  mark("meet:new");
  await click(p, p.getByTestId("new-meeting"));
  const dlg = p.getByTestId("new-meeting-dialog");
  await dlg.waitFor();
  await sleep(1500);
  await type(p, dlg.getByLabel("Room"), "Breast Tumour Board room, 2nd floor");
  await hover(p, dlg.getByLabel("Video for remote members")); await sleep(1200);
  await click(p, dlg.getByRole("button", { name: "Create meeting" }));
  await p.waitForURL(/\/meetings\/S\d+/, { timeout: 30_000 });
  mid = p.url().split("/meetings/")[1].split(/[/?#]/)[0];
  save({ mid });
  mark("meet:created", { mid });
  }
  await p.getByTestId("meeting-page").waitFor({ timeout: 30_000 });
  await sleep(2500);
  mark("meet:add");
  await click(p, p.getByTestId("add-case"));
  const add = p.getByTestId("add-case-dialog");
  await add.waitFor();
  await sleep(1800);
  await hover(p, add.getByText("Anjali Nair", { exact: false }).first());
  await sleep(1200);
  await click(p, add.getByRole("button", { name: "Discussion", exact: true }).first());
  await sleep(1800);
  await click(p, add.getByRole("button", { name: "Done" }));
  await sleep(2000);
  mark("meet:code");
  await click(p, p.getByTestId("new-code"));
  await p.getByTestId("meeting-code").waitFor({ timeout: 20_000 });
  const code = ((await p.getByTestId("meeting-code").innerText()) || "").replace(/\D/g, "").slice(0, 6);
  save({ code });
  await sleep(2000);
  mark("meet:send-agenda");
  await click(p, p.getByTestId("send-agenda"));
  await sleep(3000);
  // the board joins: Radiology and Pathology in the background, the surgeon on camera
  mark("meet:start");
  await click(p, p.getByTestId("start-meeting"));
  await p.getByTestId("prejoin").waitFor({ timeout: 40_000 });
  await sleep(3500);
  mark("meet:prejoin");
  await click(p, p.getByTestId("prejoin-join"));
  await p.getByTestId("control-view").waitFor({ timeout: 40_000 });
  await sleep(2500);
  // a current case for the conduct panel
  const cur = await (await p.request.get(`${L.V}/api/tb/meetings/${mid}`, { headers: { "X-Requested-With": "tb-nik" } })).json().catch(() => ({}));
  if (!(cur.current && cur.current.case_id)) await p.request.post(`${L.V}/api/tb/meetings/${mid}/current`, { data: { case_id: st.caseId }, headers: { "X-Requested-With": "tb-nik" } });
  const silent = [];
  for (const [user, cam] of [["tb-rad-doc", "rad"], ["tb-path-head", "path"]]) {
    try { silent.push(await silentMember(user, cam, code, mid, mdt)); } catch (e) { mark(`skip:silent-${user}`, { error: String(e).slice(0, 160) }); }
  }
  await sleep(4000);
  mark("meet:doc-join");
  const doc = await get("doc2", { camera: CAM("breast") });
  await apiLogin(doc, "tb-breast-doc");
  await doc.page.goto(`${L.V}/tb-nik/meetings/join`);
  await doc.page.getByTestId("join-page").waitFor({ timeout: 30_000 });
  await sleep(1500);
  await type(doc.page, doc.page.getByLabel("Meeting code"), code, { delay: 160 });
  await click(doc.page, doc.page.getByTestId("join-submit"));
  await sleep(2500);
  mark("meet:admit");
  await soft("admit-ui", async () => {
    const banner = p.getByTestId("waiting-banner");
    await banner.waitFor({ timeout: 20_000 });
    await sleep(1500);
    await click(p, banner.getByRole("button", { name: "Admit" }).first());
  });
  await sleep(2000);
  await soft("doc-prejoin", async () => {
    if (!/\/member/.test(doc.page.url())) await doc.page.goto(`${L.V}/tb-nik/meetings/${mid}/member`);
    await doc.page.getByTestId("prejoin").waitFor({ timeout: 40_000 });
    await sleep(3000);
    await click(doc.page, doc.page.getByTestId("prejoin-join"));
    await doc.page.getByTestId("member-view").waitFor({ timeout: 40_000 });
  });
  await sleep(5000);
  mark("meet:in-call");
  // the room screen: its own identity and camera
  const room = await get("room", { camera: CAM("room") });
  await apiLogin(room, "tb-mdt");
  await room.page.goto(`${L.V}/tb-nik/meetings/${mid}/room`);
  await room.page.getByTestId("room-screen").waitFor({ timeout: 40_000 });
  await sleep(6000);
  mark("meet:room");
  // Share: the slides, then the IHC report and the mammogram images on the room screen
  await soft("share-tab", async () => { await click(p, p.getByRole("tab", { name: "Share" }).or(p.getByRole("button", { name: "Share" })).first()); await sleep(1500); });
  await soft("slides", async () => {
    const picker = p.getByRole("group", { name: "Slide picker" });
    const n = await picker.getByRole("button").count();
    for (let i = 0; i < Math.min(n, 4); i++) { mark(`meet:slide-${i + 1}`); await click(p, picker.getByRole("button").nth(i)); await sleep(5500); }
    await click(p, picker.getByRole("button").first()); await sleep(2500);
  });
  await soft("show-ihc", async () => {
    mark("meet:show-ihc");
    await click(p, p.getByRole("button", { name: /Show IMMUNOHISTOCHEMISTRY|Show Immunohistochemistry/i }).first());
    await sleep(7000);
  });
  await soft("show-images", async () => {
    mark("meet:show-images");
    await click(p, p.getByRole("button", { name: /Show the images of .*MAMMOGRAPH/i }).first());
    await sleep(12000);
  });
  await soft("back-to-slide", async () => { mark("meet:back"); await click(p, p.getByRole("button", { name: "Back to the slide" })); await sleep(3000); });
  // Decision: typed live (the room screen shows it, marked not saved), then saved
  mark("meet:decision");
  await soft("decision", async () => {
    await click(p, p.getByRole("tab", { name: "Decision" }).or(p.getByRole("button", { name: "Decision", exact: true })).first());
    const f = p.getByTestId("decision-form");
    await f.waitFor({ timeout: 15_000 });
    await sleep(1500);
    await type(p, f.getByLabel("Decision, in the board's words"), "Breast-conserving surgery with sentinel lymph node biopsy first; adjuvant treatment to be decided on the final histology.", { delay: 26 });
    await sleep(1500);
    await type(p, f.getByLabel("Rationale as discussed"), "Operable right breast cancer, ER and PR positive, HER2 negative; one suspicious axillary node on imaging; no distant disease on CECT.", { delay: 20 });
    await type(p, f.getByLabel("Treatment intent as stated by the board"), "Curative", { delay: 40 });
    await type(p, f.getByLabel("Responsible doctor"), "Dr Breast Surgery (demo)", { delay: 30 });
    await type(p, f.getByLabel("Next step"), "Surgery date and pre-anaesthetic check in the Breast OPD", { delay: 22 });
    const boxes = f.getByRole("checkbox");
    for (let i = 0; i < await boxes.count(); i++) { if (!(await boxes.nth(i).isChecked())) { await click(p, boxes.nth(i), { pause: 120, after: 200 }); } }
    mark("meet:save-decision");
    await click(p, p.getByTestId("save-decision"));
    await sleep(4000);
  });
  await soft("room-after-decision", async () => { await sleep(3000); });
  // cards: each board head agrees or raises a concern
  mark("meet:cards");
  await soft("end-case", async () => { await click(p, p.getByTestId("end-case")); await sleep(2500); });
  await soft("doc-card", async () => { mark("meet:doc-card"); const a = doc.page.getByTestId("card-agree"); await a.waitFor({ timeout: 30_000 }); await sleep(1500); await click(doc.page, a); await sleep(800); await click(doc.page, doc.page.getByTestId("card-send")); await sleep(2500); });
  for (const m of silent) await giveCard(m.page).catch(() => {});
  await sleep(5000);
  // end the meeting
  mark("meet:end");
  await soft("end-meeting", async () => {
    await click(p, p.getByRole("button", { name: "End meeting" }).first());
    await sleep(1500);
    const confirm = p.getByRole("dialog").getByRole("button", { name: "End meeting" }).or(p.getByRole("alertdialog").getByRole("button", { name: "End meeting" }));
    if (await confirm.count()) await click(p, confirm.first());
    await sleep(4000);
  });
  mark("meet:closed");
  await sleep(3000);
  await p.screenshot({ path: `${L.RAW}/check-meeting.png` });
  for (const m of silent) await m.b.close().catch(() => {});
}

async function dismissOhif(page) {
  for (const f of [page, ...page.frames()]) {
    for (const name of ["Skip all", "Confirm and hide"]) {
      const b = f.getByRole("button", { name }).or(f.getByText(name, { exact: true })).first();
      if (await b.count().catch(() => 0)) { await b.click({ timeout: 3000 }).catch(() => {}); await sleep(500); }
    }
  }
}

/** After the meeting: the Case File holds the decision; the images; the activity log. */
async function after() {
  const doc = await get("doc");
  const page = doc.page;
  await apiLogin(doc, "tb-breast-doc");
  await page.goto(`${L.V}/tb-nik/cases`);
  await sleep(3500);
  mark("after:list");
  await hover(page, page.getByText("Anjali Nair (SYNTHETIC)").first());
  await sleep(2500);
  await click(page, page.getByText("Anjali Nair (SYNTHETIC)").first());
  await page.getByRole("heading", { name: "Board brief" }).waitFor({ timeout: 60_000 });
  await sleep(3500);
  mark("after:casefile");
  await page.screenshot({ path: `${L.RAW}/check-after.png` });
  await scroll(page, 500, { ms: 2200 }); await sleep(3500);
  await scroll(page, 500, { ms: 2200 }); await sleep(3500);
  await soft("download-menu", async () => {
    mark("after:download");
    await scrollTo(page, page.getByRole("heading", { level: 1 }), { block: "start" });
    await click(page, page.getByRole("button", { name: "Download" }));
    await sleep(3500);
    await page.keyboard.press("Escape"); await sleep(800);
  });
  // the images, from the report list (the viewer's first-use tour dismissed off camera)
  await soft("images", async () => {
    mark("after:images");
    const btn = page.getByRole("button", { name: /Open images/ }).or(page.getByRole("link", { name: /Open images/ })).first();
    await scrollTo(page, btn);
    const [popup] = await Promise.all([page.context().waitForEvent("page", { timeout: 15_000 }).catch(() => null), click(page, btn)]);
    const view = popup || page;
    if (popup) { await L.record(popup, "images").then((r) => { doc.extra = r; }); }
    await view.waitForLoadState("domcontentloaded");
    await sleep(6000);
    await dismissOhif(view);
    await sleep(1500);
    await dismissOhif(view);
    mark("after:images-shown");
    await sleep(8000);
    if (popup) { await doc.extra.stop(); await popup.close(); }
  });
  await soft("activity", async () => {
    mark("after:activity");
    await page.goto(`${L.V}/tb-nik/activity`);
    await sleep(4000);
    await scroll(page, 400, { ms: 2000 }); await sleep(3000);
  });
  mark("after:end");
}

/** The root admin: hospital set-up and people. */
async function admin() {
  const s = await get("root");
  const page = s.page;
  mark("admin:login");
  await vLogin(s, "tb-root");
  await soft("setup", async () => {
    if (!/\/admin/.test(page.url())) { await page.goto(`${L.V}/tb-nik/admin`); }
    await sleep(3500);
    mark("admin:setup");
    await scroll(page, 400, { ms: 2000 }); await sleep(3000);
    const steps = page.getByRole("complementary", { name: "Set-up so far" }).getByRole("button");
    const n = await steps.count();
    for (let i = 1; i < Math.min(n, 5); i++) { await click(page, steps.nth(i)); await sleep(3000); }
  });
  await soft("people", async () => {
    mark("admin:people");
    await page.goto(`${L.V}/tb-nik/people`);
    await sleep(4000);
    await scroll(page, 400, { ms: 2000 }); await sleep(3000);
  });
  mark("admin:end");
}

/** The phone: the Case File list, a Case File, the Dock. */
async function phone() {
  const s = await get("phone", { size: { width: 390, height: 844 }, dsf: 3, mobile: true });
  const page = s.page;
  await apiLogin(s, "tb-breast-doc");
  await page.goto(`${L.V}/tb-nik/cases`);
  await sleep(4000);
  mark("phone:list");
  await page.mouse.move(195, 500);
  await scroll(page, 300, { ms: 1500 }); await sleep(2000);
  await click(page, page.getByText("Anjali Nair (SYNTHETIC)").first());
  await sleep(4500);
  mark("phone:casefile");
  for (let i = 0; i < 4; i++) { await scroll(page, 420, { ms: 1500 }); await sleep(2200); }
  await soft("dock", async () => { mark("phone:dock"); await click(page, page.getByRole("link", { name: "Meetings" }).last()); await sleep(4000); });
  mark("phone:end");
}

/** The public website, signed out: the entrance, the product page, the workflow map, Research. */
async function site() {
  const s = await get("site");
  const page = s.page;
  mark("site:start");
  await page.goto(`${L.V}/tb-nik`);
  await sleep(9000); // the brand entrance, then the hero's mark gathers
  mark("site:hero");
  await page.mouse.move(900, 600);
  await sleep(2000);
  const stops = [700, 700, 800, 800, 800, 900, 900, 900, 900, 900, 900];
  for (const px of stops) { await scroll(page, px, { ms: 1800 }); await sleep(2600); }
  mark("site:research");
  await page.goto(`${L.V}/tb-nik/research`);
  await sleep(4500);
  for (const px of [700, 800, 900]) { await scroll(page, px, { ms: 1800 }); await sleep(2500); }
  mark("site:end");
}

/** After the Board, part two: the decision in the Board form, and the downloads. */
async function after2() {
  const doc = await get("doc");
  const page = doc.page;
  await apiLogin(doc, "tb-breast-doc");
  await openCase(doc);
  await sleep(1500);
  mark("after2:boardform");
  await click(page, page.getByRole("button", { name: "Board form" }));
  const panel = page.getByRole("complementary", { name: "Board form" });
  await panel.waitFor({ timeout: 15_000 });
  await sleep(1500);
  await hover(page, panel.getByText("Decision as recorded"));
  await sleep(4500);
  await hover(page, panel.getByText("Members present"));
  await sleep(3500);
  await page.keyboard.press("Escape"); await sleep(1200);
  mark("after2:download");
  await click(page, page.getByRole("button", { name: "Download" }));
  await sleep(1200);
  await hover(page, page.getByRole("menuitem", { name: /Board deck/ }));
  await sleep(2200);
  await hover(page, page.getByRole("menuitem", { name: /NCG VTB template/ }));
  await sleep(2200);
  await page.keyboard.press("Escape"); await sleep(1000);
  mark("after2:end");
}

module.exports = { after2, after, admin, phone, site, meeting, brief, prepare, request, apiLogin, openCase, casefile, vLogin, get, soft, SESS, TODAY };
