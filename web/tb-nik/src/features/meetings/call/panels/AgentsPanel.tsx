// The Agents panel of the call (night-v3 5.1, owner decision D2, research/04 section 6.9): one card per AI agent standing in for an
// absent board head, with its true state (the server names it), the questions already asked to it on this Case File with their
// answers, and an Ask box. Agents answer from the records and guidelines only, never a decision, and are not members of the board.
// Adding or removing an agent comes with Phase 6.
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Bot } from "lucide-react";
import type { AgentInfo } from "@/lib/live";
import { cn } from "@/lib/utils";
import { useCall } from "../context";
import { AGENT_STATE_WORD } from "../types";
import { QuestionForm, QuestionItems, questionsFor } from "./ChatPanel";

/** The states in which an agent is working on a question (the Agents button's count). */
export const AGENT_BUSY = new Set(["thinking", "answering"]);

export function busyAgents(agents: AgentInfo[] | undefined): number {
  return (agents ?? []).filter((a) => AGENT_BUSY.has(a.state)).length;
}

const RING: Record<string, string> = { ready: "border-ok", listening: "border-indigo", reading_question: "border-indigo", reading: "border-indigo", thinking: "border-review", answering: "border-primary", speaking: "border-primary" };

function Dots() {
  return <span className="ml-0.5 inline-flex gap-0.5" aria-hidden>{[0, 1, 2].map((i) => <motion.span key={i} className="size-1 rounded-full bg-current" animate={{ opacity: [0.2, 1, 0.2] }} transition={{ repeat: Infinity, duration: 1, delay: i * 0.2 }} />)}</span>;
}

function AgentCard({ agent }: { agent: AgentInfo }) {
  const { state: s, cid } = useCall();
  const reduce = useReducedMotion();
  const key = AGENT_STATE_WORD[agent.state] ? agent.state : "ready";
  const busy = key !== "ready";
  const asked = questionsFor(s.questions, cid, agent.role);
  return (
    <li className={cn("space-y-2 rounded-lg border-2 border-dashed bg-card p-3", RING[key] ?? "border-ok")} data-role={agent.role} data-agent-state={key}>
      <div className="flex items-center gap-3">
        <motion.span animate={reduce ? {} : busy ? { scale: [1, 1.08, 1] } : { scale: 1 }} transition={busy ? { repeat: Infinity, duration: key === "thinking" ? 1.2 : 0.8 } : {}} className="grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-secondary-foreground" aria-hidden>
          <Bot className="size-5" />
        </motion.span>
        <div className="min-w-0">
          <p className="text-sm font-medium leading-tight text-foreground">{agent.label}{agent.department_name && agent.department_name !== agent.label ? <span className="font-normal text-muted-foreground"> · {agent.department_name}</span> : null}</p>
          <p className="text-xs text-muted-foreground">Standing in for the absent head</p>
          <p className="text-xs text-muted-foreground" role="status" aria-live="polite">
            <AnimatePresence mode="wait" initial={false}>
              <motion.span key={key} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} className="inline-flex items-center gap-1">
                {AGENT_STATE_WORD[key]}{busy ? <Dots /> : null}
              </motion.span>
            </AnimatePresence>
          </p>
        </div>
      </div>
      {agent.note ? <p className="text-[10px] text-muted-foreground">{agent.note}</p> : null}
      <QuestionItems questions={asked} emptyText={`No questions to ${agent.label} on this case yet.`} testId="agent-questions" />
      {s.can?.ask !== false ? <QuestionForm role={agent.role} roleLabel={agent.label} id={`agent-q-${agent.role}`} /> : null}
    </li>
  );
}

export function AgentsPanel() {
  const { agents, variant } = useCall();
  return (
    <div className="space-y-3">
      <p className="rounded-md bg-muted px-2 py-1.5 text-xs text-muted-foreground">AI agents, support only: answers from the records and guidelines; never a decision; not members of the board</p>
      {agents.length === 0 ? <p className="text-sm text-muted-foreground">Every board head is present; no agent is standing in.</p> : (
        <ul className="space-y-3" aria-label="AI agents standing in">
          {agents.map((a) => (variant === "room" ? <li key={a.role} className="text-sm">{a.label}: {AGENT_STATE_WORD[a.state] ?? "Ready"}</li> : <AgentCard key={a.role} agent={a} />))}
        </ul>
      )}
    </div>
  );
}
