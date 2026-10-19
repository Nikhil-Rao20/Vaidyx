// Option A, "Ledger": the three items as a numbered ledger of type and hairlines on the left; on the right the observed
// context as a pull quote and the national figures as rows with bars. No boxes around the items.
import { PROBLEM } from "../../content";
import { Reveal, Stagger } from "../../components/Reveal";
import { Bar, CountUp, SourceLink } from "../../components/Stats";
import { Source } from "./shared";

export function OptionA() {
  return (
    <div className="grid gap-12 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
      <Stagger className="mt-2">
        {PROBLEM.items.map((it) => (
          <div key={it.n} className="l-ledger-row">
            <span className="l-ledger-n">{it.n}</span>
            <div>
              <h3 className="l-title text-[1.4rem]">{it.title}</h3>
              <p className="l-muted mt-2">{it.text}</p>
            </div>
          </div>
        ))}
      </Stagger>
      <div className="space-y-10">
        <Reveal>
          <p className="l-eyebrow">{PROBLEM.observed.label}</p>
          <p className="l-quote-bar l-serif mt-4 text-[clamp(1.5rem,2.4vw,2rem)] leading-[1.2]">{PROBLEM.observed.text}</p>
          <p className="l-faint mt-3 text-[13px]">{PROBLEM.observed.note}</p>
        </Reveal>
        <Reveal delay={0.1}>
          <p className="l-eyebrow">{PROBLEM.national.label}</p>
          <ul className="mt-5 space-y-5">
            {PROBLEM.national.stats.map((st) => (
              <li key={st.text}>
                <div className="flex items-baseline justify-between gap-4">
                  <CountUp value={st.value} className="text-[2.4rem]" />
                  <SourceLink href={PROBLEM.national.source.href} label={PROBLEM.national.source.short} />
                </div>
                <Bar value={st.value} className="mt-2" />
                <p className="l-muted mt-2 text-[15px]">{st.text}</p>
              </li>
            ))}
          </ul>
          <Source className="mt-5" />
        </Reveal>
      </div>
    </div>
  );
}
