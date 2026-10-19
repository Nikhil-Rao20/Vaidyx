// What Vaidyx will never do: the scope statement lights up word by word as it scrolls into the middle of the screen, then the
// six principles.
import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useTransform, type MotionValue } from "motion/react";
import { SAFETY } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Stagger } from "../components/Reveal";

function Word({ progress, range, children }: { progress: MotionValue<number>; range: [number, number]; children: string }) {
  const opacity = useTransform(progress, range, [0.16, 1]);
  const y = useTransform(progress, range, [4, 0]);
  return <motion.span style={{ opacity, y }} className="inline-block will-change-[opacity,transform]">{children}&nbsp;</motion.span>;
}

export function Safety() {
  const ref = useRef<HTMLParagraphElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.85", "end 0.42"] });
  const words = SAFETY.statement.split(" ");
  return (
    <section id="safety" className="l-ink on-ink relative overflow-hidden py-24 sm:py-32" style={{ background: "linear-gradient(180deg, #050b18 0%, #071530 100%)" }}>
      <span className="l-orb l-orb-violet" style={{ width: 640, height: 640, left: "-10%", top: "10%", opacity: 0.3 }} aria-hidden />
      <span className="l-orb l-orb-teal" style={{ width: 760, height: 760, right: "-16%", bottom: "-20%", opacity: 0.3 }} aria-hidden />
      <span className="l-grain" aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead onInk eyebrow={SAFETY.eyebrow} title={[SAFETY.title[0], SAFETY.title[1]]} />
        <p ref={ref} className="l-title mt-14 max-w-5xl text-[clamp(1.55rem,3.3vw,2.75rem)] font-medium leading-[1.2] text-white" data-testid="scope-statement">
          {reduce ? SAFETY.statement : words.map((w, i) => <Word key={i} progress={scrollYProgress} range={[i / words.length, Math.min(1, (i + 1.2) / words.length)]}>{w}</Word>)}
        </p>
        <Stagger className="mt-20 grid gap-4 md:grid-cols-2 lg:grid-cols-3" itemClassName="h-full">
          {SAFETY.principles.map((p) => {
            const Icon = p.icon;
            return (
              <div key={p.title} className="l-card-ink flex h-full flex-col p-6">
                <span className="grid size-10 place-items-center rounded-xl bg-[rgba(1,203,211,0.12)] text-[var(--mint)] ring-1 ring-white/10"><Icon className="size-[18px]" aria-hidden /></span>
                <p className="mt-5 text-[1.1rem] font-semibold text-white">{p.title}</p>
                <p className="l-muted mt-2 text-[15px]">{p.text}</p>
              </div>
            );
          })}
        </Stagger>
      </div>
    </section>
  );
}
