// The Board view's Reports tab (meetings-v2 item 2.3, D3): every report grouped by type, as the Reports step lists them in read mode
// (title, date, the "not signed" or "preliminary" mark, an outside report, a report with images); a click opens the report INSIDE the
// Board view at its page with the quoted line highlighted, as the Case File's source viewer shows it, with page buttons. The page and
// the line are part of the follow state, so this viewer is controlled: the page comes from the view, a page button navigates, and the
// jump to the quote's page is navigated by the driver (posted) or by a member looking around (local), never by a follower.
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight, ExternalLink, FileText, Images, Loader2, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { docFileUrl, getQuoteBoxes, notBuiltYet } from "@/features/casefile/api";
import { docStatusChip } from "@/features/casefile/components/SourceViewer";
import { EmptyState, fmtDate, niceTitle } from "@/features/casefile/components/common";
import type { CaseDocument } from "@/features/casefile/types";
import type { StepDocument } from "@/features/casefile/steps/types";
import type { BoardNavigate, BoardPosition } from "./useFollow";

const GROUPS: Array<[string, string]> = [["pathology", "Pathology"], ["imaging", "Imaging"], ["labs", "Labs"], ["notes", "Clinical notes"], ["outside", "Outside reports"], ["other", "Other reports"]];
const KNOWN = new Set(GROUPS.map(([g]) => g));
const IMAGE_EXT = ["png", "jpg", "jpeg", "webp", "gif"];

/** The report groups in the Reports step's order; a group the list does not know joins "Other reports". */
export function groupReports(docs: StepDocument[]) {
  return GROUPS.map(([id, label]) => ({ id, label, docs: docs.filter((d) => (KNOWN.has(d.group) ? d.group : "other") === id) })).filter((g) => g.docs.length);
}

/** A highlight box as fractions of the page: [x0, y0, x1, y1] from quote_boxes.py, or {x, y, w, h} from an older draft. */
function toRect(b: unknown): { x: number; y: number; w: number; h: number } | null {
  if (Array.isArray(b) && b.length >= 4 && b.every((n) => typeof n === "number")) {
    const [x0, y0, x1, y1] = b as number[];
    return { x: Math.max(0, x0), y: Math.max(0, y0), w: Math.max(0, x1 - x0), h: Math.max(0, y1 - y0) };
  }
  if (b && typeof b === "object" && "x" in b && "w" in b) return b as { x: number; y: number; w: number; h: number };
  return null;
}

function Marks({ d }: { d: StepDocument }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {d.final?.warn && d.check.status !== "reading" ? <span className="rounded-md status-warn px-1.5 py-0.5 text-xs font-semibold" data-testid="board-final-warn">{d.final.label}</span> : null}
      {d.outside ? <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">Outside report</span> : null}
      {d.images ? <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground"><Images className="size-3.5" aria-hidden />Images</span> : null}
      {d.check.status === "reading" ? <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground"><Loader2 className="size-3.5 animate-spin" aria-hidden />Being read</span> : null}
      {d.check.status === "failed" ? <span className="rounded-md status-bad px-1.5 py-0.5 text-xs">{d.check.reasons[0] ?? "Could not be read"}</span> : null}
      {d.check.status === "please_check" ? <span className="rounded-md status-warn px-1.5 py-0.5 text-xs">Please check: {d.check.reasons.join("; ")}</span> : null}
      {d.check.status === "dismissed" ? <span className="text-xs text-muted-foreground">{d.check.reasons[0]}</span> : null}
    </span>
  );
}

function ReportList({ docs, interactive, onNavigate }: { docs: StepDocument[]; interactive: boolean; onNavigate: BoardNavigate }) {
  const groups = useMemo(() => groupReports(docs), [docs]);
  if (!docs.length) return <EmptyState title="No reports yet" text="Nothing came from the hospital system for this Case File." className="py-8" />;
  return (
    <div className="space-y-4" data-testid="board-report-list">
      {groups.map((g) => (
        <section key={g.id} className="surface overflow-hidden" aria-labelledby={`bv-rg-${g.id}`} data-testid="board-report-group">
          <h2 id={`bv-rg-${g.id}`} className="border-b border-border bg-muted/40 px-4 py-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            {g.label} <span className="font-normal normal-case">({g.docs.length})</span>
          </h2>
          <ul className="divide-y divide-border">
            {g.docs.map((d) => (
              <li key={d.doc_id}>
                <button type="button" disabled={!interactive || d.check.status === "reading"} onClick={() => onNavigate("reports", d.doc_id, 0)}
                  className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors enabled:hover:bg-accent/60 disabled:cursor-default"
                  data-testid="board-report-row" data-doc={d.doc_id}>
                  <FileText className="mt-1 size-5 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1 space-y-1">
                    <span className="flex flex-wrap items-baseline gap-x-3">
                      <span className="text-base font-medium text-foreground">{niceTitle(d.title)}</span>
                      {d.date ? <span className="text-sm tabular-nums text-muted-foreground">{fmtDate(d.date)}</span> : null}
                    </span>
                    <Marks d={d} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** One report at the page of the view, the quoted line boxed on the page. */
function ReportPage({ caseId, view, doc, sdoc, interactive, navigates, onNavigate }: {
  caseId: string; view: BoardPosition & { doc_id: string }; doc?: CaseDocument; sdoc?: StepDocument; interactive: boolean;
  /** This screen moves the view itself (the driver, or a member looking around): the jump to the quote's page is navigated here. */
  navigates: boolean; onNavigate: BoardNavigate;
}) {
  const docId = view.doc_id;
  const quote = view.quote || "";
  const pages = Math.max(1, doc?.pages ?? 1);
  const page = Math.min(Math.max(0, view.page ?? 0), pages - 1);
  const [zoom, setZoom] = useState(1);
  const [img, setImg] = useState<"loading" | "ok" | "error">("loading");
  const scroller = useRef<HTMLDivElement>(null);
  const isImage = IMAGE_EXT.includes(String(doc?.ext ?? "").replace(".", "").toLowerCase());
  const src = isImage ? docFileUrl(caseId, docId) : docFileUrl(caseId, docId, page);
  useEffect(() => { setImg("loading"); }, [src]);
  useEffect(() => { setZoom(1); }, [docId]);

  // the same query as the Case File's source viewer (["quote-boxes", case, doc, fact, text]): one answer for both
  const boxesQ = useQuery({
    queryKey: ["quote-boxes", caseId, docId, "", quote],
    queryFn: () => getQuoteBoxes(caseId, docId, { text: quote }),
    enabled: !!quote,
    retry: false,
    staleTime: 10 * 60_000,
  });
  // the line sits on another page than the one asked for: the driver (or a member looking around) moves there, once per report and line
  const jumped = useRef("");
  useEffect(() => {
    const b = boxesQ.data;
    const key = `${docId}|${quote}`;
    if (!b?.found || typeof b.page !== "number" || jumped.current === key) return;
    jumped.current = key;
    if (navigates && b.page !== page && b.page >= 0 && b.page < pages) onNavigate("reports", docId, b.page, quote);
    // only when the answer arrives
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boxesQ.data]);

  const boxes = boxesQ.data?.found && boxesQ.data.page === page ? (boxesQ.data.boxes ?? []).map(toRect).filter((r): r is NonNullable<ReturnType<typeof toRect>> => !!r) : [];
  const boxesUnavailable = !!quote && (boxesQ.isError || (boxesQ.data && !boxesQ.data.found));
  const pageOnly = !!quote && !!boxesQ.data?.found && boxesQ.data.page === page && boxes.length === 0;

  // the highlighted line in sight: the page scrolls to the first box once the picture is drawn
  const top = boxes.length ? Math.min(...boxes.map((b) => b.y)) : null;
  useEffect(() => {
    const el = scroller.current;
    if (img !== "ok" || top === null || !el) return;
    const inner = el.firstElementChild as HTMLElement | null;
    const h = inner?.offsetHeight ?? el.scrollHeight;
    el.scrollTo({ top: Math.max(0, top * h - el.clientHeight / 3) });
  }, [img, top, zoom]);

  const title = niceTitle(sdoc?.title || doc?.classification?.title || doc?.filename || "Report");
  const go = (p: number) => onNavigate("reports", docId, Math.max(0, Math.min(pages - 1, p)), quote);
  return (
    <section className="flex flex-col gap-3 @3xl:h-full" aria-labelledby="bv-report-title" data-testid="board-report-page" data-doc={docId} data-page={page}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted-foreground">
        <h2 id="bv-report-title" className="min-w-0 break-words text-xl font-semibold text-foreground">{title}</h2>
        {sdoc?.final ? (
          <span className={cn("rounded-md px-1.5 py-0.5 text-xs font-semibold", sdoc.final.warn ? "status-warn" : "status-ok")} data-testid={sdoc.final.warn ? "board-final-warn" : "board-final"}>{sdoc.final.label}</span>
        ) : docStatusChip(doc)}
        {sdoc?.date || doc?.classification?.event_date_iso ? <span className="tabular-nums">{fmtDate(sdoc?.date || doc?.classification?.event_date_iso)}</span> : null}
        {doc?.his?.accession ? <span className="mono">{doc.his.accession}</span> : null}
        {interactive ? <a className="ml-auto inline-flex items-center gap-1 text-link hover:underline" href={docFileUrl(caseId, docId)} target="_blank" rel="noopener noreferrer">Open original <ExternalLink className="size-3.5" aria-hidden /></a> : null}
      </div>
      {quote ? (
        <blockquote className="rounded-md border-l-4 border-primary bg-secondary/60 px-4 py-2 text-lg text-foreground" data-testid="board-quote">
          <span className="mb-0.5 block text-xs text-muted-foreground">Quote as printed</span>
          {quote}
        </blockquote>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {interactive ? <Button variant="outline" onClick={() => onNavigate("reports")} data-testid="board-all-reports"><ArrowLeft className="size-4" />All reports</Button> : null}
        {interactive ? <Button variant="outline" size="icon" onClick={() => go(page - 1)} disabled={page <= 0} aria-label="Previous page"><ChevronLeft className="size-5" /></Button> : null}
        <span className="px-1 text-base tabular-nums text-foreground" data-testid="board-page-of">Page {page + 1} of {pages}</span>
        {interactive ? <Button variant="outline" size="icon" onClick={() => go(page + 1)} disabled={page >= pages - 1} aria-label="Next page"><ChevronRight className="size-5" /></Button> : null}
        <span className="flex-1" />
        {interactive ? (
          <>
            <Button variant="ghost" size="icon" onClick={() => setZoom((z) => Math.max(0.6, +(z - 0.2).toFixed(1)))} aria-label="Smaller" title="Smaller (on this screen only)" disabled={zoom <= 0.6}><ZoomOut className="size-5" /></Button>
            <Button variant="ghost" size="icon" onClick={() => setZoom((z) => Math.min(2.2, +(z + 0.2).toFixed(1)))} aria-label="Larger" title="Larger (on this screen only)" disabled={zoom >= 2.2}><ZoomIn className="size-5" /></Button>
          </>
        ) : null}
      </div>
      <div ref={scroller} className="relative max-h-[75dvh] min-h-[320px] overflow-auto rounded-md border border-border bg-muted @3xl:max-h-none @3xl:min-h-[360px] @3xl:flex-1" tabIndex={0} role="region" aria-label={`${title}, page ${page + 1}`}>
        <div className={cn("relative origin-top-left", img !== "ok" && "min-h-64")} style={{ width: `${zoom * 100}%` }}>
          {img === "loading" ? <div className="absolute inset-0 min-h-64 skeleton-line" aria-hidden /> : null}
          {img === "error" ? (
            <div className="p-6 text-center">
              <p className="font-medium text-foreground">This page could not be shown.</p>
              <p className="text-sm text-muted-foreground">The file may still be fetching from the hospital system, or it is not a page-based document.</p>
            </div>
          ) : (
            <img src={src} alt={`${title}, page ${page + 1}`} className={cn("block h-auto w-full bg-white", img !== "ok" && "opacity-0")} onLoad={() => setImg("ok")} onError={() => setImg("error")} />
          )}
          {img === "ok" && boxes.map((b, i) => (
            <div key={i} className="pointer-events-none absolute rounded-sm border-2 border-primary bg-primary/25" style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }} aria-hidden data-testid="board-quote-box" />
          ))}
        </div>
      </div>
      {pageOnly ? <p className="text-sm text-muted-foreground">The quote is on this page (a typed report: the words are not boxed). It is shown above as printed.</p> : null}
      {boxesUnavailable ? <p className="text-sm text-muted-foreground">{boxesQ.isError && notBuiltYet(boxesQ.error) ? "Highlighting on the page is not available on this server yet; the quote is shown above." : "The exact place on the page could not be marked; the quote is shown above."}</p> : null}
      {quote && boxesQ.isFetching && !boxesQ.data ? <p className="text-sm text-muted-foreground">Finding the quote on the page</p> : null}
    </section>
  );
}

export function BoardReports({ caseId, view, docs, cfDocs, interactive, navigates, onNavigate }: {
  caseId: string; view: BoardPosition; docs: StepDocument[]; cfDocs?: CaseDocument[]; interactive: boolean; navigates: boolean; onNavigate: BoardNavigate;
}) {
  if (view.doc_id) {
    const id = view.doc_id;
    return <ReportPage key={id} caseId={caseId} view={{ ...view, doc_id: id }} doc={cfDocs?.find((d) => d.doc_id === id)} sdoc={docs.find((d) => d.doc_id === id)}
      interactive={interactive} navigates={navigates} onNavigate={onNavigate} />;
  }
  return <ReportList docs={docs} interactive={interactive} onNavigate={onNavigate} />;
}
