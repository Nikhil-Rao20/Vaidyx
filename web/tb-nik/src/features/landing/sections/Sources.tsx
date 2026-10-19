// Every fact has its source: a synthetic report on the left, the values read from it on the right, and a line from each value
// to the exact line it came from. The lines draw themselves; the pair in focus walks on its own and follows the pointer.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { Eye, Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import { SOURCES } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Reveal, Stagger } from "../components/Reveal";

export function Sources() {
  const wrap = useRef<HTMLDivElement>(null);
  const [paths, setPaths] = useState<string[]>([]);
  const [active, setActive] = useState(0);
  const [pinned, setPinned] = useState(false);
  const inView = useInView(wrap, { amount: 0.35 });
  const reduce = useReducedMotion();

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const compute = () => {
      if (window.innerWidth < 1024) { setPaths([]); return; }
      const box = el.getBoundingClientRect();
      const out: string[] = [];
      SOURCES.fields.forEach((f, i) => {
        const q = el.querySelector<HTMLElement>(`[data-quote="${f.quote}"]`);
        const d = el.querySelector<HTMLElement>(`[data-field="${i}"]`);
        if (!q || !d) return;
        const a = q.getBoundingClientRect(), b = d.getBoundingClientRect();
        const x1 = a.right - box.left + 6, y1 = a.top + a.height / 2 - box.top;
        const x2 = b.left - box.left - 6, y2 = b.top + b.height / 2 - box.top;
        const dx = Math.max(36, (x2 - x1) * 0.55);
        out.push(`M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`);
      });
      setPaths(out);
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    document.fonts?.ready.then(compute).catch(() => undefined);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!inView || reduce || pinned) return;
    const t = window.setInterval(() => setActive((a) => (a + 1) % SOURCES.fields.length), 2600);
    return () => window.clearInterval(t);
  }, [inView, reduce, pinned]);

  const onQuote = SOURCES.fields[active]?.quote;
  return (
    <section id="sources" className="l-ink on-ink relative overflow-hidden py-24 sm:py-32">
      <span className="l-orb l-orb-teal" style={{ width: 700, height: 700, right: "-14%", top: "-20%", opacity: 0.35 }} aria-hidden />
      <span className="l-grain" aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead onInk eyebrow={SOURCES.eyebrow} title={[SOURCES.title[0], SOURCES.title[1]]} lead={SOURCES.lead} />
        <div ref={wrap} className="relative mt-16 grid gap-6 lg:grid-cols-[1.05fr_minmax(72px,0.22fr)_0.9fr] lg:gap-0" onPointerLeave={() => setPinned(false)}>
          <Reveal y={24} className="l-win p-5 sm:p-6" style={{ color: "var(--text)" }}>
            <div className="flex items-center justify-between gap-3 border-b border-[rgba(11,25,48,0.08)] pb-3">
              <p className="text-[15px] font-semibold tracking-[-0.01em]">{SOURCES.report.title}</p>
              <span className="l-chip l-chip-review">{SOURCES.report.stamp}</span>
            </div>
            <div className="mt-3 space-y-0.5 text-[14px] leading-relaxed text-[var(--text-2)]">
              {SOURCES.report.lines.map((line, i) => (
                <p key={i} data-quote={i} data-on={onQuote === i ? "true" : "false"} className="l-quote-line">{line}</p>
              ))}
            </div>
          </Reveal>
          <div className="pointer-events-none hidden lg:block" aria-hidden>
            <svg className="absolute inset-0 h-full w-full overflow-visible">
              {paths.map((d, i) => (
                <g key={i}>
                  <motion.path d={d} fill="none" stroke="var(--mint)" strokeWidth={1.5} initial={reduce ? false : { pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true, amount: 0.3 }} animate={{ opacity: active === i ? 1 : 0.25 }} transition={{ pathLength: { duration: 1.1, delay: 0.3 + i * 0.12, ease: [0.22, 1, 0.36, 1] }, opacity: { duration: 0.4 } }} />
                  {active === i ? <motion.circle r={3.5} fill="var(--mint)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ offsetPath: `path("${d}")`, offsetDistance: "100%" } as React.CSSProperties} /> : null}
                </g>
              ))}
            </svg>
          </div>
          <Reveal y={24} delay={0.1} className="l-card-ink p-2">
            <ul className="divide-y divide-white/[0.07]">
              {SOURCES.fields.map((f, i) => (
                <li key={f.label} data-field={i} onPointerEnter={() => { setActive(i); setPinned(true); }} onFocus={() => setActive(i)} tabIndex={0} className={cn("flex cursor-default items-center gap-3 rounded-xl px-3.5 py-3.5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--cyan)]", active === i && "bg-white/[0.06]")}>
                  <span className="hidden w-[6.5rem] shrink-0 text-[12.5px] uppercase tracking-[0.08em] text-white/55 sm:block">{f.label}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[11px] uppercase tracking-[0.08em] text-white/55 sm:hidden">{f.label}</span>
                    <span className="block text-[17px] font-semibold tracking-[-0.01em] text-white">{f.value}</span>
                    {f.state === "review" ? <span className="block text-[12px] text-white/55">{f.note}</span> : null}
                  </span>
                  {f.state === "quoted" ? <span className="l-chip l-chip-ok"><Quote className="size-3" aria-hidden />quoted</span> : <span className="l-chip l-chip-review"><Eye className="size-3" aria-hidden />needs review</span>}
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
        <Stagger className="mt-14 grid gap-4 md:grid-cols-3">
          {SOURCES.rules.map((r) => {
            const Icon = r.icon;
            return (
              <div key={r.title} className="flex gap-4">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/[0.06] text-[var(--mint)] ring-1 ring-white/10"><Icon className="size-[18px]" aria-hidden /></span>
                <div><p className="font-semibold text-white">{r.title}</p><p className="l-muted mt-1 text-[15px]">{r.text}</p></div>
              </div>
            );
          })}
        </Stagger>
      </div>
    </section>
  );
}
