// Summary (B7): written before sending. "Write the summary" (15 to 35 s, from the checked values only; every sentence keeps its report
// line), read it, "I have read it", then "Send to the board". What the doctor typed is shown apart, "entered by Dr X, no report". The
// specialty briefs and similar published cases sit here too (B9).
import type { ReactNode } from "react";
import { CheckCheck, PenLine, RefreshCw, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { SlotHandlers } from "../components/SlotLine";
import { ProseBlock } from "../components/SummaryColumn";
import { LoadingButton, SkeletonLines, fmtDateTime, indianDates, modelLabel } from "../components/common";
import type { CaseDocument } from "../types";
import { Card } from "./Overview";
import type { Steps } from "./types";

export function SummaryStep({ steps, docs, h, canWrite, canRead, busy, reading, onWrite, onRead, onSend, resident, consultantName, briefs, published }: {
  steps: Steps; docs: CaseDocument[]; h: SlotHandlers; canWrite: boolean; canRead: boolean; busy: boolean; reading: boolean; resident: boolean; consultantName: string;
  onWrite: () => void; onRead: () => void; onSend: () => void; briefs: ReactNode; published: ReactNode;
}) {
  const prose = steps.summary.prose;
  const sent = steps.summary.sent;
  const shown = prose.status === "ready" || prose.status === "stale";
  const entered = [
    ...(steps.question.text ? [{ label: "Question for the board", value: steps.question.text, by: steps.question.by }] : []),
    ...steps.question.extras.filter((x) => x.status === "entered").map((x) => ({ label: x.label, value: x.value, by: x.entered_by })),
  ];
  return (
    <div className="space-y-4" data-testid="section-summary">
      <Card title="The board summary" icon={<Sparkles className="size-4 text-brand" aria-hidden />} testId="summary-card">
        <div className="space-y-3 py-2">
          {prose.status === "none" && !busy ? (
            <div className="space-y-2">
              <p className="text-sm text-body">Vaidyx writes the summary the board will read from the checked values only; every sentence keeps the report line it came from. It takes 15 to 35 seconds.</p>
              {steps.left ? <p className="text-sm text-warn">{steps.left} still open. You can write it now; it is written again when the open items are settled.</p> : null}
              {canWrite ? <LoadingButton onClick={onWrite} loading={busy} data-testid="write-summary"><Sparkles className="size-4" />Write the summary</LoadingButton> : <p className="text-sm text-muted-foreground">The treating team writes it.</p>}
            </div>
          ) : null}
          {prose.status === "pending" || busy || prose.preparing ? (
            <div className="space-y-2" aria-busy="true"><p className="text-xs text-muted-foreground">Being written: each line becomes a sentence once its report line is checked.</p><SkeletonLines n={5} /></div>
          ) : null}
          {prose.status === "stale" && !busy ? (
            <div className="flex flex-wrap items-center gap-2 rounded-md status-warn px-3 py-2 text-sm">
              <span className="flex-1">The reports changed after this was written{prose.stale_reason ? `: ${prose.stale_reason}` : ""}.</span>
              {canWrite ? <LoadingButton size="sm" variant="outline" loading={busy} onClick={onWrite}><RefreshCw className="size-4" />Write it again</LoadingButton> : null}
            </div>
          ) : null}
          {shown && prose.paragraphs.length && !busy ? (
            <div className="space-y-3 text-[0.97rem] leading-relaxed" data-testid="prose-text">
              {prose.paragraphs.map((p, i) => <ProseBlock key={i} p={p} docs={docs} h={h} />)}
              <p className="text-xs text-muted-foreground">{[prose.generated ? `Written ${fmtDateTime(prose.generated)}` : "", prose.model ? `by ${modelLabel(prose.model)}` : ""].filter(Boolean).join(" ")}</p>
            </div>
          ) : null}
          {shown && (prose.points_for_review ?? []).length && !busy ? (
            <div className="rounded-md border border-border bg-muted/40 p-3">
              <h3 className="text-sm font-semibold">Points for review</h3>
              <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm">{prose.points_for_review!.map((pt, i) => <li key={i}>{indianDates(pt.text)}</li>)}</ol>
            </div>
          ) : null}
          {shown && !busy ? (
            <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
              {prose.reviewed ? <span className="inline-flex items-center gap-1.5 text-sm text-ok"><CheckCheck className="size-4" aria-hidden />Read{prose.reviewed_by ? ` by ${prose.reviewed_by}` : ""}</span>
                : canRead ? <LoadingButton variant="outline" loading={reading} onClick={onRead} data-testid="read-summary"><CheckCheck className="size-4" />I have read it</LoadingButton>
                : <span className="text-sm text-muted-foreground">{resident ? `Dr ${consultantName} reads it and marks it read.` : "A doctor of the treating team reads it."}</span>}
              {!sent && prose.reviewed && canWrite ? <Button onClick={onSend} data-testid="summary-send"><Send className="size-4" />{resident ? `Send to Dr ${consultantName} for sign-off` : "Send to the board"}</Button> : null}
              {sent ? <span className="text-sm text-ok">Sent to the board{sent.at ? `, ${fmtDateTime(sent.at)}` : ""}</span> : null}
            </div>
          ) : null}
        </div>
      </Card>
      {entered.length ? (
        <Card title="Entered by the treating doctor, no report" icon={<PenLine className="size-4 text-muted-foreground" aria-hidden />} testId="summary-entered">
          <dl className="divide-y divide-border">
            {entered.map((e) => (
              <div key={e.label} className="grid gap-x-3 py-2 text-sm sm:grid-cols-[minmax(8rem,11rem)_1fr]">
                <dt className="text-muted-foreground">{e.label}</dt><dd className="text-foreground">{e.value}{e.by ? <span className="ml-2 text-xs text-muted-foreground">entered by {e.by}</span> : null}</dd>
              </div>
            ))}
          </dl>
        </Card>
      ) : null}
      <Card title="Specialty briefs" testId="summary-briefs"><div className="py-2">{briefs}</div></Card>
      <Card title="Similar published cases" testId="summary-published"><div className="py-2">{published}</div></Card>
    </div>
  );
}
