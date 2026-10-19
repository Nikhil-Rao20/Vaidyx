// The site's own entrance: the Vaidyx reveal (mark, then wordmark) on the dark field, about three seconds, then it dissolves into
// the hero. Plays on every page load of the landing page, not on in-app navigation back to it; a click, a tap or Escape skips it.
// Reduced motion: no intro.
import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { BrandLockup, BrandMark, BrandWord } from "@/components/BrandReveal";
import { SITE } from "../content";

const SPEED = 2;         // the brand file's 6 s sequence at 2x
const LENGTH = 3150;     // ms until the dissolve starts
let played = false;      // once per page load

export function Intro({ onDone }: { onDone: () => void }) {
  const reduce = useReducedMotion();
  const [show, setShow] = useState(() => !played && !reduce);
  const finish = useCallback(() => { setShow(false); onDone(); }, [onDone]);
  useEffect(() => {
    if (!show) { onDone(); return; }
    played = true;
    const t = window.setTimeout(finish, LENGTH);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") finish(); };
    window.addEventListener("keydown", onKey);
    return () => { window.clearTimeout(t); window.removeEventListener("keydown", onKey); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <AnimatePresence>
      {show ? (
        <motion.div
          key="intro"
          role="presentation"
          data-testid="site-intro"
          className="l-ink fixed inset-0 z-[90] grid place-items-center overflow-hidden"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, scale: 1.04, transition: { duration: 0.75, ease: [0.65, 0, 0.35, 1] } }}
          onClick={finish}
        >
          <span className="l-grain" aria-hidden />
          <motion.span
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 size-[80vmin] -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ background: "radial-gradient(circle, rgba(1, 203, 211, 0.22) 0%, rgba(1, 203, 211, 0) 62%)" }}
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1.6, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
          />
          <BrandLockup play speed={SPEED} onDark>
            <BrandMark style={{ "--br-mark-w": "clamp(150px, 26vmin, 250px)" } as React.CSSProperties} />
            <BrandWord style={{ "--br-word-h": "clamp(38px, 6.5vmin, 62px)" } as React.CSSProperties} />
          </BrandLockup>
          <motion.span className="absolute bottom-6 right-6 text-xs text-white/45" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1, duration: 0.5 }}>{SITE.skip}</motion.span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
