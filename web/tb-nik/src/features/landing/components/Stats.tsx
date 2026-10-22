// Figures for the problem section: a number that counts up when it scrolls into view, a radial gauge that draws to its share,
// a bar that fills, and the source link. Reduced motion: the finished state.
import { useEffect, useRef } from "react";
import { animate, motion, useInView, useReducedMotion } from "motion/react";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

export function CountUp({ value, decimals = 1, suffix = "%", className, duration = 1.6 }: { value: number; decimals?: number; suffix?: string; className?: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true, amount: 0.6 });
  const reduce = useReducedMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!seen || reduce) { el.textContent = value.toFixed(decimals) + suffix; return; }
    const c = animate(0, value, { duration, ease: [0.22, 1, 0.36, 1], onUpdate: (v) => { el.textContent = v.toFixed(decimals) + suffix; } });
    return () => c.stop();
  }, [seen, reduce, value, decimals, suffix, duration]);
  return <span ref={ref} className={cn("l-figure", className)}>{reduce ? value.toFixed(decimals) + suffix : `0${decimals ? "." + "0".repeat(decimals) : ""}${suffix}`}</span>;
}

export function Gauge({ value, size = 128, stroke = 9, className, children }: { value: number; size?: number; stroke?: number; className?: string; children?: React.ReactNode }) {
  const reduce = useReducedMotion();
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <span className={cn("relative inline-grid place-items-center", className)} style={{ width: size, height: size }} role="img" aria-label={`${value} percent`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--l-surface-2)" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke="url(#l-gauge-grad)" strokeWidth={stroke} strokeLinecap="round" strokeDasharray={c}
          initial={{ strokeDashoffset: reduce ? c * (1 - value / 100) : c }}
          whileInView={{ strokeDashoffset: c * (1 - value / 100) }}
          viewport={{ once: true, amount: 0.6 }}
          transition={{ duration: reduce ? 0 : 1.6, ease: [0.22, 1, 0.36, 1] }}
        />
        <defs>
          <linearGradient id="l-gauge-grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--cyan)" /><stop offset="1" stopColor="var(--violet)" /></linearGradient>
        </defs>
      </svg>
      <span className="absolute inset-0 grid place-items-center">{children}</span>
    </span>
  );
}

export function Bar({ value, className }: { value: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <span className={cn("l-barline block", className)} aria-hidden>
      <motion.i initial={{ scaleX: reduce ? value / 100 : 0 }} whileInView={{ scaleX: value / 100 }} viewport={{ once: true, amount: 0.6 }} transition={{ duration: reduce ? 0 : 1.4, ease: [0.22, 1, 0.36, 1] }} />
    </span>
  );
}

export function SourceLink({ href, label, className }: { href: string; label: string; className?: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className={cn("l-source text-[13px]", className)} aria-label={`Source: ${label}, opens in a new tab`}>
      {label} <ExternalLink className="size-3.5" aria-hidden />
    </a>
  );
}
