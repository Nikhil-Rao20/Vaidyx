// An agent's points from the records (night-v3 6.2, research/05 sections 6.1 and 11.1): the brief's points for review shown from the
// start of the case, each with its source chips (the document, its date as DD/MM/YYYY, the page; the verbatim quote as the chip's
// title), the count of the items the brief lists as not documented, and the words of the tile ("4 points from the records", "Reading
// the records", "No Radiology reports in this Case File"). A chip opens the record on the stage for the coordinator and the presenter;
// for anyone else it shows the quote. "Present your points" asks the agent to read its points to the room: the answer is built by
// code from the brief (no model call) and lands in the questions like any answer. The points are an AI draft until a doctor reviews
// the brief; the agent never decides or advises.
import { useState } from "react";
import { FileText, Megaphone } from "lucide-react";
import type { AgentCitation, AgentInfo } from "@/lib/live";
import { LoadingButton, fmtDate, indianDates, niceTitle } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { usePanelAction } from "../../components/People";
import { useCall } from "../context";
import type { CallCtx } from "../types";

/** The department's name of an agent ("Radiology"). */
function deptOf(a: Pick<AgentInfo, "label" | "department" | "department_name" | "role">): string {
  return a.department_name || a.department || a.label || a.role.replace(/_/g, " ");
}

type BriefPick = Pick<AgentInfo, "label" | "department" | "department_name" | "role" | "brief" | "points" | "points_count">;

/** The number of points: the brief's count, else the points sent. */
export function pointsCount(a: Pick<AgentInfo, "points" | "points_count">): number {
  return typeof a.points_count === "number" ? a.points_count : (a.points ?? []).length;
}

/** The tile's count line: "4 points from the records", "1 point from the records", "No points yet", "Reading the records" while the
 * brief is prepared, "No Radiology reports in this Case File" when there is nothing to read. */
export function pointsLine(a: BriefPick): string {
  const status = a.brief?.status;
  if (status === "preparing") return "Reading the records";
  if (status === "no_documents") return `No ${deptOf(a)} reports in this Case File`;
  const n = pointsCount(a);
  if (!n) return "No points yet";
  return `${n} point${n === 1 ? "" : "s"} from the records`;
}

/** The header of the points: "Points from the records, AI draft, not reviewed" until a doctor reviewed the brief, then "Reviewed by
 * <name>". */
export function pointsHeader(a: Pick<AgentInfo, "brief">): string {
  const b = a.brief;
  if (b?.reviewed_by) return `Reviewed by ${b.reviewed_by}`;
  if (b?.label && /^reviewed/i.test(b.label)) return "Reviewed";
  return "Points from the records, AI draft, not reviewed";
}

/** Why "Present your points" is not offered now, or null when it is: the brief is prepared, there is nothing to read, or no points. */
export function presentBlockedReason(a: BriefPick): string | null {
  const status = a.brief?.status;
  if (status === "preparing") return "The brief is still being prepared from the records.";
  if (status === "no_documents") return `No ${deptOf(a)} reports in this Case File.`;
  if (!pointsCount(a)) return status === "none" || status === "error" || !status ? "No brief has been prepared from the records yet." : "The brief lists no points for review.";
  return null;
}

/** "2 items not documented; see the Case File" (null for none). */
export function notDocumentedLine(n: number | undefined | null): string | null {
  if (!n || n < 1) return null;
  return `${n} item${n === 1 ? "" : "s"} not documented; see the Case File`;
}

/** The words of a source chip: "Histopathology report, 17/09/2026, p. 1" (pages are counted from 0 by the server). */
export function chipText(c: Pick<AgentCitation, "doc_title" | "date" | "page">): string {
  const parts = [niceTitle(c.doc_title) || "Record"];
  const d = fmtDate(c.date ?? null);
  if (d) parts.push(d);
  if (typeof c.page === "number") parts.push(`p. ${c.page + 1}`);
  return parts.join(", ");
}

/** True when this person may put a record on the stage: the coordinator, or the presenter of the Case File on the floor. */
export function mayOpenRecords(ctx: Pick<CallCtx, "canManage" | "me" | "state" | "variant">): boolean {
  if (ctx.variant === "room") return false;
  return ctx.canManage || (!!ctx.me && ctx.state.current?.presenter?.user === ctx.me);
}

/** One source chip. For the coordinator and the presenter it opens the record on the stage; for others it shows the quote. */
export function CitationChip({ c, onQuote }: { c: AgentCitation; onQuote?: () => void }) {
  const ctx = useCall();
  const text = chipText(c);
  const quote = c.quote ? `"${c.quote}"` : undefined;
  const open = mayOpenRecords(ctx) && !!c.doc_id;
  if (ctx.variant === "room") return <span className="quote-chip ml-1 align-middle" title={quote}><FileText className="size-3" aria-hidden />{text}</span>;
  const onClick = () => {
    if (open) {
      void ctx.actions.open("record", c.doc_id).catch(() => undefined);
      if (ctx.phone) ctx.setPanel(null);  // the sheet covers the stage on a phone
      return;
    }
    onQuote?.();
  };
  return (
    <button type="button" className="quote-chip ml-1 align-middle hover:brightness-95" title={quote} onClick={onClick} data-testid="point-chip"
      aria-label={open ? `${text}: open the record on the screen` : `${text}: show the quote`}>
      <FileText className="size-3" aria-hidden />{text}
    </button>
  );
}

/** A statement or a point with its chips; a chip that cannot open the record shows the quote under the text. */
export function CitedText({ text, citations, className }: { text: string; citations?: AgentCitation[]; className?: string }) {
  const [shown, setShown] = useState<number | null>(null);
  const cites = citations ?? [];
  const q = shown !== null ? cites[shown]?.quote : null;
  return (
    <div className={className}>
      <p className="text-sm text-foreground">
        {indianDates(text)}
        {cites.map((c, i) => <CitationChip key={i} c={c} onQuote={() => setShown(shown === i ? null : i)} />)}
      </p>
      {q ? <p className="mt-0.5 text-xs italic text-muted-foreground" data-testid="point-quote">"{q}"</p> : null}
    </div>
  );
}

/** The points of an agent's brief (at most five), with the header, the not documented count and "Present your points". */
export function AgentPoints({ agent }: { agent: AgentInfo }) {
  const ctx = useCall();
  const act = usePanelAction();
  const status = agent.brief?.status;
  const points = (agent.points ?? []).slice(0, 5);
  const blocked = presentBlockedReason(agent);
  const nd = notDocumentedLine(agent.not_documented_count);
  const more = pointsCount(agent) - points.length;
  const canPresent = ctx.variant !== "room" && ctx.inSession && !!ctx.cid;
  return (
    <section className="space-y-1.5" aria-label={`${deptOf(agent)}: points from the records`} data-testid="agent-points">
      {status === "preparing" ? (
        <p className="text-xs text-muted-foreground">Reading the records for {deptOf(agent)}</p>
      ) : status === "no_documents" ? (
        <p className="text-xs text-muted-foreground">No {deptOf(agent)} reports in this Case File</p>
      ) : points.length ? (
        <>
          <p className={cn("text-[11px] font-semibold", agent.brief?.reviewed_by ? "text-ok" : "text-review")} data-testid="points-header">{pointsHeader(agent)}</p>
          <ol className="space-y-1.5">
            {points.map((p, i) => <li key={i}><CitedText text={p.text} citations={p.citations} /></li>)}
          </ol>
          {more > 0 ? <p className="text-xs text-muted-foreground">{more} more in the Case File</p> : null}
        </>
      ) : <p className="text-xs text-muted-foreground">No points yet</p>}
      {nd ? <p className="text-xs text-muted-foreground" data-testid="points-not-documented">{nd}</p> : null}
      {canPresent ? (
        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          <LoadingButton size="sm" variant="outline" className={cn(ctx.phone && "min-h-11")} loading={act.pending === "present"} loadingText="Presenting"
            disabled={!!blocked || !!act.pending} title={blocked ?? undefined} aria-describedby={blocked ? `present-why-${agent.role}` : undefined}
            onClick={() => void act.run("present", () => ctx.actions.presentPoints(agent.role))} data-testid="present-points">
            <Megaphone className="size-4" />Present your points
          </LoadingButton>
          {blocked ? <span id={`present-why-${agent.role}`} className="min-w-0 flex-1 text-xs text-muted-foreground" data-testid="present-why">{blocked}</span> : null}
        </div>
      ) : null}
      {act.error ? <p role="alert" className="text-xs text-bad">{act.error}</p> : null}
    </section>
  );
}
