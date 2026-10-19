// Made for everyone on the Board: a table with a seat for each role around the Case File. A seat lights its connector and
// shows the role's card; the seats take turns until someone chooses one.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { Check, FileText } from "lucide-react";
import { ROLES } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Reveal } from "../components/Reveal";

const SEATS: Array<{ from: string; to: string; shadow: string }> = [
  { from: "#0a8fb0", to: "#0a6a86", shadow: "rgba(10,106,134,0.55)" },
  { from: "#5fdcd6", to: "#1fb9cc", shadow: "rgba(31,185,204,0.55)" },
  { from: "#8f64fd", to: "#5b3fc4", shadow: "rgba(91,63,196,0.55)" },
  { from: "#1b7fb5", to: "#0b4e74", shadow: "rgba(11,78,116,0.55)" },
  { from: "#0b4e74", to: "#00183c", shadow: "rgba(0,24,60,0.55)" },
  { from: "#5c6b7c", to: "#2b3645", shadow: "rgba(43,54,69,0.55)" },
];
const R = 41; // seat ring radius, in % of the table

export function Roles() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { amount: 0.35 });
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const [chosen, setChosen] = useState(false);
  const n = ROLES.cards.length;
  useEffect(() => {
    if (!inView || chosen || reduce) return;
    const t = window.setInterval(() => setActive((a) => (a + 1) % n), 4200);
    return () => window.clearInterval(t);
  }, [inView, chosen, reduce, n]);
  const role = ROLES.cards[active];
  const pos = (i: number) => { const a = (-90 + (360 / n) * i) * (Math.PI / 180); return { x: 50 + R * Math.cos(a), y: 50 + R * Math.sin(a) }; };
  return (
    <section id="roles" ref={ref} className="l-section-2 py-24 sm:py-32">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={ROLES.eyebrow} title={[ROLES.title[0], ROLES.title[1]]} lead={ROLES.lead} />
        <div className="mt-14 grid items-center gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
          <Reveal y={20}>
            <div className="l-table" data-testid="roles-table">
              <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" aria-hidden>
                <motion.circle cx={50} cy={50} r={R} fill="none" stroke="var(--l-line-2)" strokeWidth={0.35} strokeDasharray="1.4 2.2" style={{ transformOrigin: "50% 50%" }} animate={reduce ? undefined : { rotate: 360 }} transition={{ duration: 120, repeat: Infinity, ease: "linear" }} />
                <motion.circle cx={50} cy={50} r={27} fill="none" stroke="var(--l-line)" strokeWidth={0.35} strokeDasharray="0.6 2" style={{ transformOrigin: "50% 50%" }} animate={reduce ? undefined : { rotate: -360 }} transition={{ duration: 90, repeat: Infinity, ease: "linear" }} />
                {ROLES.cards.map((c, i) => {
                  const p = pos(i);
                  const on = i === active;
                  return (
                    <g key={c.key}>
                      <line x1={50} y1={50} x2={p.x} y2={p.y} stroke="var(--l-line-2)" strokeWidth={0.3} />
                      {on ? <motion.line x1={50} y1={50} x2={p.x} y2={p.y} stroke="var(--cyan)" strokeWidth={0.6} strokeDasharray="2 1.6" initial={{ pathLength: 0 }} animate={{ pathLength: 1, strokeDashoffset: reduce ? 0 : [0, -14.4] }} transition={{ pathLength: { duration: 0.6 }, strokeDashoffset: { duration: 2.4, repeat: Infinity, ease: "linear" } }} /> : null}
                    </g>
                  );
                })}
              </svg>
              <div className="l-centre" aria-hidden>
                <div className="flex flex-col items-center gap-1.5">
                  <span className="l-icon !size-11"><FileText className="size-5" /></span>
                  <span className="text-[12px] font-semibold tracking-[-0.01em]">{ROLES.centre}</span>
                </div>
              </div>
              {ROLES.cards.map((c, i) => {
                const p = pos(i);
                const Icon = c.icon;
                const s = SEATS[i];
                return (
                  <button
                    key={c.key}
                    type="button"
                    className="l-seat"
                    style={{ left: `${p.x}%`, top: `${p.y}%`, "--seat": `linear-gradient(145deg, ${s.from}, ${s.to})`, "--seat-shadow": s.shadow } as React.CSSProperties}
                    data-active={i === active}
                    aria-pressed={i === active}
                    aria-label={c.title}
                    onClick={() => { setActive(i); setChosen(true); }}
                    onPointerEnter={(e) => { if (e.pointerType === "mouse") { setActive(i); setChosen(true); } }}
                  >
                    <span className="disc"><Icon className="size-6" strokeWidth={1.9} aria-hidden /></span>
                    <span>{c.short}</span>
                  </button>
                );
              })}
            </div>
          </Reveal>
          <div className="relative min-h-[22rem]">
            <AnimatePresence mode="wait" initial={false}>
              <motion.article
                key={role.key}
                className="l-card p-7 sm:p-9"
                data-testid="role-card"
                initial={reduce ? false : { opacity: 0, y: 14, scale: 0.99 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, transition: { duration: 0.22 } }}
                transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
              >
                <p className="l-eyebrow">{active + 1} of {n}</p>
                <h3 className="l-title mt-3 text-[clamp(1.5rem,2.4vw,2rem)]">{role.title}</h3>
                <p className="l-muted mt-3 text-[1.05rem]">{role.text}</p>
                <ul className="mt-6 space-y-2.5 border-t border-[var(--l-line)] pt-6">
                  {role.points.map((pt, j) => (
                    <motion.li key={pt} className="flex items-start gap-3" initial={reduce ? false : { opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + j * 0.08, duration: 0.4 }}>
                      <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full" style={{ background: "var(--l-ok-bg)", color: "var(--l-ok)" }}><Check className="size-3" strokeWidth={3} aria-hidden /></span>
                      <span>{pt}</span>
                    </motion.li>
                  ))}
                </ul>
              </motion.article>
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
}
