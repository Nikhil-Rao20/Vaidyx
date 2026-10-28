// The left side list of the guided Case File (B1, like Epic's Navigator): one loud "Continue" button on top, then the six sections in
// working order, each a whole clickable row with its status word (B9). The section last worked in carries a loud "You left off here"
// (research: a subtle cue is no better than none). Below 1024 px the same sections become a row of chips that scrolls sideways.
import { ArrowRight, CheckCircle2, Circle, CircleDot, Hourglass, LayoutDashboard, Loader2, MinusCircle, OctagonAlert, Send } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SectionId, SectionStatus, StepSection, Steps } from "./types";

const ICON: Record<SectionStatus, typeof Circle> = {
  home: LayoutDashboard, done: CheckCircle2, todo: CircleDot, waiting: Hourglass, overdue: OctagonAlert, not_started: Circle, working: Loader2, empty: MinusCircle, not_needed: MinusCircle,
};
const TONE: Record<SectionStatus, string> = {
  home: "text-muted-foreground", done: "text-ok", todo: "text-brand", waiting: "text-warn", overdue: "text-bad", not_started: "text-muted-foreground",
  working: "text-link", empty: "text-muted-foreground", not_needed: "text-muted-foreground",
};

export function ContinueButton({ next, onGo, compact }: { next: Steps["next"]; onGo: (section: SectionId, target?: string) => void; compact?: boolean }) {
  if (!next) return null;
  if (next.done) {
    return (
      <div className={cn("flex items-center gap-2 rounded-lg status-ok px-3 py-2.5 text-sm font-medium", compact && "py-2")} data-testid="continue-done">
        <Send className="size-4 shrink-0" aria-hidden />{next.label}
      </div>
    );
  }
  return (
    <button type="button" onClick={() => onGo(next.section, next.target)} data-testid="continue"
      className={cn("group flex w-full items-center gap-2 rounded-lg bg-primary px-3 text-left font-semibold text-primary-foreground shadow-[var(--shadow-outer)] transition hover:bg-primary-hover active:scale-[0.99]",
        compact ? "py-2 text-sm" : "py-3 text-[0.95rem]")}>
      <span className="min-w-0 flex-1"><span className="block text-[11px] font-medium uppercase tracking-wide opacity-80">Continue</span>{next.label}</span>
      <ArrowRight className="size-5 shrink-0 transition-transform group-hover:translate-x-0.5" aria-hidden />
    </button>
  );
}

function Row({ s, active, leftOff, onOpen, number }: { s: StepSection; active: boolean; leftOff: boolean; onOpen: () => void; number: number }) {
  const Icon = ICON[s.status] ?? Circle;
  const loud = s.status === "todo" || s.status === "overdue";
  return (
    <li>
      <button type="button" onClick={onOpen} aria-current={active ? "page" : undefined} data-testid={`nav-${s.id}`} data-status={s.status}
        className={cn("relative flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left transition",
          active ? "bg-secondary text-secondary-foreground" : "hover:bg-accent")}>
        {active ? <span className="absolute inset-y-1.5 left-0 w-1 rounded-full bg-primary" aria-hidden /> : null}
        <Icon className={cn("mt-0.5 size-[18px] shrink-0", TONE[s.status], s.status === "working" && "animate-spin")} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className={cn("flex items-baseline gap-1.5 text-[0.95rem]", loud || active ? "font-semibold text-foreground" : "text-foreground")}>
            {s.id !== "overview" ? <span className="text-xs tabular-nums text-muted-foreground">{number}</span> : null}
            <span className="truncate">{s.label}</span>
            {s.id === "reports" && s.count ? <span className="ml-auto text-xs font-normal tabular-nums text-muted-foreground">{s.count}</span> : null}
          </span>
          {s.detail && s.status !== "done" ? (
            <span className={cn("block text-xs leading-snug", s.status === "overdue" ? "font-medium text-bad" : loud ? "font-medium text-brand-text" : s.status === "waiting" ? "text-warn" : "text-muted-foreground")}>{s.detail}</span>
          ) : null}
          {leftOff && !active ? <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-indigo/10 px-2 py-0.5 text-[11px] font-semibold text-indigo" data-testid="left-off">You left off here</span> : null}
        </span>
      </button>
    </li>
  );
}

export function SectionNav({ steps, active, leftOff, onOpen, onGo }: { steps: Steps; active: SectionId; leftOff: SectionId | null; onOpen: (s: SectionId) => void; onGo: (s: SectionId, target?: string) => void }) {
  return (
    <nav aria-label="Case File sections" className="space-y-3" data-testid="section-nav">
      {steps.mode === "prepare" ? <ContinueButton next={steps.next} onGo={onGo} /> : null}
      <ol className="space-y-0.5">
        {steps.sections.map((s, i) => <Row key={s.id} s={s} number={i} active={active === s.id} leftOff={leftOff === s.id && s.id !== "overview"} onOpen={() => onOpen(s.id)} />)}
      </ol>
      {steps.mode === "read" ? <p className="px-2.5 text-xs text-muted-foreground">You can read this Case File. The treating team prepares it.</p> : null}
    </nav>
  );
}

/** Phones and narrow windows: the sections as chips in one row that scrolls sideways, Continue under it. */
export function SectionChips({ steps, active, onOpen, onGo }: { steps: Steps; active: SectionId; onOpen: (s: SectionId) => void; onGo: (s: SectionId, target?: string) => void }) {
  return (
    <div className="space-y-2" data-testid="section-chips">
      <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 scroll-thin">
        {steps.sections.map((s) => {
          const Icon = ICON[s.status] ?? Circle;
          return (
            <button key={s.id} type="button" onClick={() => onOpen(s.id)} aria-current={active === s.id ? "page" : undefined}
              className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm", active === s.id ? "border-primary bg-secondary font-semibold text-secondary-foreground" : "border-border bg-card")}>
              <Icon className={cn("size-4", TONE[s.status], s.status === "working" && "animate-spin")} aria-hidden />{s.label}
              {s.status === "todo" && s.count ? <span className="rounded-full bg-primary px-1.5 text-[11px] font-bold text-primary-foreground">{s.count}</span> : null}
            </button>
          );
        })}
      </div>
      {steps.mode === "prepare" ? <ContinueButton next={steps.next} onGo={onGo} compact /> : null}
    </div>
  );
}

