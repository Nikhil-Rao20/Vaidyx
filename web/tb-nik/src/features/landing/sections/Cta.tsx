// The close: one invitation, two ways in.
import { Link } from "react-router-dom";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { useSession } from "@/lib/session";
import { CTA, HERO } from "../content";
import { Reveal, Words } from "../components/Reveal";
import { Magnetic } from "../components/Magnetic";

export function Cta() {
  const { me } = useSession();
  return (
    <section className="l-ink on-ink relative overflow-hidden py-28 sm:py-36">
      <span className="l-orb l-orb-teal" style={{ width: 900, height: 900, left: "50%", top: "50%", transform: "translate(-50%,-50%)", opacity: 0.4 }} aria-hidden />
      <span className="l-grid-lines" aria-hidden />
      <span className="l-grain" aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 text-center sm:px-8">
        <h2 className="l-display mx-auto max-w-4xl text-[clamp(2.4rem,6vw,5rem)] text-white">
          <Words text={CTA.title[0]} inView /> <span className="l-serif block" style={{ color: "var(--mint)", fontSize: "1.08em" }}><Words text={CTA.title[1]} inView start={0.25} /></span>
        </h2>
        <Reveal delay={0.2} y={14}><p className="l-lead l-muted mx-auto mt-7 max-w-xl">{CTA.text}</p></Reveal>
        <Reveal delay={0.3} y={14} className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Magnetic><Link to={me ? "/cases" : "/sign-in"} className="l-btn l-btn-primary">{me ? HERO.open : CTA.signIn} <ArrowRight className="size-4" aria-hidden /></Link></Magnetic>
          <Magnetic><a href={CTA.writeHref} target="_blank" rel="noreferrer" className="l-btn l-btn-ghost">{CTA.write} <ArrowUpRight className="size-4" aria-hidden /></a></Magnetic>
        </Reveal>
      </div>
    </section>
  );
}
