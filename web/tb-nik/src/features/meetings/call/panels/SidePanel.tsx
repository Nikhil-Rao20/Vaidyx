// The one side panel of the call (night-v3 5.1, research/04 section 6.9): People, Chat and questions, Agenda, Case, Agents or
// Decision, one at a time. On a laptop it slides in on the right of the stage (22 rem; the Decision panel 26 rem, for its six step
// tabs); on a phone it is a bottom sheet, 85 % high,
// with a handle and a visible Close. Esc closes it (the sheet by itself; on a laptop the shell's shortcut). The body follows the
// stage's (light) theme. The badge and title helpers here feed the bar's panel buttons.
import { useRef } from "react";
import { Bot, ClipboardList, FileText, ListOrdered, MessageSquareText, Users, X, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { StagePanel } from "../../components/Stage";
import { useCall } from "../context";
import type { CallCtx, PanelKind } from "../types";
import { AgendaPanel } from "./AgendaPanel";
import { AgentsPanel, busyAgents } from "./AgentsPanel";
import { CasePanel } from "./CasePanel";
import { ChatPanel, unansweredCount } from "./ChatPanel";
import { DecisionPanel } from "./DecisionPanel";
import { PeoplePanel } from "./PeoplePanel";

type Kind = Exclude<PanelKind, null>;

export const PANEL_ICONS: Record<Kind, LucideIcon> = {
  people: Users,
  chat: MessageSquareText,
  agenda: ListOrdered,
  case: FileText,
  agents: Bot,
  decision: ClipboardList,
};

/** The laptop width of a panel: the Decision panel is wider so its six step tabs are not cut. */
export function panelWidth(kind: PanelKind): string {
  return kind === "decision" ? "w-[26rem]" : "w-[22rem]";
}

/** The words of each panel's button and the screen reader's description of the sheet. */
export const PANEL_WORD: Record<Kind, { label: string; about: string }> = {
  people: { label: "People", about: "Who is in the room, remote and waiting, and the AI agents standing in." },
  chat: { label: "Chat", about: "Questions to the board and to the AI agents standing in." },
  agenda: { label: "Agenda", about: "The Case Files of this meeting in order." },
  case: { label: "Case", about: "The slides, records and images of the Case File on the screen." },
  agents: { label: "Agents", about: "The AI agents standing in for absent heads: support only, never a decision." },
  decision: { label: "Decision", about: "The decision record of the Case File on the screen, and the cards." },
};

type BadgeCtx = Pick<CallCtx, "state" | "cid" | "canManage" | "hands" | "agents">;

/** The count on a panel's button: People, the waiting people for the coordinator, else the raised hands; Chat, the questions
 * still unanswered on this Case File; Agents, the agents working on a question; the others none (0). */
export function panelBadge(kind: PanelKind, ctx: BadgeCtx): number | undefined {
  switch (kind) {
    case "people": return ctx.canManage ? ctx.state.attendance.filter((a) => a.status === "waiting").length : ctx.hands.size;
    case "chat": return unansweredCount(ctx.state.questions, ctx.cid);
    case "agents": return busyAgents(ctx.agents);
    case "agenda": case "case": case "decision": return 0;
    default: return undefined;
  }
}

type TitleCtx = Pick<CallCtx, "state" | "order" | "agents">;

/** The panel's title with its count. */
export function panelTitle(kind: PanelKind, ctx: TitleCtx): string {
  switch (kind) {
    case "people": return `People · ${ctx.state.attendance.filter((a) => a.status === "present" || a.status === "remote").length}`;
    case "chat": return "Chat and questions";
    case "agenda": return `Agenda · ${ctx.order.length}`;
    case "case": return "Case";
    case "agents": return `AI agents · ${ctx.agents.length}`;
    case "decision": return "Decision";
    default: return "";
  }
}

function PanelBody({ kind }: { kind: Kind }) {
  switch (kind) {
    case "people": return <PeoplePanel />;
    case "chat": return <ChatPanel />;
    case "agenda": return <AgendaPanel />;
    case "case": return <CasePanel />;
    case "agents": return <AgentsPanel />;
    case "decision": return <DecisionPanel />;
  }
}

export function SidePanel() {
  const ctx = useCall();
  const { panel, phone, setPanel } = ctx;
  // Keep the last panel drawn while the laptop panel slides out.
  const last = useRef<Kind | null>(null);
  if (panel) last.current = panel;
  const kind = panel ?? last.current;
  if (!kind) return null;
  const title = panelTitle(kind, ctx);

  if (phone) {
    return (
      <Sheet open={!!panel} onOpenChange={(o) => { if (!o) setPanel(null); }}>
        <SheetContent side="bottom" showCloseButton={false} data-testid={`${kind}-panel`} aria-label={title}
          className="h-[85dvh] gap-0 rounded-t-2xl border-stage-line bg-stage-panel p-0 pb-[env(safe-area-inset-bottom)] text-stage-fg">
          <div className="mx-auto mt-2 h-1.5 w-10 shrink-0 rounded-full bg-stage-line" aria-hidden />
          <header className="flex items-center gap-2 border-b border-stage-line px-4 py-2">
            <SheetTitle className="min-w-0 flex-1 truncate text-base font-semibold text-stage-fg">{title}</SheetTitle>
            <SheetDescription className="sr-only">{PANEL_WORD[kind].about}</SheetDescription>
            <Button variant="ghost" className="min-h-11 text-stage-fg hover:bg-stage-raised hover:text-stage-fg" onClick={() => setPanel(null)} aria-label="Close the panel"><X className="size-4" />Close</Button>
          </header>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-4">
            <PanelBody kind={kind} />
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <StagePanel open={!!panel} title={title} onClose={() => setPanel(null)} testId={`${kind}-panel`} width={panelWidth(kind)}>
      <div className="space-y-3">
        <PanelBody kind={kind} />
      </div>
    </StagePanel>
  );
}
