// The staging book, open at the cited page: every page of the chapter one under the other (scroll freely), the cited page scrolled into
// view with its line highlighted on the printed page itself. Zoom in and out. The page images come from the server (the book never
// leaves it); a licensed book is only on the internal instance.
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Minus, Plus, X } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ErrorState, SkeletonLines } from "../components/common";
import { bookPageUrl, getBook, type BookTarget } from "./api";

export function BookViewer({ target, onClose }: { target: BookTarget | null; onClose: () => void }) {
  const meta = useQuery({ queryKey: ["book", target?.book], queryFn: () => getBook(target!.book), enabled: !!target, staleTime: 3_600_000, retry: false });
  const [zoom, setZoom] = useState(1);
  const scroller = useRef<HTMLDivElement>(null);
  const cited = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!target || !meta.data) return;
    const t = window.setTimeout(() => cited.current?.scrollIntoView({ block: "start" }), 120);
    return () => window.clearTimeout(t);
  }, [target, meta.data]);
  useEffect(() => { if (target) setZoom(1); }, [target]);
  return (
    <Dialog open={!!target} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="flex h-[92dvh] w-[min(1100px,96vw)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none" aria-describedby="book-desc" data-testid="book-viewer">
        <header className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
          <BookOpen className="size-5 text-brand" aria-hidden />
          <div className="min-w-0 flex-1">
            <DialogTitle className="truncate text-base">{meta.data?.title ?? "Staging book"}</DialogTitle>
            <DialogDescription id="book-desc" className="text-xs">{target?.label ? `${target.label} · ` : ""}page {target?.page}, the line is highlighted on the printed page</DialogDescription>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon-sm" onClick={() => setZoom((z) => Math.max(0.6, +(z - 0.2).toFixed(1)))} aria-label="Smaller" disabled={zoom <= 0.6}><Minus className="size-4" /></Button>
            <span className="w-12 text-center text-xs tabular-nums text-muted-foreground">{Math.round(zoom * 100)} %</span>
            <Button variant="outline" size="icon-sm" onClick={() => setZoom((z) => Math.min(2.2, +(z + 0.2).toFixed(1)))} aria-label="Larger" disabled={zoom >= 2.2}><Plus className="size-4" /></Button>
            <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close"><X className="size-4" /></Button>
          </div>
        </header>
        <div ref={scroller} className="flex-1 overflow-auto bg-muted px-4 py-4 scroll-thin" data-testid="book-pages">
          {meta.isLoading ? <SkeletonLines n={10} /> : null}
          {meta.isError ? <ErrorState error={meta.error} compact title="This book is not on this server" /> : null}
          {meta.data ? (
            <div className="mx-auto space-y-4" style={{ width: `${Math.round(zoom * 820)}px`, maxWidth: zoom <= 1 ? "100%" : undefined }}>
              {meta.data.printed.map((p) => {
                const isCited = p === target?.page;
                return (
                  <div key={p} ref={isCited ? cited : undefined} className={cn("overflow-hidden rounded-md bg-white shadow-[var(--shadow-outer)]", isCited && "ring-2 ring-primary")} data-page={p}>
                    <img src={bookPageUrl(target!.book, p, isCited ? target?.find : undefined)} alt={`Page ${p}`} loading={isCited ? "eager" : "lazy"} decoding="async"
                      className="block h-auto w-full bg-white" style={{ aspectRatio: String(meta.data!.aspect ?? 0.77) }} />
                    <p className="border-t border-border bg-card px-3 py-1 text-right text-xs text-muted-foreground">page {p}{isCited ? " · cited" : ""}</p>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
