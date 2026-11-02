// The main stage of the call (night-v3 5.1, research/04 section 6.6): one item at a time. A pinned person or the spotlight; else a
// screen someone presents (night-v3 5.2: the LiveKit screen share, full on the stage, "<name> is presenting", Stop for the sharer and
// the coordinator; its audio plays through the room's audio renderer); else the active speaker when the layout asks for it; else the
// Board view of the Case File on the floor (meetings-v2 2.5, owner decisions D1 to D5: the Case File itself, read-only, led by the
// coordinator or the presenter, followed by the room and every remote member; an outside expert sees the identity-stripped summary
// instead); else, with nothing on the floor, a grid of every tile with the next case named. Layout "grid" shows every tile with the
// shared content as the first tile. The connection banner and the call's audio live here so every variant has them once. Overlays from
// the shell come as children. No slides (D5).
import type { ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { RoomAudioRenderer, VideoTrack } from "@livekit/components-react";
import { FileText, MonitorUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { BoardView } from "../board/BoardView";
import { ExpertSummary } from "../board/ExpertSummary";
import { useCall } from "./context";
import { ConnectionBanner } from "./ConnectionBanner";
import { AgentCallTile, CallTile, ContentTile, UnpinChip, nextCaseLine, presenterName, screenShareRef, useCallAgents, useCallPeople, useStageMode, type CallPerson } from "./Strip";
import type { CallCtx } from "./types";

/** The words on a stage with no Case File on the floor. */
export function emptyStageText(ctx: Pick<CallCtx, "cid" | "variant" | "state">): string {
  const st = ctx.state.meeting.status;
  if (st === "planned") return ctx.variant === "room" ? "Waiting for the coordinator to start" : "The meeting has not started";
  if (st === "closed") return "The meeting is closed";
  if (st === "cancelled") return "The meeting was cancelled";
  if (ctx.cid) return "No Case File on the floor yet";
  return ctx.variant === "coordinator" ? "No Case File on the floor yet: pick one from the agenda or press First case." : "Waiting for the first case";
}

/** The Board view on the stage: the Case File on the floor as this screen follows, leads or looks around; the outside expert's summary;
 *  or the plain words when nothing is on the floor yet. */
function BoardOnStage({ big }: { big: boolean }) {
  const ctx = useCall();
  const f = ctx.follow;
  if (ctx.expert && ctx.cid) return <ExpertSummary mid={ctx.mid} caseId={ctx.cid} big={big} />;
  if (!f.caseId) {
    return (
      <div className="grid h-full place-items-center p-6 text-center" data-testid="board-empty">
        <p className={cn("flex flex-col items-center gap-3 text-stage-muted", big ? "text-3xl" : "text-xl")}><FileText className={big ? "size-12" : "size-9"} aria-hidden />{emptyStageText(ctx)}</p>
      </div>
    );
  }
  return (
    <BoardView caseId={f.caseId} view={f.view} mode={f.mode} onNavigate={f.navigate} followingName={f.followingName}
      onLookAround={f.canLook ? f.lookAround : undefined} onBackToRoom={f.backToRoom} presenter={ctx.state.current?.presenter?.name}
      error={f.error} pending={f.pending} className={cn("h-full min-h-0", big && "board-big")} />
  );
}

const fade = { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } };

function TileWall({ people, withContent, big }: { people: CallPerson[]; withContent: boolean; big?: boolean }) {
  const agents = useCallAgents();
  const n = people.length + agents.length + (withContent ? 1 : 0);
  const cols = n <= 1 ? "grid-cols-1" : n <= 4 ? "grid-cols-2" : n <= 9 ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-2 sm:grid-cols-3 xl:grid-cols-4";
  return (
    <div className={cn("grid content-center gap-2", cols, n <= 1 && "mx-auto w-full max-w-xl")} role="list" aria-label="People in the call" data-testid="stage-grid">
      {withContent ? <div role="listitem"><ContentTile big={big} /></div> : null}
      {people.map((p) => <div role="listitem" key={p.key}><CallTile p={p} size={big ? "lg" : "md"} big={big} /></div>)}
      {agents.map((a) => <div role="listitem" key={`agent-${a.role}`}><AgentCallTile agent={a} big={big} /></div>)}
    </div>
  );
}

/** "<name> is presenting" on the shared picture, with Stop for the sharer (my own share) and the coordinator (anyone's). */
function ShareBadge({ name, user }: { name: string; user: string }) {
  const ctx = useCall();
  const big = ctx.variant === "room";
  const mine = !!ctx.me && user === ctx.me && ctx.variant !== "room";
  const canStop = ctx.variant !== "room" && (mine ? !!ctx.video.toggleShare : ctx.canManage);
  const stop = () => { if (mine) void ctx.video.toggleShare?.(); else void ctx.actions.presenting?.(false).catch(() => undefined); };
  return (
    <p className={cn("absolute left-3 top-3 z-10 flex items-center gap-2 rounded-full bg-black/70 py-1 pl-3 font-medium text-white", canStop ? "pr-1" : "pr-3", big ? "text-lg" : "text-xs")} data-testid="share-badge">
      <MonitorUp className={big ? "size-5" : "size-3.5"} aria-hidden />{name} presenting
      {canStop ? <button type="button" onClick={stop} className="rounded-full bg-[#c23b3b] px-2.5 py-0.5 text-xs font-semibold text-white outline-none hover:bg-[#ad3434] focus-visible:ring-2 focus-visible:ring-white" aria-label={mine ? "Stop presenting" : "Stop the share for everyone"} title={mine ? "Stop presenting (Ctrl+Alt+T)" : "Stop the share for everyone"} data-testid="share-stop">Stop</button> : null}
    </p>
  );
}

export function StageContent({ className, children }: { className?: string; children?: ReactNode }) {
  const ctx = useCall();
  const people = useCallPeople();
  const agents = useCallAgents();
  const mode = useStageMode(people);
  const big = ctx.variant === "room";
  const byKey = new Map(people.map((p) => [p.key, p]));
  const room = ctx.video.room;

  let body: ReactNode;
  let bodyKey: string;
  let stage: string = mode.kind;
  if (mode.kind === "share") {
    const user = ctx.state.presenting ?? "";
    const name = presenterName(user, ctx.state.attendance ?? [], room);
    const mine = !!ctx.me && user === ctx.me && ctx.variant !== "room";
    const track = mine ? null : screenShareRef(room, user);
    stage = mine ? "share-self" : track ? "share" : "share-waiting";
    bodyKey = `${stage}-${user}`;
    body = (
      <motion.div key={bodyKey} {...fade} className={cn("absolute inset-0", track && "bg-black")} data-testid="stage-share">
        {track ? <VideoTrack trackRef={track} className="h-full w-full bg-black object-contain" /> : (
          <div className="grid h-full place-items-center p-6 text-center">
            <p className={cn("flex flex-col items-center gap-2 text-stage-muted", big ? "text-2xl" : "text-base")}>
              <MonitorUp className={big ? "size-10" : "size-7"} aria-hidden />
              {mine ? "You are presenting. Everyone sees the screen you chose." : `${name} is presenting: waiting for the picture`}
            </p>
          </div>
        )}
        <ShareBadge name={mine ? "You are" : `${name} is`} user={user} />
      </motion.div>
    );
  } else if (mode.kind === "person" || mode.kind === "spotlight") {
    const shown = mode.keys.map((k) => byKey.get(k)).filter((p): p is CallPerson => !!p);
    const pinned = mode.kind === "person" && mode.why === "pinned";
    const lit = (ctx.spotlight ?? []).filter((u) => byKey.has(u));
    bodyKey = `${mode.kind}-${mode.keys.join(",")}`;
    body = (
      <motion.div key={bodyKey} {...fade} className={cn("absolute inset-0 grid gap-2 p-2", shown.length === 2 ? "grid-cols-1 sm:grid-cols-2" : shown.length >= 3 ? "grid-cols-1 sm:grid-cols-3" : "grid-cols-1")} data-testid="stage-person">
        {shown.map((p) => <CallTile key={p.key} p={p} size="lg" big className="aspect-auto h-full min-h-0" fit="contain" chip={pinned ? <UnpinChip big={big} /> : undefined} />)}
        {pinned && lit.length && ctx.variant !== "room" ? (
          <p className="absolute bottom-14 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full bg-black/65 px-3 py-1 text-xs text-white" role="status">
            The coordinator spotlighted {lit.map((u) => byKey.get(u)?.name ?? u).join(", ")}
            <button type="button" className="rounded-full bg-primary px-2 py-0.5 font-semibold text-primary-foreground outline-none hover:bg-primary-hover focus-visible:ring-2 focus-visible:ring-primary" onClick={() => { ctx.setPinned(null); ctx.setLayout("spotlight"); }} title="Show the spotlight">Show</button>
          </p>
        ) : null}
      </motion.div>
    );
  } else if (mode.kind === "grid" || mode.kind === "floor") {
    const next = mode.kind === "floor" ? nextCaseLine(ctx.order, ctx.cid) : null;
    bodyKey = mode.kind;
    body = (
      <motion.div key={bodyKey} {...fade} className="scroll-thin absolute inset-0 flex flex-col gap-3 overflow-y-auto p-3">
        {mode.kind === "floor" ? (
          <div className="text-center">
            <p className={cn("text-stage-fg", big ? "text-2xl" : "text-base")}>{emptyStageText(ctx)}</p>
            {next ? <p className={cn("mt-0.5 text-stage-muted", big ? "text-lg" : "text-sm")} data-testid="next-case">{next}</p> : null}
          </div>
        ) : null}
        {people.length || agents.length || mode.kind === "grid" ? <div className="flex min-h-0 flex-1 flex-col justify-center"><TileWall people={people} withContent={mode.kind === "grid" && !!ctx.cid} big={big} /></div> : null}
      </motion.div>
    );
  } else if (mode.kind === "board") {
    // one key per Case File: a tab or a report changes inside the Board view, it never fades the whole stage
    bodyKey = `board-${ctx.cid ?? ""}`;
    body = (
      <motion.div key={bodyKey} {...fade} className={cn("absolute inset-0 flex min-h-0 flex-col bg-background", big ? "p-4 lg:p-5" : "p-3 lg:p-4")} data-testid="stage-board">
        <BoardOnStage big={big} />
      </motion.div>
    );
  } else {
    bodyKey = "empty";
    body = (
      <motion.div key={bodyKey} {...fade} className="absolute inset-0 grid place-items-center p-6 text-center">
        <p className={cn("text-stage-muted", big ? "text-2xl" : "text-base")}>{emptyStageText(ctx)}</p>
      </motion.div>
    );
  }

  return (
    <section
      className={cn("relative min-h-0 flex-1 overflow-hidden rounded-xl border border-stage-line bg-stage-panel", className)}
      aria-label="Shared screen"
      data-testid="shared-screen"
      data-stage={stage}
    >
      <AnimatePresence mode="wait" initial={false}>{body}</AnimatePresence>
      <ConnectionBanner />
      {children}
      {room ? <RoomAudioRenderer room={room} /> : null}
    </section>
  );
}
