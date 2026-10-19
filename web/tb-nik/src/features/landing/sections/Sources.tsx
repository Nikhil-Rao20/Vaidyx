// Every value traceable to its source. A synthetic report on the left; on the right the values read from it, then "Ask the Case
// File": a question is typed, the answer appears sentence by sentence, and each value and each sentence draws a line to the report
// line that supports it. The sequence runs while the section is in view and repeats; pointing at a value holds it.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { Eye, MessageSquareText, Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import { SOURCES } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Reveal, Stagger } from "../components/Reveal";

const F = SOURCES.fields.length;
const A = SOURCES.ask.answer.length;
// steps: 0..F-1 the values in turn; F the question is typed; F+1..F+A the answer sentences; F+A+1 a pause; then again.
const STEPS = F + A + 2;
const dur = (step: number) => (step < F ? 1500 : step === F ? 2400 : step <= F + A ? 1500 : 3200);

interface Line { d: string; kind: "field" | "ans"; i: number }

export function Sources() {
  const wrap = useRef<HTMLDivElement>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [step, setStep] = useState(0);
  const [pinned, setPinned] = useState<number | null>(null);
  const [chars, setChars] = useState(0);
  const inView = useInView(wrap, { amount: 0.3 });
  const reduce = useReducedMotion();

  const typing = step === F && !reduce;
  const shown = reduce ? A : Math.max(0, Math.min(A, step - F));
  const activeField = pinned ?? (step < F && !reduce ? step : null);
  const activeAns = pinned !== null || reduce ? null : step > F && step <= F + A ? step - F - 1 : null;
  const activeQuote = activeField !== null ? SOURCES.fields[activeField].quote : activeAns !== null ? SOURCES.ask.answer[activeAns].quote : null;
  const typed = reduce || step > F ? SOURCES.ask.question : typing ? SOURCES.ask.question.slice(0, chars) : "";

  useEffect(() => {
    if (!inView || reduce || pinned !== null) return;
    const t = window.setTimeout(() => setStep((s) => (s + 1) % STEPS), dur(step));
    return () => window.clearTimeout(t);
  }, [inView, reduce, pinned, step]);

  useEffect(() => {
    if (!typing) { setChars(0); return; }
    const n = SOURCES.ask.question.length;
    const t = window.setInterval(() => setChars((c) => (c >= n ? c : c + 1)), 36);
    return () => window.clearInterval(t);
  }, [typing]);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const compute = () => {
      if (window.innerWidth < 1024) { setLines([]); return; }
      const box = el.getBoundingClientRect();
      const out: Line[] = [];
      const link = (fromQuote: number, to: HTMLElement | null, kind: Line["kind"], i: number) => {
        const q = el.querySelector<HTMLElement>(`[data-quote="${fromQuote}"]`);
        if (!q || !to) return;
        const a = q.getBoundingClientRect(), b = to.getBoundingClientRect();
        const x1 = a.right - box.left + 6, y1 = a.top + a.height / 2 - box.top;
        const x2 = b.left - box.left - 6, y2 = b.top + b.height / 2 - box.top;
        const dx = Math.max(36, (x2 - x1) * 0.55);
        out.push({ d: `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`, kind, i });
      };
      SOURCES.fields.forEach((f, i) => link(f.quote, el.querySelector<HTMLElement>(`[data-field="${i}"]`), "field", i));
      SOURCES.ask.answer.forEach((s, i) => link(s.quote, el.querySelector<HTMLElement>(`[data-ans="${i}"]`), "ans", i));
      setLines(out);
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    document.fonts?.ready.then(compute).catch(() => undefined);
    return () => ro.disconnect();
  }, [shown]);

  const ask = SOURCES.ask;
  return (
    <section id="sources" className="l-ink on-ink relative overflow-hidden py-24 sm:py-32">
      <span className="l-orb l-orb-teal" style={{ width: 700, height: 700, right: "-14%", top: "-20%", opacity: 0.35 }} aria-hidden />
      <span className="l-grain" aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead onInk eyebrow={SOURCES.eyebrow} title={[SOURCES.title[0], SOURCES.title[1]]} lead={SOURCES.lead} />
        <div ref={wrap} className="relative mt-16 grid items-start gap-6 lg:grid-cols-[1.05fr_minmax(72px,0.2fr)_0.95fr] lg:gap-0" onPointerLeave={() => setPinned(null)}>
          <Reveal y={24} className="l-win p-5 sm:p-6" style={{ color: "var(--text)" }}>
            <div className="flex items-center justify-between gap-3 border-b border-[rgba(11,25,48,0.08)] pb-3">
              <p className="text-[15px] font-semibold tracking-[-0.01em]">{SOURCES.report.title}</p>
              <span className="l-chip l-chip-review">{SOURCES.report.stamp}</span>
            </div>
            <div className="mt-3 space-y-0.5 text-[14px] leading-relaxed text-[var(--text-2)]">
              {SOURCES.report.lines.map((line, i) => (
                <p key={i} data-quote={i} data-on={activeQuote === i ? "true" : "false"} className="l-quote-line">{line}</p>
              ))}
            </div>
          </Reveal>
          <div className="pointer-events-none hidden lg:block" aria-hidden>
            <svg className="absolute inset-0 h-full w-full overflow-visible">
              <AnimatePresence>
                {lines.map((l) => {
                  const active = l.kind === "field" ? activeField === l.i : activeAns === l.i;
                  return (
                    <motion.path
                      key={`${l.kind}${l.i}`}
                      d={l.d}
                      fill="none"
                      stroke={l.kind === "ans" ? "var(--violet)" : "var(--mint)"}
                      strokeWidth={1.5}
                      initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: active ? 1 : 0.28 }}
                      exit={{ opacity: 0, transition: { duration: 0.25 } }}
                      transition={{ pathLength: { duration: 1, ease: [0.22, 1, 0.36, 1] }, opacity: { duration: 0.4 } }}
                    />
                  );
                })}
              </AnimatePresence>
            </svg>
          </div>
          <div className="space-y-4">
            <Reveal y={24} delay={0.1} className="l-card-ink p-2">
              <p className="px-3.5 pb-1 pt-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-white/50">{SOURCES.valuesTitle}</p>
              <ul className="divide-y divide-white/[0.07]">
                {SOURCES.fields.map((f, i) => (
                  <li key={f.label} data-field={i} onPointerEnter={() => setPinned(i)} onFocus={() => setPinned(i)} onBlur={() => setPinned(null)} tabIndex={0} className={cn("flex cursor-default items-center gap-3 rounded-xl px-3.5 py-3 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--cyan)]", activeField === i && "bg-white/[0.06]")}>
                    <span className="hidden w-[6.5rem] shrink-0 text-[12.5px] uppercase tracking-[0.08em] text-white/55 sm:block">{f.label}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[11px] uppercase tracking-[0.08em] text-white/55 sm:hidden">{f.label}</span>
                      <span className="block text-[17px] font-semibold tracking-[-0.01em] text-white">{f.value}</span>
                      {f.state === "review" ? <span className="block text-[12px] text-white/55">{f.note}</span> : null}
                    </span>
                    {f.state === "verified" ? <span className="l-chip l-chip-ok"><Quote className="size-3" aria-hidden />{ask.labels.verified}</span> : <span className="l-chip l-chip-review"><Eye className="size-3" aria-hidden />{ask.labels.review}</span>}
                  </li>
                ))}
              </ul>
            </Reveal>
            <Reveal y={24} delay={0.2} className="l-card-ink p-4 sm:p-5" testId="ask-demo">
              <div className="flex items-center gap-2.5">
                <span className="grid size-8 place-items-center rounded-lg bg-[rgba(143,100,253,0.18)] text-[#c4b2ff] ring-1 ring-white/10"><MessageSquareText className="size-4" aria-hidden /></span>
                <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-white/50">{ask.title}</p>
              </div>
              <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.04] px-3.5 py-3">
                <p className="min-h-[1.5rem] text-[15.5px] text-white" aria-live="polite">
                  {typed}
                  {typing ? <motion.span className="ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[3px] bg-[var(--mint)]" animate={{ opacity: [1, 0, 1] }} transition={{ duration: 0.8, repeat: Infinity }} aria-hidden /> : null}
                </p>
                <p className="mt-1 text-[12px] text-white/45">{ask.who}</p>
              </div>
              <div className="mt-3 min-h-[8.75rem]">
                <AnimatePresence initial={false}>
                  {ask.answer.slice(0, shown).map((s, i) => (
                    <motion.div key={i} data-ans={i} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.2 } }} transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }} className={cn("flex items-start gap-3 rounded-xl px-3 py-2 transition-colors", activeAns === i && "bg-white/[0.06]")}>
                      <span className="mt-[3px] grid size-5 shrink-0 place-items-center rounded-full bg-white/[0.08] text-[11px] font-semibold text-white/70 tabular-nums">{i + 1}</span>
                      <span className="min-w-0 flex-1 text-[15px] text-white/90">{s.text}</span>
                      {s.review ? <span className="l-chip l-chip-review shrink-0"><Eye className="size-3" aria-hidden />{ask.labels.review}</span> : <span className="l-chip l-chip-ok shrink-0"><Quote className="size-3" aria-hidden />{ask.labels.source}</span>}
                    </motion.div>
                  ))}
                </AnimatePresence>
                <AnimatePresence>
                  {shown >= A ? <motion.p key="note" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-2 px-3 text-[12.5px] text-white/55">{ask.note}</motion.p> : null}
                </AnimatePresence>
              </div>
            </Reveal>
          </div>
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
