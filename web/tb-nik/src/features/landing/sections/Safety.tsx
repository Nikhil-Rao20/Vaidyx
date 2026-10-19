// Safe by design: six principles, not interactive. The layout is one of three in sections/safety (the design lab at /lab shows
// all three); Option B, the illustrated cards, is on the product page until the owner chooses.
import { SAFETY } from "../content";
import { SectionHead } from "../components/SectionHead";
import { OptionA } from "./safety/OptionA";
import { OptionB } from "./safety/OptionB";
import { OptionC } from "./safety/OptionC";

export type SafetyVariant = "A" | "B" | "C";
const LAYOUTS = { A: OptionA, B: OptionB, C: OptionC };

export function Safety({ variant = "B", head = true }: { variant?: SafetyVariant; head?: boolean }) {
  const Layout = LAYOUTS[variant];
  return (
    <section id="safety" className="l-section-2 relative overflow-hidden py-24 sm:py-32" data-variant={variant} data-testid="safety">
      <span className="l-orb l-orb-violet" style={{ width: 640, height: 640, left: "-10%", top: "10%", opacity: 0.35 }} aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        {head ? <SectionHead eyebrow={SAFETY.eyebrow} title={[SAFETY.title[0], SAFETY.title[1]]} lead={SAFETY.lead} /> : null}
        <div className={head ? "mt-16" : ""}><Layout /></div>
      </div>
    </section>
  );
}
