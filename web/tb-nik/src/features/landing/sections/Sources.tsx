// Every value shows where it came from: the synthetic report on the left, "Ask the Case File" on the right. A question is typed;
// lines then run from the report lines that answer it to the answer area; the whole answer arrives at once, each sentence with
// its source. The sequence runs while the section is in view and repeats. Under reduced motion the finished state is shown.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { Eye, MessageSquareText, Quote } from "lucide-react";
import { SOURCES } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Reveal } from "../components/Reveal";

const A = SOURCES.ask.answer.length;
// steps: 0 an empty question; 1 the question is typed; 2 the lines run to the report; 3 the answer, all at once; 4 a pause.
const STEPS = 5;
const dur = (step: number) => (step === 0 ? 1000 : step === 1 ? 2200 : step === 2 ? 1200 : step === 3 ? 600 : 4200);

export function Sources() {
  const wrap = useRef<HTMLDivElement>(null);
  const [paths, setPaths] = useState<string[]>([]);
  const [step, setStep] = useState(0);
  const [chars, setChars] = useState(0);
  const inView = useInView(wrap, { amount: 0.3 });
  const reduce = useReducedMotion();
  const ask = SOURCES.ask;

  const typing = step === 1 && !reduce;
  const asked = reduce || step >= 2;
  const answered = reduce || step >= 3;
  const shown = answered ? A : 0;
  const typed = reduce || step >= 2 ? ask.question : typing ? ask.question.slice(0, chars) : "";
  const onQuote = (i: number) => !reduce && step >= 2 && ask.answer.some((a) => a.quote === i);

  useEffect(() => {
    if (!inView || reduce) return;
    const t = window.setTimeout(() => setStep((s) => (s + 1) % STEPS), dur(step));
    return () => window.clearTimeout(t);
  }, [inView, reduce, step]);

  useEffect(() => {
    if (!typing) { setChars(0); return; }
    const n = ask.question.length;
    const t = window.setInterval(() => setChars((c) => (c >= n ? c : c + 1)), 28);
    return () => window.clearInterval(t);
  }, [typing, ask.question.length]);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const compute = () => {
      if (window.innerWidth < 1024) { setPaths([]); return; }
      const box = el.getBoundingClientRect();
      const out: string[] = [];
      ask.answer.forEach((s, i) => {
        const q = el.querySelector<HTMLElement>(`[data-quote="${s.quote}"]`);
        const d = el.querySelector<HTMLElement>(`[data-ans="${i}"]`);
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
  }, [ask.answer, shown, asked]);

  return (
    <section id="sources" className="l-section relative overflow-hidden py-24 sm:py-32">
      <span className="l-orb l-orb-teal" style={{ width: 700, height: 700, right: "-14%", top: "-20%", opacity: 0.35 }} aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={SOURCES.eyebrow} title={[SOURCES.title[0], SOURCES.title[1]]} lead={SOURCES.lead} />
        <div ref={wrap} className="relative mt-16 grid items-start gap-6 lg:grid-cols-[1fr_minmax(64px,0.18fr)_1fr] lg:gap-0">
          <Reveal y={24} className="l-card p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3 border-b border-[var(--l-line)] pb-3">
              <p className="text-[15px] font-semibold tracking-[-0.01em]">{SOURCES.report.title}</p>
              <span className="l-chip l-chip-review">{SOURCES.report.stamp}</span>
            </div>
            <div className="l-muted mt-3 space-y-0.5 text-[14px] leading-relaxed">
              {SOURCES.report.lines.map((line, i) => (
                <p key={i} data-quote={i} data-on={onQuote(i) ? "true" : "false"} className="l-quote-line">{line}</p>
              ))}
            </div>
          </Reveal>
          <div className="pointer-events-none hidden lg:block" aria-hidden>
            <svg className="absolute inset-0 h-full w-full overflow-visible">
              {asked ? paths.map((d, i) => (
                <motion.path
                  key={i}
                  d={d}
                  fill="none"
                  stroke="var(--violet)"
                  strokeWidth={1.5}
                  initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: answered ? 0.9 : 0.5 }}
                  transition={{ pathLength: { duration: 0.8, delay: i * 0.12, ease: [0.22, 1, 0.36, 1] }, opacity: { duration: 0.4 } }}
                />
              )) : null}
            </svg>
          </div>
          <Reveal y={24} delay={0.1} className="l-card p-4 sm:p-5" testId="ask-demo">
            <div className="flex items-center gap-2.5">
              <span className="grid size-8 place-items-center rounded-lg" style={{ background: "var(--l-review-bg)", color: "var(--l-review)" }}><MessageSquareText className="size-4" aria-hidden /></span>
              <p className="l-faint text-[12px] font-semibold uppercase tracking-[0.12em]">{ask.title}</p>
            </div>
            <div className="l-box mt-3 px-3.5 py-3">
              <p className="min-h-[1.5rem] text-[15.5px]" aria-live="polite">
                {typed || (step === 0 && !reduce ? <span className="l-faint">{ask.placeholder}</span> : null)}
                {typing ? <motion.span className="ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[3px] bg-[var(--l-accent)]" animate={{ opacity: [1, 0, 1] }} transition={{ duration: 0.8, repeat: Infinity }} aria-hidden /> : null}
              </p>
              <p className="l-faint mt-1 text-[12px]">{ask.who}</p>
            </div>
            <div className="mt-3 min-h-[11rem]">
              <AnimatePresence>
                {asked ? (
                  <motion.div key="answer" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.25 } }}>
                    {!reduce && step === 2 ? (
                      <p className="l-faint mb-2 flex items-center gap-2 px-3 text-[12.5px]">
                        <motion.span className="size-1.5 rounded-full bg-[var(--violet)]" animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 0.9, repeat: Infinity }} aria-hidden />{ask.reading}
                      </p>
                    ) : null}
                    {ask.answer.map((s, i) => (
                      <div key={i} data-ans={i} className="flex items-start gap-3 rounded-xl px-3 py-2">
                        <span className="l-faint mt-[3px] grid size-5 shrink-0 place-items-center rounded-full bg-[var(--l-surface-2)] text-[11px] font-semibold tabular-nums">{i + 1}</span>
                        {shown > i ? (
                          <>
                            <motion.span className="min-w-0 flex-1 text-[15px]" initial={reduce ? false : { opacity: 0, y: 8, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 0.4, delay: i * 0.07, ease: [0.22, 1, 0.36, 1] }}>{s.text}</motion.span>
                            <motion.span className="shrink-0" initial={reduce ? false : { opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.3, delay: 0.25 + i * 0.07 }}>
                              {s.review ? <span className="l-chip l-chip-review"><Eye className="size-3" aria-hidden />{ask.labels.review}</span> : <span className="l-chip l-chip-ok"><Quote className="size-3" aria-hidden />{ask.labels.source}</span>}
                            </motion.span>
                          </>
                        ) : (
                          <span className="flex-1 space-y-1.5 py-1"><span className="l-skeleton block h-3 w-11/12" /><span className="l-skeleton block h-3 w-7/12" /></span>
                        )}
                      </div>
                    ))}
                    <AnimatePresence>
                      {shown >= A ? <motion.p key="note" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ delay: 0.4 }} className="l-faint mt-2 px-3 text-[12.5px]">{ask.note}</motion.p> : null}
                    </AnimatePresence>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
