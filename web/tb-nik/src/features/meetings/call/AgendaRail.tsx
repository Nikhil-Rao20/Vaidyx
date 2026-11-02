// The agenda rail at the left of the call on a laptop (research/04 section 6.13): each row "n. patient line", a state word (Done with
// the outcome, Now, Next, Later, Not ready) and its time: the planned minutes for Later and Next; for Now the time spent (counting up
// while the timer runs) and what is left ("7:42 left", amber under 2 minutes, "time up" in red at 0: the words carry the meaning);
// for Done the minutes it took when known. The presenter under the current row. The coordinator clicks a row to put that case on the
// screen. Under 1280 px (and while a side panel is open under 1536 px) it folds to a column of numbers; a button opens it. The quorum
// line (QuorumLine compact) sits at its foot when the server sends one.
// Meetings-v2 3.4: a Case File taken up during the meeting is marked "Taken up"; the coordinator's "Take up another Case File" sits at
// the rail's foot while the meeting is in session (the search dialog lives in the shell, TakeUpDialog.tsx).
// The room screen (night-v3 5.5, research/04 section 6.4) has its own look (RoomAgenda): the number, the patient line and the word
// (Done, Now, Next, Later) in 20 px type, no click, no fold button; folded to the numbers under 1600 px; "+n more" past ROOM_ROWS.
import { useContext, useEffect, useState } from "react";
import { FilePlus2, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import type { AgendaRow, MeetingState } from "@/lib/live";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useCall } from "./context";
import { fmtClock } from "../components/shared";
import { fmtMinutes, presenterOf, remainingOf, rowElapsed, spokenClock, useCaseClock, type ClockTone } from "./CaseFlow";
import { QuorumLine } from "./QuorumLine";
import { ShellContext } from "./useCallState";
import { TAKEN_UP_WORD, takenUp } from "./TakeUpDialog";
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

// "Now" in a deep teal on the light stage (the brand teal is 2:1 on the raised row); the brand teal stays on a dark stage.
const TONE: Record<RowState, string> = {
  done: "text-ok",
  now: "text-[#006b65] dark:text-primary",
  next: "text-stage-fg",
  later: "text-stage-muted",
  not_ready: "text-stage-muted",
};

/** The remaining time's colour on the stage: amber under 2 minutes, red at 0 (the words say it too). */
export const CLOCK_TONE: Record<ClockTone, string> = { normal: "text-stage-fg", low: "text-warn", up: "text-bad" };

/** The most agenda rows the room screen shows; the rest are "+n more" (the page never scrolls). */
export const ROOM_ROWS = 12;

/** The rows the room screen shows: the current case kept in view, at most `max`, and how many are left out. Pure. */
export function roomRows<T extends { case_id: string }>(rows: T[], cid: string | null, max = ROOM_ROWS): { shown: T[]; more: number } {
  if (rows.length <= max) return { shown: rows, more: 0 };
  const at = Math.max(0, rows.findIndex((r) => r.case_id === cid));
  const from = Math.min(Math.max(0, at - 2), rows.length - max);
  return { shown: rows.slice(from, from + max), more: rows.length - max };
}

const ROOM_WORD: Record<RowState, string> = { done: "Done", now: "Now", next: "Next", later: "Later", not_ready: "Not ready" };
/** The room's colours: at least 7:1 on the panel and on the raised "Now" row, light or dark (the muted grey is too faint on a
 * projector for the later rows). */
const ROOM_TONE: Record<RowState, string> = { done: "text-[#155a3a] dark:text-[#8fe0b3]", now: "text-[#08506a] dark:text-[#7cc4ff]", next: "text-stage-fg", later: "text-stage-fg/80", not_ready: "text-stage-fg/80" };

/** The room screen's agenda column: large type, no click; the numbers only under 1600 px. */
function RoomAgenda({ className }: { className?: string }) {
  const c = useCall();
  const open = useMediaQuery("(min-width: 1600px)");
  const s = c.state;
  const states = rowStates(c.order, [], c.cid, s.outcomes);
  const { shown, more } = roomRows(c.order, c.cid);
  return (
    <nav aria-label="Agenda" data-testid="agenda-rail" data-look="room" data-open={open ? "true" : "false"} className={cn("flex min-h-0 shrink-0 flex-col overflow-hidden rounded-xl border border-stage-line bg-stage-panel", open ? "w-64" : "w-16", className)}>
      {open ? <h2 className="border-b border-stage-line px-3 py-2 text-base font-semibold uppercase tracking-wide text-stage-fg/80">Agenda</h2> : null}
      <ol className="min-h-0 flex-1 space-y-1 overflow-hidden p-2">
        {shown.map((r) => {
          const st = states.get(r.case_id) ?? "later";
          const n = c.order.indexOf(r) + 1;
          const line = r.patient_line || r.case_id;
          const word = ROOM_WORD[st];
          return (
            <li key={r.case_id} aria-current={st === "now" ? "true" : undefined} data-state={st} aria-label={`${n}. ${line}, ${word}`} title={`${n}. ${line}, ${word}`}
              className={cn("rounded-lg px-2 py-1.5 text-[20px] leading-snug", st === "now" && "bg-stage-raised ring-2 ring-primary/70")}>
              {open ? (
                <div className="flex items-baseline gap-2">
                  <span className="w-7 shrink-0 tabular-nums text-stage-fg/80">{n}.</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-stage-fg">{line}</span>
                    <span className={cn("block font-semibold", ROOM_TONE[st])} data-testid="room-row-word">{word}</span>
                  </span>
                </div>
              ) : <span className={cn("block text-center font-semibold tabular-nums", ROOM_TONE[st])}>{n}</span>}
            </li>
          );
        })}
      </ol>
      {more > 0 ? <p className="border-t border-stage-line px-2 py-1.5 text-center text-[20px] text-stage-fg/80" data-testid="room-agenda-more">+{more} more</p> : null}
    </nav>
  );
}

export function AgendaRail({ className, room }: { className?: string; room?: boolean }) {
  if (room) return <RoomAgenda className={className} />;
  return <CallAgendaRail className={className} />;
}

function CallAgendaRail({ className }: { className?: string }) {
  const c = useCall();
  const x = useContext(ShellContext);
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
          const taken = st !== "not_ready" && takenUp(r);
          const label = `${n ? `${n}. ` : ""}${line}, ${word}${taken ? `, ${TAKEN_UP_WORD.toLowerCase()} during the meeting` : ""}${timeSaid ? `, ${timeSaid}` : ""}${presenter ? `, presenter ${presenter}` : ""}`;
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
                {taken ? <span className="mt-0.5 inline-block rounded-full bg-stage-raised px-1.5 text-[11px] font-medium text-stage-fg ring-1 ring-stage-line" data-testid="rail-taken-up" title="Taken up during the meeting: it was not on the planned agenda">{TAKEN_UP_WORD}</span> : null}
                {presenter ? <span className="block truncate text-[11px] text-stage-muted" data-testid="rail-presenter">Presenter: {presenter}</span> : null}
              </span>
            </>
          ) : <span className={cn("w-full text-center text-sm tabular-nums", TONE[st], now && remaining && remaining.tone !== "normal" && CLOCK_TONE[remaining.tone])}>{n ?? "·"}</span>;
          const cls = cn("flex w-full items-start gap-1.5 rounded-lg px-1.5 py-1.5 text-left outline-none", st === "now" && "bg-stage-raised ring-1 ring-primary/60", st === "not_ready" && "text-stage-muted", clickable && "hover:bg-stage-raised focus-visible:ring-2 focus-visible:ring-primary");
          return (
            <li key={r.case_id} aria-current={st === "now" ? "true" : undefined} data-state={st} data-taken-up={taken ? "true" : undefined}>
              {clickable
                ? <button type="button" className={cls} onClick={() => void c.actions.go(r.case_id).catch(() => {})} title={`Put this case on the screen: ${line}`} aria-label={`Put on the screen: ${label}`}>{inner}</button>
                : <div className={cls} title={label} aria-label={open ? undefined : label}>{inner}</div>}
            </li>
          );
        })}
      </ol>
      {coordinator && c.inSession ? (
        <div className={cn("shrink-0 border-t border-stage-line p-1.5", !open && "flex justify-center")}>
          <button type="button" onClick={x.openTakeUp} title="Take up another Case File: search one that is not on this agenda and put it on the screen" aria-label="Take up another Case File"
            className={cn("flex items-center gap-1.5 rounded-lg text-sm text-stage-fg outline-none hover:bg-stage-raised focus-visible:ring-2 focus-visible:ring-primary", open ? "w-full px-1.5 py-1.5 text-left" : "size-8 justify-center")} data-testid="rail-take-up">
            <FilePlus2 className="size-4 shrink-0 text-stage-muted" aria-hidden />{open ? <span className="min-w-0 truncate">Take up another Case File</span> : null}
          </button>
        </div>
      ) : null}
      {q && open ? (
        <div className="scroll-thin max-h-56 shrink-0 overflow-y-auto border-t border-stage-line p-2.5" data-testid="rail-quorum">
          <QuorumLine compact />
        </div>
      ) : null}
    </nav>
  );
}
