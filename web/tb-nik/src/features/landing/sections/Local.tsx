// Runs locally (12 Nov): the hospital boundary as a drawing in HTML, so it reads the same on a phone. Inside the dashed line:
// the hospital's systems, the Vaidyx server with its AI models, and the doctors' screens. One dashed line crosses it: the
// search words to PubMed. Then four points.
import { ArrowDown, ArrowRight, Building2, CloudOff, Images, Library, MicOff, MonitorPlay, ScrollText, Search, Server, ShieldCheck, type LucideIcon } from "lucide-react";
import { LOCAL } from "../content.pillars";
import { SectionHead } from "../components/SectionHead";
import { Reveal, Stagger } from "../components/Reveal";

const D = LOCAL.diagram;
const SYS_ICON: Record<string, LucideIcon> = { his: Building2, pacs: Images, casefile: ScrollText, meeting: MonitorPlay };
type Key = (typeof LOCAL.points)[number]["key"];
const POINT_ICON: Record<Key, LucideIcon> = { models: Server, records: ShieldCheck, voice: MicOff, words: Search };

function Node({ id, title, sub }: { id: string; title: string; sub: string }) {
  const I = SYS_ICON[id] ?? Building2;
  return (
    <div className="l-card flex items-center gap-3 !rounded-2xl px-4 py-3">
      <span className="l-icon !h-9 !w-9 shrink-0"><I className="size-[18px]" aria-hidden /></span>
      <span className="min-w-0"><span className="block text-[15px] font-semibold">{title}</span><span className="l-faint block text-[13px]">{sub}</span></span>
    </div>
  );
}

const Flow = ({ label }: { label: string }) => <div className="l-zone-flow" aria-hidden><span>{label}</span><ArrowRight className="hidden size-4 lg:block" /><ArrowDown className="size-4 lg:hidden" /></div>;

export function Local() {
  return (
    <section id="local" className="l-section relative overflow-hidden py-24 sm:py-32" data-testid="local">
      <span className="l-orb l-orb-teal" style={{ width: 640, height: 640, left: "-12%", top: "12%", opacity: 0.3 }} aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={LOCAL.eyebrow} title={[LOCAL.title[0], LOCAL.title[1]]} lead={LOCAL.lead} />
        <Reveal y={20} className="mt-16" testId="local-diagram">
          <div role="group" aria-label={D.label}>
            <div className="l-zone">
              <span className="l-zone-tag"><ShieldCheck className="size-3.5" aria-hidden />{D.inside}</span>
              <div className="grid items-center gap-3 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1.4fr)_auto_minmax(0,1fr)] lg:gap-4">
                <div className="space-y-2.5">
                  <p className="l-eyebrow !text-[0.7rem]">{D.systemsTitle}</p>
                  {D.systems.map((s) => <Node key={s.key} id={s.key} title={s.title} sub={s.sub} />)}
                </div>
                <Flow label={D.reads} />
                <div className="l-zone-server" data-testid="local-server">
                  <div className="flex items-center gap-3">
                    <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/15"><Server className="size-5" aria-hidden /></span>
                    <div><p className="text-[1.2rem] font-semibold tracking-[-0.02em]">{D.server.title}</p><p className="text-[13px] opacity-85">{D.server.sub}</p></div>
                  </div>
                  <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.12em] opacity-80">{D.server.modelsTitle}</p>
                  <ul className="mt-2 space-y-1.5">
                    {D.server.models.map((m) => (
                      <li key={m.name} className="l-zone-model">
                        <span className="w-[3.6rem] shrink-0 text-[10.5px] font-semibold uppercase tracking-[0.1em] opacity-75">{m.does}</span>
                        <span className="min-w-0 flex-1"><b className="font-semibold">{m.name}</b> <span className="opacity-85">({m.tag})</span></span>
                      </li>
                    ))}
                  </ul>
                </div>
                <Flow label={D.shows} />
                <div className="space-y-2.5">
                  <p className="l-eyebrow !text-[0.7rem]">{D.peopleTitle}</p>
                  {D.people.map((s) => <Node key={s.key} id={s.key} title={s.title} sub={s.sub} />)}
                </div>
              </div>
            </div>
            {/* the one line that crosses the boundary, from the server down to PubMed; beside it, what is not used */}
            <div className="grid gap-x-5 lg:grid-cols-3 lg:items-end">
              <p className="l-faint order-3 mt-4 text-center text-[11px] font-semibold uppercase tracking-[0.14em] lg:order-1 lg:mt-0 lg:pb-6 lg:text-right">{D.outsideTitle}</p>
              <div className="order-1 lg:order-2">
                <div className="l-zone-out" aria-hidden />
                <p className="mb-2 mt-2 text-center"><span className="l-chip l-chip-review !px-2.5 !py-1 !text-[12px]"><Search className="size-3" aria-hidden />{D.out}</span></p>
                <div className="l-card flex items-center gap-3 !rounded-2xl px-4 py-3" data-testid="local-pubmed">
                  <span className="grid size-9 shrink-0 place-items-center rounded-[0.75rem]" style={{ background: "var(--l-review-bg)", color: "var(--l-review)" }}><Library className="size-[18px]" aria-hidden /></span>
                  <span className="min-w-0"><span className="block text-[15px] font-semibold">{D.pubmed.title}</span><span className="l-faint block text-[13px]">{D.pubmed.sub}</span></span>
                </div>
              </div>
              <div className="order-2 mt-3 lg:order-3 lg:mt-0">
                <div className="l-card l-zone-off flex items-center gap-3 !rounded-2xl px-4 py-3" data-testid="local-cloud">
                  <span className="grid size-9 shrink-0 place-items-center rounded-[0.75rem] bg-[var(--l-surface-2)] text-[var(--l-fg-3)]"><CloudOff className="size-[18px]" aria-hidden /></span>
                  <span className="min-w-0"><span className="l-muted block text-[15px] font-semibold">{D.cloud.title}</span><span className="l-faint block text-[13px]">{D.cloud.sub}</span></span>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
        <Stagger className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4" itemClassName="h-full">
          {LOCAL.points.map((p) => {
            const I = POINT_ICON[p.key];
            return (
              <article key={p.key} className="l-tile flex h-full flex-col p-6" data-testid="local-point">
                <span className="l-icon"><I className="size-5" aria-hidden /></span>
                <h3 className="l-title mt-4 text-[1.2rem]">{p.title}</h3>
                <p className="l-muted mt-2 text-[15px]">{p.text}</p>
              </article>
            );
          })}
        </Stagger>
      </div>
    </section>
  );
}
