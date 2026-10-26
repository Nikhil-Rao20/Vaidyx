// The Staging card (owner decision 22 Oct 2026, docs/staging/DECISION.md), at the top of the Overview. The doctor's walk through the
// staging book, done by Vaidyx and shown step by step: for T, N and M the report line on the left and the book line on the right (a click
// opens the book at that page with the line highlighted), then the row of the stage table. Labelled "Vaidyx draft stage, for the board to
// confirm"; a consultant confirms it or marks it wrong with a reason. A part no report states says "Cannot stage" and can be filled in by
// the doctor ("entered by Dr X, no report"). The stage the reports wrote, and its history, sit beside it; a difference is flagged.
// For breast, the prognostic stage group (AJCC 8, pp. 621 to 624) sits under the anatomic one (night-v3 item 1.12): the same label and
// guards, the grade, HER2, ER and PR walked like T, N and M, confirmed or marked wrong on its own, a written prognostic stage flagged.
// A resident on the team sends the confirmation to the treating consultant for sign-off, pinned to the draft on the card (night-v3 item
// 1.8); the card says "Waiting for Dr X's sign-off" while that proposal is pending.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, BookOpen, Check, CheckCircle2, Clock, FlaskConical, History, Info, Layers, PenLine, RefreshCw, Send, XCircle } from "lucide-react";
import { notify } from "@/components/Toasts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { SourceTarget } from "../components/SourceViewer";
import { LoadingButton, SkeletonLines, errorText, fmtDate, fmtDateTime, niceTitle } from "../components/common";
import { SourceChip } from "../steps/Value";
import { getProposals } from "../api";
import { confirmStaging, enterPart, proposeStaging, rejectStaging, runStaging, type BookTarget, type Component, type Criterion, type PrognosticDraft, type ProgPart, type Quote, type StagingView, type Which, type Written } from "./api";

const PART_WORD: Record<"T" | "N" | "M", string> = { T: "Primary tumour", N: "Regional lymph nodes", M: "Distant metastasis" };
const FIGO_WORD: Record<"T" | "N" | "M", string> = { T: "Local extent", N: "Lymph nodes", M: "Distant spread" };
const PROG_WORD: Record<ProgPart, string> = { G: "Histologic grade", HER2: "HER2 status", ER: "ER status", PR: "PR status" };
const PROG_PARTS: ProgPart[] = ["G", "HER2", "ER", "PR"];
// The book's categories for the markers, in plain words ("negative_ish_equivocal" is the table's footnote *).
const CRIT_WORD: Record<string, string> = { positive: "Positive", negative: "Negative", ihc_3plus: "IHC 3+", ihc_0_1plus: "IHC 0 or 1+", negative_ish_equivocal: "Equivocal by ISH" };
const cap = (x?: string) => (x ? x.charAt(0).toUpperCase() + x.slice(1) : "");

/** A resident's sign-off of one draft (anatomic or prognostic): the button, then "Waiting for Dr X's sign-off" while it is pending. */
interface SignOff { canPropose: boolean; consultantName: string; waiting: (which: Which) => boolean; send: (which: Which) => void; sending: Which | null }

function SignOffButton({ which, stage, s, testId }: { which: Which; stage: string; s: SignOff; testId: string }) {
  if (s.waiting(which)) return <span className="inline-flex items-center gap-1.5 rounded-md bg-muted px-2.5 py-1.5 text-sm text-muted-foreground" data-testid={`${testId}-waiting`}><Clock className="size-4" aria-hidden />Waiting for Dr {s.consultantName}'s sign-off</span>;
  return <LoadingButton onClick={() => s.send(which)} loading={s.sending === which} data-testid={testId} aria-label={`Send ${which === "prognostic" ? "prognostic stage" : "Stage"} ${stage} to Dr ${s.consultantName} for sign-off`}><Send className="size-4" />Send to Dr {s.consultantName} for sign-off</LoadingButton>;
}

function BookChip({ book, page, find, label, onOpen, here = true }: { book: string; page: number | null; find?: string; label: string; onOpen: (t: BookTarget) => void; here?: boolean }) {
  if (!here || page == null) {
    return <span className="quote-chip" title="The book's PDF is not on this server yet: the line is shown here as the book prints it" data-testid="book-chip-missing"><BookOpen className="size-3 shrink-0" aria-hidden />{label} (PDF not on this server yet)</span>;
  }
  return (
    <button type="button" onClick={() => onOpen({ book, page, find, label })} className="quote-chip !border-brand/30 !bg-secondary !text-secondary-foreground hover:!border-brand" data-testid="book-chip">
      <BookOpen className="size-3 shrink-0" aria-hidden />{label}, p. {page}
    </button>
  );
}

// One step of the walk: the category, the report line (or the doctor's entry) and the book line. Used for T, N and M and for the grade
// and the markers of the prognostic stage group.
interface StepData { quotes: Quote[]; criterion: Criterion | null; note?: string; size_mm?: number; entered?: Component["entered"] }

function Step({ testId, word, cat, c, book, bookShort, onOpen, onBook, here }: { testId: string; word: string; cat: string; c: StepData; book: string; bookShort: string; onOpen: (t: SourceTarget) => void; onBook: (t: BookTarget) => void; here?: boolean }) {
  const q = c.quotes[0];
  return (
    <li className="grid gap-3 py-3 md:grid-cols-[5.5rem_minmax(0,1fr)_minmax(0,1fr)]" data-testid={testId}>
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{word}</p>
        <p className="mt-0.5 text-2xl font-bold tracking-tight text-foreground">{cat}</p>
      </div>
      <div className="min-w-0 rounded-md border border-border bg-muted/40 p-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{c.entered ? "Entered by the doctor" : "The report says"}</p>
        {c.entered ? (
          <p className="mt-1 text-sm text-foreground"><PenLine className="mr-1 inline size-3.5 text-muted-foreground" aria-hidden />{c.entered.reason}<span className="ml-1 text-xs text-muted-foreground">, {c.entered.by_name || c.entered.by}, no report</span></p>
        ) : q ? (
          <>
            <p className="mt-1 text-sm text-foreground">"{q.quote}"</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <SourceChip quote={{ doc_id: q.doc_id, doc_title: q.doc_title, page: q.page ?? 0, text: q.quote, date: q.date ?? null }} onOpen={onOpen} />
              {q.final === false ? <span className="rounded-md status-warn px-1.5 py-0.5 text-[11px] font-medium">from a report that is not final</span> : null}
              {typeof c.size_mm === "number" ? <span className="text-xs text-muted-foreground">measured {c.size_mm >= 10 ? `${(c.size_mm / 10).toFixed(1)} cm` : `${c.size_mm} mm`}</span> : null}
            </div>
          </>
        ) : null}
        {c.note ? <p className="mt-1 text-xs text-muted-foreground">{c.note}</p> : null}
      </div>
      {c.criterion ? (
        <div className="min-w-0 rounded-md border border-brand/25 bg-secondary/40 p-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">The book says</p>
          <p className="mt-1 text-sm text-foreground"><span className="font-semibold">{c.criterion.cat}:</span> {c.criterion.text}</p>
          <div className="mt-1.5"><BookChip book={book} page={c.criterion.page} find={c.criterion.find} label={bookShort} onOpen={onBook} here={here} /></div>
        </div>
      ) : null}
    </li>
  );
}

function FillPart({ part, caseId, options, onDone }: { part: "T" | "N" | "M"; caseId: string; options: Array<{ cat: string; text: string }>; onDone: (v: StagingView) => void }) {
  const [open, setOpen] = useState(false);
  const [cat, setCat] = useState("");
  const [reason, setReason] = useState("");
  const m = useMutation({ mutationFn: () => enterPart(caseId, part, cat, reason.trim()), onSuccess: (v) => { setOpen(false); onDone(v); } });
  if (!open) return <Button size="xs" variant="outline" onClick={() => setOpen(true)}><PenLine className="size-3" />Fill it in myself</Button>;
  return (
    <form className="mt-1.5 space-y-1.5 rounded-md border border-border bg-card p-2" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      <select value={cat} onChange={(e) => setCat(e.target.value)} className="h-8 w-full rounded-md border border-input bg-card px-2 text-sm" aria-label={`${part} category`}>
        <option value="">Choose the {part} category</option>
        {options.map((o) => <option key={o.cat} value={o.cat}>{o.cat}: {o.text.length > 90 ? `${o.text.slice(0, 88)}...` : o.text}</option>)}
      </select>
      <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="On what you base it (for example: clinical examination, no symptoms)" className="h-8 text-sm" maxLength={300} aria-label="Why" />
      <div className="flex gap-1.5">
        <LoadingButton size="xs" type="submit" loading={m.isPending} disabled={!cat || reason.trim().length < 3}>Save</LoadingButton>
        <Button size="xs" variant="ghost" type="button" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
      {m.isError ? <p role="alert" className="text-xs text-bad">{errorText(m.error)}</p> : null}
    </form>
  );
}

function History_({ written, onOpen, show, none = "No report writes a stage." }: { written: Written[]; onOpen: (t: SourceTarget) => void; show?: (w: Written) => string; none?: string }) {
  if (!written.length) return <p className="text-sm text-muted-foreground">{none}</p>;
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2" data-testid="stage-history">
      {written.map((w, i) => (
        <li key={`${w.doc_id}-${i}`} className="flex items-center gap-2">
          {i ? <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden /> : null}
          <span className={cn("rounded-md border px-2 py-1 text-sm", w.superseded ? "border-dashed border-border text-muted-foreground line-through" : "border-border bg-card")}>
            <span className="text-xs text-muted-foreground">{w.date ? fmtDate(w.date) : "date not stated"} · </span>
            <span className="font-semibold text-foreground">{show ? show(w) : w.value}</span>
            {w.prefix ? <span className="ml-1 rounded bg-muted px-1 text-[10px] font-semibold uppercase text-muted-foreground">{w.prefix === "c" ? "clinical" : w.prefix === "p" ? "pathological" : "after treatment"}</span> : null}
          </span>
          <SourceChip quote={{ doc_id: w.doc_id, doc_title: w.doc_title, page: w.page ?? 0, text: w.quote, date: null }} onOpen={onOpen} />
        </li>
      ))}
    </ol>
  );
}

// The breast prognostic stage group (AJCC 8, pp. 621 to 624), under the anatomic draft: the anatomic T, N and M with the grade and the
// HER2, ER and PR status, each from a verified report line; the row of the book's table; confirmed or marked wrong on its own ("which").
function Prognostic({ caseId, view, p, book, bookShort, here, canConfirm, signOff, onOpen, onBook, onChanged }: {
  caseId: string; view: StagingView; p: PrognosticDraft; book: string; bookShort: string; here: boolean; canConfirm: boolean; signOff: SignOff;
  onOpen: (t: SourceTarget) => void; onBook: (t: BookTarget) => void; onChanged: (v?: StagingView) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const which: Which = "prognostic";
  const confirm = useMutation({ mutationFn: () => confirmStaging(caseId, which), onSuccess: (v) => onChanged(v) });
  const reject = useMutation({ mutationFn: () => rejectStaging(caseId, reason.trim(), which), onSuccess: (v) => { setRejecting(false); setReason(""); onChanged(v); } });
  const ref = view.prognostic_ref;
  const sw = view.switch;
  const staged = p.status === "staged" && !!p.stage;
  const comps = p.components;
  const plain = (x?: string) => (x ?? "").replace(/^c(?=[TNM])/, "");
  const tnm = [p.tnm.T, p.tnm.N, p.tnm.M].map(plain).filter(Boolean).join(" ");
  const shown = (k: ProgPart) => (k === "G" ? comps.G?.cat ?? "" : cap(comps[k]?.cat));
  const markers = PROG_PARTS.filter((k) => comps[k]).map((k) => (k === "G" ? shown(k) : `${k} ${comps[k]?.cat}`)).join(", ");
  const missOf = (k: ProgPart) => p.missing.find((m) => m.startsWith(`${k}:`))?.replace(/^\w+:\s*/, "");
  const other = p.missing.filter((m) => !/^(G|HER2|ER|PR):/.test(m));
  const foot = (mark: string) => ref?.footnotes?.find((f) => f.mark === mark);
  const cmp = view.prognostic_comparison;
  const err = confirm.error || reject.error;
  return (
    <div className="space-y-3 border-t border-border pt-4" data-testid="prognostic-section">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-foreground">{p.label || ref?.label || "Prognostic stage group"}</h3>
        {sw.preview ? <span className="inline-flex items-center gap-1 rounded-md bg-warn-soft px-1.5 py-0.5 text-[11px] font-medium text-warn" title={sw.label}><FlaskConical className="size-3" aria-hidden />Preview</span> : null}
        <span className="flex-1" />
        {ref ? <BookChip book={book} page={ref.page} find={ref.find} label={bookShort} onOpen={onBook} here={here} /> : null}
      </div>
      {ref?.note ? <p className="text-xs text-muted-foreground">{ref.note}</p> : null}

      {/* the result */}
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-gradient-to-br from-secondary/70 to-card p-4 sm:flex-row sm:items-center" data-testid="prognostic-result">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{view.draft_label}</p>
          {staged ? (
            <p className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-3xl font-bold tracking-tight text-foreground">Prognostic stage {p.stage}</span>
              <span className="text-base font-semibold text-muted-foreground">{tnm}, {markers}</span>
            </p>
          ) : (
            <>
              <p className="mt-1 text-2xl font-bold tracking-tight text-foreground">Cannot stage yet</p>
              {other.length ? (
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-warn" data-testid="prognostic-missing">
                  {other.map((m) => <li key={m}>{m}</li>)}
                </ul>
              ) : null}
            </>
          )}
          <p className="mt-1 text-xs text-muted-foreground">Counted for the board only after a doctor confirms it. The grade, HER2, ER and PR come from report lines checked word for word; fixed rules, not a model, decide each category.</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {p.confirmed ? <span className="inline-flex items-center gap-1.5 rounded-md status-ok px-2.5 py-1.5 text-sm font-medium"><CheckCircle2 className="size-4" aria-hidden />Confirmed by {p.confirmed.by_name || p.confirmed.by}</span> : null}
          {p.rejected ? <span className="inline-flex items-center gap-1.5 rounded-md status-bad px-2.5 py-1.5 text-sm font-medium" title={p.rejected.reason}><XCircle className="size-4" aria-hidden />Marked wrong by {p.rejected.by_name || p.rejected.by}: {p.rejected.reason}</span> : null}
          {staged && canConfirm && !p.confirmed && !view.stale && view.draft?.confirmed && !view.draft?.rejected ? <LoadingButton onClick={() => confirm.mutate()} loading={confirm.isPending} data-testid="confirm-prognostic"><Check className="size-4" />Confirm prognostic stage {p.stage}</LoadingButton> : null}
          {staged && canConfirm && !p.confirmed && !view.stale && !(view.draft?.confirmed && !view.draft?.rejected) ? <span className="text-xs text-muted-foreground" data-testid="prognostic-needs-anatomic">Confirm the anatomic stage first: this group is built on its T, N and M.</span> : null}
          {staged && !canConfirm && signOff.canPropose && !p.confirmed && !view.stale ? <SignOffButton which="prognostic" stage={p.stage ?? ""} s={signOff} testId="propose-prognostic" /> : null}
          {staged && canConfirm && !rejecting && !p.rejected ? <Button variant="outline" onClick={() => setRejecting(true)} data-testid="reject-prognostic">This is wrong</Button> : null}
        </div>
      </div>
      {rejecting ? (
        <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); reject.mutate(); }}>
          <Input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="What is wrong? (recorded with your name)" className="h-9 max-w-md text-sm" maxLength={300} aria-label="What is wrong with the prognostic stage group" />
          <LoadingButton size="sm" type="submit" loading={reject.isPending} disabled={reason.trim().length < 3}>Save</LoadingButton>
          <Button size="sm" variant="ghost" type="button" onClick={() => setRejecting(false)}>Cancel</Button>
        </form>
      ) : null}

      {/* the walk: grade, HER2, ER, PR */}
      <ol className="divide-y divide-border">
        {PROG_PARTS.map((k) => {
          const c = comps[k];
          if (c) return <Step key={k} testId={`prog-step-${k}`} word={PROG_WORD[k]} cat={shown(k)} c={{ quotes: c.quotes, criterion: c.criterion ? { ...c.criterion, cat: CRIT_WORD[c.criterion.cat] ?? c.criterion.cat } : null, note: c.how ? `Decided from ${c.how}.` : undefined }} book={book} bookShort={bookShort} onOpen={onOpen} onBook={onBook} here={here} />;
          return (
            <li key={k} className="grid gap-3 py-3 md:grid-cols-[5.5rem_minmax(0,1fr)]" data-testid={`prog-step-${k}`}>
              <div><p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{PROG_WORD[k]}</p><p className="mt-0.5 text-2xl font-bold text-muted-foreground">?</p></div>
              <div className="rounded-md border border-dashed border-warn/50 bg-warn-soft/60 p-2.5">
                <p className="text-sm font-medium text-warn">Cannot stage: {missOf(k) ?? "not stated in a report"}</p>
              </div>
            </li>
          );
        })}
      </ol>

      {/* the row of the prognostic table */}
      {staged && p.row ? (
        <div className="space-y-1 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm" data-testid="prognostic-row">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Prognostic table</span>
            <span className="font-medium text-foreground">{tnm}, {markers}</span>
            <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
            <span className="font-semibold text-foreground">Prognostic stage {p.stage}</span>
            <span className="flex-1" />
            <BookChip book={book} page={p.row.page} find={p.row.page === ref?.page ? ref?.find : undefined} label={bookShort} onOpen={onBook} here={here} />
          </div>
          <p className="text-xs text-muted-foreground">The book prints this row as: {p.row.printed}</p>
          {p.row.changed_from_anatomic ? <p className="text-xs text-muted-foreground">The book marks this group with ***: grade and the markers move it more than one stage group from the anatomic stage group (footnote ***, p. {foot("***")?.page ?? 624}).</p> : null}
          {p.row.note ? <p className="text-xs text-muted-foreground">Note: {p.row.note}</p> : null}
        </div>
      ) : null}
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="prognostic-multigene"><Info className="size-3.5 shrink-0" aria-hidden />{p.multigene?.note || ref?.multigene_note}</p>

      {/* the prognostic stage the reports wrote: shown and flagged, never changed */}
      <div className="space-y-2">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"><History className="size-3.5" aria-hidden />Prognostic stage as written in the reports</p>
        {cmp ? (
          <p className={cn("flex items-start gap-1.5 rounded-md px-3 py-1.5 text-sm", cmp.result === "differs" ? "status-warn" : "status-ok")} data-testid="prognostic-compare">
            {cmp.result === "differs" ? <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />}
            <span>{cmp.result === "matches" ? `The draft matches what ${niceTitle(cmp.written.doc_title)} writes (prognostic stage ${cmp.written.stage}).`
              : `${niceTitle(cmp.written.doc_title)} writes prognostic stage ${cmp.written.stage}; the draft is ${p.stage}. The report is shown as written, for the board to look at.`}</span>
          </p>
        ) : null}
        <History_ written={view.prognostic_written ?? []} onOpen={onOpen} show={(w) => (w.stage ? `Prognostic stage ${w.stage}` : w.value)} none="No report writes a prognostic stage." />
      </div>
      {err ? <p role="alert" className="text-sm text-bad">{errorText(err)}</p> : null}
    </div>
  );
}

export function StagingCard({ caseId, view, loading, canRun, canConfirm, canPropose = false, consultantName = "the consultant", onOpen, onBook, onChanged }: {
  caseId: string; view: StagingView | null | undefined; loading: boolean; canRun: boolean; canConfirm: boolean;
  /** A resident on the team: the confirm buttons send the draft to the consultant for sign-off (night-v3 item 1.8). */
  canPropose?: boolean; consultantName?: string;
  onOpen: (t: SourceTarget) => void; onBook: (t: BookTarget) => void; onChanged: (v?: StagingView) => void;
}) {
  const qc = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const run = useMutation({ mutationFn: () => runStaging(caseId), onSuccess: (v) => onChanged(v) });
  const confirm = useMutation({ mutationFn: () => confirmStaging(caseId), onSuccess: (v) => onChanged(v) });
  const reject = useMutation({ mutationFn: () => rejectStaging(caseId, reason.trim()), onSuccess: (v) => { setRejecting(false); setReason(""); onChanged(v); } });
  const proposalsq = useQuery({ queryKey: ["proposals", caseId], queryFn: () => getProposals(caseId), enabled: canPropose && !canConfirm && !!view?.draft, retry: false });
  const pin = (which: Which) => ({ stage: (which === "prognostic" ? view?.prognostic?.stage : view?.draft?.stage) ?? "", signature: view?.draft?.signature ?? "" });
  const propose = useMutation({
    mutationFn: (which: Which) => { const p = pin(which); return proposeStaging(caseId, which, p.stage, p.signature); },
    onSuccess: async (_r, which) => {
      notify.success(`Sent to Dr ${consultantName} for sign-off`, `Confirm the ${which === "prognostic" ? "prognostic stage" : "draft stage"} ${pin(which).stage}`);
      await qc.invalidateQueries({ queryKey: ["proposals", caseId] });
    },
  });
  const signOff: SignOff = {
    canPropose: canPropose && !canConfirm, consultantName, sending: propose.isPending ? propose.variables ?? null : null,
    send: (which) => propose.mutate(which),
    waiting: (which) => {
      const p = pin(which);
      return (proposalsq.data?.proposals ?? []).some((x) => x.status === "pending" && x.action === "staging_confirm" && (x.payload?.which ?? "anatomic") === which
        && x.payload?.stage === p.stage && x.payload?.signature === p.signature);
    },
  };
  if (loading) return <section className="surface p-4"><SkeletonLines n={4} /></section>;
  if (!view) return null;
  const sw = view.switch;
  const d = view.draft;
  const book = view.book;
  const bookShort = book?.short || book?.title || "";
  const err = run.error || confirm.error || reject.error || propose.error;
  const staged = d?.status === "staged";
  const comps = d?.components ?? {};
  const figo = view.notation === "figo";
  const here = view.book_here !== false;
  const tnm = staged && !figo ? `${comps.T?.cat} ${comps.N?.cat} ${comps.M?.cat}` : "";
  return (
    <section className="surface overflow-hidden" data-testid="staging-card" aria-labelledby="h-stage">
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
        <Layers className="size-4 text-brand" aria-hidden />
        <h2 id="h-stage" className="text-[15px]">Stage</h2>
        {view.system ? <span className="text-xs text-muted-foreground">{view.system}</span> : null}
        <span className="flex-1" />
        {book && sw.on ? <BookChip book={book.id} page={view.groups_ref?.page ?? null} find={view.groups_ref?.find} label={bookShort} onOpen={onBook} here={here} /> : null}
      </header>
      {sw.preview ? <p className="flex items-center gap-2 border-b border-border bg-warn-soft px-4 py-1.5 text-xs font-medium text-warn" data-testid="staging-preview"><FlaskConical className="size-3.5" aria-hidden />{sw.label}</p> : null}

      <div className="space-y-4 px-4 py-4">
        {!sw.on ? (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">As written in the reports</p>
            <History_ written={view.written} onOpen={onOpen} />
          </div>
        ) : !d ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <p className="flex-1 text-sm text-body">Vaidyx walks the {view.system ?? "staging"} tables with this patient's reports, step by step: each step shows the report line and the book line. The board confirms the result.</p>
            {canRun ? <LoadingButton onClick={() => run.mutate()} loading={run.isPending} loadingText="Reading the reports" data-testid="run-staging"><Layers className="size-4" />Work out the draft stage</LoadingButton> : null}
          </div>
        ) : (
          <>
            {view.stale ? (
              <div className="flex flex-wrap items-center gap-2 rounded-md status-warn px-3 py-2 text-sm">
                <AlertTriangle className="size-4 shrink-0" aria-hidden /><span className="flex-1">The reports changed after this draft was worked out.</span>
                {canRun ? <LoadingButton size="sm" variant="outline" loading={run.isPending} onClick={() => run.mutate()}><RefreshCw className="size-4" />Work it out again</LoadingButton> : null}
              </div>
            ) : null}

            {/* the result, big */}
            <div className="flex flex-col gap-3 rounded-xl border border-border bg-gradient-to-br from-secondary/70 to-card p-4 sm:flex-row sm:items-center" data-testid="stage-result">
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{view.draft_label}</p>
                {staged ? (
                  <p className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="text-3xl font-bold tracking-tight text-foreground">Stage {d.stage}</span>
                    <span className="text-lg font-semibold text-muted-foreground">{tnm}</span>
                  </p>
                ) : (
                  <p className="mt-1 text-2xl font-bold tracking-tight text-foreground">Cannot stage yet</p>
                )}
                <p className="mt-1 text-xs text-muted-foreground">Worked out {fmtDateTime(d.at)} from the reports and {view.system}. Every step below shows its report line and its book line.</p>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                {d.confirmed ? <span className="inline-flex items-center gap-1.5 rounded-md status-ok px-2.5 py-1.5 text-sm font-medium"><CheckCircle2 className="size-4" aria-hidden />Confirmed by {d.confirmed.by_name || d.confirmed.by}</span> : null}
                {d.rejected ? <span className="inline-flex items-center gap-1.5 rounded-md status-bad px-2.5 py-1.5 text-sm font-medium" title={d.rejected.reason}><XCircle className="size-4" aria-hidden />Marked wrong by {d.rejected.by_name || d.rejected.by}: {d.rejected.reason}</span> : null}
                {staged && canConfirm && !d.confirmed && !view.stale ? <LoadingButton onClick={() => confirm.mutate()} loading={confirm.isPending} data-testid="confirm-stage"><Check className="size-4" />Confirm Stage {d.stage}</LoadingButton> : null}
                {staged && !canConfirm && signOff.canPropose && !d.confirmed && !view.stale ? <SignOffButton which="anatomic" stage={d.stage ?? ""} s={signOff} testId="propose-stage" /> : null}
                {staged && canConfirm && !rejecting && !d.rejected ? <Button variant="outline" onClick={() => setRejecting(true)}>This is wrong</Button> : null}
                {canRun && !view.stale ? <Button variant="ghost" size="sm" onClick={() => run.mutate()} disabled={run.isPending}><RefreshCw className={cn("size-4", run.isPending && "animate-spin")} />Again</Button> : null}
              </div>
            </div>
            {rejecting ? (
              <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); reject.mutate(); }}>
                <Input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="What is wrong? (recorded with your name)" className="h-9 max-w-md text-sm" maxLength={300} aria-label="What is wrong" />
                <LoadingButton size="sm" type="submit" loading={reject.isPending} disabled={reason.trim().length < 3}>Save</LoadingButton>
                <Button size="sm" variant="ghost" type="button" onClick={() => setRejecting(false)}>Cancel</Button>
              </form>
            ) : null}

            {/* the walk: T, N, M */}
            <ol className="divide-y divide-border">
              {(["T", "N", "M"] as const).map((p) => {
                const c = comps[p];
                if (c && book) return <Step key={p} testId={`stage-step-${p}`} word={(figo ? FIGO_WORD : PART_WORD)[p]} cat={c.cat} c={c} book={book.id} bookShort={bookShort} onOpen={onOpen} onBook={onBook} here={here} />;
                const miss = d.missing.find((m) => m.startsWith(`${p}:`));
                return (
                  <li key={p} className="grid gap-3 py-3 md:grid-cols-[5.5rem_minmax(0,1fr)]" data-testid={`stage-step-${p}`}>
                    <div><p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{(figo ? FIGO_WORD : PART_WORD)[p]}</p><p className="mt-0.5 text-2xl font-bold text-muted-foreground">?</p></div>
                    <div className="rounded-md border border-dashed border-warn/50 bg-warn-soft/60 p-2.5">
                      <p className="text-sm font-medium text-warn">Cannot stage: {miss ? miss.replace(/^[TNM]:\s*/, "") : "not stated in a report"}</p>
                      {canConfirm && view.criteria ? <div className="mt-1.5"><FillPart part={p} caseId={caseId} options={view.criteria[p]} onDone={(v) => onChanged(v)} /></div> : null}
                    </div>
                  </li>
                );
              })}
            </ol>

            {/* the stage table row */}
            {staged && book && d.row ? (
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Stage table</span>
                <span className="font-medium text-foreground">{figo ? `local ${comps.T?.cat}, nodes ${comps.N?.cat}, distant ${comps.M?.cat}` : `${comps.T?.cat} ${comps.N?.cat.replace(/^c/, "")} ${comps.M?.cat.replace(/^c/, "")}`}</span>
                <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
                <span className="font-semibold text-foreground">Stage {d.stage}</span>
                <span className="flex-1" />
                <BookChip book={book.id} page={view.groups_ref?.page ?? null} find={d.row.find || view.groups_ref?.find} label={bookShort} onOpen={onBook} here={here} />
              </div>
            ) : null}
            {view.groups_note ? <p className="text-xs text-muted-foreground">{view.groups_note}</p> : null}

            {/* the breast prognostic stage group, under the anatomic one */}
            {view.prognostic && book ? (
              <Prognostic caseId={caseId} view={view} p={view.prognostic} book={book.id} bookShort={bookShort} here={here} canConfirm={canConfirm} signOff={signOff} onOpen={onOpen} onBook={onBook} onChanged={onChanged} />
            ) : null}
          </>
        )}

        {/* the stage the reports wrote, and its history */}
        {sw.on ? (
          <div className="space-y-2 border-t border-border pt-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"><History className="size-3.5" aria-hidden />As written in the reports, over time</p>
            {view.comparison ? (
              <p className={cn("rounded-md px-3 py-1.5 text-sm", view.comparison.result === "differs" ? "status-warn" : view.comparison.result === "matches" ? "status-ok" : "bg-muted text-muted-foreground")} data-testid="stage-compare">
                {view.comparison.result === "matches" ? `The draft matches what ${niceTitle(view.comparison.written.doc_title)} writes (${view.comparison.written.value}).`
                  : view.comparison.result === "differs" ? `${niceTitle(view.comparison.written.doc_title)} writes ${view.comparison.written.value}. ${view.comparison.differences.join("; ")}.`
                  : `${niceTitle(view.comparison.written.doc_title)} writes ${view.comparison.written.value}.`}
              </p>
            ) : null}
            <History_ written={view.prognostic_ref ? view.written.filter((w) => w.kind !== "prognostic") : view.written} onOpen={onOpen} />
          </div>
        ) : null}
        {err ? <p role="alert" className="text-sm text-bad">{errorText(err)}</p> : null}
      </div>
    </section>
  );
}
