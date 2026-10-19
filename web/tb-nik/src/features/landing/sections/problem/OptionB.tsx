// Option B, "Bento": three tiles with a ghost numeral and a badge, a wide tile with three gauges for the national figures and
// the source, and a tinted tile for the observed context.
import { motion, useReducedMotion } from "motion/react";
import { PROBLEM } from "../../content";
import { Reveal, Stagger } from "../../components/Reveal";
import { CountUp, Gauge, SourceLink } from "../../components/Stats";
import { BADGES, Source } from "./shared";

export function OptionB() {
  const reduce = useReducedMotion();
  return (
    <div className="space-y-5">
      <Stagger className="grid gap-5 md:grid-cols-3" itemClassName="h-full">
        {PROBLEM.items.map((it, i) => {
          const Icon = it.icon;
          return (
            <article key={it.n} className="l-tile flex h-full flex-col p-7 sm:p-8">
              <span className="l-ghost" aria-hidden>{it.n}</span>
              <span className="l-badge" style={{ "--badge": BADGES[i].bg, "--badge-shadow": BADGES[i].shadow } as React.CSSProperties}><Icon className="size-5" strokeWidth={1.9} aria-hidden /></span>
              <h3 className="l-title mt-6 text-[1.4rem]">{it.title}</h3>
              <p className="l-muted mt-3">{it.text}</p>
            </article>
          );
        })}
      </Stagger>
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <Reveal className="l-tile p-7 sm:p-8">
          <p className="l-eyebrow">{PROBLEM.national.label}</p>
          <div className="mt-6 grid gap-6 sm:grid-cols-3">
            {PROBLEM.national.stats.map((st) => (
              <div key={st.text} className="flex flex-col items-center text-center sm:items-start sm:text-left">
                <Gauge value={st.value} size={124} stroke={9}><CountUp value={st.value} className="text-[1.45rem]" /></Gauge>
                <p className="l-muted mt-4 text-[15px]">{st.text}</p>
                <SourceLink href={PROBLEM.national.source.href} label={PROBLEM.national.source.short} className="mt-2" />
              </div>
            ))}
          </div>
          <Source className="mt-7 border-t border-[var(--l-line)] pt-5" />
        </Reveal>
        <Reveal delay={0.1} className="l-tile l-tile-tint flex flex-col p-7 sm:p-8">
          <p className="l-eyebrow">{PROBLEM.observed.label}</p>
          <p className="l-serif mt-5 text-[clamp(2.2rem,3.6vw,3rem)] leading-none">{PROBLEM.observed.figure}</p>
          <p className="mt-4 text-[1.05rem]">{PROBLEM.observed.text}</p>
          {/* a week of days: the records arrive one by one */}
          <div className="mt-8 flex items-center gap-2" aria-hidden>
            {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => (
              <motion.span key={i} className="grid size-8 place-items-center rounded-full text-[11px] font-semibold" style={{ background: i < 5 ? "var(--l-accent-bg)" : "transparent", color: i < 5 ? "var(--l-accent)" : "var(--l-fg-3)", border: i < 5 ? "1px solid transparent" : "1px dashed var(--l-line-2)" }} initial={reduce ? false : { opacity: 0, scale: 0.6 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ delay: 0.3 + i * 0.09, duration: 0.4 }}>{d}</motion.span>
            ))}
          </div>
          <p className="l-faint mt-auto pt-6 text-[13px]">{PROBLEM.observed.note}</p>
        </Reveal>
      </div>
    </div>
  );
}
