// The Agents panel of the call (night-v3 5.1 and 6.1, owner decision D2, research/05 sections 6.1 to 6.9): first "Agents in this
// meeting", the six specialty agents as rows (the coordinator switches each in or out for the Case File on the floor, with the reason
// beside the switch; a member reads the same rows as words), and the coordinator's switch "Members can ask the agents"; then one card
// per agent in the meeting with its title, its true state (the server names it), the questions already asked to it on this Case File
// with their answers, and an Ask box. Agents answer from the records and guidelines only, never a decision, and are not members of
// the board: they never appear among the people and never count. Item 6.2: each card shows the agent's points from the records from
// the start of the case (AgentPoints.tsx) and "Present your points".
import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Bot } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import type { AgentInfo, MeetingState } from "@/lib/live";
import { cn } from "@/lib/utils";
import { PanelSection, usePanelAction } from "../../components/People";
import { Dots } from "../../components/shared";
import { useCall } from "../context";
import { agentBusy, agentDept, agentStateKey, agentStateWord, agentTitle } from "../Strip";
import { AGENT_ROLES, AgentPoints } from "./AgentPoints";
import { QuestionForm, QuestionItems, questionsFor } from "./ChatPanel";

/** The states in which an agent is working on a question (the Agents button's count). */
export const AGENT_BUSY = new Set(["thinking", "answering", "speaking"]);

export function busyAgents(agents: AgentInfo[] | undefined): number {
  return (agents ?? []).filter((a) => AGENT_BUSY.has(a.state)).length;
}

/** The six specialty agents (AgentPoints.tsx, shared with the Questions tab's @mention). */
export { AGENT_ROLES };

/** Why an agent is in the meeting: the server's reason ("Head absent", "Marked absent", "Added by <name>"), else from its flags. */
export function agentReason(a: Pick<AgentInfo, "reason" | "added" | "added_by_name">): string {
  if (a.reason) return a.reason;
  if (a.added) return a.added_by_name ? `Added by ${a.added_by_name}` : "Added by the MDT Coordinator";
  return "Head absent";
}

/** True when the head of this department is present for the Case File on the floor (the quorum line, else the attendance). */
export function headPresent(s: Pick<MeetingState, "quorum" | "attendance">, role: string): boolean {
  const h = (s.quorum?.heads ?? []).find((x) => (x.role ?? x.id) === role);
  if (h) return !!h.present;
  return (s.attendance ?? []).some((a) => !!a.head && a.department === role && (a.status === "present" || a.status === "remote"));
}

/** The words of one roster row: for an agent in the meeting its reason; else "Head present" or "Not in this meeting". */
export function rosterWord(agent: AgentInfo | undefined, present: boolean): string {
  if (agent) return agentReason(agent);
  return present ? "Head present" : "Not in this meeting";
}

/** A member's reading of a roster row: "In this meeting: Head absent", "Not in this meeting: Head present", "Not in this meeting". */
export function rosterSentence(agent: AgentInfo | undefined, present: boolean): string {
  if (agent) return `In this meeting: ${agentReason(agent)}`;
  return present ? "Not in this meeting: Head present" : "Not in this meeting";
}


const RING: Record<string, string> = {
  ready: "border-ok", preparing: "border-stage-muted", listening: "border-indigo", reading_question: "border-indigo", reading: "border-indigo",
  thinking: "border-review", answering: "border-primary", speaking: "border-primary", error: "border-bad",
};

/** "Agents in this meeting": the six roles; the coordinator's switches with the reason beside them, a member's rows in words. */
function AgentRoster() {
  const ctx = useCall();
  const { state: s, agents, cid, canManage } = ctx;
  const act = usePanelAction();
  const [want, setWant] = useState<Record<string, boolean>>({});
  const [askWant, setAskWant] = useState<boolean | null>(null);
  const manage = canManage && ctx.variant !== "room";
  const tap = ctx.phone ? "min-h-11" : "min-h-9";
  const byRole = new Map(agents.map((a) => [a.role, a]));
  const toggle = async (role: string, on: boolean) => {
    setWant((w) => ({ ...w, [role]: on }));
    await act.run(`agent:${role}`, () => ctx.actions.setAgent(role, on));
    setWant((w) => { const { [role]: _drop, ...rest } = w; void _drop; return rest; });
  };
  const askOn = askWant ?? s.can?.ask_agents !== false;
  const setAsk = async (on: boolean) => {
    setAskWant(on);
    await act.run("agents-ask", () => ctx.actions.setAgentsAsk(on));
    setAskWant(null);
  };
  return (
    <PanelSection title="Agents in this meeting" count={agents.length} id="ap-roster">
      {!cid ? <p className="pb-1 text-xs text-stage-muted">The agents are set for the Case File on the screen. They join when a case comes up.</p> : null}
      <ul className="space-y-0.5" data-testid="agent-roster">
        {AGENT_ROLES.map(({ role, name }) => {
          const agent = byRole.get(role);
          const present = headPresent(s, role);
          const on = want[role] ?? !!agent;
          const key = agentStateKey(agent?.state);
          const working = !!agent && agentBusy(key) && key !== "preparing";
          const word = agent ? agentStateWord(key, agent.by_name) : "";
          const id = `ap-switch-${role}`;
          return (
            <li key={role} className={cn("flex items-center gap-2.5 px-1 py-1", tap)} data-role={role} data-on={on ? "true" : "false"} data-testid="agent-roster-row">
              <span className={cn("grid size-8 shrink-0 place-items-center rounded-full border border-dashed text-stage-fg", on ? "border-stage-muted bg-stage-raised" : "border-stage-line opacity-60")} aria-hidden><Bot className="size-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-stage-fg">{name}</span>
                <span className="block truncate text-xs text-stage-muted" data-testid="agent-reason">{manage ? rosterWord(agent, present) : rosterSentence(agent, present)}</span>
                {working ? <span className="block truncate text-xs text-stage-fg" data-testid="agent-roster-state">{word}</span> : null}
              </span>
              {manage ? (
                <label htmlFor={id} className={cn("flex shrink-0 cursor-pointer items-center gap-2 text-xs text-stage-muted", tap)}>
                  <span><span className="sr-only">{name}: </span>In this meeting</span>
                  <Switch id={id} checked={on} disabled={!cid || act.pending === `agent:${role}`} onCheckedChange={(v) => void toggle(role, v)} data-testid="agent-switch" />
                </label>
              ) : null}
            </li>
          );
        })}
      </ul>
      {manage ? (
        <div className="mt-2 flex items-center gap-2.5 border-t border-stage-line px-1 pt-2">
          <span className="min-w-0 flex-1">
            <label htmlFor="ap-members-ask" className="block cursor-pointer text-sm font-medium text-stage-fg">Members can ask the agents</label>
            <span className="block text-xs text-stage-muted">{askOn ? "Every admitted member can ask." : "Only the MDT Coordinator can ask for now."}</span>
          </span>
          <Switch id="ap-members-ask" checked={askOn} disabled={act.pending === "agents-ask"} onCheckedChange={(v) => void setAsk(v)} className={cn(ctx.phone && "my-3")} data-testid="agents-ask-switch" />
        </div>
      ) : s.can?.ask_agents === false ? <p className="mt-2 text-xs text-stage-muted" data-testid="agents-ask-closed">The MDT Coordinator has closed questions to the agents for now.</p> : null}
      {act.error ? <p role="alert" className="mt-1 text-xs text-bad">{act.error}</p> : null}
    </PanelSection>
  );
}

function AgentCard({ agent }: { agent: AgentInfo }) {
  const { state: s, cid, canManage } = useCall();
  const reduce = useReducedMotion();
  const key = agentStateKey(agent.state);
  const word = agentStateWord(key, agent.by_name);
  const busy = agentBusy(key);
  const asked = questionsFor(s.questions, cid, agent.role);
  const title = agentTitle(agent);
  const dept = agentDept(agent);
  const mayAsk = s.can?.ask !== false && (canManage || s.can?.ask_agents !== false);
  const closed = s.can?.ask !== false && !mayAsk;
  const [draft, setDraft] = useState("");
  const quick = (t: string) => { setDraft(t); window.setTimeout(() => document.getElementById(`agent-q-${agent.role}`)?.focus(), 0); };
  return (
    <li className={cn("space-y-2 rounded-lg border-2 border-dashed bg-card p-3", RING[key] ?? "border-ok")} data-role={agent.role} data-agent-state={key} data-testid="agent-card">
      <div className="flex items-center gap-3">
        <motion.span animate={reduce ? {} : busy ? { scale: [1, 1.08, 1] } : { scale: 1 }} transition={busy ? { repeat: Infinity, duration: key === "thinking" || key === "preparing" ? 1.2 : 0.8 } : {}} className="grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-secondary-foreground" aria-hidden>
          <Bot className="size-5" />
        </motion.span>
        <div className="min-w-0">
          <p className="text-sm font-medium leading-tight text-foreground">{title}</p>
          <p className="text-xs text-muted-foreground">AI agent, support only. {agentReason(agent)}.</p>
          <p className={cn("text-xs", key === "error" ? "text-bad" : "text-muted-foreground")} role="status" aria-live="polite" data-testid="agent-card-state">
            <AnimatePresence mode="wait" initial={false}>
              <motion.span key={`${key}:${word}`} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} className="inline-flex items-center gap-1">
                {word}{busy ? <Dots /> : null}
              </motion.span>
            </AnimatePresence>
          </p>
        </div>
      </div>
      <p className="text-[10px] text-muted-foreground">Reads this Case File and the guidelines. Does not decide or advise. Not a member of the board.</p>
      <AgentPoints agent={agent} />
      <QuestionItems questions={asked} emptyText={`No questions to ${dept} on this case yet.`} testId="agent-questions" onQuick={mayAsk ? quick : undefined} />
      {mayAsk ? <QuestionForm role={agent.role} roleLabel={dept} id={`agent-q-${agent.role}`} text={draft} onText={setDraft} /> : null}
      {closed ? <p className="text-xs text-muted-foreground">The MDT Coordinator has closed questions to the agents for now.</p> : null}
    </li>
  );
}

export function AgentsPanel() {
  const { agents, variant } = useCall();
  if (variant === "room") {
    return (
      <div className="space-y-3">
        <p className="rounded-md bg-muted px-2 py-1.5 text-xs text-muted-foreground">AI agents, support only: answers from the records and guidelines; never a decision; not members of the board</p>
        {agents.length === 0 ? <p className="text-sm text-muted-foreground">No AI agent is in this meeting for this case.</p> : (
          <ul className="space-y-1" aria-label="AI agents in this meeting">
            {agents.map((a) => <li key={a.role} className="text-sm" data-role={a.role}>{agentTitle(a)}: {agentStateWord(agentStateKey(a.state), a.by_name)}</li>)}
          </ul>
        )}
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <p className="rounded-md bg-muted px-2 py-1.5 text-xs text-muted-foreground">AI agents, support only: answers from the records and guidelines; never a decision; not members of the board</p>
      <AgentRoster />
      {agents.length === 0 ? <p className="text-sm text-muted-foreground">No AI agent is in this meeting for this case.</p> : (
        <ul className="space-y-3" aria-label="AI agents in this meeting">
          {agents.map((a) => <AgentCard key={a.role} agent={a} />)}
        </ul>
      )}
    </div>
  );
}
