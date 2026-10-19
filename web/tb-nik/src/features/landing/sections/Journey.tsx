// The Tumour Board workflow, step by step: the swimlane map on the left lights the stations and lines of the current step and
// sends a dot along them; the panel on the right tells the step, names who acts, shows a small preview, and carries Next step
// and Start over, pinned to its bottom so they never move. It advances on its own while in view until the visitor takes over.
// On a phone the map scrolls sideways and the panel sits under it.
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
      <div className="mx-auto max-w-[1400px] px-5 sm:px-8">
        <SectionHead eyebrow={FLOW.eyebrow} title={[FLOW.title[0], FLOW.title[1]]} lead={FLOW.lead} />
        <Reveal y={20} className="l-card mt-14 overflow-hidden" testId="journey-card">
          <div className="grid lg:grid-cols-[7fr_3fr]" style={{ gridAutoRows: "minmax(0, 1fr)" }}>
            <div className="jy-scroll l-section-2 min-w-0 border-b border-[var(--l-line)] p-4 sm:p-6 lg:border-b-0 lg:border-r">
              <Diagram activeNodes={step.nodes} activePaths={step.paths} lanes={FLOW.lanes} phases={FLOW.phases} frame={FLOW.frame} />
            </div>
            {/* the panel: as tall as the drawing on a laptop; the actions are pinned to its bottom so they never move */}
            <div className="flex min-w-0 flex-col overflow-hidden p-5 sm:p-6 lg:min-h-0" data-testid="journey-panel" data-step={step.id}>
              <div className="flex items-center justify-between gap-3">
                <span className="l-eyebrow">{FLOW.labels.step} {String(i + 1).padStart(2, "0")}</span>
                <span className="l-pill !py-1 text-[12px]">{i + 1} {FLOW.labels.of} {n}</span>
              </div>
              <div className="mt-4 min-h-[8.5rem]">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div key={step.id} initial={reduce ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.15 } }} transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
                    <h3 className="l-title text-[clamp(1.2rem,1.6vw,1.45rem)]">{step.title}</h3>
                    <p className="l-muted mt-2 text-[14px]">{step.body}</p>
                  </motion.div>
                </AnimatePresence>
              </div>
              <div className="mt-3 flex min-h-[2.25rem] flex-wrap items-center gap-2">
                <span className="l-pill !py-1 text-[12.5px]"><UserRound className="size-3.5 text-[var(--l-accent)]" aria-hidden />{FLOW.labels.who}: <b className="font-semibold text-[var(--l-fg)]">{step.who}</b></span>
                {step.chip ? <span className="l-chip l-chip-info !py-1 !text-[12px]">{step.chip}</span> : null}
              </div>
              {/* a fixed slot for the preview, so the actions below never move */}
              <div className="mt-3 h-[168px] overflow-hidden">
                <AnimatePresence mode="wait" initial={false}>
                  {Preview ? (
                    <motion.div key={step.id} initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.15 } }} transition={{ duration: 0.35 }} className="origin-top-left">
                      <Preview />
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>
              <div className="mt-auto pt-6">
                <div className="flex items-center gap-1.5" role="tablist" aria-label="Steps">
                  {FLOW.steps.map((s, k) => <button key={s.id} type="button" role="tab" aria-selected={k === i} aria-label={`Step ${k + 1}: ${s.title}`} className="jy-seg" data-state={k < i ? "done" : k === i ? "current" : "todo"} onClick={() => go(k)} />)}
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <button type="button" className="l-btn l-btn-primary !h-10 !px-4 text-[14px]" onClick={() => go(i + 1)} data-testid="journey-next">{FLOW.labels.next} <ArrowRight className="size-4" aria-hidden /></button>
                  <button type="button" className={cn("l-btn l-btn-ghost !h-10 !px-4 text-[14px]", i === 0 && !manual && "opacity-60")} onClick={() => go(0)} data-testid="journey-restart"><RotateCcw className="size-4" aria-hidden /> {FLOW.labels.restart}</button>
                </div>
                {/* a line that is always there, so the buttons never move when the label goes */}
                <span className="l-faint mt-3 block h-5 text-[12px]" aria-live="polite">{!manual && !reduce ? FLOW.labels.auto : ""}</span>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
