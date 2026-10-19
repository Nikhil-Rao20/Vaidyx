// The design lab (/lab): the entrance in five ways, each on its own stage with a Replay button. Not linked from the top bar.
import { useRef, useState } from "react";
import { useInView } from "motion/react";
import { RotateCcw } from "lucide-react";
import { SiteFrame } from "../components/SiteFrame";
import { PageHead } from "../components/PageHead";
import { INTROS, type IntroOption } from "../intro/options";

function Stage({ o }: { o: IntroOption }) {
  const [run, setRun] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const seen = useInView(ref, { once: true, amount: 0.5 });
  const Scene = o.Component;
  return (
    <div className="mx-auto max-w-[1280px] px-5 pb-16 sm:px-8" data-testid={`lab-${o.key}`}>
      <div className="flex flex-wrap items-end justify-between gap-4 pt-14">
        <div>
          <p className="l-eyebrow">{o.name}{o.key === "A" ? " · on the site now" : ""}</p>
          <p className="l-muted mt-2 max-w-3xl text-[15px]">{o.why}</p>
        </div>
        <button type="button" className="l-btn l-btn-ghost !h-10 !px-4 text-[14px]" onClick={() => setRun((n) => n + 1)}><RotateCcw className="size-4" aria-hidden /> Replay</button>
      </div>
      <div ref={ref} className="l-card relative mt-6 grid aspect-[16/9] place-items-center overflow-hidden" style={{ background: "var(--l-bg)" }}>
        {seen ? <div key={run} className="landing-intro-stage absolute inset-0 grid place-items-center"><Scene /></div> : null}
      </div>
    </div>
  );
}

export default function LabPage() {
  return (
    <SiteFrame title="Vaidyx design lab" testId="lab">
      <PageHead eyebrow="Design lab" title={["The entrance,", "five ways."]} lead="The same lockup, large and on the plain field, arriving in five different ways. Each plays when it scrolls into view; Replay runs it again. Choose one." compact />
      {INTROS.map((o) => <Stage key={o.key} o={o} />)}
    </SiteFrame>
  );
}
