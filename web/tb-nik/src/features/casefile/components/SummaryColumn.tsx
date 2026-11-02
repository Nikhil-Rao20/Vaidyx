// The left column, read the way a board reads a file: first the BOARD BRIEF (the question for the Tumour Board, what is still
// open with its actions in one place, the summary narrative with its points for review, the staging data as recorded), then
// the record sections folded, each with its counts, to open when a value is needed. Every line is a SlotLine.
import { useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Bot, CheckCheck, ChevronDown, ChevronsDownUp, ChevronsUpDown, CircleAlert, Hourglass, ListChecks, MessageSquareQuote, ShieldCheck, Sparkles } from "lucide-react";
import type { Citation, DocFinal, ProseSection, Slot, SlotSection, SlotsResponse } from "../types";
import { SlotLine, type SlotContext, type SlotHandlers } from "./SlotLine";
import { LoadingButton, NotYetState, SkeletonLines, StatusChip, NotSigned, docTitleOf, finalWordOf, fmtDate, fmtDateTime, indianDates, modelLabel } from "./common";
import type { CaseCitation } from "../steps/types";
import { fieldOf } from "@/features/meetings/components/DecisionForm";
import { cn } from "@/lib/utils";
import { consultantTitle } from "@/lib/format";

type Docs = Array<{ doc_id: string; filename: string; classification?: { title?: string }; final?: DocFinal }>;
const OPEN = new Set(["not_found", "waiting", "needs_confirmation"]);
const isQuestion = (s: Slot) => (s.fact_id ?? s.id.replace(/^fact:/, "")) === "clinical_question";

/** The field words of the board-record citations the decision record table does not hold (code-built lines of the Case summary). */
const BOARD_FIELD: Record<string, string> = { board_date: "Date", outcome_type: "Outcome", outcome: "Outcome", versions: "Correction", intent_as_recorded: "Treatment intent", divergent_opinions: "Divergent views", deferred_reason: "What is awaited" };
const ACTION_FIELD: Record<string, string> = { label: "task", department: "department", due: "due date", completed: "done", status: "status" };

/** One citation chip: a record line opens its report with the quote marked (as before); the Case summary (night-v3 3.4) also cites a
 *  board-record field ("Board DD/MM/YYYY, Decision", opens Board decisions when `onBoard` is given), an action, the stage confirmation
 *  or a member's card (no click: the quote shows on hover). */
export function CiteChip({ c, docs, h, onBoard }: { c: Citation | CaseCitation; docs?: Docs; h: Pick<SlotHandlers, "openSource">; onBoard?: () => void }) {
  const kind = "kind" in c ? c.kind : undefined;
  if (!kind) {
    const r = c as Citation;
    const title = docTitleOf(docs, r.doc_id, r.doc_title);
    return (
      <button type="button" className="quote-chip ml-1 align-middle active:scale-95" onClick={() => h.openSource({ docId: r.doc_id, page: r.page ?? 0, quote: r.quote, title })} title={`Open ${title} with the quote marked`}>
        {title}{typeof r.page === "number" ? ` p. ${r.page + 1}` : ""}<NotSigned word={finalWordOf(docs, r.doc_id)} />
      </button>
    );
  }
  const x = c as Exclude<CaseCitation, { kind?: undefined }>;
  const quote = x.quote ? `Quoted: ${x.quote}` : undefined;
  if (x.kind === "board") {
    const words = `Board${x.board_date ? ` ${fmtDate(x.board_date)}` : ""}, ${x.label || BOARD_FIELD[x.field] || fieldOf(x.field).label}`;
    return onBoard
      ? <button type="button" className="quote-chip ml-1 align-middle active:scale-95" onClick={onBoard} title={quote ? `${quote}. Opens Board decisions` : "Opens Board decisions"} data-cite="board">{words}</button>
      : <span className="quote-chip ml-1 align-middle" title={quote} data-cite="board">{words}</span>;
  }
  const words = x.kind === "action" ? `Action: ${x.label || ACTION_FIELD[x.field] || x.field.replace(/_/g, " ")}` : x.kind === "staging" ? "Stage confirmation" : x.kind === "card" ? "Member's card" : "Record";
  return <span className="quote-chip ml-1 align-middle" title={quote} data-cite={x.kind}>{words}</span>;
}

export function Cites({ cites, docs, h, onBoard, max = 3 }: { cites?: Array<Citation | CaseCitation>; docs?: Docs; h: Pick<SlotHandlers, "openSource">; onBoard?: () => void; max?: number }) {
  return <>{(cites ?? []).slice(0, max).map((c, j) => <CiteChip key={j} c={c} docs={docs} h={h} onBoard={onBoard} />)}</>;
}

export function ProseBlock({ p, docs, h }: { p: string | ProseSection; docs?: Docs; h: SlotHandlers }) {
  if (typeof p === "string") return <p className="text-foreground">{indianDates(p)}</p>;
  const sentences = p.sentences ?? [];
  if (!sentences.length) return null;
  return (
    <section>
      {p.title ? <h4 className="text-sm font-semibold text-foreground">{p.title}</h4> : null}
      <p className="text-foreground">
        {sentences.map((x, i) => (typeof x === "string" ? <span key={i}>{indianDates(x)} </span> : <span key={i}>{indianDates(x.text)}<Cites cites={x.citations} docs={docs} h={h} /> </span>))}
      </p>
    </section>
  );
}

function counts(slots: Slot[]) {
  let found = 0, open = 0, skipped = 0;
  for (const s of slots) {
    if (s.kind === "prose") continue;
    if (OPEN.has(s.status)) open += 1;
    else if (s.status === "not_needed") skipped += 1;
    else found += 1;
  }
  return { found, open, skipped };
}

/** A folded record section: the header carries the counts; the lines open with a short slide. */
function FoldedSection({ sec, open, onToggle, ctx, h }: { sec: SlotSection; open: boolean; onToggle: () => void; ctx: SlotContext; h: SlotHandlers }) {
  const reduce = useReducedMotion();
  const c = counts(sec.slots);
  return (
    <section id={`section-${sec.id}`} className="surface overflow-hidden print:shadow-none print:border-0" aria-labelledby={`h-${sec.id}`}>
      <button type="button" onClick={onToggle} aria-expanded={open} aria-controls={`body-${sec.id}`} className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/60 print:hidden">
        <motion.span animate={{ rotate: open ? 0 : -90 }} transition={{ duration: 0.18 }} className="grid size-6 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"><ChevronDown className="size-4" aria-hidden /></motion.span>
        <h2 id={`h-${sec.id}`} className="min-w-0 flex-1 truncate text-[15px]">{sec.label}</h2>
        <span className="flex shrink-0 items-center gap-1.5 text-xs">
          {sec.slots.length === 0 ? <StatusChip kind="muted">nothing asked for</StatusChip> : null}
          {c.open ? <StatusChip kind="warn">{c.open} open</StatusChip> : null}
          {c.found ? <span className="text-muted-foreground">{c.found} found</span> : null}
          {c.skipped ? <span className="text-muted-foreground">· {c.skipped} not needed</span> : null}
        </span>
      </button>
      <h2 className="hidden px-4 pt-3 text-[15px] print:block">{sec.label}</h2>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div id={`body-${sec.id}`} key="body" initial={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }} animate={reduce ? { opacity: 1 } : { height: "auto", opacity: 1 }} exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }} className="overflow-hidden print:!h-auto print:!opacity-100">
            <div className="border-t border-border px-4 pb-2">
              {sec.slots.length === 0 ? <p className="py-3 text-sm text-muted-foreground">Nothing is asked for here for this cancer and setting; what the records hold shows up here when it is found.</p> : null}
              <dl>{sec.slots.map((s) => <SlotLine key={s.id} slot={s} ctx={ctx} h={h} />)}</dl>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </section>
  );
}

export function SummaryColumn({ slots, derived, ctx, h, onReviewProse, onPrepareProse, proseBusy, canReview, docs }: {
  slots: SlotsResponse; derived: boolean; ctx: SlotContext; h: SlotHandlers;
  onReviewProse: () => Promise<void>; onPrepareProse: () => Promise<void>; proseBusy: boolean; canReview: boolean; docs?: Docs;
}) {
  const [reviewing, setReviewing] = useState(false);
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  const [showOptional, setShowOptional] = useState(true);
  const prose = slots.prose;
  const all = useMemo(() => slots.sections.flatMap((s) => s.slots), [slots]);
  const question = useMemo(() => all.find(isQuestion) ?? null, [all]);
  const staging = useMemo(() => slots.sections.find((s) => s.id === "staging") ?? null, [slots]);
  const sections = useMemo(() => slots.sections.filter((s) => s.id !== "question"), [slots]);
  const open = useMemo(() => all.filter((s) => OPEN.has(s.status) && !isQuestion(s) && s.kind !== "prose"), [all]);
  const required = open.filter((s) => s.required !== false);
  const optional = open.filter((s) => s.required === false);
  const groups = [
    { id: "confirm", title: "Needs your confirmation", icon: ShieldCheck, kind: "review" as const, items: required.filter((s) => s.status === "needs_confirmation") },
    { id: "waiting", title: "Waiting on a department", icon: Hourglass, kind: "warn" as const, items: required.filter((s) => s.status === "waiting") },
    { id: "missing", title: "Not in the file: ask, enter or mark not needed", icon: CircleAlert, kind: "bad" as const, items: required.filter((s) => s.status === "not_found") },
  ].filter((g) => g.items.length);
  const allOpen = sections.every((s) => opened[s.id]);
  const toggleAll = () => setOpened(Object.fromEntries(sections.map((s) => [s.id, !allOpen])));
  const proseShown = prose.status === "ready" || prose.status === "stale";

  return (
    <div className="space-y-3" data-testid="summary-column">
      {derived ? (
        <NotYetState what="The fill-in summary (slots)" fallback="Showing the same lines built from the current Pre-Authorization checklist and the verified values. Every action below still works." />
      ) : null}
      {slots.sections.length === 0 ? (
        <div className="surface p-4 text-sm text-muted-foreground">No summary lines yet: the protocol for this cancer has no records listed, or the records are still being read.</div>
      ) : null}

      {/* ---- the board brief ------------------------------------------------------------------------------------------ */}
      <section className="surface overflow-hidden print:shadow-none print:border-0" aria-labelledby="h-brief" data-testid="board-brief">
        <header className="flex items-center gap-2 border-b border-border bg-muted/40 px-4 py-2.5">
          <ListChecks className="size-4 text-brand" aria-hidden />
          <h2 id="h-brief" className="text-[15px]">Board brief</h2>
          <span className="flex-1" />
          {slots.board_ready ? <StatusChip kind="ok">ready for the board</StatusChip> : open.length === 0 && question?.status !== "not_found" ? <StatusChip kind="ok">nothing open</StatusChip> : <StatusChip kind="warn">{required.length + (question?.status === "not_found" ? 1 : 0)} open</StatusChip>}
        </header>

        {/* the question */}
        <div className="border-b border-border px-4 py-3" data-testid="brief-question">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"><MessageSquareQuote className="size-3.5" aria-hidden />Question for the Tumour Board</div>
          {question ? <dl className="[&>div]:border-b-0 [&>div]:py-1 [&_dt]:hidden sm:[&>div]:grid-cols-1">
            <SlotLine slot={question} ctx={ctx} h={h} />
          </dl> : <p className="text-sm text-muted-foreground">No question line for this cancer yet.</p>}
        </div>

        {/* what is open */}
        <div className="border-b border-border px-4 py-3" data-testid="brief-open">
          <div className="mb-1.5 flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">Still open</h3>
            {required.length ? <span className="text-xs text-muted-foreground">{required.length} required · each with its next step</span> : null}
          </div>
          {!required.length ? (
            <p className="flex items-center gap-2 rounded-md status-ok px-3 py-2 text-sm"><CheckCheck className="size-4 shrink-0" aria-hidden />Every required record is found, confirmed or marked not needed.</p>
          ) : (
            <div className="space-y-3">
              {groups.map((g) => (
                <div key={g.id}>
                  <p className={cn("mb-0.5 inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium", `status-${g.kind}`)}><g.icon className="size-3.5" aria-hidden />{g.title} · {g.items.length}</p>
                  <dl>{g.items.map((s) => <SlotLine key={`open-${s.id}`} slot={s} ctx={ctx} h={h} />)}</dl>
                </div>
              ))}
            </div>
          )}
          {optional.length ? (
            <div className={cn(required.length && "mt-3")}>
              <button type="button" onClick={() => setShowOptional((v) => !v)} aria-expanded={showOptional} className="mb-0.5 inline-flex items-center gap-1.5 rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground hover:text-foreground">
                <ChevronDown className={cn("size-3.5 transition-transform", !showOptional && "-rotate-90")} aria-hidden />
                Optional, not in the file · {optional.length}
                {!showOptional ? <span className="font-normal">: {optional.slice(0, 4).map((s) => s.label).join(", ")}{optional.length > 4 ? ", …" : ""}</span> : null}
              </button>
              {showOptional ? <dl>{optional.map((s) => <SlotLine key={`opt-${s.id}`} slot={s} ctx={ctx} h={h} />)}</dl> : null}
            </div>
          ) : null}
        </div>

        {/* the summary */}
        <div className="border-b border-border px-4 py-3" data-testid="prose-section">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold text-foreground"><Sparkles className="size-4 text-brand" aria-hidden />Summary</h3>
            {prose.status === "ready" && !prose.reviewed ? <StatusChip kind="review" icon={Bot}>AI draft, not reviewed</StatusChip> : null}
            {prose.status === "ready" && prose.reviewed ? <StatusChip kind="ok" icon={CheckCheck}>reviewed{prose.reviewed_by ? ` by ${prose.reviewed_by}` : ""}</StatusChip> : null}
            {prose.status === "stale" ? <StatusChip kind="warn">records changed since this draft</StatusChip> : null}
            {prose.status === "pending" ? <StatusChip kind="info">preparing</StatusChip> : null}
            <span className="flex-1" />
            {proseShown && !prose.reviewed && canReview && !ctx.resident ? (
              <LoadingButton size="sm" variant="secondary" loading={reviewing} onClick={async () => { setReviewing(true); try { await onReviewProse(); } finally { setReviewing(false); } }} className="print:hidden" data-testid="mark-reviewed">
                <CheckCheck className="size-4" />Mark reviewed
              </LoadingButton>
            ) : null}
            {(prose.status === "stale" || prose.status === "none") && canReview && !ctx.resident ? (
              <LoadingButton size="sm" variant="outline" loading={proseBusy} onClick={onPrepareProse} className="print:hidden" title="Writes the summary from the verified values only; every sentence keeps its quote">
                {prose.status === "stale" ? "Prepare again" : "Prepare the summary"}
              </LoadingButton>
            ) : null}
          </div>
          {prose.status === "none" && !proseBusy ? (
            <p className="text-sm text-muted-foreground">Written at the ready mark from the verified lines of the records. A line becomes a sentence only after its quote is checked.</p>
          ) : null}
          {prose.status === "pending" || proseBusy ? (
            <div className="space-y-3" aria-busy="true" aria-label="Summary filling in">
              <p className="text-xs text-muted-foreground">Filling in: each line turns into a sentence once its quote is verified.</p>
              <SkeletonLines n={4} />
            </div>
          ) : null}
          {proseShown && prose.paragraphs.length ? (
            <div className={cn("space-y-3 text-[0.95rem] leading-relaxed", !prose.reviewed && "border-l-2 border-review/50 pl-3")} data-testid="prose-text">
              {prose.paragraphs.map((p, i) => <ProseBlock key={i} p={p} docs={docs} h={h} />)}
              {prose.stale_reason && prose.status === "stale" ? <p className="text-xs text-warn">{prose.stale_reason}</p> : null}
              <p className="text-xs text-muted-foreground">{[prose.generated ? `Written ${fmtDateTime(prose.generated)}` : "", prose.model ? `by ${modelLabel(prose.model)}` : "", prose.at ? `reviewed ${fmtDateTime(prose.at)}` : ""].filter(Boolean).join(", ")}</p>
            </div>
          ) : null}
          {proseShown && (prose.points_for_review ?? []).length ? (
            <div className="mt-3 rounded-md border border-border bg-muted/40 p-3">
              <h4 className="text-sm font-semibold text-foreground">Points for review</h4>
              <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm">{prose.points_for_review!.map((pt, i) => <li key={i} className="text-foreground">{indianDates(pt.text)}<Cites cites={pt.citations} docs={docs} h={h} /></li>)}</ol>
            </div>
          ) : null}
          {proseShown && !prose.reviewed && ctx.resident ? <p className="mt-2 text-xs text-muted-foreground">{consultantTitle(ctx.consultantName, true)} reads it against the records and marks it reviewed.</p> : null}
          {prose.status === "ready" && !prose.paragraphs.length ? <p className="text-sm text-muted-foreground">The summary came back empty: nothing could be written without a verified quote.</p> : null}
          {prose.status === "ready" && !prose.reviewed && !canReview ? <p className="mt-2 text-xs text-muted-foreground">Only a doctor of the owning department marks this reviewed.</p> : null}
          {prose.status === "ready" && !prose.reviewed && canReview && !ctx.resident ? <p className="mt-2 text-xs text-muted-foreground print:hidden">Read it against the records; every sentence keeps its quote. The export opens after review.</p> : null}
        </div>

        {/* staging as recorded */}
        {staging && staging.slots.some((s) => s.kind !== "prose") ? (
          <div className="px-4 py-3" data-testid="brief-staging">
            <h3 className="text-sm font-semibold text-foreground">Staging data as recorded</h3>
            {staging.slots.filter((s) => s.kind !== "prose").length ? (
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {staging.slots.filter((s) => s.kind !== "prose").map((s) => (
                  <li key={s.id} className={cn("inline-flex max-w-full items-baseline gap-1.5 rounded-md border px-2 py-1 text-sm", s.status === "found" || s.status === "entered" ? "border-border bg-card" : "border-dashed border-border-strong text-muted-foreground")}>
                    <span className="text-xs text-muted-foreground">{s.label}</span>
                    {s.status === "found" || s.status === "entered" ? (
                      <span className="truncate text-foreground">{s.value}{s.unit ? ` ${s.unit}` : ""}</span>
                    ) : <span className="text-xs">{s.status === "waiting" ? "waiting" : s.status === "not_needed" ? "not needed" : "not in the file"}</span>}
                    {s.quote ? <button type="button" className="quote-chip" onClick={() => h.openSource({ docId: s.quote!.doc_id, page: s.quote!.page ?? 0, quote: s.quote!.text || undefined, factId: s.quote!.fact_id ?? undefined, title: s.quote!.doc_title })} title="Open the source">{s.quote.doc_title}</button> : null}
                  </li>
                ))}
              </ul>
            ) : <p className="mt-1 text-sm text-muted-foreground">Nothing is asked for here for this cancer and setting; what the records hold shows up here when it is found.</p>}
            <p className="mt-1.5 text-xs text-muted-foreground">As recorded in the reports. Vaidyx never computes a stage.</p>
          </div>
        ) : null}
      </section>

      {/* ---- the records, folded ---------------------------------------------------------------------------------------- */}
      <div className="flex items-center gap-2 pt-1 print:hidden">
        <h2 className="text-[15px]">Records</h2>
        <span className="text-xs text-muted-foreground">every line, with its source</span>
        <span className="flex-1" />
        <button type="button" onClick={toggleAll} className="inline-flex items-center gap-1 text-xs text-link hover:underline">{allOpen ? <ChevronsDownUp className="size-3.5" aria-hidden /> : <ChevronsUpDown className="size-3.5" aria-hidden />}{allOpen ? "Fold all" : "Open all"}</button>
      </div>
      {sections.map((sec) => <FoldedSection key={sec.id} sec={sec} open={!!opened[sec.id]} onToggle={() => setOpened((o) => ({ ...o, [sec.id]: !o[sec.id] }))} ctx={ctx} h={h} />)}
    </div>
  );
}
