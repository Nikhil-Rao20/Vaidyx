// The product page at /tb-nik, the site's default: the intro (the Vaidyx reveal, every time the page is opened), then the hero
// and the sections in order. Signed-in people see "Open Case Files" where visitors see "Sign in".
import { useCallback, useState } from "react";
import { SiteFrame } from "./components/SiteFrame";
import { Intro } from "./components/Intro";
import { Hero } from "./sections/Hero";
import { Strip } from "./sections/Strip";
import { Problem } from "./sections/Problem";
import { HowItWorks } from "./sections/HowItWorks";
import { Sources } from "./sections/Sources";
import { Journey } from "./sections/Journey";
import { Safety } from "./sections/Safety";
import { Cta } from "./sections/Cta";

export default function LandingPage() {
  const [ready, setReady] = useState(false);
  const onDone = useCallback(() => setReady(true), []);
  return (
    <SiteFrame title="Vaidyx Tumour Board: every patient ready for the Tumour Board" ready={ready} testId="landing">
      <Intro onDone={onDone} />
      {ready ? <Hero /> : <div className="l-section min-h-[100svh]" aria-hidden />}
      <Strip />
      <Problem />
      <HowItWorks />
      <Sources />
      <Journey />
      <Safety />
      <Cta />
    </SiteFrame>
  );
}
