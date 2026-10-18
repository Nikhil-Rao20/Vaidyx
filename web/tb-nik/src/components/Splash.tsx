// The Vaidyx splash after a sign-in (the main app shows the same sequence): the icon pops in with a glow, the wordmark rises,
// the product name spreads. Shown once per sign-in (sessionStorage flag set by the sign-in page), 1.6 s, skippable, never
// on a reload. Reduced motion: a short fade only.
import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { VaidyxIcon, VaidyxWordmark } from "@/components/Wordmark";

const FLAG = "tbnik.splash";

export function requestSplash() {
  try { sessionStorage.setItem(FLAG, "1"); } catch { /* no storage */ }
}

function takeFlag(): boolean {
  try {
    const v = sessionStorage.getItem(FLAG) === "1";
    if (v) sessionStorage.removeItem(FLAG);
    return v;
  } catch { return false; }
}

export function Splash() {
  const [show, setShow] = useState(() => takeFlag());
  const reduce = useReducedMotion();
  useEffect(() => {
    if (!show) return;
    const t = window.setTimeout(() => setShow(false), reduce ? 500 : 1700);
    return () => window.clearTimeout(t);
  }, [show, reduce]);
  return (
    <AnimatePresence>
      {show ? (
        <motion.div
          key="splash"
          role="presentation"
          className="fixed inset-0 z-[100] grid place-items-center bg-background"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.35 } }}
          onClick={() => setShow(false)}
        >
          <div className="flex flex-col items-center gap-5">
            <motion.div
              className="brand-glow"
              initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.5, rotate: -10 }}
              animate={reduce ? { opacity: 1 } : { opacity: 1, scale: 1, rotate: 0 }}
              transition={{ duration: 0.8, ease: [0.34, 1.56, 0.64, 1] }}
            >
              <VaidyxIcon className="h-[72px]" />
            </motion.div>
            <motion.div initial={{ opacity: 0, y: reduce ? 0 : 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.45, ease: "easeOut" }}>
              <VaidyxWordmark className="h-14" />
            </motion.div>
            <motion.p
              className="text-[13px] font-medium uppercase text-brand"
              initial={{ opacity: 0, letterSpacing: "0.5em" }}
              animate={{ opacity: 0.75, letterSpacing: "0.28em" }}
              transition={{ duration: 0.8, delay: 0.9, ease: "easeOut" }}
            >
              Tumour Board
            </motion.p>
          </div>
          <span className="absolute bottom-6 right-6 text-xs text-muted-foreground">Click to skip</span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
