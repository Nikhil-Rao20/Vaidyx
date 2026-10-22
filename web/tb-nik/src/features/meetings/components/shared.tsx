// Pieces the meeting pages share: the meeting status chip, the live-channel dot, the case timer, the slide renderer,
// the members strip, the questions list and the stand-in agent tile with its true states.
import { useEffect, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Bot, FileText, Hand, Images, Radio, Timer as TimerIcon, Wifi, WifiOff } from "lucide-react";
import { answerText, handUsers, type AgentState, type Attendee, type LiveStatus, type MeetingQuestion, type MeetingState, type MeetingTimer } from "@/lib/live";
import type { Slide, SlideCitation, SlideContentMap, SlideSentence } from "../types";
import { StatusChip, fmtDate, indianDates, initials, niceTitle } from "@/features/casefile/components/common";
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

function Dots() {
  return <span className="inline-flex gap-0.5 ml-0.5" aria-hidden>{[0, 1, 2].map((i) => <motion.span key={i} className="size-1 rounded-full bg-current" animate={{ opacity: [0.2, 1, 0.2] }} transition={{ repeat: Infinity, duration: 1, delay: i * 0.2 }} />)}</span>;
}

function Cite({ c, big }: { c: SlideCitation; big?: boolean }) {
  const page = typeof c.page === "number" ? ` p. ${c.page + 1}` : "";
  return <span className={cn("quote-chip ml-1 align-middle", big && "text-sm")} title={c.quote ? `"${c.quote}"` : undefined}><FileText className="size-3" aria-hidden />{niceTitle(c.doc_title) || "record"}{page}</span>;
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
            <p className={cn("text-muted-foreground", big ? "text-sm" : "text-xs")}>{q.by_name}{q.role ? `, to the ${q.agent_label ?? q.role.replace(/_/g, " ")} stand-in` : ""}</p>
            {a && (a.statements ?? []).length ? (
              <div className={cn("mt-1 border-l-2 border-primary pl-2 space-y-1", big ? "text-base" : "text-sm")}>
                {a.statements!.map((s, i) => <p key={i} className="text-foreground">{indianDates(s.text)}{(s.citations ?? []).map((c, j) => <Cite key={j} c={c} big={big} />)}</p>)}
                <p className={cn("text-muted-foreground", big ? "text-xs" : "text-[10px]")}>{a.note ?? "From the records only; the stand-in is not a member of the board."}</p>
              </div>
            ) : text ? <p className={cn("mt-1 text-foreground border-l-2 border-primary pl-2", big ? "text-base" : "text-sm")}>{text}</p> : null}
            {a?.status === "not_documented" ? <p className={cn("text-muted-foreground", big ? "text-sm" : "text-xs")}>Not documented in the records.</p> : null}
            {waiting ? <p className={cn("text-muted-foreground italic", big ? "text-sm" : "text-xs")}>The stand-in is reading the records</p> : null}
          </li>
        );
      })}
    </ol>
  );
}

// ---- slides -------------------------------------------------------------------------------------------------------------
function Sentence({ s, big }: { s: SlideSentence | string; big?: boolean }) {
  if (typeof s === "string") return <li className={cn("text-foreground", big ? "text-xl leading-snug" : "text-sm")}>{indianDates(s)}</li>;
  return <li className={cn("text-foreground", big ? "text-xl leading-snug" : "text-sm")}>{indianDates(s.text)}{(s.citations ?? []).slice(0, 3).map((c, j) => <Cite key={j} c={c} big={big} />)}</li>;
}

const GAP_WORD: Record<string, string> = { missing: "not found in the file", needs_confirmation: "needs confirmation", not_final: "not final", waived: "not needed", not_applicable: "not applicable" };

function SlideBody({ slide, c, big }: { slide: Slide; c: SlideContentMap; big?: boolean }) {
  const t = big ? "text-xl leading-snug" : "text-sm";
  const small = big ? "text-base" : "text-xs";
  const kind = slide.kind;
  if (kind === "summary" && c.from === "gate") {
    return (
      <div className="space-y-2">
        {c.board_question ? <p className={cn("text-foreground", t)}><span className="text-muted-foreground">Board question: </span>{c.board_question}</p> : null}
        {typeof c.satisfied === "number" && typeof c.total === "number" ? <p className={cn("text-foreground", t)}>{c.satisfied} of {c.total} records in the file</p> : null}
        <ul className="space-y-1">
          {(c.requirements ?? []).map((r) => (
            <li key={r.id} className={cn("flex items-baseline gap-2", t)}>
              <span className={cn("shrink-0 rounded-md border border-dashed px-1.5 font-mono", small, r.status === "satisfied" ? "text-ok border-ok/40" : r.status === "missing" ? "text-muted-foreground" : "text-warn")}>{r.status === "satisfied" ? "found" : `[ ${GAP_WORD[r.status] ?? r.status.replace(/_/g, " ")} ]`}</span>
              <span className="text-foreground">{r.label}</span>
            </li>
          ))}
        </ul>
        {c.note ? <p className={cn("text-muted-foreground", small)}>{c.note}</p> : null}
      </div>
    );
  }
  if (kind === "summary" || c.sections) {
    return (
      <div className="space-y-3">
        {c.label ? <span className={cn("inline-block rounded-full px-2 py-0.5 font-medium", small, c.reviewed ? "status-ok" : "status-review")}>{c.label}</span> : null}
        {c.stale ? <p className={cn("status-warn rounded-md px-2 py-1", small)}>Records changed since this draft: {c.stale}</p> : null}
        {(c.sections ?? []).filter((s) => s.text || (s.sentences ?? s.items ?? []).length).map((s, i) => (
          <section key={s.id ?? i}>
            <h4 className={cn("font-semibold text-foreground", big ? "text-xl" : "text-sm")}>{s.title ?? s.heading}</h4>
            {s.text ? <p className={cn("text-foreground", t)}>{indianDates(s.text)}</p> : null}
            <ul className="space-y-1">{(s.sentences ?? s.items ?? []).map((x, j) => <Sentence key={j} s={x} big={big} />)}</ul>
          </section>
        ))}
      </div>
    );
  }
  if (kind === "values" || c.values) {
    const vals = c.values ?? [];
    if (!vals.length) return <p className={cn("text-muted-foreground", t)}>No verified values yet.</p>;
    return (
      <dl className={cn("grid gap-x-4 gap-y-1.5", big ? "grid-cols-[minmax(12rem,auto)_1fr]" : "grid-cols-[minmax(8rem,auto)_1fr]")}>
        {vals.map((v) => (
          <div key={v.id} className="contents">
            <dt className={cn("text-muted-foreground", t)}>{v.label}</dt>
            <dd className={cn("text-foreground", t)}>{v.value}{v.doc_title ? <Cite c={{ doc_id: v.doc_id ?? "", doc_title: v.doc_title, page: v.page, quote: v.quote }} big={big} /> : null}{v.date ? <span className={cn("ml-2 text-muted-foreground", small)}>{fmtDate(v.date)}</span> : null}</dd>
          </div>
        ))}
      </dl>
    );
  }
  if (kind === "gaps" || c.gaps) {
    const gaps = c.gaps ?? [];
    const waivers = c.waivers ?? [];
    return (
      <div className="space-y-3">
        {typeof c.satisfied === "number" && typeof c.total === "number" ? <p className={cn("text-foreground", t)}>{c.satisfied} of {c.total} required records in the file</p> : null}
        {gaps.length === 0 ? <p className={cn("text-ok", t)}>No gaps: every required record is in the file or marked not needed.</p> : (
          <ul className="space-y-1">{gaps.map((g) => <li key={g.id} className={cn("text-foreground", t)}><span className={cn("mr-2 rounded-md border border-dashed px-1.5 font-mono text-muted-foreground", small)}>[ {GAP_WORD[g.status] ?? g.status.replace(/_/g, " ")} ]</span>{g.label}{g.department ? <span className="text-muted-foreground">, {g.department}</span> : null}</li>)}</ul>
        )}
        {waivers.length ? (
          <div>
            <h4 className={cn("font-semibold text-foreground", big ? "text-xl" : "text-sm")}>Marked not needed</h4>
            <ul className="space-y-1">{waivers.map((w, i) => <li key={i} className={cn("text-foreground", t)}>{w.requirement.replace(/_/g, " ")}{w.reason ? `: ${w.reason}` : ""}{w.by ? <span className="text-muted-foreground"> ({w.by})</span> : null}</li>)}</ul>
          </div>
        ) : null}
      </div>
    );
  }
  if (kind === "imaging" || kind === "pathology" || c.documents) {
    const docs = c.documents ?? [];
    if (!docs.length) return <p className={cn("text-muted-foreground", t)}>No {kind === "imaging" ? "imaging" : "pathology"} reports in the file.</p>;
    return (
      <div className="space-y-2">
        <ul className="space-y-2">
          {docs.map((d) => (
            <li key={d.doc_id} className={cn("text-foreground", t)}>
              <span className="font-medium">{niceTitle(d.title)}</span>
              <span className={cn("ml-2 text-muted-foreground", small)}>{[d.date ? fmtDate(d.date) : "", (d.status ?? "").toLowerCase(), d.signed === "yes" ? "signed" : ""].filter(Boolean).join(", ")}</span>
              {d.images ? <span className={cn("ml-2 inline-flex items-center gap-1 text-link", small)}><Images className="size-3.5" aria-hidden />{d.viewer_available ? "images in the viewer" : "images listed"}</span> : null}
              {(d.facts ?? []).length ? <ul className="mt-0.5 pl-4 space-y-0.5">{d.facts!.map((f) => <li key={f.id} className={cn("text-foreground", big ? "text-lg" : "text-sm")}><span className="text-muted-foreground">{f.label}: </span>{f.value}</li>)}</ul> : null}
            </li>
          ))}
        </ul>
        {c.note ? <p className={cn("text-muted-foreground", small)}>{c.note}</p> : null}
      </div>
    );
  }
  if (kind === "points" || c.points) {
    const pts = c.points ?? [];
    if (!pts.length) return <p className={cn("text-muted-foreground", t)}>No points for review yet.</p>;
    return (
      <div className="space-y-2">
        <ol className="space-y-1.5 list-decimal pl-6">{pts.map((p, i) => <li key={i} className={cn("text-foreground", t)}>{indianDates(p.text)}{(p.citations ?? []).slice(0, 2).map((c2, j) => <Cite key={j} c={c2} big={big} />)}{p.label ? <span className={cn("ml-2 text-muted-foreground", small)}>({p.label})</span> : null}</li>)}</ol>
        {c.note ? <p className={cn("text-muted-foreground", small)}>{c.note}</p> : null}
      </div>
    );
  }
  if (kind === "published" || c.items) {
    return (
      <div className="space-y-2">
        <span className={cn("inline-block rounded-full px-2 py-0.5 bg-muted text-muted-foreground font-medium", small)}>Published case, not advice for this patient</span>
        <ul className="space-y-2">{(c.items ?? []).map((p, i) => <li key={p.id ?? i} className={cn("text-foreground", t)}><span className="font-medium">{p.title}</span><span className={cn("block text-muted-foreground", small)}>{[p.authors, p.journal, p.year].filter(Boolean).join(", ")}{p.peer_reviewed === false ? ", not peer-reviewed" : ""}</span>{(p.quotes ?? []).map((q, j) => <blockquote key={j} className={cn("border-l-2 border-border pl-2 mt-0.5", big ? "text-lg" : "text-sm")}>{q.text}</blockquote>)}</li>)}</ul>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {(c.paragraphs ?? []).map((p, i) => <p key={i} className={cn("text-foreground", t)}>{p}</p>)}
      {c.note ? <p className={cn("text-muted-foreground", small)}>{c.note}</p> : null}
    </div>
  );
}

export function SlideContent({ slide, big }: { slide: Slide; big?: boolean }) {
  const c = slide.content;
  const body: ReactNode = c == null ? <p className={cn("text-muted-foreground", big ? "text-xl" : "text-sm")}>Nothing to show on this slide.</p>
    : typeof c === "string" ? c.split(/\n{2,}/).map((p, i) => <p key={i} className={cn("text-foreground", big ? "text-2xl leading-snug" : "text-sm")}>{p}</p>)
    : Array.isArray(c) ? <ul className="space-y-1.5 list-disc pl-5">{c.map((it, i) => <Sentence key={i} s={it} big={big} />)}</ul>
    : <SlideBody slide={slide} c={c} big={big} />;
  return (
    <div data-testid="slide" data-slide-kind={slide.kind}>
      <h3 className={cn("font-bold text-foreground mb-2", big ? "text-3xl" : "text-base")}>{slide.title}</h3>
      {body}
      {slide.kind === "summary" || slide.kind === "points" ? <p className={cn("mt-3 text-muted-foreground", big ? "text-sm" : "text-[10px]")}>From the records, with quotes. Vaidyx checks, routes, summarises and flags; the decision is the board's.</p> : null}
    </div>
  );
}
