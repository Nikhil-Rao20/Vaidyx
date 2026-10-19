// The opening band of a secondary page (About, Docs, Contact): the eyebrow, the title with its serif line, the lead.
import { motion } from "motion/react";
import { L_EASE, Words } from "./Reveal";

export function PageHead({ eyebrow, title, lead, compact }: { eyebrow: string; title: readonly [string, string]; lead?: string; compact?: boolean }) {
  return (
    <section className={`relative overflow-hidden ${compact ? "pb-16 pt-36 sm:pb-20 sm:pt-40" : "pb-20 pt-36 sm:pb-24 sm:pt-44"}`}>
      <div className="l-hero-bg" aria-hidden>
        <span className="l-orb l-orb-teal" style={{ width: 700, height: 700, right: "-10%", top: "-30%" }} />
        <span className="l-orb l-orb-violet" style={{ width: 520, height: 520, left: "-12%", bottom: "-40%" }} />
        <span className="l-grid-lines" />
        <span className="l-grain" />
      </div>
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <motion.span className="l-eyebrow block" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: L_EASE }}>{eyebrow}</motion.span>
        <h1 className="l-display mt-5 max-w-4xl text-[clamp(2.4rem,5.6vw,4.8rem)]">
          <Words text={title[0]} start={0.15} /> <span className="l-serif block sm:inline" style={{ fontSize: "1.08em" }}><Words text={title[1]} start={0.45} /></span>
        </h1>
        {lead ? <motion.p className="l-lead l-muted mt-7 max-w-2xl" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.7, duration: 0.7, ease: L_EASE }}>{lead}</motion.p> : null}
      </div>
    </section>
  );
}
