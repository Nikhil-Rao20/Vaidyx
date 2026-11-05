// Ask PubMed, one component in three places (docs/pubmed-ask/DESIGN.md section 8): the Home page (/pubmed, variant "page", the
// login's own history), the Case File's Ask panel (variant "panel", the team's PubMed threads, pinned first) and the meeting's side
// panel (variant "meeting", Case File mode for the case on the floor). The question box with the mic; the live steps while PubMed
// is searched; the answer card; the history. The papers come only from PubMed through the server; Vaidyx never applies them to a
// patient.
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import { BookOpen, Pin, RotateCcw, Search, WifiOff } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { notify } from "@/components/Toasts";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import { routeMissing } from "@/lib/live";
import { stopSpeaking } from "@/lib/voice";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, LoadingButton, NotYetState, SkeletonLines, errorText, fmtDateTime, useAnnounce } from "@/features/casefile/components/common";
import {
  LABEL_CASE, LABEL_HOME, getCaseThreads, getHistory, pinThread, savePaper, threadsKey, usePubMedJob,
  type AskInput, type PubMedThread, type ThreadList, type Years,
} from "./api";
import { AnswerCard, unavailableTitle, type SaveControl } from "./AnswerCard";
import { LiveSteps } from "./LiveSteps";
import { PubMedMark } from "./PubMedMark";

const MAX_Q = 600;

/** One-click examples (they fill the box; the doctor still presses Ask). From the 3 Nov live run's fixed questions. */
export const EXAMPLES: Array<{ short: string; question: string }> = [
  { short: "Metronomic chemotherapy, head and neck, India", question: "What did trials from India report about low-dose metronomic chemotherapy in head and neck cancer?" },
  { short: "Neoadjuvant pembrolizumab, triple-negative breast", question: "What pathological complete response did trials report with neoadjuvant pembrolizumab in triple-negative breast cancer?" },
  { short: "Induction chemotherapy, cervical cancer", question: "What did trials report about induction chemotherapy before chemoradiation in locally advanced cervical cancer?" },
];

export interface PubMedAskProps {
  /** Case File mode: the team's threads of this Case File (the search may add its cancer and documented terms). */
  caseId?: string;
  variant?: "page" | "panel" | "meeting";
  /** Fills the question box; with autoAsk it is asked once (the one-click suggestion, the Home card). */
  initialQuestion?: string;
  autoAsk?: boolean;
  /** What the page knows: this login is the owner consultant and may Save a paper. The server's can_save wins when it sends one. */
  canSave?: boolean;
  compact?: boolean;
  /** One more line under the intro of the panel and meeting variants (where the answers are kept). */
  note?: string;
}

/** The short words of a thread in the history list. */
export function statusWords(t: PubMedThread): string {
  const lines = (t.statements ?? []).length;
  const papers = new Set((t.statements ?? []).flatMap((s) => (s.citations ?? []).map((c) => c.pmid))).size;
  switch (t.status) {
    case "answered": return `${lines} ${lines === 1 ? "line" : "lines"} from ${papers} ${papers === 1 ? "paper" : "papers"}`;
    case "not_found": return "No answer in the abstracts read";
    case "no_papers": return "PubMed found no papers";
    case "refused": return "Not a question for Ask PubMed";
    case "unavailable": return unavailableTitle(t.message);
    default: return String(t.status || "");
  }
}

function ThreadRow({ t, onOpen, active }: { t: PubMedThread; onOpen: () => void; active?: boolean }) {
  const bad = t.status === "unavailable" || t.status === "refused";
  return (
    <li>
      <button type="button" onClick={onOpen} aria-current={active ? "true" : undefined} data-testid="pubmed-thread-row" data-thread={t.id}
        className={cn("row-lift flex w-full items-start gap-2.5 rounded-md border p-2.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring",
          active ? "border-pubmed/60 bg-pubmed-soft" : "border-border bg-card hover:bg-accent")}>
        <BookOpen className={cn("mt-0.5 size-4 shrink-0", bad ? "text-muted-foreground" : "text-pubmed")} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="line-clamp-2 block text-sm font-medium leading-snug text-foreground">{t.question}</span>
          <span className="mt-0.5 block text-xs text-muted-foreground">{[statusWords(t), t.by_name ?? "", t.at ? fmtDateTime(t.at) : ""].filter(Boolean).join(" · ")}</span>
        </span>
        {t.pinned ? <Pin className="mt-0.5 size-3.5 shrink-0 text-pubmed" aria-label="pinned" /> : null}
      </button>
    </li>
  );
}

export function PubMedAsk({ caseId, variant = "page", initialQuestion, autoAsk, canSave, compact, note }: PubMedAskProps) {
  const qc = useQueryClient();
  const { me } = useSession();
  const reduce = useReducedMotion();
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const key = useMemo(() => threadsKey(caseId), [caseId]);
  const list = useQuery({ queryKey: key, queryFn: () => (caseId ? getCaseThreads(caseId) : getHistory()), retry: false });
  const notBuilt = list.isError && routeMissing(list.error);
  const [question, setQuestion] = useState(autoAsk ? "" : initialQuestion ?? "");
  const [openId, setOpenId] = useState<string | null>(null);
  const [announce, liveNode] = useAnnounce();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastAsked = useRef<AskInput | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveDenied, setSaveDenied] = useState(false);
  const [savedLocal, setSavedLocal] = useState<Record<string, string[]>>({});

  const onDone = useCallback((t: PubMedThread) => {
    qc.setQueryData<ThreadList>(key, (old) => ({ ...(old ?? {}), threads: [t, ...(old?.threads ?? []).filter((x) => x.id !== t.id)] }));
    void qc.invalidateQueries({ queryKey: key });
    setOpenId(t.id);
    announce(t.status === "answered" ? "The PubMed answer is ready." : t.message || "No answer.");
  }, [qc, key, announce]);
  const live = usePubMedJob({ caseId, onDone });

  const ask = useCallback((input: AskInput) => {
    if (live.busy) return;
    stopSpeaking();
    setSaveError(null);
    lastAsked.current = input;
    void live.start(input);
  }, [live]);

  const submit = () => {
    const t = question.trim();
    if (t.length < 3 || live.busy) return;
    ask({ question: t });
    setQuestion("");
  };
  // a refused start (the rate limit, no access) puts the question back in the box
  useEffect(() => {
    if (live.startError && lastAsked.current && !question.trim()) setQuestion(lastAsked.current.question);
    // only when a start fails
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live.startError]);

  // the one-click suggestion and the Home card: ask once; a timer so a development double mount asks only once
  const autoDone = useRef<string | null>(null);
  useEffect(() => {
    const q = (initialQuestion ?? "").trim();
    if (!q) return;
    if (!autoAsk) { setQuestion(q); return; }
    if (q.length < 3 || autoDone.current === q) return;
    const t = window.setTimeout(() => { autoDone.current = q; ask({ question: q }); }, 0);
    return () => window.clearTimeout(t);
    // ask is stable enough per render; the question is what matters
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAsk, initialQuestion]);

  const threads = useMemo(() => {
    const server = list.data?.threads ?? [];
    const latest = live.job?.thread;
    const all = latest && !server.some((x) => x.id === latest.id) ? [latest, ...server] : [...server];
    return all.sort((a, b) => (caseId ? Number(!!b.pinned) - Number(!!a.pinned) : 0) || String(b.at ?? "").localeCompare(String(a.at ?? "")));
  }, [list.data, live.job?.thread, caseId]);
  // while a question runs, its steps are the one thing open; the earlier answers fold into rows until it ends
  const open = live.busy ? undefined : openId ? threads.find((t) => t.id === openId) ?? threads[0] : threads[0];
  const others = threads.filter((t) => t.id !== open?.id);

  const pin = useMutation({
    mutationFn: ({ tid, pinned }: { tid: string; pinned: boolean }) => pinThread(caseId!, tid, pinned),
    onSuccess: (_r, v) => { void qc.invalidateQueries({ queryKey: key }); announce(v.pinned ? "Pinned for the team." : "Unpinned."); },
    onError: (e) => notify.error("Could not pin", errorText(e)),
  });

  const save = async (t: PubMedThread, pmid: string) => {
    if (!caseId || saving) return;
    setSaving(pmid);
    setSaveError(null);
    const title = t.papers?.find((p) => p.pmid === pmid)?.title;
    const keep = () => setSavedLocal((m) => ({ ...m, [t.id]: [...(m[t.id] ?? []), pmid] }));
    try {
      await savePaper(caseId, t.id, pmid);
      keep();
      void qc.invalidateQueries({ queryKey: ["published", caseId] });
      void qc.invalidateQueries({ queryKey: key });
      notify.success("Saved to the Published list", title);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setSaveDenied(true);
        setSaveError("Only a consultant of the owner team can save a paper to this Case File's Published list.");
      } else if (e instanceof ApiError && e.status === 409) {
        keep();  // already on the list
      } else setSaveError(`Could not save: ${errorText(e)}`);
    } finally {
      setSaving(null);
    }
  };
  const saveFor = (t: PubMedThread): SaveControl | undefined => {
    if (!caseId) return undefined;
    const allowed = !saveDenied && (t.can_save ?? list.data?.can_save ?? canSave ?? false);
    return { allowed, pending: saving, error: saveError, saved: new Set([...(t.saved_pmids ?? []), ...(savedLocal[t.id] ?? [])]), onSave: (pmid) => void save(t, pmid) };
  };

  const editQuestion = (q: string) => {
    setQuestion(q);
    window.setTimeout(() => { inputRef.current?.focus(); inputRef.current?.select(); }, 0);
  };
  const actionsFor = (t: PubMedThread) => ({
    busy: live.busy,
    onAgain: (i: { years: Years; words?: string }) => ask({ question: t.question, years: i.years, words: i.words }),
    onEditQuestion: editQuestion,
    onPin: caseId ? (pinned: boolean) => pin.mutate({ tid: t.id, pinned }) : undefined,
    pinBusy: pin.isPending,
    save: saveFor(t),
  });
  const label = caseId ? LABEL_CASE : LABEL_HOME;
  const page = variant === "page";

  if (notBuilt) return <NotYetState what="Ask PubMed" fallback="It comes with the PubMed routes on the server." />;

  const box = (
    <form className={cn("flex flex-col gap-1.5", page && "surface p-4")} onSubmit={(e) => { e.preventDefault(); submit(); }} data-testid="pubmed-form">
      <label htmlFor={`${uid}-q`} className={page ? "text-sm font-semibold text-foreground" : "sr-only"}>Your general question for PubMed</label>
      <Textarea ref={inputRef} id={`${uid}-q`} value={question} maxLength={MAX_Q} data-testid="pubmed-input"
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
        placeholder="A general question about published research, for example: what did trials report about induction chemotherapy in cervical cancer?"
        className={cn("resize-y text-sm", page ? "min-h-20" : "min-h-14")} />
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-[11rem] flex-1 text-xs text-muted-foreground">
          {me?.real_data ? "Search words leave this server for PubMed (NCBI, USA): do not type a name or anything that could identify the patient." : caseId ? "The search may add this Case File's cancer and documented terms. Never a name or number." : "Only search words go to PubMed, never a name or number."}
        </span>
        <MicButton target={inputRef} screen="pubmed" context="question" caseId={caseId} label="Dictate the question" hint={false}
          onInsert={(next) => { if (next.length > MAX_Q) setQuestion(next.slice(0, MAX_Q)); }} />
        <LoadingButton type="submit" size="sm" loading={live.busy} loadingText="Asking PubMed" disabled={question.trim().length < 3}
          className="min-h-11 hover:bg-primary-hover sm:min-h-8" data-testid="pubmed-ask-button">
          <Search className="size-4" aria-hidden />Ask PubMed
        </LoadingButton>
      </div>
      {live.startError ? <p role="alert" className="text-xs text-bad" data-testid="pubmed-start-error">{live.startError}</p> : null}
      {page || (!list.isLoading && threads.length === 0 && !live.busy) ? (
        <div className="mt-1 flex flex-wrap items-center gap-1.5" data-testid="pubmed-examples">
          <span className="text-xs text-muted-foreground">Try:</span>
          {EXAMPLES.map((x) => (
            <button key={x.short} type="button" onClick={() => editQuestion(x.question)} title={`Put this question in the box: ${x.question}`}
              className="min-h-9 max-w-full truncate rounded-full border border-border bg-card px-2.5 text-left text-xs text-foreground transition hover:border-pubmed/50 hover:bg-pubmed-soft active:scale-[0.98] sm:min-h-7">
              {x.short}
            </button>
          ))}
        </div>
      ) : null}
    </form>
  );

  const failed = live.job && live.job.status === "failed" && !live.job.thread ? (
    <div className="flex items-start gap-2.5 rounded-md status-bad p-3" role="alert" data-testid="pubmed-job-failed">
      <WifiOff className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">No answer this time</p>
        <p className="mt-0.5 text-sm text-foreground/80">{live.job.error}</p>
        <LoadingButton type="button" size="sm" className="mt-2 min-h-11 sm:min-h-8" onClick={() => lastAsked.current && ask(lastAsked.current)}><RotateCcw className="size-3.5" aria-hidden />Try again</LoadingButton>
      </div>
    </div>
  ) : null;

  const running = live.busy && live.job ? <LiveSteps job={live.job} /> : null;
  const loading = list.isLoading ? <SkeletonLines n={3} /> : null;
  const listError = list.isError ? <ErrorState error={list.error} retry={() => void list.refetch()} compact title="The earlier PubMed questions could not be loaded" /> : null;
  const empty = !list.isLoading && !list.isError && threads.length === 0 && !live.busy
    ? <EmptyState kind="search" title="No PubMed questions yet" text={caseId ? "Ask a general question; the team sees every answer here." : "Your questions and their answers stay here, only for you."} className="py-5" />
    : null;

  const card = (t: PubMedThread) => (
    <motion.div key={t.id} layout={!reduce} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <AnswerCard thread={t} caseId={caseId} defaultLabel={label} actions={actionsFor(t)} idPrefix={uid} />
    </motion.div>
  );

  if (page) {
    return (
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_23rem]" data-testid="pubmed-ask" data-variant={variant}>
        {liveNode}
        <div className="min-w-0 space-y-4">
          {box}
          {running}
          {failed}
          {open ? card(open) : !list.isLoading && !live.busy && !list.isError && !threads.length ? (
            <div className="surface flex flex-col items-center gap-3 px-6 py-8 text-center" data-testid="pubmed-intro">
              <PubMedMark size="lg" />
              <p className="max-w-prose text-sm text-muted-foreground">Ask a general question about published research. Vaidyx searches PubMed, reads the abstracts and writes 2 to 5 short lines, each with a word-for-word quote and its paper. Nothing comes from the model's own memory.</p>
            </div>
          ) : null}
        </div>
        <aside className="surface min-w-0 p-3 lg:sticky lg:top-20" aria-labelledby={`${uid}-hist`} data-testid="pubmed-history">
          <h2 id={`${uid}-hist`} className="mb-2 flex items-center gap-2 text-sm"><BookOpen className="size-4 text-pubmed" aria-hidden />Your PubMed questions{threads.length ? <span className="font-normal text-muted-foreground">({threads.length})</span> : null}</h2>
          {loading}{listError}{empty}
          {threads.length ? (
            <ul className="scroll-thin max-h-[70dvh] space-y-1.5 overflow-y-auto">
              {threads.map((t) => <ThreadRow key={t.id} t={t} onOpen={() => setOpenId(t.id)} active={open?.id === t.id} />)}
            </ul>
          ) : null}
        </aside>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col", compact ? "gap-2.5" : "gap-3")} data-testid="pubmed-ask" data-variant={variant}>
      {liveNode}
      <p className="flex items-start gap-2 text-xs leading-snug text-muted-foreground" data-testid="pubmed-intro-line">
        <PubMedMark size="sm" className="mt-px" />
        <span>General questions, answered only from PubMed abstracts. {caseId ? "Published evidence, not advice for this patient." : "Published evidence, not advice for any patient."}{note ? <span className="mt-0.5 block">{note}</span> : null}</span>
      </p>
      {box}
      {running}
      {failed}
      {loading}{listError}{empty}
      {open ? card(open) : null}
      {others.length ? (
        <section className="space-y-1.5" aria-labelledby={`${uid}-earlier`} data-testid="pubmed-earlier">
          <h3 id={`${uid}-earlier`} className="text-xs font-semibold text-muted-foreground">{caseId ? "Earlier PubMed questions on this Case File" : "Your earlier PubMed questions"} ({others.length})</h3>
          <ul className="space-y-1.5">{others.map((t) => <ThreadRow key={t.id} t={t} onOpen={() => setOpenId(t.id)} />)}</ul>
        </section>
      ) : null}
    </div>
  );
}
