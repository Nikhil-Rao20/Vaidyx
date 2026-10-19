// The people behind Vaidyx: six cards; a photo when there is one, the initials in a brand ring until then.
import { UserRound } from "lucide-react";
import { TEAM, type Member } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Stagger } from "../components/Reveal";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("");
}

function Avatar({ m }: { m: Member }) {
  if (m.photo) return <img src={m.photo} alt="" className="size-[84px] rounded-full object-cover shadow-[0_0_0_4px_#fff,0_0_0_5px_rgba(1,203,211,0.35)]" loading="lazy" />;
  const placeholder = /^team member$/i.test(m.name);
  return <span className="l-avatar" aria-hidden>{placeholder ? <UserRound className="size-8 opacity-80" /> : initials(m.name)}</span>;
}

export function Team() {
  return (
    <section id="team" className="l-paper py-24 sm:py-32">
      <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={TEAM.eyebrow} title={[TEAM.title[0], TEAM.title[1]]} lead={TEAM.lead} />
        <Stagger className="mt-16 grid grid-cols-2 gap-4 sm:gap-5 md:grid-cols-3" itemClassName="h-full">
          {TEAM.members.map((m, i) => (
            <article key={i} className="l-card flex h-full flex-col items-center p-6 text-center sm:p-8">
              <Avatar m={m} />
              <p className="mt-5 text-[1.05rem] font-semibold tracking-[-0.01em]">{m.name}</p>
              <p className="l-muted mt-1 text-[14.5px]">{m.role}</p>
            </article>
          ))}
        </Stagger>
      </div>
    </section>
  );
}
