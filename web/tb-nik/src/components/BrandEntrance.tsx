// The Vaidyx entrance (the owner's choice, 20 Oct): the brand's own reveal, large, on a plain field, then it dissolves into the
// page beneath. Used by the website's first load, after a sign-out, and (with its own morph) after a sign-in. A click, a tap or
// Escape skips it. Reduced motion: the finished lockup fades in and out instead of the sweep.
import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { BrandLockup, BrandMark, BrandWord } from "@/components/BrandReveal";

export const ENTRANCE_SPEED = 1.35;       // the brand file's 6 s sequence at 1.35x, the same pace as the sign-in entrance
export const ENTRANCE_LENGTH = 4600;      // ms until the dissolve starts
export const ENTRANCE_STILL = 1700;
export const MARK_W = "clamp(170px, 30vmin, 300px)";
export const WORD_H = "clamp(64px, 11vmin, 118px)";

export function BrandEntrance({ onDone, background = "var(--background)", tagline, testId = "brand-entrance", skipLabel = "Click to skip" }: { onDone: () => void; background?: string; tagline?: string; testId?: string; skipLabel?: string }) {
  const reduce = useReducedMotion();
  const [show, setShow] = useState(true);
  const finish = useCallback(() => { setShow(false); onDone(); }, [onDone]);
  useEffect(() => {
    const t = window.setTimeout(finish, reduce ? ENTRANCE_STILL : ENTRANCE_LENGTH);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") finish(); };
    window.addEventListener("keydown", onKey);
    return () => { window.clearTimeout(t); window.removeEventListener("keydown", onKey); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <AnimatePresence>
      {show ? (
        <motion.div
          key="entrance"
          role="presentation"
          data-testid={testId}
          className="fixed inset-0 z-[90] grid place-items-center overflow-hidden"
          style={{ background }}
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, scale: 1.04, transition: { duration: 0.75, ease: [0.65, 0, 0.35, 1] } }}
          onClick={finish}
        >
          <motion.div initial={{ opacity: reduce ? 0 : 1 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
            <BrandLockup play={!reduce} still={!!reduce} speed={ENTRANCE_SPEED}>
              <BrandMark style={{ "--br-mark-w": MARK_W } as React.CSSProperties} />
              <BrandWord style={{ "--br-word-h": WORD_H } as React.CSSProperties} />
              {tagline ? (
                <motion.p className="text-[13px] font-medium uppercase text-brand" initial={{ opacity: 0, letterSpacing: "0.55em", y: 6 }} animate={{ opacity: 0.8, letterSpacing: "0.3em", y: 0 }} transition={{ delay: reduce ? 0.2 : 1.9, duration: 0.9, ease: "easeOut" }}>{tagline}</motion.p>
              ) : null}
            </BrandLockup>
          </motion.div>
          <motion.span className="absolute bottom-6 right-6 text-xs text-muted-foreground" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1, duration: 0.5 }}>{skipLabel}</motion.span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
