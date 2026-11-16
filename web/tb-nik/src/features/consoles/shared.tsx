// Pieces both admin consoles share (docs/admin-console/DESIGN.md section 4): the section tabs (sub-routes), stat tiles, status
// pills for a hospital and its hospital system, set-up progress, and the one-time first password (shown once, Copy, mail draft).
// Counts and names of people only: nothing here ever shows patient data.
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import type { LucideIcon } from "lucide-react";
import { CheckCircle2, CircleDashed, KeyRound, Mail, PauseCircle, PlugZap, Unplug, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CopyButton } from "@/components/CopyButton";
import { RowSkeleton } from "@/components/DataList";
import { Pill } from "@/components/StatusPill";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { HisState, HospitalHis, HospitalStatus } from "@/lib/types";

// ---- Section tabs ------------------------------------------------------------------------------------------------------------

export interface ConsoleTab {
  to: string;
  label: string;
  icon: LucideIcon;
  /** The index tab: active only on its own path. */
  end?: boolean;
}

/** The console's sections as links (each is its own address, so Back and a shared link work). Scrolls sideways on a phone. */
export function ConsoleTabs({ tabs, label, id }: { tabs: ConsoleTab[]; label: string; id: string }) {
  const { pathname } = useLocation();
  return (
    <div className="-mx-4 mb-5 overflow-x-auto px-4 scroll-thin md:mx-0 md:px-0">
      <nav aria-label={label} className="inline-flex min-w-max items-center gap-0.5 rounded-full bg-muted p-0.5">
        {tabs.map((t) => {
          const active = t.end ? pathname === t.to : pathname === t.to || pathname.startsWith(t.to + "/");
          const Icon = t.icon;
          return (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative inline-flex h-9 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-[13px] sm:px-3.5 font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {active ? <motion.span layoutId={`${id}-tab-pill`} className="absolute inset-0 rounded-full bg-card shadow-[var(--shadow-outer)]" transition={spring} aria-hidden /> : null}
              <Icon className="relative size-4" aria-hidden />
              <span className="relative">{t.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}

// ---- Tiles ---------------------------------------------------------------------------------------------------------------------

/** A number and what it counts. With `to`, the whole tile is a link. */
export function StatTile({ value, label, hint, icon: Icon, tone = "neutral", to, loading }: {
  value?: number | string | null;
  label: string;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: "neutral" | "ok" | "warn" | "bad";
  to?: string;
  loading?: boolean;
}) {
  const body = (
    <>
      <span className="flex items-start justify-between gap-2">
        <span className="min-w-0 text-xs font-medium text-muted-foreground">{label}</span>
        {Icon ? <Icon className={cn("size-4 shrink-0", tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : tone === "bad" ? "text-bad" : "text-muted-foreground")} aria-hidden /> : null}
      </span>
      {loading ? <span className="skeleton-line mt-2 block h-7 w-12" aria-hidden /> : (
        <span className="mt-1 block text-2xl font-semibold tabular-nums text-foreground">{value ?? 0}</span>
      )}
      {hint ? <span className="mt-0.5 block text-xs text-muted-foreground">{hint}</span> : null}
    </>
  );
  const cls = "surface flex min-h-[92px] flex-col p-4 text-left";
  if (to) return <Link to={to} className={cn(cls, "row-lift outline-none focus-visible:ring-2 focus-visible:ring-ring")}>{body}</Link>;
  return <div className={cls}>{body}</div>;
}

export function TileGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("grid grid-cols-2 gap-3 md:grid-cols-4", className)}>{children}</div>;
}

/** A titled card on the page (one surface level). */
export function Card({ title, icon: Icon, action, children, className, id }: { title: ReactNode; icon?: LucideIcon; action?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section className={cn("surface p-4", className)} aria-labelledby={id}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id={id} className="flex items-center gap-2 text-base">{Icon ? <Icon className="size-4 text-brand-text" aria-hidden /> : null}{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

// ---- Status words ---------------------------------------------------------------------------------------------------------------

export function HospitalStatusPill({ status }: { status: HospitalStatus | string }) {
  return status === "suspended" ? <Pill tone="bad" icon={PauseCircle}>Suspended</Pill> : <Pill tone="ok" icon={CheckCircle2}>Active</Pill>;
}

const HIS_WORDS: Record<HisState, { word: string; tone: "ok" | "bad" | "warn" | "neutral"; icon: LucideIcon }> = {
  connected: { word: "Connected", tone: "ok", icon: PlugZap },
  failing: { word: "Not answering", tone: "bad", icon: TriangleAlert },
  not_tested: { word: "Not tested", tone: "warn", icon: CircleDashed },
  not_set: { word: "Not set", tone: "neutral", icon: Unplug },
};

export function hisWords(his?: Partial<HospitalHis> | null) {
  const state = (his?.state && his.state in HIS_WORDS ? his.state : his?.ok ? "connected" : his?.ok === false ? "failing" : his?.url_set ? "not_tested" : "not_set") as HisState;
  return { state, ...HIS_WORDS[state] };
}

export function HisPill({ his }: { his?: Partial<HospitalHis> | null }) {
  const w = hisWords(his);
  return <Pill tone={w.tone} icon={w.icon}>{w.word}{his?.demo ? " (demo)" : ""}</Pill>;
}

/** "3 of 5" with a thin bar. */
export function SetupProgress({ done, total, className }: { done: number; total: number; className?: string }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <span className={cn("flex min-w-[96px] items-center gap-2", className)}>
      <Progress value={pct} className="h-1.5 w-16" aria-label={`Set-up ${done} of ${total} steps done`} />
      <span className="whitespace-nowrap text-xs tabular-nums text-muted-foreground">{done} of {total}</span>
    </span>
  );
}

// ---- The first password, shown once ------------------------------------------------------------------------------------------

/** The login name and the first password with Copy buttons, and the mail draft. Vaidyx keeps no copy (D10). */
export function OneTimeLoginPanel({ login, password, mailto }: { login: string; password: string; mailto?: string }) {
  return (
    <div className="grid grid-cols-1 gap-3" data-testid="one-time-login">
      <div className="grid grid-cols-1 gap-2 rounded-md border border-border bg-muted/60 p-3 text-sm" role="group" aria-label="First login">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="w-28 shrink-0 text-muted-foreground">Login name</span>
          <span className="mono min-w-0 break-all text-foreground">{login}</span>
          <CopyButton text={login} label="Copy the login name" />
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="w-28 shrink-0 text-muted-foreground">First password</span>
          <span className="mono min-w-0 break-all font-medium text-foreground" data-testid="first-password">{password}</span>
          <CopyButton text={password} label="Copy the first password" />
        </div>
      </div>
      <p className="flex items-start gap-2 rounded-md status-warn px-3 py-2 text-xs">
        <KeyRound className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>Shown only this once. Copy it now or open the mail draft; Vaidyx keeps no copy. They choose their own password at the first sign-in.</span>
      </p>
      {mailto ? (
        <Button type="button" variant="outline" asChild className="w-full sm:w-fit">
          <a href={mailto}><Mail className="size-4" aria-hidden /> Open mail draft</a>
        </Button>
      ) : null}
    </div>
  );
}

/** The one-time login in its own dialog (after a password reset or a new login). */
export function OneTimeLoginDialog({ value, onClose, title, text }: {
  value: { login: string; password: string; mailto?: string; who?: string } | null;
  onClose: () => void;
  title?: string;
  text?: string;
}) {
  return (
    <Dialog open={Boolean(value)} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title ?? `The first login for ${value?.who || value?.login || ""}`}</DialogTitle>
          <DialogDescription>{text ?? "Give it to the person directly (in person, by phone or in the mail draft)."}</DialogDescription>
        </DialogHeader>
        {value ? <OneTimeLoginPanel login={value.login} password={value.password} mailto={value.mailto} /> : null}
        <DialogFooter>
          <Button type="button" onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---- Words ------------------------------------------------------------------------------------------------------------------

/** The role keys of the consoles in plain words. */
export const ROLE_LABEL: Record<string, string> = {
  hospital_admin: "Hospital admin",
  root_admin: "Hospital admin",
  doctor: "Doctor",
  member: "Doctor",
  head: "Head of department",
  resident: "Resident",
  coordinator: "MDT Coordinator",
  dept_admin: "Department admin",
  auditor: "Auditor",
  guest: "Guest reviewer",
  outside_expert: "Outside expert",
  vaidyx_admin: "Vaidyx admin",
};

export function roleLabel(k: string): string {
  return ROLE_LABEL[k] ?? k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** A set-up summary from the server in plain words: "13 login(s)" reads "13 logins", "root admin" reads "hospital admin". */
export function plainSummary(text?: string): string {
  return (text ?? "").replace(/\b(\d+) ([\w ]*?\w)\(s\)/g, (_m, n, w) => `${n} ${w}${n === "1" ? "" : "s"}`).replace(/\broot admin/gi, "hospital admin");
}

/** "Good morning" by the hour on this device. */
export function greeting(now = new Date()): string {
  const h = now.getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** A short skeleton for a card's body. */
export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2" aria-hidden>
      {Array.from({ length: lines }).map((_, i) => <div key={i} className="skeleton-line h-4" style={{ width: `${90 - i * 12}%` }} />)}
    </div>
  );
}

/** While a console section loads: four tiles and a few rows. */
export function TabSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="surface h-[92px] p-4"><div className="skeleton-line h-3 w-2/3" /><div className="skeleton-line mt-3 h-7 w-12" /></div>)}</div>
      {Array.from({ length: 4 }).map((_, i) => <RowSkeleton key={i} />)}
    </div>
  );
}
