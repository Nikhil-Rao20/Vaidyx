import { forwardRef, type ComponentProps, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ActionState } from "@/hooks/useAsyncAction";
import { cn } from "@/lib/utils";

/**
 * A button with every state: default, hover, pressed (scale), disabled, loading (spinner, aria-busy) and done
 * (turns into a tick with the word given, e.g. "Sent", announced to screen readers).
 */
export const ActionButton = forwardRef<HTMLButtonElement, ComponentProps<typeof Button> & {
  state?: ActionState;
  doneText?: string;
  loadingText?: string;
  icon?: ReactNode;
}>(function ActionButton({ state = "idle", doneText = "Done", loadingText, icon, children, className, disabled, ...props }, ref) {
  const busy = state === "loading";
  const done = state === "done";
  return (
    <Button
      ref={ref}
      {...props}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      data-state={state}
      className={cn("relative overflow-hidden transition-transform active:scale-[0.97] hover:bg-primary-hover data-[variant=outline]:hover:bg-accent", done && "bg-ok text-white hover:bg-ok", className)}
    >
      <AnimatePresence mode="wait" initial={false}>
        {busy ? (
          <motion.span key="busy" className="inline-flex items-center gap-2" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.15 }}>
            <Loader2 className="size-4 animate-spin" aria-hidden /> {loadingText ?? children}
          </motion.span>
        ) : done ? (
          <motion.span key="done" className="inline-flex items-center gap-2" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ type: "spring", stiffness: 500, damping: 30 }} role="status" aria-live="polite">
            <Check className="size-4" aria-hidden /> {doneText}
          </motion.span>
        ) : (
          <motion.span key="idle" className="inline-flex items-center gap-2" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
            {icon}{children}
          </motion.span>
        )}
      </AnimatePresence>
    </Button>
  );
});
