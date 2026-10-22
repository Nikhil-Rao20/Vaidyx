// The close: one invitation, two ways forward.
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useSession } from "@/lib/session";
import { CTA, SITE } from "../content";
import { Reveal, Words } from "../components/Reveal";
import { Magnetic } from "../components/Magnetic";

export function Cta() {
  const { me } = useSession();
  return (
    <section className="l-section-2 relative overflow-hidden py-28 sm:py-36">
      <span className="l-orb l-orb-teal" style={{ width: 900, height: 900, left: "50%", top: "50%", transform: "translate(-50%,-50%)", opacity: 0.5 }} aria-hidden />
      <span className="l-grid-lines" aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 text-center sm:px-8">
        <h2 className="l-display mx-auto max-w-4xl text-[clamp(2.4rem,6vw,5rem)]">
          <Words text={CTA.title[0]} inView /> <span className="l-serif block" style={{ fontSize: "1.08em" }}><Words text={CTA.title[1]} inView start={0.25} /></span>
        </h2>
        <Reveal delay={0.2} y={14}><p className="l-lead l-muted mx-auto mt-7 max-w-xl">{CTA.text}</p></Reveal>
        <Reveal delay={0.3} y={14} className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Magnetic><Link to={me ? "/cases" : "/sign-in"} className="l-btn l-btn-primary">{me ? SITE.open : CTA.signIn} <ArrowRight className="size-4" aria-hidden /></Link></Magnetic>
          <Magnetic><Link to={CTA.contactTo} className="l-btn l-btn-ghost">{CTA.contact} <ArrowRight className="size-4" aria-hidden /></Link></Magnetic>
        </Reveal>
      </div>
    </section>
  );
}
