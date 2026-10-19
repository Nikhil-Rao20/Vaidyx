// The opening: the title arrives word by word while thousands of points gather into the Vaidyx mark; synthetic record chips
// settle around it. Scrolling lifts the words away and lets the mark drift apart.
import { useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { ArrowDown, ArrowRight } from "lucide-react";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { HERO } from "../content";
import { ParticleMark } from "../components/ParticleMark";
import { Magnetic } from "../components/Magnetic";
import { L_EASE, Words } from "../components/Reveal";
import { useScrollTo } from "../components/lenis";

const SPOTS: Array<{ style: React.CSSProperties; phone?: boolean }> = [
  { style: { left: "-2%", top: "10%" }, phone: true },
  { style: { right: "-3%", top: "25%" } },
  { style: { left: "-7%", bottom: "27%" } },
  { style: { right: "0%", bottom: "11%" }, phone: true },
  { style: { left: "26%", bottom: "-2%" } },
];

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const { me } = useSession();
  const scrollTo = useScrollTo();
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const textY = useTransform(scrollYProgress, [0, 1], [0, 160]);
  const textO = useTransform(scrollYProgress, [0, 0.5], [1, 0]);
  const chipsY = useTransform(scrollYProgress, [0, 1], [0, -90]);
  const disperse = useTransform(scrollYProgress, [0.04, 0.8], [0, 1]);
  const d = (t: number) => (reduce ? 0 : t);
  const drift = (dx: number, dy: number, dur: number) => (reduce ? {} : { animate: { x: [0, dx, 0], y: [0, dy, 0] }, transition: { duration: dur, repeat: Infinity, ease: "easeInOut" as const } });
  return (
    <section id="top" ref={ref} className="l-ink on-ink relative overflow-hidden" data-testid="landing-hero">
      <div className="l-hero-bg" aria-hidden>
        <motion.span className="l-orb l-orb-teal" style={{ width: 760, height: 760, left: "52%", top: "-16%" }} {...drift(50, 36, 24)} />
        <motion.span className="l-orb l-orb-violet" style={{ width: 600, height: 600, left: "-14%", bottom: "-22%" }} {...drift(36, -40, 28)} />
        <span className="l-orb l-orb-blue" style={{ width: 980, height: 640, right: "-24%", bottom: "-34%" }} />
        <span className="l-grid-lines" />
        <span className="l-grain" />
      </div>
      <div className="relative mx-auto grid min-h-[100svh] max-w-[1280px] items-center gap-8 px-5 pb-24 pt-28 sm:px-8 lg:grid-cols-[1.02fr_0.98fr] lg:gap-4 lg:pt-24">
        <motion.div style={{ y: textY, opacity: textO }} className="relative z-10">
          <motion.div className="flex flex-wrap items-center gap-2" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: d(0.15), duration: 0.7, ease: L_EASE }}>
            <span className="l-pill bg-white/[0.04] text-white/85"><span className="size-1.5 rounded-full bg-[var(--mint)] shadow-[0_0_12px_var(--mint)]" aria-hidden />{HERO.eyebrow}</span>
            <span className="l-pill text-white/60"><span className="sm:hidden">by TANUH</span><span className="hidden sm:inline">by TANUH, the AI Centre of Excellence in Healthcare</span></span>
          </motion.div>
          <h1 className="l-display mt-7 text-[clamp(2.85rem,7vw,6.3rem)] text-white">
            <Words text={HERO.title[0]} start={0.35} />
            <span className="l-serif block" style={{ color: "var(--mint)", fontSize: "1.08em" }}><Words text={HERO.title[1]} start={0.75} /></span>
          </h1>
          <motion.p className="l-lead l-muted mt-7 max-w-xl" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: d(1.05), duration: 0.8, ease: L_EASE }}>{HERO.lead}</motion.p>
          <motion.div className="mt-9 flex flex-wrap items-center gap-3" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: d(1.25), duration: 0.8, ease: L_EASE }}>
            <Magnetic><button type="button" className="l-btn l-btn-primary" onClick={() => scrollTo("how")}>{HERO.primary} <ArrowDown className="size-4" aria-hidden /></button></Magnetic>
            <Magnetic><Link to={me ? "/cases" : "/sign-in"} className="l-btn l-btn-ghost">{me ? HERO.open : HERO.signIn} <ArrowRight className="size-4" aria-hidden /></Link></Magnetic>
          </motion.div>
        </motion.div>
        <div className="relative mx-auto aspect-square w-full max-w-[560px] lg:max-w-none">
          <ParticleMark className="absolute inset-0 h-full w-full" progress={disperse} />
          <motion.div style={{ y: chipsY }} className="pointer-events-none absolute inset-0" aria-hidden>
            {HERO.chips.map((c, i) => {
              const Icon = c.icon;
              const spot = SPOTS[i];
              return (
                <motion.div key={c.text} className={cn("absolute", spot.phone ? "flex" : "hidden md:flex")} style={spot.style} initial={{ opacity: 0, y: 18, scale: 0.92 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ delay: d(1.8 + i * 0.16), duration: 0.7, ease: L_EASE }}>
                  <motion.div className="l-float" animate={reduce ? undefined : { y: [0, -7, 0] }} transition={{ delay: 2.6 + i * 0.3, duration: 5 + i * 0.7, repeat: Infinity, ease: "easeInOut" }}>
                    <span className="ic"><Icon className="size-4" aria-hidden /></span>
                    <span><b>{c.text}</b><span>{c.sub}</span></span>
                  </motion.div>
                </motion.div>
              );
            })}
          </motion.div>
        </div>
      </div>
      <motion.div className="absolute bottom-6 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 text-[11px] font-medium uppercase tracking-[0.2em] text-white/45 sm:flex" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: d(2.2), duration: 0.8 }} aria-hidden>
        <span>{HERO.scroll}</span>
        <span className="relative h-9 w-px overflow-hidden bg-white/15">
          <motion.span className="absolute inset-x-0 top-0 h-3 bg-[var(--mint)]" animate={reduce ? undefined : { y: [-14, 40] }} transition={{ duration: 1.7, repeat: Infinity, ease: "easeInOut" }} />
        </span>
      </motion.div>
    </section>
  );
}
