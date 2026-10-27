// The Chat panel of the call (night-v3 5.1, research/04 section 6.9): two tabs. "Questions to the board" is today's questions list
// with the ask box (a role chip row picks "Ask the board" or one of the agents standing in); an agent's answer shows its text, its
// sources as quote chips, the time, and Read aloud when agent voices are on. "Meeting chat" comes with item 5.3; the tab is kept
// so the layout is final.
import { useRef, useState } from "react";
import { FileText, SendHorizontal } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { SpeakButton } from "@/components/SpeakButton";
import { answerText, type MeetingQuestion } from "@/lib/live";
import { LoadingButton, fmtDateTime, indianDates, niceTitle } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { usePanelAction } from "../../components/People";
import { useCall } from "../context";

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

type ChatTab = "questions" | "chat";

export function ChatPanel() {
  const ctx = useCall();
  const { state: s, cid, agents } = ctx;
  const [tab, setTab] = useState<ChatTab>("questions");
  const [role, setRole] = useState<string | undefined>(undefined);
  const chosen = agents.find((a) => a.role === role);
  const canAsk = ctx.variant !== "room" && s.can?.ask !== false;
  const tabs: Array<{ id: ChatTab; label: string }> = [{ id: "questions", label: "Questions to the board" }, { id: "chat", label: "Meeting chat" }];
  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div role="tablist" aria-label="Chat and questions" className="flex gap-0.5 rounded-lg bg-stage-raised p-0.5">
        {tabs.map((t) => (
          <button key={t.id} type="button" role="tab" id={`chat-tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`chat-body-${t.id}`} onClick={() => setTab(t.id)}
            className={cn("flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors", ctx.phone && "min-h-11", tab === t.id ? "bg-stage-panel text-stage-fg shadow-sm" : "text-stage-muted hover:text-stage-fg")}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "questions" ? (
        <div role="tabpanel" id="chat-body-questions" aria-labelledby="chat-tab-questions" className="space-y-3" data-testid="questions-panel">
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
        <div role="tabpanel" id="chat-body-chat" aria-labelledby="chat-tab-chat">
          <p className="text-sm text-stage-muted">Meeting chat comes with the next update.</p>
        </div>
      )}
    </div>
  );
}
