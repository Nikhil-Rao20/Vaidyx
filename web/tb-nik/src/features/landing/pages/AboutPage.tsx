// About: purpose, approach and setting; the team; TANUH; the close.
import { SiteFrame } from "../components/SiteFrame";
import { PageHead } from "../components/PageHead";
import { Stagger } from "../components/Reveal";
import { ABOUT } from "../content";
import { Team } from "../sections/Team";
import { Tanuh } from "../sections/Tanuh";
import { Cta } from "../sections/Cta";

export default function AboutPage() {
  return (
    <SiteFrame title="About Vaidyx" testId="about">
      <PageHead eyebrow={ABOUT.eyebrow} title={[ABOUT.title[0], ABOUT.title[1]]} lead={ABOUT.lead} />
      <section className="l-paper py-20 sm:py-24">
        <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
          <Stagger className="grid gap-5 md:grid-cols-3" itemClassName="h-full">
            {ABOUT.mission.map((m, i) => (
              <article key={m.title} className="l-card flex h-full flex-col p-7 sm:p-8">
                <span className="l-eyebrow text-[#0a6a86]">0{i + 1}</span>
                <h2 className="l-title mt-4 text-[1.45rem]">{m.title}</h2>
                <p className="l-muted mt-3">{m.text}</p>
              </article>
            ))}
          </Stagger>
        </div>
      </section>
      <Team />
      <Tanuh />
      <Cta />
    </SiteFrame>
  );
}
