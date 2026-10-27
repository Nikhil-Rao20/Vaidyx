// The main stage of the call (night-v3 5.1, research/04 section 6.6): one item at a time. A pinned person or the spotlight; else a
// screen someone presents (night-v3 5.2: the LiveKit screen share, full on the stage, "<name> is presenting", Stop for the sharer and
// the coordinator; its audio plays through the room's audio renderer); else the active speaker when the layout asks for it; else what the coordinator opened (the images in the hospital viewer, only when a
// same-origin viewer path exists, or a record page); else the slide; else, with nothing on the floor, a grid of every tile with
// the next case named. Layout "grid" shows every tile with the shared content as the first tile. The connection banner and the
// call's audio live here so every variant has them once. Overlays from the shell come as children.
import type { ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { RoomAudioRenderer, VideoTrack } from "@livekit/components-react";
import { ImageOff, MonitorUp } from "lucide-react";
import { recordPageUrl, viewerSrc } from "../api";
import { SlideContent } from "../components/shared";
import { errorText } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { useCall } from "./context";
import { ConnectionBanner } from "./ConnectionBanner";
import { AgentCallTile, CallTile, ContentTile, UnpinChip, nextCaseLine, presenterName, screenShareRef, useCallAgents, useCallPeople, useStageMode, type CallPerson } from "./Strip";
import type { CallCtx } from "./types";

/** The words on an empty stage. */
export function emptyStageText(ctx: Pick<CallCtx, "cid" | "variant" | "slidesStatus" | "slidesError" | "state">): string {
  if (ctx.cid) {
    if (ctx.slidesStatus === "loading" || ctx.slidesStatus === "idle") return "Loading the slides";
    if (ctx.slidesStatus === "error") return `The slides could not be loaded: ${errorText(ctx.slidesError)}`;
    return ctx.variant === "coordinator" ? "Pick a slide, a record or the images." : ctx.variant === "room" ? "The coordinator can show a slide, a record or the images here." : "Nothing on the screen yet";
  }
  const st = ctx.state.meeting.status;
  return st === "planned" ? "The meeting has not started" : st === "closed" ? "The meeting is closed" : st === "cancelled" ? "The meeting was cancelled" : "Waiting for the first case";
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
      {canStop ? <button type="button" onClick={stop} className="rounded-full bg-[#d64545] px-2.5 py-0.5 text-xs font-semibold text-white outline-none hover:bg-[#c23b3b] focus-visible:ring-2 focus-visible:ring-white" aria-label={mine ? "Stop presenting" : "Stop the share for everyone"} title={mine ? "Stop presenting (Ctrl+Alt+T)" : "Stop the share for everyone"} data-testid="share-stop">Stop</button> : null}
    </p>
  );
}

export function StageContent({ className, children }: { className?: string; children?: ReactNode }) {
  const ctx = useCall();
  const people = useCallPeople();
  const agents = useCallAgents();
  const mode = useStageMode(people);
  const big = ctx.variant === "room";
  const opened = ctx.variant === "member" && !ctx.following ? null : ctx.opened;
  const slide = ctx.slides[ctx.shownSlide] ?? null;
  const viewer = opened?.kind === "images" ? viewerSrc(opened) : null;
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
      <motion.div key={bodyKey} {...fade} className="absolute inset-0 bg-black" data-testid="stage-share">
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
        {people.length || agents.length || mode.kind === "grid" ? <div className="flex min-h-0 flex-1 flex-col justify-center"><TileWall people={people} withContent={mode.kind === "grid" && (!!ctx.cid || !!opened)} big={big} /></div> : null}
      </motion.div>
    );
  } else if (mode.kind === "opened" && opened?.kind === "images") {
    bodyKey = `img-${viewer ?? "none"}`;
    body = viewer ? (
      <motion.iframe key={bodyKey} {...fade} title={`Image viewer${opened.title ? `: ${opened.title}` : ""}`} src={viewer} className="absolute inset-0 h-full w-full bg-black" allow="fullscreen" />
    ) : (
      <motion.div key={bodyKey} {...fade} className="absolute inset-0 grid place-items-center p-6 text-center" data-testid="no-images">
        <p className={cn("flex flex-col items-center gap-2 text-stage-muted", big ? "text-2xl" : "text-base")}><ImageOff className={big ? "size-10" : "size-7"} aria-hidden />No images are linked to this Case File yet</p>
      </motion.div>
    );
  } else if (mode.kind === "opened" && opened?.kind === "record" && opened.doc_id && ctx.cid) {
    bodyKey = `rec-${opened.doc_id}-${opened.page ?? 0}`;
    body = (
      <motion.div key={bodyKey} {...fade} className="scroll-thin absolute inset-0 overflow-auto bg-[#1a1f26] p-3 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary" tabIndex={0} role="region" aria-label="Record">
        {opened.title ? <p className="sticky top-0 z-10 mb-2 inline-block rounded-md bg-stage-raised/90 px-2 py-1 text-sm font-medium text-stage-fg shadow">{opened.title}</p> : null}
        <img src={recordPageUrl(ctx.cid, opened.doc_id, opened.page ?? 0)} alt={`${opened.title ?? "Record"}, page ${(opened.page ?? 0) + 1}`} className="mx-auto h-auto max-w-full rounded-md bg-white" />
      </motion.div>
    );
  } else if (slide) {
    bodyKey = `slide-${slide.id}`;
    body = (
      <motion.div key={bodyKey} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.22 }} className={cn("scroll-thin stage-slide absolute inset-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary", big ? "p-6 lg:p-8" : "p-4 lg:p-5")} tabIndex={0} role="region" aria-label="Slide">
        <SlideContent slide={slide} big={big} />
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
      data-opened={opened?.kind ?? "slide"}
      data-stage={stage}
    >
      <AnimatePresence mode="wait" initial={false}>{body}</AnimatePresence>
      <ConnectionBanner />
      {children}
      {room ? <RoomAudioRenderer room={room} /> : null}
    </section>
  );
}
