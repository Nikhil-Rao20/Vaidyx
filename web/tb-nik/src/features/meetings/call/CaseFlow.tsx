// The case flow of the call (night-v3 5.4, research/04 section 6.13): when the coordinator moves the meeting to another case, the
// member and the room screen see a short toast at the top of the stage, "Moved to case 4 of 8: <patient line>", for 3 s and hear the
// polite announcement "The meeting moved to case 4 of 8"; a new presenter is announced as "Presenter: <name>". The member's "stepped
// away" state is reset by the shell on a case change, not here. Also the case clock the agenda rail and the Agenda panel share: the
// time spent on the case on the floor (counting up between events while the timer runs) and what is left of its timer.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRightLeft } from "lucide-react";
import type { AgendaRow, MeetingState, MeetingTimer } from "@/lib/live";
import { fmtClock, useCountdown } from "../components/shared";
import { useCall } from "./context";
import type { CallCtx } from "./types";
import { cn } from "@/lib/utils";

/** How long the "Moved to case" toast stays. */
export const CASE_TOAST_MS = 3000;
/** Under this many seconds left the remaining time turns amber ("under 2 minutes"). */
export const LOW_SECONDS = 120;

export type ClockTone = "normal" | "low" | "up";

export interface CaseClock {
  /** Seconds spent on the case on the floor so far. */
  elapsed: number;
  /** Seconds left on its timer (0 without a timer). */
  left: number;
  timer: MeetingTimer | null;
}

/** Seconds spent: total minus what is left when the timer knows its total (the server's own rule), else the server's figure plus what
 * the local countdown has used since the last event. */
export function elapsedOf(current: MeetingState["current"], left: number): number {
  const t = current?.timer ?? null;
  if (t && typeof t.total === "number" && t.total > 0) return Math.max(0, t.total - left);
  const base = Math.max(0, current?.elapsed_seconds ?? 0);
  return t ? base + Math.max(0, t.seconds_left - left) : base;
}

/** The clock of the case on the floor, ticking between events while its timer runs. */
export function useCaseClock(state: MeetingState): CaseClock {
  const timer = state.current?.timer ?? null;
  const left = useCountdown(timer);
  return { elapsed: elapsedOf(state.current, left), left, timer };
}

/** "7:42 left" (amber under 2 minutes), "time up" at 0 (red), "paused" when the timer is stopped; null without a timer. The words
 * carry the meaning; the colour only repeats it. */
export function remainingOf(left: number, timer: MeetingTimer | null | undefined): { text: string; tone: ClockTone } | null {
  if (!timer) return null;
  if (left <= 0 && (timer.total || timer.running)) return { text: "time up", tone: "up" };
  if (left <= 0) return null;
  const text = `${fmtClock(left)} left${timer.running ? "" : ", paused"}`;
  return { text, tone: left < LOW_SECONDS ? "low" : "normal" };
}

/** Minutes in words for a finished case: "12 min", "under 1 min"; "" when unknown. */
export function fmtMinutes(sec: number | null | undefined): string {
  if (typeof sec !== "number" || !Number.isFinite(sec) || sec <= 0) return "";
  return sec < 60 ? "under 1 min" : `${Math.round(sec / 60)} min`;
}

/** "3 minutes 8 seconds" for a screen reader. */
export function spokenClock(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return [m ? `${m} minute${m === 1 ? "" : "s"}` : "", r || !m ? `${r} second${r === 1 ? "" : "s"}` : ""].filter(Boolean).join(" ");
}

/** The seconds a finished case took (the server keeps it when the coordinator ends the case). */
export function rowElapsed(r: AgendaRow): number | null {
  const v = (r as AgendaRow & { elapsed_seconds?: number | null }).elapsed_seconds;
  return typeof v === "number" ? v : null;
}

/** The presenter's words for a row: the live presenter for the case on the floor (with the department), else the row's own. */
export function presenterOf(r: AgendaRow, s: MeetingState, cid: string | null): string {
  const p = cid && r.case_id === cid ? s.current?.presenter : null;
  if (p?.name) return p.name;
  return r.presenter_name || r.presenter?.name || "";
}

/** "case 4 of 8" for the case on the floor, or "the next case" when it is not in the agenda order. */
export function casePosition(order: AgendaRow[], cid: string): string {
  const i = order.findIndex((r) => r.case_id === cid);
  return i >= 0 ? `case ${i + 1} of ${order.length}` : "the next case";
}

/** The toast and the announcement when the meeting moves to the case `cid`. */
export function moveMessages(c: Pick<CallCtx, "order" | "row" | "state">, cid: string, presenterName?: string | null): { toast: string; said: string } {
  const pos = casePosition(c.order, cid);
  const line = c.row?.patient_line || cid;
  const lead = pos === "the next case" ? "Moved to the next case" : `Moved to ${pos}`;
  return { toast: `${lead}: ${line}`, said: `The meeting moved to ${pos}.${presenterName ? ` Presenter: ${presenterName}.` : ""}` };
}

export function CaseFlow() {
  const c = useCall();
  const reduce = useReducedMotion();
  const cid = c.cid;
  const presenter = c.state.current?.presenter ?? null;
  const pKey = presenter?.user || presenter?.name || "";
  const seen = useRef<{ cid: string | null; presenter: string } | null>(null);
  const [toast, setToast] = useState<{ key: number; text: string } | null>(null);
  const showToast = c.variant === "member" || c.variant === "room";

  useEffect(() => {
    const before = seen.current;
    seen.current = { cid, presenter: pKey };
    if (!before) return; // the first render: nothing moved
    if (cid && cid !== before.cid) {
      const m = moveMessages(c, cid, presenter?.name);
      if (showToast) setToast({ key: Date.now(), text: m.toast });
      c.announce(m.said);
      return;
    }
    if (pKey && pKey !== before.presenter && presenter?.name) c.announce(`Presenter: ${presenter.name}`);
  }, [cid, pKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!toast) return undefined;
    const id = window.setTimeout(() => setToast(null), CASE_TOAST_MS);
    return () => window.clearTimeout(id);
  }, [toast]);

  const room = c.variant === "room";
  return (
    <div className={cn("pointer-events-none fixed inset-x-0 z-40 flex justify-center px-4", room ? "top-28" : c.phone ? "top-16" : "top-[7.25rem]")}>
      <AnimatePresence>
        {toast ? (
          // role status for the tests and assistive tools; aria-live off because the shell's polite region already says it once.
          <motion.p key="case-toast" role="status" aria-live="off" data-testid="case-toast"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}
            className={cn("inline-flex max-w-full items-center gap-2 rounded-xl border border-stage-line bg-stage-panel/95 px-4 py-2 font-medium text-stage-fg shadow-[var(--shadow-lift)] backdrop-blur", room ? "text-xl" : "text-sm")}>
            <ArrowRightLeft className={cn("shrink-0 text-primary", room ? "size-6" : "size-4")} aria-hidden />
            <span className="min-w-0 truncate">{toast.text}</span>
          </motion.p>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
