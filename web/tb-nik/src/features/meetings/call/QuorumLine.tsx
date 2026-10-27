// The quorum line (night-v3 5.4, research/04 section 6.14): who of the board's heads is present as a person, who is not here and the
// AI agents standing in (listed apart, support only, never counted), and the PM-JAY composition. The NHA manual says multidisciplinary
// decisions are "advised", so the line says "PM-JAY advises", never "requires"; it states who is present, not whether a decision is
// valid, so it has no colour alarm (a neutral "1 of 3" chip). Compact at the foot of the agenda rail, full in the top bar's popover,
// big on the room screen.
import type { QuorumInfo } from "@/lib/live";
import { useCall } from "./context";
import { cn } from "@/lib/utils";

/** The fixed PM-JAY words (the server's note says the same); "advises", never "requires". */
export const PMJAY_LEAD = "PM-JAY advises Surgical, Radiation and Medical Oncology";

type Head = QuorumInfo["heads"][number];

function list(names: string[]): string {
  return names.join(", ");
}

export interface QuorumSentences {
  /** "Heads present 2 of 5: Radiology (Shanthi Raman), Medical Oncology (Thomas Joseph)." */
  present: string;
  /** "Not here: Surgical Oncology, Pathology (AI agents standing in: Pathology; support only, never counted)." or "" */
  absent: string;
  /** "PM-JAY advises Surgical, Radiation and Medical Oncology: 1 of 3 present as people." or "" */
  pmjay: string;
  /** The parts the chips draw: "2 of 5" and "1 of 3". */
  headsCount: string;
  pmjayCount: string;
}

/** The three sentences of the quorum line. `withNames` adds the person beside each head present. `agents` are department names of
 * the AI agents standing in (the server's list; the call's agents when the server sent none). */
export function quorumSentences(q: QuorumInfo, agents: string[] = q.agents ?? [], withNames = true): QuorumSentences {
  const heads: Head[] = q.heads ?? [];
  const here = heads.filter((h) => h.present);
  const away = heads.filter((h) => !h.present);
  const total = q.total ?? heads.length;
  const count = q.present ?? here.length;
  const headsCount = `${count} of ${total}`;
  const names = here.map((h) => (withNames && h.by ? `${h.name} (${h.by})` : h.name));
  const present = `Heads present ${headsCount}${names.length ? `: ${list(names)}` : ""}.`;
  const agentWords = agents.length ? `AI agent${agents.length === 1 ? "" : "s"} standing in: ${list(agents)}; support only, never counted` : "";
  let absent = "";
  if (away.length) absent = `Not here: ${list(away.map((h) => h.name))}${agentWords ? ` (${agentWords})` : ""}.`;
  else if (agentWords) absent = `Every head is here. ${agentWords.charAt(0).toUpperCase()}${agentWords.slice(1)}.`;
  else if (total) absent = "Every head is here.";
  const pm = q.pmjay;
  const pmjayCount = pm ? `${pm.present} of ${pm.total}` : "";
  const pmjay = pm ? `${PMJAY_LEAD}: ${pmjayCount} present as people.` : "";
  return { present, absent, pmjay, headsCount, pmjayCount };
}

export function QuorumLine({ compact, big }: { compact?: boolean; big?: boolean }) {
  const c = useCall();
  const q = c.state.quorum;
  if (!q) return null;
  const agents = q.agents?.length ? q.agents : c.agents.filter((a) => a.standing_in !== false).map((a) => a.department_name || a.label);
  const t = quorumSentences(q, agents, !compact);
  const full = quorumSentences(q, agents, true);
  const chip = cn("inline-flex items-center rounded-full bg-secondary px-1.5 py-px align-baseline font-medium tabular-nums text-secondary-foreground", big ? "text-sm" : compact ? "text-[10px]" : "text-xs");
  return (
    <div className={cn("space-y-1 text-muted-foreground", compact ? "text-[11px] leading-snug" : big ? "text-lg leading-snug" : "text-sm")} data-testid="quorum-line" title={compact ? [full.present, full.absent, full.pmjay].filter(Boolean).join(" ") : undefined}>
      <p data-part="heads"><span className="font-medium text-foreground">Heads present</span>{t.present.slice("Heads present".length)}</p>
      {t.absent ? <p data-part="absent">{t.absent}</p> : null}
      {t.pmjay ? (
        <p data-part="pmjay">{PMJAY_LEAD}:{" "}<span className={chip}>{t.pmjayCount}</span> present as people.</p>
      ) : null}
    </div>
  );
}
