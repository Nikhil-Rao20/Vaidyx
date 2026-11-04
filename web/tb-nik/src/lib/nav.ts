// The 2 to 5 items of the top bar and the Dock, per role: Case Files and Meetings for everyone clinical, plus the role items. Several roles give the union, in a fixed order.
import type { LucideIcon } from "lucide-react";
import { Activity, BookOpen, CalendarDays, FolderOpen, Inbox, MessageSquare, Settings2, Users } from "lucide-react";
import type { Me } from "@/lib/session";

export interface NavItem {
  key: string;
  label: string;
  to: string;
  icon: LucideIcon;
  /** True when the current path belongs to this item. */
  match: (path: string) => boolean;
  /** A small number shown on the item (open requests, waiting). */
  badge?: number;
}

const startsWith = (prefix: string) => (path: string) => path === prefix || path.startsWith(prefix + "/");

export function isRootAdminOnly(me: Me): boolean {
  const r = me.roles;
  return Boolean(r.root_admin) && !r.coordinator && !Object.keys(r.departments || {}).length && !(r.admin_of || []).length;
}

export function isDeptAdmin(me: Me): boolean {
  return (me.roles.admin_of || []).length > 0;
}

export function isDoctor(me: Me): boolean {
  return Object.keys(me.roles.departments || {}).length > 0;
}

export function hasInbox(me: Me): boolean {
  return (me.roles.supporting || []).length > 0 || (me.counts?.open_requests ?? 0) > 0;
}

export function navItems(me: Me, messagesUnread?: number): NavItem[] {
  const r = me.roles;
  const items: NavItem[] = [];
  const primary = me.primary_role;
  const doctor = isDoctor(me);
  const clinical = doctor || Boolean(r.coordinator);

  // One list, not two: "Case Files" is the home of every clinical role (the owner, 19 Oct: Home and Case Files were the same page).
  if (clinical) {
    items.push({ key: "cases", label: "Case Files", to: "/cases", icon: FolderOpen, match: (p) => p === "/" || p === "/home" || startsWith("/cases")(p) });
  }
  if (hasInbox(me) && primary !== "supporting") {
    items.push({ key: "requests", label: "Requests", to: "/requests", icon: Inbox, match: startsWith("/requests"), badge: me.counts?.open_requests || undefined });
  }
  if (clinical || r.outside_expert) {
    items.push({ key: "meetings", label: "Meetings", to: "/meetings", icon: CalendarDays, match: startsWith("/meetings") });
    // Ask PubMed (3 Nov 2026): general questions answered from PubMed abstracts, for the same clinical logins and outside experts.
    items.push({ key: "pubmed", label: "PubMed", to: "/pubmed", icon: BookOpen, match: startsWith("/pubmed") });
  }
  // Messages (Phase 8): every placed login and the MDT Coordinator; the badge is the unread count.
  if (me.messages) {
    items.push({ key: "messages", label: "Messages", to: "/messages", icon: MessageSquare, match: startsWith("/messages"), badge: (messagesUnread ?? me.counts?.messages_unread) || undefined });
  }
  if (isDeptAdmin(me) || r.root_admin) {
    items.push({ key: "people", label: "People", to: "/people", icon: Users, match: startsWith("/people") });
  }
  if (r.root_admin) {
    items.push({ key: "admin", label: "Admin", to: "/admin", icon: Settings2, match: startsWith("/admin") });
  }
  // The auditor's page; admins who hold no clinical role also get it (their own actions and, for the root admin, the full log).
  if (r.auditor || (!clinical && (r.root_admin || isDeptAdmin(me)))) {
    items.push({ key: "activity", label: "Activity", to: "/activity", icon: Activity, match: startsWith("/activity") });
  }
  return fitNav(items);
}

/** Five fit the top bar and the Dock. When there are more, Messages steps out first: its icon with the badge stays in the top bar
 * beside the bell on every screen, so nothing is lost. Still more (a clinical login who is also an admin): PubMed steps out next,
 * as the Case Files page keeps its Ask PubMed card. */
export function fitNav(items: NavItem[]): NavItem[] {
  if (items.length <= 5) return items;
  let out = items.filter((it) => it.key !== "messages");
  if (out.length > 5) out = out.filter((it) => it.key !== "pubmed");
  return out.slice(0, 5);
}

/** Where "Home" goes for this person. */
export function homePath(me: Me): string {
  if (isRootAdminOnly(me)) return "/admin";
  if (me.primary_role === "auditor" && !isDoctor(me)) return "/activity";
  return "/cases";
}

/** Plain words for the role list in the profile menu. */
export function roleWords(me: Me): string[] {
  const r = me.roles;
  const out: string[] = [];
  if ((r.treating || []).length) out.push("Treating doctor");
  if (Object.values(r.departments || {}).includes("resident")) out.push("Resident");
  if ((r.supporting || []).length) out.push("Supporting doctor");
  if (r.coordinator) out.push("MDT Coordinator");
  if ((r.admin_of || []).length) out.push("Department admin");
  if (r.root_admin) out.push("Root admin");
  if (r.auditor) out.push("Auditor");
  if (r.outside_expert) out.push("Outside expert");
  if (!out.length) out.push("No role yet");
  return out;
}
