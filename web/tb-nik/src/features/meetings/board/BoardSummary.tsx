// The Board view's Summary tab (meetings-v2 item 2.3, D3): the question for the board in large type; then the Case summary when the
// Case File has one ("Summary after the board", night-v3 3.4, D14) else the pre-board summary ("Summary before the board"); every sentence
// with its source chips (the "not signed" mark kept); the stage as written in the reports, and the Vaidyx draft stage only when a doctor
// confirmed it (docs/staging/DECISION.md). Read-only: no edit, review, write or send; a chip opens its report inside the Board view.
import { Bot, CheckCheck, History, Layers, MessageSquareQuote, Sparkles } from "lucide-react";
import { drName } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CaseSummaryLabel } from "@/features/casefile/components/CaseSummaryCard";
import { Cites, ProseBlock } from "@/features/casefile/components/SummaryColumn";
import type { SlotHandlers } from "@/features/casefile/components/SlotLine";
import type { SourceTarget } from "@/features/casefile/components/SourceViewer";
import { NotSigned, StatusChip, finalWordOf, fmtDate, fmtDateTime, indianDates, modelLabel, niceTitle } from "@/features/casefile/components/common";
import type { CaseDocument } from "@/features/casefile/types";
import type { CaseSentence, CaseSummarySection, CaseSummaryView, Steps } from "@/features/casefile/steps/types";
import { SourceChip } from "@/features/casefile/steps/Value";
import type { StagingView, Written } from "@/features/casefile/staging/api";
import { Panel } from "./parts";

type Open = (t: SourceTarget) => void;

/** Written by the model and not since rewritten by a doctor: the sentence carries the AI mark (as the Case summary card marks it). */
const modelMark = (s: CaseSentence, sec: CaseSummarySection) => sec.built_by === "model" && !s.code && !s.fixed && !s.from_fields && !s.edited;
const hasSentences = (v: CaseSummaryView | null | undefined) =>
  !!v && (v.sections ?? []).some((s) => (s.sentences ?? []).length || (s.blocks ?? []).some((b) => b.sentences.length));
const modelWords = (v: CaseSummaryView) => modelLabel(String(v.model_line ?? "").replace(/^Written by\s+/i, "").replace(/\s*\(non-medical\)\s*$/i, "")) || "a model";

function Question({ steps }: { steps: Steps }) {
  const q = steps.question;
  const meta = [q.reason?.label, q.by ? `written by ${q.by}` : "", q.at ? fmtDate(q.at) : ""].filter(Boolean).join(" · ");
  return (
    <section className="surface px-4 py-4 @2xl:px-6 @2xl:py-5" aria-labelledby="bv-question" data-testid="board-question">
      <h2 id="bv-question" className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        <MessageSquareQuote className="size-5 text-brand" aria-hidden />Question for the board
      </h2>
      {q.text ? (
        <>
          <p className="mt-2 text-2xl font-semibold leading-snug text-foreground @3xl:text-3xl">{indianDates(q.text)}</p>
          {meta ? <p className="mt-2 text-xs text-muted-foreground">{meta}</p> : null}
        </>
      ) : <p className="mt-2 text-lg text-muted-foreground">No question was written for the board.</p>}
    </section>
  );
}

function CaseSentenceLine({ s, sec, docs, open }: { s: CaseSentence; sec: CaseSummarySection; docs?: CaseDocument[]; open: Open }) {
  return (
    <span data-testid="board-cs-sentence" data-id={s.id}>
      {indianDates(s.text)}
      {modelMark(s, sec) ? <Bot className="ml-1 inline size-4 align-[-2px] text-review" aria-label="Written by the AI model" /> : null}
      <Cites cites={s.citations} docs={docs} h={{ openSource: open }} max={4} />
      {s.approximate ? <span className="ml-1 text-xs text-muted-foreground">(quote matched closely, not word for word)</span> : null}
      {s.edited ? <span className="ml-1 text-xs text-muted-foreground">(edited by {drName(s.edited.by_name || s.edited.by)} on {fmtDate(s.edited.at)})</span> : null}
      {" "}
    </span>
  );
}

/** The Case summary, read-only: its sections with every sentence's chips; no version picker, no edit, no review. */
function AfterBoard({ view, docs, open }: { view: CaseSummaryView; docs?: CaseDocument[]; open: Open }) {
  return (
    <Panel labelId="bv-after" testId="board-summary-after" title="Summary after the board" icon={<Sparkles className="size-5 text-brand" aria-hidden />}
      aside={<CaseSummaryLabel v={view} />}>
      <p className="text-xs text-muted-foreground">Version {view.current}{view.built_at ? `, written ${fmtDateTime(view.built_at)}` : ""} by {modelWords(view)}</p>
      <div className={cn("mt-3 space-y-4 text-base leading-relaxed", view.review?.status !== "reviewed" && "border-l-2 border-review/50 pl-3")}>
        {view.sections.map((sec) => (
          <section key={sec.id} aria-labelledby={`bv-cs-${sec.id}`}>
            <h3 id={`bv-cs-${sec.id}`} className="text-sm font-semibold text-foreground">{sec.title}</h3>
            {sec.blocks ? (
              <div className="mt-1 space-y-2">
                {sec.blocks.map((b) => (
                  <ul key={`${b.record}-${b.version ?? 1}`} className="space-y-1 border-l-2 border-border pl-3">
                    {b.sentences.map((s) => <li key={s.id}><CaseSentenceLine s={s} sec={sec} docs={docs} open={open} /></li>)}
                  </ul>
                ))}
              </div>
            ) : <p className="mt-1 text-foreground">{(sec.sentences ?? []).map((s) => <CaseSentenceLine key={s.id} s={s} sec={sec} docs={docs} open={open} />)}</p>}
          </section>
        ))}
      </div>
    </Panel>
  );
}

/** The pre-board summary, read-only: its sections and Points for review, each sentence with its chips. */
function BeforeBoard({ steps, docs, open }: { steps: Steps; docs?: CaseDocument[]; open: Open }) {
  const prose = steps.summary.prose;
  const shown = (prose.status === "ready" || prose.status === "stale") && prose.paragraphs.length > 0;
  const h = { openSource: open } as SlotHandlers;  // ProseBlock reads only openSource
  const label = !shown ? null
    : prose.reviewed ? <StatusChip kind="ok" icon={CheckCheck}>Read{prose.reviewed_by ? ` by ${prose.reviewed_by}` : ""}</StatusChip>
    : <StatusChip kind="review" icon={Bot}>AI draft, not reviewed</StatusChip>;
  return (
    <Panel labelId="bv-before" testId="board-summary-before" title="Summary before the board" icon={<Sparkles className="size-5 text-brand" aria-hidden />} aside={label}>
      {shown ? (
        <div className="space-y-4">
          {prose.status === "stale" ? <p className="rounded-md status-warn px-3 py-2 text-sm">The reports changed after this was written{prose.stale_reason ? `: ${prose.stale_reason}` : ""}.</p> : null}
          <div className={cn("space-y-3 text-base leading-relaxed", !prose.reviewed && "border-l-2 border-review/50 pl-3")} data-testid="board-prose">
            {prose.paragraphs.map((p, i) => <ProseBlock key={i} p={p} docs={docs} h={h} />)}
          </div>
          <p className="text-xs text-muted-foreground">{[prose.generated ? `Written ${fmtDateTime(prose.generated)}` : "", prose.model ? `by ${modelLabel(prose.model)}` : ""].filter(Boolean).join(" ")}</p>
          {(prose.points_for_review ?? []).length ? (
            <div className="rounded-md border border-border bg-muted/40 px-4 py-3" data-testid="board-points">
              <h3 className="text-sm font-semibold text-foreground">Points for review</h3>
              <ol className="mt-1 list-decimal space-y-1.5 pl-6 text-base">
                {prose.points_for_review!.map((pt, i) => <li key={i} className="text-foreground">{indianDates(pt.text)}<Cites cites={pt.citations} docs={docs} h={h} /></li>)}
              </ol>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="text-base text-muted-foreground">{prose.status === "pending" || prose.preparing ? "The summary is being written." : "No summary was written before the board."}</p>
      )}
    </Panel>
  );
}

const prefixWord = (x?: string) => (!x ? "" : x === "c" ? "clinical" : x === "p" ? "pathological" : "after treatment");

function WrittenRow({ w, docs, open }: { w: Written; docs?: CaseDocument[]; open: Open }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2" data-testid="board-stage-written">
      <span className="text-xl font-semibold text-foreground">{w.kind === "prognostic" && w.stage ? `Prognostic stage ${w.stage}` : w.value}</span>
      {w.prefix ? <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-semibold uppercase text-muted-foreground">{prefixWord(w.prefix)}</span> : null}
      <span className="text-xs text-muted-foreground">{w.date ? fmtDate(w.date) : "date not stated"}</span>
      <span className="inline-flex items-center">
        <SourceChip quote={{ doc_id: w.doc_id, doc_title: w.doc_title, page: w.page ?? 0, text: w.quote, date: null }} onOpen={open} />
        <NotSigned word={finalWordOf(docs, w.doc_id) ?? (w.final === false ? "not final" : null)} />
      </span>
    </li>
  );
}

/** The stage as the reports write it (the latest of each kind), and the Vaidyx draft stage only once a doctor confirmed it. A differing
 *  stage written in a report is shown and flagged, never overridden. */
function StageNow({ staging, docs, open }: { staging: StagingView | null | undefined; docs?: CaseDocument[]; open: Open }) {
  if (!staging) return null;
  const written = (staging.written ?? []).filter((w) => !w.superseded);
  const progWritten = (staging.prognostic_written ?? []).filter((w) => !w.superseded && !written.some((x) => x.doc_id === w.doc_id && x.quote === w.quote));
  const d = staging.draft;
  const confirmed = d && d.status === "staged" && d.stage && d.confirmed && !d.rejected ? d : null;
  const p = staging.prognostic;
  const progConfirmed = confirmed && p && p.status === "staged" && p.stage && p.confirmed && !p.rejected ? p : null;
  const cmp = staging.comparison;
  return (
    <Panel labelId="bv-stage" testId="board-stage-now" title="Stage" icon={<Layers className="size-5 text-brand" aria-hidden />}
      aside={staging.system ? <span className="text-xs text-muted-foreground">{staging.system}</span> : null}>
      <div className="space-y-3">
        <div>
          <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"><History className="size-4" aria-hidden />As written in the reports</h3>
          {written.length || progWritten.length ? (
            <ul className="divide-y divide-border">{[...written, ...progWritten].map((w, i) => <WrittenRow key={`${w.doc_id}-${i}`} w={w} docs={docs} open={open} />)}</ul>
          ) : <p className="py-1 text-base text-muted-foreground">No report writes a stage.</p>}
        </div>
        {confirmed ? (
          <div className="rounded-lg border border-border bg-secondary/50 px-4 py-3" data-testid="board-stage-confirmed">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Vaidyx draft stage, confirmed by {confirmed.confirmed!.by_name || confirmed.confirmed!.by} on {fmtDate(confirmed.confirmed!.at)}</p>
            <p className="mt-1 text-2xl font-bold tracking-tight text-foreground">Stage {confirmed.stage}</p>
            {progConfirmed ? <p className="mt-1 text-lg font-semibold text-foreground">Prognostic stage {progConfirmed.stage}<span className="ml-2 text-xs font-normal text-muted-foreground">confirmed by {progConfirmed.confirmed!.by_name || progConfirmed.confirmed!.by}</span></p> : null}
            {staging.stale ? <p className="mt-1 rounded-md status-warn px-2 py-1 text-sm">The reports changed after this draft was worked out.</p> : null}
            {cmp && cmp.result !== "matches" ? (
              <p className="mt-2 rounded-md status-warn px-2 py-1 text-sm" data-testid="board-stage-differs">
                {cmp.result === "differs" ? `${niceTitle(cmp.written.doc_title)} writes ${cmp.written.value}. ${cmp.differences.join("; ")}.` : `Compare by eye: ${niceTitle(cmp.written.doc_title)} writes ${cmp.written.value}.`}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

export function BoardSummary({ steps, docs, staging, open }: { steps: Steps; docs?: CaseDocument[]; staging: StagingView | null | undefined; open: Open }) {
  const cs = steps.summary.case_summary ?? null;
  return (
    <div className="space-y-4" data-testid="board-summary">
      <Question steps={steps} />
      {hasSentences(cs) ? <AfterBoard view={cs!} docs={docs} open={open} /> : <BeforeBoard steps={steps} docs={docs} open={open} />}
      <StageNow staging={staging} docs={docs} open={open} />
    </div>
  );
}
