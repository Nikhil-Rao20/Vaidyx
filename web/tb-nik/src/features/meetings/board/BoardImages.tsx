// The Board view's Images tab (meetings-v2 item 2.3, D3): the imaging reports of the Case File that have a study in the image viewer;
// opening one shows the hospital image viewer (OHIF, same origin through the app's PACS proxy) inside the Board view, as the meeting's
// shared screen showed it. The driver's open is posted: the server grants every admitted member the viewer on the study and puts its url
// in the follow state, which the followers render. A member looking around opens the study for themself (the Case File's own "Open
// images", which grants and audits that one login). Images are viewed by people; no model ever reads them.
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText, ImageOff, Images, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { openImages } from "@/features/casefile/api";
import { EmptyState, errorText, fmtDate, niceTitle } from "@/features/casefile/components/common";
import type { StepDocument } from "@/features/casefile/steps/types";
import { viewerSrc } from "../api";
import type { BoardMode, BoardNavigate, BoardPosition } from "./useFollow";

const NOTE = "Images are viewed by people; no model reads them.";

function ImageList({ docs, interactive, onNavigate }: { docs: StepDocument[]; interactive: boolean; onNavigate: BoardNavigate }) {
  if (!docs.length) return <EmptyState title="No images" text="No imaging report of this Case File has a study in the image viewer." className="py-8" />;
  return (
    <section className="surface overflow-hidden" aria-labelledby="bv-images" data-testid="board-image-list">
      <h2 id="bv-images" className="border-b border-border bg-muted/40 px-4 py-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Imaging reports with images <span className="font-normal normal-case">({docs.length})</span>
      </h2>
      <ul className="divide-y divide-border">
        {docs.map((d) => (
          <li key={d.doc_id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3" data-testid="board-image-row" data-doc={d.doc_id}>
            <Images className="size-5 shrink-0 text-muted-foreground" aria-hidden />
            <span className="min-w-[12rem] flex-1">
              <span className="block text-base font-medium text-foreground">{niceTitle(d.title)}</span>
              <span className="text-sm text-muted-foreground">{[d.date ? fmtDate(d.date) : "", d.accession].filter(Boolean).join(" · ")}</span>
              {d.final?.warn ? <span className="ml-2 rounded-md status-warn px-1.5 py-0.5 text-xs font-semibold">{d.final.label}</span> : null}
            </span>
            {interactive ? (
              <span className="flex flex-wrap gap-2">
                <Button onClick={() => onNavigate("images", d.doc_id)} data-testid="board-open-images"><Images className="size-4" />Show images</Button>
                <Button variant="outline" onClick={() => onNavigate("reports", d.doc_id, 0)}><FileText className="size-4" />Read the report</Button>
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="border-t border-border px-4 py-2 text-xs text-muted-foreground">{NOTE}</p>
    </section>
  );
}

/** The viewer url for this screen: from the follow state (driver and followers), or the member's own open while looking around. */
function useViewer(caseId: string, view: BoardPosition, mode: BoardMode) {
  const docId = view.doc_id ?? "";
  const own = useQuery({
    queryKey: ["board-images", caseId, docId],
    queryFn: () => openImages(caseId, docId),
    enabled: mode === "look" && !!docId,
    staleTime: 10 * 60_000,
    retry: false,
  });
  if (mode === "look") {
    const r = own.data;
    const url = r?.available && r.viewer_url && r.viewer_url.startsWith("/") ? r.viewer_url : null;
    return { src: url, loading: own.isLoading, problem: own.isError ? errorText(own.error) : r && !url ? r.reason || "The images are not in the image viewer." : null };
  }
  const o = view.opened && view.opened.kind === "images" && view.opened.doc_id === docId ? view.opened : null;
  return { src: viewerSrc(o), loading: !o, problem: o && !viewerSrc(o) ? "The image viewer could not be shown here." : null };
}

function ImageViewer({ caseId, view, mode, doc, interactive, onNavigate }: {
  caseId: string; view: BoardPosition; mode: BoardMode; doc?: StepDocument; interactive: boolean; onNavigate: BoardNavigate;
}) {
  const v = useViewer(caseId, view, mode);
  const title = niceTitle(doc?.title || view.opened?.title || "Images");
  return (
    <section className="flex flex-col gap-3 @3xl:h-full" aria-labelledby="bv-viewer-title" data-testid="board-image-viewer" data-doc={view.doc_id ?? ""}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {interactive ? <Button variant="outline" onClick={() => onNavigate("images")} data-testid="board-all-images"><ArrowLeft className="size-4" />All images</Button> : null}
        <h2 id="bv-viewer-title" className="min-w-0 flex-1 break-words text-xl font-semibold text-foreground">{title}</h2>
        {view.opened?.modality ? <span className="rounded-md bg-muted px-2 py-0.5 text-sm text-muted-foreground">{view.opened.modality}</span> : null}
        {interactive && view.doc_id ? <Button variant="outline" onClick={() => onNavigate("reports", view.doc_id, 0)}><FileText className="size-4" />Read the report</Button> : null}
      </div>
      {v.src ? (
        <iframe title={`Image viewer: ${title}`} src={v.src} className="block h-[62dvh] min-h-[360px] w-full rounded-lg border border-border bg-black @3xl:h-auto @3xl:min-h-[420px] @3xl:flex-1" allow="fullscreen" data-testid="board-image-frame" />
      ) : v.problem ? (
        <div className="grid min-h-64 place-items-center rounded-lg border border-border bg-muted p-6 text-center" role="alert">
          <p className="flex flex-col items-center gap-2 text-base text-muted-foreground"><ImageOff className="size-8" aria-hidden />{v.problem}</p>
        </div>
      ) : (
        <div className="grid min-h-64 place-items-center rounded-lg border border-border bg-muted p-6 text-center" aria-busy="true">
          <p className="flex items-center gap-2 text-base text-muted-foreground"><Loader2 className="size-5 animate-spin" aria-hidden />{mode === "follow" ? "Waiting for the images" : "Opening the images in the image viewer"}</p>
        </div>
      )}
      <p className="text-xs text-muted-foreground">{NOTE}</p>
    </section>
  );
}

export function BoardImages({ caseId, view, mode, docs, interactive, onNavigate }: {
  caseId: string; view: BoardPosition; mode: BoardMode; docs: StepDocument[]; interactive: boolean; onNavigate: BoardNavigate;
}) {
  const imaging = docs.filter((d) => d.images);
  if (view.doc_id) return <ImageViewer key={view.doc_id} caseId={caseId} view={view} mode={mode} doc={docs.find((d) => d.doc_id === view.doc_id)} interactive={interactive} onNavigate={onNavigate} />;
  return <ImageList docs={imaging} interactive={interactive} onNavigate={onNavigate} />;
}
