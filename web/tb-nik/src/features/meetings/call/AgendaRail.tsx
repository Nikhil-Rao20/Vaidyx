// The agenda rail at the left of the call on a laptop (research/04 section 6.13): each row "n. patient line", a state word (Done with
// the outcome, Now, Next, Later, Not ready) and its time: the planned minutes for Later and Next; for Now the time spent (counting up
// while the timer runs) and what is left ("7:42 left", amber under 2 minutes, "time up" in red at 0: the words carry the meaning);
// for Done the minutes it took when known. The presenter under the current row. The coordinator clicks a row to put that case on the
// screen. Under 1280 px (and while a side panel is open under 1536 px) it folds to a column of numbers; a button opens it. The quorum
// line (QuorumLine compact) sits at its foot when the server sends one.
import { useEffect, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import type { AgendaRow, MeetingState } from "@/lib/live";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useCall } from "./context";
import { fmtClock } from "../components/shared";
import { fmtMinutes, presenterOf, remainingOf, rowElapsed, spokenClock, useCaseClock, type ClockTone } from "./CaseFlow";
import { QuorumLine } from "./QuorumLine";
import { cn } from "@/lib/utils";

export type RowState = "done" | "now" | "next" | "later" | "not_ready";

/** The state of each agenda row: done when an outcome is saved, now for the case on the screen, next for the first open one after it. */
export function rowStates(order: AgendaRow[], notReady: AgendaRow[], cid: string | null, outcomes?: MeetingState["outcomes"]): Map<string, RowState> {
  const out = new Map<string, RowState>();
  const done = (r: AgendaRow) => !!(r.decided || r.outcome || outcomes?.[r.case_id]);
  const at = order.findIndex((r) => r.case_id === cid);
  let nextGiven = false;
  order.forEach((r, i) => {
    if (r.case_id === cid) out.set(r.case_id, "now");
    else if (done(r)) out.set(r.case_id, "done");
    else if (!nextGiven && i > at) { out.set(r.case_id, "next"); nextGiven = true; }
    else out.set(r.case_id, "later");
  });
  for (const r of notReady) if (!out.has(r.case_id)) out.set(r.case_id, "not_ready");
  return out;
}

export function stateWord(st: RowState, r: AgendaRow, outcomes?: MeetingState["outcomes"]): string {
  if (st === "done") return `Done: ${r.outcome_label || outcomes?.[r.case_id]?.label || (r.outcome ?? outcomes?.[r.case_id]?.outcome ?? "outcome saved").replace(/_/g, " ")}`;
  return st === "now" ? "Now" : st === "next" ? "Next" : st === "later" ? "Later" : "Not ready";
}

const TONE: Record<RowState, string> = {
  done: "text-[#8fe0b3]",
  now: "text-primary",
  next: "text-stage-fg",
  later: "text-stage-muted",
  not_ready: "text-stage-muted",
};

/** The remaining time's colour on the dark stage: amber under 2 minutes, red at 0 (the words say it too). */
export const CLOCK_TONE: Record<ClockTone, string> = { normal: "text-stage-fg", low: "text-[#ffd48a]", up: "text-[#ffb4a8]" };

export function AgendaRail({ className }: { className?: string }) {
  const c = useCall();
  const wide = useMediaQuery("(min-width: 1280px)");
  const roomy = useMediaQuery("(min-width: 1536px)");
  // Open from 1280 px; folded while a side panel is open below 1536 px so the stage keeps its width. The button overrides it.
  const panelOpen = !!c.panel;
  const [open, setOpen] = useState(wide && (!panelOpen || roomy));
  useEffect(() => { setOpen(wide && (!panelOpen || roomy)); }, [wide, roomy, panelOpen]);
  const s = c.state;
  const coordinator = c.variant === "coordinator" && c.canManage;
  const notReady = s.agenda.not_ready ?? [];
  const states = rowStates(c.order, notReady, c.cid, s.outcomes);
  const perCase = s.meeting.minutes_per_case;
  const rows = [...c.order, ...notReady];
  const q = s.quorum;
  const clock = useCaseClock(s);
  const remaining = remainingOf(clock.left, clock.timer);
  const remainingSaid = !remaining ? "" : remaining.tone === "up" ? "time up" : `${spokenClock(clock.left)} left${clock.timer?.running ? "" : ", paused"}`;

  return (
    <nav aria-label="Agenda" data-testid="agenda-rail" data-open={open ? "true" : "false"} className={cn("flex min-h-0 shrink-0 flex-col rounded-xl border border-stage-line bg-stage-panel transition-[width] duration-200", open ? "w-56 xl:w-60" : "w-12", className)}>
      <div className={cn("flex items-center border-b border-stage-line px-1.5 py-1.5", open ? "justify-between" : "justify-center")}>
        {open ? <h2 className="px-1.5 text-xs font-semibold uppercase tracking-wide text-stage-muted">Agenda</h2> : null}
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={open ? "Fold the agenda" : "Open the agenda"} title={open ? "Fold the agenda" : "Open the agenda"} className="grid size-8 place-items-center rounded-md text-stage-muted outline-none hover:bg-stage-raised hover:text-stage-fg focus-visible:ring-2 focus-visible:ring-primary">
          {open ? <PanelLeftClose className="size-4" aria-hidden /> : <PanelLeftOpen className="size-4" aria-hidden />}
        </button>
      </div>
      <ol className="scroll-thin min-h-0 flex-1 space-y-0.5 overflow-y-auto p-1.5">
        {rows.map((r) => {
          const st = states.get(r.case_id) ?? "later";
          const n = st === "not_ready" ? null : c.order.indexOf(r) + 1;
          const word = stateWord(st, r, s.outcomes);
          const mins = r.minutes ?? perCase;
          const line = r.patient_line || r.case_id;
          const now = st === "now";
          const took = st === "done" ? fmtMinutes(rowElapsed(r)) : "";
          const presenter = now ? presenterOf(r, s, c.cid) : "";
          // The time words: planned minutes for Next and Later, spent and left for Now, the minutes it took for Done.
          const timeSaid = now
            ? [clock.elapsed > 0 || clock.timer ? `${spokenClock(clock.elapsed)} spent` : "", remainingSaid, mins ? `${mins} minutes planned` : ""].filter(Boolean).join(", ")
            : st === "done" ? (took ? `took ${took}` : "") : mins && st !== "not_ready" ? `${mins} minutes planned` : "";
          const label = `${n ? `${n}. ` : ""}${line}, ${word}${timeSaid ? `, ${timeSaid}` : ""}${presenter ? `, presenter ${presenter}` : ""}`;
          const clickable = coordinator && st !== "not_ready" && !now;
          const times = now ? (
            <>
              {clock.elapsed > 0 || clock.timer ? <span className="shrink-0 tabular-nums text-stage-fg" data-testid="rail-elapsed">· {fmtClock(clock.elapsed)} spent</span> : null}
              {remaining ? <span className={cn("shrink-0 font-medium tabular-nums", CLOCK_TONE[remaining.tone])} data-testid="rail-remaining" data-tone={remaining.tone}>· {remaining.text}</span>
                : mins ? <span className="shrink-0 text-stage-muted">· {mins} min planned</span> : null}
            </>
          ) : st === "done" ? (took ? <span className="shrink-0 text-stage-muted" data-testid="rail-took">· {took}</span> : null)
            : mins && st !== "not_ready" ? <span className="shrink-0 text-stage-muted" data-testid="rail-planned">· {mins} min</span> : null;
          const inner = open ? (
            <>
              <span className="w-5 shrink-0 text-xs tabular-nums text-stage-muted">{n ? `${n}.` : ""}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{line}</span>
                <span className="flex flex-wrap items-center gap-x-1.5 text-[11px]"><span className={cn("truncate font-medium", TONE[st])}>{word}</span>{times}</span>
                {presenter ? <span className="block truncate text-[11px] text-stage-muted" data-testid="rail-presenter">Presenter: {presenter}</span> : null}
              </span>
            </>
          ) : <span className={cn("w-full text-center text-sm tabular-nums", TONE[st], now && remaining && remaining.tone !== "normal" && CLOCK_TONE[remaining.tone])}>{n ?? "·"}</span>;
          const cls = cn("flex w-full items-start gap-1.5 rounded-lg px-1.5 py-1.5 text-left outline-none", st === "now" && "bg-stage-raised ring-1 ring-primary/60", st === "not_ready" && "opacity-55", clickable && "hover:bg-stage-raised focus-visible:ring-2 focus-visible:ring-primary");
          return (
            <li key={r.case_id} aria-current={st === "now" ? "true" : undefined} data-state={st}>
              {clickable
                ? <button type="button" className={cls} onClick={() => void c.actions.go(r.case_id).catch(() => {})} title={`Put this case on the screen: ${line}`} aria-label={`Put on the screen: ${label}`}>{inner}</button>
                : <div className={cls} title={label} aria-label={open ? undefined : label}>{inner}</div>}
            </li>
          );
        })}
      </ol>
      {q && open ? (
        <div className="scroll-thin max-h-56 shrink-0 overflow-y-auto border-t border-stage-line p-2.5" data-testid="rail-quorum">
          <QuorumLine compact />
        </div>
      ) : null}
    </nav>
  );
}
