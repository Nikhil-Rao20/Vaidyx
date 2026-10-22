import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";

export type ActionState = "idle" | "loading" | "done" | "error";

export interface AsyncAction<A extends unknown[], R> {
  state: ActionState;
  error: string | null;
  run: (...args: A) => Promise<R | undefined>;
  reset: () => void;
}

export function errorMessage(e: unknown, fallback = "Something went wrong."): string {
  if (e instanceof ApiError) return e.message || fallback;
  if (e instanceof Error) return e.message || fallback;
  return fallback;
}

/**
 * A button's life: idle -> loading -> done (shown for `doneMs`, then idle again) or error (message kept until the next try).
 * The page passes the async work; the button reads `state`.
 */
export function useAsyncAction<A extends unknown[], R>(fn: (...args: A) => Promise<R>, opts: { doneMs?: number; onError?: (msg: string) => void } = {}): AsyncAction<A, R> {
  const [state, setState] = useState<ActionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; if (timer.current) window.clearTimeout(timer.current); }, []);
  const reset = useCallback(() => { setState("idle"); setError(null); }, []);
  const run = useCallback(async (...args: A) => {
    if (state === "loading") return undefined;
    setState("loading");
    setError(null);
    try {
      const r = await fn(...args);
      if (!alive.current) return r;
      setState("done");
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => { if (alive.current) setState("idle"); }, opts.doneMs ?? 2000);
      return r;
    } catch (e) {
      if (!alive.current) return undefined;
      const msg = errorMessage(e);
      setState("error");
      setError(msg);
      opts.onError?.(msg);
      return undefined;
    }
  }, [fn, state, opts]);
  return { state, error, run, reset };
}
