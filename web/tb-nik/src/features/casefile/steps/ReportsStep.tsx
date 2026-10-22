// Reports (B4): every report, grouped by type (Pathology, Imaging, Labs, Clinical notes, Other, Outside reports; newest first), with a
// switch to group them by visit. Each row: the title and date, "Checked by Vaidyx" (the machine's check: read, type found, final and
// signed found, patient matched, every value matched to its report line), or an amber "Please check" with the reason; the values read
// (one click lists them with their lines); "Preliminary, not signed yet" when it is not final; Open images for imaging.
import { useCallback, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, ChevronDown, ExternalLink, FileText, Images, Loader2, RefreshCw, ShieldQuestion, Upload, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { openImages, refetchHis } from "../api";
import { useJob } from "../hooks";
import type { CaseFile, Job } from "../types";
import type { SourceTarget } from "../components/SourceViewer";
import { JobSteps, UploadDialog } from "../components/ReportsPanel";
import { EmptyState, LoadingButton, errorText, fmtDate, fmtDateTime, niceTitle, plural, useAnnounce } from "../components/common";
import type { StepDocument, Steps } from "./types";

const GROUPS: Array<[string, string]> = [["pathology", "Pathology"], ["imaging", "Imaging"], ["labs", "Labs"], ["notes", "Clinical notes"], ["other", "Other reports"]];

function CheckTag({ d, onCheck }: { d: StepDocument; onCheck: () => void }) {
  const c = d.check;
  if (c.status === "checked") return <span className="inline-flex items-center gap-1 rounded-md status-ok px-1.5 py-0.5 text-xs font-medium" data-testid="checked-tag"><CheckCircle2 className="size-3.5" aria-hidden />Checked by Vaidyx</span>;
  if (c.status === "reading") return <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-1.5 py-0.5 text-xs font-medium text-secondary-foreground"><Loader2 className="size-3.5 animate-spin" aria-hidden />Being read</span>;
  if (c.status === "failed") return <span className="inline-flex items-center gap-1 rounded-md status-bad px-1.5 py-0.5 text-xs font-medium"><XCircle className="size-3.5" aria-hidden />{c.reasons[0] ?? "Could not be read"}</span>;
  if (c.status === "dismissed") return <span className="text-xs text-muted-foreground">{c.reasons[0]}</span>;
  return (
    <button type="button" onClick={onCheck} className="inline-flex items-center gap-1 rounded-md status-warn px-1.5 py-0.5 text-left text-xs font-semibold hover:brightness-95" data-testid="please-check">
      <ShieldQuestion className="size-3.5 shrink-0" aria-hidden />Please check: {c.reasons.join("; ")}
    </button>
  );
}

function DocRow({ d, onOpen, onCheck, onImages, imagesBusy }: { d: StepDocument; onOpen: (t: SourceTarget) => void; onCheck: () => void; onImages: () => void; imagesBusy: boolean }) {
  const [open, setOpen] = useState(false);
  const n = d.check.values.length;
  const title = niceTitle(d.title);
  return (
    <li className="py-3" data-testid="report-row" data-check={d.check.status}>
      <div className="flex flex-wrap items-start gap-3">
        <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <button type="button" className="text-left text-[0.95rem] font-medium text-foreground hover:underline underline-offset-2" onClick={() => onOpen({ docId: d.doc_id, page: 0, title: d.title })} disabled={d.check.status === "reading"}>{title}</button>
            {d.date ? <span className="text-sm text-muted-foreground tabular-nums">{fmtDate(d.date)}</span> : null}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <CheckTag d={d} onCheck={onCheck} />
            {d.outside ? <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">Outside report</span> : null}
            {d.final.warn && d.check.status !== "reading" ? <span className="rounded-md status-warn px-1.5 py-0.5 text-xs font-medium" data-testid="final-warn">{d.final.label}</span> : null}
            {n ? (
              <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-link hover:bg-accent" data-testid="values-read">
                {plural(n, "value")} read<ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
              </button>
            ) : null}
          </div>
          {open ? (
            <dl className="mt-1 divide-y divide-border rounded-md border border-border bg-muted/40 px-3" data-testid="values-list">
              {d.check.values.map((v) => (
                <div key={v.fact_id} className="grid gap-x-3 py-1.5 text-sm sm:grid-cols-[minmax(8rem,11rem)_1fr]">
                  <dt className="text-muted-foreground">{v.label}</dt>
                  <dd className="min-w-0">
                    <span className="text-foreground">{v.value}</span>
                    {v.quote ? <button type="button" className="ml-2 text-left text-xs text-link hover:underline" onClick={() => onOpen({ docId: d.doc_id, page: v.page ?? 0, quote: v.quote, factId: v.fact_id, title: d.title })}>"{v.quote}"</button> : null}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
          {d.earlier.length ? <p className="text-xs text-muted-foreground">{plural(d.earlier.length, "earlier version")}: {d.earlier.map((e) => e.status).join(", ")}</p> : null}
        </div>
        <div className="flex shrink-0 gap-1.5">
          <Button size="sm" variant="outline" onClick={() => onOpen({ docId: d.doc_id, page: 0, title: d.title })} disabled={d.check.status === "reading"}>Open</Button>
          {d.images ? <LoadingButton size="sm" variant="outline" loading={imagesBusy} onClick={onImages} title="Opens the study in the image viewer in a new tab. Images are viewed by people; no model reads them."><Images className="size-4" />Open images</LoadingButton> : null}
        </div>
      </div>
    </li>
  );
}

export function ReportsStep({ steps, cf, caseId, onOpen, onCheckDoc, onChanged, onNext }: {
  steps: Steps; cf: CaseFile; caseId: string; onOpen: (t: SourceTarget) => void; onCheckDoc: (docId: string) => void; onChanged: () => Promise<void>; onNext: () => void;
}) {
  const [by, setBy] = useState<"type" | "visit">("type");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [imgMsg, setImgMsg] = useState<{ err?: string; blocked?: string } | null>(null);
  const [announce, liveNode] = useAnnounce();
  const docs = steps.documents;
  const byId = useMemo(() => Object.fromEntries(docs.map((d) => [d.doc_id, d])), [docs]);
  const onJobDone = useCallback(async (j: Job) => { announce(j.state === "failed" ? "The fetch did not finish." : "Reports updated."); await onChanged(); setJobId(null); }, [announce, onChanged]);
  const job = useJob(jobId, onJobDone);
  const refetch = useMutation({ mutationFn: () => refetchHis(caseId), onSuccess: (r) => { setJobId(r.job); announce("Getting new reports from the hospital."); } });
  const images = useMutation({
    mutationFn: (docId: string) => openImages(caseId, docId),
    onSuccess: (r) => {
      if (!r.available || !r.viewer_url) { setImgMsg({ err: r.reason ?? "The images are not in the image viewer." }); return; }
      const w = window.open(r.viewer_url, "_blank");
      if (w) { w.opener = null; setImgMsg(null); } else setImgMsg({ blocked: r.viewer_url });
    },
    onError: (e) => setImgMsg({ err: errorText(e) }),
  });
  const groups = by === "type"
    ? GROUPS.map(([id, label]) => ({ key: id, label, docs: docs.filter((d) => d.group === id) })).filter((g) => g.docs.length)
    : (cf.groups ?? []).map((g) => ({ key: g.key, label: [g.label, g.department, g.start ? fmtDate(g.start) : ""].filter(Boolean).join(", "), docs: g.docs.map((id) => byId[id]).filter(Boolean) as StepDocument[] }))
      .concat([{ key: "rest", label: "Other documents", docs: docs.filter((d) => !(cf.groups ?? []).some((g) => g.docs.includes(d.doc_id))) }]).filter((g) => g.docs.length);
  const toCheck = docs.filter((d) => d.check.status === "please_check" || d.check.status === "failed").length;
  const row = (d: StepDocument) => <DocRow key={d.doc_id} d={d} onOpen={onOpen} onCheck={() => onCheckDoc(d.doc_id)} onImages={() => images.mutate(d.doc_id)} imagesBusy={images.isPending && images.variables === d.doc_id} />;
  return (
    <div className="space-y-4" data-testid="section-reports">
      {liveNode}
      <section className="surface">
        <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-[15px]">Reports <span className="font-normal text-muted-foreground">({docs.length})</span></h2>
            <p className="text-xs text-muted-foreground">{toCheck ? `${plural(toCheck, "report")} to check` : "Every report is checked by Vaidyx"}{cf.his?.fetched_at ? ` · last fetched from the hospital ${fmtDateTime(cf.his.fetched_at)}` : ""}</p>
          </div>
          <div role="group" aria-label="Group the reports" className="inline-flex rounded-md border border-border bg-muted p-0.5">
            {(["type", "visit"] as const).map((k) => (
              <button key={k} type="button" aria-pressed={by === k} onClick={() => setBy(k)} className={cn("rounded px-2.5 py-1 text-xs transition", by === k ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>By {k}</button>
            ))}
          </div>
        </header>
        <div className="flex flex-wrap gap-2 border-b border-border px-4 py-2.5">
          {cf.permissions?.refetch ? <LoadingButton size="sm" variant="outline" loading={refetch.isPending || !!jobId} loadingText="Getting new reports" onClick={() => refetch.mutate()}><RefreshCw className="size-4" />Get new reports from the hospital</LoadingButton> : null}
          {cf.permissions?.upload ? <Button size="sm" variant="outline" onClick={() => setUploadOpen(true)}><Upload className="size-4" />Upload outside report</Button> : null}
        </div>
        {refetch.isError ? <p role="alert" className="px-4 pt-2 text-xs text-bad">{errorText(refetch.error)}</p> : null}
        {jobId ? <div className="px-4 pt-2"><JobSteps job={job} /></div> : null}
        {imgMsg?.err ? <p role="alert" className="px-4 pt-2 text-xs text-bad">{imgMsg.err}</p> : null}
        {imgMsg?.blocked ? <p className="px-4 pt-2 text-xs">The browser blocked the new tab. <a className="text-link underline" href={imgMsg.blocked} target="_blank" rel="noopener noreferrer">Open the image viewer <ExternalLink className="inline size-3" aria-hidden /></a></p> : null}
        <div className="px-4 pb-2">
          {!docs.length ? <EmptyState title="No reports yet" text="Nothing came from the hospital system yet. Get new reports, or upload an outside report." className="py-6" /> : null}
          {groups.map((g) => (
            <div key={g.key} className="pt-3" data-testid="report-group">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{g.label} <span className="font-normal normal-case">({g.docs.length})</span></h3>
              <ul className="divide-y divide-border">{g.docs.map(row)}</ul>
            </div>
          ))}
        </div>
      </section>
      <div className="flex justify-end"><Button variant="outline" onClick={onNext}>Next: Check<ArrowRight className="size-4" /></Button></div>
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} caseId={caseId} hisCase={!!cf.his} onStarted={(j) => { setJobId(j); announce("Upload started; reading the files."); }} />
    </div>
  );
}
