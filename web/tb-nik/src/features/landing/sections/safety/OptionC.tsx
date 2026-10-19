// Option C, "Band": one gradient line across the section with the six principles as stations on it, above and below in
// turn. Every station is a column of three rows (text above, the badge on the line, text below) so the line sits at the same
// height in every column. On a phone the line runs down the left and the stations stack.
import { motion, useReducedMotion } from "motion/react";
import { SAFETY } from "../../content";
import { Stagger } from "../../components/Reveal";
import { BADGES, ICONS } from "./shared";

const AREA = "9.5rem";   // the height of the text area above and below the line

export function OptionC() {
  const reduce = useReducedMotion();
  const badge = (i: number) => {
    const Icon = ICONS[SAFETY.principles[i].key];
    return <span className="l-badge" style={{ "--badge": BADGES[i].bg, "--badge-shadow": BADGES[i].shadow } as React.CSSProperties}><Icon className="size-5" strokeWidth={1.9} aria-hidden /></span>;
  };
  const text = (i: number) => {
    const p = SAFETY.principles[i];
    return (
      <>
        <span className="l-eyebrow">0{i + 1}</span>
        <h3 className="mt-1 text-[1.05rem] font-semibold tracking-[-0.01em]">{p.title}</h3>
        <p className="l-muted mt-1.5 text-[14.5px]">{p.text}</p>
      </>
    );
  };
  return (
    <>
      {/* laptop: the band */}
      <div className="relative hidden md:block">
        <motion.span className="absolute inset-x-0 h-[3px] rounded-full" style={{ top: `calc(${AREA} + 1.5rem - 1.5px)`, background: "linear-gradient(90deg, var(--cyan), var(--violet))", transformOrigin: "left" }} initial={reduce ? false : { scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true, amount: 0.3 }} transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1] }} aria-hidden />
        <Stagger className="grid grid-cols-6 gap-x-4">
          {SAFETY.principles.map((p, i) => {
            const up = i % 2 === 0;
            return (
              <div key={p.key} className="grid text-center" style={{ gridTemplateRows: `${AREA} 3rem ${AREA}` }}>
                <div className="flex flex-col justify-end pb-5">{up ? text(i) : null}</div>
                <div className="grid place-items-center">{badge(i)}</div>
                <div className="pt-5">{!up ? text(i) : null}</div>
              </div>
            );
          })}
        </Stagger>
      </div>
      {/* phone: the line runs down the left */}
      <div className="relative md:hidden">
        <span className="absolute left-[1.45rem] top-2 h-[calc(100%-1rem)] w-[3px] rounded-full" style={{ background: "linear-gradient(180deg, var(--cyan), var(--violet))" }} aria-hidden />
        <Stagger className="space-y-8">
          {SAFETY.principles.map((p, i) => (
            <div key={p.key} className="relative flex gap-5">
              <span className="relative z-10 shrink-0">{badge(i)}</span>
              <div className="pt-1">{text(i)}</div>
            </div>
          ))}
        </Stagger>
      </div>
    </>
  );
}
