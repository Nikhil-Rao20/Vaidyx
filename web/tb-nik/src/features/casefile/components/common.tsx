// Small pieces every Case File and meeting screen uses: dates in Indian display form, status chips (colour + icon + word),
// buttons with a loading state, empty and error states with a small drawing and one plain sentence, a screen-reader announcer.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { format, formatDistanceToNowStrict, isValid, parseISO } from "date-fns";
import { CheckCircle2, CircleDashed, Clock, HelpCircle, Loader2, MinusCircle, Search, XCircle, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api";

// ---- dates -------------------------------------------------------------------------------------------------------
// On screen: DD/MM/YYYY (India first); the API sends ISO 8601.
export function fmtDate(iso?: string | null): string {
  if (!iso) return "";
  const d = parseISO(String(iso));
  return isValid(d) ? format(d, "dd/MM/yyyy") : String(iso);
}
export function fmtDateTime(iso?: string | null): string {
  if (!iso) return "";
  const d = parseISO(String(iso));
  return isValid(d) ? format(d, "dd/MM/yyyy, HH:mm") : String(iso);
}
/** Today as YYYY-MM-DD in the browser's own time zone (for date inputs). */
export function todayIso(): string {
  return format(new Date(), "yyyy-MM-dd");
}
export function ago(iso?: string | null): string {
  if (!iso) return "";
  const d = parseISO(String(iso));
  return isValid(d) ? formatDistanceToNowStrict(d, { addSuffix: true }) : "";
}
export function plural(n: number, one: string, many = one + "s"): string {
  return `${n} ${n === 1 ? one : many}`;
}
export function initials(name?: string): string {
  return (name ?? "").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}
/** Model names as the owner wants them labelled everywhere (the project rules on model labels). */
export function modelLabel(m?: string | null): string {
  const s = String(m ?? "").trim();
  if (!s) return "";
  if (/gemma/i.test(s)) return "Gemma-4-31B (non-medical)";
  if (/qwen/i.test(s)) return "Qwen3.5-4B (Chinese, non-medical)";
  return s;
}

/** The title of a record for a quote chip: the citation's own title, else the Case File's document list. */
export function docTitleOf(docs: Array<{ doc_id: string; filename: string; classification?: { title?: string } }> | undefined, docId: string, given?: string | null): string {
  if (given) return given;
  const d = (docs ?? []).find((x) => x.doc_id === docId);
  return d?.classification?.title || d?.filename || "record";
}


// ---- status chips ------------------------------------------------------------------------------------------------
export type ChipKind = "ok" | "warn" | "bad" | "review" | "muted" | "info";
const CHIP_ICON: Record<ChipKind, LucideIcon> = { ok: CheckCircle2, warn: Clock, bad: XCircle, review: HelpCircle, muted: MinusCircle, info: CircleDashed };
const CHIP_CLASS: Record<ChipKind, string> = {
  ok: "status-ok", warn: "status-warn", bad: "status-bad", review: "status-review",
  muted: "bg-muted text-muted-foreground", info: "bg-secondary text-secondary-foreground",
};
export function StatusChip({ kind, icon: Icon, children, className, title }: { kind: ChipKind; icon?: LucideIcon; children: ReactNode; className?: string; title?: string }) {
  const I = Icon ?? CHIP_ICON[kind];
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", CHIP_CLASS[kind], className)}>
      <I className="size-3.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </span>
  );
}

// ---- buttons -----------------------------------------------------------------------------------------------------
type ButtonProps = React.ComponentProps<typeof Button>;
export function LoadingButton({ loading, children, disabled, className, loadingText, ...rest }: ButtonProps & { loading?: boolean; loadingText?: string }) {
  return (
    <Button {...rest} disabled={disabled || loading} aria-busy={loading || undefined} className={cn("active:scale-[0.98] transition-transform", className)}>
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
      {loading && loadingText ? loadingText : children}
    </Button>
  );
}

/** A control the person may not use right now: still visible, greyed, with the reason in a tooltip and for screen readers. */
export function DisabledReason({ reason, children }: { reason: string; children: ReactNode }) {
  return (
    <span className="inline-flex" title={reason} aria-label={reason}>
      {children}
    </span>
  );
}

// ---- empty and error states ----------------------------------------------------------------------------------------
function Drawing({ kind }: { kind: "empty" | "error" | "search" | "wait" }) {
  const stroke = "currentColor";
  return (
    <svg viewBox="0 0 96 64" className="h-12 w-20 text-muted-foreground/70" aria-hidden>
      <rect x="18" y="10" width="60" height="44" rx="6" fill="none" stroke={stroke} strokeWidth="2" />
      {kind === "empty" && <><line x1="30" y1="24" x2="54" y2="24" stroke={stroke} strokeWidth="2" strokeLinecap="round" /><line x1="30" y1="34" x2="66" y2="34" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeDasharray="3 4" /><line x1="30" y1="44" x2="48" y2="44" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeDasharray="3 4" /></>}
      {kind === "error" && <><line x1="40" y1="24" x2="56" y2="40" stroke={stroke} strokeWidth="2.5" strokeLinecap="round" /><line x1="56" y1="24" x2="40" y2="40" stroke={stroke} strokeWidth="2.5" strokeLinecap="round" /></>}
      {kind === "search" && <><circle cx="45" cy="30" r="8" fill="none" stroke={stroke} strokeWidth="2" /><line x1="51" y1="36" x2="60" y2="45" stroke={stroke} strokeWidth="2.5" strokeLinecap="round" /></>}
      {kind === "wait" && <><circle cx="48" cy="32" r="10" fill="none" stroke={stroke} strokeWidth="2" /><line x1="48" y1="32" x2="48" y2="25" stroke={stroke} strokeWidth="2" strokeLinecap="round" /><line x1="48" y1="32" x2="53" y2="35" stroke={stroke} strokeWidth="2" strokeLinecap="round" /></>}
    </svg>
  );
}

export function EmptyState({ title, text, action, kind = "empty", className }: { title: string; text?: string; action?: ReactNode; kind?: "empty" | "search" | "wait"; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center text-center gap-2 py-8 px-4", className)}>
      <Drawing kind={kind} />
      <p className="font-medium text-foreground">{title}</p>
      {text ? <p className="text-sm text-muted-foreground max-w-prose">{text}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message || "Something went wrong.";
  return "Something went wrong.";
}

export function ErrorState({ error, retry, title, className, compact }: { error: unknown; retry?: () => void; title?: string; className?: string; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const status = error instanceof ApiError ? error.status : undefined;
  const cause = status === 0 ? "No connection to the server." : status === 403 ? "You do not have permission for this." : status === 404 ? "This is not on the server." : status && status >= 500 ? "The server could not answer." : "Something went wrong.";
  return (
    <div role="alert" className={cn("flex flex-col items-center text-center gap-2", compact ? "py-4 px-3" : "py-8 px-4", className)}>
      {!compact && <Drawing kind="error" />}
      <p className="font-medium text-foreground">{title ?? cause}</p>
      <p className="text-sm text-muted-foreground max-w-prose">{errorText(error)}</p>
      <div className="flex items-center gap-2 mt-1">
        {retry ? <Button size="sm" variant="outline" onClick={retry}>Try again</Button> : null}
        <button type="button" className="text-xs text-muted-foreground underline underline-offset-2" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{open ? "Hide details" : "Details"}</button>
      </div>
      {open ? <pre className="mt-2 max-w-full overflow-auto rounded-md bg-muted p-2 text-left text-xs text-muted-foreground">{JSON.stringify(error instanceof ApiError ? { status: error.status, code: error.code, detail: error.detail } : String(error), null, 2)}</pre> : null}
    </div>
  );
}

/** The honest state for a new endpoint the server does not have yet. */
export function NotYetState({ what, fallback }: { what: string; fallback?: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-border-strong bg-muted/60 p-3 text-sm">
      <p className="text-foreground font-medium"><Search className="inline size-4 mr-1 -mt-0.5" aria-hidden />{what} is not available on this server yet.</p>
      {fallback ? <div className="mt-1 text-muted-foreground">{fallback}</div> : null}
    </div>
  );
}


// ---- screen-reader announcements -------------------------------------------------------------------------------------
export function useAnnounce(): [(text: string) => void, ReactNode] {
  const [text, setText] = useState("");
  const timer = useRef<number | null>(null);
  const announce = useCallback((t: string) => {
    setText("");
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setText(t), 30);
  }, []);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);
  const node = <div className="sr-only" aria-live="polite" aria-atomic="true">{text}</div>;
  return [announce, node];
}

/** Copy to the clipboard with a "Copied" state for 2 s; falls back to selecting the text when the clipboard is blocked. */
export function useCopy(): [copied: boolean, copy: (text: string) => Promise<void>] {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async (text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(true); window.setTimeout(() => setCopied(false), 2000); }
    catch { window.prompt("Copy this code", text); }
  }, []);
  return [copied, copy];
}

export function SkeletonLines({ n = 3, className }: { n?: number; className?: string }) {
  const widths = ["w-full", "w-5/6", "w-4/6", "w-3/4", "w-2/3"];
  return (
    <div className={cn("space-y-2", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: n }).map((_, i) => <div key={i} className={cn("skeleton-line h-4", widths[i % widths.length])} />)}
    </div>
  );
}
