// Small reversible steps (send a drafted request, remind, not needed) act in place with Undo for 10 s. The server has no
// "unsend", so the step is shown as done at once and really posted when the 10 s run out (or when the page is left);
// Undo inside that window cancels it and the row goes back to what it was.
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Loader2, Undo2 } from "lucide-react";
import { whileLeaving } from "@/lib/api";
import { cn } from "@/lib/utils";

export const UNDO_MS = 10_000;

export interface Pending {
  key: string;
  label: string;
  startedAt: number;
  ms: number;
  phase: "waiting" | "running" | "done" | "failed";
  error?: string;
}

interface Entry extends Pending {
  timer: number;
  run: () => Promise<void>;
  onUndo?: () => void;
  onDone?: () => void;
  onError?: (e: unknown) => void;
}

export function useDeferred() {
  const entries = useRef<Map<string, Entry>>(new Map());
  const [, tick] = useState(0);
  const bump = useCallback(() => tick((n) => n + 1), []);

  const fire = useCallback(async (key: string) => {
    const e = entries.current.get(key);
    if (!e) return;
    window.clearTimeout(e.timer);
    e.phase = "running"; bump();
    try {
      await e.run();
      e.phase = "done"; bump();
      e.onDone?.();
      window.setTimeout(() => { if (entries.current.get(key) === e) { entries.current.delete(key); bump(); } }, 2000);
    } catch (err) {
      e.phase = "failed"; e.error = err instanceof Error ? err.message : "Something went wrong."; bump();
      e.onError?.(err);
      window.setTimeout(() => { if (entries.current.get(key) === e) { entries.current.delete(key); bump(); } }, 6000);
    }
  }, [bump]);

  const schedule = useCallback((key: string, label: string, run: () => Promise<void>, opts: { onUndo?: () => void; onDone?: () => void; onError?: (e: unknown) => void; ms?: number } = {}) => {
    const old = entries.current.get(key);
    if (old) window.clearTimeout(old.timer);
    const ms = opts.ms ?? UNDO_MS;
    const timer = window.setTimeout(() => { void fire(key); }, ms);
    entries.current.set(key, { key, label, startedAt: Date.now(), ms, phase: "waiting", timer, run, onUndo: opts.onUndo, onDone: opts.onDone, onError: opts.onError });
    bump();
  }, [bump, fire]);

  const undo = useCallback((key: string) => {
    const e = entries.current.get(key);
    if (!e || e.phase !== "waiting") return;
    window.clearTimeout(e.timer);
    entries.current.delete(key);
    bump();
    e.onUndo?.();
  }, [bump]);

  const flushAll = useCallback(() => {
    for (const [key, e] of entries.current) if (e.phase === "waiting") void fire(key);
  }, [fire]);

  // Leaving the page must not lose a step the doctor saw as done: the requests go out marked keepalive, which the browser lets finish
  // after the page is gone (a plain request is cancelled; 2 Nov test pass).
  useEffect(() => {
    const onHide = () => whileLeaving(() => {
      for (const e of entries.current.values()) if (e.phase === "waiting") { window.clearTimeout(e.timer); e.phase = "running"; void e.run().catch(() => undefined); }
    });
    window.addEventListener("pagehide", onHide);
    return () => { window.removeEventListener("pagehide", onHide); onHide(); };
  }, []);

  const get = useCallback((key: string): Pending | undefined => entries.current.get(key), []);
  return { schedule, undo, get, flushAll };
}

/** The in-place bar: a tick, the label, a slider that empties over 10 s, and Undo. Announced to screen readers. */
export function UndoBar({ pending, onUndo, className }: { pending: Pending; onUndo: () => void; className?: string }) {
  const { phase, label, ms, error } = pending;
  return (
    <div className={cn("relative overflow-hidden rounded-md border text-sm", phase === "failed" ? "status-bad border-transparent" : "bg-ok-soft text-ok border-transparent", className)} role="status" aria-live="polite">
      <div className="flex items-center gap-2 px-2 py-1.5">
        {phase === "running" ? <Loader2 className="size-4 animate-spin shrink-0" aria-hidden /> : <Check className="size-4 shrink-0" aria-hidden />}
        <span className="flex-1 min-w-0 truncate">
          {phase === "failed" ? `Could not finish: ${error ?? "something went wrong"}` : phase === "done" ? `${label}. Done.` : phase === "running" ? `${label}. Saving` : `${label}. Undo within 10 seconds.`}
        </span>
        {phase === "waiting" ? (
          <button type="button" onClick={onUndo} className="inline-flex items-center gap-1 rounded px-2 py-0.5 font-medium hover:bg-ok/10 active:scale-95 transition focus-visible:outline-2">
            <Undo2 className="size-3.5" aria-hidden /> Undo
          </button>
        ) : null}
      </div>
      {phase === "waiting" ? (
        <div className="absolute inset-x-0 bottom-0 h-0.5 bg-ok/20">
          <div className="h-full bg-ok" style={{ animation: `undo-drain ${ms}ms linear forwards` }} />
        </div>
      ) : null}
      <style>{`@keyframes undo-drain { from { width: 100% } to { width: 0% } }`}</style>
    </div>
  );
}
