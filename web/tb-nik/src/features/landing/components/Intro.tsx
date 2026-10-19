// The site's own entrance: the lockup, large, on the plain field, arriving in the way chosen in intro/options.tsx; then it
// dissolves into the hero. Plays once per page load, the first time the Product page is shown: a reload plays it again, moving
// from About back to Product does not. A click, a tap or Escape skips it.
import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { SITE } from "../content";
import { INTROS } from "../intro/options";

export const CHOSEN = "A";   // the owner picks from /lab
const LENGTH_STILL = 1700;
let played = false;          // per page load, not per visit of the route

export function Intro({ onDone }: { onDone: () => void }) {
  const reduce = useReducedMotion();
  const [show, setShow] = useState(() => !played);
  const finish = useCallback(() => { setShow(false); onDone(); }, [onDone]);
  const option = INTROS.find((o) => o.key === CHOSEN) ?? INTROS[0];
  useEffect(() => {
    if (!show) { onDone(); return; }
    played = true;
    const t = window.setTimeout(finish, reduce ? LENGTH_STILL : option.length);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") finish(); };
    window.addEventListener("keydown", onKey);
    return () => { window.clearTimeout(t); window.removeEventListener("keydown", onKey); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const Scene = option.Component;
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
          <div className="landing-intro-stage absolute inset-0 grid place-items-center"><Scene /></div>
          <motion.span className="l-faint absolute bottom-6 right-6 text-xs" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1, duration: 0.5 }}>{SITE.skip}</motion.span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
