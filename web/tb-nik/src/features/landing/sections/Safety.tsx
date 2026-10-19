// Clinical safety by design: six principles, each stated as what Vaidyx does.
import { SAFETY } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Stagger } from "../components/Reveal";
import { Tilt } from "../components/Tilt";

export function Safety() {
  return (
    <section id="safety" className="l-ink on-ink relative overflow-hidden py-24 sm:py-32" style={{ background: "linear-gradient(180deg, #050b18 0%, #071530 100%)" }}>
      <span className="l-orb l-orb-violet" style={{ width: 640, height: 640, left: "-10%", top: "10%", opacity: 0.3 }} aria-hidden />
      <span className="l-orb l-orb-teal" style={{ width: 760, height: 760, right: "-16%", bottom: "-20%", opacity: 0.3 }} aria-hidden />
      <span className="l-grid-lines" aria-hidden />
      <span className="l-grain" aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead onInk eyebrow={SAFETY.eyebrow} title={[SAFETY.title[0], SAFETY.title[1]]} lead={SAFETY.lead} />
        <Stagger className="mt-16 grid gap-4 md:grid-cols-2 lg:grid-cols-3" itemClassName="h-full">
          {SAFETY.principles.map((p, i) => {
            const Icon = p.icon;
            return (
              <Tilt key={p.title} className="l-card-ink l-principle flex h-full flex-col overflow-hidden p-7" max={4}>
                <span className="l-index" aria-hidden>0{i + 1}</span>
                <span className="grid size-11 place-items-center rounded-xl bg-[rgba(1,203,211,0.12)] text-[var(--mint)] ring-1 ring-white/10"><Icon className="size-5" aria-hidden /></span>
                <p className="mt-6 text-[1.15rem] font-semibold text-white">{p.title}</p>
                <p className="l-muted mt-2 text-[15px]">{p.text}</p>
              </Tilt>
            );
          })}
        </Stagger>
      </div>
    </section>
  );
}
