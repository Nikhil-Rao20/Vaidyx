// Chapters in the mock hospital (DemoHIMS, :7130): reception registers the patient and opens the OP visit; the OPD consultant
// writes and signs the note and places the orders; the laboratory, radiology and pathology desks do their work. The IHC is left
// ordered on purpose: Vaidyx finds it missing and asks Pathology for it (the split-screen chapter).
const L = require("./lib.cjs");
const { mark, save, state, click, type, sleep, hover, scroll } = L;

const P = {
  name: "Anjali Nair (SYNTHETIC)", sex: "F", age: "49", mobile: "+91 98450 12345", address: "No. 22, 5th Main, Jayanagar 4th Block",
  town: "Bengaluru", district: "Bengaluru Urban", state: "Karnataka", pin: "560011", abha: "99-2600-4520-0002", pmjay: "PMJAY-VX-26004520",
};
const NOTE = {
  complaint: "Painless lump in the right breast for 3 months, noticed while bathing. No nipple discharge. No family history of breast or ovarian cancer.",
  exam: "Hard, irregular 3 x 2.5 cm lump in the upper outer quadrant of the right breast, not fixed to the chest wall. One mobile right axillary node, about 1.5 cm. Left breast and axilla normal. ECOG performance status 1.",
  question: "Core biopsy, receptor status and staging work-up before the Breast Tumour Board.",
  plan: "Bilateral mammogram, core biopsy with IHC, CECT chest, abdomen and pelvis, CBC, LFT and RFT. Present at the Breast Tumour Board.",
};
const ORDERS = ["Complete blood count", "Liver function tests", "Renal function tests", "Bilateral mammogram", "Histopathology report (biopsy)",
  "IHC: ER, PR, HER2, Ki-67", "CECT chest, abdomen and pelvis"];

async function hisLogin(s, email, label) {
  const page = s.page;
  mark(`his-login:${label}`);
  await page.goto(L.H + "/his/login");
  await sleep(900);
  await type(page, page.getByLabel("Email"), email);
  await type(page, page.getByLabel("Password"), L.hisPassword(email), { secret: true });
  await click(page, page.getByRole("button", { name: "Sign in" }));
  await page.waitForLoadState("domcontentloaded");
  await sleep(1400);
}
async function hisLogout(s) {
  const page = s.page;
  const b = page.getByRole("button", { name: "Logout" }).first();
  if (await b.count()) {
    await click(page, b);
    await page.waitForLoadState("domcontentloaded");
    const again = page.getByRole("button", { name: /Logout|Sign out/ }).first();
    if (/logout/.test(page.url()) && (await again.count())) await click(page, again);
    await sleep(800);
  }
}
async function gotoModule(page, name) { await click(page, page.getByRole("navigation").getByRole("link", { name, exact: true })); await page.waitForLoadState("domcontentloaded"); await sleep(1000); }

async function reception(s) {
  const page = s.page;
  mark("ch:reception");
  await hisLogin(s, "reception@vaidyx-demo.invalid", "reception");
  await scrollTo(page, page.getByRole("heading", { name: "New registration" }), "start");
  await type(page, page.getByLabel('Name (ends with "(SYNTHETIC)")'), P.name);
  await hover(page, page.getByLabel("Sex")); await page.getByLabel("Sex").selectOption(P.sex); await sleep(300);
  await type(page, page.getByLabel("Age (years)"), P.age);
  await type(page, page.getByLabel("Mobile phone"), P.mobile);
  await type(page, page.getByLabel("Address", { exact: true }), P.address);
  await type(page, page.getByLabel("Town / village"), P.town);
  await type(page, page.getByLabel("District"), P.district);
  await hover(page, page.getByLabel("State")); await page.getByLabel("State").selectOption(P.state); await sleep(300);
  await type(page, page.getByLabel("PIN code"), P.pin);
  await type(page, page.getByLabel("ABHA number (optional, permanent only)"), P.abha);
  await type(page, page.getByLabel("PM-JAY ID (optional)"), P.pmjay);
  mark("reception:register");
  await click(page, page.getByRole("button", { name: "Register" }));
  await page.waitForLoadState("domcontentloaded");
  await sleep(1500);
  const anyway = page.getByRole("button", { name: /Register anyway/ });
  if (await anyway.count()) { await click(page, anyway); await page.waitForLoadState("domcontentloaded"); await sleep(1200); }
  const h1 = (await page.getByRole("heading", { level: 1 }).first().innerText()).trim();
  const uhid = (h1.match(/VXH\/(?:T\/)?\d+\/\d+/) || [])[0];
  const patientUrl = page.url();
  if (!uhid) throw new Error(`no UHID on the patient page: ${h1}`);
  save({ uhid, patientUrl });
  mark("reception:registered", { uhid });
  await scroll(page, 420);
  await sleep(1200);
  // open the OP visit: Breast Surgery, Unit I, Dr Kavitha Raghunathan, new
  const visit = page.locator("form").filter({ has: page.getByRole("button", { name: "Open OP visit" }) });
  await scrollTo(page, visit.getByRole("button", { name: "Open OP visit" }));
  await hover(page, visit.getByLabel("Department")); await visit.getByLabel("Department").selectOption({ label: "Breast Surgery" }); await sleep(300);
  await hover(page, visit.getByLabel("Consultant")); await visit.getByLabel("Consultant").selectOption({ label: "Dr Kavitha Raghunathan (Breast Surgery)" }); await sleep(300);
  mark("reception:open-visit");
  await click(page, visit.getByRole("button", { name: "Open OP visit" }));
  await page.waitForLoadState("domcontentloaded");
  await sleep(1800);
  const h = (await page.getByRole("heading", { level: 1 }).first().innerText()).trim();
  const op = (h.match(/OP\/\d+\/\d+/) || [])[0];
  save({ op, encounterUrl: page.url() });
  mark("reception:visit-opened", { op });
  await sleep(1500);
  await hisLogout(s);
}

async function scrollTo(page, loc, block = "center") { await L.scrollTo(page, loc, { block }); }

async function opd(s) {
  const page = s.page;
  const st = state();
  mark("ch:opd");
  await hisLogin(s, "opd.doctor@vaidyx-demo.invalid", "opd");
  await gotoModule(page, "OPD");
  const link = page.getByRole("link", { name: new RegExp(st.op.replace(/\//g, "\\/")) }).first();
  const byName = page.getByRole("link", { name: /Anjali Nair/ }).first();
  if (await link.count()) await click(page, link); else if (await byName.count()) await click(page, byName); else await page.goto(st.encounterUrl);
  await page.waitForLoadState("domcontentloaded");
  await sleep(1500);
  mark("opd:note");
  await scrollTo(page, page.getByRole("heading", { name: "OPD consultation note" }), "start");
  await type(page, page.getByRole("textbox", { name: /Presenting complaint/ }), NOTE.complaint, { delay: 18 });
  await type(page, page.getByRole("textbox", { name: "Examination", exact: true }), NOTE.exam, { delay: 18 });
  await type(page, page.getByRole("textbox", { name: "Clinical question", exact: true }), NOTE.question, { delay: 18 });
  await type(page, page.getByRole("textbox", { name: "Plan", exact: true }), NOTE.plan, { delay: 18 });
  await click(page, page.getByRole("button", { name: "Sign the note" }));
  await page.waitForLoadState("domcontentloaded");
  await sleep(1800);
  mark("opd:orders");
  await scrollTo(page, page.getByRole("heading", { name: "Order entry" }), "start");
  for (const name of ORDERS) {
    const box = page.getByRole("checkbox", { name, exact: true });
    await scrollTo(page, box);
    await click(page, box, { pause: 150, after: 250 });
  }
  await click(page, page.getByRole("button", { name: "Place orders" }));
  await page.waitForLoadState("domcontentloaded");
  await sleep(1500);
  // the accessions just allocated, from the visit's order table
  await scrollTo(page, page.getByRole("heading", { name: "Orders and reports" }), "start");
  await sleep(1800);
  const rows = await page.locator("table tr").allInnerTexts();
  const acc = {};
  for (const r of rows) {
    const m = r.match(/^(\S+\/\d+\/\d+)\s+(.+?)\t/) || r.match(/^(\S+\/\d+\/\d+)\s+(.+?)\s{2,}/);
    const a = (r.match(/[A-Z]{2,4}\/\d+\/\d+/) || [])[0];
    if (a) for (const name of ORDERS) if (r.includes(name)) acc[name] = a;
  }
  save({ accessions: acc });
  mark("opd:orders-placed", { accessions: acc });
  await sleep(1200);
  await hisLogout(s);
}

async function openOrder(page, accession) {
  const link = page.getByRole("link", { name: accession, exact: true }).first();
  if (!(await link.count())) {
    for (const tab of ["Ordered", "Sample collected", "Specimen received", "Scheduled", "Entered", "Results entered", "Reported"]) {
      const t = page.getByRole("link", { name: new RegExp(`^${tab}`) }).first();
      if (await t.count()) { await click(page, t); await page.waitForLoadState("domcontentloaded"); await sleep(700); if (await link.count()) break; }
    }
  }
  await click(page, link);
  await page.waitForLoadState("domcontentloaded");
  await sleep(1200);
}

const LAB = {
  "Complete blood count": ["11.8", "7400", "2.6"],
  "Liver function tests": ["0.7", "28", "31"],
  "Renal function tests": ["0.8", "24"],
};
async function lab(s) {
  const page = s.page;
  const st = state();
  mark("ch:lab");
  await hisLogin(s, "lab.doctor@vaidyx-demo.invalid", "lab");
  await gotoModule(page, "Laboratory");
  for (const [test, values] of Object.entries(LAB)) {
    mark(`lab:${test}`);
    await openOrder(page, st.accessions[test]);
    await click(page, page.getByRole("button", { name: "Collect sample" }));
    await page.waitForLoadState("domcontentloaded"); await sleep(1200);
    const form = page.locator("form").filter({ has: page.getByRole("button", { name: "Save results" }) });
    const inputs = form.locator("input[type=text], input:not([type]), input[type=number]");
    const n = await inputs.count();
    for (let i = 0; i < Math.min(n, values.length); i++) await type(page, inputs.nth(i), values[i], { delay: 60 });
    await click(page, form.getByRole("button", { name: "Save results" }));
    await page.waitForLoadState("domcontentloaded"); await sleep(1200);
    await click(page, page.getByRole("button", { name: "Verify and sign" }));
    await page.waitForLoadState("domcontentloaded"); await sleep(1500);
    await gotoModule(page, "Laboratory");
  }
  await hisLogout(s);
}

const RAD = {
  "Bilateral mammogram": {
    findings: "Right breast: irregular spiculated mass, 2.8 x 2.2 cm, upper outer quadrant at 10 o'clock, with pleomorphic microcalcifications. Right axilla: one enlarged lymph node, 1.6 cm, with loss of the fatty hilum. Left breast: scattered fibroglandular density, no suspicious lesion.",
    impression: "Right breast mass, BI-RADS 5, highly suggestive of malignancy, with a suspicious right axillary node. Left breast BI-RADS 1.",
  },
  "CECT chest, abdomen and pelvis": {
    findings: "Lungs clear, no pulmonary nodule or pleural effusion. Liver normal in size, no focal lesion. No ascites or abdominal lymphadenopathy. No lytic or sclerotic lesion in the visualised skeleton. Right axillary node 1.6 cm, as on mammography.",
    impression: "No evidence of distant metastasis in the chest, abdomen or pelvis.",
  },
};
async function radiology(s) {
  const page = s.page;
  const st = state();
  mark("ch:radiology");
  await hisLogin(s, "radiologist@vaidyx-demo.invalid", "radiologist");
  await gotoModule(page, "Radiology");
  for (const [test, r] of Object.entries(RAD)) {
    mark(`rad:${test}`);
    await openOrder(page, st.accessions[test]);
    const sched = page.locator("form").filter({ has: page.getByRole("button", { name: "Schedule" }) });
    if (await sched.count()) {
      const room = sched.getByLabel("Modality room");
      if (await room.count()) { await hover(page, room); const opts = await room.locator("option").allInnerTexts(); const pick = opts.find((o) => /mammo/i.test(o) && /mammo/i.test(test)) || opts.find((o) => /CT/.test(o) && /CECT/.test(test)) || opts[1] || opts[0]; await room.selectOption({ label: pick }); }
      await click(page, sched.getByRole("button", { name: "Schedule" }));
      await page.waitForLoadState("domcontentloaded"); await sleep(1200);
    }
    const done = page.getByRole("button", { name: /exam done|Exam performed|Mark done/i }).first();
    if (await done.count()) { await click(page, done); await page.waitForLoadState("domcontentloaded"); await sleep(1200); }
    const form = page.locator("form").filter({ has: page.getByRole("button", { name: "Save preliminary" }) });
    await scrollTo(page, form.getByLabel(/^Findings/), "center");
    await type(page, form.getByLabel(/^Findings/), r.findings, { delay: 14 });
    await type(page, form.getByLabel(/^Impression/), r.impression, { delay: 14 });
    await click(page, form.getByRole("button", { name: "Save preliminary" }));
    await page.waitForLoadState("domcontentloaded"); await sleep(1200);
    mark(`rad:sign:${test}`);
    await click(page, page.getByRole("button", { name: "Sign final" }));
    await page.waitForLoadState("domcontentloaded"); await sleep(1800);
    await gotoModule(page, "Radiology");
  }
  await hisLogout(s);
}

const HPE = {
  Specimen: "Core biopsy, right breast at 10 o'clock, in 10% buffered formalin",
  Gross: "Three linear grey-white cores, 1.2 to 1.5 cm, entirely submitted",
  Microscopy: "Cores show an infiltrating carcinoma in nests and cords with moderate nuclear pleomorphism; mitoses 6 per 10 high-power fields. No lymphovascular invasion seen in the cores.",
  "Histological type": "Invasive breast carcinoma of no special type",
  Grade: "Grade 2 (Nottingham score 6)",
  Diagnosis: "Right breast, core biopsy: invasive breast carcinoma of no special type, grade 2. IHC for ER, PR, HER2 and Ki-67 to follow.",
};
async function pathology(s) {
  const page = s.page;
  const st = state();
  mark("ch:pathology");
  await hisLogin(s, "pathologist@vaidyx-demo.invalid", "pathologist");
  await gotoModule(page, "Pathology");
  mark("path:hpe");
  await openOrder(page, st.accessions["Histopathology report (biopsy)"]);
  const recv = page.getByRole("button", { name: "Receive specimen" });
  if (await recv.count()) { await click(page, recv); await page.waitForLoadState("domcontentloaded"); await sleep(1200); }
  for (const [label, text] of Object.entries(HPE)) {
    const f = page.getByLabel(new RegExp(`^${label.replace(/[()]/g, "\\$&")}`)).first();
    await scrollTo(page, f);
    await type(page, f, text, { delay: 14 });
  }
  mark("path:sign-hpe");
  await click(page, page.getByRole("button", { name: "Sign final" }));
  await page.waitForLoadState("domcontentloaded"); await sleep(1800);
  await gotoModule(page, "Pathology");
  await sleep(1500);
  await hisLogout(s);
}

module.exports = { reception, opd, lab, radiology, pathology, hisLogin, hisLogout, gotoModule, openOrder, P };
