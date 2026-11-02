// One value as the guided Case File shows it everywhere: the value with the report line it came from (one click opens the report at that
// line), or "entered by Dr X, no report", or a plain status in the owner's words (B9): Please check, Not found in the reports, Request
// sent to Pathology department, Not needed.
import { FileText, Hourglass, PenLine, ShieldQuestion } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SourceTarget } from "../components/SourceViewer";
import { NotSigned, fmtDate, niceTitle, screenNote } from "../components/common";
import type { StepRow } from "./types";

export function SourceChip({ quote, onOpen, className }: { quote: NonNullable<StepRow["quote"]>; onOpen: (t: SourceTarget) => void; className?: string }) {
  const title = niceTitle(quote.doc_title) || "report";
  const page = (quote.page ?? 0) + 1;
  return (
    <button type="button" className={cn("quote-chip max-w-full hover:brightness-95 active:scale-95", className)} data-testid="source-chip"
      onClick={() => onOpen({ docId: quote.doc_id, page: quote.page ?? 0, quote: quote.text || undefined, factId: quote.fact_id ?? undefined, title: quote.doc_title })}
      title={quote.text ? `"${quote.text}"\nOpen ${title}, page ${page}, at this line` : `Open ${title}`}>
      <FileText className="size-3 shrink-0" aria-hidden /><span className="truncate">{title}</span>{quote.date ? <span className="shrink-0">{fmtDate(quote.date)}</span> : null}
    </button>
  );
}

export function ValueCell({ row, onOpen, onCheck, dense }: { row: StepRow; onOpen: (t: SourceTarget) => void; onCheck?: () => void; dense?: boolean }) {
  const v = `${row.value}${row.unit ? ` ${row.unit}` : ""}`;
  if (row.status === "found") {
    return (
      <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-foreground">{v}</span>
        {row.quote?.doc_id ? <SourceChip quote={row.quote} onOpen={onOpen} /> : null}
        {row.corrected_by ? <span className="text-xs text-muted-foreground">corrected by {row.corrected_by}</span> : null}
      </span>
    );
  }
  if (row.status === "entered") {
    return (
      <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-foreground">{v}</span>
        <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-1.5 py-0.5 text-[11px] font-medium text-secondary-foreground"><PenLine className="size-3" aria-hidden />entered by {row.entered_by || "the treating doctor"}, no report</span>
      </span>
    );
  }
  if (row.status === "needs_confirmation") {
    return (
      <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
        {row.value ? <span className="text-foreground">{v}</span> : null}
        <button type="button" onClick={onCheck} disabled={!onCheck} className="inline-flex items-center gap-1 rounded-md status-warn px-1.5 py-0.5 text-[11px] font-semibold enabled:hover:brightness-95">
          <ShieldQuestion className="size-3" aria-hidden />Please check
        </button>
      </span>
    );
  }
  if (row.unsigned) {  // only in a report not final and signed: shown, marked; the board still needs the signed one (owner, 2 Nov 2026)
    const u = row.unsigned;
    return (
      <span className="flex min-w-0 flex-col gap-1">
        <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-foreground">{u.value}</span>
          {u.quote?.doc_id ? <SourceChip quote={u.quote} onOpen={onOpen} /> : null}
          <NotSigned word={u.word} />
        </span>
        {row.status === "waiting" ? <span className="inline-flex items-center gap-1 text-xs text-warn"><Hourglass className="size-3" aria-hidden />Request sent, waiting for the signed report</span> : null}
      </span>
    );
  }
  if (row.status === "waiting") {
    return <span className="inline-flex items-center gap-1 text-sm text-warn"><Hourglass className="size-3.5" aria-hidden />Request sent, waiting</span>;
  }
  if (row.status === "not_needed") return <span className="text-sm text-muted-foreground">Not needed</span>;
  return <span className={cn("text-muted-foreground", dense ? "text-xs" : "text-sm")}>{row.note && /pending/i.test(row.note) ? screenNote(row.note) : row.note && /not written/i.test(row.note) ? row.note : "Not found in the reports"}</span>;
}
