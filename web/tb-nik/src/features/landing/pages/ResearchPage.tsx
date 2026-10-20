// Research: the benchmark and the grounded evaluations, written like a paper (numbered sections, static tables, data cards),
// with the typeset PDF as the one download. Words in content.ts (RESEARCH), numbers in research/data.ts (generated).
import { Download, ExternalLink } from "lucide-react";
import { SiteFrame } from "../components/SiteFrame";
import { PageHead } from "../components/PageHead";
import { Reveal, Stagger } from "../components/Reveal";
import { Cta } from "../sections/Cta";
import { RESEARCH as R } from "../content";
import { RESEARCH_DATA as D } from "../research/data";
import { DataCard, Items, P, Sec, Sub } from "../research/ui";
import {
  AnswerabilityTable, BakeoffTable, ImageAllTable, ImagePublishedTable, ImageSplitTable, ModelsTable, OcrTables, OmniTable, Q4Table, StatusTable,
  TcgaTable, TextCotTable, TextDirectTable, TextPublishedTable, ThroughputTable,
} from "../research/tables";
import "../research/research.css";

const TOC = [
  ["abstract", R.abstract.title], ["why", R.why.title], ["models", R.models.title], ["benchmarks", R.data.title], ["protocol", R.protocol.title],
  ["text", R.text.title], ["image", R.image.title], ["throughput", R.throughput.title], ["grounded", R.grounded.title], ["findings", R.findings.title],
  ["caveats", R.caveats.title], ["uses", R.uses.title], ["sources", R.sources.title],
] as const;

export default function ResearchPage() {
  const p = R.paper;
  const textCards = D.dataCards.filter((c) => c.kind === "text");
  const imageCards = D.dataCards.filter((c) => c.kind === "image");
  const labels = { ...R.data.fields, kind: "" };
  return (
    <SiteFrame title="Vaidyx research" testId="research">
      <PageHead eyebrow={R.eyebrow} title={[R.title[0], R.title[1]]} lead={R.lead} compact />

      <section className="l-section pb-24 sm:pb-32">
        <div className="mx-auto max-w-[1240px] px-5 sm:px-8">
          {/* The paper's front matter: title, authors, affiliation, the download, the four numbers. */}
          <Reveal className="l-card p-6 sm:p-9" testId="research-paper">
            <div className="grid gap-8 lg:grid-cols-[1fr_auto] lg:items-start">
              <div className="min-w-0">
                <span className="l-eyebrow">{p.kind} · {p.date}</span>
                <h2 className="l-title mt-3 text-[clamp(1.5rem,2.8vw,2.3rem)]">{p.title}</h2>
                <p className="r-byline mt-5">
                  {p.authors.map((a, i) => (
                    <span key={a}>{i > 0 ? ", " : ""}<b>{a}</b>{a === p.corresponding ? <sup aria-label="corresponding author">*</sup> : null}</span>
                  ))}
                </p>
                <p className="r-byline mt-1">{p.affiliation}</p>
              </div>
              <a href={p.file} className="l-btn l-btn-dark shrink-0" download data-testid="research-download">
                <Download className="size-4" aria-hidden /> {p.download}
              </a>
            </div>
            <Stagger className="mt-8 grid grid-cols-2 gap-4 border-t pt-7 sm:grid-cols-4" itemClassName="min-w-0" amount={0.3}>
              {p.facts.map(([v, l]) => (
                <div key={l}><div className="r-fact">{v}</div><div className="l-mini l-muted mt-1.5 uppercase tracking-[0.12em]">{l}</div></div>
              ))}
            </Stagger>
          </Reveal>

          {/* The contents, a plain list of anchors, under the front matter so the tables keep the full width. */}
          <Reveal y={10} className="mt-6">
            <nav aria-label={R.contents} className="r-toc l-box px-6 py-5 sm:px-8" data-testid="research-contents">
              <span className="l-eyebrow">{R.contents}</span>
              <ol className="mt-4 grid gap-x-8 gap-y-2 text-[14px] leading-snug sm:grid-cols-2 lg:grid-cols-4">
                {TOC.map(([id, t], i) => <li key={id} className="flex gap-2"><span className="l-faint w-5 shrink-0 tabular-nums">{i + 1}</span><a href={`#${id}`}>{t}</a></li>)}
              </ol>
            </nav>
          </Reveal>

          <div className="mt-14 sm:mt-20">
            <article className="min-w-0 space-y-2">
              <Sec id="abstract" n={1} title={R.abstract.title}>
                {R.abstract.text.map((t) => <P key={t.slice(0, 24)}>{t}</P>)}
              </Sec>

              <Sec id="why" n={2} title={R.why.title}>
                {R.why.text.map((t) => <P key={t.slice(0, 24)}>{t}</P>)}
              </Sec>

              <Sec id="models" n={3} title={R.models.title}>
                {R.models.text.map((t) => <P key={t.slice(0, 24)}>{t}</P>)}
                <ModelsTable />
              </Sec>

              <Sec id="benchmarks" n={4} title={R.data.title}>
                {R.data.text.map((t) => <P key={t.slice(0, 24)}>{t}</P>)}
                <div data-testid="research-datacards">
                  <Reveal y={10}><p className="r-cap mb-4"><b>Table 2.</b> {R.data.caption}</p></Reveal>
                  <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" amount={0.1}>
                    {textCards.map(({ key, ...c }) => <DataCard key={key} {...c} labels={{ ...labels, kind: R.data.textLabel }} />)}
                  </Stagger>
                  <Stagger className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" amount={0.1}>
                    {imageCards.map(({ key, ...c }) => <DataCard key={key} {...c} labels={{ ...labels, kind: R.data.imageLabel }} />)}
                  </Stagger>
                </div>
              </Sec>

              <Sec id="protocol" n={5} title={R.protocol.title}>
                <Reveal y={10}><Items items={R.protocol.items} /></Reveal>
              </Sec>

              <Sec id="text" n={6} title={R.text.title}>
                <Sub n="6.1" title={R.text.cot.title}><P>{R.text.cot.text}</P><TextCotTable /></Sub>
                <Sub n="6.2" title={R.text.direct.title}><P>{R.text.direct.text}</P><TextDirectTable /></Sub>
                <Sub n="6.3" title={R.text.published.title}><P>{R.text.published.text}</P><TextPublishedTable /></Sub>
                <Sub n="6.4" title={R.text.q4.title}><P>{R.text.q4.text}</P><Q4Table /></Sub>
              </Sec>

              <Sec id="image" n={7} title={R.image.title}>
                <Sub n="7.1" title={R.image.all.title}><P>{R.image.all.text}</P><ImageAllTable /></Sub>
                <Sub n="7.2" title={R.image.split.title}><P>{R.image.split.text}</P><ImageSplitTable /></Sub>
                <Sub n="7.3" title={R.image.omni.title}><P>{R.image.omni.text}</P><OmniTable /></Sub>
                <Sub n="7.4" title={R.image.published.title}><P>{R.image.published.text}</P><ImagePublishedTable /></Sub>
              </Sec>

              <Sec id="throughput" n={8} title={R.throughput.title}>
                <P>{R.throughput.text}</P>
                <ThroughputTable />
              </Sec>

              <Sec id="grounded" n={9} title={R.grounded.title}>
                <P>{R.grounded.intro}</P>
                <Sub n="9.1" title={R.grounded.bakeoff.title}><P>{R.grounded.bakeoff.text}</P><BakeoffTable /></Sub>
                <Sub n="9.2" title={R.grounded.answerability.title}><P>{R.grounded.answerability.text}</P><AnswerabilityTable /></Sub>
                <Sub n="9.3" title={R.grounded.tcga.title}><P>{R.grounded.tcga.text}</P><TcgaTable /></Sub>
                <Sub n="9.4" title={R.grounded.status.title}><P>{R.grounded.status.text}</P><StatusTable /></Sub>
                <Sub n="9.5" title={R.grounded.summary.title}><P>{R.grounded.summary.text}</P></Sub>
                <Sub n="9.6" title={R.grounded.ocr.title}>{R.grounded.ocr.text.map((t) => <P key={t.slice(0, 24)}>{t}</P>)}<OcrTables /></Sub>
                <Sub n="9.7" title={R.grounded.speed.title}><P>{R.grounded.speed.text}</P></Sub>
              </Sec>

              <Sec id="findings" n={10} title={R.findings.title}>
                <Reveal y={10}><Items items={R.findings.items} as="ul" /></Reveal>
              </Sec>

              <Sec id="caveats" n={11} title={R.caveats.title}>
                <Reveal y={10}><Items items={R.caveats.items} as="ul" /></Reveal>
              </Sec>

              <Sec id="uses" n={12} title={R.uses.title}>
                {R.uses.text.map((t) => <P key={t.slice(0, 24)}>{t}</P>)}
              </Sec>

              <Sec id="sources" n={13} title={R.sources.title}>
                <P className="r-note">{R.sources.note}</P>
                <Reveal y={10}>
                  <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {R.sources.items.map((s) => (
                      <li key={s.href}><a href={s.href} target="_blank" rel="noreferrer" className="l-source text-[14px]">{s.label} <ExternalLink className="size-3.5" aria-hidden /></a></li>
                    ))}
                  </ul>
                </Reveal>
              </Sec>
            </article>
          </div>
        </div>
      </section>
      <Cta />
    </SiteFrame>
  );
}
