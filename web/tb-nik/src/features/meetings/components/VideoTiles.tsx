// The people in the meeting as tiles, the way a video call shows them: the camera when it is on, the initials when it is off,
// the name and department, the role badges, the microphone state, a ring and a "speaking" icon while someone speaks, the
// connection bars, a hand when it is raised, a reaction for a moment. Members who are in the room without a laptop still get a
// tile from the attendance list. LiveKit carries the video and audio. The call shell's strip and stage (call/Strip.tsx,
// call/StageContent.tsx) build on TileFrame and LiveVideo; TileGrid stays for the older pages.
import { useMemo, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { RoomAudioRenderer, RoomContext, VideoTrack, isTrackReference, useIsSpeaking, useTracks, type TrackReference } from "@livekit/components-react";
import { Track, type Participant, type Room } from "livekit-client";
import { AudioLines, Hand, Mic, MicOff, MonitorPlay } from "lucide-react";
import type { Attendee } from "@/lib/live";
import { identityUser, isRoomScreen } from "@/lib/video";
import { initials } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { BADGE_WORD, type RoleBadge } from "../call/types";

export interface TilePerson {
  key: string;
  user: string;
  name: string;
  department?: string;
  remote: boolean;
  hand: boolean;
  local?: boolean;
  roomScreen?: boolean;
  /** Head, Coordinator, Presenter, Outside expert (call/types.ts badgesOf). */
  badges?: RoleBadge[];
  /** The place in the queue of raised hands (1 is the first). */
  handOrder?: number;
}

export type TileSize = "sm" | "md" | "lg";

const COLOURS = ["#2f6f8f", "#3e5cad", "#5b3fc4", "#1d6a44", "#8a5200", "#9c3d5e", "#2a7a74", "#6b4e2e"];
export function colourOf(key: string): string {
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COLOURS[h % COLOURS.length];
}

export function Avatar({ name, size }: { name: string; size: TileSize }) {
  const dim = size === "lg" ? "size-20 text-2xl" : size === "md" ? "size-14 text-lg" : "size-9 text-sm";
  return <span className={cn("grid place-items-center rounded-full font-semibold text-white", dim)} style={{ background: colourOf(name) }} aria-hidden>{initials(name)}</span>;
}

/** The bars of a connection (excellent 3, good 2, poor 1, lost 0); nothing when LiveKit does not know yet. */
export const QUALITY_BARS: Record<string, number> = { excellent: 3, good: 2, poor: 1, lost: 0 };
export function QualityBars({ quality, className, mine }: { quality?: string | null; className?: string; mine?: boolean }) {
  if (!quality || !(quality in QUALITY_BARS)) return null;
  const n = QUALITY_BARS[quality];
  const label = `${mine ? "Your connection" : "Connection"} is ${quality}`;
  return (
    <span className={cn("inline-flex items-end gap-px", className)} role="img" aria-label={label} title={label}>
      {[0, 1, 2].map((i) => <span key={i} className={cn("w-[3px] rounded-[1px]", i < n ? (n === 1 ? "bg-warn" : "bg-white/90") : "bg-white/30")} style={{ height: 4 + i * 3 }} />)}
    </span>
  );
}

/** The small "speaking" bars, so the ring is not the only sign (not colour alone). */
export function SpeakingIcon({ className }: { className?: string }) {
  return <AudioLines className={cn("size-3.5 shrink-0 text-primary", className)} role="img" aria-label="speaking" />;
}

/** A reaction over a tile for a moment: the glyph and its word. */
export function ReactionBadge({ glyph, word, big }: { glyph: string; word: string; big?: boolean }) {
  const reduce = useReducedMotion();
  return (
    <motion.span
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0 }}
      className={cn("pointer-events-none absolute left-2 top-2 z-10 inline-flex items-center gap-1 rounded-full bg-black/65 px-2 py-0.5 font-medium text-white shadow", big ? "text-base" : "text-xs")}
      role="status"
    >
      <span aria-hidden className={big ? "text-xl" : "text-sm"}>{glyph}</span>{word}
    </motion.span>
  );
}

/** The old aria label of a tile (TileGrid); the call shell builds a fuller one with tileAriaLabel in call/Strip.tsx. */
function plainLabel(person: TilePerson, micOn?: boolean | null): string {
  return `${person.name}${person.department ? `, ${person.department}` : ""}${person.remote ? ", remote" : ", in the room"}${micOn === false ? ", microphone off" : ""}${person.hand ? ", hand raised" : ""}`;
}

export function TileFrame({ person, speaking, micOn, children, size, className, label, quality, qualityMine, reaction, menu, chip, big, testId = "tile" }: {
  person: TilePerson;
  speaking?: boolean;
  micOn?: boolean | null;
  children?: ReactNode;
  size: TileSize;
  className?: string;
  /** The aria label (default: name, department, where, microphone, hand). */
  label?: string;
  quality?: string | null;
  qualityMine?: boolean;
  reaction?: { glyph: string; word: string } | null;
  /** The tile menu (three dots), positioned by the frame at the top right. */
  menu?: ReactNode;
  /** A chip at the top left (for example "Pinned"). */
  chip?: ReactNode;
  /** Large type (the room screen, a person on the stage). */
  big?: boolean;
  testId?: string;
}) {
  return (
    <div
      className={cn("group/tile relative aspect-video overflow-hidden rounded-xl bg-stage-raised ring-2 ring-transparent transition-[box-shadow,ring-color] duration-200", speaking && "ring-ok", className)}
      data-testid={testId}
      data-user={person.user}
      data-speaking={speaking ? "true" : undefined}
      role="group"
      aria-label={label ?? plainLabel(person, micOn)}
    >
      {children ?? <div className="grid h-full w-full place-items-center"><Avatar name={person.name} size={size} /></div>}
      {chip ? <div className="absolute left-2 top-2 z-10 flex items-center gap-1">{chip}</div> : null}
      <AnimatePresence>{reaction ? <ReactionBadge key={reaction.word} glyph={reaction.glyph} word={reaction.word} big={big} /> : null}</AnimatePresence>
      {menu ? <div className="absolute right-1.5 top-1.5 z-10 opacity-100 transition-opacity lg:opacity-0 lg:group-hover/tile:opacity-100 lg:group-focus-within/tile:opacity-100 [&:has([data-state=open])]:opacity-100">{menu}</div> : null}
      <div className={cn("absolute inset-x-0 bottom-0 flex items-center gap-1.5 bg-gradient-to-t from-black/75 to-transparent px-2 pb-1.5 pt-5", big && "px-3 pb-2.5")} aria-hidden>
        {micOn === false ? <MicOff className={cn("shrink-0 text-white/90", big ? "size-5" : "size-3.5")} /> : micOn ? <Mic className={cn("shrink-0 text-white/90", big ? "size-5" : "size-3.5", speaking && "text-ok")} /> : null}
        {speaking ? <SpeakingIcon className={big ? "size-5" : undefined} /> : null}
        <span className={cn("min-w-0 truncate font-medium text-white", big ? "text-lg" : "text-xs")}>{person.name}{person.local ? " (you)" : ""}</span>
        {person.department ? <span className={cn("hidden min-w-0 truncate text-white/70 sm:inline", big ? "text-base" : "text-[11px]")}>· {person.department}</span> : null}
        {(person.badges ?? []).map((b) => <span key={b} className={cn("hidden shrink-0 rounded px-1 font-medium sm:inline", big ? "text-sm" : "text-[10px]", b === "presenter" ? "bg-primary/80 text-primary-foreground" : "bg-white/15 text-white/90")}>{BADGE_WORD[b]}</span>)}
        <span className="flex-1" />
        {person.roomScreen ? <MonitorPlay className="size-3.5 text-white/80" /> : null}
        {!person.remote && !person.roomScreen ? <span className={cn("rounded bg-white/15 px-1 text-white/90", big ? "text-sm" : "text-[10px]")}>room</span> : null}
        <QualityBars quality={quality} mine={qualityMine} />
        {person.hand ? <span className={cn("inline-flex h-5 items-center gap-0.5 rounded-full bg-warn px-1 text-white", big && "h-7 px-2")}><Hand className={big ? "size-4" : "size-3"} />{person.handOrder ? <span className={cn("font-bold leading-none", big ? "text-sm" : "text-[10px]")}>{person.handOrder}</span> : null}</span> : null}
      </div>
    </div>
  );
}

/** A LiveKit participant's camera as a track reference (null when the camera is off, muted or not subscribed yet). */
export function cameraRef(participant: Participant): TrackReference | null {
  const pub = participant.getTrackPublication(Track.Source.Camera);
  if (!pub || pub.isMuted || (!pub.track && !participant.isLocal)) return null;
  return { participant, publication: pub, source: Track.Source.Camera };
}

/** The microphone state of a participant: true on, false off. */
export function micStateOf(participant: Participant): boolean {
  const pub = participant.getTrackPublication(Track.Source.Microphone);
  return pub ? !pub.isMuted : false;
}

/** The camera of a participant inside a tile (mirrored for my own), or nothing (the frame then shows the initials). */
export function LiveVideo({ participant, fit = "cover" }: { participant: Participant; fit?: "cover" | "contain" }) {
  const ref = cameraRef(participant);
  if (!ref) return null;
  return <VideoTrack trackRef={ref} className={cn("h-full w-full", fit === "contain" ? "object-contain bg-black" : "object-cover", participant.isLocal && "-scale-x-100")} />;
}

/** True while the participant speaks (LiveKit's own speaking flag). */
export function useSpeaking(participant: Participant): boolean {
  return useIsSpeaking(participant);
}

/** A tile for a LiveKit participant: the camera when published and not muted, else the initials; the ring while speaking. */
function LiveTile({ participant, person, size, trackRef }: { participant: Participant; person: TilePerson; size: TileSize; trackRef: ReturnType<typeof useTracks>[number] }) {
  const speaking = useIsSpeaking(participant);
  const camPub = participant.getTrackPublication(Track.Source.Camera);
  const micPub = participant.getTrackPublication(Track.Source.Microphone);
  const hasVideo = !!camPub && !camPub.isMuted && (!!camPub.track || participant.isLocal);
  const micOn = micPub ? !micPub.isMuted : false;
  return (
    <TileFrame person={person} speaking={speaking} micOn={micOn} size={size}>
      {hasVideo && isTrackReference(trackRef) ? <VideoTrack trackRef={trackRef} className={cn("h-full w-full object-cover", participant.isLocal && "-scale-x-100")} /> : undefined}
    </TileFrame>
  );
}

function Live({ people, size, max }: { people: TilePerson[]; size: TileSize; max: number }) {
  const tracks = useTracks([{ source: Track.Source.Camera, withPlaceholder: true }], { onlySubscribed: false });
  const byUser = useMemo(() => new Map(people.map((p) => [p.key, p])), [people]);
  const seen = new Set<string>();
  const tiles: React.ReactNode[] = [];
  for (const t of tracks) {
    const id = t.participant.identity;
    const key = isRoomScreen(id) ? `${identityUser(id)}#room` : identityUser(id);
    seen.add(key);
    const base = byUser.get(key);
    const person: TilePerson = base ?? { key, user: identityUser(id), name: t.participant.name || identityUser(id), remote: !isRoomScreen(id), hand: false, roomScreen: isRoomScreen(id) };
    tiles.push(<LiveTile key={`${id}-${t.source}`} participant={t.participant} person={{ ...person, local: t.participant.isLocal }} size={size} trackRef={t} />);
  }
  for (const p of people) if (!seen.has(p.key)) tiles.push(<TileFrame key={p.key} person={p} size={size} micOn={null} />);
  const shown = tiles.slice(0, max);
  const more = tiles.length - shown.length;
  return (
    <>
      {shown}
      {more > 0 ? <div className="grid aspect-video place-items-center rounded-xl bg-stage-raised text-sm text-stage-muted">+{more} more</div> : null}
      <RoomAudioRenderer />
    </>
  );
}

/** The attendance list as tile people: admitted members, the hands, the room screen when the coordinator has it on. */
export function tilePeople(attendance: Attendee[], hands: Set<string>, me?: string | null): TilePerson[] {
  return attendance
    .filter((a) => a.status === "present" || a.status === "remote")
    .map((a) => ({ key: a.user, user: a.user, name: a.name, department: a.department_name ?? a.department, remote: a.status === "remote", hand: hands.has(a.user) || !!a.hand, local: a.user === me }));
}

export function TileGrid({ room, people, layout = "column", size = "md", max = 8, className }: { room: Room | null; people: TilePerson[]; layout?: "column" | "row" | "grid"; size?: TileSize; max?: number; className?: string }) {
  const cls = layout === "column" ? "flex flex-col gap-2" : layout === "row" ? "flex gap-2 overflow-x-auto scroll-thin [&>*]:w-40 [&>*]:shrink-0" : "grid gap-2 grid-cols-2 sm:grid-cols-3";
  if (!people.length && !room) return <p className="text-sm text-stage-muted">No one has joined yet.</p>;
  return (
    <div className={cn(cls, className)} data-testid="tile-grid">
      {room ? <RoomContext.Provider value={room}><Live people={people} size={size} max={max} /></RoomContext.Provider> : (
        <>
          {people.slice(0, max).map((p) => <TileFrame key={p.key} person={p} size={size} micOn={null} />)}
          {people.length > max ? <div className="grid aspect-video place-items-center rounded-xl bg-stage-raised text-sm text-stage-muted">+{people.length - max} more</div> : null}
        </>
      )}
    </div>
  );
}
