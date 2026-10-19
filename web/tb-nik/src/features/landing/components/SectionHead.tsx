// A section's opening: the eyebrow, the title with its second line in the serif face, the lead. The thin rule draws itself.
import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";
import { Reveal, Words } from "./Reveal";

export function SectionHead({ eyebrow, title, lead, className, center, size = "md" }: { eyebrow?: string; title: readonly [string, string]; lead?: string; className?: string; center?: boolean; size?: "md" | "lg" }) {
  const reduce = useReducedMotion();
  return (
    <div className={cn("max-w-3xl", center && "mx-auto text-center", className)}>
      {eyebrow ? (
        <Reveal y={12} className={cn("flex items-center gap-3", center && "justify-center")}>
          {!center ? <motion.span className="l-rule w-10" initial={reduce ? false : { scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} aria-hidden /> : null}
          <span className="l-eyebrow">{eyebrow}</span>
        </Reveal>
      ) : null}
      <h2 className={cn("l-title mt-5", size === "lg" ? "text-[clamp(2.4rem,5.2vw,4.4rem)]" : "text-[clamp(2rem,4.2vw,3.5rem)]")}>
        <Words text={title[0]} inView />{" "}
        <span className="l-serif block sm:inline" style={{ fontSize: "1.08em" }}><Words text={title[1]} inView start={0.25} /></span>
      </h2>
      {lead ? <Reveal delay={0.15} y={16}><p className={cn("l-lead l-muted mt-6", center && "mx-auto")}>{lead}</p></Reveal> : null}
    </div>
  );
}
