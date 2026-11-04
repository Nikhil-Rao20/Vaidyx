// The live steps of a PubMed question, as a compact stepper: Writing the search words, Searching PubMed (N found), Fetching the
// records, Reading M abstracts, Checking every quote. The step the server is on spins and shows the server's own words under it;
// the bar starts at a fifth (it never sits at zero) and the seconds count up, so a 15 s wait never looks frozen.
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Check, Circle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { stepViews, type LiveJob } from "./api";
import { PubMedMark } from "./PubMedMark";

export function LiveSteps({ job, className }: { job: LiveJob; className?: string }) {
  const reduce = useReducedMotion();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const starting = job.status === "starting" || job.steps.length === 0;
  const views = stepViews(starting ? [{ step: "words", detail: "sending your question" }] : job.steps);
  const done = views.filter((v) => v.state === "done").length;
  const active = views.find((v) => v.state === "active");
  const pct = Math.min(96, 20 + (80 * (done + 0.5)) / views.length);
  const secs = Math.max(0, Math.round((now - job.startedAt) / 1000));
  return (
    <section className={cn("rounded-lg border border-pubmed-line bg-card p-3 shadow-[var(--shadow-inner)]", className)} aria-label="Asking PubMed" aria-busy="true" data-testid="pubmed-steps" data-step={active?.key ?? ""}>
      <div className="flex items-start gap-2">
        <PubMedMark size="sm" className="mt-0.5" />
        <p className="min-w-0 flex-1 text-sm font-medium text-foreground">{job.question}</p>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground" aria-hidden>{secs} s</span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-pubmed-soft" aria-hidden>
        <motion.div className="h-full rounded-full bg-pubmed" initial={false} animate={{ width: `${pct}%` }} transition={reduce ? { duration: 0 } : { duration: 0.5, ease: [0.22, 1, 0.36, 1] }} />
      </div>
      <ol className="mt-2.5 space-y-1.5">
        {views.map((v) => (
          <li key={v.key} className="flex items-start gap-2" data-state={v.state} data-testid="pubmed-step">
            <span className={cn("mt-0.5 grid size-4 shrink-0 place-items-center rounded-full",
              v.state === "done" ? "bg-ok-soft text-ok" : v.state === "active" ? "text-pubmed" : "text-border-strong")} aria-hidden>
              {v.state === "done" ? <Check className="size-3" strokeWidth={3} /> : v.state === "active" ? <Loader2 className="size-4 animate-spin" /> : <Circle className="size-3" />}
            </span>
            <span className="min-w-0 flex-1">
              <span className={cn("block text-sm leading-tight", v.state === "waiting" ? "text-muted-foreground" : "font-medium text-foreground")}>
                {v.label}{v.state === "done" ? <span className="sr-only">, done</span> : v.state === "active" ? <span className="sr-only">, working</span> : null}
              </span>
              {v.state === "active" && v.detail ? <span className="mt-0.5 block break-words text-xs text-muted-foreground" data-testid="pubmed-step-detail">{v.detail}</span> : null}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-2.5 text-[11px] text-muted-foreground">Papers come only from PubMed. This usually takes 10 to 20 seconds.</p>
      <span className="sr-only" aria-live="polite">{active ? active.label : ""}</span>
    </section>
  );
}
