// Ask PubMed in the screenshot run (docs/pubmed-ask/DESIGN.md section 8): the threads come from f2/pubmed.json, cut from the Part 1
// proof runs (docs/pubmed-ask/proof q1, q3, q4: public PubMed records and their quotes as the server verified them; no patient data).
// The refused, no papers and unavailable messages are the server's own sentences (pubmed_ask.py, the live run of 3 Nov). The two
// citation marks (whole sentence, added for the numbers) are set by hand on one quote each, only so the screens show them.
// routePubMed answers every PubMed route: a question starts a job that walks through the five steps (words, search, fetch, read,
// check), one step every `pollsPerStep` polls, then ends as the next outcome in `outcomes`.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Page, Route } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));
type AnyObj = any; // eslint-disable-line @typescript-eslint/no-explicit-any
const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));
const FX: Record<"case" | "home" | "home2", AnyObj> = JSON.parse(fs.readFileSync(path.join(HERE, "f2", "pubmed.json"), "utf8"));

const now = () => new Date().toISOString();
const ago = (min: number) => new Date(Date.now() - min * 60_000).toISOString();
const PEOPLE = { by: "rao@vxh.example", by_name: "Lakshmi Rao" };

/** A stored thread as GET answers it (no steps), at `minutesAgo`. */
export function pmThread(which: "case" | "home" | "home2", over: Record<string, unknown> = {}, minutesAgo = 30): AnyObj {
  const t = clone(FX[which]);
  delete t.steps;
  if (which === "case") {
    // the marks of a quote, for the screens (see the header)
    t.statements[0].citations[0].added_for_numbers = true;
    t.statements[1].citations[0].whole_sentence = true;
  }
  return { ...t, ...PEOPLE, at: ago(minutesAgo), ...over };
}

export const REFUSED = "Ask PubMed answers general questions about published research. It does not give advice, a stage or an outlook for a patient. Ask about published results, for example: \"What pathological complete response did trials report with neoadjuvant pembrolizumab in triple-negative breast cancer?\"";
export const NO_PAPERS = "PubMed found no paper for these search words. Change the words and try again.";
export const DOWN = "PubMed could not connect (ConnectError) after 4 tries. Try again in a minute.";
export const MODEL_DOWN = "The model could not be reached (LLMError). The papers PubMed found are listed.";

export type Outcome = "answered" | "refused" | "no_papers" | "unavailable" | "model_down" | "not_found" | "hold" | "failed";

export type PubMedMockOptions = {
  /** The outcome of each new question in turn; the last one repeats (default answered). "hold" stays at `holdAt` for ever. */
  outcomes?: Outcome[];
  holdAt?: "words" | "search" | "fetch" | "read" | "check";
  /** Polls per step (about 700 ms each); default 1. */
  pollsPerStep?: number;
  caseThreads?: AnyObj[];
  homeThreads?: AnyObj[];
  /** GET /cases/{id}/pubmed carries can_save (left out when undefined). */
  canSave?: boolean;
  /** Save answers 403 (not the owner consultant). */
  saveForbidden?: boolean;
  /** POST .../ask answers this instead of a job (429 rate limit, 403). */
  start?: { status: number; body?: unknown };
};

type Job = { id: string; question: string; years: number | null; words?: string; caseId: string | null; outcome: Outcome; polls: number; reply?: AnyObj };

const STEP_KEYS = ["words", "search", "fetch", "read", "check"] as const;

function stepsFor(j: Job, upTo: number, t: AnyObj) {
  const term = j.words || t?.search?.used || "pembrolizumab AND \"triple-negative breast cancer\"";
  const found = t?.counts?.found ?? 209;
  const read = t?.counts?.read ?? 17;
  const detail: Record<string, string> = {
    words: "writing the PubMed search words",
    search: `searching PubMed: ${term}${j.years ? ` (last ${j.years} years)` : " (all years)"}`,
    fetch: `${found} papers found, fetching the top 20 records`,
    read: `the model is reading ${read} abstracts`,
    check: "checking every quote against PubMed's text",
  };
  return STEP_KEYS.slice(0, upTo + 1).map((k, i) => ({ step: k, detail: detail[k], seconds: +(i * 1.6).toFixed(2) }));
}

/** The thread an outcome ends in, for this question. */
function finish(j: Job): AnyObj {
  // the proof run whose question matches (so a screen never shows lines about another question); a Case File keeps its own label
  const which = /pembrolizumab|breast/i.test(j.question) ? "case" : /cervi/i.test(j.question) ? "home2" : "home";
  const base = pmThread(which, j.caseId ? { label: FX.case.label } : { label: FX.home.label }, 0);
  const t: AnyObj = { ...base, id: `PM-new-${j.id}`, question: j.question, at: now(), pinned: false, saved_pmids: [], seconds: 12.4 };
  t.search = { ...t.search, years: j.years, ...(j.words ? { used: j.words, by: "doctor" } : {}) };
  const empty = { statements: [], papers: [], counts: { found: 0, fetched: 0, read: 0 } };
  switch (j.outcome) {
    case "refused": return { ...t, ...empty, status: "refused", message: REFUSED, search: {}, model: null, seconds: 0.1 };
    case "no_papers": return { ...t, ...empty, status: "no_papers", message: NO_PAPERS, search: { used: "zorblatinib AND \"quantum sarcoma\"", years: j.years, by: "model", count: 0, attempts: [] }, model: null, seconds: 3.2 };
    case "unavailable": return { ...t, ...empty, status: "unavailable", message: DOWN, model: null, seconds: 18.0 };
    case "model_down": return { ...t, statements: [], status: "unavailable", message: MODEL_DOWN, papers: t.papers.map((p: AnyObj) => ({ ...p, cited: false })) };
    case "not_found": return { ...t, statements: [], status: "not_found", message: "No answer found in the PubMed abstracts read.", papers: t.papers.map((p: AnyObj) => ({ ...p, cited: false })) };
    default: return t;
  }
}

/** How far each outcome runs through the steps before it ends (refused ends before the first step). */
const LAST_STEP: Record<Outcome, number> = { answered: 4, not_found: 4, model_down: 3, unavailable: 1, no_papers: 1, refused: -1, hold: 99, failed: 2 };

export async function routePubMed(page: Page, o: PubMedMockOptions = {}) {
  const outcomes = [...(o.outcomes ?? ["answered"])];
  const per = Math.max(1, o.pollsPerStep ?? 1);
  const caseThreads: AnyObj[] = o.caseThreads ?? [];
  const homeThreads: AnyObj[] = o.homeThreads ?? [];
  const jobs = new Map<string, Job>();
  const asked: Array<{ path: string; body: AnyObj }> = [];
  let n = 0;
  await page.route(/\/api\/tb\/(pubmed|cases\/[^/]+\/pubmed)(\/|$)/, async (route: Route) => {
    const url = new URL(route.request().url());
    const m = route.request().method();
    const p = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const body = (): AnyObj => { try { return JSON.parse(route.request().postData() || "{}"); } catch { return {}; } };
    const cm = /^\/api\/tb\/cases\/([^/]+)\/pubmed(?:\/(.*))?$/.exec(p);
    const caseId = cm ? decodeURIComponent(cm[1]) : null;
    const rest = cm ? cm[2] ?? "" : p.replace(/^\/api\/tb\/pubmed\/?/, "");

    if (m === "GET" && p === "/api/tb/pubmed/history") return json({ threads: homeThreads });
    if (m === "GET" && caseId && rest === "") return json({ threads: caseThreads, ...(o.canSave === undefined ? {} : { can_save: o.canSave }) });
    if (m === "POST" && rest === "ask") {
      const b = body();
      asked.push({ path: p, body: b });
      if (o.start) return json(o.start.body ?? { detail: { message: "Too many PubMed questions in a short time.", code: "rate_limited" } }, o.start.status);
      const outcome = (outcomes.length > 1 ? outcomes.shift() : outcomes[0]) ?? "answered";
      const id = `PJ${++n}`;
      jobs.set(id, { id, question: String(b.question ?? ""), years: b.years ?? null, words: b.words, caseId, outcome, polls: 0 });
      return json({ job_id: id }, 202);
    }
    const jm = /^jobs\/([^/]+)$/.exec(rest);
    if (m === "GET" && !caseId && jm) {
      const j = jobs.get(jm[1]);
      if (!j) return json({ detail: { message: "No such job.", code: "not_found" } }, 404);
      if (j.reply) return json(j.reply);  // a finished job answers the same again
      j.polls += 1;
      const at = Math.floor((j.polls - 1) / per);
      const thread = finish(j);
      if (j.outcome === "hold") {
        const k = STEP_KEYS.indexOf(o.holdAt ?? "read");
        return json({ job_id: j.id, status: "running", steps: stepsFor(j, Math.min(at, k), thread) });
      }
      const last = LAST_STEP[j.outcome];
      if (at <= last) return json({ job_id: j.id, status: "running", steps: stepsFor(j, at, thread) });
      if (j.outcome === "failed") return json({ job_id: j.id, status: "failed", steps: stepsFor(j, last, thread), error: "The search stopped on the server. Ask again." });
      (j.caseId ? caseThreads : homeThreads).unshift(thread);
      // a failed job is a thread with status "unavailable" and the reason, never a 500 (the contract)
      j.reply = { job_id: j.id, status: thread.status === "unavailable" ? "failed" : "done", steps: last >= 0 ? stepsFor(j, last, thread) : [], thread };
      return json(j.reply);
    }
    const pin = /^([^/]+)\/pin$/.exec(rest);
    if (m === "POST" && caseId && pin) {
      const t = caseThreads.find((x) => x.id === decodeURIComponent(pin[1]));
      if (!t) return json({ detail: { message: "No such thread.", code: "not_found" } }, 404);
      t.pinned = !!body().pinned;
      return json(t);
    }
    const save = /^([^/]+)\/save$/.exec(rest);
    if (m === "POST" && caseId && save) {
      if (o.saveForbidden) return json({ detail: { message: "You do not have permission for this.", code: "forbidden" } }, 403);
      const t = caseThreads.find((x) => x.id === decodeURIComponent(save[1]));
      const pmid = String(body().pmid ?? "");
      if (t) t.saved_pmids = [...(t.saved_pmids ?? []), pmid];
      const paper = t?.papers?.find((x: AnyObj) => x.pmid === pmid) ?? {};
      return json({ id: `PUB-${pmid}`, title: paper.title, source: "pubmed", kind: "paper", label: "Published case, not advice for this patient" });
    }
    return route.fallback();
  });
  return { asked, caseThreads, homeThreads };
}

/** The records chat of the Case File with a general question the records cannot answer (suggest_pubmed). */
export function chatsWithSuggestion(base: { threads: AnyObj[] }) {
  return {
    threads: [
      { id: "T9", by: "rao@vxh.example", by_name: "Lakshmi Rao", at: ago(2), question: "What pathological complete response did trials report with neoadjuvant pembrolizumab in triple-negative breast cancer?", status: "not_documented", pinned: false, stale: false, seconds: 6, statements: [],
        message: "Not documented in the records of this Case File.", suggest_pubmed: true },
      ...base.threads,
    ],
  };
}

/** Defaults for the shared mock (helpers.ts) and the Case File routes (f2.ts): the history, a finished job, the team's threads. */
export const pubmedDefaults = {
  history: () => ({ threads: [pmThread("home", {}, 60 * 20), pmThread("home2", {}, 60 * 48)] }),
  caseThreads: () => ({ threads: [pmThread("case", {}, 90)] }),
  job: (id: string) => ({ job_id: id, status: "done", steps: stepsFor({ id, question: "", years: null, caseId: null, outcome: "answered", polls: 0 }, 4, FX.home), thread: pmThread("home", { id: `PM-${id}` }, 0) }),
};
