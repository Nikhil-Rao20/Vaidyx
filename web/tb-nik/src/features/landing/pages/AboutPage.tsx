// About: meet the team, then TANUH, then the close.
import { SiteFrame } from "../components/SiteFrame";
import { PageHead } from "../components/PageHead";
import { ABOUT } from "../content";
import { Team } from "../sections/Team";
import { Tanuh } from "../sections/Tanuh";
import { Cta } from "../sections/Cta";

export default function AboutPage() {
  return (
    <SiteFrame title="About Vaidyx" testId="about">
      <PageHead eyebrow={ABOUT.eyebrow} title={[ABOUT.title[0], ABOUT.title[1]]} lead={ABOUT.lead} compact />
      <Team />
      <Tanuh />
      <Cta />
    </SiteFrame>
  );
}
