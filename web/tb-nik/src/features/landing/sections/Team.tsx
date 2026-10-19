// Our team: six portraits, the name on each. A photograph when there is one; the brand field with the mark until then.
import { UserRound } from "lucide-react";
import { TEAM, type Member } from "../content";
import { Stagger } from "../components/Reveal";
import { Tilt } from "../components/Tilt";

function Portrait({ m }: { m: Member }) {
  return (
    <Tilt max={5} className="l-portrait">
      {m.photo ? <img src={m.photo} alt={m.name} loading="lazy" /> : <span className="ph" aria-hidden><UserRound className="size-14 opacity-80" strokeWidth={1.4} /></span>}
      <span className="name">{m.name}</span>
    </Tilt>
  );
}

export function Team() {
  return (
    <section id="team" className="l-section py-16 sm:py-24">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <Stagger className="grid grid-cols-2 gap-4 sm:gap-6 md:grid-cols-3" itemClassName="h-full">
          {TEAM.members.map((m, i) => <Portrait key={i} m={m} />)}
        </Stagger>
      </div>
    </section>
  );
}
