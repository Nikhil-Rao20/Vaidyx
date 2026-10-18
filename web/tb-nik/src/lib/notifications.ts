// Plain words, an icon and a link for every notification kind the server writes (notify.KINDS plus the new kinds of SPEC-API push.py).
import type { LucideIcon } from "lucide-react";
import {
  Bell, CalendarDays, CheckCircle2, ClipboardList, FileCheck2, FilePlus2, Gavel, Handshake, Inbox, Link2, MailWarning,
  PenLine, RefreshCw, Send, ShieldAlert, Timer, UserPlus, Users,
} from "lucide-react";
import type { Notification } from "@/lib/types";
import { parseDate } from "@/lib/format";

export type Tone = "neutral" | "ok" | "warn" | "bad" | "review";

export interface KindInfo {
  label: string;
  icon: LucideIcon;
  tone: Tone;
}

export const KIND_INFO: Record<string, KindInfo> = {
  request: { label: "Request", icon: Inbox, tone: "warn" },
  request_closed: { label: "Request closed", icon: CheckCircle2, tone: "ok" },
  request_acknowledged: { label: "Request taken up", icon: Handshake, tone: "neutral" },
  request_done: { label: "Done by the department", icon: FileCheck2, tone: "ok" },
  request_reminder: { label: "Reminder", icon: Timer, tone: "warn" },
  owner_reminder: { label: "Reminder", icon: Timer, tone: "warn" },
  reminder_automatic: { label: "Automatic reminder", icon: RefreshCw, tone: "neutral" },
  case_ready: { label: "Case File ready", icon: CheckCircle2, tone: "ok" },
  board_ready: { label: "Ready for the board", icon: CheckCircle2, tone: "ok" },
  board_action: { label: "Board action", icon: ClipboardList, tone: "neutral" },
  board_action_suggestion: { label: "Board action", icon: ClipboardList, tone: "neutral" },
  decision_value_changed: { label: "A value changed", icon: ShieldAlert, tone: "review" },
  case_shared: { label: "Added to a Case File", icon: Users, tone: "neutral" },
  case_unshared: { label: "Removed from a Case File", icon: Users, tone: "neutral" },
  referral: { label: "Referral", icon: Send, tone: "review" },
  referral_answered: { label: "Referral answered", icon: Send, tone: "neutral" },
  sign_off: { label: "Asks you to sign off", icon: PenLine, tone: "review" },
  join_request: { label: "Wants to join", icon: UserPlus, tone: "review" },
  outcome: { label: "Board outcome", icon: Gavel, tone: "ok" },
  agenda: { label: "Agenda", icon: CalendarDays, tone: "neutral" },
  meeting_starting: { label: "Meeting starting", icon: CalendarDays, tone: "warn" },
  summary_stale: { label: "Summary out of date", icon: MailWarning, tone: "warn" },
  record_arrived: { label: "A record arrived", icon: FilePlus2, tone: "ok" },
  linked: { label: "Linked", icon: Link2, tone: "neutral" },
};

export function kindInfo(kind: string): KindInfo {
  return KIND_INFO[kind] ?? { label: "Update", icon: Bell, tone: "neutral" };
}

/** Where a click goes: the Case File, the meeting, or nowhere. */
export function notificationLink(n: Notification): string | null {
  if (n.meeting_id) return `/meetings/${encodeURIComponent(n.meeting_id)}`;
  if (n.kind === "agenda" || n.kind === "meeting_starting") return "/meetings";
  if (n.kind === "request" || n.kind === "request_reminder") return n.case_id ? `/requests?case=${encodeURIComponent(n.case_id)}` : "/requests";
  if (n.case_id) return `/cases/${encodeURIComponent(n.case_id)}`;
  return null;
}

/** "Today", "Yesterday", "Earlier" groups, newest first inside each. */
export function groupByDay(items: Notification[], now: Date = new Date()): Array<{ label: string; items: Notification[] }> {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const groups: Record<string, Notification[]> = { Today: [], Yesterday: [], Earlier: [] };
  for (const n of items) {
    const t = parseDate(n.ts)?.getTime() ?? 0;
    const key = t >= start ? "Today" : t >= start - 86400000 ? "Yesterday" : "Earlier";
    groups[key].push(n);
  }
  return Object.entries(groups).filter(([, v]) => v.length).map(([label, items]) => ({ label, items }));
}

/** The notification kinds a person can switch on or off in Settings, with plain words. */
export const PREF_KINDS: Array<{ id: string; label: string; hint: string }> = [
  { id: "request", label: "Requests to my department", hint: "A treating doctor asks for a record" },
  { id: "request_done", label: "Answers to my requests", hint: "The department sends done or acknowledges" },
  { id: "sign_off", label: "Sign-off asks", hint: "A resident asks me to approve a step" },
  { id: "join_request", label: "Join requests", hint: "Someone wants to join a Case File with a code" },
  { id: "record_arrived", label: "New records", hint: "The hospital system sent a new report" },
  { id: "summary_stale", label: "Summary out of date", hint: "Records changed after the summary was written" },
  { id: "agenda", label: "Agenda and meetings", hint: "Agenda sent, meeting about to start" },
  { id: "outcome", label: "Board outcomes", hint: "The decision on my Case File" },
  { id: "reminder_automatic", label: "Automatic reminders", hint: "Sent by Vaidyx when a request is due" },
];
