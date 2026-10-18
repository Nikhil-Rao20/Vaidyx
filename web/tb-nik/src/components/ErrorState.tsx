import { useState, type ReactNode } from "react";
import { ChevronDown, RefreshCw, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Illustration } from "@/components/Illustration";
import { ApiError } from "@/lib/api";
import { isRouteMissing } from "@/lib/errors";
import { cn } from "@/lib/utils";

export interface ErrorWords {
  title: string;
  text: string;
  notBuilt: boolean;
  offline: boolean;
  status: number;
  detail: string;
}

/** Plain words for an error: what happened (the cause) and nothing else. */
export function errorWords(error: unknown, what = "this"): ErrorWords {
  if (error instanceof ApiError) {
    if (error.status === 0) return { title: "No connection", text: "The server did not answer. Check the network and try again.", notBuilt: false, offline: true, status: 0, detail: error.message };
    if (isRouteMissing(error)) return { title: "Not available yet", text: `The server part for ${what} is not built yet. Nothing is lost; try again later.`, notBuilt: true, offline: false, status: 404, detail: error.message };
    if (error.status === 404) return { title: "Not found", text: error.message && error.message !== "Not found." ? error.message : `${what === "this" ? "This" : what.charAt(0).toUpperCase() + what.slice(1)} could not be found. It may have been moved or archived.`, notBuilt: false, offline: false, status: 404, detail: "" };
    if (error.status === 403) return { title: "No permission", text: error.message || "You do not have permission for this.", notBuilt: false, offline: false, status: 403, detail: error.message };
    if (error.status === 429) return { title: "Too many tries", text: error.message || "Please wait a moment and try again.", notBuilt: false, offline: false, status: 429, detail: error.message };
    if (error.status >= 500) return { title: "The server could not answer", text: "Your work is safe; nothing was lost. Try again in a moment.", notBuilt: false, offline: false, status: error.status, detail: error.message };
    return { title: "Could not load", text: error.message, notBuilt: false, offline: false, status: error.status, detail: typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail ?? "") };
  }
  if (error instanceof Error) return { title: "Something went wrong", text: error.message || "Please try again.", notBuilt: false, offline: false, status: -1, detail: error.stack || "" };
  return { title: "Something went wrong", text: "Please try again.", notBuilt: false, offline: false, status: -1, detail: String(error ?? "") };
}

/** In place: a small drawing, the cause in one sentence, one action (Try again), details folded. */
export function ErrorState({ error, what, title, text, onRetry, retrying, action, className, compact }: {
  error?: unknown;
  /** "the Case File list": completes "The server part for ... is not built yet". */
  what?: string;
  title?: string;
  text?: ReactNode;
  onRetry?: () => void;
  retrying?: boolean;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const w = errorWords(error, what);
  const heading = title ?? w.title;
  const body = text ?? w.text;
  return (
    <div className={cn("flex flex-col items-center text-center", compact ? "px-4 py-5 gap-2" : "px-6 py-10 gap-3", className)} role="alert">
      {w.offline ? <WifiOff className="size-8 text-muted-foreground" aria-hidden /> : <Illustration kind={w.notBuilt ? "notfound" : "error"} className={compact ? "w-20 h-14" : undefined} />}
      <h3 className="text-base font-bold">{heading}</h3>
      <p className="max-w-md text-sm text-muted-foreground">{body}</p>
      <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
        {onRetry ? (
          <Button type="button" variant="outline" size="sm" onClick={onRetry} disabled={retrying} aria-busy={retrying}>
            <RefreshCw className={cn("size-4", retrying && "animate-spin")} aria-hidden /> {retrying ? "Trying" : "Try again"}
          </Button>
        ) : null}
        {action}
      </div>
      {w.detail && w.detail !== body ? (
        <div className="mt-1">
          <button type="button" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} aria-hidden /> Details
          </button>
          {open ? <pre className="mt-2 max-w-md overflow-auto rounded-md bg-muted p-2 text-left text-xs text-muted-foreground mono whitespace-pre-wrap">{w.status > 0 ? `HTTP ${w.status}: ` : ""}{w.detail}</pre> : null}
        </div>
      ) : null}
    </div>
  );
}
