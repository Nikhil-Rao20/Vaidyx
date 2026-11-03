// Ask PubMed Part 2, the live check on the real app (:7000) with real PubMed and the real model. Synthetic Case File TB-2026-0011
// (Rekha Sharma, cervix; treating Gynaecologic Oncology) only. Logins by name, passwords read in code (lib.mjs), never printed.
// 1. The treating consultant: Case File Ask, PubMed tab, a live answer (steps, lines, quote popover, papers, Save), a records question
//    that gets the suggestion and its one click, a refused question; the /pubmed page on the laptop and the phone (Dock).
// 2. The MDT Coordinator: the Home card, a meeting with the Case File on the floor and its Ask PubMed panel; the meeting is ended.
// 3. Access over the API: a department admin may not ask; a job is only its starter's; no email, key or eutils URL in any answer.
// Run: OUT=/data/vaidyx/pubmed-ask/shots node docs/pubmed-ask/tools/live_screens.mjs
import { BASE, H, open, settle, shot, note, problem, finish, j } from "../../meetings-v2/tools/lib.mjs";

const CASE = "TB-2026-0011";
const Q_CASE = "What did trials report about induction chemotherapy before chemoradiation in locally advanced cervical cancer?";
const Q_HOME = "What did trials from India report about low-dose metronomic chemotherapy in head and neck cancer?";
const Q_GENERAL_IN_RECORDS = "What did trials report about pembrolizumab with chemoradiotherapy in locally advanced cervical cancer?";
const ANSWER_MS = 120000;
const today = new Date().toISOString().slice(0, 10);

async function waitAnswer(page, scope, label) {
  const t0 = Date.now();
  const steps = scope.getByTestId("pubmed-steps").first();
  if (await steps.isVisible({ timeout: 8000 }).catch(() => false)) note(`${label}: live steps shown: ${(await steps.innerText()).replace(/\s+/g, " ").slice(0, 160)}`);
  else note(`${label}: steps not seen (answer may have come fast)`);
  const done = scope.getByTestId("pubmed-answer").first();
  await done.waitFor({ timeout: ANSWER_MS }).catch(() => problem(`${label}: no answer card in ${ANSWER_MS / 1000} s`));
  note(`${label}: answer card after ${Math.round((Date.now() - t0) / 1000)} s, ${await scope.getByTestId("pubmed-line").count()} lines, ${await scope.getByTestId("pubmed-paper").count()} papers`);
  return done;
}

async function noLeaks(rq, url, label) {
  const r = await rq.get(`${BASE}${url}`, { headers: H });
  const t = await r.text();
  if (/eutils|api_key|nikhilproffesion|%40|sha256/i.test(t)) problem(`${label}: provenance or email in ${url}`);
  else note(`${label}: ${url} ${r.status()}, no email / key / eutils URL`);
}

// ---- 1. the treating consultant -------------------------------------------------------------------------------------------------------
const doc = await open("tb-gynonc-doc");
try {
  const p = doc.page;
  await p.goto(`${BASE}/tb-nik/cases/${CASE}`); await settle(p, 1500);
  await p.getByTestId("ask-bubble").or(p.getByRole("button", { name: /Ask about this patient/ })).first().click();
  const panel = p.getByTestId("ask-panel").first();
  await panel.waitFor({ timeout: 10000 });
  await shot(p, "live-casefile-ask-tabs", { full: false });
  await panel.getByTestId("ask-tab-pubmed").click(); await settle(p, 400);
  await panel.getByTestId("pubmed-input").fill(Q_CASE);
  await panel.getByTestId("pubmed-ask-button").click();
  await p.waitForTimeout(2500);
  await shot(p, "live-casefile-steps", { full: false });
  await waitAnswer(p, panel, "Case File PubMed");
  await shot(p, "live-casefile-answer", { full: false });
  const label = await panel.getByTestId("pubmed-label").first().innerText().catch(() => "");
  if (!/not advice for this patient/i.test(label)) problem(`Case File label wrong: ${label}`); else note("Case File label: " + label.replace(/\s+/g, " "));
  const chip = panel.getByTestId("pubmed-quote-chip").first();
  if (await chip.count()) {
    await chip.click(); await settle(p, 400);
    const q = p.getByTestId("pubmed-quote").first();
    note("quote popover: " + (await q.innerText().catch(() => "MISSING")).replace(/\s+/g, " ").slice(0, 220));
    await shot(p, "live-casefile-quote", { full: false });
    await p.keyboard.press("Escape");  // closes the popover; on a laptop the side sheet may close with it: open Ask again
    await settle(p, 400);
    if (!(await panel.isVisible().catch(() => false))) {
      note("Escape closed the Ask side sheet with the popover; opening Ask again");
      await p.getByTestId("ask-bubble").or(p.getByRole("button", { name: /Ask about this patient/ })).first().click();
      await panel.waitFor({ timeout: 10000 });
    }
  } else problem("no quote chip in the Case File answer");
  const pmidLink = panel.getByTestId("pubmed-pmid").first();
  const href = await pmidLink.getAttribute("href").catch(() => "");
  if (!/^https:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/\d+\/$/.test(href || "")) problem(`PMID link not a PubMed URL: ${href}`); else note(`PMID link: ${href}`);
  note(`Save buttons shown to the treating consultant: ${await panel.getByTestId("pubmed-save").count()}`);
  await panel.getByTestId("pubmed-papers").first().scrollIntoViewIfNeeded().catch(() => {});
  await shot(p, "live-casefile-papers", { full: false });

  // a general question asked under the records: the suggestion, then one click
  await panel.getByTestId("ask-tab-records").click(); await settle(p, 300);
  await panel.locator("#ask-input").fill(Q_GENERAL_IN_RECORDS);
  await panel.getByRole("button", { name: /^Ask$/ }).click();
  const sug = panel.getByTestId("suggest-pubmed").first();
  if (await sug.waitFor({ timeout: 90000 }).then(() => true).catch(() => false)) {
    note("records answer offered: " + (await sug.innerText()).replace(/\s+/g, " "));
    await shot(p, "live-casefile-suggestion", { full: false });
    await panel.getByTestId("suggest-pubmed-ask").first().click();
    await waitAnswer(p, panel, "Suggestion one click");
    await shot(p, "live-casefile-suggestion-answer", { full: false });
  } else problem("no 'Ask PubMed?' suggestion on a general question asked under the records");

  // a refused question in the PubMed tab
  await panel.getByTestId("ask-tab-pubmed").click(); await settle(p, 300);
  await panel.getByTestId("pubmed-input").fill("Should we give her chemoradiation?");
  await panel.getByTestId("pubmed-ask-button").click();
  await p.waitForTimeout(6000);
  note("refused question shows: " + (await panel.getByTestId("pubmed-answer").first().innerText().catch(() => "MISSING")).replace(/\s+/g, " ").slice(0, 200));
  await shot(p, "live-casefile-refused", { full: false });

  // the Home page, laptop
  await p.goto(`${BASE}/tb-nik/pubmed`); await settle(p, 1000);
  await p.getByTestId("pubmed-input").first().fill(Q_HOME);
  await p.getByTestId("pubmed-ask-button").first().click();
  await waitAnswer(p, p.getByTestId("pubmed-page").first(), "Home page");
  await shot(p, "live-page-answer");
  const homeLabel = await p.getByTestId("pubmed-label").first().innerText().catch(() => "");
  if (!/not advice for any patient/i.test(homeLabel)) problem(`Home label wrong: ${homeLabel}`);
  await noLeaks(doc.rq, `/api/tb/cases/${CASE}/pubmed`, "Case File threads");
  await noLeaks(doc.rq, `/api/tb/pubmed/history`, "Home history");
} catch (e) {
  problem("consultant run stopped: " + String(e.message || e).slice(0, 300));
}
// the phone, same login
const phone = await open("tb-gynonc-doc", { viewport: { width: 390, height: 844 } });
try {
  await phone.page.goto(`${BASE}/tb-nik/cases`); await settle(phone.page, 1200);
  await shot(phone.page, "live-phone-home", { full: false });
  await phone.page.goto(`${BASE}/tb-nik/pubmed`); await settle(phone.page, 1200);
  await shot(phone.page, "live-phone-pubmed", { full: false });
  const hist = phone.page.getByTestId("pubmed-thread-row").first();
  if (await hist.count()) { await hist.click(); await settle(phone.page, 800); await shot(phone.page, "live-phone-pubmed-answer"); }
  else problem("phone: no history row for the earlier Home question");
} catch (e) {
  problem("phone run stopped: " + String(e.message || e).slice(0, 300));
} finally { await phone.browser.close(); }

// ---- 2. the MDT Coordinator: Home card and the meeting panel ----------------------------------------------------------------------------
const mdt = await open("tb-mdt");
let mid = "";
try {
  const p = mdt.page;
  await p.goto(`${BASE}/tb-nik/cases`); await settle(p, 1200);
  if (!(await p.getByTestId("pubmed-home-card").count())) problem("coordinator: no Ask PubMed card on Home"); else note("coordinator: Ask PubMed card on Home");
  await shot(p, "live-coordinator-home", { full: false });
  let r = await mdt.rq.post(`${BASE}/api/tb/meetings`, { headers: H, data: { date: today, time: "23:40", title: "Ask PubMed check (synthetic)", video: false } });
  mid = (await j(r))?.meeting?.id; note(`meeting ${mid} ${r.status()}`);
  await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/agenda/add`, { headers: H, data: { case_id: CASE, list: "discussion", reason: "Ask PubMed check (synthetic)" } });
  note(`start ${(await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/start`, { headers: H, data: {} })).status()}`);
  note(`current ${(await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/current`, { headers: H, data: { case_id: CASE } })).status()}`);
  await p.goto(`${BASE}/tb-nik/meetings/${mid}`); await settle(p, 3000);
  const skip = p.getByRole("button", { name: /Join without video|Continue without|Skip/ }).first();
  if (await skip.count()) { await skip.click(); await settle(p, 1500); }
  await p.getByRole("button", { name: /Ask PubMed|PubMed/ }).first().click(); await settle(p, 800);
  const mp = p.getByTestId("pubmed-panel").first();
  await mp.waitFor({ timeout: 10000 }).catch(() => problem("meeting: no Ask PubMed panel"));
  await mp.getByTestId("pubmed-input").fill("What did trials report about adjuvant chemotherapy after chemoradiation in locally advanced cervical cancer?");
  await mp.getByTestId("pubmed-ask-button").click();
  await waitAnswer(p, mp, "Meeting panel");
  await shot(p, "live-meeting-panel", { full: false });
} catch (e) {
  problem("coordinator run stopped: " + String(e.message || e).slice(0, 300));
} finally {
  if (mid) note(`end meeting ${(await mdt.rq.post(`${BASE}/api/tb/meetings/${mid}/end`, { headers: H, data: {} })).status()}`);
}

// ---- 3. access over the API ----------------------------------------------------------------------------------------------------------
try {
  const adm = await open("tb-rad-admin");
  const r = await adm.rq.post(`${BASE}/api/tb/pubmed/ask`, { headers: H, data: { question: Q_HOME } });
  if (r.status() !== 403) problem(`department admin asked PubMed: ${r.status()}`); else note("department admin: Home ask 403 (as designed)");
  const nav = await adm.page.goto(`${BASE}/tb-nik/`).then(() => adm.page.getByRole("link", { name: /^PubMed$/ }).count());
  note(`department admin: PubMed nav links ${nav}`);
  // a job is only its starter's
  const start = await mdt.rq.post(`${BASE}/api/tb/pubmed/ask`, { headers: H, data: { question: "What did trials report about HPV self-sampling for cervical screening?" } });
  const jid = (await j(start))?.job_id;
  const other = await adm.rq.get(`${BASE}/api/tb/pubmed/jobs/${jid}`, { headers: H });
  if (other.status() !== 404) problem(`another login read a job: ${other.status()}`); else note("another login reading a job: 404 (as designed)");
  await adm.browser.close();
  const path = await open("tb-path-head");
  const pr = await path.rq.get(`${BASE}/api/tb/cases/${CASE}/pubmed`, { headers: H });
  note(`Pathology head on ${CASE} PubMed threads: ${pr.status()} (403 unless Pathology is on the team with full scope)`);
  const ph = await path.rq.post(`${BASE}/api/tb/pubmed/ask`, { headers: H, data: { question: "What did studies report about p16 immunohistochemistry as a surrogate for HPV in cervical cancer?" } });
  note(`Pathology head Home ask: ${ph.status()}`);
  await path.browser.close();
} catch (e) {
  problem("access checks stopped: " + String(e.message || e).slice(0, 300));
}
await doc.browser.close();
await mdt.browser.close();
finish("pubmed_live_screens");
