// Small pieces the Messages screens share: avatars with the online dot, the five reactions, day labels, the patient-number check.
import type { LucideIcon } from "lucide-react";
import { Building2, Check, Eye, HeartHandshake, ListChecks, ThumbsUp, Users } from "lucide-react";
import { Avatar, AvatarBadge, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { formatDate, initials, parseDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ConversationKind, Presence, ReactionKind } from "@/features/messages/types";

export const TEXT_MAX = 2000;
export const COUNTER_FROM = 1800;

export const NOT_PLACED = "Messages are for placed hospital staff.";
export const NOTE_UNDER_COMPOSER = "Do not type patient names or numbers here. Attach the Case File. Decisions go in the Case File.";
export const PATIENT_NUMBER_WARNING = "This looks like a patient number. Attach the Case File instead?";

/** The five fixed reactions (section 9.8 point 5), in the order the menu shows them. */
export const REACTIONS: Array<{ kind: ReactionKind; label: string; icon: LucideIcon; word?: boolean }> = [
  { kind: "thumbs_up", label: "Thumbs up", icon: ThumbsUp },
  { kind: "seen", label: "Seen", icon: Eye, word: true },
  { kind: "thanks", label: "Thanks", icon: HeartHandshake, word: true },
  { kind: "will_do", label: "Will do", icon: ListChecks, word: true },
  { kind: "tick", label: "Tick", icon: Check },
];

const PRESENCE_WORD: Record<Presence, string> = { online: "Online", away: "Away", offline: "Offline" };
export const presenceWord = (p: Presence) => PRESENCE_WORD[p];

/** A person's round picture (or initials) with the online dot: green online, amber away, none offline. */
export function PersonAvatar({ name, photo, presence, size = "default", className }: {
  name: string;
  photo?: string | null;
  presence?: Presence;
  size?: "default" | "sm" | "lg";
  className?: string;
}) {
  return (
    <Avatar size={size} className={cn("overflow-visible", size === "default" && "size-9", className)}>
      {photo ? <AvatarImage src={photo} alt="" className="rounded-full object-cover" /> : null}
      <AvatarFallback className="bg-secondary text-sm font-bold text-secondary-foreground">{initials(name.replace(/^Dr\.?\s+/i, ""))}</AvatarFallback>
      {presence && presence !== "offline" ? (
        <AvatarBadge className={cn("ring-card", presence === "online" ? "bg-ok" : "bg-warn")} title={presenceWord(presence)}>
          <span className="sr-only">{presenceWord(presence)}</span>
        </AvatarBadge>
      ) : null}
    </Avatar>
  );
}

/** The avatar of a conversation: the person, or a department or coordinator mark. */
export function ConversationAvatar({ kind, name, presence, size }: { kind: ConversationKind; name: string; presence?: Presence; size?: "default" | "lg" }) {
  if (kind === "direct") return <PersonAvatar name={name} presence={presence} size={size} />;
  const Icon = kind === "department" ? Building2 : Users;
  return (
    <span className={cn("grid shrink-0 place-items-center rounded-full bg-accent text-accent-foreground", size === "lg" ? "size-10" : "size-9")} aria-hidden>
      <Icon className="size-4" />
    </span>
  );
}

/** "Today", "Yesterday" or DD/MM/YYYY for the day separators of a thread. */
export function dayLabel(ts: string, now: Date = new Date()): string {
  const d = parseDate(ts);
  if (!d) return "";
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  if (t === start) return "Today";
  if (t === start - 86400000) return "Yesterday";
  return formatDate(d);
}

/** HH:MM (24 h, the browser's time zone). */
export function clock(ts: string): string {
  const d = parseDate(ts);
  return d ? `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}` : "";
}

/** Groups items by calendar day, oldest day first (the order of a thread). */
export function groupDays<T extends { ts: string }>(items: T[]): Array<{ key: string; label: string; items: T[] }> {
  const out: Array<{ key: string; label: string; items: T[] }> = [];
  for (const it of items) {
    const d = parseDate(it.ts);
    const key = d ? `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}` : "unknown";
    const last = out[out.length - 1];
    if (last && last.key === key) last.items.push(it);
    else out.push({ key, label: dayLabel(it.ts), items: [it] });
  }
  return out;
}

// Patterns that look like a patient number (section 9.8 point 4): a soft warning, never a block.
const PATTERNS: RegExp[] = [
  // UHID, MRN, CR No., IP / OP No. written with letters and numbers in parts: "VXH/2026/000123", "IP-24-55321"
  /(?:^|[^A-Za-z0-9])[A-Za-z]{2,6}\s?[/-]\s?\d{2,4}\s?[/-]\s?\d{3,}(?![0-9])/,
  // A number written after one of those words: "UHID 4471203", "CR No. 88213"
  /\b(?:UHID|MRN|CR\.?\s?No|IP\s?No|OP\s?No|Reg(?:istration)?\.?\s?No)\b\.?[\s:#-]*[A-Za-z0-9/-]*\d{4,}/i,
  // ABHA: 14 digits, often 12-3456-7890-1234
  /(?:^|[^\d])\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}(?!\d)/,
  // A phone number: 10 digits starting 6 to 9, with or without +91
  /(?:^|[^\d])(?:\+?91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}(?!\d)/,
];

/** True when the text looks like it holds a UHID, an ABHA number or a phone number. */
export function looksLikePatientNumber(text: string): boolean {
  return PATTERNS.some((re) => re.test(text));
}

/** Minutes left (rounded up) until an ISO time, or 0 when it has passed. */
export function minutesLeft(until: string | null, now: number = Date.now()): number {
  const d = parseDate(until);
  if (!d) return 0;
  const ms = d.getTime() - now;
  return ms > 0 ? Math.ceil(ms / 60000) : 0;
}
