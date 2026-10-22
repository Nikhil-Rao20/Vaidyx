// Safe by design: six principles as illustrated cards, not interactive (the layout the owner chose on 20 Oct).
import { SAFETY } from "../content";
import { SectionHead } from "../components/SectionHead";
import { OptionB } from "./safety/OptionB";

export function Safety() {
  return (
    <section id="safety" className="l-section relative overflow-hidden py-24 sm:py-32" data-testid="safety">
      <span className="l-orb l-orb-violet" style={{ width: 640, height: 640, left: "-10%", top: "10%", opacity: 0.35 }} aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={SAFETY.eyebrow} title={[SAFETY.title[0], SAFETY.title[1]]} lead={SAFETY.lead} />
        <div className="mt-16"><OptionB /></div>
      </div>
    </section>
  );
}
