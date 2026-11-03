// Ask PubMed (docs/pubmed-ask/DESIGN.md section 8): the thread, the job and the paper as the server sends them, the calls (through
// lib/api), and usePubMedJob, which starts a question and polls its job about every 700 ms so the screen can show PubMed's steps
// live. Every paper comes from PubMed's own record; every line carries a verbatim quote of an abstract and its PMID.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { routeMissing } from "@/lib/live";

// ---- shapes --------------------------------------------------------------------------------------------------------------
export type PubMedStatus = "answered" | "not_found" | "no_papers" | "refused" | "unavailable";
/** The year filter: every year (PubMed's Best Match, so a landmark trial is found), or the last 10 or 5 years. */
export type Years = null | 10 | 5;

export interface PubMedCitation {
  pmid: string;
  /** The paper's own words, verified word for word against its abstract (or title). */
  quote: string;
  /** Where in the abstract: "RESULTS", "CONCLUSIONS", "Abstract", "Title". */
  where: string;
  /** The model's quote was shortened; the paper's whole sentence is shown. */
  whole_sentence?: boolean;
  /** One more sentence of the same paper, added because it states a number the line gives. */
  added_for_numbers?: boolean;
}
export interface PubMedStatement { text: string; citations: PubMedCitation[] }

export interface PubMedPaper {
  pmid: string;
  title: string;
  journal?: string;
  journal_abbr?: string;
  year?: string | number;
  authors_line?: string;
  study_type?: string;
  tier?: number;
  preprint?: boolean;
  retracted?: boolean;
  retraction_notice?: boolean;
  concern?: boolean;
  india?: boolean;
  doi?: string | null;
  pmcid?: string | null;
  url?: string;
  has_abstract?: boolean;
  read?: boolean;
  why_not_read?: string;
  cited?: boolean;
  rank?: number;
}

export interface PubMedSearch {
  /** The words sent to PubMed. */
  used?: string;
  years?: number | null;
  /** "model" (written by the model from the question) or "words" (the question's own words). */
  by?: string;
  count?: number;
  attempts?: Array<{ term: string; years?: number | null; count?: number }>;
}

export interface PubMedThread {
  id: string;
  kind?: "pubmed";
  by?: string;
  by_name?: string;
  at?: string;
  question: string;
  status: PubMedStatus | string;
  message?: string;
  /** "From PubMed. Every line is quoted word for word from the paper's abstract. Published evidence, not advice for ..." */
  label?: string;
  search?: PubMedSearch;
  statements?: PubMedStatement[];
  papers?: PubMedPaper[];
  counts?: { found?: number; fetched?: number; read?: number };
  model?: string | null;
  seconds?: number;
  dropped?: number;
  invented_pmids?: number;
  pinned?: boolean;
  saved_pmids?: string[];
  /** Optional: the server says whether this login may Save a paper to the Published list. */
  can_save?: boolean;
  searched_at?: string;
}

export type StepKey = "words" | "search" | "fetch" | "read" | "check";
export interface PubMedStep { step: StepKey | string; detail?: string; seconds?: number }

export interface PubMedJob {
  job_id: string;
  status: "running" | "done" | "failed";
  steps?: PubMedStep[];
  thread?: PubMedThread | null;
  error?: string | null;
}

export interface ThreadList { threads: PubMedThread[]; can_save?: boolean }

/** The label under every answer (pubmed_ask.LABEL and LABEL_HOME), shown before the server sends its own. */
export const LABEL_CASE = "From PubMed. Every line is quoted word for word from the paper's abstract. Published evidence, not advice for this patient.";
export const LABEL_HOME = "From PubMed. Every line is quoted word for word from the paper's abstract. Published evidence, not advice for any patient.";
export const NLM_LINE = "Source: PubMed, U.S. National Library of Medicine";
export const PUBMED_HOME = "https://pubmed.ncbi.nlm.nih.gov/";

export const paperUrl = (p: Pick<PubMedPaper, "pmid" | "url">) => p.url || `${PUBMED_HOME}${encodeURIComponent(p.pmid)}/`;

// ---- calls ---------------------------------------------------------------------------------------------------------------
export interface AskInput { question: string; years?: Years; words?: string }

function askBody(i: AskInput) {
  const body: Record<string, unknown> = { question: i.question };
  if (i.years) body.years = i.years;
  if (i.words && i.words.trim()) body.words = i.words.trim();
  return body;
}

export const askPubMed = (i: AskInput, caseId?: string) =>
  api.post<{ job_id: string }>(caseId ? EP.casePubmedAsk(caseId) : EP.pubmedAsk, askBody(i));
export const getJob = (jobId: string, signal?: AbortSignal) => api.get<PubMedJob>(EP.pubmedJob(jobId), { signal });
export const getHistory = () => api.get<ThreadList>(EP.pubmedHistory);
export const getCaseThreads = (caseId: string) => api.get<ThreadList>(EP.casePubmed(caseId));
export const pinThread = (caseId: string, tid: string, pinned: boolean) => api.post<PubMedThread>(EP.casePubmedPin(caseId, tid), { pinned });
export const savePaper = (caseId: string, tid: string, pmid: string) => api.post<Record<string, unknown>>(EP.casePubmedSave(caseId, tid), { pmid });

export const threadsKey = (caseId?: string) => (caseId ? ["pubmed", "case", caseId] : ["pubmed", "home"]);

/** A plain sentence for a refused start (the rate limit, no access, the route not built yet, no connection). */
export function startErrorText(e: unknown): string {
  if (routeMissing(e)) return "Ask PubMed is not available on this server yet.";
  if (e instanceof ApiError) {
    if (e.status === 429) return "Too many PubMed questions in a short time. Please wait a few minutes, then ask again.";
    if (e.status === 403) return e.message && !/permission for this/.test(e.message) ? e.message : "You cannot ask PubMed here. Ask PubMed works for doctors, the MDT Coordinator and outside experts.";
    if (e.status === 0) return "No connection to the server. Check the network and try again.";
    return e.message;
  }
  return e instanceof Error && e.message ? e.message : "Something went wrong. Try again.";
}

// ---- the steps -----------------------------------------------------------------------------------------------------------
export const STEP_ORDER: StepKey[] = ["words", "search", "fetch", "read", "check"];
export type StepState = "done" | "active" | "waiting";
export interface StepView { key: StepKey; label: string; state: StepState; detail: string; seconds?: number }

const num = (s?: string | null) => {
  const m = /(\d[\d,]*)/.exec(s ?? "");
  return m ? Number(m[1].replace(/,/g, "")) : null;
};

/** The server's step text as a sentence ("searching PubMed: ..." reads "Searching PubMed: ..."). */
export const sentence = (s?: string | null) => {
  const t = (s ?? "").trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : "";
};

/** The five steps in order with their state: the last step the server reported is working, those before it are done. */
export function stepViews(steps: PubMedStep[], finished = false): StepView[] {
  const last = new Map<string, PubMedStep>();
  for (const s of steps) last.set(String(s.step), s);
  const reached = STEP_ORDER.reduce((n, k, i) => (last.has(k) ? i : n), -1);
  const fetchDetail = last.get("fetch")?.detail;
  const found = fetchDetail ? num(/papers? found/i.test(fetchDetail) ? fetchDetail : "") : null;
  const reading = num(/reading\s+(\d+)/i.exec(last.get("read")?.detail ?? "")?.[1] ?? "");
  const label: Record<StepKey, string> = {
    words: "Writing the search words",
    search: found !== null ? `Searching PubMed (${found.toLocaleString("en-IN")} found)` : "Searching PubMed",
    fetch: "Fetching the records",
    read: reading !== null ? `Reading ${reading} abstracts` : "Reading the abstracts",
    check: "Checking every quote",
  };
  return STEP_ORDER.map((key, i) => {
    const s = last.get(key);
    const state: StepState = i < reached || (finished && i <= reached) ? "done" : i === reached ? "active" : "waiting";
    return { key, label: label[key], state, detail: sentence(s?.detail), seconds: s?.seconds };
  });
}

// ---- the papers ----------------------------------------------------------------------------------------------------------
/** The paper list in its order (cited first, in the order the lines cite them; then read; then not read) with the number each
 *  quote chip carries. */
export function orderPapers(t: Pick<PubMedThread, "papers" | "statements">): { papers: PubMedPaper[]; numberOf: Map<string, number> } {
  const firstCite = new Map<string, number>();
  let n = 0;
  for (const s of t.statements ?? []) for (const c of s.citations ?? []) if (!firstCite.has(c.pmid)) firstCite.set(c.pmid, n++);
  const all = [...(t.papers ?? [])];
  const group = (p: PubMedPaper) => (p.cited || firstCite.has(p.pmid) ? 0 : p.read ? 1 : 2);
  const idx = new Map(all.map((p, i) => [p.pmid, i]));
  all.sort((a, b) => group(a) - group(b)
    || (group(a) === 0 ? (firstCite.get(a.pmid) ?? 99) - (firstCite.get(b.pmid) ?? 99) : 0)
    || (idx.get(a.pmid) ?? 0) - (idx.get(b.pmid) ?? 0));
  return { papers: all, numberOf: new Map(all.map((p, i) => [p.pmid, i + 1])) };
}

// ---- the job ----------------------------------------------------------------------------------------------------------------
export const POLL_MS = 700;
/** Poll failures in a row (no connection) before the screen gives up and says so. */
const MAX_MISSES = 8;

export interface LiveJob {
  jobId: string | null;
  question: string;
  years: Years;
  words?: string;
  status: "starting" | "running" | "done" | "failed";
  steps: PubMedStep[];
  thread: PubMedThread | null;
  /** A failure with no thread (the job expired, the connection was lost). */
  error: string | null;
  startedAt: number;
}

/** Starts a question (Home or the Case File's route) and polls its job until done or failed; stops polling on unmount or reset.
 *  onDone gets the finished thread (a failed job is a thread with status "unavailable" and the reason). */
export function usePubMedJob({ caseId, onDone }: { caseId?: string; onDone?: (t: PubMedThread) => void } = {}) {
  const [job, setJob] = useState<LiveJob | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const ac = useRef<AbortController | null>(null);
  const run = useRef(0);  // a new start or a reset ends the earlier run's polling
  const alive = useRef(true);
  const done = useRef(onDone);
  useEffect(() => { done.current = onDone; });

  const stop = useCallback(() => {
    run.current += 1;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
    ac.current?.abort();
    ac.current = null;
  }, []);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; stop(); };
  }, [stop]);

  const poll = useCallback((jobId: string, myRun: number, misses: number) => {
    timer.current = window.setTimeout(async () => {
      if (!alive.current || myRun !== run.current) return;
      const ctl = new AbortController();
      ac.current = ctl;
      try {
        const j = await getJob(jobId, ctl.signal);
        if (!alive.current || myRun !== run.current) return;
        const steps = Array.isArray(j.steps) ? j.steps : [];
        if (j.status === "running") {
          setJob((cur) => (cur && cur.jobId === jobId ? { ...cur, status: "running", steps } : cur));
          poll(jobId, myRun, 0);
          return;
        }
        const thread = j.thread ?? null;
        const error = thread ? null : j.error || "PubMed could not answer this time. Try again.";
        setJob((cur) => (cur && cur.jobId === jobId ? { ...cur, status: j.status === "done" ? "done" : "failed", steps, thread, error } : cur));
        if (thread) done.current?.(thread);
      } catch (e) {
        if ((e as Error)?.name === "AbortError" || !alive.current || myRun !== run.current) return;
        const gone = e instanceof ApiError && (e.status === 404 || e.status === 403);
        if (gone || misses + 1 >= MAX_MISSES) {
          const error = gone ? "This search is no longer on the server (it keeps a search for 15 minutes). Ask again."
            : "Lost touch with the server while PubMed was being searched. Check the network and ask again.";
          setJob((cur) => (cur && cur.jobId === jobId ? { ...cur, status: "failed", error } : cur));
          return;
        }
        poll(jobId, myRun, misses + 1);
      }
    }, POLL_MS);
  }, []);

  const start = useCallback(async (input: AskInput) => {
    stop();
    const myRun = run.current;
    setStartError(null);
    setJob({ jobId: null, question: input.question, years: input.years ?? null, words: input.words, status: "starting", steps: [], thread: null, error: null, startedAt: Date.now() });
    try {
      const r = await askPubMed(input, caseId);
      if (!alive.current || myRun !== run.current) return;
      if (!r?.job_id) throw new ApiError(500, "The server did not start the search. Try again.");
      setJob((cur) => (cur ? { ...cur, jobId: r.job_id, status: "running" } : cur));
      poll(r.job_id, myRun, 0);
    } catch (e) {
      if (!alive.current || myRun !== run.current) return;
      setJob(null);
      setStartError(startErrorText(e));
    }
  }, [caseId, poll, stop]);

  const reset = useCallback(() => { stop(); setJob(null); setStartError(null); }, [stop]);

  const busy = !!job && (job.status === "starting" || job.status === "running");
  return { job, busy, start, reset, startError, clearStartError: () => setStartError(null) };
}
