// The entrance options: the same lockup (the mark above the wordmark, large, on the plain field) arriving in five ways.
// Each plays once when mounted; `length` is the time in ms before the page may dissolve it.
import { useLayoutEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { BrandLockup, BrandMark, BrandWord } from "@/components/BrandReveal";
import { ParticleMark } from "../components/ParticleMark";
import { AnimatedWord, DrawnMark, E } from "./parts";

export const MARK_W = "clamp(170px, 30vmin, 300px)";
export const WORD_H = "clamp(64px, 11vmin, 118px)";
const markStyle = { width: MARK_W } as React.CSSProperties;
const wordStyle = { height: WORD_H, width: "auto" } as React.CSSProperties;

export interface IntroOption { key: string; name: string; why: string; length: number; Component: () => React.JSX.Element }

/** A: the brand's own reveal: the V sweeps in, the slants lock, the light crosses, the wordmark wipes in. */
function IntroAssemble() {
  const r = useReducedMotion();
  return (
    <BrandLockup play={!r} still={!!r} speed={2}>
      <BrandMark style={{ "--br-mark-w": MARK_W } as React.CSSProperties} />
      <BrandWord style={{ "--br-word-h": WORD_H } as React.CSSProperties} />
    </BrandLockup>
  );
}

/** B: points stream in from the corners and settle into the mark; the letters rise one by one; the crisp mark fades over. The
 * canvas covers the whole stage and is told where the mark sits and how wide it is. */
function IntroParticles() {
  const r = useReducedMotion();
  const stage = useRef<HTMLDivElement>(null);
  const mark = useRef<HTMLImageElement>(null);
  const [geo, setGeo] = useState<{ centre: { x: number; y: number }; radius: number } | null>(null);
  useLayoutEffect(() => {
    const measure = () => {
      const st = stage.current?.getBoundingClientRect(), m = mark.current?.getBoundingClientRect();
      if (!st || !m || !m.width) return;
      setGeo({ centre: { x: m.left + m.width / 2 - st.left, y: m.top + m.height / 2 - st.top }, radius: m.width / 2 });
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (stage.current) ro.observe(stage.current);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={stage} className="absolute inset-0 grid place-items-center">
      {!r && geo ? <motion.div className="absolute inset-0" initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={{ delay: 2.4, duration: 0.7 }}><ParticleMark className="h-full w-full" count={1800} centre={geo.centre} radius={geo.radius} /></motion.div> : null}
      <div className="relative flex flex-col items-center gap-7">
        <motion.img ref={mark} src="/static/tb-nik/brand/vaidyx-icon.svg" alt="" style={markStyle} className="h-auto" initial={{ opacity: r ? 1 : 0, scale: r ? 1 : 1.04 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: r ? 0 : 2.3, duration: 0.8, ease: E }} />
        <AnimatedWord mode="rise" delay={1.7} style={wordStyle} />
      </div>
    </div>
  );
}

/** C: a line draws the mark, then the letters, and each fills as the line fades. */
function IntroDraw() {
  return (
    <div className="flex flex-col items-center gap-7">
      <DrawnMark delay={0.1} style={markStyle} />
      <AnimatedWord mode="draw" delay={0.9} step={0.12} style={wordStyle} />
    </div>
  );
}

/** D: the mark wipes in from the left and the wordmark from the right, a hairline rises between them, then they settle side by side. */
function IntroWipe() {
  const r = useReducedMotion();
  return (
    <div className="flex items-center gap-8 sm:gap-12">
      <motion.div initial={r ? false : { clipPath: "inset(0 100% 0 0)", x: -40 }} animate={{ clipPath: "inset(0 0% 0 0)", x: 0 }} transition={{ duration: 1.1, ease: E }}>
        <BrandMark style={{ "--br-mark-w": "clamp(120px, 22vmin, 220px)" } as React.CSSProperties} className="br-still" />
      </motion.div>
      <motion.span className="w-px self-stretch bg-[var(--l-line-2)]" initial={r ? false : { scaleY: 0 }} animate={{ scaleY: 1 }} transition={{ delay: 0.5, duration: 0.8, ease: E }} aria-hidden />
      <motion.div initial={r ? false : { clipPath: "inset(0 0 0 100%)", x: 40 }} animate={{ clipPath: "inset(0 0 0 0%)", x: 0 }} transition={{ delay: 0.35, duration: 1.1, ease: E }}>
        <BrandWord style={{ "--br-word-h": "clamp(56px, 10vmin, 104px)" } as React.CSSProperties} className="br-still" />
      </motion.div>
    </div>
  );
}

/** E: the lockup opens through an iris while it settles from slightly larger, then a light passes over the wordmark. */
function IntroIris() {
  const r = useReducedMotion();
  return (
    <motion.div className="flex flex-col items-center gap-7" initial={r ? false : { clipPath: "circle(0% at 50% 50%)", scale: 1.14 }} animate={{ clipPath: "circle(75% at 50% 50%)", scale: 1 }} transition={{ duration: 1.5, ease: E }}>
      <BrandMark style={{ "--br-mark-w": MARK_W } as React.CSSProperties} className="br-still" />
      <div className="relative overflow-hidden">
        <BrandWord style={{ "--br-word-h": WORD_H } as React.CSSProperties} className="br-still" />
        {!r ? <motion.span aria-hidden className="pointer-events-none absolute inset-y-0 w-1/3" style={{ background: "linear-gradient(100deg, transparent, rgba(255,255,255,0.75), transparent)", mixBlendMode: "screen" }} initial={{ left: "-40%" }} animate={{ left: "120%" }} transition={{ delay: 1.5, duration: 1.1, ease: "easeInOut" }} /> : null}
      </div>
    </motion.div>
  );
}

export const INTROS: IntroOption[] = [
  { key: "A", name: "Option A: Assemble", why: "The brand's own reveal: the V sweeps in, the two slants lock with a pulse, a light crosses the mark, the wordmark wipes in. Now large and on a plain field.", length: 3150, Component: IntroAssemble },
  { key: "B", name: "Option B: Particles", why: "Points stream in from the corners of the screen and settle into the mark, the crisp mark fades over them, and the letters of the wordmark rise one by one with the dots dropping in last. Ties the entrance to the hero.", length: 3600, Component: IntroParticles },
  { key: "C", name: "Option C: Line draw", why: "A thin line draws the mark part by part and then each letter, and the shapes fill as the line fades. Quiet and precise.", length: 3400, Component: IntroDraw },
  { key: "D", name: "Option D: Wipe", why: "The mark wipes in from the left, the wordmark from the right, and a hairline rises between them: a title card, side by side.", length: 2600, Component: IntroWipe },
  { key: "E", name: "Option E: Iris", why: "The lockup opens through a circle while it settles from slightly larger, then a light passes over the wordmark. Soft and cinematic.", length: 3000, Component: IntroIris },
];
