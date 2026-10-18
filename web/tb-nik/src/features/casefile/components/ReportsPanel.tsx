// Reports: a compact list grouped by OP visit and IP admission (newest first), or a dated timeline. Status chips,
// Open (page viewer in the side panel), Open images (hospital viewer in a new tab), Upload outside report, Re-fetch now.
import { useCallback, useMemo, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CalendarRange, ExternalLink, FileText, FolderOpen, Images, Loader2, RefreshCw, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { openImages, refetchHis, uploadDocuments } from "../api";
import { useJob } from "../hooks";
import type { CaseDocument, CaseFile, Job, RecordGroup, TimelineEvent } from "../types";
import type { SourceTarget } from "./SourceViewer";
import { docNeedsConfirmation, docStatusChip } from "./SourceViewer";
import { EmptyState, LoadingButton, StatusChip, errorText, fmtDate, fmtDateTime, plural, screenNote, useAnnounce } from "./common";
import { useOrg } from "@/hooks/useQueries";
import { cn } from "@/lib/utils";

function groupHeading(g: RecordGroup): string {
  const enc = g.kind === "OP" || g.kind === "IP";
  const when = enc && g.start ? fmtDate(g.start) + (g.kind === "IP" && g.end ? ` to ${fmtDate(g.end)}` : "") : "";
  return enc ? [g.label, g.department, g.unit, when].filter(Boolean).join(", ") : g.label;
}

function JobSteps({ job }: { job: Job | null }) {
  if (!job) return null;
  const running = job.state === "running";
  const last = job.events.slice(-4);
  return (
    <div className="rounded-md border border-border bg-muted/60 p-2 text-xs" role="status" aria-live="polite">
      <div className="flex items-center gap-2">
        {running ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
        <span className="font-medium text-foreground">{running ? `Reading ${job.done} of ${job.total}` : job.state === "failed" ? "The fetch did not finish" : `Done: ${job.done} of ${job.total} read`}</span>
      </div>
      {job.error ? <p className="text-bad mt-1">{job.error}</p> : null}
      <ol className="mt-1 space-y-0.5 text-muted-foreground">
        {last.map((e, i) => <li key={i}>{e.text ?? `${e.doc_id ?? ""} ${e.state ?? ""}`.trim()} <span className="opacity-70">({e.t}s)</span></li>)}
      </ol>
    </div>
  );
}

export function ReportsPanel({ caseId, cf, onOpenSource, onChanged, compact }: { caseId: string; cf: CaseFile; onOpenSource: (t: SourceTarget) => void; onChanged: () => Promise<void>; compact?: boolean }) {
  const [view, setView] = useState<"grouped" | "timeline">("grouped");
  const org = useOrg();
  // "radiology" from the server reads "Radiology" (the hospital's own department name when set up).
  const deptName = useMemo(() => {
    const names = new Map((org.data?.departments ?? []).map((d) => [d.id, d.name]));
    return (id: string) => names.get(id) ?? id.replace(/_/g, " ").replace(/\b\p{L}/gu, (m) => m.toUpperCase());
  }, [org.data]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [imgErr, setImgErr] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);
  const [announce, liveNode] = useAnnounce();
  const docs = cf.documents ?? [];
  const byId = useMemo(() => Object.fromEntries(docs.map((d) => [d.doc_id, d])), [docs]);
  // One row per report: an earlier version (a preliminary entry, the version an amendment replaced) folds under the version
  // that replaced it (18 Oct). The head of a chain is the version nothing supersedes.
  const earlierOf = useMemo(() => {
    const out: Record<string, CaseDocument[]> = {};
    const head = (d: CaseDocument): string => {
      let cur = d, hops = 0;
      while (cur.superseded?.by_doc && byId[cur.superseded.by_doc] && hops < 20) { cur = byId[cur.superseded.by_doc]; hops += 1; }
      return cur.doc_id;
    };
    for (const d of docs) if (d.superseded?.by_doc) (out[head(d)] ??= []).push(d);
    return out;
  }, [docs, byId]);
  const currentCount = docs.filter((d) => !d.superseded).length;
  const groups = useMemo<RecordGroup[]>(() => {
    const gs = cf.groups ?? [];
    const seen = new Set(gs.flatMap((g) => g.docs));
    const rest = docs.filter((d) => !seen.has(d.doc_id)).map((d) => d.doc_id);
    if (rest.length) return [...gs, { key: "rest", kind: "upload", label: gs.length ? "Other documents" : "Documents", docs: rest }];
    return gs;
  }, [cf.groups, docs]);

  const onJobDone = useCallback(async (j: Job) => { announce(j.state === "failed" ? "The fetch failed." : "Records updated."); await onChanged(); setJobId(null); }, [announce, onChanged]);
  const job = useJob(jobId, onJobDone);

  const refetch = useMutation({
    mutationFn: () => refetchHis(caseId),
    onSuccess: (r) => { setJobId(r.job); announce("Re-fetch started."); },
  });
  const images = useMutation({
    mutationFn: (docId: string) => openImages(caseId, docId),
    onSuccess: (r) => {
      setImgErr(null); setBlocked(null);
      if (!r.available || !r.viewer_url) { setImgErr(r.reason ?? "The images are not available in the image viewer."); return; }
      const w = window.open(r.viewer_url, "_blank", "noopener");
      if (!w) setBlocked(r.viewer_url);
      announce(`Image viewer opened${r.modality ? `: ${r.modality}` : ""}. Images are viewed by people; no model reads them.`);
    },
    onError: (e) => setImgErr(errorText(e)),
  });

  const canUpload = !!cf.permissions?.upload;
  const canRefetch = !!cf.permissions?.refetch;

  const DocRow = ({ d, earlier = [] }: { d: CaseDocument; earlier?: CaseDocument[] }) => {
    const c = d.classification ?? {};
    const needs = docNeedsConfirmation(d);
    const ids = [d.his?.encounter_number, d.his?.accession].filter(Boolean).join(" / ");
    const isPage = d.state === "ready";
    return (
      <li className="row-lift group rounded-md border border-transparent hover:border-border px-2 py-2 -mx-2" data-testid="doc-row">
        <div className="flex items-start gap-2">
          <FileText className="size-4 mt-0.5 text-muted-foreground shrink-0" aria-hidden />
          <div className="min-w-0 flex-1">
            <button type="button" className="text-left text-sm font-medium text-foreground hover:underline underline-offset-2 truncate max-w-full" onClick={() => onOpenSource({ docId: d.doc_id, page: 0, title: c.title ?? d.filename })} disabled={!isPage} title={isPage ? "Open the report in the side panel" : "Still being read"}>
              {c.title ?? d.filename}
            </button>
            <div className="text-xs text-muted-foreground flex flex-wrap gap-x-2">
              {c.event_date_iso ? <span>{fmtDate(c.event_date_iso)}</span> : null}
              {c.doc_type ? <span>{screenNote(String(c.doc_type).replace(/_/g, " "))}</span> : null}
              {ids ? <span className="mono">{ids}</span> : null}
              {d.department ? <span>{d.his ? "from" : "uploaded by"} {deptName(d.department)}</span> : null}
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {docStatusChip(d)}
              {needs ? <StatusChip kind="review">needs confirmation: {needs}</StatusChip> : null}
              {d.outside ? <StatusChip kind="muted">outside report</StatusChip> : null}
              {d.superseded ? <StatusChip kind="muted">earlier version</StatusChip> : null}
              {(d.page_flags ?? []).map((f) => <StatusChip key={f} kind="warn">{f}</StatusChip>)}
            </div>
            {earlier.length ? (
              <details className="mt-1 text-xs text-muted-foreground">
                <summary className="cursor-pointer hover:text-foreground">Earlier versions ({earlier.length})</summary>
                <ul className="mt-1 space-y-0.5 pl-3">
                  {earlier.map((e) => (
                    <li key={e.doc_id} className="flex items-center gap-2">
                      <span>{e.his?.version ? `Version ${e.his.version}` : "Earlier version"}{e.classification?.status ? `, ${String(e.classification.status).toLowerCase()}` : ""}</span>
                      <Button size="xs" variant="ghost" onClick={() => onOpenSource({ docId: e.doc_id, page: 0, title: (e.classification?.title ?? e.filename) + " (earlier version)" })} disabled={e.state !== "ready"}><FolderOpen className="size-3" />Open</Button>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>
          <div className="flex flex-col sm:flex-row gap-1 shrink-0 opacity-80 group-hover:opacity-100">
            <Button size="xs" variant="outline" onClick={() => onOpenSource({ docId: d.doc_id, page: 0, title: c.title ?? d.filename })} disabled={!isPage} aria-label={`Open ${c.title ?? d.filename}`}><FolderOpen className="size-3" />Open</Button>
            {d.his?.imaging_study_ref ? (
              <LoadingButton size="xs" variant="outline" loading={images.isPending && images.variables === d.doc_id} onClick={() => images.mutate(d.doc_id)} title="Opens the study in the hospital's image viewer in a new tab. Images are viewed by people; no model reads them." aria-label={`Open images for ${c.title ?? d.filename}`}><Images className="size-3" />Open images</LoadingButton>
            ) : null}
          </div>
        </div>
      </li>
    );
  };

  const timeline: TimelineEvent[] = useMemo(() => [...(cf.timeline ?? [])].sort((a, b) => String(b.date ?? "").localeCompare(String(a.date ?? ""))), [cf.timeline]);

  return (
    <section className={cn("surface", compact ? "p-3" : "p-4")} aria-labelledby="h-reports" data-testid="reports-panel">
      {liveNode}
      <header className="flex flex-wrap items-center gap-2 mb-2">
        <h2 id="h-reports" className="text-base">Reports</h2>
        <span className="text-xs text-muted-foreground">{plural(currentCount, "record")}</span>
        <span className="flex-1" />
        <div role="group" aria-label="View" className="inline-flex rounded-md border border-border p-0.5 bg-muted">
          <button type="button" aria-pressed={view === "grouped"} onClick={() => setView("grouped")} className={cn("px-2 py-0.5 text-xs rounded transition", view === "grouped" ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground")}>By visit</button>
          <button type="button" aria-pressed={view === "timeline"} onClick={() => setView("timeline")} className={cn("px-2 py-0.5 text-xs rounded transition inline-flex items-center gap-1", view === "timeline" ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground")}><CalendarRange className="size-3" aria-hidden />Timeline</button>
        </div>
      </header>
      <div className="flex flex-wrap gap-1.5 mb-3 print:hidden">
        {canUpload ? <Button size="sm" variant="outline" onClick={() => setUploadOpen(true)}><Upload className="size-4" />Upload outside report</Button> : null}
        {canRefetch ? <LoadingButton size="sm" variant="outline" loading={refetch.isPending || !!jobId} loadingText="Fetching" onClick={() => refetch.mutate()} title="Fetch new or changed records from the hospital system now"><RefreshCw className="size-4" />Re-fetch now</LoadingButton> : null}
        {cf.his?.fetched_at ? <span className="text-xs text-muted-foreground self-center">last fetch {fmtDateTime(cf.his.fetched_at)}</span> : null}
      </div>
      {refetch.isError ? <p role="alert" className="text-xs text-bad mb-2">{errorText(refetch.error)}</p> : null}
      {jobId ? <div className="mb-2"><JobSteps job={job} /></div> : null}
      {imgErr ? <p role="alert" className="text-xs text-bad mb-2">{imgErr}</p> : null}
      {blocked ? <p className="text-xs mb-2">The browser blocked the new tab. <a className="text-link underline" href={blocked} target="_blank" rel="noopener noreferrer">Open the image viewer <ExternalLink className="inline size-3" aria-hidden /></a></p> : null}

      {docs.length === 0 ? <EmptyState title="No records yet" text={cf.his ? "Nothing came from the hospital system for this window. Re-fetch, or upload an outside report." : "Upload the reports to start."} action={canUpload ? <Button size="sm" onClick={() => setUploadOpen(true)}><Upload className="size-4" />Upload</Button> : undefined} className="py-5" /> : null}

      {docs.length > 0 && view === "grouped" ? (
        <div className="space-y-3">
          {groups.map((g) => {
            const ds = g.docs.map((id) => byId[id]).filter((d): d is CaseDocument => Boolean(d) && !d.superseded);
            return (
              <div key={g.key} data-testid="record-group">
                <h3 className="text-sm font-semibold text-foreground flex flex-wrap items-center gap-1.5">
                  <span>{groupHeading(g)}</span>
                  {g.pre_admission ? <StatusChip kind="info">pre-admission OPD</StatusChip> : null}
                  <span className="text-xs font-normal text-muted-foreground">{plural(ds.length, "record")}</span>
                </h3>
                {g.consultant ? <p className="text-xs text-muted-foreground">Consultant: {g.consultant}</p> : null}
                {ds.length ? <ul className="mt-1 space-y-0.5">{ds.map((d) => <DocRow key={d.doc_id} d={d} earlier={earlierOf[d.doc_id]} />)}</ul> : <p className="text-xs text-muted-foreground mt-1">No record of this visit in the Case File.</p>}
              </div>
            );
          })}
        </div>
      ) : null}

      {docs.length > 0 && view === "timeline" ? (
        <ol className="relative border-l border-border-strong ml-2 space-y-2" data-testid="timeline">
          {timeline.length === 0 ? <li className="pl-4 text-sm text-muted-foreground">No dated events yet.</li> : null}
          {timeline.map((e, i) => {
            const d = e.doc_id ? byId[e.doc_id] : undefined;
            return (
              <li key={i} className="pl-4 relative">
                <span className={cn("absolute -left-[5px] top-1.5 size-2.5 rounded-full border-2 border-card", e.kind === "encounter" ? "bg-indigo" : e.kind === "document" ? "bg-primary" : e.kind === "action" ? "bg-warn" : e.kind === "board" ? "bg-ok" : "bg-muted-foreground")} aria-hidden />
                <div className="text-xs text-muted-foreground tabular-nums">{fmtDate(e.date)}{e.end ? ` to ${fmtDate(e.end)}` : ""}</div>
                {d ? (
                  <button type="button" className="text-sm text-foreground hover:underline underline-offset-2 text-left" onClick={() => onOpenSource({ docId: d.doc_id, page: 0, title: e.title })}>{e.title}</button>
                ) : <div className="text-sm text-foreground">{e.title}</div>}
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {d ? docStatusChip(d) : null}
                  {e.kind === "action" && e.status ? <StatusChip kind={e.status === "completed" ? "ok" : e.status === "overdue" ? "bad" : "warn"}>{e.status === "completed" ? "request closed" : e.status === "suggested" ? "request not sent" : `request ${e.status}`}</StatusChip> : null}
                  {e.kind === "referral" ? <StatusChip kind="info">referral</StatusChip> : null}
                </div>
              </li>
            );
          })}
        </ol>
      ) : null}

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} caseId={caseId} hisCase={!!cf.his} onStarted={(j) => { setJobId(j); announce("Upload started; reading the files."); }} />
    </section>
  );
}

function UploadDialog({ open, onOpenChange, caseId, hisCase, onStarted }: { open: boolean; onOpenChange: (o: boolean) => void; caseId: string; hisCase: boolean; onStarted: (job: string) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [outside, setOutside] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const up = useMutation({
    mutationFn: () => uploadDocuments(caseId, files, outside),
    onSuccess: (r) => { onStarted(r.job); setFiles([]); onOpenChange(false); },
    onError: (e) => setErr(errorText(e)),
  });
  const tooBig = files.find((f) => f.size > 60 * 1024 * 1024);
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!up.isPending) { onOpenChange(o); setErr(null); } }}>
      <DialogContent aria-describedby="upload-desc">
        <DialogHeader>
          <DialogTitle>Upload outside report</DialogTitle>
          <DialogDescription id="upload-desc">A report from another hospital or a private laboratory. PDF or an image, up to 60 MB each. It is read and checked against the patient's identity like every record.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div
            className={cn("rounded-md border-2 border-dashed border-border-strong p-4 text-center text-sm cursor-pointer hover:bg-muted transition", files.length && "border-primary")}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); setFiles(Array.from(e.dataTransfer.files)); }}
            role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputRef.current?.click(); } }}
            aria-label="Choose files"
          >
            <input ref={inputRef} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp" className="sr-only" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
            {files.length ? <ul className="text-left space-y-0.5">{files.map((f) => <li key={f.name} className="truncate">{f.name} <span className="text-muted-foreground">({Math.round(f.size / 1024)} KB)</span></li>)}</ul> : <span className="text-muted-foreground">Drop files here or click to choose</span>}
          </div>
          <div className="flex items-center gap-2">
            <Switch id="outside" checked={outside} onCheckedChange={setOutside} />
            <Label htmlFor="outside" className="text-sm">Outside report (another hospital or laboratory)</Label>
          </div>
          {hisCase && !outside ? <p className="text-xs text-muted-foreground">Into a hospital-system Case File every upload is normally an outside report.</p> : null}
          {tooBig ? <p role="alert" className="text-xs text-bad">{tooBig.name} is larger than 60 MB.</p> : null}
          {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={up.isPending}>Cancel</Button>
          <LoadingButton onClick={() => { setErr(null); up.mutate(); }} loading={up.isPending} loadingText="Uploading" disabled={!files.length || !!tooBig}><Upload className="size-4" />Upload {files.length ? plural(files.length, "file") : ""}</LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
