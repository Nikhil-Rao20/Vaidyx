// The Chat panel of the call (night-v3 5.1, research/04 section 6.9): two tabs. "Questions to the board" is today's questions list
// with the ask box (a role chip row picks "Ask the board" or one of the agents standing in); an agent's answer shows its text, its
// sources as quote chips, the time, and Read aloud when agent voices are on. "Meeting chat" (item 5.3, research/04 section 6.9) is
// the text chat of the members admitted to the meeting: kept with the meeting record, apart from the questions to the agents, never
// pushed as a notification (owner decision D5). The room screen shows the questions only.
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { format, isToday, isValid, parseISO } from "date-fns";
import { ArrowDown, FileText, SendHorizontal } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { SpeakButton } from "@/components/SpeakButton";
import { answerText, type AgendaRow, type ChatMessage, type MeetingQuestion, type MeetingState } from "@/lib/live";
import { LoadingButton, fmtDateTime, indianDates, niceTitle } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { usePanelAction } from "../../components/People";
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

/** The questions with their answers, newest first: the text, who asked and when, the agent's statements with their sources as quote
 * chips, the answer's time and a Read aloud button (agent voices on). The same look as QuestionsList (components/shared.tsx). */
export function QuestionItems({ questions, emptyText = "No questions yet.", testId = "questions-list" }: { questions: MeetingQuestion[]; emptyText?: string; testId?: string }) {
  const { mid, agentVoices } = useCall();
  if (!questions.length) return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  return (
    <ol className="space-y-2" data-testid={testId}>
      {[...questions].reverse().map((q) => {
        const a = q.answer && typeof q.answer === "object" ? q.answer : null;
        const text = answerText(q);
        const waiting = !q.answer && !!q.role;
        const who = q.agent_label ?? (q.role ? q.role.replace(/_/g, " ") : "");
        return (
          <li key={q.id} className="rounded-md border border-border bg-card p-2">
            <p className="text-sm font-medium text-foreground">{q.text}</p>
            <p className="text-xs text-muted-foreground">{q.by_name}{who ? `, to the ${who} agent` : ""}{q.at ? ` · ${fmtDateTime(q.at)}` : ""}</p>
            {a && (a.statements ?? []).length ? (
              <div className="mt-1 space-y-1 border-l-2 border-primary pl-2 text-sm">
                {a.statements!.map((st, i) => (
                  <p key={i} className="text-foreground">
                    {indianDates(st.text)}
                    {(st.citations ?? []).map((c, j) => {
                      const page = typeof c.page === "number" ? ` p. ${c.page + 1}` : "";
                      return <span key={j} className="quote-chip ml-1 align-middle" title={c.quote ? `"${c.quote}"` : undefined}><FileText className="size-3" aria-hidden />{niceTitle(c.doc_title) || "record"}{page}</span>;
                    })}
                  </p>
                ))}
              </div>
            ) : text ? <p className="mt-1 border-l-2 border-primary pl-2 text-sm text-foreground">{text}</p> : null}
            {a?.status === "not_documented" ? <p className="text-xs text-muted-foreground">Not documented in the records.</p> : null}
            {a || text ? (
              <div className="mt-1 flex items-center gap-1.5">
                <p className="min-w-0 flex-1 text-[10px] text-muted-foreground">{a?.note ?? "From the records only; the agent is not a member of the board."}{a?.at ? ` Answered ${fmtDateTime(a.at)}.` : ""}</p>
                {agentVoices && text ? <SpeakButton source={{ ref: { kind: "meeting_answer", meeting_id: mid, id: q.id } }} screen="meeting" size="icon-xs" /> : null}
              </div>
            ) : null}
            {waiting ? <p className="text-xs italic text-muted-foreground">The agent is reading the records</p> : null}
          </li>
        );
      })}
    </ol>
  );
}

/** The question box (the member view's, as it was): Textarea `member-q`, the dictation button, Send; `role` routes it to an agent. */
export function QuestionForm({ role, roleLabel, id = "member-q" }: { role?: string; roleLabel?: string; id?: string }) {
  const ctx = useCall();
  const { cid, inSession } = ctx;
  const [question, setQuestion] = useState("");
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const act = usePanelAction();
  const pending = act.pending === "ask";
  const send = async () => { if (await act.run("ask", () => ctx.actions.ask(question.trim(), role))) setQuestion(""); };
  const hint = !inSession ? "Questions open when the meeting starts." : !cid ? "Questions open when a case is on the screen." : roleLabel ? `The ${roleLabel} agent answers from the records only.` : "The stand-in answers from the records only.";
  return (
    <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (question.trim().length >= 3) void send(); }}>
      <label htmlFor={id} className="sr-only">{roleLabel ? `Type a question for ${roleLabel}` : "Type a question"}</label>
      <Textarea ref={questionRef} id={id} value={question} onChange={(e) => setQuestion(e.target.value)} className="min-h-16 text-sm" placeholder="Type a question; it shows on the room screen with your name" maxLength={500} disabled={pending || !inSession || !cid} />
      <div className="flex items-center gap-2">
        {act.error ? <p role="alert" className="flex-1 text-xs text-bad">{act.error}</p> : <span className="flex-1 text-xs text-muted-foreground">{hint}</span>}
        {inSession && cid ? <MicButton target={questionRef} screen="meeting-q" context="question" label="Dictate the question" caseId={cid} className="max-w-[60%] shrink-0" onInsert={(next) => { if (next.length > 500) setQuestion(next.slice(0, 500)); }} /> : null}
        <LoadingButton size="sm" type="submit" loading={pending} loadingText="Sending" disabled={question.trim().length < 3 || !inSession || !cid} className={cn(ctx.phone && "min-h-11")} data-testid={id === "member-q" ? "send-question" : undefined}><SendHorizontal className="size-4" />Send</LoadingButton>
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
  const chosen = agents.find((a) => a.role === role);
  const canAsk = !room && s.can?.ask !== false;
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
          <QuestionItems questions={questionsFor(s.questions, cid)} emptyText="No questions on this case yet." />
          {canAsk ? (
            <div className="space-y-1.5">
              {agents.length ? (
                <div className="flex flex-wrap gap-1" role="group" aria-label="Who the question is for">
                  {[{ role: undefined as string | undefined, label: "Ask the board" }, ...agents.map((a) => ({ role: a.role as string | undefined, label: `Ask ${a.label}` }))].map((c) => (
                    <button key={c.role ?? "board"} type="button" aria-pressed={role === c.role} onClick={() => setRole(c.role)}
                      className={cn("rounded-full border px-2.5 py-1 text-xs transition active:scale-95", ctx.phone && "min-h-11", role === c.role ? "border-primary bg-secondary text-secondary-foreground" : "border-stage-line text-stage-muted hover:text-stage-fg")}>
                      {c.label}
                    </button>
                  ))}
                </div>
              ) : null}
              <QuestionForm role={chosen?.role} roleLabel={chosen?.label} />
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
