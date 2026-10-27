// The Case panel of the call (night-v3 5.1, research/04 section 6.9): the slides of the Case File on the floor as a list (the
// coordinator puts one on the room's screen; a member looks at it on their own and can follow the room again), then the records
// and images: Show and Images for whoever may open them on the shared screen (the coordinator, or the presenter of this Case File),
// a read-only list for everyone else; and a link to the Case File.
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Images, MonitorCheck, MonitorOff, MonitorUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getCase } from "@/features/casefile/api";
import { ApiError } from "@/lib/api";
import { docStatusChip } from "@/features/casefile/components/SourceViewer";
import { StatusChip, errorText, niceTitle } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { PanelSection, usePanelAction } from "../../components/People";
import { useCall } from "../context";

/** Who may open a record or the images on the shared screen: the coordinator, or the presenter of the Case File on the floor (the
 * chosen presenter, else the owner), as the server's rule (api/meetings.py _may_open). */
export function mayOpen(o: { canManage: boolean; me: string; presenter?: string | null; chosen?: string | null; owner?: string | null }): boolean {
  if (o.canManage) return true;
  if (!o.me) return false;
  if (o.presenter && o.presenter === o.me) return true;
  return o.chosen ? o.chosen === o.me : !!o.owner && o.owner === o.me;
}

/** The plain line for a member who may not open the Case File (the records list answers 403). */
export const RECORDS_FORBIDDEN = "The coordinator or the presenter opens the records of this Case File on the stage.";

/** True when the records could not be listed because this person may not open the Case File. */
export function recordsForbidden(e: unknown): boolean {
  return e instanceof ApiError ? e.status === 403 : (e as { status?: number } | null)?.status === 403;
}

export function CasePanel() {
  const ctx = useCall();
  const { cid, row, slides, opened, me, canManage } = ctx;
  const act = usePanelAction();
  const cf = useQuery({ queryKey: ["case", cid], queryFn: () => getCase(cid!), enabled: !!cid, retry: false, staleTime: 60_000 });
  const docs = (cf.data?.documents ?? []).filter((d) => d.state === "ready" && !d.superseded);
  const canOpen = ctx.variant !== "room" && mayOpen({ canManage, me, presenter: ctx.state.current?.presenter?.user, chosen: row?.presenter?.user, owner: cf.data?.case.team?.owner });
  const conduct = canManage && ctx.variant === "coordinator";
  const onSlide = !opened || opened.kind === "none";
  const current = conduct ? ctx.sharedSlide : ctx.shownSlide;
  const tap = ctx.phone ? "min-h-11" : "";
  const forbidden = cf.isError && recordsForbidden(cf.error);

  if (!cid) return <p className="text-sm text-muted-foreground">No case is on the screen yet.</p>;

  return (
    <div className="space-y-4">
      <PanelSection title="Slides" count={slides.length || undefined} id="cp-slides"
        right={!conduct && !ctx.following ? <Button size="xs" variant="outline" className={tap} onClick={() => ctx.setFollowing(true)}><MonitorCheck className="size-3" />Back to the room's screen</Button> : undefined}>
        {ctx.slidesStatus === "loading" ? <div className="skeleton-line h-7 w-64" /> : null}
        {ctx.slidesStatus === "error" ? <p className="text-xs text-warn">Slides are not available for this case: {errorText(ctx.slidesError)}</p> : null}
        {slides.length ? (
          <ol className="space-y-0.5" aria-label="Slides of this Case File">
            {slides.map((sl, i) => {
              const here = i === current && (conduct ? onSlide : true);
              const roomHere = i === ctx.sharedSlide;
              return (
                <li key={sl.id}>
                  <button type="button" aria-current={here ? "true" : undefined} disabled={!!act.pending || ctx.variant === "room"}
                    onClick={() => { if (conduct) void act.run(`slide:${i}`, () => ctx.actions.go(cid, i)); else ctx.showSlide(i); }}
                    className={cn("flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors disabled:opacity-60", tap, here ? "bg-secondary text-secondary-foreground" : "hover:bg-muted")}>
                    <span className="w-5 shrink-0 text-xs tabular-nums text-muted-foreground">{i + 1}.</span>
                    <span className="min-w-0 flex-1 truncate">{sl.title}</span>
                    {!conduct && roomHere ? <span className="shrink-0 text-[10px] text-muted-foreground">on the room's screen</span> : null}
                  </button>
                </li>
              );
            })}
          </ol>
        ) : ctx.slidesStatus === "ready" ? <p className="text-xs text-muted-foreground">No slides for this case.</p> : null}
      </PanelSection>

      <PanelSection title="Records and images" id="cp-records"
        right={canOpen ? (!onSlide ? <Button size="xs" variant="outline" className={tap} onClick={() => void act.run("open:none", () => ctx.actions.open("none"))} disabled={!!act.pending}><MonitorOff className="size-3" />Back to the slide</Button> : <StatusChip kind="muted">slide only</StatusChip>) : undefined}>
        <ul className="divide-y divide-border rounded-md border border-border" aria-label="Records of this Case File">
          {cf.isLoading ? <li className="p-2"><div className="skeleton-line h-4 w-3/4" /></li> : null}
          {forbidden ? <li className="p-2 text-xs text-muted-foreground" data-testid="records-forbidden">{RECORDS_FORBIDDEN}</li> : null}
          {cf.isError && !forbidden ? <li className="p-2 text-xs text-warn">The records could not be listed: {errorText(cf.error)}</li> : null}
          {!cf.isLoading && !cf.isError && docs.length === 0 ? <li className="p-2 text-xs text-muted-foreground">No records to open.</li> : null}
          {docs.map((d) => {
            const title = niceTitle(d.classification?.title ?? d.filename);
            const onScreen = opened?.doc_id === d.doc_id;
            return (
              <li key={d.doc_id} className={cn("flex items-center gap-2 px-2 py-1.5 text-xs", onScreen && "bg-secondary/60")}>
                <span className="min-w-0 flex-1 truncate">{title}</span>
                {docStatusChip(d)}
                {canOpen ? (
                  <>
                    <Button size="xs" variant={onScreen && opened?.kind === "record" ? "secondary" : "ghost"} className={tap} onClick={() => void act.run(`record:${d.doc_id}`, () => ctx.actions.open("record", d.doc_id))} disabled={!!act.pending} aria-label={`Show ${title} on the screen`}><MonitorUp className="size-3" />Show</Button>
                    {d.his?.imaging_study_ref ? <Button size="xs" variant={onScreen && opened?.kind === "images" ? "secondary" : "ghost"} className={tap} onClick={() => void act.run(`images:${d.doc_id}`, () => ctx.actions.open("images", d.doc_id))} disabled={!!act.pending} aria-label={`Show the images of ${title} on the screen`}><Images className="size-3" />Images</Button> : null}
                  </>
                ) : onScreen ? <StatusChip kind="info">on the screen</StatusChip> : null}
              </li>
            );
          })}
        </ul>
      </PanelSection>

      {act.error ? <p role="alert" className="text-xs text-bad">{act.error}</p> : null}
      {forbidden ? null : <Link to={`/cases/${cid}`} className={cn("inline-flex items-center gap-1 text-sm text-link underline", tap)} target="_blank" rel="noopener" title="Opens the Case File in a new tab">Open the Case File<ExternalLink className="size-3.5" aria-hidden /></Link>}
    </div>
  );
}
