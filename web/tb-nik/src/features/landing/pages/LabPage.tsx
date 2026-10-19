// The design lab (/lab): the same content laid out in several ways, for the owner to choose from. Not linked from the top bar.
import { SiteFrame } from "../components/SiteFrame";
import { PageHead } from "../components/PageHead";
import { Safety, type SafetyVariant } from "../sections/Safety";

const OPTIONS: Array<{ v: SafetyVariant; name: string; why: string; pick?: boolean }> = [
  { v: "B", name: "Option B: Illustrated", why: "Six cards, each with its own drawing in a tinted header: the draft becoming reviewed, the value and its line, the scan for doctors, the on-site server, the order of sources, the audit log. The richest of the three; the one I recommend.", pick: true },
  { v: "A", name: "Option A: Shield", why: "One drawing, a shield with the Vaidyx mark and the words Doctor-led, beside the six principles as a two-column list with badges. Calm and compact." },
  { v: "C", name: "Option C: Band", why: "One gradient line across the section with the six principles as stations on it, above and below in turn. Reads as a route; on a phone the line runs down the left." },
];

export default function LabPage() {
  return (
    <SiteFrame title="Vaidyx design lab" testId="lab">
      <PageHead eyebrow="Design lab" title={["Safe by design,", "three ways."]} lead="The same words in three layouts, none of them interactive. Choose one, or say what to change." compact />
      {OPTIONS.map((o) => (
        <div key={o.v} className="border-t border-[var(--l-line)]" data-testid={`lab-${o.v}`}>
          <div className="mx-auto max-w-[1280px] px-5 pt-14 sm:px-8">
            <p className="l-eyebrow">{o.name}{o.pick ? " · recommended" : ""}</p>
            <p className="l-muted mt-2 max-w-3xl text-[15px]">{o.why}</p>
          </div>
          <Safety variant={o.v} head={false} />
        </div>
      ))}
    </SiteFrame>
  );
}
