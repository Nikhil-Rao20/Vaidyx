// The left column: the summary that is the checklist. Sections in board order, each line a SlotLine; then the AI
// narrative, which is skeleton lines until the ready mark and "AI draft, not reviewed" until a doctor reviews it.
import { useState } from "react";
import { Bot, CheckCheck, Sparkles } from "lucide-react";
import type { Citation, ProseSection, Slot, SlotsResponse } from "../types";
import { SlotLine, type SlotContext, type SlotHandlers } from "./SlotLine";
import { LoadingButton, NotYetState, SkeletonLines, StatusChip, docTitleOf, fmtDateTime, indianDates, modelLabel } from "./common";

type Docs = Array<{ doc_id: string; filename: string; classification?: { title?: string } }>;

function Cites({ cites, docs, h }: { cites?: Citation[]; docs?: Docs; h: SlotHandlers }) {
  return (
    <>
      {(cites ?? []).slice(0, 3).map((c, j) => {
        const title = docTitleOf(docs, c.doc_id, c.doc_title);
        return (
          <button key={j} type="button" className="quote-chip ml-1 align-middle hover:brightness-95 active:scale-95 transition" onClick={() => h.openSource({ docId: c.doc_id, page: c.page ?? 0, quote: c.quote, title })} title={`Open ${title} with the quote marked`}>
            {title}{typeof c.page === "number" ? ` p. ${c.page + 1}` : ""}
          </button>
        );
      })}
    </>
  );
}

function ProseBlock({ p, docs, h }: { p: string | ProseSection; docs?: Docs; h: SlotHandlers }) {
  if (typeof p === "string") return <p className="text-foreground">{indianDates(p)}</p>;
  const sentences = p.sentences ?? [];
  if (!sentences.length) return null;
  return (
    <section>
      {p.title ? <h3 className="text-sm font-semibold text-foreground">{p.title}</h3> : null}
      <p className="text-foreground">
        {sentences.map((x, i) => (typeof x === "string" ? <span key={i}>{indianDates(x)} </span> : <span key={i}>{indianDates(x.text)}<Cites cites={x.citations} docs={docs} h={h} /> </span>))}
      </p>
    </section>
  );
}
import { cn } from "@/lib/utils";

function openCount(slots: Slot[]): number {
  return slots.filter((s) => s.status === "not_found" || s.status === "waiting" || s.status === "needs_confirmation").length;
}

export function SummaryColumn({ slots, derived, ctx, h, onReviewProse, onPrepareProse, proseBusy, canReview, docs }: {
  slots: SlotsResponse; derived: boolean; ctx: SlotContext; h: SlotHandlers;
  onReviewProse: () => Promise<void>; onPrepareProse: () => Promise<void>; proseBusy: boolean; canReview: boolean; docs?: Docs;
}) {
  const [reviewing, setReviewing] = useState(false);
  const prose = slots.prose;
  return (
    <div className="space-y-4" data-testid="summary-column">
      {derived ? (
        <NotYetState what="The fill-in summary (slots)" fallback="Showing the same lines built from the current Pre-Authorization checklist and the verified values. Every action below still works." />
      ) : null}
      {slots.sections.length === 0 ? (
        <div className="surface p-4 text-sm text-muted-foreground">No summary lines yet: the protocol for this cancer has no records listed, or the records are still being read.</div>
      ) : null}
      {slots.sections.map((sec) => {
        const open = openCount(sec.slots);
        return (
          <section key={sec.id} id={`section-${sec.id}`} className="surface p-4 print:shadow-none print:border-0 print:p-0" aria-labelledby={`h-${sec.id}`}>
            <header className="flex items-center gap-2 mb-1">
              <h2 id={`h-${sec.id}`} className="text-base">{sec.label}</h2>
              {sec.slots.length === 0 ? <StatusChip kind="muted" className="print:hidden">no lines</StatusChip> : open > 0 ? <StatusChip kind="warn" className="print:hidden">{open} open</StatusChip> : <StatusChip kind="ok" className="print:hidden">complete</StatusChip>}
            </header>
            {sec.slots.length === 0 ? <p className="text-sm text-muted-foreground">Nothing is asked for here for this cancer and setting; what the records hold shows up here when it is found.</p> : null}
            <dl>
              {sec.slots.map((s) => <SlotLine key={s.id} slot={s} ctx={ctx} h={h} />)}
            </dl>
          </section>
        );
      })}

      <section className="surface p-4 print:shadow-none print:border-0 print:p-0" aria-labelledby="h-prose" data-testid="prose-section">
        <header className="flex flex-wrap items-center gap-2 mb-2">
          <h2 id="h-prose" className="text-base inline-flex items-center gap-1.5"><Sparkles className="size-4 text-brand" aria-hidden />Case File narrative</h2>
          {prose.status === "ready" && !prose.reviewed ? <StatusChip kind="review" icon={Bot}>AI draft, not reviewed</StatusChip> : null}
          {prose.status === "ready" && prose.reviewed ? <StatusChip kind="ok" icon={CheckCheck}>reviewed{prose.reviewed_by ? ` by ${prose.reviewed_by}` : ""}</StatusChip> : null}
          {prose.status === "stale" ? <StatusChip kind="warn">records changed since this draft</StatusChip> : null}
          {prose.status === "pending" ? <StatusChip kind="info">preparing</StatusChip> : null}
          <span className="flex-1" />
          {(prose.status === "ready" || prose.status === "stale") && !prose.reviewed && canReview && !ctx.resident ? (
            <LoadingButton size="sm" variant="secondary" loading={reviewing} onClick={async () => { setReviewing(true); try { await onReviewProse(); } finally { setReviewing(false); } }} className="print:hidden" data-testid="mark-reviewed">
              <CheckCheck className="size-4" />Mark reviewed
            </LoadingButton>
          ) : null}
          {(prose.status === "stale" || prose.status === "none") && canReview && !ctx.resident ? (
            <LoadingButton size="sm" variant="outline" loading={proseBusy} onClick={onPrepareProse} className="print:hidden" title="Writes the narrative from the verified values only; every sentence keeps its quote">
              {prose.status === "stale" ? "Prepare again" : "Prepare the narrative"}
            </LoadingButton>
          ) : null}
        </header>
        {prose.status === "none" && !proseBusy ? (
          <p className="text-sm text-muted-foreground">Written at the ready mark from the verified lines above. Grey lines become sentences only after their quote is checked.</p>
        ) : null}
        {prose.status === "pending" || proseBusy ? (
          <div className="space-y-3" aria-busy="true" aria-label="Preview filling in">
            <p className="text-xs text-muted-foreground">Preview filling in: each line turns into a sentence once its quote is verified.</p>
            <SkeletonLines n={5} />
          </div>
        ) : null}
        {(prose.status === "ready" || prose.status === "stale") && prose.paragraphs.length ? (
          <div className={cn("space-y-3 text-[0.95rem] leading-relaxed", !prose.reviewed && "border-l-2 border-review/50 pl-3")} data-testid="prose-text">
            {prose.paragraphs.map((p, i) => <ProseBlock key={i} p={p} docs={docs} h={h} />)}
            {prose.stale_reason && prose.status === "stale" ? <p className="text-xs text-warn">{prose.stale_reason}</p> : null}
            <p className="text-xs text-muted-foreground">{[prose.generated ? `Written ${fmtDateTime(prose.generated)}` : "", prose.model ? `by ${modelLabel(prose.model)}` : "", prose.at ? `reviewed ${fmtDateTime(prose.at)}` : ""].filter(Boolean).join(", ")}</p>
          </div>
        ) : null}
        {(prose.status === "ready" || prose.status === "stale") && (prose.points_for_review ?? []).length ? (
          <div className="mt-3">
            <h3 className="text-sm font-semibold text-foreground">Points for review</h3>
            <ol className="mt-1 list-decimal pl-5 space-y-1 text-sm">{prose.points_for_review!.map((pt, i) => <li key={i} className="text-foreground">{indianDates(pt.text)}<Cites cites={pt.citations} docs={docs} h={h} /></li>)}</ol>
          </div>
        ) : null}
        {(prose.status === "ready" || prose.status === "stale") && !prose.reviewed && ctx.resident ? <p className="text-xs text-muted-foreground mt-2">Dr {ctx.consultantName} reads it against the lines above and marks it reviewed.</p> : null}
        {prose.status === "ready" && !prose.paragraphs.length ? <p className="text-sm text-muted-foreground">The narrative came back empty: nothing could be written without a verified quote.</p> : null}
        {prose.status === "ready" && !prose.reviewed && !canReview ? <p className="text-xs text-muted-foreground mt-2">Only a doctor of the owning department marks this reviewed.</p> : null}
        {prose.status === "ready" && !prose.reviewed && canReview && !ctx.resident ? <p className="text-xs text-muted-foreground mt-2 print:hidden">Read it against the lines above; every sentence keeps its quote. The export opens after review.</p> : null}
      </section>
    </div>
  );
}
