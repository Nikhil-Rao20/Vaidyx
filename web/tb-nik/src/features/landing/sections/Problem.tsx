// The problem: the owner's three items, the observed context and the national figures with their source, laid out as bento
// tiles (sections/problem/OptionB, the layout the owner chose on 20 Oct).
import { CHALLENGE } from "../content";
import { SectionHead } from "../components/SectionHead";
import { OptionB } from "./problem/OptionB";

export function Problem() {
  return (
    <section id="why" className="l-section py-24 sm:py-32">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={CHALLENGE.eyebrow} title={[CHALLENGE.title[0], CHALLENGE.title[1]]} lead={CHALLENGE.lead} />
        <div className="mt-16"><OptionB /></div>
      </div>
    </section>
  );
}
