// The Board view (meetings-v2 items 2.3 and 2.4, owner decisions D2 to D4): the Case File on the floor, read-only, as the Tumour Board
// sees it on the projector (the coordinator's laptop is mirrored) and on every remote member's screen. Four tabs: Summary (the question
// for the board first), Reports (a report opens here at its page with the line highlighted), Images (the hospital image viewer) and
// Stage and values. No To do, no Pre-Authorization, no Ask panel, no editing. Built from the Case File's own pieces; every read goes
// through the Case File routes the meeting window opens to the admitted members.
// Modes: "drive" (the coordinator, or the presenter while presenting: every click moves the room), "follow" (renders exactly `view`;
// with `onLookAround` a click starts looking around, without it, the room screen, nothing is clickable) and "look" (a member clicking
// freely on this screen only, with "Back to the room"). The state itself lives in useFollow.
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { Eye, Loader2, MonitorUp, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { UrgencyTag } from "@/components/UrgencyTag";
import { drName } from "@/lib/format";
import type { BoardTab } from "@/lib/live";
import { cn } from "@/lib/utils";
import { ErrorState, SkeletonLines } from "@/features/casefile/components/common";
import type { SourceTarget } from "@/features/casefile/components/SourceViewer";
import type { CaseFile } from "@/features/casefile/types";
import type { Steps } from "@/features/casefile/steps/types";
import { BoardImages } from "./BoardImages";
import { BoardReports } from "./BoardReports";
import { BoardStage } from "./BoardStage";
import { BoardSummary } from "./BoardSummary";
import { useBoardData } from "./parts";
import type { BoardMode, BoardNavigate, BoardPosition } from "./useFollow";
import "./board.css";

export interface BoardViewProps {
  /** The Case File on the floor. */
  caseId: string;
  /** What to show (useFollow's `view`): the tab, and on Reports or Images the record with its page and line. */
  view: BoardPosition;
  mode: BoardMode;
  /** Every click: a tab, a report (with page and line) or the images. useFollow's `navigate`. */
  onNavigate: BoardNavigate;
  /** A follower's header: "Following <name>". */
  followingName?: string;
  /** A remote member may look around (absent on the room screen, which always follows). */
  onLookAround?: () => void;
  onBackToRoom?: () => void;
  /** The presenter's name (the meeting's current.presenter.name); the owner's consultant when absent. */
  presenter?: string | null;
  /** The driver's last post refused, in the server's words. */
  error?: string | null;
  /** The driver's click is on its way. */
  pending?: boolean;
  className?: string;
}

const TABS: Array<{ id: BoardTab; label: string }> = [
  { id: "summary", label: "Summary" },
  { id: "reports", label: "Reports" },
  { id: "images", label: "Images" },
  { id: "stage", label: "Stage and values" },
];

function CaseLine({ cf, steps, presenter }: { cf?: CaseFile; steps?: Steps; presenter?: string | null }) {
  const c = cf?.case;
  const p = c?.patient;
  if (!c || !p) return <SkeletonLines n={2} className="max-w-xl" />;
  const cancer = steps?.protocol_label || c.protocol_label || (c.protocol ? c.protocol.replace(/_/g, " ") : "Cancer not chosen yet");
  const setting = c.setting ? c.setting.replace(/_/g, " ") : "";
  const who = presenter || cf?.access?.owner_name || "";
  const urgency = c.urgency?.level ?? steps?.question?.urgency?.level ?? null;
  return (
    <div className="min-w-0 space-y-1" data-testid="board-case-line">
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <span className="break-words text-2xl font-semibold leading-tight text-foreground">{p.name || "Unnamed patient"}</span>
        {p.agesex ? <span className="text-lg text-muted-foreground">{p.agesex}</span> : null}
        {p.mrn ? <span className="text-sm text-muted-foreground">UHID <span className="id text-foreground">{p.mrn}</span></span> : null}
      </p>
      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-base">
        <span className="font-medium text-foreground">{cancer}{setting ? <span className="font-normal text-muted-foreground">, {setting}</span> : null}</span>
        {who ? <span className="text-muted-foreground">Presented by <span className="text-foreground">{drName(who)}</span></span> : null}
        <span className="inline-flex items-center gap-2 text-muted-foreground">Urgency<UrgencyTag level={urgency} /></span>
      </p>
    </div>
  );
}

function FollowBar({ mode, followingName, onLookAround, onBackToRoom, pending }: Pick<BoardViewProps, "mode" | "followingName" | "onLookAround" | "onBackToRoom" | "pending">) {
  let words: ReactNode;
  let action: ReactNode = null;
  if (mode === "drive") {
    words = <><MonitorUp className="size-5 shrink-0 text-brand" aria-hidden />You lead: everyone follows what you open.{pending ? <Loader2 className="size-4 animate-spin" aria-label="Sending" /> : null}</>;
  } else if (mode === "look") {
    words = <><Eye className="size-5 shrink-0" aria-hidden />You are looking around on your own. The room has not moved.</>;
    action = onBackToRoom ? <Button onClick={onBackToRoom} data-testid="board-back-to-room"><Users className="size-4" />Back to the room</Button> : null;
  } else {
    words = <><Users className="size-5 shrink-0 text-brand" aria-hidden />Following {followingName || "the room"}</>;
    action = onLookAround ? <Button variant="outline" onClick={onLookAround} data-testid="board-look-around"><Eye className="size-4" />Look around</Button> : null;
  }
  // beside the patient's line on a wide view (the tabs keep the whole width under it), under it on a narrow one
  return (
    <div className={cn("flex w-full min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-2 rounded-lg px-3 py-1.5 @3xl:w-auto @3xl:max-w-[24rem] @3xl:shrink-0", mode === "look" ? "status-info" : "bg-muted/60")} data-testid="board-follow" data-mode={mode}>
      <p role="status" className="flex min-w-[10rem] flex-1 items-center gap-2 text-sm font-medium text-foreground">{words}</p>
      {action}
    </div>
  );
}

export function BoardView({ caseId, view, mode, onNavigate, followingName, onLookAround, onBackToRoom, presenter, error, pending, className }: BoardViewProps) {
  const { steps, cf, staging } = useBoardData(caseId);
  // the room screen (follow without look around) takes no clicks; a follower's click starts looking around (useFollow)
  const interactive = mode !== "follow" || !!onLookAround;
  // the jump to a quote's page is made by the screen that moves the view: the driver posts it, a member looking around keeps it
  const navigates = mode !== "follow";
  const go: BoardNavigate = (tab, docId, page, quote) => { if (interactive) onNavigate(tab, docId, page, quote); };
  const open = (t: SourceTarget) => go("reports", t.docId, t.page ?? 0, t.quote);
  const tab = view.tab;
  const s = steps.data;
  const docs = s?.documents ?? [];
  const imaging = docs.filter((d) => d.images).length;

  // a new tab or record starts at its top (the body scrolls on a wide view, the whole view on a narrow one)
  const frame = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => { body.current?.scrollTo({ top: 0 }); frame.current?.scrollTo({ top: 0 }); }, [tab, view.doc_id]);

  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!interactive || (e.key !== "ArrowRight" && e.key !== "ArrowLeft" && e.key !== "Home" && e.key !== "End")) return;
    e.preventDefault();
    const i = TABS.findIndex((t) => t.id === tab);
    const n = e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : (i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length;
    go(TABS[n].id);
    tabRefs.current[n]?.focus();
  };

  let content: ReactNode;
  if (steps.isLoading) content = <div className="surface p-5"><SkeletonLines n={6} /></div>;
  else if (steps.isError || !s) content = <ErrorState error={steps.error} retry={() => void steps.refetch()} title="The Case File could not be read here" />;
  else if (tab === "summary") content = <BoardSummary steps={s} docs={cf.data?.documents} staging={staging.data} open={open} />;
  else if (tab === "reports") content = <BoardReports caseId={caseId} view={view} docs={docs} cfDocs={cf.data?.documents} interactive={interactive} navigates={navigates} onNavigate={go} />;
  else if (tab === "images") content = <BoardImages caseId={caseId} view={view} mode={mode} docs={docs} interactive={interactive} onNavigate={go} />;
  else content = <BoardStage caseId={caseId} steps={s} staging={staging.data} stagingLoading={staging.isLoading} open={open} />;

  return (
    <div className={cn("board-view @container flex min-h-0 flex-col text-foreground", className)} data-testid="board-view" data-mode={mode} data-tab={tab} data-doc={view.doc_id ?? ""} data-page={view.page ?? ""}>
      {/* narrow (a phone): the header scrolls away with the content; wide (the projector): the header stays, the body scrolls */}
      <div ref={frame} className="scroll-thin flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto @3xl:overflow-visible" data-testid="board-frame">
        <header className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
            <div className="min-w-0 flex-1 basis-[20rem]"><CaseLine cf={cf.data} steps={s} presenter={presenter} /></div>
            <FollowBar mode={mode} followingName={followingName} onLookAround={onLookAround} onBackToRoom={onBackToRoom} pending={pending} />
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div role="tablist" aria-label="Board view" className="flex flex-wrap gap-2" onKeyDown={onTabKey}>
              {TABS.map((t, i) => {
                const on = t.id === tab;
                const count = t.id === "reports" ? docs.length : t.id === "images" ? imaging : null;
                return (
                  <button key={t.id} ref={(el) => { tabRefs.current[i] = el; }} type="button" role="tab" id={`bv-tab-${t.id}`} aria-selected={on} aria-controls="bv-panel"
                    tabIndex={on ? 0 : -1} disabled={!interactive && !on} onClick={() => go(t.id)} data-testid={`board-tab-${t.id}`}
                    className={cn("inline-flex items-center gap-2 rounded-full border px-4 py-2 text-base font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                      on ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-foreground enabled:hover:bg-accent disabled:cursor-default disabled:text-muted-foreground")}>
                    {t.label}{s && count !== null ? <span className={cn("text-sm tabular-nums", on ? "text-primary-foreground/80" : "text-muted-foreground")}>{count}</span> : null}
                  </button>
                );
              })}
            </div>
          </div>
          {error ? <p role="alert" className="rounded-md status-bad px-3 py-2 text-sm" data-testid="board-error">{error}</p> : null}
        </header>
        <div ref={body} id="bv-panel" role="tabpanel" aria-labelledby={`bv-tab-${tab}`} className="scroll-thin @3xl:min-h-0 @3xl:flex-1 @3xl:overflow-y-auto" data-testid="board-body">
          {content}
        </div>
      </div>
    </div>
  );
}
