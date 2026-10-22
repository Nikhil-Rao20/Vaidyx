import { motion } from "motion/react";
import { useTextSize } from "@/hooks/useTheme";
import type { TextSize } from "@/lib/appearance";
import { cn } from "@/lib/utils";

const SIZES: Array<{ id: TextSize; label: string; sample: string }> = [
  { id: "small", label: "Small", sample: "text-xs" },
  { id: "normal", label: "Normal", sample: "text-sm" },
  { id: "large", label: "Large", sample: "text-base" },
];

/** Three sizes as a segmented control; the whole page changes at once (html font size). */
export function TextSizeToggle({ className, saveToProfile = true }: { className?: string; saveToProfile?: boolean }) {
  const { size, setSize } = useTextSize(saveToProfile);
  return (
    <div className={cn("inline-flex rounded-md border border-border bg-muted p-0.5", className)} role="radiogroup" aria-label="Text size">
      {SIZES.map((s) => {
        const on = s.id === size;
        return (
          <button
            key={s.id}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => setSize(s.id)}
            className={cn("relative h-8 min-w-14 rounded-[6px] px-2.5 font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring active:scale-95", s.sample, on ? "text-foreground" : "text-muted-foreground hover:text-foreground")}
          >
            {on ? <motion.span layoutId="text-size-pill" className="absolute inset-0 rounded-[6px] bg-card shadow-[var(--shadow-outer)]" transition={{ type: "spring", stiffness: 500, damping: 40 }} aria-hidden /> : null}
            <span className="relative">{s.label}</span>
          </button>
        );
      })}
    </div>
  );
}
