// The Vaidyx mark and wordmark as inline SVG, with the official cinematic reveal (brand/animation.html) available as CSS
// classes: wrap the two in <BrandLockup play> and the sequence plays once. Each instance has its own gradient ids, so several
// can sit on one page. Letters follow --br-letter (black on light, the pale blue on dark); the X keeps its gradient.
import { useId, type CSSProperties, type ReactNode } from "react";
import { ICON_BOX, ICON_GRADIENTS, ICON_PATHS, WORD_BOX, WORD_DOTS, WORD_LETTERS, WORD_X } from "@/components/brand-paths";
import { cn } from "@/lib/utils";
import "./brand-reveal.css";

/** The icon with its three parts (for the reveal) and the light sweep. */
export function BrandMark({ className, style }: { className?: string; style?: CSSProperties }) {
  const id = useId().replace(/:/g, "");
  const g = ICON_GRADIENTS;
  return (
    <div className={cn("br-mark", className)} style={style} aria-hidden>
      <svg viewBox={`${ICON_BOX.x} ${ICON_BOX.y} ${ICON_BOX.w} ${ICON_BOX.h}`} xmlns="http://www.w3.org/2000/svg">
        <defs>
          {g.map((gr, i) => (
            <linearGradient key={i} id={`${id}-g${i}`} gradientUnits="userSpaceOnUse" x1={gr.x1} y1={gr.y1} x2={gr.x2} y2={gr.y2}>
              <stop offset="0" stopColor={gr.from} />
              <stop offset="1" stopColor={gr.to} />
            </linearGradient>
          ))}
          <clipPath id={`${id}-clip`}>
            {ICON_PATHS.map((d, i) => <path key={i} d={d} />)}
          </clipPath>
          <linearGradient id={`${id}-shine`} gradientUnits="objectBoundingBox" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#fff" stopOpacity="0" />
            <stop offset="0.3" stopColor="#fff" stopOpacity="0" />
            <stop offset="0.48" stopColor="#fff" stopOpacity="0.85" />
            <stop offset="0.52" stopColor="#67DCF3" stopOpacity="0.55" />
            <stop offset="0.7" stopColor="#fff" stopOpacity="0" />
            <stop offset="1" stopColor="#fff" stopOpacity="0" />
          </linearGradient>
        </defs>
        <g className="br-icon">
          <g className="br-v"><path fill={`url(#${id}-g0)`} d={ICON_PATHS[0]} /></g>
          <g className="br-x2"><path fill={`url(#${id}-g1)`} d={ICON_PATHS[1]} /></g>
          <g className="br-x1"><path fill={`url(#${id}-g2)`} d={ICON_PATHS[2]} /></g>
        </g>
        <rect className="br-shine" clipPath={`url(#${id}-clip)`} x="100" y="180" width="220" height="520" fill={`url(#${id}-shine)`} style={{ mixBlendMode: "screen", pointerEvents: "none" }} />
      </svg>
    </div>
  );
}

/** The wordmark (letters, the two violet dots, the gradient X) with its light sweep. */
export function BrandWord({ className, style }: { className?: string; style?: CSSProperties }) {
  const id = useId().replace(/:/g, "");
  return (
    <div className={cn("br-word", className)} style={style} role="img" aria-label="Vaidyx">
      <svg viewBox={`${WORD_BOX.x} ${WORD_BOX.y} ${WORD_BOX.w} ${WORD_BOX.h}`} xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id={`${id}-xfill`} gradientUnits="userSpaceOnUse" x1="1111.103" y1="566.711" x2="1019.877" y2="586.751" gradientTransform="translate(-68.305,280.772)">
            <stop offset="0" style={{ stopColor: "var(--br-x-from)" }} />
            <stop offset="1" style={{ stopColor: "var(--br-x-to)" }} />
          </linearGradient>
          <linearGradient id={`${id}-xedge`} gradientUnits="userSpaceOnUse" x1="1111.103" y1="566.711" x2="1140.494" y2="552.82" gradientTransform="translate(-68.305,280.772)">
            <stop offset="0" style={{ stopColor: "var(--br-edge)" }} stopOpacity="0.83" />
            <stop offset="1" stopColor="#000" stopOpacity="0" />
          </linearGradient>
          <clipPath id={`${id}-wclip`}>
            {WORD_LETTERS.map((d, i) => <path key={i} d={d} />)}
            {WORD_DOTS.map((d, i) => <path key={`d${i}`} d={d} />)}
            <path d={WORD_X} />
          </clipPath>
          <linearGradient id={`${id}-wsweep`} gradientUnits="userSpaceOnUse" x1="-100" y1="850" x2="300" y2="850">
            <stop offset="0" stopColor="#fff" stopOpacity="0" />
            <stop offset="0.2" stopColor="#fff" stopOpacity="0" />
            <stop offset="0.4" stopColor="#fff" stopOpacity="0.35" />
            <stop offset="0.5" stopColor="#fff" stopOpacity="0.45" />
            <stop offset="0.6" stopColor="#fff" stopOpacity="0.35" />
            <stop offset="0.8" stopColor="#fff" stopOpacity="0" />
            <stop offset="1" stopColor="#fff" stopOpacity="0" />
          </linearGradient>
        </defs>
        <g className="br-word-group">
          {WORD_LETTERS.map((d, i) => <path key={i} className="br-letter" d={d} />)}
          {WORD_DOTS.map((d, i) => <path key={`d${i}`} fill="#8f64fd" d={d} />)}
          <path fill={`url(#${id}-xfill)`} stroke={`url(#${id}-xedge)`} d={WORD_X} />
        </g>
        <rect className="br-word-shine" clipPath={`url(#${id}-wclip)`} x="-100" y="700" width="400" height="340" fill={`url(#${id}-wsweep)`} style={{ mixBlendMode: "screen" }} />
      </svg>
    </div>
  );
}

/**
 * The stage for the reveal. `play` starts the sequence; `still` shows the finished lockup with no animation (reduced motion, or a
 * static logo). `speed` 1 is the brand file's 6 s; the splash uses 1.35. `onDark` forces the dark-theme letters.
 */
export function BrandLockup({ play, still, speed = 1, onDark, className, style, children }: { play?: boolean; still?: boolean; speed?: number; onDark?: boolean; className?: string; style?: CSSProperties; children: ReactNode }) {
  return (
    <div className={cn("br", play && !still && "br-run", still && "br-still", onDark && "br-on-dark", className)} style={{ ...style, "--br-ts": speed } as CSSProperties}>
      <div className="br-lockup">{children}</div>
    </div>
  );
}

/** How long the reveal takes at a given speed (the wordmark's light sweep ends last), in milliseconds. */
export function revealDuration(speed = 1): number {
  return Math.round((6000 / speed));
}
