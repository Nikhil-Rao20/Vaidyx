// Pieces the meeting pages share: the meeting status chip, the live-channel dot, the case timer, the members strip, the questions
// list and the stand-in agent tile with its true states. (No slide renderer: the meeting shows the Case File itself, meetings-v2 2.6.)
import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Bot, FileText, Hand, Radio, Timer as TimerIcon, Wifi, WifiOff } from "lucide-react";
import { answerText, handUsers, type AgentState, type Attendee, type LiveStatus, type MeetingQuestion, type MeetingState, type MeetingTimer, type QuestionAnswer } from "@/lib/live";
import type { SlideCitation } from "../types";
import { NotSigned, StatusChip, indianDates, initials, modelLabel, niceTitle } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

export function MeetingStatusChip({ status }: { status: string }) {
  if (status === "in_session") return <StatusChip kind="ok" icon={Radio}>in session</StatusChip>;
  if (status === "closed" || status === "decided") return <StatusChip kind="muted">closed</StatusChip>;
  if (status === "cancelled") return <StatusChip kind="bad">cancelled</StatusChip>;
  return <StatusChip kind="info">planned</StatusChip>;
}

export function LiveDot({ status, detail, className }: { status: LiveStatus; detail?: string; className?: string }) {
  const word = status === "open" ? "live" : status === "connecting" ? "connecting" : status === "reconnecting" ? "reconnecting" : status === "unavailable" ? "checking every 10 s" : status === "closed" ? "closed" : "checking every 10 s";
  const Icon = status === "open" ? Wifi : WifiOff;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs", status === "open" ? "text-ok" : status === "reconnecting" || status === "unavailable" ? "text-warn" : "text-muted-foreground", className)} title={detail ?? (status === "open" ? "Connected to the live channel" : "The page checks the meeting every 10 seconds")} data-testid="live-dot" data-live={status}>
      <Icon className="size-3.5" aria-hidden />{word}
    </span>
  );
}

/** Counts down locally from the last timer event so the display stays smooth between events. */
export function useCountdown(t: MeetingTimer | null | undefined): number {
  const [left, setLeft] = useState(t?.seconds_left ?? 0);
  useEffect(() => {
    setLeft(t?.seconds_left ?? 0);
    if (!t?.running) return;
    const start = Date.now();
    const base = t.seconds_left;
    const id = window.setInterval(() => setLeft(Math.max(0, base - Math.round((Date.now() - start) / 1000))), 500);
    return () => window.clearInterval(id);
  }, [t?.seconds_left, t?.running]);
  return left;
}

export function fmtClock(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function TimerBadge({ timer, big }: { timer?: MeetingTimer | null; big?: boolean }) {
  const left = useCountdown(timer);
  if (!timer) return <span className={cn("inline-flex items-center gap-1 text-muted-foreground", big ? "text-2xl" : "text-sm")} data-testid="timer"><TimerIcon className={big ? "size-6" : "size-4"} aria-hidden />no timer</span>;
  const low = left <= 60 && timer.running;
  return (
    <span className={cn("inline-flex items-center gap-1 tabular-nums font-mono", big ? "text-3xl" : "text-sm", low ? "text-bad" : left === 0 ? "text-warn" : "text-foreground")} role="timer" aria-live={low ? "polite" : "off"} aria-label={`${fmtClock(left)} left`} data-testid="timer">
      <TimerIcon className={cn(big ? "size-6" : "size-4", timer.running && "animate-pulse")} aria-hidden />{fmtClock(left)}{!timer.running ? <span className={cn("text-muted-foreground font-sans", big ? "text-base" : "text-xs")}>{left === 0 && timer.total ? "time up" : "paused"}</span> : null}
    </span>
  );
}

export function MembersStrip({ attendance, hands, big }: { attendance: Attendee[]; hands?: MeetingState["hands"]; big?: boolean }) {
  const handSet = handUsers(hands);
  const admitted = attendance.filter((a) => a.status === "present" || a.status === "remote");
  const waiting = attendance.filter((a) => a.status === "waiting");
  const onlineCount = admitted.filter((a) => a.online !== false).length;
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Members" data-testid="members-strip">
      {admitted.length === 0 ? <span className={cn("text-muted-foreground", big ? "text-base" : "text-xs")}>No one has joined yet</span> : <span className={cn("text-muted-foreground", big ? "text-sm" : "text-xs")}>{onlineCount} online</span>}
      {admitted.map((a) => {
        const off = a.online === false;
        const label = `${a.name}${a.department_name || a.department ? `, ${a.department_name ?? a.department}` : ""}: ${a.status === "remote" ? "remote" : "in the room"}${off ? ", offline" : ""}`;
        return (
          <span key={a.user} className={cn("inline-flex items-center gap-1 rounded-full border border-border bg-card pr-2", big ? "text-sm" : "text-xs", off && "opacity-55")} title={label}>
            <span className={cn("grid place-items-center rounded-full font-medium text-primary-foreground", big ? "size-7 text-xs" : "size-5 text-[10px]", a.status === "remote" ? "bg-indigo text-white" : "bg-primary")} aria-hidden>{initials(a.name)}</span>
            <span className="max-w-[9rem] truncate">{a.name}</span>
            {a.head ? <span className="text-muted-foreground">head</span> : null}
            {a.status === "remote" ? <span className="text-muted-foreground">remote</span> : null}
            {handSet.has(a.user) || a.hand ? <Hand className="size-3.5 text-warn" aria-label="hand raised" /> : null}
            <span className="sr-only">{label}</span>
          </span>
        );
      })}
      {waiting.length ? <span className={cn("text-warn", big ? "text-sm" : "text-xs")}>{waiting.length} waiting to be admitted</span> : null}
    </div>
  );
}

const AGENT_STATES: Record<string, { word: string; ring: string }> = {
  ready: { word: "Ready", ring: "border-ok" },
  reading_question: { word: "Reading the question", ring: "border-indigo" },
  reading: { word: "Reading the question", ring: "border-indigo" },
  thinking: { word: "Thinking", ring: "border-review" },
  answering: { word: "Answering", ring: "border-primary" },
};

/** The stand-in agent tile: only when a stand-in for an absent head is active; its state is the real one from the server. */
export function AgentTile({ agent, big }: { agent?: AgentState | null; big?: boolean }) {
  const reduce = useReducedMotion();
  if (!agent?.active) return null;
  const key = agent.state && AGENT_STATES[agent.state] ? agent.state : "ready";
  const st = AGENT_STATES[key];
  const busy = key !== "ready";
  const who = agent.label || (agent.role ? agent.role.replace(/_/g, " ") : "");
  return (
    <motion.div layout initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className={cn("rounded-lg border-2 bg-card p-3 flex items-center gap-3", st.ring, big ? "min-w-64" : "")} role="status" aria-live="polite" data-testid="agent-tile" data-agent-state={key}>
      <motion.span animate={reduce ? {} : busy ? { scale: [1, 1.08, 1] } : { scale: 1 }} transition={busy ? { repeat: Infinity, duration: key === "thinking" ? 1.2 : 0.8 } : {}} className={cn("grid place-items-center rounded-full bg-secondary text-secondary-foreground shrink-0", big ? "size-12" : "size-9")} aria-hidden>
        <Bot className={big ? "size-7" : "size-5"} />
      </motion.span>
      <div className="min-w-0">
        <p className={cn("font-medium text-foreground leading-tight", big ? "text-lg" : "text-sm")}>Stand-in{who ? `: ${who}` : ""}</p>
        <p className={cn("text-muted-foreground", big ? "text-base" : "text-xs")}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.span key={key} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} className="inline-flex items-center gap-1">
              {st.word}{busy ? <Dots /> : null}
            </motion.span>
          </AnimatePresence>
        </p>
        <p className={cn("text-muted-foreground", big ? "text-xs" : "text-[10px]")}>{agent.note || "AI support: answers from the records only; not a member of the board."}</p>
      </div>
    </motion.div>
  );
}

/** Three pulsing dots after a busy word ("Thinking", "Answering"); the one copy the meeting screens share (review 9 C, M5). */
export function Dots() {
  return <span className="ml-0.5 inline-flex gap-0.5" aria-hidden>{[0, 1, 2].map((i) => <motion.span key={i} className="size-1 rounded-full bg-current" animate={{ opacity: [0.2, 1, 0.2] }} transition={{ repeat: Infinity, duration: 1, delay: i * 0.2 }} />)}</span>;
}

function Cite({ c, big }: { c: SlideCitation; big?: boolean }) {
  const page = typeof c.page === "number" ? ` p. ${c.page + 1}` : "";
  return <span className={cn("quote-chip ml-1 align-middle", big && "text-sm")} title={c.quote ? `"${c.quote}"` : undefined}><FileText className="size-3" aria-hidden />{niceTitle(c.doc_title) || "record"}{page}<NotSigned word={c.final_word} /></span>;
}

/** The review-status line of a "Present your points" answer: the brief's label ("AI draft, not reviewed", or "Reviewed by Dr <name>")
 * with the model that wrote the brief: "AI draft, not reviewed. Gemma-4-31B (non-medical)." (review 9 C, S1). */
export function briefAnswerLabel(a: Pick<QuestionAnswer, "brief_label" | "brief_model"> | null | undefined): string {
  const label = String(a?.brief_label || "AI draft, not reviewed").trim().replace(/\.+$/, "");
  const m = modelLabel(a?.brief_model);
  return m ? `${label}. ${m}.` : `${label}.`;
}

/** True when the brief behind a "Present your points" answer was reviewed by a doctor. */
export const briefAnswerReviewed = (a: Pick<QuestionAnswer, "brief_label"> | null | undefined) => /^reviewed/i.test(String(a?.brief_label ?? ""));

/** The department of the agent a question went to ("Medical Oncology", as the call names it): the role in words, title case. */
function agentDeptName(q: Pick<MeetingQuestion, "agent_label" | "role">): string {
  const r = String(q.role ?? "").trim();
  if (r) return r.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  return String(q.agent_label ?? "").replace(/\s+(support|stand-in|records check)$/i, "").trim();
}

export function QuestionsList({ questions, big, emptyText = "No questions yet.", caseId }: { questions: MeetingQuestion[]; big?: boolean; emptyText?: string; caseId?: string | null }) {
  const shown = caseId ? questions.filter((q) => !q.case_id || q.case_id === caseId) : questions;
  if (!shown.length) return <p className={cn("text-muted-foreground", big ? "text-base" : "text-sm")}>{emptyText}</p>;
  return (
    <ol className="space-y-2" data-testid="questions-list">
      {[...shown].reverse().map((q) => {
        const a = q.answer && typeof q.answer === "object" ? q.answer : null;
        const text = answerText(q);
        const waiting = !q.answer && !!q.role;
        return (
          <li key={q.id} className={cn("rounded-md border border-border bg-card p-2", big && "p-3")}>
            <p className={cn("font-medium text-foreground", big ? "text-lg" : "text-sm")}>{q.text}</p>
            <p className={cn("text-muted-foreground", big ? "text-sm" : "text-xs")}>{q.by_name}{q.role ? `, to the ${agentDeptName(q)} AI agent` : ""}</p>
            {a?.kind === "present_points" ? (
              <p className={cn("mt-1 font-semibold", briefAnswerReviewed(a) ? "text-ok" : "text-review", big ? "text-sm" : "text-[11px]")} data-testid="answer-brief-label">{briefAnswerLabel(a)}</p>
            ) : null}
            {a && (a.statements ?? []).length ? (
              <div className={cn("mt-1 border-l-2 border-primary pl-2 space-y-1", big ? "text-base" : "text-sm")}>
                {a.statements!.map((s, i) => <p key={i} className="text-foreground">{indianDates(s.text)}{(s.citations ?? []).map((c, j) => <Cite key={j} c={c} big={big} />)}</p>)}
                {a.kind === "present_points" && a.dropped_note ? <p className={cn("text-muted-foreground", big ? "text-xs" : "text-[10px]")} data-testid="answer-dropped-note">{a.dropped_note}</p> : null}
                <p className={cn("text-muted-foreground", big ? "text-xs" : "text-[10px]")}>{a.note ?? "From the records only; the AI agent is not a member of the board."}{a.model ? ` ${modelLabel(a.model)}.` : ""}</p>
              </div>
            ) : text ? <p className={cn("mt-1 text-foreground border-l-2 border-primary pl-2", big ? "text-base" : "text-sm")}>{indianDates(text)}</p> : null}
            {a?.status === "not_documented" ? <p className={cn("text-muted-foreground", big ? "text-sm" : "text-xs")}>Not documented in the records.</p> : null}
            {waiting ? <p className={cn("text-muted-foreground italic", big ? "text-sm" : "text-xs")}>The AI agent is reading the records</p> : null}
          </li>
        );
      })}
    </ol>
  );
}

