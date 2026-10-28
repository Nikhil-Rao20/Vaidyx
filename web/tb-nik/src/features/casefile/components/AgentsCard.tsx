// The Overview's "Specialty agents" card (night-v3 item 6.5, owner decision D2): the six AI agents in their order, each a chip with the
// Bot mark, the name and its count badges (points for review, not documented, questions on the shared thread); while a brief is
// prepared in the background a spinner and "Reading the records" (useHelpers polls every 4 s until it is done). A chip opens that agent
// in the Summary section (?item=<role>). "Prepare all" and a chip's "Prepare" for those who may prepare a brief.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { prepareHelper } from "../api";
import type { CaseFile } from "../types";
import { AGENT_LABEL, AgentBadges, AgentState, NAMES, agentName, canPrepareAll, usePrepareAll, useHelpers } from "./HelpersPanel";
import { LoadingButton, SkeletonLines, errorText } from "./common";

export function AgentsCard({ caseId, cf, onOpen }: { caseId: string; cf: CaseFile | null; onOpen: (role: string) => void }) {
  const { helpers, notBuilt, isLoading, error } = useHelpers(caseId, cf, true);
  const qc = useQueryClient();
  const all = usePrepareAll(caseId);
  const one = useMutation({
    mutationFn: (role: string) => prepareHelper(caseId, role),
    onSettled: () => qc.invalidateQueries({ queryKey: ["helpers", caseId] }),
  });
  // A reader the server does not show the agents to sees no card (the Summary says why).
  if (error) return null;
  if (!isLoading && !helpers.length) return null;
  const failed = all.error ?? one.error;
  return (
    <section className="surface overflow-hidden" aria-labelledby="h-agents" data-testid="overview-agents">
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
        <Bot className="size-4 text-brand" aria-hidden />
        <h2 id="h-agents" className="flex-1 text-[15px]">Specialty agents</h2>
        {canPrepareAll(helpers, notBuilt) ? <LoadingButton size="sm" variant="outline" loading={all.isPending} loadingText="Starting" onClick={() => all.mutate()} data-testid="overview-prepare-all">Prepare all</LoadingButton> : null}
      </header>
      <div className="space-y-2 px-4 py-3">
        <p className="text-sm text-muted-foreground">AI agents, support only: they read this Case File and the guidelines, never decide or advise.</p>
        {failed ? <p role="alert" className="text-xs text-bad">{errorText(failed)}</p> : null}
        {isLoading ? <SkeletonLines n={3} /> : (
          <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {helpers.map((h) => {
              const name = NAMES[h.role] ?? agentName(h);
              const canPrepare = h.brief.status === "none" && h.prepare_allowed && !notBuilt;
              return (
                <li key={h.role} className="flex items-stretch rounded-md border border-border bg-card transition-colors hover:border-primary/60" data-testid={`agent-chip-${h.role}`} data-state={h.brief.status}>
                  <button type="button" onClick={() => onOpen(h.role)} className="min-h-11 min-w-0 flex-1 rounded-md px-3 py-2 text-left focus-visible:outline-2">
                    <span className="flex items-center gap-2">
                      <Bot className="size-4 shrink-0 text-brand" aria-hidden />
                      <span className="truncate font-medium text-foreground">{name}<span className="sr-only">, AI agent: open its brief and questions</span></span>
                    </span>
                    <span className="mt-1.5 flex flex-wrap items-center gap-1">
                      <AgentState h={h} />
                      <AgentBadges h={h} />
                    </span>
                  </button>
                  {canPrepare ? (
                    <span className="flex items-center pr-2">
                      <LoadingButton size="sm" variant="outline" loading={one.isPending && one.variables === h.role} loadingText="Starting" onClick={() => one.mutate(h.role)} aria-label={`Prepare the ${name} brief`}>Prepare</LoadingButton>
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
        <p className="text-xs text-muted-foreground">{AGENT_LABEL}. Not members of the board. Every point keeps the report line it came from.</p>
      </div>
    </section>
  );
}
