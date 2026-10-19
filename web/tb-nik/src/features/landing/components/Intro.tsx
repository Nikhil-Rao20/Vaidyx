// The site's own entrance: the Vaidyx reveal (the mark, then the wordmark) on the page's field, about three seconds, then it
// dissolves into the hero. Plays every time the landing page is opened; a click, a tap or Escape skips it. Reduced motion: the
// finished lockup fades in and out instead of the sweep.
import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { BrandLockup, BrandMark, BrandWord } from "@/components/BrandReveal";
import { SITE } from "../content";

const SPEED = 2;         // the brand file's 6 s sequence at 2x
const LENGTH = 3150;     // ms until the dissolve starts
const LENGTH_STILL = 1700;

export function Intro({ onDone }: { onDone: () => void }) {
  const reduce = useReducedMotion();
  const [show, setShow] = useState(true);
  const finish = useCallback(() => { setShow(false); onDone(); }, [onDone]);
  useEffect(() => {
    const t = window.setTimeout(finish, reduce ? LENGTH_STILL : LENGTH);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") finish(); };
    window.addEventListener("keydown", onKey);
    return () => { window.clearTimeout(t); window.removeEventListener("keydown", onKey); };
  }, [finish, reduce]);
  return (
    <AnimatePresence>
      {show ? (
        <motion.div
          key="intro"
          role="presentation"
          data-testid="site-intro"
          className="fixed inset-0 z-[90] grid place-items-center overflow-hidden"
          style={{ background: "var(--l-bg)" }}
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, scale: 1.04, transition: { duration: 0.75, ease: [0.65, 0, 0.35, 1] } }}
          onClick={finish}
        >
          <span className="l-grain" aria-hidden />
          <motion.span
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 size-[80vmin] -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ background: "radial-gradient(circle, var(--l-glow-teal) 0%, rgba(1, 203, 211, 0) 62%)" }}
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1.6, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
          />
          <motion.div initial={{ opacity: reduce ? 0 : 1 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
            <BrandLockup play={!reduce} still={!!reduce} speed={SPEED}>
              <BrandMark style={{ "--br-mark-w": "clamp(150px, 26vmin, 250px)" } as React.CSSProperties} />
              <BrandWord style={{ "--br-word-h": "clamp(38px, 6.5vmin, 62px)" } as React.CSSProperties} />
            </BrandLockup>
          </motion.div>
          <motion.span className="l-faint absolute bottom-6 right-6 text-xs" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1, duration: 0.5 }}>{SITE.skip}</motion.span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
