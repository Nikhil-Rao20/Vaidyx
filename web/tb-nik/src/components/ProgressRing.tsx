// A small ring that fills to a percentage with a short ease when it appears or changes (the Case File's readiness). Colour by
// state: teal while filling, the ok green at 100. Reduced motion: no sweep.
import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

export function ProgressRing({ value, size = 40, stroke = 4, className, label, done }: { value: number; size?: number; stroke?: number; className?: string; label?: string; done?: boolean }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const reduce = useReducedMotion();
  const colour = done || v >= 100 ? "var(--ok)" : "var(--primary)";
  return (
    <span className={cn("relative inline-grid place-items-center", className)} style={{ width: size, height: size }} role="img" aria-label={label ?? `${v} percent`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={colour} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: reduce ? c * (1 - v / 100) : c }}
          animate={{ strokeDashoffset: c * (1 - v / 100) }}
          transition={{ duration: reduce ? 0 : 0.9, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <span className="absolute text-[10px] font-semibold tabular-nums text-foreground">{v}%</span>
    </span>
  );
}
