import type { LucideIcon } from "lucide-react";
import { Archive, CalendarCheck, CheckCircle2, CircleCheck, CircleDashed, Gavel, Hand, Hourglass } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CaseStatusKey } from "@/lib/types";

export type Tone = "neutral" | "ok" | "warn" | "bad" | "review" | "info";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground",
  ok: "status-ok",
  warn: "status-warn",
  bad: "status-bad",
  review: "status-review",
  info: "bg-secondary text-secondary-foreground",
};

export const STATUS_STYLE: Record<CaseStatusKey, { icon: LucideIcon; tone: Tone; word: string }> = {
  needs_me: { icon: Hand, tone: "review", word: "Needs you" },
  waiting_department: { icon: Hourglass, tone: "warn", word: "Waiting" },
  ready: { icon: CheckCircle2, tone: "ok", word: "Ready for the board" },
  scheduled: { icon: CalendarCheck, tone: "info", word: "Scheduled" },
  decided: { icon: Gavel, tone: "ok", word: "Decided" },
  archived: { icon: Archive, tone: "neutral", word: "Archived" },
  draft: { icon: CircleDashed, tone: "neutral", word: "Reading records" },
  quiet: { icon: CircleCheck, tone: "neutral", word: "Nothing open" },
};

/** Status = colour + icon + word, never colour alone. Any pill with a tone and an icon. */
export function Pill({ tone = "neutral", icon: Icon, children, className, title }: { tone?: Tone; icon?: LucideIcon; children: React.ReactNode; className?: string; title?: string }) {
  return (
    <span className={cn("inline-flex max-w-full items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONE_CLASS[tone], className)} title={title}>
      {Icon ? <Icon className="size-3.5 shrink-0" aria-hidden /> : null}
      <span className="truncate">{children}</span>
    </span>
  );
}

/** The Case File status word with its icon; `label` from the server wins over the built-in word. */
export function StatusPill({ status, className }: { status: { key: CaseStatusKey | string; label?: string; detail?: string }; className?: string }) {
  const s = STATUS_STYLE[status.key as CaseStatusKey] ?? STATUS_STYLE.draft;
  // The server may put an ISO date in the label ("Scheduled 2026-10-21"); the screen shows DD/MM/YYYY.
  const label = (status.label || s.word).replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, (_m, y, mo, d) => `${d}/${mo}/${y}`);
  return (
    <Pill tone={s.tone} icon={s.icon} className={className} title={status.detail || undefined}>
      {label}
    </Pill>
  );
}
