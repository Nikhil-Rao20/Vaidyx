// A product of TANUH: the centre's mark on its own plate, what the centre is, and where to read more.
import { ArrowUpRight } from "lucide-react";
import { TANUH } from "../content";
import { Reveal, Words } from "../components/Reveal";

const LOGO = "/static/tb-nik/brand/tanuh.png";

export function Tanuh() {
  const Place = TANUH.place.icon;
  return (
    <section id="tanuh" className="l-paper-2 py-24 sm:py-32">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <Reveal>
          <div className="l-card grid items-center gap-10 p-7 sm:p-10 md:grid-cols-[auto_1fr] md:p-14">
            <div className="grid place-items-center">
              <div className="grid size-[180px] place-items-center rounded-3xl bg-white shadow-[0_1px_2px_rgba(11,25,48,0.05),0_20px_50px_-24px_rgba(11,25,48,0.35)] ring-1 ring-[rgba(11,25,48,0.08)] sm:size-[220px]">
                <img src={LOGO} alt="TANUH, The AI Centre of Excellence in Healthcare" className="h-[120px] w-auto sm:h-[150px]" loading="lazy" />
              </div>
            </div>
            <div>
              <span className="l-eyebrow text-[#0a6a86]">{TANUH.eyebrow}</span>
              <h2 className="l-title mt-4 text-[clamp(1.9rem,3.6vw,3rem)]">
                <Words text={TANUH.title[0]} inView /> <span className="l-serif" style={{ fontSize: "1.08em", color: "var(--blue)" }}><Words text={TANUH.title[1]} inView start={0.2} /></span>
              </h2>
              <p className="l-lead l-muted mt-5">{TANUH.text}</p>
              <p className="l-muted mt-4 flex items-center gap-2 text-[15px]"><Place className="size-4 text-[#0a6a86]" aria-hidden />{TANUH.place.text}</p>
              <div className="mt-7 flex flex-wrap gap-3">
                {TANUH.links.map((l) => (
                  <a key={l.href} href={l.href} target="_blank" rel="noreferrer" className="l-pill bg-white text-[15px] transition-colors hover:border-[rgba(11,25,48,0.3)]">
                    <span className="font-semibold">{l.label}</span><span className="l-muted hidden sm:inline">{l.text}</span><ArrowUpRight className="size-4 text-[#0a6a86]" aria-hidden />
                  </a>
                ))}
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
