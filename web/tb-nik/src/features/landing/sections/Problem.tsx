// The problem: three items, the observed context and the national figures with their source. The layout is one of the three in
// sections/problem (the design lab at /lab shows all three); Option B is the one on the product page.
import { CHALLENGE } from "../content";
import { SectionHead } from "../components/SectionHead";
import { OptionA } from "./problem/OptionA";
import { OptionB } from "./problem/OptionB";
import { OptionC } from "./problem/OptionC";

export type ProblemVariant = "A" | "B" | "C";
const LAYOUTS = { A: OptionA, B: OptionB, C: OptionC };

export function Problem({ variant = "B", head = true }: { variant?: ProblemVariant; head?: boolean }) {
  const Layout = LAYOUTS[variant];
  return (
    <section id="why" className="l-section py-24 sm:py-32" data-variant={variant}>
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        {head ? <SectionHead eyebrow={CHALLENGE.eyebrow} title={[CHALLENGE.title[0], CHALLENGE.title[1]]} lead={CHALLENGE.lead} /> : null}
        <div className={head ? "mt-16" : ""}><Layout /></div>
      </div>
    </section>
  );
}
