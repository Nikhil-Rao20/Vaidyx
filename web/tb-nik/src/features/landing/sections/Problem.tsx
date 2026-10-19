// Why: the day before the board, in three honest statements.
import { PROBLEM } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Stagger } from "../components/Reveal";

export function Problem() {
  return (
    <section id="why" className="l-paper py-24 sm:py-32">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={PROBLEM.eyebrow} title={[PROBLEM.title[0], PROBLEM.title[1]]} lead={PROBLEM.lead} />
        <Stagger className="mt-16 grid gap-5 md:grid-cols-3" itemClassName="h-full">
          {PROBLEM.points.map((p) => {
            const Icon = p.icon;
            return (
              <article key={p.title} className="l-card flex h-full flex-col p-7 sm:p-8">
                <span className="grid size-11 place-items-center rounded-xl bg-[rgba(1,180,194,0.12)] text-[#0a6a86]"><Icon className="size-5" aria-hidden /></span>
                <h3 className="l-title mt-6 text-[1.45rem]">{p.title}</h3>
                <p className="l-muted mt-3">{p.text}</p>
              </article>
            );
          })}
        </Stagger>
      </div>
    </section>
  );
}
