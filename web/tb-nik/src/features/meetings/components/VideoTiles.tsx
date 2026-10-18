// The people in the meeting as tiles, the way a video call shows them: the camera when it is on, the initials when it is off,
// the name and department, the microphone state, a ring while someone speaks, a hand when it is raised. Members who are in the
// room without a laptop still get a tile from the attendance list. LiveKit carries the video and audio.
import { useMemo } from "react";
import { RoomAudioRenderer, RoomContext, VideoTrack, isTrackReference, useIsSpeaking, useTracks } from "@livekit/components-react";
import { Track, type Participant, type Room } from "livekit-client";
import { Hand, Mic, MicOff, MonitorPlay } from "lucide-react";
import type { Attendee } from "@/lib/live";
import { identityUser, isRoomScreen } from "@/lib/video";
import { initials } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

export interface TilePerson {
  key: string;
  user: string;
  name: string;
  department?: string;
  remote: boolean;
  hand: boolean;
  local?: boolean;
  roomScreen?: boolean;
}

const COLOURS = ["#2f6f8f", "#3e5cad", "#5b3fc4", "#1d6a44", "#8a5200", "#9c3d5e", "#2a7a74", "#6b4e2e"];
function colourOf(key: string): string {
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COLOURS[h % COLOURS.length];
}

function Avatar({ name, size }: { name: string; size: "sm" | "md" | "lg" }) {
  const dim = size === "lg" ? "size-20 text-2xl" : size === "md" ? "size-14 text-lg" : "size-9 text-sm";
  return <span className={cn("grid place-items-center rounded-full font-semibold text-white", dim)} style={{ background: colourOf(name) }} aria-hidden>{initials(name)}</span>;
}

function TileFrame({ person, speaking, micOn, children, size, className }: { person: TilePerson; speaking?: boolean; micOn?: boolean | null; children?: React.ReactNode; size: "sm" | "md" | "lg"; className?: string }) {
  return (
    <div
      className={cn("relative aspect-video overflow-hidden rounded-xl bg-stage-raised ring-2 ring-transparent transition-[box-shadow,ring-color] duration-200", speaking && "ring-primary", className)}
      data-testid="tile"
      data-user={person.user}
      aria-label={`${person.name}${person.department ? `, ${person.department}` : ""}${person.remote ? ", remote" : ", in the room"}${micOn === false ? ", microphone off" : ""}${person.hand ? ", hand raised" : ""}`}
    >
      {children ?? <div className="grid h-full w-full place-items-center"><Avatar name={person.name} size={size} /></div>}
      <div className="absolute inset-x-0 bottom-0 flex items-center gap-1.5 bg-gradient-to-t from-black/70 to-transparent px-2 pb-1.5 pt-5">
        {micOn === false ? <MicOff className="size-3.5 shrink-0 text-white/90" aria-hidden /> : micOn ? <Mic className={cn("size-3.5 shrink-0 text-white/90", speaking && "text-primary")} aria-hidden /> : null}
        <span className="min-w-0 truncate text-xs font-medium text-white">{person.name}{person.local ? " (you)" : ""}</span>
        {person.department ? <span className="hidden min-w-0 truncate text-[11px] text-white/70 sm:inline">· {person.department}</span> : null}
        <span className="flex-1" />
        {person.roomScreen ? <MonitorPlay className="size-3.5 text-white/80" aria-label="room screen" /> : null}
        {!person.remote && !person.roomScreen ? <span className="rounded bg-white/15 px-1 text-[10px] text-white/90">room</span> : null}
        {person.hand ? <span className="grid size-5 place-items-center rounded-full bg-warn text-white" aria-label="hand raised"><Hand className="size-3" /></span> : null}
      </div>
    </div>
  );
}

/** A tile for a LiveKit participant: the camera when published and not muted, else the initials; the ring while speaking. */
function LiveTile({ participant, person, size, trackRef }: { participant: Participant; person: TilePerson; size: "sm" | "md" | "lg"; trackRef: ReturnType<typeof useTracks>[number] }) {
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

function Live({ people, size, max }: { people: TilePerson[]; size: "sm" | "md" | "lg"; max: number }) {
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

export function TileGrid({ room, people, layout = "column", size = "md", max = 8, className }: { room: Room | null; people: TilePerson[]; layout?: "column" | "row" | "grid"; size?: "sm" | "md" | "lg"; max?: number; className?: string }) {
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
