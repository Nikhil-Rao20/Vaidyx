// The right inspector: non-modal, 420 px on a 1366 laptop and 520 px at 1920, the page stays scrollable behind it.
// Below 1024 px it fills the screen. Escape closes; focus goes to the title on open and back to the opener on close.
import { useEffect, useRef, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function SidePanel({ open, onClose, title, subtitle, children, footer, width = "normal", testId }: {
  open: boolean; onClose: () => void; title: ReactNode; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode; width?: "normal" | "wide"; testId?: string;
}) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  const opener = useRef<Element | null>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (open) {
      opener.current = document.activeElement;
      const t = window.setTimeout(() => titleRef.current?.focus(), 60);
      return () => window.clearTimeout(t);
    }
    const el = opener.current as HTMLElement | null;
    if (el && typeof el.focus === "function" && document.contains(el)) el.focus();
    return undefined;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    // Escape on a popover inside the panel (Radix, listening on the document) closes the popover first, so by the time the key
    // reaches the window nothing looks open: the capture phase notes that a dialog was open when the key went down, and the panel
    // then stays. The panel itself still listens in the bubble phase, so a control that takes Escape for itself (the mic while
    // listening stops it there) keeps it.
    const hadDialog = new WeakSet<KeyboardEvent>();
    const onDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && document.querySelector("[role=dialog][data-state=open]")) hadDialog.add(e);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || hadDialog.has(e)) return;
      // A dialog on top handles its own Escape.
      if (document.querySelector("[role=dialog][data-state=open]")) return;
      onClose();
    };
    window.addEventListener("keydown", onDown, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onDown, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.aside
          key="side-panel"
          role="complementary"
          aria-label={typeof title === "string" ? title : "Details"}
          data-testid={testId ?? "side-panel"}
          initial={reduce ? { opacity: 0 } : { x: 40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={reduce ? { opacity: 0 } : { x: 40, opacity: 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 38, mass: 0.8 }}
          className={cn(
            "fixed z-[45] inset-0 lg:inset-auto lg:top-0 lg:right-0 lg:h-dvh bg-card border-l border-border flex flex-col",
            "shadow-[var(--shadow-inner)] print:hidden",
            width === "wide" ? "lg:w-[520px] min-[1700px]:w-[640px]" : "lg:w-[420px] min-[1700px]:w-[520px]",
          )}
        >
          <header className="flex items-start gap-2 border-b border-border px-4 py-3">
            <div className="min-w-0 flex-1">
              <h2 ref={titleRef} tabIndex={-1} className="text-base font-bold leading-tight outline-none truncate">{title}</h2>
              {subtitle ? <div className="text-xs text-muted-foreground mt-0.5">{subtitle}</div> : null}
            </div>
            <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close panel" title="Close (Esc)"><X className="size-4" /></Button>
          </header>
          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">{children}</div>
          {footer ? <footer className="border-t border-border px-4 py-3 bg-card">{footer}</footer> : null}
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}
