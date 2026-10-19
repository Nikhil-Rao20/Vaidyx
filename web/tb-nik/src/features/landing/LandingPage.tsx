// The public landing page at /tb-nik: who Vaidyx is for, what it does before, during and after the board, how it keeps every
// fact tied to its source, what it will never do, the team, and TANUH. Its own palette (landing.css), smooth scrolling, and
// the sections in order. Signed-in people see "Open Case Files" where visitors see "Sign in".
import { useEffect } from "react";
import "./landing.css";
import { SmoothScroll } from "./components/lenis";
import { Nav } from "./sections/Nav";
import { Hero } from "./sections/Hero";
import { Strip } from "./sections/Strip";
import { Problem } from "./sections/Problem";
import { HowItWorks } from "./sections/HowItWorks";
import { Sources } from "./sections/Sources";
import { Roles } from "./sections/Roles";
import { Safety } from "./sections/Safety";
import { Team } from "./sections/Team";
import { Tanuh } from "./sections/Tanuh";
import { Cta } from "./sections/Cta";
import { Footer } from "./sections/Footer";

export default function LandingPage() {
  useEffect(() => {
    const was = document.title;
    document.title = "Vaidyx Tumour Board: the Case File assistant for Indian hospitals";
    return () => { document.title = was; };
  }, []);
  return (
    <SmoothScroll>
      <div className="landing" data-testid="landing">
        <Nav />
        <main>
          <Hero />
          <Strip />
          <Problem />
          <HowItWorks />
          <Sources />
          <Roles />
          <Safety />
          <Team />
          <Tanuh />
          <Cta />
        </main>
        <Footer />
      </div>
    </SmoothScroll>
  );
}
