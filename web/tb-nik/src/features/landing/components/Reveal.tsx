// Scroll reveals for the landing page: a block rises as it enters (once), groups stagger their children, a title arrives word by
// word. Under reduced motion everything is simply there.
import { Children, useRef, type ReactNode } from "react";
import { motion, useInView, useReducedMotion, type Variants } from "motion/react";
import { cn } from "@/lib/utils";

export const L_EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

export function Reveal({ children, className, delay = 0, y = 28, amount = 0.25, blur = false, once = true, style, testId }: { children: ReactNode; className?: string; delay?: number; y?: number; amount?: number; blur?: boolean; once?: boolean; style?: React.CSSProperties; testId?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className} style={style} data-testid={testId}>{children}</div>;
  return (
    <motion.div
      className={className}
      style={style}
      data-testid={testId}
      initial={{ opacity: 0, y, filter: blur ? "blur(8px)" : "blur(0px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once, amount, margin: "0px 0px -6% 0px" }}
      transition={{ duration: 0.85, delay, ease: L_EASE }}
    >
      {children}
    </motion.div>
  );
}

const group: Variants = { hidden: {}, show: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } } };
const item: Variants = { hidden: { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: 0.75, ease: L_EASE } } };

/** Children arrive one after the other when the group scrolls into view. Each direct child is wrapped. */
export function Stagger({ children, className, amount = 0.2, itemClassName }: { children: ReactNode; className?: string; amount?: number; itemClassName?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{Children.map(children, (c) => <div className={itemClassName}>{c}</div>)}</div>;
  return (
    <motion.div className={className} variants={group} initial="hidden" whileInView="show" viewport={{ once: true, amount, margin: "0px 0px -6% 0px" }}>
      {Children.map(children, (c) => <motion.div variants={item} className={itemClassName}>{c}</motion.div>)}
    </motion.div>
  );
}

/** A line of text that arrives word by word (titles). With `inView` it waits until the line itself scrolls into view: the
 * wrapper is observed, never the clipped, translated words, which would never intersect. `start` delays the whole line. */
export function Words({ text, className, start = 0, step = 0.055, inView = false }: { text: string; className?: string; start?: number; step?: number; inView?: boolean }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true, amount: 0.4, margin: "0px 0px -6% 0px" });
  const words = text.split(" ");
  if (reduce) return <span className={className}>{text}</span>;
  const on = !inView || seen;
  return (
    <span ref={ref} className={cn("inline", className)} aria-label={text}>
      {words.map((w, i) => (
        <span key={i} className="inline-block overflow-hidden align-bottom pb-[0.08em] -mb-[0.08em]" aria-hidden>
          <motion.span
            className="inline-block will-change-transform"
            initial={{ y: "110%", opacity: 0, filter: "blur(6px)" }}
            animate={on ? { y: 0, opacity: 1, filter: "blur(0px)" } : { y: "110%", opacity: 0, filter: "blur(6px)" }}
            transition={{ duration: 0.9, delay: start + i * step, ease: L_EASE }}
          >
            {w}
          </motion.span>
          {i < words.length - 1 ? "\u00a0" : ""}
        </span>
      ))}
    </span>
  );
}
