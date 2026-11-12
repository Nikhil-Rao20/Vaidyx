// Ask PubMed (12 Nov): what it promises on the left, an example answer on the right. The example is one real answer of the
// product on public PubMed records (see content.pillars.ts); nothing here is generated in the browser.
import { BookOpenText, Globe, Quote, Search, ShieldOff, type LucideIcon } from "lucide-react";
import { PUBMED } from "../content.pillars";
import { SectionHead } from "../components/SectionHead";
import { Reveal, Stagger } from "../components/Reveal";

type Key = (typeof PUBMED.points)[number]["key"];
const ICON: Record<Key, LucideIcon> = { live: Globe, quote: Quote, memory: ShieldOff, words: Search };

export function PubMed() {
  const d = PUBMED.demo;
  return (
    <section id="pubmed" className="l-section-2 relative overflow-hidden py-24 sm:py-32" data-testid="pubmed">
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={PUBMED.eyebrow} title={[PUBMED.title[0], PUBMED.title[1]]} lead={PUBMED.lead} />
        <div className="mt-14 grid items-start gap-8 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)] lg:gap-12">
          <Stagger className="grid gap-6 sm:grid-cols-2 lg:sticky lg:top-28 lg:grid-cols-1 lg:gap-7">
            {PUBMED.points.map((p) => {
              const I = ICON[p.key];
              return (
                <div key={p.key} className="flex gap-4">
                  <span className="l-icon shrink-0"><I className="size-5" aria-hidden /></span>
                  <div>
                    <h3 className="text-[1.05rem] font-semibold tracking-[-0.01em]">{p.title}</h3>
                    <p className="l-muted mt-1 text-[15px]">{p.text}</p>
                  </div>
                </div>
              );
            })}
          </Stagger>
          <Reveal y={24} className="l-card p-4 sm:p-6" testId="pubmed-demo">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="grid size-8 place-items-center rounded-lg" style={{ background: "var(--l-review-bg)", color: "var(--l-review)" }}><BookOpenText className="size-4" aria-hidden /></span>
                <p className="l-faint text-[12px] font-semibold uppercase tracking-[0.12em]">{d.title}</p>
              </div>
              <span className="l-chip l-chip-review">{d.stamp}</span>
            </div>
            <div className="l-box mt-3 px-3.5 py-3">
              <p className="l-faint text-[11.5px] font-semibold uppercase tracking-[0.1em]">{d.asked}</p>
              <p className="mt-1 text-[15.5px]">{d.question}</p>
            </div>
            <div className="mt-3 rounded-[14px] border border-dashed border-[var(--l-line-2)] px-3.5 py-3">
              <p className="flex items-center gap-2 text-[12.5px] font-semibold text-[var(--l-accent)]"><Search className="size-3.5" aria-hidden />{d.wordsLabel}</p>
              <p className="l-mono l-muted mt-1.5">{d.words}</p>
              <p className="l-faint mt-1.5 text-[12.5px]">{d.counts}</p>
            </div>
            <ol className="mt-4 space-y-4">
              {d.lines.map((l, i) => (
                <li key={l.pmid} className="flex gap-3" data-testid="pubmed-line">
                  <span className="l-faint mt-[3px] grid size-5 shrink-0 place-items-center rounded-full bg-[var(--l-surface-2)] text-[11px] font-semibold tabular-nums" aria-hidden>{i + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[15px]">{l.text}</p>
                    <blockquote className="l-pubquote">
                      <span className="l-chip l-chip-ok mb-1 mr-1.5 align-middle"><Quote className="size-3" aria-hidden />{d.quoteLabel}</span>
                      "{l.quote}"
                    </blockquote>
                    <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px]">
                      <a className="l-link" href={`${d.pmidHref}${l.pmid}/`} target="_blank" rel="noreferrer" aria-label={`${d.pmidLabel} ${l.pmid}, opens PubMed in a new tab`}>{d.pmidLabel} {l.pmid}</a>
                      <span className="l-faint">{l.paper}</span>
                    </p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-5 rounded-[14px] px-3.5 py-3" style={{ background: "var(--l-warn-bg)", color: "var(--l-warn)" }} data-testid="pubmed-label">
              <p className="text-[13.5px] font-semibold">{d.label}</p>
            </div>
            <p className="l-faint mt-3 text-[12.5px]">{d.model}</p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
