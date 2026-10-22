// TANUH: the centre's mark on its own plate, the centre's own summary, its mission and vision folded until opened, and one way
// to visit it.
import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { TANUH } from "../content";
import { Reveal } from "../components/Reveal";

const LOGO = "/static/tb-nik/brand/tanuh.png";

function Fold({ title, text, open, onToggle }: { title: string; text: string; open: boolean; onToggle: () => void }) {
  const reduce = useReducedMotion();
  return (
    <div className="border-t border-[var(--l-line)]">
      <button type="button" className="flex w-full items-center justify-between gap-4 py-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)]" aria-expanded={open} onClick={onToggle}>
        <span className="text-[1.05rem] font-semibold tracking-[-0.01em]">{title}</span>
        <ChevronDown className={cn("size-5 shrink-0 text-[var(--l-accent)] transition-transform duration-300", open && "rotate-180")} aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div key="body" className="overflow-hidden" initial={reduce ? false : { height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
            <p className="l-muted pb-5 text-[15.5px]">{text}</p>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

export function Tanuh() {
  const Place = TANUH.place.icon;
  const [open, setOpen] = useState<number | null>(null);
  return (
    <section id="tanuh" className="l-section-2 py-20 sm:py-28">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <Reveal>
          <div className="l-card grid items-start gap-10 p-7 sm:p-10 md:grid-cols-[auto_1fr] md:p-14">
            <div className="grid place-items-center md:sticky md:top-28">
              <div className="grid size-[180px] place-items-center rounded-3xl bg-white shadow-[0_1px_2px_rgba(11,25,48,0.05),0_20px_50px_-24px_rgba(11,25,48,0.35)] ring-1 ring-[rgba(11,25,48,0.08)] sm:size-[220px]">
                <img src={LOGO} alt="TANUH, The AI Centre of Excellence in Healthcare" className="h-[120px] w-auto sm:h-[150px]" loading="lazy" />
              </div>
            </div>
            <div>
              <span className="l-eyebrow">{TANUH.eyebrow}</span>
              <h2 className="l-title mt-4 text-[clamp(1.8rem,3.2vw,2.6rem)]">{TANUH.title}</h2>
              <div className="mt-5 space-y-4">{TANUH.summary.map((t, i) => <p key={i} className={i === 0 ? "l-lead l-muted" : "l-muted text-[15.5px]"}>{t}</p>)}</div>
              <div className="mt-7 border-b border-[var(--l-line)]">
                {TANUH.sections.map((sec, i) => <Fold key={sec.title} title={sec.title} text={sec.text} open={open === i} onToggle={() => setOpen(open === i ? null : i)} />)}
              </div>
              <p className="l-muted mt-6 flex items-center gap-2 text-[15px]"><Place className="size-4 text-[var(--l-accent)]" aria-hidden />{TANUH.place.text}</p>
              <a href={TANUH.href} target="_blank" rel="noreferrer" className="l-btn l-btn-dark mt-6">{TANUH.visit} <ArrowUpRight className="size-4" aria-hidden /></a>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
