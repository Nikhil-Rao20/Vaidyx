// Built for everyone at the table: one card per role, each leaning towards the pointer.
import { Check } from "lucide-react";
import { ROLES } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Stagger } from "../components/Reveal";
import { Tilt } from "../components/Tilt";

export function Roles() {
  return (
    <section id="roles" className="l-paper py-24 sm:py-32">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={ROLES.eyebrow} title={[ROLES.title[0], ROLES.title[1]]} lead={ROLES.lead} />
        <Stagger className="mt-16 grid gap-5 md:grid-cols-2 lg:grid-cols-3" itemClassName="h-full">
          {ROLES.cards.map((c) => {
            const Icon = c.icon;
            return (
              <Tilt key={c.title} className="l-card flex h-full flex-col overflow-hidden p-7">
                <span className="grid size-11 place-items-center rounded-xl bg-[rgba(1,180,194,0.12)] text-[#0a6a86]"><Icon className="size-5" aria-hidden /></span>
                <h3 className="l-title mt-6 text-[1.35rem]">{c.title}</h3>
                <p className="l-muted mt-2.5">{c.text}</p>
                <ul className="mt-5 space-y-2 border-t border-[rgba(11,25,48,0.08)] pt-5 text-[15px]">
                  {c.points.map((p) => (
                    <li key={p} className="flex items-start gap-2.5"><Check className="mt-1 size-4 shrink-0 text-[#0a6a86]" strokeWidth={2.5} aria-hidden /><span>{p}</span></li>
                  ))}
                </ul>
              </Tilt>
            );
          })}
        </Stagger>
      </div>
    </section>
  );
}
