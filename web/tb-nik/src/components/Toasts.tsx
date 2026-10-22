// Global toasts (sonner) with a screen-reader announcement for every message, and the Undo toast: "Sent" with a tick,
// a 10 s slider and an Undo button for the steps that can be taken back.
import { useEffect, useState } from "react";
import { Toaster, toast } from "sonner";
import { motion } from "motion/react";
import { Check, CircleAlert, Info, Undo2, X } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { useIsDesktop } from "@/hooks/useMediaQuery";

let liveRegion: HTMLDivElement | null = null;

/** Writes the text into an aria-live region so assistive tech hears every toast, whatever sonner renders. */
export function announce(text: string, mode: "polite" | "assertive" = "polite") {
  if (typeof document === "undefined") return;
  if (!liveRegion) {
    liveRegion = document.createElement("div");
    liveRegion.className = "sr-only";
    liveRegion.setAttribute("aria-atomic", "true");
    document.body.appendChild(liveRegion);
  }
  liveRegion.setAttribute("aria-live", mode);
  liveRegion.textContent = "";
  window.setTimeout(() => { if (liveRegion) liveRegion.textContent = text; }, 30);
}

export const notify = {
  success(text: string, description?: string) { announce(text); return toast.success(text, { description }); },
  info(text: string, description?: string) { announce(text); return toast(text, { description, icon: <Info className="size-4" aria-hidden /> }); },
  error(text: string, description?: string) { announce(text, "assertive"); return toast.error(text, { description, duration: 8000 }); },
  dismiss(id?: string | number) { toast.dismiss(id); },
};

/** The in-place "Sent, Undo" toast. `onUndo` runs when pressed in time; `onExpire` after the slider ends untouched. */
export function undoToast({ text, seconds = 10, onUndo, onExpire }: { text: string; seconds?: number; onUndo: () => Promise<unknown> | unknown; onExpire?: () => void }) {
  announce(`${text}. Undo within ${seconds} seconds.`);
  const id = toast.custom((tid) => <UndoToast id={tid} text={text} seconds={seconds} onUndo={onUndo} onExpire={onExpire} />, { duration: seconds * 1000 });
  return id;
}

export function UndoToast({ id, text, seconds, onUndo, onExpire }: { id: string | number; text: string; seconds: number; onUndo: () => Promise<unknown> | unknown; onExpire?: () => void }) {
  const [state, setState] = useState<"ticking" | "undoing" | "undone" | "failed">("ticking");
  useEffect(() => {
    if (state !== "ticking") return;
    const t = window.setTimeout(() => onExpire?.(), seconds * 1000);
    return () => window.clearTimeout(t);
  }, [state, seconds, onExpire]);
  const undo = async () => {
    setState("undoing");
    try {
      await onUndo();
      setState("undone");
      announce("Undone");
      window.setTimeout(() => toast.dismiss(id), 900);
    } catch {
      setState("failed");
    }
  };
  return (
    <div className="surface-inner flex w-[min(92vw,360px)] items-center gap-3 p-3" role="status">
      <span className="grid size-7 shrink-0 place-items-center rounded-full status-ok"><Check className="size-4" aria-hidden /></span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{state === "undone" ? "Undone" : state === "failed" ? "Could not undo" : text}</p>
        {state === "ticking" ? (
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted" aria-hidden>
            <motion.div className="h-full bg-primary" initial={{ width: "100%" }} animate={{ width: "0%" }} transition={{ duration: seconds, ease: "linear" }} />
          </div>
        ) : null}
      </div>
      {state === "ticking" || state === "undoing" ? (
        <button type="button" onClick={undo} disabled={state === "undoing"} className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs font-medium hover:bg-accent active:scale-95 disabled:opacity-50">
          <Undo2 className="size-3.5" aria-hidden /> Undo
        </button>
      ) : null}
      <button type="button" onClick={() => toast.dismiss(id)} className="rounded-md p-1 text-muted-foreground hover:text-foreground" aria-label="Close">
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}

/** Mount once in the shell. Bottom right on a laptop, top centre on a phone (above the Dock). */
export function Toasts() {
  const { theme } = useTheme(false);
  const desktop = useIsDesktop();
  return (
    <Toaster
      theme={theme}
      position={desktop ? "bottom-right" : "top-center"}
      closeButton
      visibleToasts={4}
      icons={{ success: <Check className="size-4" aria-hidden />, error: <CircleAlert className="size-4" aria-hidden />, info: <Info className="size-4" aria-hidden /> }}
      toastOptions={{ classNames: { toast: "font-sans" } }}
      style={{ "--normal-bg": "var(--popover)", "--normal-text": "var(--popover-foreground)", "--normal-border": "var(--border)", "--border-radius": "var(--radius)" } as React.CSSProperties}
    />
  );
}
