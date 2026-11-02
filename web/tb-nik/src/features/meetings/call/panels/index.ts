// The call's side panels (night-v3 5.1): the one SidePanel slot, every panel, and the helpers the bar uses for its panel buttons
// (icons, titles, counts). The panels read everything through useCall() and act through ctx.actions.
import type { CallCtx, PanelKind } from "../types";
import { panelBadge as panelCount } from "./SidePanel";
import { unreadChat } from "./ChatPanel";

export { SidePanel, PANEL_ICONS, PANEL_WORD, panelTitle } from "./SidePanel";
export { PeoplePanel, personBadges, peopleSections, nextSpotlight, SPOTLIGHT_MAX } from "./PeoplePanel";
export {
  ChatPanel, QuestionForm, QuestionItems, questionsFor, unansweredCount,
  caseChipLabel, chatClosedReason, chatDays, chatSeenKey, chatTime, countUnread, newestAt, readChatSeen, unreadChat, writeChatSeen,
} from "./ChatPanel";
export { AgendaPanel, agendaRowState, isDone, outcomeWord, type AgendaState, type AgendaStateKind } from "./AgendaPanel";
export { AgentsPanel, AGENT_BUSY, busyAgents } from "./AgentsPanel";
export { DecisionPanel, cardsLine } from "./DecisionPanel";
export { handOrder, whereWord } from "../../components/People";

type BadgeCtx = Parameters<typeof panelCount>[1] & Pick<CallCtx, "mid" | "me" | "variant"> & Partial<Pick<CallCtx, "panel">>;

/** The count on a panel's button (SidePanel's panelBadge); Chat adds my unread meeting chat lines (item 5.3: the lines of others
 * newer than my seen mark). While the Chat panel is open its "Meeting chat" tab carries that count, so the button shows the
 * unanswered questions only. */
export function panelBadge(kind: PanelKind, ctx: BadgeCtx): number | undefined {
  const n = panelCount(kind, ctx);
  if (kind !== "chat" || ctx.panel === "chat") return n;
  return (n ?? 0) + unreadChat(ctx);
}
