// The Agenda panel of the call (night-v3 5.1, research/04 section 6.9): every Case File in order with its number, patient line, its
// state (Done with the outcome, Now, Next, Later, Not ready), planned minutes, "waiting on Dr X" and the presenter; the coordinator
// clicks a row to put that case on the floor. The not-ready Case Files are listed greyed at the end. "Started" at the foot.
import { Link } from "react-router-dom";
import type { AgendaRow, MeetingOutcome } from "@/lib/live";
import { StatusChip, fmtDateTime, type ChipKind } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { usePanelAction } from "../../components/People";
import { useCall } from "../context";

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

export function AgendaPanel() {
  const ctx = useCall();
  const { state: s, order, cid, canManage } = ctx;
  const act = usePanelAction();
  const notReady = s.agenda.not_ready ?? [];
  const per = s.meeting.minutes_per_case;
  const conduct = canManage && ctx.variant === "coordinator";

  const item = (r: AgendaRow, n: number | null, greyed: boolean) => {
    const st = agendaRowState(r, order, cid, s.outcomes, greyed);
    const minutes = r.minutes ?? per;
    const presenter = r.presenter_name ?? r.presenter?.name;
    const now = st.kind === "now";
    const line = r.patient_line || r.case_id;
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
        <p className="pl-7 text-xs text-muted-foreground">
          {[minutes ? `${minutes} min planned` : "", presenter ? `Presenter: ${presenter}` : "", r.waiting_on ? `waiting on ${r.waiting_on.name}` : "", greyed && r.reason ? r.reason : ""].filter(Boolean).join(" · ")}
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
      {s.meeting.started_at ? <p className="border-t border-border pt-2 text-xs text-muted-foreground">Started {fmtDateTime(s.meeting.started_at)}</p> : null}
    </div>
  );
}
