// Option C, "Flow": the three items as steps along a dashed line, then a band with the observed context on the left and the
// national figures with small gauges on the right.
import { motion, useReducedMotion } from "motion/react";
import { Clock3 } from "lucide-react";
import { PROBLEM } from "../../content";
import { Reveal, Stagger } from "../../components/Reveal";
import { CountUp, Gauge, SourceLink } from "../../components/Stats";
import { BADGES, Source } from "./shared";

export function OptionC() {
  const reduce = useReducedMotion();
  return (
    <div className="space-y-10">
      <div className="relative">
        <motion.span className="l-flow-line hidden md:block" initial={reduce ? false : { scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true, amount: 0.4 }} transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }} style={{ transformOrigin: "left" }} aria-hidden />
        <Stagger className="grid gap-8 md:grid-cols-3">
          {PROBLEM.items.map((it, i) => {
            const Icon = it.icon;
            return (
              <div key={it.n} className="relative flex flex-col items-start md:items-center md:text-center">
                <span className="l-badge relative z-10" style={{ "--badge": BADGES[i].bg, "--badge-shadow": BADGES[i].shadow } as React.CSSProperties}><Icon className="size-5" strokeWidth={1.9} aria-hidden /></span>
                <span className="l-eyebrow mt-5">{it.n}</span>
                <h3 className="l-title mt-2 text-[1.35rem]">{it.title}</h3>
                <p className="l-muted mt-3 max-w-sm">{it.text}</p>
              </div>
            );
          })}
        </Stagger>
      </div>
      <Reveal className="l-tile grid gap-8 p-7 sm:p-8 lg:grid-cols-[1fr_1.6fr] lg:gap-12">
        <div className="l-box flex gap-4 p-5">
          <span className="l-icon shrink-0"><Clock3 className="size-5" aria-hidden /></span>
          <div>
            <p className="l-eyebrow">{PROBLEM.observed.label}</p>
            <p className="mt-2 text-[1.05rem]">{PROBLEM.observed.text}</p>
            <p className="l-faint mt-2 text-[13px]">{PROBLEM.observed.note}</p>
          </div>
        </div>
        <div>
          <p className="l-eyebrow">{PROBLEM.national.label}</p>
          <ul className="mt-4 divide-y divide-[var(--l-line)]">
            {PROBLEM.national.stats.map((st) => (
              <li key={st.text} className="flex items-center gap-4 py-3">
                <Gauge value={st.value} size={44} stroke={5} />
                <CountUp value={st.value} className="w-[5.2rem] text-[1.6rem]" />
                <span className="l-muted min-w-0 flex-1 text-[15px]">{st.text}</span>
                <SourceLink href={PROBLEM.national.source.href} label={PROBLEM.national.source.short} className="hidden sm:inline-flex" />
              </li>
            ))}
          </ul>
          <Source className="mt-3" />
        </div>
      </Reveal>
    </div>
  );
}
