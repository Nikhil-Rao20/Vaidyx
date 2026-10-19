// The design lab (/lab): the same content laid out in several ways, for the owner to choose from. Not linked from the top bar.
import { SiteFrame } from "../components/SiteFrame";
import { PageHead } from "../components/PageHead";
import { Problem, type ProblemVariant } from "../sections/Problem";

const OPTIONS: Array<{ v: ProblemVariant; name: string; why: string; pick?: boolean }> = [
  { v: "B", name: "Option B: Bento", why: "Three tiles with a badge and a ghost numeral, the national figures as gauges that draw themselves, the observed context on a tinted tile. The one I recommend: the figures read at a glance and the three items stay level.", pick: true },
  { v: "A", name: "Option A: Ledger", why: "No boxes around the items: a numbered ledger of type and hairlines, the observed context as a pull quote, the figures as rows with bars. Quieter and more editorial." },
  { v: "C", name: "Option C: Flow", why: "The three items as steps along a line, which says they happen in sequence; the figures as a compact list with small gauges beside the observed note." },
];

export default function LabPage() {
  return (
    <SiteFrame title="Vaidyx design lab" testId="lab">
      <PageHead eyebrow="Design lab" title={["The problem,", "three ways."]} lead="The same words in three layouts. Choose one, or say what to change." compact />
      {OPTIONS.map((o) => (
        <div key={o.v} className="border-t border-[var(--l-line)]" data-testid={`lab-${o.v}`}>
          <div className="mx-auto max-w-[1280px] px-5 pt-14 sm:px-8">
            <p className="l-eyebrow">{o.name}{o.pick ? " · recommended" : ""}</p>
            <p className="l-muted mt-2 max-w-3xl text-[15px]">{o.why}</p>
          </div>
          <Problem variant={o.v} head={false} />
        </div>
      ))}
    </SiteFrame>
  );
}
