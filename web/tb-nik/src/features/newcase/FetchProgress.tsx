// After Create: the first fetch runs as a job (GET /jobs/{id}, polled). Live steps: the Case File made, the reports
// fetched from the hospital system, each report read (queued, reading, classifying, extracting, ready), what the board
// needs checked. The bar starts at 20 percent (owner's UX note 5). When it finishes the Case File opens by itself after a
// short countdown that can be stopped; it can be opened at any moment (it fills in live there too).
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Check, CircleAlert, CircleDashed, FileSearch, FolderCheck, KeyRound, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { CopyButton } from "@/components/CopyButton";
import { useJob } from "@/hooks/useQueries";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface FollowUp {
  id: string;
  label: string;
  state: "pending" | "done" | "failed";
  detail?: string;
}

type StepState = "done" | "active" | "waiting" | "failed";

function StepRow({ state, title, detail }: { state: StepState; title: string; detail?: string }) {
  const icon = state === "done" ? <Check className="size-4" aria-hidden /> : state === "active" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : state === "failed" ? <CircleAlert className="size-4" aria-hidden /> : <CircleDashed className="size-4" aria-hidden />;
  const tone = state === "done" ? "status-ok" : state === "active" ? "bg-secondary text-secondary-foreground" : state === "failed" ? "status-bad" : "bg-muted text-muted-foreground";
  return (
    <motion.li layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} className="flex items-start gap-3">
      <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full", tone)}>{icon}</span>
      <span className="min-w-0">
        <span className={cn("block text-sm", state === "waiting" ? "text-muted-foreground" : "font-medium text-foreground")}>{title}</span>
        {detail ? <span className="block text-xs text-muted-foreground">{detail}</span> : null}
      </span>
    </motion.li>
  );
}

const READING = new Set(["queued", "reading", "classifying", "extracting"]);
const STATE_WORDS: Record<string, string> = { queued: "waiting", reading: "reading", classifying: "sorting", extracting: "finding values", ready: "read", error: "could not be read" };

export function FetchProgress({ caseId, jobId, total, patientLine, followUps, joinCode }: {
  caseId: string;
  jobId: string | null;
  total: number;
  patientLine: string;
  followUps: FollowUp[];
  joinCode?: string | null;
}) {
  const navigate = useNavigate();
  const job = useJob(jobId);
  const j = job.data;
  const count = j?.total ?? total;
  const done = j?.done ?? 0;
  const finished = j?.state === "finished" || (count === 0 && Boolean(j || !jobId));
  const failed = j?.state === "failed";
  const states = useMemo(() => {
    const out: Record<string, number> = {};
    for (const s of Object.values(j?.doc_states ?? {})) out[s] = (out[s] ?? 0) + 1;
    return out;
  }, [j]);
  const reading = Object.entries(states).filter(([k]) => READING.has(k)).reduce((n, [, v]) => n + v, 0);
  const errors = states.error ?? 0;
  const pct = finished ? 100 : count ? 20 + Math.round((done / count) * 75) : 20;
  const to = `/cases/${encodeURIComponent(caseId)}`;

  // Auto-open after the job finishes, with a visible countdown the doctor can stop.
  const [countdown, setCountdown] = useState<number | null>(null);
  useEffect(() => { if (finished && countdown === null) setCountdown(4); }, [finished]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (countdown === null || countdown < 0) return;
    if (countdown === 0) { navigate(to, { replace: true }); return; }
    const t = window.setTimeout(() => setCountdown((c) => (c === null || c < 0 ? c : c - 1)), 1000);
    return () => window.clearTimeout(t);
  }, [countdown, navigate, to]);

  const readTitle = count ? `Reading the reports: ${done} of ${count}` : "No reports in the window to read";
  const readDetail = count
    ? [reading ? `${reading} in progress` : "", errors ? `${errors} could not be read (shown on the Case File)` : "", Object.entries(states).filter(([k]) => READING.has(k)).map(([k, v]) => `${v} ${STATE_WORDS[k] ?? k}`).join(", ")].filter(Boolean).join("; ")
    : "Older reports can be fetched from the Case File.";
  const gate = j?.gate;

  return (
    <div className="grid gap-5" aria-live="polite">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">New Case File</p>
        <h2 className="mt-1 text-lg">{patientLine}</h2>
        <Progress value={pct} className="mt-3 h-2" aria-label={`Fetch ${pct} percent done`} />
        <p className="mt-1 text-xs text-muted-foreground tabular-nums">{finished ? "Done" : failed ? "Stopped" : `${pct} percent`}</p>
      </div>
      <ol className="grid gap-3">
        <StepRow state="done" title="Registration found in the hospital system" />
        <StepRow state="done" title="Case File created" detail={caseId} />
        <StepRow state="done" title={`${plural(count, "report")} fetched from the hospital system`} />
        <StepRow
          state={failed ? "failed" : finished ? "done" : job.error && !j ? "failed" : "active"}
          title={failed ? "Reading stopped" : readTitle}
          detail={failed ? (j?.error || "The server stopped the reading. The reports already read are on the Case File.") : job.error && !j ? "The progress could not be read; the work goes on. Open the Case File to see it." : readDetail}
        />
        <StepRow
          state={finished ? "done" : failed ? "failed" : "waiting"}
          title="Checking what the board needs"
          detail={finished && gate && typeof gate.total === "number" ? `${gate.satisfied ?? 0} of ${gate.total} required records found` : finished ? "Open the Case File to see what is missing." : undefined}
        />
        {followUps.map((f) => (
          <StepRow key={f.id} state={f.state === "done" ? "done" : f.state === "failed" ? "failed" : "active"} title={f.label} detail={f.detail} />
        ))}
      </ol>

      {joinCode ? (
        <div className="surface-inner flex flex-wrap items-center gap-3 p-4">
          <KeyRound className="size-5 text-primary" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Join code for your residents</p>
            <p className="text-xs text-muted-foreground">They type it in the search bar: Join a Case File with a code.</p>
          </div>
          <span className="mono rounded-md bg-muted px-3 py-1 text-lg font-bold tracking-[0.3em]">{joinCode}</span>
          <CopyButton text={joinCode} label="Copy the code" />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" asChild className="hover:bg-primary-hover active:scale-[0.97]">
          <Link to={to} replace>
            {finished ? <FolderCheck className="size-4" aria-hidden /> : <FileSearch className="size-4" aria-hidden />}
            {finished ? "Open the Case File" : "Open it now (it fills in live)"}
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        </Button>
        <AnimatePresence>
          {countdown !== null && countdown > 0 ? (
            <motion.span key="cd" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
              Opening in {countdown} s
              <Button type="button" variant="ghost" size="sm" onClick={() => setCountdown(-1)}><X className="size-4" aria-hidden /> Stay here</Button>
            </motion.span>
          ) : null}
        </AnimatePresence>
        <Button type="button" variant="ghost" asChild><Link to="/home">Back to Home</Link></Button>
      </div>
    </div>
  );
}
