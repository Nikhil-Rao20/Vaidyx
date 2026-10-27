// The Chat panel of the call (night-v3 5.1, research/04 section 6.9): two tabs. "Questions to the board" is today's questions list
// with the ask box (a role chip row picks "Ask the board" or one of the agents standing in); an agent's answer shows its text, its
// sources as quote chips, the time, and Read aloud when agent voices are on. "Meeting chat" (item 5.3, research/04 section 6.9) is
// the text chat of the members admitted to the meeting: kept with the meeting record, apart from the questions to the agents, never
// pushed as a notification (owner decision D5). The room screen shows the questions only. Item 6.2: the chips of an answer are the
// agent points' chips (AgentPoints.tsx: document, date, page; open the record or show the quote), and a "Present your points"
// answer lists the brief's not documented items.
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { format, isToday, isValid, parseISO } from "date-fns";
import { motion } from "motion/react";
import { ArrowDown, SendHorizontal, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { SpeakButton } from "@/components/SpeakButton";
import { answerText, type AgendaRow, type AgentReference, type ChatMessage, type MeetingQuestion, type MeetingState, type QuestionAnswer } from "@/lib/live";
import { LoadingButton, fmtDateTime, indianDates, modelLabel } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { usePanelAction } from "../../components/People";
import { CitedText, parseMention, roleName } from "./AgentPoints";
import { useCall } from "../context";
import type { CallCtx } from "../types";

/** The questions of the Case File on the floor (questions without a case are shown everywhere), optionally for one agent role. */
export function questionsFor(questions: MeetingQuestion[] | undefined, caseId: string | null, role?: string): MeetingQuestion[] {
  return (questions ?? []).filter((q) => (!caseId || !q.case_id || q.case_id === caseId) && (role === undefined || q.role === role));
}

/** The questions still waiting for an answer (the Chat button's count). */
export function unansweredCount(questions: MeetingQuestion[] | undefined, caseId: string | null): number {
  return questionsFor(questions, caseId).filter((q) => !q.answer).length;
}

/** The items a "Present your points" answer lists as not documented (the brief's list; strings, or objects with a text). */
export function notDocumentedItems(a: unknown): string[] {
  const list = (a && typeof a === "object" ? (a as { not_documented?: unknown }).not_documented : null);
  if (!Array.isArray(list)) return [];
  return list.map((x) => (typeof x === "string" ? x : x && typeof x === "object" ? String((x as Record<string, unknown>).text ?? (x as Record<string, unknown>).item ?? (x as Record<string, unknown>).label ?? "") : "")).filter(Boolean);
}

/** The plain sentence of an answer the records do not support (the server speaks the same words; its technical message is the detail). */
export const NOT_DOCUMENTED_TEXT = "This is not documented in the Case File. I could not find a record line that supports an answer.";
/** After a refusal: two questions an agent can answer from the records, offered as quick fills of the box. */
export const QUICK_QUESTIONS = ["What do the records document?", "What is pending?"];
const ANSWER_NOTE = "AI agent, support only. From the records and guidelines only. Check the source.";

/** The footer of an agent's answer: "AI agent, support only. From the records and guidelines only. Check the source. Gemma-4-31B
 * (non-medical)." (the server's note, then the model's label). */
export function answerFooter(a: Pick<QuestionAnswer, "note" | "model"> | null | undefined): string {
  const note = (a?.note || ANSWER_NOTE).trim();
  const n = /[.!?]$/.test(note) ? note : `${note}.`;
  const m = modelLabel(a?.model);
  return m ? `${n} ${m}.` : n;
}

/** One guideline reference in words: "NCG Guidelines for Breast Cancer, NCG, 2023, p. 14" (the quote is shown apart). */
export function referenceLine(r: AgentReference): string {
  const parts = [String(r.title || r.file || "Guideline")];
  if (r.org) parts.push(String(r.org));
  if (r.year) parts.push(String(r.year));
  if (typeof r.page === "number") parts.push(r.page_end && r.page_end !== r.page ? `pp. ${r.page}-${r.page_end}` : `p. ${r.page}`);
  return parts.join(", ");
}

/** The queue line of a question waiting for the same agent's earlier answer: the server's words, else "Radiology is answering
 * <name>. Yours is next." */
export function queueLine(q: MeetingQuestion, dept: string, answering?: string | null): string {
  const note = (q as { queue_note?: unknown }).queue_note;
  if (typeof note === "string" && note.trim()) return note;
  return `${dept} is answering ${answering || "another question"}. Yours is next.`;
}

function Dots() {
  return <span className="ml-0.5 inline-flex gap-0.5" aria-hidden>{[0, 1, 2].map((i) => <motion.span key={i} className="size-1 rounded-full bg-current" animate={{ opacity: [0.2, 1, 0.2] }} transition={{ repeat: Infinity, duration: 1, delay: i * 0.2 }} />)}</span>;
}

/** One question with its answer: the statements as they arrive (each with its chips and its note), the guideline references, the
 * footer, Stop while the answer is being spoken and Read aloud once it is finished; a refusal with two quick questions; the plain
 * not documented sentence. */
function QuestionItem({ q, onQuick }: { q: MeetingQuestion; onQuick?: (text: string, role?: string) => void }) {
  const ctx = useCall();
  const { mid, agentVoices, agents, me, canManage } = ctx;
  const a = q.answer && typeof q.answer === "object" ? q.answer : null;
  const text = answerText(q);
  const status = a?.status ?? (q.answer ? "answered" : null);
  const dept = q.role ? roleName(q.role, agents) : "";
  const agent = q.role ? agents.find((x) => x.role === q.role) : undefined;
  const stmts = a?.statements ?? [];
  const streaming = status === "answering";
  const refused = status === "out_of_scope" || status === "not_listed";
  const notDoc = status === "not_documented" && a?.kind !== "present_points" && !stmts.length;
  const refs = a?.references ?? [];
  const cited = stmts.some((st) => (st.citations ?? []).length > 0) || refs.length > 0;
  const nd = a?.kind === "present_points" ? notDocumentedItems(a) : [];
  const playingHere = !!q.role && ctx.speakingNow?.question === q.id;
  const mayStopAll = !!q.role && (canManage || (!!me && q.by === me));
  const speakingSomewhere = !!agent && agent.question === q.id && agent.state === "speaking";
  const showStop = ctx.variant !== "room" && (playingHere || (speakingSomewhere && mayStopAll));
  const stop = () => {
    ctx.stopAgentAudio();
    if (mayStopAll && q.role) void ctx.actions.stopAgent(q.role, q.id).catch(() => undefined);
  };
  const quick = refused && !!onQuick && ctx.variant !== "room";
  return (
    <li className="rounded-md border border-border bg-card p-2" data-testid="question-item" data-status={status ?? "waiting"} data-question={q.id}>
      <p className="text-sm font-medium text-foreground">{q.text}</p>
      <p className="text-xs text-muted-foreground">{q.by_name}{q.role ? `, to the ${dept} AI agent` : ""}{q.at ? ` · ${fmtDateTime(q.at)}` : ""}</p>
      {q.role && !q.answer ? (
        q.queued ? <p className="mt-1 text-xs text-muted-foreground" data-testid="queue-line">{queueLine(q, dept, agent?.by_name)}</p>
          : <p className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground" role="status" data-testid="answer-waiting">Thinking<Dots /></p>
      ) : null}
      {stmts.length ? (
        <div className="mt-1 space-y-1 border-l-2 border-primary pl-2" aria-live={streaming ? "polite" : undefined}>
          {stmts.map((st, i) => (
            <div key={i} data-testid="answer-statement">
              <CitedText text={st.text} citations={st.citations} />
              {st.note ? <p className="text-[10px] text-muted-foreground">{st.note}</p> : null}
            </div>
          ))}
        </div>
      ) : notDoc ? (
        <div className="mt-1 border-l-2 border-stage-line pl-2" data-testid="answer-not-documented-text">
          <p className="text-sm text-foreground">{NOT_DOCUMENTED_TEXT}</p>
          {a?.message && a.message !== NOT_DOCUMENTED_TEXT ? <p className="text-[10px] text-muted-foreground">{a.message}</p> : null}
        </div>
      ) : refused ? (
        <div className="mt-1 border-l-2 border-review pl-2" data-testid="answer-refusal">
          <p className="text-sm text-foreground">{a?.message || text}</p>
        </div>
      ) : status === "error" ? (
        <div className="mt-1 border-l-2 border-bad pl-2">
          <p className="text-sm text-foreground">Could not answer, try again</p>
          {a?.message ? <p className="text-[10px] text-muted-foreground">{a.message}</p> : null}
        </div>
      ) : text ? <p className="mt-1 border-l-2 border-primary pl-2 text-sm text-foreground">{indianDates(text)}</p> : null}
      {streaming ? <p className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground" data-testid="answer-streaming">Answering<Dots /></p> : null}
      {quick ? (
        <div className="mt-1.5 flex flex-wrap gap-1" role="group" aria-label="Questions the agent can answer from the records">
          {QUICK_QUESTIONS.map((t) => (
            <button key={t} type="button" onClick={() => onQuick!(t, q.role ?? undefined)} data-testid="quick-question"
              className={cn("rounded-full border border-border px-2.5 py-1 text-xs text-foreground transition hover:bg-accent active:scale-95", ctx.phone && "min-h-11")}>{t}</button>
          ))}
        </div>
      ) : null}
      {nd.length ? (
        <div className="mt-1" data-testid="answer-not-documented">
          <p className="text-xs font-medium text-muted-foreground">Not documented (from the brief)</p>
          <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">{nd.map((x, i) => <li key={i}>{indianDates(x)}</li>)}</ul>
        </div>
      ) : null}
      {refs.length ? (
        <div className="mt-1.5 space-y-1" data-testid="answer-references">
          <p className="text-[11px] font-semibold text-review">Reference text, not about this patient</p>
          {refs.map((r, i) => (
            <div key={i} className="rounded border border-border bg-muted/50 px-2 py-1">
              <p className="text-[11px] font-medium text-muted-foreground">{referenceLine(r)}</p>
              {r.quote ? <p className="text-xs italic text-foreground">"{r.quote}"</p> : null}
            </div>
          ))}
        </div>
      ) : null}
      {q.role && a && cited ? <p className="mt-1 text-[10px] text-muted-foreground" data-testid="sources-line">Sources are on the screen.</p> : null}
      {a || text ? (
        <div className="mt-1 flex items-center gap-1.5">
          <p className="min-w-0 flex-1 text-[10px] text-muted-foreground" data-testid="answer-footer">
            {q.role ? answerFooter(a) : (a?.note ?? "")}{a?.at && !streaming ? ` Answered ${fmtDateTime(a.at)}.` : ""}
          </p>
          {showStop ? (
            <Button size="xs" variant="outline" className={cn(ctx.phone && "min-h-11")} onClick={stop} data-testid="answer-stop"
              aria-label={mayStopAll ? `Stop the ${dept} agent's voice for everyone` : "Stop the agent's voice on this device"} title={mayStopAll ? "Stops the voice for everyone; the text stays" : "Stops the voice on this device; the text stays"}>
              <Square className="size-3" />Stop
            </Button>
          ) : agentVoices && text && !streaming ? <SpeakButton source={{ ref: { kind: "meeting_answer", meeting_id: mid, id: q.id } }} screen="meeting" size="icon-xs" /> : null}
        </div>
      ) : null}
    </li>
  );
}

/** The questions with their answers, newest first (QuestionItem). `onQuick` fills the box with a quick question after a refusal. */
export function QuestionItems({ questions, emptyText = "No questions yet.", testId = "questions-list", onQuick }: { questions: MeetingQuestion[]; emptyText?: string; testId?: string; onQuick?: (text: string, role?: string) => void }) {
  if (!questions.length) return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  return (
    <ol className="space-y-2" data-testid={testId}>
      {[...questions].reverse().map((q) => <QuestionItem key={q.id} q={q} onQuick={onQuick} />)}
    </ol>
  );
}

/** Why I may not ask this agent now, or null: the coordinator closed questions to the agents for members. */
export function agentsClosedFor(ctx: Pick<CallCtx, "canManage" | "state">): string | null {
  return !ctx.canManage && ctx.state.can?.ask_agents === false ? "The MDT Coordinator has closed questions to the agents for now." : null;
}

/** The question box: Textarea `member-q` (or `agent-q-<role>`), the dictation button, Send. `role` routes it to an agent (the
 * placeholder "Ask Radiology about this Case File", the microphone tells the agent it is listening). `mentions` reads "@Radiology" at
 * the start (any of the six department names, any case), picks that agent through `onRole` and strips the mention on send. The box
 * keeps the text when the server refuses it; the reason stands beside it. `text`/`onText` make it controlled (quick questions). */
export function QuestionForm({ role, roleLabel, id = "member-q", text, onText, mentions, onRole }: { role?: string; roleLabel?: string; id?: string; text?: string; onText?: (t: string) => void; mentions?: boolean; onRole?: (role: string | undefined) => void }) {
  const ctx = useCall();
  const { cid, inSession, agents } = ctx;
  const [own, setOwn] = useState("");
  const question = text ?? own;
  const setQuestion = (t: string) => { if (onText) onText(t); else setOwn(t); };
  const [localError, setLocalError] = useState<string | null>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const act = usePanelAction();
  const pending = act.pending === "ask";
  const closed = role ? agentsClosedFor(ctx) : null;
  const change = (t: string) => {
    setQuestion(t);
    setLocalError(null);
    if (!mentions) return;
    const m = parseMention(t);
    if (m && agents.some((x) => x.role === m.role)) onRole?.(m.role);
  };
  const send = async () => {
    let t = question.trim();
    let r = role;
    if (mentions) {
      const m = parseMention(t);
      if (m) {
        if (!agents.some((x) => x.role === m.role)) { setLocalError("That agent is not in this meeting. The coordinator can add it."); return; }
        if (agentsClosedFor(ctx)) { setLocalError(agentsClosedFor(ctx)); return; }
        t = m.rest.trim();
        r = m.role;
        if (t.length < 3) { setLocalError(`Type the question for ${m.name} after the mention.`); return; }
      }
    }
    setLocalError(null);
    if (await act.run("ask", () => ctx.actions.ask(t, r))) setQuestion("");
  };
  const hint = !inSession ? "Questions open when the meeting starts." : !cid ? "Questions open when a case is on the screen." : closed ? closed : roleLabel ? `The ${roleLabel} agent answers from the records and guidelines only.` : "Your question shows on the room screen with your name.";
  const error = localError ?? act.error;
  return (
    <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (question.trim().length >= 3) void send(); }}>
      <label htmlFor={id} className="sr-only">{roleLabel ? `Ask ${roleLabel} about this Case File` : "Type a question"}</label>
      <Textarea ref={questionRef} id={id} value={question} onChange={(e) => change(e.target.value)} className="min-h-16 text-base md:text-base"
        placeholder={roleLabel ? `Ask ${roleLabel} about this Case File` : "Type a question; it shows on the room screen with your name"} maxLength={500} disabled={pending || !inSession || !cid} />
      <div className="flex items-center gap-2">
        {error ? <p role="alert" className="flex-1 text-xs text-bad" data-testid="ask-error">{error}</p> : <span className="flex-1 text-xs text-muted-foreground">{hint}</span>}
        {inSession && cid ? (
          <MicButton target={questionRef} screen="meeting-q" context="question" label={roleLabel ? `Dictate the question for ${roleLabel}` : "Dictate the question"} caseId={cid} className="max-w-[60%] shrink-0"
            hintText={role ? "Heard this. Check it before asking." : undefined}
            onListening={role ? (on) => { void ctx.actions.agentListening(role, on).catch(() => undefined); } : undefined}
            onInsert={(next) => change(next.slice(0, 500))} />
        ) : null}
        <LoadingButton size="sm" type="submit" loading={pending} loadingText="Sending" disabled={question.trim().length < 3 || !inSession || !cid || !!closed} className={cn(ctx.phone && "min-h-11")} data-testid={id === "member-q" ? "send-question" : `send-${id}`}><SendHorizontal className="size-4" />Send</LoadingButton>
      </div>
    </form>
  );
}

// ---- meeting chat helpers (pure; index.ts re-exports them for the bar's badge) ------------------------------------------------

/** The sessionStorage key of my seen mark: the `at` of the newest chat line I had in front of me with the chat tab open. */
export const chatSeenKey = (mid: string) => `tbnik.chat.seen.${mid}`;

export function readChatSeen(mid: string): string | null {
  try { return sessionStorage.getItem(chatSeenKey(mid)); } catch { return null; }
}

export function writeChatSeen(mid: string, at: string): void {
  try { sessionStorage.setItem(chatSeenKey(mid), at); } catch { /* private window: the badge counts again on the next visit */ }
}

/** True when the time `a` is after `b` (ISO strings; compared as text when one does not parse). */
export function isAfter(a: string, b: string): boolean {
  const ta = Date.parse(a), tb = Date.parse(b);
  return Number.isFinite(ta) && Number.isFinite(tb) ? ta > tb : a > b;
}

/** The newest time among the chat lines (the seen mark when the chat tab is open), or null. */
export function newestAt(chat: ChatMessage[] | undefined): string | null {
  let out: string | null = null;
  for (const m of chat ?? []) if (m.at && (!out || isAfter(m.at, out))) out = m.at;
  return out;
}

/** The chat lines of other people newer than the seen mark (all of them when there is no mark yet). */
export function countUnread(chat: ChatMessage[] | undefined, me: string, seen: string | null): number {
  return (chat ?? []).filter((m) => m.by !== me && (!seen || !m.at || isAfter(m.at, seen))).length;
}

/** My unread meeting chat lines (none on the room screen, which never shows the chat). */
export function unreadChat(ctx: Pick<CallCtx, "mid" | "me" | "variant" | "state">): number {
  if (ctx.variant === "room") return 0;
  return countUnread(ctx.state.chat, ctx.me, readChatSeen(ctx.mid));
}

/** Why the chat box is closed, or null when I may chat. */
export function chatClosedReason(s: Pick<MeetingState, "can" | "meeting">): string | null {
  if (s.can?.chat) return null;
  const status = s.meeting?.status;
  return status === "planned" || status === "in_session" ? "Only members admitted to the meeting can chat." : "Chat opens when the meeting is planned or running.";
}

/** The short case chip of a chat line: the patient's initials from the agenda line ("Fatima B., 46 F, ..." gives "FB"), else
 * the case id. Initials only, so the chip never repeats a full name. */
export function caseChipLabel(caseId: string, rows: AgendaRow[]): string {
  const row = rows.find((r) => r.case_id === caseId);
  const name = (row?.patient_line ?? "").split(",")[0].replace(/\([^)]*\)/g, " ").trim();
  const initials = name.split(/\s+/).map((w) => w.replace(/[^A-Za-z]/g, "").charAt(0).toUpperCase()).filter(Boolean).slice(0, 3).join("");
  return initials || caseId;
}

/** The chat lines grouped by day, oldest first, each group headed "Today" or DD/MM/YYYY. */
export function chatDays(chat: ChatMessage[] | undefined, today?: (d: Date) => boolean): Array<{ key: string; label: string; lines: ChatMessage[] }> {
  const out: Array<{ key: string; label: string; lines: ChatMessage[] }> = [];
  for (const m of chat ?? []) {
    const d = m.at ? parseISO(m.at) : null;
    const ok = !!d && isValid(d);
    const key = ok ? format(d!, "yyyy-MM-dd") : "unknown";
    const label = ok ? ((today ?? isToday)(d!) ? "Today" : format(d!, "dd/MM/yyyy")) : "Earlier";
    const last = out[out.length - 1];
    if (last && last.key === key) last.lines.push(m); else out.push({ key, label, lines: [m] });
  }
  return out;
}

/** HH:MM of a chat line. */
export function chatTime(at?: string | null): string {
  if (!at) return "";
  const d = parseISO(at);
  return isValid(d) ? format(d, "HH:mm") : "";
}

const CHAT_MAX = 1000;
const CHAT_COUNTER_FROM = 900;

/** The "Meeting chat" tab: the lines, the New messages pill, and the composer. */
function MeetingChat() {
  const ctx = useCall();
  const { state: s, mid, me, cid, phone } = ctx;
  const lines = s.chat ?? [];
  const rows = [...s.agenda.discussion, ...s.agenda.noting, ...s.agenda.not_ready];
  const days = chatDays(lines);
  const newest = lines.length ? lines[lines.length - 1] : null;
  const mark = newestAt(lines);
  const listRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const lastId = useRef<string | null>(newest?.id ?? null);
  const [pill, setPill] = useState(false);
  const [text, setText] = useState("");
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const act = usePanelAction();
  const pending = act.pending === "chat";
  const closed = chatClosedReason(s) ?? (ctx.actions.chat ? null : "Chat is not available on this server yet.");

  // The chat tab is open: everything here is seen.
  useEffect(() => { if (mark) writeChatSeen(mid, mark); }, [mid, mark]);

  const toBottom = (smooth = false) => {
    const el = listRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    atBottom.current = true;
    setPill(false);
  };
  useLayoutEffect(() => { toBottom(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // A new line: follow it when I am at the bottom (or it is mine); else the New messages pill.
  useLayoutEffect(() => {
    const id = newest?.id ?? null;
    if (id === lastId.current) return;
    lastId.current = id;
    if (!newest) return;
    if (atBottom.current || newest.by === me) toBottom(); else setPill(true);
  }, [newest?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const onScroll = () => {
    const el = listRef.current;
    if (!el) return;
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    if (atBottom.current) setPill(false);
  };

  // The shell's banner announces an action's error (role="alert"); here it stays beside the box, tied to it, in red.
  const send = async () => {
    const t = text.trim();
    if (!t || closed || pending || !ctx.actions.chat) return;
    if (await act.run("chat", () => ctx.actions.chat!(t))) { setText(""); boxRef.current?.focus(); }
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); }
  };

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <div className="relative">
        <div ref={listRef} onScroll={onScroll} role="log" aria-label="Meeting chat" data-testid="chat-list"
          className={cn("scroll-thin overflow-y-auto overscroll-contain pr-1", phone ? "max-h-[42dvh]" : "max-h-[min(52dvh,26rem)]")}>
          {!lines.length ? <p className="py-2 text-sm text-stage-muted">No messages yet. Meeting chat is kept with the meeting record.</p> : (
            days.map((day) => (
              <section key={day.key} aria-label={day.label} className="space-y-1.5 pb-2">
                <h3 className="sticky top-0 z-[1] mx-auto w-fit rounded-full bg-stage-raised px-2 py-0.5 text-[10px] font-medium text-stage-muted">{day.label}</h3>
                <ol className="space-y-1.5">
                  {day.lines.map((m) => {
                    const mine = !!me && m.by === me;
                    const other = m.case_id && m.case_id !== cid ? m.case_id : null;
                    return (
                      <li key={m.id} data-testid="chat-line" data-mine={mine ? "true" : "false"} className={cn("flex", mine ? "justify-end" : "justify-start")}>
                        <div className={cn("max-w-[85%] rounded-lg border px-2.5 py-1.5", mine ? "border-primary/40 bg-primary/15" : "border-stage-line bg-stage-raised")}>
                          <p className={cn("flex flex-wrap items-baseline gap-x-1.5 text-xs", mine && "justify-end")}>
                            <span className="font-semibold text-stage-fg">{mine ? "You" : m.by_name || m.by}</span>
                            {m.at ? <time dateTime={m.at} title={fmtDateTime(m.at)} className="text-[10px] text-stage-muted">{chatTime(m.at)}</time> : null}
                            {other ? <span className="rounded-full border border-stage-line px-1.5 text-[10px] text-stage-muted" title={`Sent while ${other} was on the screen`}>on {caseChipLabel(other, rows)}</span> : null}
                          </p>
                          <p className="whitespace-pre-wrap break-words text-sm text-stage-fg">{m.text}</p>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </section>
            ))
          )}
        </div>
        {pill ? (
          <button type="button" onClick={() => toBottom(true)} data-testid="chat-new-pill" aria-label="New messages: go to the newest" title="Go to the newest message"
            className={cn("absolute bottom-2 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground shadow-md", phone && "min-h-11")}>
            <ArrowDown className="size-3.5" aria-hidden />New messages
          </button>
        ) : null}
      </div>

      <form className="flex flex-col gap-1.5 border-t border-stage-line pt-2" onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <label htmlFor="meeting-chat" className="sr-only">Type a message to the meeting</label>
        <Textarea ref={boxRef} id="meeting-chat" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} maxLength={CHAT_MAX}
          className="min-h-11 text-base md:text-base" placeholder={closed ? "" : "Message the meeting (Enter sends, Shift+Enter for a new line)"}
          disabled={!!closed || pending} aria-invalid={act.error ? true : undefined} aria-describedby={act.error ? "meeting-chat-error meeting-chat-note" : "meeting-chat-note"} />
        <div className="flex items-center gap-2">
          {act.error ? <p id="meeting-chat-error" className="min-w-0 flex-1 text-xs text-bad" data-testid="chat-error">{act.error}</p>
            : closed ? <p className="min-w-0 flex-1 text-xs text-stage-muted">{closed}</p>
            : <span className={cn("min-w-0 flex-1 text-xs", text.length >= CHAT_COUNTER_FROM ? "text-stage-fg" : "text-transparent")} aria-live="polite">{text.length >= CHAT_COUNTER_FROM ? `${text.length} / ${CHAT_MAX}` : ""}</span>}
          {!closed ? <MicButton target={boxRef} screen="meeting-chat" context="note" label="Dictate the message" caseId={cid ?? undefined} className="max-w-[60%] shrink-0" onInsert={(next) => { setText(next.length > CHAT_MAX ? next.slice(0, CHAT_MAX) : next); }} /> : null}
          <LoadingButton size="sm" type="submit" loading={pending} loadingText="Sending" disabled={!!closed || !text.trim()} className={cn(phone && "min-h-11")} data-testid="send-chat"
            aria-label="Send the message" title={closed ?? "Send the message (Enter)"}><SendHorizontal className="size-4" />Send</LoadingButton>
        </div>
        <p id="meeting-chat-note" className="text-[10px] text-stage-muted">Kept with the meeting record; not sent as a notification.</p>
      </form>
    </div>
  );
}

type ChatTab = "questions" | "chat";

/** The tab each meeting's Chat panel showed last (kept while the page lives, so a resize from laptop to phone keeps it). */
const lastTab = new Map<string, ChatTab>();

export function ChatPanel() {
  const ctx = useCall();
  const { state: s, cid, agents } = ctx;
  const room = ctx.variant === "room";
  // Opened with unread chat lines and no question waiting: the chat tab comes first (item 5.3).
  const [tab, setTabState] = useState<ChatTab>(() => (room ? "questions" : unreadChat(ctx) > 0 && unansweredCount(s.questions, cid) === 0 ? "chat" : lastTab.get(ctx.mid) ?? "questions"));
  const setTab = (t: ChatTab) => { lastTab.set(ctx.mid, t); setTabState(t); };
  const shown: ChatTab = room ? "questions" : tab;
  const unread = shown === "chat" ? 0 : unreadChat(ctx);
  const [role, setRole] = useState<string | undefined>(undefined);
  const [draft, setDraft] = useState("");
  const closed = agentsClosedFor(ctx);
  const chosen = closed ? undefined : agents.find((a) => a.role === role);
  const canAsk = !room && s.can?.ask !== false;
  const quick = (t: string, r?: string) => {
    setDraft(t);
    if (r && !closed && agents.some((a) => a.role === r)) setRole(r);
    window.setTimeout(() => document.getElementById("member-q")?.focus(), 0);
  };
  const tabs: Array<{ id: ChatTab; label: string; count?: number }> = [{ id: "questions", label: "Questions to the board" }, { id: "chat", label: "Meeting chat", count: unread }];
  return (
    <div className="flex min-h-0 flex-col gap-3" data-testid="chat-panel-body">
      {!room ? (
      <div role="tablist" aria-label="Chat and questions" className="flex gap-0.5 rounded-lg bg-stage-raised p-0.5">
        {tabs.map((t) => (
          <button key={t.id} type="button" role="tab" id={`chat-tab-${t.id}`} aria-selected={shown === t.id} aria-controls={`chat-body-${t.id}`} onClick={() => setTab(t.id)}
            className={cn("inline-flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors", ctx.phone && "min-h-11", shown === t.id ? "bg-stage-panel text-stage-fg shadow-sm" : "text-stage-muted hover:text-stage-fg")}>
            {t.label}
            {t.count ? <span className="rounded-full bg-primary px-1.5 text-[10px] font-semibold leading-4 text-primary-foreground" data-testid="chat-tab-unread"><span className="sr-only">, unread </span>{t.count}</span> : null}
          </button>
        ))}
      </div>
      ) : null}

      {shown === "questions" ? (
        <div role={room ? undefined : "tabpanel"} id="chat-body-questions" aria-labelledby={room ? undefined : "chat-tab-questions"} className="space-y-3" data-testid="questions-panel">
          <QuestionItems questions={questionsFor(s.questions, cid)} emptyText="No questions on this case yet." onQuick={canAsk ? quick : undefined} />
          {canAsk ? (
            <div className="space-y-1.5">
              {agents.length ? (
                <div className="flex flex-wrap gap-1" role="group" aria-label="Who the question is for">
                  {[{ role: undefined as string | undefined, label: "Ask the board" }, ...agents.map((a) => ({ role: a.role as string | undefined, label: `Ask ${roleName(a.role, agents)}` }))].map((c) => {
                    const off = !!c.role && !!closed;
                    const on = (chosen?.role ?? undefined) === c.role;
                    return (
                      <button key={c.role ?? "board"} type="button" aria-pressed={on} onClick={() => setRole(c.role)} disabled={off} title={off ? closed! : undefined} data-testid="ask-chip" data-role={c.role ?? "board"}
                        className={cn("rounded-full border px-2.5 py-1 text-xs transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-50", ctx.phone && "min-h-11", on ? "border-primary bg-secondary text-secondary-foreground" : "border-stage-line text-stage-muted hover:text-stage-fg")}>
                        {c.label}
                      </button>
                    );
                  })}
                </div>
              ) : null}
              {agents.length ? <p className="text-[10px] text-stage-muted" data-testid="mention-hint">{closed ?? "Type @ and a department to ask one agent, for example @Radiology"}</p> : null}
              <QuestionForm role={chosen?.role} roleLabel={chosen ? roleName(chosen.role, agents) : undefined} text={draft} onText={setDraft} mentions={!!agents.length} onRole={setRole} />
              {chosen ? <p className="text-[10px] text-muted-foreground">AI agent, support only: answers from the records and guidelines; never a decision; not a member of the board.</p> : null}
            </div>
          ) : null}
        </div>
      ) : (
        <div role="tabpanel" id="chat-body-chat" aria-labelledby="chat-tab-chat" data-testid="meeting-chat-panel">
          <MeetingChat />
        </div>
      )}
    </div>
  );
}
