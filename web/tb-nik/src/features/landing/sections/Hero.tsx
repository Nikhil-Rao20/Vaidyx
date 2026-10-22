// The opening: the title arrives word by word while thousands of points stream in from the corners of the screen and gather
// into the Vaidyx mark. Scrolling lifts the words away and lets the mark drift apart.
import { useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { ArrowDown, ArrowRight } from "lucide-react";
import { useSession } from "@/lib/session";
import { HERO, SITE } from "../content";
import { ParticleMark } from "../components/ParticleMark";
import { Magnetic } from "../components/Magnetic";
import { L_EASE, Words } from "../components/Reveal";
import { useScrollTo } from "../components/lenis";

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const { me } = useSession();
  const scrollTo = useScrollTo();
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const textY = useTransform(scrollYProgress, [0, 1], [0, 160]);
  const textO = useTransform(scrollYProgress, [0, 0.5], [1, 0]);
  const disperse = useTransform(scrollYProgress, [0.04, 0.8], [0, 1]);
  const d = (t: number) => (reduce ? 0 : t);
  const drift = (dx: number, dy: number, dur: number) => (reduce ? {} : { animate: { x: [0, dx, 0], y: [0, dy, 0] }, transition: { duration: dur, repeat: Infinity, ease: "easeInOut" as const } });
  return (
    <section id="top" ref={ref} className="relative overflow-hidden" data-testid="landing-hero">
      <div className="l-hero-bg" aria-hidden>
        <motion.span className="l-orb l-orb-teal" style={{ width: 760, height: 760, left: "52%", top: "-16%" }} {...drift(50, 36, 24)} />
        <motion.span className="l-orb l-orb-violet" style={{ width: 600, height: 600, left: "-14%", bottom: "-22%" }} {...drift(36, -40, 28)} />
        <span className="l-orb l-orb-blue" style={{ width: 980, height: 640, right: "-24%", bottom: "-34%" }} />
        <span className="l-grid-lines" />
        <span className="l-grain" />
      </div>
      <div className="relative mx-auto grid min-h-[100svh] max-w-[1280px] items-start gap-8 px-5 pb-32 pt-24 sm:px-8 lg:grid-cols-[1.02fr_0.98fr] lg:gap-4 lg:pb-40 lg:pt-24">
        <motion.div style={{ y: textY, opacity: textO }} className="relative z-10 lg:pt-10">
          <h1 className="l-display text-[clamp(2.6rem,6.2vw,5.6rem)]">
            <Words text={HERO.title[0]} start={d(0.35)} />
            <span className="l-serif block" style={{ fontSize: "1.08em" }}><Words text={HERO.title[1]} start={d(0.75)} /></span>
          </h1>
          <motion.p className="l-lead l-muted mt-7 max-w-xl" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: d(1.05), duration: 0.8, ease: L_EASE }}>{HERO.lead}</motion.p>
          <motion.div className="mt-9 flex flex-wrap items-center gap-3" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: d(1.25), duration: 0.8, ease: L_EASE }}>
            <Magnetic><button type="button" className="l-btn l-btn-primary" onClick={() => scrollTo("how")}>{HERO.primary} <ArrowDown className="size-4" aria-hidden /></button></Magnetic>
            <Magnetic><Link to={me ? "/cases" : "/sign-in"} className="l-btn l-btn-ghost">{me ? SITE.open : SITE.signIn} <ArrowRight className="size-4" aria-hidden /></Link></Magnetic>
          </motion.div>
        </motion.div>
        <div className="relative mx-auto aspect-square w-full max-w-[560px] lg:max-w-none">
          <ParticleMark className="absolute inset-0 h-full w-full" progress={disperse} />
        </div>
      </div>
      <motion.div className="l-faint absolute bottom-6 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 text-[11px] font-medium uppercase tracking-[0.2em] sm:flex" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: d(2.2), duration: 0.8 }} aria-hidden>
        <span>{HERO.scroll}</span>
        <span className="relative h-9 w-px overflow-hidden bg-[var(--l-line-2)]">
          <motion.span className="absolute inset-x-0 top-0 h-3 bg-[var(--l-accent)]" animate={reduce ? undefined : { y: [-14, 40] }} transition={{ duration: 1.7, repeat: Infinity, ease: "easeInOut" }} />
        </span>
      </motion.div>
    </section>
  );
}
