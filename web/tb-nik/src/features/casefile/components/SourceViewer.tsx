// The source page: a PNG render of one page of the report with the quote's boxes drawn over it. Pages are 0-based in the
// API and shown as "page 1 of N". When the server cannot say where the quote sits, the quote text is shown under the page.
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { docFileUrl, getQuoteBoxes, notBuiltYet } from "../api";
import type { CaseDocument } from "../types";
import { StatusChip, fmtDate } from "./common";
import { cn } from "@/lib/utils";

export interface SourceTarget {
  docId: string;
  page?: number;
  quote?: string;
  factId?: string;
  title?: string;
}

const IMAGE_EXT = ["png", "jpg", "jpeg", "webp", "gif"];

/** A highlight box as fractions of the page: quote_boxes.py sends [x0, y0, x1, y1]; an older draft sent {x, y, w, h}. */
function toRect(b: unknown): { x: number; y: number; w: number; h: number } | null {
  if (Array.isArray(b) && b.length >= 4 && b.every((n) => typeof n === "number")) {
    const [x0, y0, x1, y1] = b as number[];
    return { x: Math.max(0, x0), y: Math.max(0, y0), w: Math.max(0, x1 - x0), h: Math.max(0, y1 - y0) };
  }
  if (b && typeof b === "object" && "x" in b && "w" in b) {
    const r = b as { x: number; y: number; w: number; h: number };
    return r;
  }
  return null;
}

export function docStatusChip(d?: CaseDocument) {
  if (!d) return null;
  if (d.state === "error") return <StatusChip kind="bad">failed to read</StatusChip>;
  if (d.state !== "ready") return <StatusChip kind="info">{d.state}</StatusChip>;
  const c = d.classification ?? {};
  const st = String(c.status ?? "").toUpperCase();
  if (d.his?.signed || c.signed === "yes") {
    if (st === "PRELIMINARY") return <StatusChip kind="warn">preliminary, signed</StatusChip>;
    return <StatusChip kind="ok">final, signed</StatusChip>;
  }
  if (st === "PRELIMINARY") return <StatusChip kind="warn">preliminary</StatusChip>;
  if (c.signed === "no") return <StatusChip kind="warn">not signed</StatusChip>;
  if (st === "FINAL" || st === "AMENDED" || st === "CORRECTED") return <StatusChip kind="ok">{st.toLowerCase()}</StatusChip>;
  if (st === "UNSTATED" || !st) return <StatusChip kind="review">status not stated</StatusChip>;
  return <StatusChip kind="info">{st.toLowerCase()}</StatusChip>;
}

export function docNeedsConfirmation(d?: CaseDocument): string | null {
  if (!d || d.state !== "ready") return null;
  const c = d.classification ?? {};
  if (d.identity === "name_match" && !d.identity_confirmed_by) return "patient matched by name only";
  if (d.identity === "id_differs" || d.identity === "mismatch_or_missing") return "patient identifier does not match";
  if (c.doc_type_disagreement && !c.doc_type_confirmed_by) return "document type unclear";
  return null;
}

export function SourceViewer({ caseId, target, doc, onTargetChange }: { caseId: string; target: SourceTarget; doc?: CaseDocument; onTargetChange?: (t: SourceTarget) => void }) {
  const pages = doc?.pages ?? 1;
  const [page, setPage] = useState(target.page ?? 0);
  const [zoom, setZoom] = useState(1);
  const [imgState, setImgState] = useState<"loading" | "ok" | "error">("loading");
  useEffect(() => { setPage(target.page ?? 0); setImgState("loading"); }, [target.docId, target.page]);

  const wantBoxes = !!(target.factId || target.quote);
  const boxesQ = useQuery({
    queryKey: ["quote-boxes", caseId, target.docId, target.factId ?? "", target.quote ?? ""],
    queryFn: () => getQuoteBoxes(caseId, target.docId, target.factId ? { fact: target.factId } : { text: target.quote }),
    enabled: wantBoxes,
    retry: false,
  });
  useEffect(() => {
    if (boxesQ.data?.found && typeof boxesQ.data.page === "number" && boxesQ.data.page !== page) { setPage(boxesQ.data.page); setImgState("loading"); }
    // only when the boxes answer arrives
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boxesQ.data]);

  const isImage = IMAGE_EXT.includes(String(doc?.ext ?? "").replace(".", "").toLowerCase());
  const src = useMemo(() => (isImage ? docFileUrl(caseId, target.docId) : docFileUrl(caseId, target.docId, page)), [caseId, target.docId, page, isImage]);
  const boxes = boxesQ.data?.found && boxesQ.data.page === page ? (boxesQ.data.boxes ?? []).map(toRect).filter((r): r is NonNullable<ReturnType<typeof toRect>> => !!r) : [];
  const boxesUnavailable = wantBoxes && (boxesQ.isError || (boxesQ.data && !boxesQ.data.found));
  const pageOnly = wantBoxes && !!boxesQ.data?.found && boxesQ.data.page === page && boxes.length === 0;
  const go = (p: number) => { const np = Math.max(0, Math.min(pages - 1, p)); setPage(np); setImgState("loading"); onTargetChange?.({ ...target, page: np }); };

  return (
    <div className="flex flex-col gap-2" data-testid="source-viewer">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {docStatusChip(doc)}
        {doc?.classification?.event_date_iso ? <span>{fmtDate(doc.classification.event_date_iso)}</span> : null}
        {doc?.his?.accession ? <span className="mono">{doc.his.accession}</span> : null}
        <a className="ml-auto inline-flex items-center gap-1 text-link hover:underline" href={docFileUrl(caseId, target.docId)} target="_blank" rel="noopener noreferrer">Open original <ExternalLink className="size-3" aria-hidden /></a>
      </div>
      {target.quote ? (
        <blockquote className="rounded-md border-l-4 border-primary bg-secondary/60 px-3 py-2 text-sm text-foreground">
          <span className="font-mono text-xs text-muted-foreground block mb-0.5">Quote as printed</span>
          {target.quote}
        </blockquote>
      ) : null}
      <div className="flex items-center gap-1">
        <Button variant="outline" size="icon-sm" onClick={() => go(page - 1)} disabled={page <= 0} aria-label="Previous page"><ChevronLeft className="size-4" /></Button>
        <span className="text-sm tabular-nums px-1">page {page + 1} of {pages}</span>
        <Button variant="outline" size="icon-sm" onClick={() => go(page + 1)} disabled={page >= pages - 1} aria-label="Next page"><ChevronRight className="size-4" /></Button>
        <span className="flex-1" />
        <Button variant="ghost" size="icon-sm" onClick={() => setZoom((z) => Math.max(0.6, +(z - 0.2).toFixed(1)))} aria-label="Smaller" disabled={zoom <= 0.6}><ZoomOut className="size-4" /></Button>
        <Button variant="ghost" size="icon-sm" onClick={() => setZoom((z) => Math.min(2.2, +(z + 0.2).toFixed(1)))} aria-label="Larger" disabled={zoom >= 2.2}><ZoomIn className="size-4" /></Button>
      </div>
      <div className="relative overflow-auto rounded-md border border-border bg-muted max-h-[70dvh]">
        <div className="relative origin-top-left" style={{ width: `${zoom * 100}%` }}>
          {imgState === "loading" ? <div className="absolute inset-0 skeleton-line min-h-64" aria-hidden /> : null}
          {imgState === "error" ? (
            <div className="p-6 text-center text-sm">
              <p className="font-medium text-foreground">This page could not be shown.</p>
              <p className="text-muted-foreground">The file may still be fetching from the hospital system, or it is not a page-based document.</p>
              <a className="text-link underline" href={docFileUrl(caseId, target.docId)} target="_blank" rel="noopener noreferrer">Open the original file</a>
            </div>
          ) : (
            <img src={src} alt={`${doc?.classification?.title ?? "Report"}, page ${page + 1}`} className={cn("block w-full h-auto", imgState !== "ok" && "opacity-0")} onLoad={() => setImgState("ok")} onError={() => setImgState("error")} />
          )}
          {imgState === "ok" && boxes.map((b, i) => (
            <div key={i} className="absolute rounded-sm border-2 border-primary bg-primary/25 pointer-events-none animate-[pulse_1.2s_ease-in-out_2]" style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }} aria-hidden />
          ))}
        </div>
      </div>
      {pageOnly ? <p className="text-xs text-muted-foreground" data-testid="page-only">The quote is on this page (a typed report: the words are not boxed). It is shown above as printed.</p> : null}
      {boxesUnavailable ? <p className="text-xs text-muted-foreground">{boxesQ.isError && notBuiltYet(boxesQ.error) ? "Highlighting on the page is not available on this server yet; the quote is shown above." : "The exact place on the page could not be marked; the quote is shown above."}</p> : null}
      {wantBoxes && boxesQ.isFetching && !boxesQ.data ? <p className="text-xs text-muted-foreground">Finding the quote on the page</p> : null}
    </div>
  );
}
