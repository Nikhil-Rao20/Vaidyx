// Pieces the safety layouts share: a badge colour per principle, its icon, and the shield drawing.
import { motion, useReducedMotion } from "motion/react";
import { Eye, Landmark, ListChecks, LockKeyhole, Quote, UserRoundCheck, type LucideIcon } from "lucide-react";
import { ICON_SRC } from "@/components/Wordmark";

export const ICONS: Record<string, LucideIcon> = { people: UserRoundCheck, sources: Quote, scans: Eye, onsite: LockKeyhole, india: Landmark, audit: ListChecks };
export const BADGES: Array<{ bg: string; shadow: string }> = [
  { bg: "linear-gradient(145deg, #0a8fb0, #0a6a86)", shadow: "rgba(10,106,134,0.5)" },
  { bg: "linear-gradient(145deg, #8f64fd, #5b3fc4)", shadow: "rgba(91,63,196,0.5)" },
  { bg: "linear-gradient(145deg, #1b7fb5, #0b4e74)", shadow: "rgba(11,78,116,0.5)" },
  { bg: "linear-gradient(145deg, #5fdcd6, #1fb9cc)", shadow: "rgba(31,185,204,0.5)" },
  { bg: "linear-gradient(145deg, #0b4e74, #00183c)", shadow: "rgba(0,24,60,0.5)" },
  { bg: "linear-gradient(145deg, #5c6b7c, #2b3645)", shadow: "rgba(43,54,69,0.5)" },
];

/** A shield with the Vaidyx mark inside and three orbit arcs; draws itself once when it scrolls into view. */
export function Shield({ className }: { className?: string }) {
  const r = useReducedMotion();
  const E: [number, number, number, number] = [0.22, 1, 0.36, 1];
  return (
    <svg viewBox="0 0 320 340" className={className} role="img" aria-label="A shield with the Vaidyx mark">
      <defs>
        <linearGradient id="l-shield-fill" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--cyan)" stopOpacity="0.22" /><stop offset="1" stopColor="var(--violet)" stopOpacity="0.18" /></linearGradient>
        <linearGradient id="l-shield-edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--cyan)" /><stop offset="1" stopColor="var(--violet)" /></linearGradient>
      </defs>
      {[150, 128, 106].map((rad, i) => (
        <motion.circle key={rad} cx={160} cy={170} r={rad} fill="none" stroke="var(--l-line-2)" strokeWidth={1} strokeDasharray={i === 1 ? "3 6" : "1 5"} initial={r ? false : { opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ delay: 0.2 + i * 0.1, duration: 0.8, ease: E }} style={{ transformOrigin: "160px 170px" }} />
      ))}
      <motion.path d="M 160 42 L 246 74 V 160 C 246 222 206 262 160 282 C 114 262 74 222 74 160 V 74 Z" fill="url(#l-shield-fill)" stroke="url(#l-shield-edge)" strokeWidth={2.5} strokeLinejoin="round" initial={r ? false : { pathLength: 0, opacity: 0 }} whileInView={{ pathLength: 1, opacity: 1 }} viewport={{ once: true }} transition={{ duration: 1.4, ease: E }} />
      <motion.image href={ICON_SRC} x={112} y={126} width={96} height={72} initial={r ? false : { opacity: 0, scale: 0.8 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ delay: 0.9, duration: 0.6, ease: E }} style={{ transformOrigin: "160px 162px" }} />
      <motion.g initial={r ? false : { opacity: 0, y: 6 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 1.2, duration: 0.5 }}>
        <rect x={118} y={214} width={84} height={26} rx={13} fill="var(--l-surface)" stroke="var(--l-line)" />
        <path d="M 134 227 l 6 6 l 11 -12" fill="none" stroke="var(--l-ok)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
        <text x={158} y={231.5} fontSize={11.5} fontWeight={600} fill="var(--l-fg)" fontFamily="inherit">Doctor-led</text>
      </motion.g>
    </svg>
  );
}
