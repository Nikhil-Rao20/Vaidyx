// The Case summary (night-v3 3.4, owner decision D3): after the first board decision it is the main summary of the Case File. Five
// sections (presentation and diagnosis, stage, every board round, treatment and follow-up since the board, current status and open
// actions); every sentence carries its chips: a record line opens the report, a board field opens Board decisions, an action, the stage
// confirmation and a member's card show their quote. Sentences written by code carry no AI mark and are not editable; the owner's
// consultant edits a model sentence (shown "edited by Dr X on DD/MM/YYYY"), reviews or flags the version. Earlier versions open
// read-only through the version picker. Nothing here suggests a decision: the sentences quote the records and the board record.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCheck, Flag, Pencil, RefreshCw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { drName } from "@/lib/format";
import { cn } from "@/lib/utils";
import { buildCaseSummary, editCaseSentence, getCase, getCaseSummary, reviewCaseSummary } from "../api";
import type { CaseDocument, CaseFile } from "../types";
import type { CaseSentence, CaseSummarySection, CaseSummaryView } from "../steps/types";
import { Cites } from "./SummaryColumn";
import type { SlotHandlers } from "./SlotLine";
import { LoadingButton, SkeletonLines, StatusChip, errorText, fmtDate, fmtDateTime, indianDates, modelLabel, useAnnounce } from "./common";

const MAX_EDIT = 1000;
const count = (v: unknown) => (typeof v === "number" ? v : Array.isArray(v) ? v.length : 0);
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const modelWords = (line?: string) => modelLabel(String(line ?? "").replace(/^Written by\s+/i, "")) || "the reasoner model";

/** The label chip: reviewed, flagged, out of date, being written, or an AI draft not reviewed. */
export function CaseSummaryLabel({ v, current = true }: { v: Pick<CaseSummaryView, "status" | "review" | "stale_reason">; current?: boolean }) {
  const r = v.review;
  if (r?.status === "reviewed" && (v.status === "reviewed" || !current)) return <StatusChip kind="ok" icon={CheckCheck}>Reviewed by {drName(r.by_name || r.by)}</StatusChip>;
  if (current && v.status === "stale") return <StatusChip kind="warn" className="whitespace-normal">Out of date{v.stale_reason ? `: ${v.stale_reason}` : ""}</StatusChip>;
  if (current && v.status === "building") return <StatusChip kind="info">Being written</StatusChip>;
  if (r?.status === "flagged") return <StatusChip kind="bad" icon={Flag}>Flagged for correction by {drName(r.by_name || r.by)}</StatusChip>;
  return <StatusChip kind="review" icon={Bot}>AI draft, not reviewed</StatusChip>;
}

/** A sentence the owner's consultant may change: written by the model, in the current version. */
const editable = (s: CaseSentence, sec: CaseSummarySection) => sec.built_by === "model" && !s.code && !s.fixed && !s.from_fields;

function Sentence({ s, sec, docs, h, onBoard, canEdit, onEdit }: {
  s: CaseSentence; sec: CaseSummarySection; docs?: CaseDocument[]; h: Pick<SlotHandlers, "openSource">; onBoard?: () => void; canEdit: boolean;
  onEdit: (text: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(s.text);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const model = !s.code && !s.fixed && !s.from_fields && sec.built_by === "model";
  const e = s.edited;
  const sug = typeof e?.suggested === "string" ? { text: e.suggested } : e?.suggested && typeof e.suggested === "object" && e.suggested.text ? e.suggested : null;
  const tooLong = text.trim().length > MAX_EDIT;
  const save = async () => {
    const t = text.trim();
    if (!t || tooLong) { setErr(`Write the sentence (1 to ${MAX_EDIT} characters).`); return; }
    setBusy(true); setErr(null);
    try { await onEdit(t); setEditing(false); } catch (x) { setErr(errorText(x)); } finally { setBusy(false); }
  };
  if (editing) {
    const id = `cs-edit-${s.id}`;
    return (
      <span className="my-1 block rounded-md border border-border bg-muted/40 p-2" data-testid="cs-editing">
        <label htmlFor={id} className="text-xs font-medium text-foreground">The sentence, in your words</label>
        <Textarea id={id} value={text} onChange={(x) => setText(x.target.value)} className="mt-1 min-h-16 text-sm" maxLength={MAX_EDIT} aria-invalid={!!err || undefined} aria-describedby={`${id}-note`} />
        <span id={`${id}-note`} className="mt-0.5 block text-xs text-muted-foreground">The report lines stay cited; Vaidyx checks whether every number and name is still in them. Your name is shown with the edit.</span>
        {err ? <span role="alert" className="mt-1 block text-xs text-bad">{err}</span> : null}
        <span className="mt-1.5 flex gap-2">
          <LoadingButton size="sm" loading={busy} onClick={() => void save()} data-testid="cs-edit-save">Save</LoadingButton>
          <Button size="sm" variant="outline" onClick={() => { setEditing(false); setText(s.text); setErr(null); }}>Cancel</Button>
        </span>
      </span>
    );
  }
  return (
    <span data-testid="cs-sentence" data-id={s.id} data-model={model || undefined}>
      {indianDates(s.text)}
      {model ? <Bot className="ml-1 inline size-3.5 align-[-2px] text-review" aria-label="Written by the AI model" /> : null}
      <Cites cites={s.citations} docs={docs} h={h} onBoard={onBoard} max={4} />
      {s.approximate ? <span className="ml-1 text-xs text-muted-foreground">(quote matched closely, not word for word)</span> : null}
      {canEdit && editable(s, sec) ? (
        <button type="button" onClick={() => { setText(s.text); setEditing(true); }} className="ml-1 inline-flex size-6 items-center justify-center rounded-md align-middle text-muted-foreground hover:bg-accent hover:text-foreground print:hidden" aria-label="Change this sentence" data-testid="cs-edit"><Pencil className="size-3.5" aria-hidden /></button>
      ) : null}
      {e ? (
        <span className="mb-1 mt-0.5 block text-xs text-muted-foreground" data-testid="cs-edited">
          edited by {drName(e.by_name || e.by)} on {fmtDate(e.at)}
          {e.checked === false ? <span className="text-warn">, not checked against the record</span> : null}
          {e.records_changed ? <span className="text-warn">, records changed after this edit</span> : null}
          {e.unmatched ? <span className="block" data-testid="cs-unmatched">kept from an earlier version; no current sentence matches</span> : null}
          {sug ? (
            <details className="mt-0.5" data-testid="cs-suggested">
              <summary className="cursor-pointer hover:text-foreground">Vaidyx wrote</summary>
              <span className="mt-0.5 block pl-3">Vaidyx wrote: {indianDates(sug.text)}<Cites cites={"citations" in sug ? sug.citations : undefined} docs={docs} h={h} onBoard={onBoard} max={3} /></span>
            </details>
          ) : null}
        </span>
      ) : " "}
    </span>
  );
}

function Section({ sec, docs, h, onBoard, canEdit, onEdit }: { sec: CaseSummarySection; docs?: CaseDocument[]; h: Pick<SlotHandlers, "openSource">; onBoard?: () => void; canEdit: boolean; onEdit: (sid: string, text: string) => Promise<void> }) {
  const one = (s: CaseSentence) => <Sentence key={`${s.id}:${s.text}`} s={s} sec={sec} docs={docs} h={h} onBoard={onBoard} canEdit={canEdit} onEdit={(t) => onEdit(s.id, t)} />;
  return (
    <section aria-labelledby={`cs-h-${sec.id}`} data-testid={`cs-section-${sec.id}`}>
      <h3 id={`cs-h-${sec.id}`} className="text-sm font-semibold text-foreground">{sec.title}</h3>
      {sec.blocks ? (
        <div className="mt-1 space-y-2">
          {sec.blocks.map((b) => (
            <ul key={`${b.record}-${b.version ?? 1}`} className="space-y-0.5 border-l-2 border-border pl-3" data-testid="cs-round">
              {b.sentences.map((s) => <li key={s.id}>{one(s)}</li>)}
            </ul>
          ))}
        </div>
      ) : <p className="mt-0.5 text-foreground">{(sec.sentences ?? []).map(one)}</p>}
    </section>
  );
}

/** The Case summary card of the Summary section. `onBoard` opens the Board decisions panel from a board chip. */
export function CaseSummaryCard({ caseId, view, docs, h, onBoard }: { caseId: string; view: CaseSummaryView; docs?: CaseDocument[]; h: Pick<SlotHandlers, "openSource">; onBoard?: () => void }) {
  const qc = useQueryClient();
  const [announce, liveNode] = useAnnounce();
  const [pick, setPick] = useState<number>(view.current);
  const [flagging, setFlagging] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<"" | "review" | "flag" | "build">("");
  const [err, setErr] = useState<string | null>(null);
  const shownN = view.versions.some((x) => x.n === pick) ? pick : view.current;
  const older = shownN !== view.current;
  const other = useQuery({ queryKey: ["case-summary", caseId, shownN], queryFn: () => getCaseSummary(caseId, shownN), enabled: older, staleTime: 60_000, retry: false });
  const shown: CaseSummaryView | null = older ? (other.data?.version ? { ...other.data.version, status: "ready", versions: view.versions, can: {} } as CaseSummaryView : null) : view;
  const refresh = async () => { await qc.invalidateQueries({ queryKey: ["steps", caseId] }); };
  const run = async (what: "review" | "flag" | "build", fn: () => Promise<unknown>, done: string) => {
    setBusy(what); setErr(null);
    try { await fn(); announce(done); await refresh(); } catch (x) { setErr(errorText(x)); } finally { setBusy(""); }
  };
  const edit = async (sid: string, text: string) => { await editCaseSentence(caseId, view.current, sid, text); announce("Sentence saved with your name."); await refresh(); };
  const removed = count(shown?.removed);
  const canEdit = !older && !!view.can.edit;
  const total = view.versions.length;

  return (
    <section className="surface overflow-hidden" aria-labelledby="cs-title" data-testid="case-summary-card" data-status={view.status} data-version={shownN}>
      {liveNode}
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
        <Sparkles className="size-4 text-brand" aria-hidden />
        <h2 id="cs-title" className="text-[15px]">Case summary</h2>
        {shown ? <CaseSummaryLabel v={shown} current={!older} /> : null}
        <span className="flex-1" />
        {total > 1 ? (
          <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground print:hidden">
            <span className="sr-only">Show version</span>
            <select value={shownN} onChange={(e) => setPick(Number(e.target.value))} className="h-8 rounded-md border border-input bg-card px-2 text-sm text-foreground" data-testid="cs-version">
              {[...view.versions].sort((a, b) => b.n - a.n).map((x) => <option key={x.n} value={x.n}>Version {x.n} of {total}{x.n === view.current ? " (current)" : ""}</option>)}
            </select>
          </label>
        ) : null}
      </header>
      <div className="space-y-3 px-4 py-3 text-[0.97rem] leading-relaxed">
        {view.status === "building" && !older ? <div className="space-y-2" aria-busy="true"><p className="text-xs text-muted-foreground">Being written: each sentence is kept only once its record line or board field is checked.</p><SkeletonLines n={4} /></div> : null}
        {older && other.isLoading ? <SkeletonLines n={5} /> : null}
        {older && other.isError ? <p role="alert" className="text-sm text-bad">{errorText(other.error)}</p> : null}
        {shown ? (
          <>
            <p className="text-xs text-muted-foreground" data-testid="cs-header-line">
              Version {shownN}{shown.built_at ? `, written ${fmtDateTime(shown.built_at)}` : ""} by {modelWords(shown.model_line)}{older ? ". An earlier version, read-only." : ""}
            </p>
            {older ? <p className="rounded-md status-info px-3 py-1.5 text-sm">You are reading version {shownN}. <button type="button" className="text-link underline underline-offset-2" onClick={() => setPick(view.current)}>Back to the current version</button></p> : null}
            <div className={cn("space-y-3", shown.review?.status !== "reviewed" && "border-l-2 border-review/50 pl-3")}>
              {shown.sections.map((sec) => <Section key={sec.id} sec={sec} docs={docs} h={h} onBoard={onBoard} canEdit={canEdit} onEdit={edit} />)}
            </div>
            {removed ? <p className="text-xs text-muted-foreground" data-testid="cs-removed">{plural(removed, "sentence", "sentences")} dropped because {removed === 1 ? "it" : "they"} could not be checked against the records.</p> : null}
            {shown.review?.comment ? <p className="text-xs text-muted-foreground">Review note: {shown.review.comment}</p> : null}
          </>
        ) : null}
        {err ? <p role="alert" className="text-sm text-bad">{err}</p> : null}
        {!older && (view.can.review || (view.can.build && view.status === "stale")) ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3 print:hidden" data-testid="cs-actions">
            {view.can.build && view.status === "stale" ? (
              <LoadingButton size="sm" variant="outline" loading={busy === "build"} disabled={!!busy} onClick={() => void run("build", () => buildCaseSummary(caseId), "The Case summary is written again.")} data-testid="cs-update"><RefreshCw className="size-4" />Update the Case summary</LoadingButton>
            ) : null}
            {view.can.review && view.status !== "reviewed" && view.status !== "building" ? (
              <LoadingButton size="sm" variant="secondary" loading={busy === "review"} disabled={!!busy} onClick={() => void run("review", () => reviewCaseSummary(caseId, view.current, "reviewed"), "Marked reviewed.")} data-testid="cs-review"><CheckCheck className="size-4" />Mark reviewed</LoadingButton>
            ) : null}
            {view.can.review && view.status !== "building" && !flagging ? <Button size="sm" variant="outline" onClick={() => setFlagging(true)} disabled={!!busy} data-testid="cs-flag"><Flag className="size-4" />Flag for correction</Button> : null}
            {view.status === "reviewed" ? <span className="text-xs text-muted-foreground">Reviewed{view.review?.at ? ` ${fmtDateTime(view.review.at)}` : ""}. A new version is written after the next board decision.</span> : null}
          </div>
        ) : null}
        {flagging ? (
          <div className="space-y-1.5 rounded-md border border-border bg-muted/40 p-2" data-testid="cs-flag-form">
            <label htmlFor="cs-flag-comment" className="text-xs font-medium text-foreground">What needs correcting (optional)</label>
            <Textarea id="cs-flag-comment" value={comment} onChange={(e) => setComment(e.target.value)} className="min-h-16 text-sm" maxLength={2000} />
            <div className="flex gap-2">
              <LoadingButton size="sm" loading={busy === "flag"} onClick={() => void run("flag", async () => { await reviewCaseSummary(caseId, view.current, "flagged", comment.trim()); setFlagging(false); setComment(""); }, "Flagged for correction.")} data-testid="cs-flag-send">Flag for correction</LoadingButton>
              <Button size="sm" variant="outline" onClick={() => { setFlagging(false); setComment(""); }}>Cancel</Button>
            </div>
          </div>
        ) : null}
        {!older && !view.can.review && view.status !== "reviewed" ? <p className="text-xs text-muted-foreground">The owning department's consultant reads it against the records and marks it reviewed.</p> : null}
      </div>
    </section>
  );
}

/** The Case File as the page last read it (the ["case", id] query, no extra request), for the summary line where only the steps are passed. */
export function useCaseFileCache(caseId: string): CaseFile | undefined {
  return useQuery<CaseFile>({ queryKey: ["case", caseId], queryFn: ({ signal }) => getCase(caseId, signal), enabled: false, staleTime: Infinity }).data;
}

/** The Overview's Case summary card: the summary line, the latest round's outcome and decision lines and the first two presentation
 *  sentences, each with its chips; "Open the Case summary" goes to the Summary section. */
export function CaseSummaryGlance({ view, h, onBoard, onOpen, line, docs }: { view: CaseSummaryView; h: Pick<SlotHandlers, "openSource">; onBoard?: () => void; onOpen: () => void; line?: string; docs?: CaseDocument[] }) {
  const rounds = view.sections.find((s) => s.id === "rounds");
  const last = rounds?.blocks?.length ? rounds.blocks[rounds.blocks.length - 1] : null;
  const decided = (last?.sentences ?? []).filter((s) => /-(outcome|decision_text)$/.test(s.id));
  const pres = (view.sections.find((s) => s.id === "presentation")?.sentences ?? []).filter((s) => !s.fixed).slice(0, 2);
  const row = (s: CaseSentence) => (
    <span key={s.id} data-testid="cs-sentence" data-id={s.id}>
      {indianDates(s.text)}
      {!s.code && !s.fixed && !s.from_fields ? <Bot className="ml-1 inline size-3.5 align-[-2px] text-review" aria-label="Written by the AI model" /> : null}
      <Cites cites={s.citations} docs={docs} h={h} onBoard={onBoard} max={2} />{" "}
    </span>
  );
  return (
    <section className="surface overflow-hidden" aria-labelledby="ov-cs-title" data-testid="overview-case-summary">
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
        <Sparkles className="size-4 text-brand" aria-hidden />
        <h2 id="ov-cs-title" className="text-[15px]">Case summary</h2>
        <CaseSummaryLabel v={view} />
      </header>
      <div className="space-y-2 px-4 py-3 text-[0.97rem] leading-relaxed">
        {line ? <p className="font-semibold text-foreground" data-testid="overview-summary-line">{line}</p> : null}
        {decided.length ? <p className="text-foreground">{decided.map(row)}</p> : null}
        {pres.length ? <p className="text-foreground">{pres.map(row)}</p> : null}
        <Button size="sm" variant="outline" onClick={onOpen} data-testid="open-case-summary">Open the Case summary</Button>
      </div>
    </section>
  );
}
