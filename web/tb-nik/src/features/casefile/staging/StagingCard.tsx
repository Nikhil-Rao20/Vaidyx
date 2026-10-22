// The Staging card (owner decision 22 Oct 2026, docs/staging/DECISION.md), at the top of the Overview. The doctor's walk through the
// staging book, done by Vaidyx and shown step by step: for T, N and M the report line on the left and the book line on the right (a click
// opens the book at that page with the line highlighted), then the row of the stage table. Labelled "Vaidyx draft stage, for the board to
// confirm"; a consultant confirms it or marks it wrong with a reason. A part no report states says "Cannot stage" and can be filled in by
// the doctor ("entered by Dr X, no report"). The stage the reports wrote, and its history, sit beside it; a difference is flagged.
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, BookOpen, Check, CheckCircle2, FlaskConical, History, Layers, PenLine, RefreshCw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { SourceTarget } from "../components/SourceViewer";
import { LoadingButton, SkeletonLines, errorText, fmtDate, fmtDateTime, niceTitle } from "../components/common";
import { SourceChip } from "../steps/Value";
import { confirmStaging, enterPart, rejectStaging, runStaging, type BookTarget, type Component, type StagingView, type Written } from "./api";

const PART_WORD: Record<"T" | "N" | "M", string> = { T: "Primary tumour", N: "Regional lymph nodes", M: "Distant metastasis" };

function BookChip({ book, page, find, label, onOpen }: { book: string; page: number; find?: string; label: string; onOpen: (t: BookTarget) => void }) {
  return (
    <button type="button" onClick={() => onOpen({ book, page, find, label })} className="quote-chip !border-brand/30 !bg-secondary !text-secondary-foreground hover:!border-brand" data-testid="book-chip">
      <BookOpen className="size-3 shrink-0" aria-hidden />{label}, p. {page}
    </button>
  );
}

function Step({ part, c, book, bookShort, onOpen, onBook }: { part: "T" | "N" | "M"; c: Component; book: string; bookShort: string; onOpen: (t: SourceTarget) => void; onBook: (t: BookTarget) => void }) {
  const q = c.quotes[0];
  return (
    <li className="grid gap-3 py-3 md:grid-cols-[5.5rem_minmax(0,1fr)_minmax(0,1fr)]" data-testid={`stage-step-${part}`}>
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{PART_WORD[part]}</p>
        <p className="mt-0.5 text-2xl font-bold tracking-tight text-foreground">{c.cat}</p>
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
      <div className="min-w-0 rounded-md border border-brand/25 bg-secondary/40 p-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">The book says</p>
        <p className="mt-1 text-sm text-foreground"><span className="font-semibold">{c.criterion.cat}:</span> {c.criterion.text}</p>
        <div className="mt-1.5"><BookChip book={book} page={c.criterion.page} find={c.criterion.find} label={bookShort} onOpen={onBook} /></div>
      </div>
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

function History_({ written, onOpen }: { written: Written[]; onOpen: (t: SourceTarget) => void }) {
  if (!written.length) return <p className="text-sm text-muted-foreground">No report writes a stage.</p>;
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2" data-testid="stage-history">
      {written.map((w, i) => (
        <li key={`${w.doc_id}-${i}`} className="flex items-center gap-2">
          {i ? <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden /> : null}
          <span className={cn("rounded-md border px-2 py-1 text-sm", w.superseded ? "border-dashed border-border text-muted-foreground line-through" : "border-border bg-card")}>
            <span className="text-xs text-muted-foreground">{w.date ? fmtDate(w.date) : "date not stated"} · </span>
            <span className="font-semibold text-foreground">{w.value}</span>
            {w.prefix ? <span className="ml-1 rounded bg-muted px-1 text-[10px] font-semibold uppercase text-muted-foreground">{w.prefix === "c" ? "clinical" : w.prefix === "p" ? "pathological" : "after treatment"}</span> : null}
          </span>
          <SourceChip quote={{ doc_id: w.doc_id, doc_title: w.doc_title, page: w.page ?? 0, text: w.quote, date: null }} onOpen={onOpen} />
        </li>
      ))}
    </ol>
  );
}

export function StagingCard({ caseId, view, loading, canRun, canConfirm, onOpen, onBook, onChanged }: {
  caseId: string; view: StagingView | null | undefined; loading: boolean; canRun: boolean; canConfirm: boolean;
  onOpen: (t: SourceTarget) => void; onBook: (t: BookTarget) => void; onChanged: (v?: StagingView) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const run = useMutation({ mutationFn: () => runStaging(caseId), onSuccess: (v) => onChanged(v) });
  const confirm = useMutation({ mutationFn: () => confirmStaging(caseId), onSuccess: (v) => onChanged(v) });
  const reject = useMutation({ mutationFn: () => rejectStaging(caseId, reason.trim()), onSuccess: (v) => { setRejecting(false); setReason(""); onChanged(v); } });
  if (loading) return <section className="surface p-4"><SkeletonLines n={4} /></section>;
  if (!view) return null;
  const sw = view.switch;
  const d = view.draft;
  const book = view.book;
  const bookShort = book?.short || book?.title || "";
  const err = run.error || confirm.error || reject.error;
  const staged = d?.status === "staged";
  const comps = d?.components ?? {};
  const tnm = staged ? `${comps.T?.cat} ${comps.N?.cat} ${comps.M?.cat}` : "";
  return (
    <section className="surface overflow-hidden" data-testid="staging-card" aria-labelledby="h-stage">
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
        <Layers className="size-4 text-brand" aria-hidden />
        <h2 id="h-stage" className="text-[15px]">Stage</h2>
        {view.system ? <span className="text-xs text-muted-foreground">{view.system}</span> : null}
        <span className="flex-1" />
        {book && sw.on ? <BookChip book={book.id} page={view.groups_ref?.page ?? 620} find={view.groups_ref?.find} label={bookShort} onOpen={onBook} /> : null}
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
                if (c && book) return <Step key={p} part={p} c={c} book={book.id} bookShort={bookShort} onOpen={onOpen} onBook={onBook} />;
                const miss = d.missing.find((m) => m.startsWith(`${p}:`));
                return (
                  <li key={p} className="grid gap-3 py-3 md:grid-cols-[5.5rem_minmax(0,1fr)]" data-testid={`stage-step-${p}`}>
                    <div><p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{PART_WORD[p]}</p><p className="mt-0.5 text-2xl font-bold text-muted-foreground">?</p></div>
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
                <span className="font-medium text-foreground">{comps.T?.group} {comps.N?.cat.replace(/^c/, "").replace(/[a-c]$/, "")} {comps.M?.group}</span>
                <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
                <span className="font-semibold text-foreground">Stage {d.stage}</span>
                <span className="flex-1" />
                <BookChip book={book.id} page={view.groups_ref?.page ?? 620} find={d.row.find || view.groups_ref?.find} label={bookShort} onOpen={onBook} />
              </div>
            ) : null}
            {view.groups_note ? <p className="text-xs text-muted-foreground">{view.groups_note}</p> : null}
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
            <History_ written={view.written} onOpen={onOpen} />
          </div>
        ) : null}
        {err ? <p role="alert" className="text-sm text-bad">{errorText(err)}</p> : null}
      </div>
    </section>
  );
}
