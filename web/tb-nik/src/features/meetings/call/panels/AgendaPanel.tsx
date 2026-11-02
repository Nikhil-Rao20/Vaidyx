// The Agenda panel of the call (night-v3 5.1, research/04 section 6.9): every Case File in order with its number, patient line, its
// state (Done with the outcome, Now, Next, Later, Not ready), its time as the agenda rail shows it (planned minutes; for Now the time
// spent and what is left, amber under 2 minutes and "time up" at 0; for Done the minutes it took), "waiting on Dr X" and the
// presenter; the coordinator clicks a row to put that case on the floor. The not-ready Case Files are listed greyed at the end.
// "Started" at the foot; on a phone (no rail) the quorum line too. Meetings-v2 3.4: "Taken up" on a Case File taken up during the
// meeting, and the coordinator's "Take up another Case File" (the phone has no rail).
import { Fragment, useContext, type ReactNode } from "react";
import { FilePlus2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import type { AgendaRow, MeetingOutcome } from "@/lib/live";
import { StatusChip, fmtDateTime, type ChipKind } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { usePanelAction } from "../../components/People";
import { useCall } from "../context";
import { fmtClock } from "../../components/shared";
import { fmtMinutes, presenterOf, remainingOf, rowElapsed, useCaseClock, type ClockTone } from "../CaseFlow";
import { QuorumLine } from "../QuorumLine";
import { ShellContext } from "../useCallState";
import { TAKEN_UP_WORD, takenUp } from "../TakeUpDialog";

export type AgendaStateKind = "done" | "now" | "next" | "later" | "not_ready";
export interface AgendaState { kind: AgendaStateKind; word: string }

/** The outcome's words of a decided row ("" when the row has none). */
export function outcomeWord(row: AgendaRow, outcomes?: Record<string, MeetingOutcome>): string {
  const oc = outcomes?.[row.case_id];
  return row.outcome_label ?? oc?.label ?? (row.outcome ?? oc?.outcome ?? "").replace(/_/g, " ");
}

export function isDone(row: AgendaRow, outcomes?: Record<string, MeetingOutcome>): boolean {
  return !!(row.decided || row.outcome || outcomes?.[row.case_id]);
}

/** The state of one agenda row: Not ready; Now (on the floor); Done with its outcome; Next (the first open case after the one on
 * the floor, or the first open case when none is); Later. */
export function agendaRowState(row: AgendaRow, order: AgendaRow[], cid: string | null, outcomes?: Record<string, MeetingOutcome>, notReady = false): AgendaState {
  if (notReady) return { kind: "not_ready", word: "Not ready" };
  if (cid && row.case_id === cid) return { kind: "now", word: "Now" };
  if (isDone(row, outcomes)) { const w = outcomeWord(row, outcomes); return { kind: "done", word: w ? `Done: ${w}` : "Done" }; }
  const at = cid ? order.findIndex((r) => r.case_id === cid) : -1;
  const next = order.find((r, i) => i > at && r.case_id !== cid && !isDone(r, outcomes));
  return next && next.case_id === row.case_id ? { kind: "next", word: "Next" } : { kind: "later", word: "Later" };
}

const CHIP: Record<AgendaStateKind, ChipKind> = { done: "ok", now: "info", next: "review", later: "muted", not_ready: "warn" };
const CLOCK_TONE: Record<ClockTone, string> = { normal: "text-foreground", low: "text-warn", up: "text-bad" };

export function AgendaPanel() {
  const ctx = useCall();
  const x = useContext(ShellContext);
  const { state: s, order, cid, canManage } = ctx;
  const act = usePanelAction();
  const notReady = s.agenda.not_ready ?? [];
  const per = s.meeting.minutes_per_case;
  const conduct = canManage && ctx.variant === "coordinator";
  const clock = useCaseClock(s);
  const remaining = remainingOf(clock.left, clock.timer);

  const item = (r: AgendaRow, n: number | null, greyed: boolean) => {
    const st = agendaRowState(r, order, cid, s.outcomes, greyed);
    const minutes = r.minutes ?? per;
    const now = st.kind === "now";
    const presenter = presenterOf(r, s, cid);
    const took = st.kind === "done" ? fmtMinutes(rowElapsed(r)) : "";
    const line = r.patient_line || r.case_id;
    // The time words as the rail shows them, then the presenter, who it waits on, and why it is not ready.
    const parts: ReactNode[] = [];
    if (now && (clock.elapsed > 0 || clock.timer)) parts.push(<span className="tabular-nums text-foreground">{fmtClock(clock.elapsed)} spent</span>);
    if (now && remaining) parts.push(<span className={cn("font-medium tabular-nums", CLOCK_TONE[remaining.tone])} data-tone={remaining.tone}>{remaining.text}</span>);
    if (!greyed && st.kind !== "done" && minutes) parts.push(`${minutes} min planned`);
    if (took) parts.push(`took ${took}`);
    if (presenter) parts.push(`Presenter: ${presenter}`);
    if (r.waiting_on) parts.push(`waiting on ${r.waiting_on.name}`);
    if (greyed && r.reason) parts.push(r.reason);
    if (!greyed && takenUp(r)) parts.push(<span className="font-medium text-foreground" data-testid="agenda-taken-up">{TAKEN_UP_WORD} during the meeting</span>);
    return (
      <li key={r.case_id} className={cn("rounded-md px-2 py-1.5", now && "bg-secondary", greyed && "opacity-60")} aria-current={now ? "true" : undefined} data-case={r.case_id}>
        <div className="flex items-center gap-2 text-sm">
          <span className="w-5 shrink-0 text-xs tabular-nums text-muted-foreground">{n ? `${n}.` : ""}</span>
          {conduct && !greyed ? (
            <button type="button" className={cn("min-w-0 flex-1 truncate text-left underline-offset-2 hover:underline disabled:opacity-60 disabled:no-underline", ctx.phone && "min-h-11")} onClick={() => void act.run(`go:${r.case_id}`, () => ctx.actions.go(r.case_id))} disabled={!!act.pending || now} title={now ? "On the screen" : "Put this case on the screen"}>{line}</button>
          ) : <span className="min-w-0 flex-1 truncate">{line}</span>}
          <StatusChip kind={CHIP[st.kind]}>{st.word}</StatusChip>
          <Link to={`/cases/${r.case_id}`} className={cn("shrink-0 text-xs text-link underline", ctx.phone && "inline-flex min-h-11 items-center")} title="Open the Case File">Case File</Link>
        </div>
        <p className="pl-7 text-xs text-muted-foreground" data-testid="agenda-row-times">
          {parts.map((x, i) => <Fragment key={i}>{i ? " · " : ""}{x}</Fragment>)}
        </p>
      </li>
    );
  };

  return (
    <div className="space-y-3">
      {order.length ? <ol className="space-y-1" aria-label="Agenda">{order.map((r, i) => item(r, i + 1, false))}</ol> : <p className="text-sm text-muted-foreground">No Case Files on the agenda.</p>}
      {notReady.length ? (
        <section>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Not ready · {notReady.length}</h3>
          <ul className="space-y-1">{notReady.map((r) => item(r, null, true))}</ul>
        </section>
      ) : null}
      {act.error ? <p role="alert" className="text-xs text-bad">{act.error}</p> : null}
      {conduct && ctx.inSession ? <Button size="sm" variant="outline" className={cn(ctx.phone && "min-h-11")} onClick={x.openTakeUp} data-testid="agenda-take-up"><FilePlus2 className="size-4" />Take up another Case File</Button> : null}
      {ctx.phone && s.quorum ? <section className="border-t border-border pt-2" aria-label="Quorum"><QuorumLine /></section> : null}
      {s.meeting.started_at ? <p className="border-t border-border pt-2 text-xs text-muted-foreground">Started {fmtDateTime(s.meeting.started_at)}</p> : null}
    </div>
  );
}
