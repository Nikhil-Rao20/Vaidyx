// Pieces the entrance options share: the wordmark with each letter animated on its own (rising, or drawn as a line then
// filled), and the mark drawn as a line then filled. Built from the brand's own path data.
import { useId } from "react";
import { motion, useReducedMotion } from "motion/react";
import { ICON_BOX, ICON_GRADIENTS, ICON_PATHS, WORD_BOX, WORD_DOTS, WORD_LETTERS, WORD_X } from "@/components/brand-paths";

export const E: [number, number, number, number] = [0.22, 1, 0.36, 1];
const svgStyle = { transformBox: "fill-box", transformOrigin: "center" } as const;

/** The wordmark, letter by letter. `mode` rise: each letter comes up from below; draw: outlines draw, then fill. */
export function AnimatedWord({ mode, delay = 0, step = 0.09, className, style }: { mode: "rise" | "draw"; delay?: number; step?: number; className?: string; style?: React.CSSProperties }) {
  const id = useId().replace(/:/g, "");
  const r = useReducedMotion();
  const parts: Array<{ d: string; kind: "letter" | "dot" | "x" }> = [
    ...WORD_LETTERS.slice(0, 2).map((d) => ({ d, kind: "letter" as const })),
    { d: WORD_LETTERS[2], kind: "letter" }, { d: WORD_DOTS[0], kind: "dot" },
    { d: WORD_LETTERS[3], kind: "letter" }, { d: WORD_LETTERS[4], kind: "letter" }, { d: WORD_DOTS[1], kind: "dot" },
    { d: WORD_X, kind: "x" },
  ];
  return (
    <svg viewBox={`${WORD_BOX.x} ${WORD_BOX.y} ${WORD_BOX.w} ${WORD_BOX.h}`} className={className} role="img" aria-label="Vaidyx" style={{ overflow: "visible", ...style }}>
      <defs>
        <linearGradient id={`${id}-x`} gradientUnits="userSpaceOnUse" x1="1111.103" y1="566.711" x2="1019.877" y2="586.751" gradientTransform="translate(-68.305,280.772)">
          <stop offset="0" style={{ stopColor: "var(--br-x-from, #009eb1)" }} /><stop offset="1" style={{ stopColor: "var(--br-x-to, #000)" }} />
        </linearGradient>
      </defs>
      {parts.map((p, i) => {
        const fill = p.kind === "dot" ? "#8f64fd" : p.kind === "x" ? `url(#${id}-x)` : "var(--br-letter, #000)";
        const t = delay + i * step;
        if (r) return <path key={i} d={p.d} fill={fill} />;
        if (mode === "rise") {
          return <motion.path key={i} d={p.d} fill={fill} style={svgStyle} initial={{ opacity: 0, y: p.kind === "dot" ? -60 : 70, scale: p.kind === "dot" ? 0.4 : 1 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ delay: t, duration: p.kind === "dot" ? 0.6 : 0.8, ease: p.kind === "dot" ? [0.34, 1.56, 0.64, 1] : E }} />;
        }
        return (
          <g key={i}>
            <motion.path d={p.d} fill="none" stroke={p.kind === "dot" ? "#8f64fd" : "var(--l-accent, #0a6a86)"} strokeWidth={3} initial={{ pathLength: 0, opacity: 1 }} animate={{ pathLength: 1, opacity: [1, 1, 0] }} transition={{ pathLength: { delay: t, duration: 0.9, ease: E }, opacity: { delay: t + 0.9, duration: 0.6, times: [0, 0.3, 1] } }} />
            <motion.path d={p.d} fill={fill} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: t + 0.75, duration: 0.6 }} />
          </g>
        );
      })}
    </svg>
  );
}

/** The mark drawn as a line, part by part, then filled with its gradients. */
export function DrawnMark({ delay = 0, className, style }: { delay?: number; className?: string; style?: React.CSSProperties }) {
  const id = useId().replace(/:/g, "");
  const r = useReducedMotion();
  return (
    <svg viewBox={`${ICON_BOX.x} ${ICON_BOX.y} ${ICON_BOX.w} ${ICON_BOX.h}`} className={className} aria-hidden style={{ overflow: "visible", ...style }}>
      <defs>
        {ICON_GRADIENTS.map((g, i) => <linearGradient key={i} id={`${id}-g${i}`} gradientUnits="userSpaceOnUse" x1={g.x1} y1={g.y1} x2={g.x2} y2={g.y2}><stop offset="0" stopColor={g.from} /><stop offset="1" stopColor={g.to} /></linearGradient>)}
      </defs>
      {ICON_PATHS.map((d, i) => {
        const t = delay + i * 0.25;
        if (r) return <path key={i} d={d} fill={`url(#${id}-g${i})`} />;
        return (
          <g key={i}>
            <motion.path d={d} fill="none" stroke={`url(#${id}-g${i})`} strokeWidth={6} strokeLinejoin="round" initial={{ pathLength: 0, opacity: 1 }} animate={{ pathLength: 1, opacity: [1, 1, 0] }} transition={{ pathLength: { delay: t, duration: 1.1, ease: E }, opacity: { delay: t + 1.1, duration: 0.6, times: [0, 0.3, 1] } }} />
            <motion.path d={d} fill={`url(#${id}-g${i})`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: t + 0.95, duration: 0.6 }} />
          </g>
        );
      })}
    </svg>
  );
}
