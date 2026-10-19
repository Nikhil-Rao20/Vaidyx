// The journey of one patient, step by step: the diagram on the left lights the nodes and lines of the current step and sends a
// dot along them; the panel on the right tells the step, names who acts, shows a small preview, and carries Next step and
// Start over. It advances on its own while in view until the visitor takes over. On a phone the panel sits under the drawing.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { ArrowRight, RotateCcw, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import { FLOW } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Reveal } from "../components/Reveal";
import { Diagram } from "./flow/diagram";
import { PREVIEWS } from "./flow/previews";

const AUTO_MS = 6500;

export function Journey() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { amount: 0.35 });
  const reduce = useReducedMotion();
  const [i, setI] = useState(0);
  const [manual, setManual] = useState(false);
  const n = FLOW.steps.length;
  const step = FLOW.steps[i];
  const Preview = step.preview ? PREVIEWS[step.preview] : null;

  useEffect(() => {
    if (!inView || manual || reduce) return;
    const t = window.setTimeout(() => setI((k) => (k + 1) % n), AUTO_MS);
    return () => window.clearTimeout(t);
  }, [inView, manual, reduce, i, n]);

  const go = (k: number) => { setManual(true); setI(((k % n) + n) % n); };

  return (
    <section id="journey" ref={ref} className="l-section-2 py-24 sm:py-32" data-testid="journey">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={FLOW.eyebrow} title={[FLOW.title[0], FLOW.title[1]]} lead={FLOW.lead} />
        <Reveal y={20} className="l-card mt-14 overflow-hidden">
          <div className="grid lg:grid-cols-[1.25fr_0.95fr]">
            <div className="jy-scroll l-section-2 border-b border-[var(--l-line)] p-4 sm:p-6 lg:border-b-0 lg:border-r">
              <Diagram activeNodes={step.nodes} activePaths={step.paths} zones={FLOW.zones} frame={FLOW.frame} />
            </div>
            <div className="flex flex-col p-6 sm:p-8" data-testid="journey-panel" data-step={step.id}>
              <div className="flex items-center justify-between gap-3">
                <span className="l-eyebrow">{FLOW.labels.step} {String(i + 1).padStart(2, "0")}</span>
                <span className="l-pill !py-1 text-[12px]">{i + 1} {FLOW.labels.of} {n}</span>
              </div>
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={step.id} className="mt-5 flex-1" initial={reduce ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8, transition: { duration: 0.2 } }} transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}>
                  <h3 className="l-title text-[clamp(1.4rem,2.2vw,1.85rem)]">{step.title}</h3>
                  <p className="l-muted mt-3 text-[15.5px]">{step.body}</p>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <span className="l-pill !py-1 text-[12.5px]"><UserRound className="size-3.5 text-[var(--l-accent)]" aria-hidden />{FLOW.labels.who}: <b className="font-semibold text-[var(--l-fg)]">{step.who}</b></span>
                    {step.chip ? <span className="l-chip l-chip-info !py-1 !text-[12px]">{step.chip}</span> : null}
                  </div>
                  {Preview ? <div className="mt-5"><Preview /></div> : null}
                </motion.div>
              </AnimatePresence>
              <div className="mt-6">
                <div className="flex items-center gap-1.5" role="tablist" aria-label="Steps">
                  {FLOW.steps.map((s, k) => <button key={s.id} type="button" role="tab" aria-selected={k === i} aria-label={`Step ${k + 1}: ${s.title}`} className="jy-seg" data-state={k < i ? "done" : k === i ? "current" : "todo"} onClick={() => go(k)} />)}
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <button type="button" className="l-btn l-btn-primary !h-11" onClick={() => go(i + 1)} data-testid="journey-next">{FLOW.labels.next} <ArrowRight className="size-4" aria-hidden /></button>
                  <button type="button" className={cn("l-btn l-btn-ghost !h-11", i === 0 && !manual && "opacity-60")} onClick={() => go(0)} data-testid="journey-restart"><RotateCcw className="size-4" aria-hidden /> {FLOW.labels.restart}</button>
                  {!manual && !reduce ? <span className="l-faint ml-auto text-[12px]">{FLOW.labels.auto}</span> : null}
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
