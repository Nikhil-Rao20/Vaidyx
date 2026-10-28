// What the rest of the app may use from Messages: the live hook (mounted once in the shell), the unread count, the keys,
// and the link builder for the "Message" buttons.
export { useMessagesLive, usePresence, useTyping } from "@/features/messages/useMessagesLive";
export { msgKeys, useMessagesUnread, POLL_MS } from "@/features/messages/hooks";
export { pickPath } from "@/features/messages/DirectoryPicker";
export type * from "@/features/messages/types";

/** The link of a "Message" button: /messages/new?to=<login> | dept=<id> | coordinator=1, with &case=<id> to attach the Case File. */
export function messageLink(target: { to: string } | { dept: string } | { coordinator: true }, caseId?: string): string {
  const t = "to" in target ? `to=${encodeURIComponent(target.to)}` : "dept" in target ? `dept=${encodeURIComponent(target.dept)}` : "coordinator=1";
  return `/messages/new?${t}${caseId ? `&case=${encodeURIComponent(caseId)}` : ""}`;
}
