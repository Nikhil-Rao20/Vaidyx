// What Vaidyx does, in five boxes under the hero (12 Nov). Each box is a link to the section that tells its story: two of them
// are the owner's sections (traceability, how it works), three are new (PubMed, benchmark, runs locally). One row of five on a
// laptop, 3 + 2 on a tablet, a list of five rows on a phone. A click eases to the section with the page's own smooth scroll.
import { ArrowDown, BookOpenText, FlaskConical, Quote, ServerCog, Workflow, type LucideIcon } from "lucide-react";
import { PILLARS } from "../content.pillars";
import { SectionHead } from "../components/SectionHead";
import { Stagger } from "../components/Reveal";
import { useScrollTo } from "../components/lenis";

type Key = (typeof PILLARS.items)[number]["key"];
const ICON: Record<Key, LucideIcon> = { proof: Quote, pubmed: BookOpenText, benchmark: FlaskConical, local: ServerCog, assistant: Workflow };
// the soft badge tones of the problem section, one per box
const TONE: Record<Key, { tone: string; bg: string }> = {
  proof: { tone: "#0a6a86", bg: "rgba(1, 180, 194, 0.12)" },
  pubmed: { tone: "#5b3fc4", bg: "rgba(143, 100, 253, 0.12)" },
  benchmark: { tone: "#0b4e74", bg: "rgba(11, 78, 116, 0.1)" },
  local: { tone: "#0a6a86", bg: "rgba(1, 180, 194, 0.12)" },
  assistant: { tone: "#5b3fc4", bg: "rgba(143, 100, 253, 0.12)" },
};

export function Pillars() {
  const scrollTo = useScrollTo();
  return (
    <section id="what" className="l-section pt-20 sm:pt-24" data-testid="pillars">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={PILLARS.eyebrow} title={[PILLARS.title[0], PILLARS.title[1]]} />
        <Stagger className="l-pillars mt-10 sm:mt-12" itemClassName="h-full">
          {PILLARS.items.map((p, i) => {
            const Icon = ICON[p.key];
            return (
              <a
                key={p.key}
                href={`#${p.to}`}
                className="l-pillar"
                data-testid={`pillar-${p.key}`}
                onClick={(e) => { e.preventDefault(); scrollTo(p.to); }}
              >
                <span className="l-badge-soft l-pillar-icon" style={{ "--tone": TONE[p.key].tone, "--tone-bg": TONE[p.key].bg } as React.CSSProperties}><Icon className="size-[20px]" strokeWidth={1.7} aria-hidden /></span>
                <span className="l-pillar-body">
                  <span className="l-eyebrow !text-[0.68rem] !text-[var(--l-fg-3)]" aria-hidden>0{i + 1}</span>
                  <span className="l-title mt-1 block text-[1.06rem] leading-[1.2]">{p.title}</span>
                  <span className="l-muted mt-1.5 block text-[14px] leading-[1.45]">{p.text}</span>
                </span>
                <span className="l-pillar-go"><span className="l-pillar-go-text">{PILLARS.go}</span><span className="l-pillar-arrow"><ArrowDown className="size-3.5" aria-hidden /></span></span>
              </a>
            );
          })}
        </Stagger>
      </div>
    </section>
  );
}
