// Safe by design: six principles on the left, a drawing of the chosen one on the right. They take turns until someone chooses.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { SAFETY } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Reveal } from "../components/Reveal";
import { ART } from "./SafetyArt";

export function Safety() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { amount: 0.35 });
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const [chosen, setChosen] = useState(false);
  const n = SAFETY.principles.length;
  useEffect(() => {
    if (!inView || chosen || reduce) return;
    const t = window.setInterval(() => setActive((a) => (a + 1) % n), 4600);
    return () => window.clearInterval(t);
  }, [inView, chosen, reduce, n]);
  const p = SAFETY.principles[active];
  const Art = ART[p.key];
  return (
    <section id="safety" ref={ref} className="l-section-2 relative overflow-hidden py-24 sm:py-32">
      <span className="l-orb l-orb-violet" style={{ width: 640, height: 640, left: "-10%", top: "10%", opacity: 0.35 }} aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={SAFETY.eyebrow} title={[SAFETY.title[0], SAFETY.title[1]]} lead={SAFETY.lead} />
        <div className="mt-14 grid items-start gap-8 lg:grid-cols-[0.95fr_1.05fr] lg:gap-14">
          <Reveal y={20} className="space-y-1" testId="safety-list">
            {SAFETY.principles.map((pr, i) => (
              <button key={pr.key} type="button" className="l-row" data-active={i === active} aria-pressed={i === active} onClick={() => { setActive(i); setChosen(true); }}>
                <span className="flex items-baseline gap-4">
                  <span className="l-eyebrow w-7 shrink-0 tabular-nums">0{i + 1}</span>
                  <span className="text-[1.15rem] font-semibold tracking-[-0.01em]">{pr.title}</span>
                </span>
                <AnimatePresence initial={false}>
                  {i === active ? (
                    <motion.span key="t" className="l-muted block overflow-hidden pl-11" initial={reduce ? false : { height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
                      <span className="block pt-2 text-[15.5px]">{pr.text}</span>
                    </motion.span>
                  ) : null}
                </AnimatePresence>
              </button>
            ))}
          </Reveal>
          <Reveal y={20} delay={0.1}>
            <div className="l-card overflow-hidden p-3 sm:p-4" data-testid="safety-art">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={p.key} initial={reduce ? false : { opacity: 0, scale: 0.985 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, transition: { duration: 0.2 } }} transition={{ duration: 0.4 }}>
                  <div className="l-box p-2 sm:p-4"><Art /></div>
                  <p className="l-muted mt-3 px-2 text-[14.5px]"><span className="font-semibold text-[var(--l-fg)]">{p.title}.</span> {p.text}</p>
                </motion.div>
              </AnimatePresence>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
