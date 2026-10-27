// The call's side panels (night-v3 5.1): the one SidePanel slot, every panel, and the helpers the bar uses for its panel buttons
// (icons, titles, counts). The panels read everything through useCall() and act through ctx.actions.
export { SidePanel, PANEL_ICONS, PANEL_WORD, panelBadge, panelTitle } from "./SidePanel";
export { PeoplePanel, personBadges, peopleSections, nextSpotlight, SPOTLIGHT_MAX } from "./PeoplePanel";
export { ChatPanel, QuestionForm, QuestionItems, questionsFor, unansweredCount } from "./ChatPanel";
export { AgendaPanel, agendaRowState, isDone, outcomeWord, type AgendaState, type AgendaStateKind } from "./AgendaPanel";
export { CasePanel, mayOpen } from "./CasePanel";
export { AgentsPanel, AGENT_BUSY, busyAgents } from "./AgentsPanel";
export { DecisionPanel, cardsLine } from "./DecisionPanel";
export { handOrder, whereWord } from "../../components/People";
