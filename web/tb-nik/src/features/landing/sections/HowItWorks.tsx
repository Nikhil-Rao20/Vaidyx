// Before, during and after the board: the steps on the left, a screen on the right that changes as the reader scrolls
// (sticky on a laptop; inline above each phase on a phone).
import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView } from "motion/react";
import { HOW, type Phase } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Reveal, Stagger } from "../components/Reveal";
import { SceneAfter, SceneBefore, SceneDuring } from "./Scenes";

type Key = Phase["key"];

function Screen({ scene }: { scene: Key }) {
  return (
    <div className="relative" data-scene={scene}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={scene} initial={{ opacity: 0, y: 16, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -12, scale: 0.985 }} transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}>
          {scene === "before" ? <SceneBefore /> : scene === "during" ? <SceneDuring /> : <SceneAfter />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function PhaseBlock({ phase, index, onActive }: { phase: Phase; index: number; onActive: (k: Key) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { margin: "-45% 0px -45% 0px" });
  useEffect(() => { if (inView) onActive(phase.key); }, [inView, phase.key, onActive]);
  return (
    <div ref={ref} className="lg:flex lg:min-h-[86vh] lg:flex-col lg:justify-center lg:py-10" data-phase={phase.key}>
      <Reveal>
        <div className="flex items-center gap-3">
          <span className="l-eyebrow text-[#0a6a86]">0{index + 1}</span>
          <span className="h-px w-8 bg-[rgba(11,25,48,0.15)]" aria-hidden />
          <span className="l-eyebrow l-muted">{phase.label}</span>
        </div>
        <h3 className="l-title mt-4 text-[clamp(1.6rem,2.6vw,2.25rem)]">{phase.title}</h3>
      </Reveal>
      <div className="mt-8 lg:hidden"><Reveal y={20}><Screen scene={phase.key} /></Reveal></div>
      <Stagger className="mt-8 space-y-6">
        {phase.steps.map((s, j) => (
          <div key={s.title} className="flex gap-4">
            <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full border border-[rgba(1,180,194,0.45)] bg-white text-[12px] font-semibold tabular-nums text-[#0a6a86]">{j + 1}</span>
            <div>
              <p className="text-[1.05rem] font-semibold tracking-[-0.01em]">{s.title}</p>
              <p className="l-muted mt-1">{s.text}</p>
            </div>
          </div>
        ))}
      </Stagger>
    </div>
  );
}

export function HowItWorks() {
  const [active, setActive] = useState<Key>("before");
  const onActive = useCallback((k: Key) => setActive(k), []);
  return (
    <section id="how" className="l-paper-2 py-24 sm:py-32">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={HOW.eyebrow} title={[HOW.title[0], HOW.title[1]]} lead={HOW.lead} />
        <div className="mt-12 lg:mt-4 lg:grid lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:gap-16 xl:gap-24">
          <div className="space-y-20 lg:space-y-0">
            {HOW.phases.map((ph, i) => <PhaseBlock key={ph.key} phase={ph} index={i} onActive={onActive} />)}
          </div>
          <div className="hidden lg:block">
            <div className="sticky top-28"><Screen scene={active} /></div>
          </div>
        </div>
      </div>
    </section>
  );
}
