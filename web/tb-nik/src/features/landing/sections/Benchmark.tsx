// The benchmark (12 Nov): the 13 open models in two groups, the 11 public benchmarks, and one bar per model for the overall
// score on the text questions. Every figure is read from research/data.ts, the data the Research page shows.
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";
import { RESEARCH } from "../content";
import { BENCHMARK } from "../content.pillars";
import { RESEARCH_DATA } from "../research/data";
import { SectionHead } from "../components/SectionHead";
import { Reveal } from "../components/Reveal";

const MODELS = RESEARCH_DATA.models;
const byKey = new Map<string, (typeof MODELS)[number]>(MODELS.map((m) => [m.key, m]));
const MEDICAL = MODELS.filter((m) => m.type === "Medical");
const GENERAL = MODELS.filter((m) => m.type !== "Medical");
const TEXT = RESEARCH_DATA.dataCards.filter((c) => c.kind === "text");
const IMAGE = RESEARCH_DATA.dataCards.filter((c) => c.kind === "image");
const RANKED = [...RESEARCH_DATA.textCot].sort((a, b) => b.overall - a.overall);
const USED = BENCHMARK.roles as Record<string, string>;
const n = (x: number) => x.toLocaleString("en-GB");  // 101,227, as the Research page writes it

function Group({ count, label, sub, items, tone }: { count: number; label: string; sub?: string; items: readonly string[]; tone?: "general" }) {
  return (
    <div>
      <p className="text-[14px] font-semibold"><span className="l-figure mr-1.5 text-[1.35rem]">{count}</span>{label}</p>
      {sub ? <p className="l-faint mt-0.5 text-[12.5px]">{sub}</p> : null}
      <ul className="mt-2.5 flex flex-wrap gap-1.5">
        {items.map((t) => <li key={t} className="l-tag" data-on={tone === "general" ? "true" : undefined} style={tone === "general" ? ({ background: "var(--l-review-bg)", color: "var(--l-review)", borderColor: "transparent" } as React.CSSProperties) : undefined}>{t}</li>)}
      </ul>
    </div>
  );
}

export function Benchmark() {
  const reduce = useReducedMotion();
  const C = BENCHMARK.chart;
  return (
    <section id="benchmark" className="l-section relative overflow-hidden py-24 sm:py-32" data-testid="benchmark">
      <span className="l-orb l-orb-violet" style={{ width: 620, height: 620, right: "-12%", top: "4%", opacity: 0.3 }} aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={BENCHMARK.eyebrow} title={[BENCHMARK.title[0], BENCHMARK.title[1]]} lead={BENCHMARK.lead} />
        <Reveal y={16} className="mt-12 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          {RESEARCH.paper.facts.map(([v, l]) => (
            <div key={l} className="l-tile px-5 py-5 sm:px-6" data-testid="benchmark-fact">
              <p className="l-figure text-[clamp(1.6rem,2.6vw,2.2rem)]">{v}</p>
              <p className="l-muted mt-1.5 text-[14px]">{l}</p>
            </div>
          ))}
        </Reveal>
        <div className="mt-5 grid items-stretch gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <Reveal y={20} className="l-card space-y-7 p-5 sm:p-7">
            <Group count={MEDICAL.length} label={BENCHMARK.groups.medical} items={MEDICAL.map((m) => `${m.name} · ${m.country}`)} />
            <Group count={GENERAL.length} label={BENCHMARK.groups.general} items={GENERAL.map((m) => `${m.name} · ${m.country}`)} tone="general" />
            <div className="grid gap-6 border-t border-[var(--l-line)] pt-6 sm:grid-cols-2">
              <Group count={TEXT.length} label={BENCHMARK.groups.text} sub={`${n(RESEARCH_DATA.totals.textQuestions)} ${BENCHMARK.groups.questions}`} items={TEXT.map((c) => c.name)} />
              <Group count={IMAGE.length} label={BENCHMARK.groups.image} sub={`${n(RESEARCH_DATA.totals.imageQuestions)} ${BENCHMARK.groups.questions}`} items={IMAGE.map((c) => c.name)} />
            </div>
          </Reveal>
          <Reveal y={20} delay={0.08} className="l-card p-5 sm:p-7" testId="benchmark-chart">
            <h3 className="l-title text-[1.2rem]">{C.title}</h3>
            <p className="l-muted mt-1.5 text-[14px]">{C.sub}</p>
            <p className="l-muted mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[12.5px]">
              <span className="inline-flex items-center gap-2"><span className="l-bm-key" style={{ background: "linear-gradient(90deg, var(--teal), var(--cyan))" }} aria-hidden />{C.medical}</span>
              <span className="inline-flex items-center gap-2"><span className="l-bm-key" style={{ background: "var(--violet)" }} aria-hidden />{C.general}</span>
            </p>
            <ul className="mt-4" aria-label={C.label}>
              {RANKED.map((r, i) => {
                const m = byKey.get(r.key);
                if (!m) return null;
                const kind = m.type === "Medical" ? "medical" : "general";
                const used = r.key in USED;
                return (
                  <li key={r.key} className="l-bm-row" data-kind={kind} data-used={used ? "true" : "false"} data-testid="benchmark-row">
                    <span className="min-w-0"><span className="l-bm-name block" title={m.name}>{m.name}</span>{used ? <span className="block text-[11px] font-semibold leading-tight text-[var(--l-review)]">{C.used}</span> : null}</span>
                    <span className="l-bm-track" aria-hidden>
                      <motion.i className="l-bm-fill" initial={{ scaleX: reduce ? r.overall / 100 : 0 }} whileInView={{ scaleX: r.overall / 100 }} viewport={{ once: true, amount: 0.6 }} transition={{ duration: reduce ? 0 : 1.1, delay: reduce ? 0 : i * 0.04, ease: [0.22, 1, 0.36, 1] }} style={{ width: "100%" }} />
                    </span>
                    <span className="l-bm-val">{r.overall.toFixed(1)}</span>
                  </li>
                );
              })}
            </ul>
            <ul className="l-muted mt-4 space-y-1 border-t border-[var(--l-line)] pt-4 text-[13.5px]">
              {Object.entries(USED).map(([k, t]) => <li key={k}>{t}</li>)}
            </ul>
          </Reveal>
        </div>
        <Reveal y={12} className="mt-6 flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
          <p className="l-faint max-w-2xl text-[13.5px]">{BENCHMARK.note}</p>
          <Link to={BENCHMARK.to} className="l-btn l-btn-ghost !h-11" data-testid="benchmark-link">{BENCHMARK.link} <ArrowRight className="size-4" aria-hidden /></Link>
        </Reveal>
      </div>
    </section>
  );
}
