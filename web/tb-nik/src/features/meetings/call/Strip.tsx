// The participant strip of the call (night-v3 5.1, research/04 section 6.7): the people (the admitted attendance and the
// LiveKit participants), the active speakers first after a 2 s delay so the strip does not jump, then the AI agents standing in
// for absent heads (dashed, the Vaidyx mark, never a member), then "+n more". When the stage shows a person (pin, spotlight,
// speaker) the first tile is the shared content with "Show" to put it back. Every tile has a menu: Pin for me, and for the
// coordinator Spotlight for everyone. The pure helpers at the top are checked by a small node script.
// Night-v3 5.5: the room screen's column (RoomStrip) shows at most `max` remote tiles in two columns with "+n more" as words (never
// a scroll), then the agents apart under their own heading; the phone in landscape uses a column of small tiles (`small`).
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Track, type Participant, type Room } from "livekit-client";
import type { TrackReference } from "@livekit/components-react";
import { Images, Megaphone, MessageSquareText, MonitorOff, MonitorPlay, MonitorUp, MoreVertical, Pin, PinOff, Sparkles, Square, UserRoundMinus, X } from "lucide-react";
import type { AgendaRow, AgentInfo, Attendee, MeetingState, Opened } from "@/lib/live";
import { identityUser, isRoomScreen, videoExtras } from "@/lib/video";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { VaidyxIcon } from "@/components/Wordmark";
import { cn } from "@/lib/utils";
import { indianDates } from "@/features/casefile/components/common";
import { Dots } from "../components/shared";
import { LiveVideo, TileFrame, micStateOf, useSpeaking, type TilePerson, type TileSize } from "../components/VideoTiles";
import { useCall } from "./context";
import { chipText, pointsHeader, pointsLine, presentBlockedReason } from "./panels/AgentPoints";
import { AGENT_STATE_WORD, BADGE_WORD, REACTIONS, badgesOf, type CallCtx, type LayoutKind, type RoleBadge } from "./types";

// ---- pure helpers ---------------------------------------------------------------------------------------------------------

/** The tile key of a LiveKit identity: "<user>" or "<user>#room" for the room screen. */
export function personKey(identity: string): string {
  return isRoomScreen(identity) ? `${identityUser(identity)}#room` : identityUser(identity);
}

/** The speakers most recent first, kept after they stop until someone else speaks (the strip's order). */
export function pushRecent(recent: string[], speakers: string[], cap = 12): string[] {
  if (!speakers.length) return recent;
  const next = [...speakers, ...recent.filter((k) => !speakers.includes(k))];
  return next.slice(0, cap);
}

/** The tiles in order: the recent speakers first (most recent first), then the rest in their own order. */
export function orderBySpeakers<T extends { key: string }>(items: T[], recent: string[]): T[] {
  const rank = new Map(recent.map((k, i) => [k, i]));
  const spoke = items.filter((p) => rank.has(p.key)).sort((a, b) => rank.get(a.key)! - rank.get(b.key)!);
  return [...spoke, ...items.filter((p) => !rank.has(p.key))];
}

/** The role badges in words for a label ("head, presenter"). */
export function badgeText(badges: RoleBadge[] | undefined): string {
  return (badges ?? []).map((b) => BADGE_WORD[b].toLowerCase()).join(", ");
}

/** The tile's aria label: "Dr Priya, Radiology, head, presenter, remote, microphone on, hand raised". */
export function tileAriaLabel(p: {
  name: string; department?: string; badges?: RoleBadge[]; remote: boolean; roomScreen?: boolean; local?: boolean;
  micOn?: boolean | null; hand?: boolean; handOrder?: number; speaking?: boolean; quality?: string | null; pinned?: boolean; spotlit?: boolean;
}): string {
  const parts = [p.local ? `${p.name} (you)` : p.name];
  if (p.department) parts.push(p.department);
  const b = badgeText(p.badges);
  if (b) parts.push(b);
  parts.push(p.roomScreen ? "room screen" : p.remote ? "remote" : "in the room");
  if (p.micOn === true) parts.push("microphone on");
  else if (p.micOn === false) parts.push("microphone off");
  if (p.speaking) parts.push("speaking");
  if (p.hand) parts.push(p.handOrder ? `hand raised, ${ordinal(p.handOrder)} in line` : "hand raised");
  if (p.quality === "poor" || p.quality === "lost") parts.push(`connection ${p.quality}`);
  if (p.pinned) parts.push("pinned for you");
  if (p.spotlit) parts.push("in the spotlight");
  return parts.join(", ");
}

function ordinal(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : n % 10 === 1 ? "st" : n % 10 === 2 ? "nd" : n % 10 === 3 ? "rd" : "th";
  return `${n}${s}`;
}

/** The label of an agent tile: "Radiology, AI agent standing in" (the fallback when the server sends no title). */
export function agentLine(a: Pick<AgentInfo, "label" | "department" | "department_name" | "role">): string {
  const dept = a.department_name || a.department || a.label || a.role.replace(/_/g, " ");
  return `${dept}, AI agent standing in`;
}

/** The title of an agent tile, from the server ("Radiology, AI agent standing in", "Nuclear Medicine, AI agent, called by Priya
 * Nair"), else agentLine. */
export function agentTitle(a: Pick<AgentInfo, "label" | "department" | "department_name" | "role" | "title">): string {
  return (a.title ?? "").trim() || agentLine(a);
}

/** The department's name of an agent ("Radiology"). */
export function agentDept(a: Pick<AgentInfo, "label" | "department" | "department_name" | "role">): string {
  return a.department_name || a.department || a.label || a.role.replace(/_/g, " ");
}

/** The accessible name of an agent tile: the visible words in their order ("Pathology, AI agent standing in, AI agent, support
 * only, Ready, 3 points from the records", then the first point on a big tile). */
export function agentTileLabel(line: string, word: string, ...more: Array<string | null | undefined>): string {
  return [`${line}, AI agent, support only, ${word}`, ...more.filter(Boolean)].join(", ");
}

/** The state key a tile draws: a state the words know, else "ready". */
export function agentStateKey(state: string | undefined | null): string {
  return state && AGENT_STATE_WORD[state] ? state : "ready";
}

/** The state word of an agent: AGENT_STATE_WORD, and while listening "Listening to <name>" (the asker; "Listening" without one). */
export function agentStateWord(state: string | undefined | null, byName?: string | null): string {
  if (state === "listening") return byName ? `Listening to ${byName}` : (AGENT_STATE_WORD.listening ?? "Listening");
  return (state && AGENT_STATE_WORD[state]) || "Ready";
}

/** True while an agent is working (the pulse and the dots): every state but ready and error. */
export function agentBusy(state: string | undefined | null): boolean {
  return !!state && state !== "ready" && state !== "error";
}

/** The spotlight after a click: add (at most three) or remove. */
export function spotlightToggle(list: string[], user: string, max = 3): string[] {
  return list.includes(user) ? list.filter((u) => u !== user) : [...list, user].slice(-max);
}

export type StageMode =
  | { kind: "person"; keys: string[]; why: "pinned" | "speaker" }
  | { kind: "spotlight"; keys: string[] }
  | { kind: "share" }
  | { kind: "grid" }
  | { kind: "opened" }
  | { kind: "slide" }
  | { kind: "floor" };

/** What the main stage shows, in the order of research/04 section 6.6 (a person first when pinned or spotlighted, as Meet does; then
 * a screen someone presents (night-v3 5.2); then the speaker view, the grid, the opened item, the slide, and the grid when nothing is
 * on the floor). Pure. */
export function stageMode(i: { layout: LayoutKind; pinned: string | null; spotlight: string[]; speakerKey: string | null; opened: Opened | null; cid: string | null; has: (key: string) => boolean; presenting?: string | null }): StageMode {
  if (i.pinned && i.has(i.pinned)) return { kind: "person", keys: [i.pinned], why: "pinned" };
  if (i.presenting) return { kind: "share" };  // a share is for everyone: only a personal pin beats it on one's own screen (review M1)
  if (i.layout === "spotlight") {
    const keys = i.spotlight.filter(i.has).slice(0, 3);
    if (keys.length) return { kind: "spotlight", keys };
  }
  if (i.layout === "speaker" && i.speakerKey && i.has(i.speakerKey)) return { kind: "person", keys: [i.speakerKey], why: "speaker" };
  if (i.layout === "grid") return { kind: "grid" };
  if (i.opened && (i.opened.kind === "images" || i.opened.kind === "record")) return { kind: "opened" };
  if (i.cid) return { kind: "slide" };
  return { kind: "floor" };
}

/** The keys a stage mode shows large (they leave the strip). */
export function stageKeys(m: StageMode): string[] {
  return m.kind === "person" || m.kind === "spotlight" ? m.keys : [];
}

/** True when the strip is drawn beside the stage (not when the stage itself is the grid of every tile). */
export function stripShownFor(m: StageMode): boolean {
  return m.kind !== "grid" && m.kind !== "floor";
}

/** The LiveKit screen share of a login, when its picture has arrived (a remote track subscribed, or my own track), else null. The
 * room screen's identity ("<user>#room") cannot share. */
export function screenShareRef(room: Room | null, user: string | null | undefined): TrackReference | null {
  if (!room || !user) return null;
  const all: Participant[] = [room.localParticipant, ...room.remoteParticipants.values()];
  for (const p of all) {
    if (!p?.identity || isRoomScreen(p.identity) || identityUser(p.identity) !== user) continue;
    const pub = p.getTrackPublication(Track.Source.ScreenShare);
    if (pub && pub.track && !pub.isMuted && (p.isLocal || pub.isSubscribed)) return { participant: p, publication: pub, source: Track.Source.ScreenShare };
  }
  return null;
}

/** The name of the person presenting: the attendance name, else the video name, else the login. */
export function presenterName(user: string, attendance: Array<{ user: string; name: string }>, room?: Room | null): string {
  const a = attendance.find((x) => x.user === user);
  if (a?.name) return a.name;
  if (room) {
    const all: Participant[] = [room.localParticipant, ...room.remoteParticipants.values()];
    const p = all.find((x) => !!x?.identity && !isRoomScreen(x.identity) && identityUser(x.identity) === user);
    if (p?.name) return p.name;
  }
  return user;
}

/** "Allow to present", "Withdraw the right to present" and "Stop their share": what the coordinator may do for a person. */
export function presentMenuItems(i: { user: string; coordinator: string | null; canManage: boolean; allowed: string[]; presenting: string | null; roomScreen?: boolean; defaultPresenter?: string | null }): Array<"allow" | "withdraw" | "stop"> {
  if (!i.canManage || i.roomScreen || !i.user || i.user === i.coordinator) return [];
  if (i.defaultPresenter && i.user === i.defaultPresenter) return i.presenting === i.user ? ["stop"] : [];  // presents by right: nothing to allow or withdraw
  const out: Array<"allow" | "withdraw" | "stop"> = [i.allowed.includes(i.user) ? "withdraw" : "allow"];
  if (i.presenting === i.user) out.push("stop");
  return out;
}
export const PRESENT_ITEM_WORD: Record<"allow" | "withdraw" | "stop", string> = { allow: "Allow to present", withdraw: "Withdraw the right to present", stop: "Stop their share" };

/** The room screen's cut: the first `max` people, and how many more there are. Pure. */
export function roomCut<T>(people: T[], max: number): { shown: T[]; more: number } {
  const shown = people.slice(0, Math.max(0, max));
  return { shown, more: people.length - shown.length };
}

/** The next case after the current one, for the empty floor ("Next: 4. Anitha Reddy ..."). */
export function nextCaseLine(order: AgendaRow[], cid: string | null): string | null {
  const open = (r: AgendaRow) => !r.ended && !r.decided && !r.outcome;
  const at = cid ? order.findIndex((r) => r.case_id === cid) : -1;
  const i = order.findIndex((r, j) => j > at && open(r));
  return i >= 0 ? `Next: ${i + 1}. ${order[i].patient_line}` : null;
}

/** The people of the call: the admitted attendance merged with the LiveKit participants (room screen tiles included). */
export function mergePeople<P extends { identity: string; name?: string; isLocal: boolean }>(base: TilePerson[], participants: P[]): Array<TilePerson & { participant: P | null }> {
  const out: Array<TilePerson & { participant: P | null }> = base.map((p) => ({ ...p, participant: null }));
  const at = new Map(out.map((p, i) => [p.key, i]));
  for (const part of participants) {
    const key = personKey(part.identity);
    const i = at.get(key);
    if (i !== undefined) { out[i] = { ...out[i], participant: part, local: out[i].local || part.isLocal }; continue; }
    const room = isRoomScreen(part.identity);
    at.set(key, out.length);
    out.push({ key, user: identityUser(part.identity), name: part.name || identityUser(part.identity), remote: !room, hand: false, roomScreen: room, local: part.isLocal, participant: part });
  }
  return out;
}

/** The attendance as tile people with badges and the hand order. */
export function basePeople(attendance: Attendee[], state: MeetingState, opts: { me?: string | null; canManage?: boolean; onlyRemote?: boolean }): TilePerson[] {
  const handList = (state.hands ?? []).map((h) => (typeof h === "string" ? h : h.user));
  const coordinators = new Set<string>([state.meeting.created_by ?? "", opts.canManage && opts.me ? opts.me : ""].filter(Boolean));
  return attendance
    .filter((a) => (opts.onlyRemote ? a.status === "remote" : a.status === "present" || a.status === "remote"))
    .map((a) => {
      const badges = badgesOf(a, state, state.presenting ?? null);
      if (coordinators.has(a.user)) badges.splice(a.head ? 1 : 0, 0, "coordinator");
      const order = handList.indexOf(a.user);
      return { key: a.user, user: a.user, name: a.name, department: a.department_name ?? a.department, remote: a.status === "remote", hand: order >= 0 || !!a.hand, handOrder: order >= 0 ? order + 1 : undefined, local: !!opts.me && a.user === opts.me, badges };
    });
}

/** The tiles the call draws. A remote attendee who is offline and has no LiveKit participant left the call: no tile (the People
 * panel still lists them as offline); people in the room keep their tile. On the room screen the strip shows the remote members
 * only: never the room screen itself, nor someone marked as in the room who also joined the video. Pure. */
export function visiblePeople<T extends { key: string; local?: boolean; roomScreen?: boolean; participant: unknown }>(people: T[], attendance: Array<Pick<Attendee, "user" | "status" | "online">>, variant: "member" | "coordinator" | "room"): T[] {
  const by = new Map(attendance.map((a) => [a.user, a]));
  return people.filter((p) => {
    const a = by.get(p.key);
    if (!p.local && !p.participant && a?.status === "remote" && a.online === false) return false;
    if (variant === "room") {
      if (p.local && p.roomScreen) return false;
      if (!p.roomScreen && a?.status === "present") return false;
    }
    return true;
  });
}

// ---- hooks ----------------------------------------------------------------------------------------------------------------

export type CallPerson = TilePerson & { participant: Participant | null };

/** Every person tile of the call, recomputed when the attendance, the hands or the LiveKit room change. */
export function useCallPeople(): CallPerson[] {
  const { state, me, canManage, variant, video } = useCall();
  const { room, tick } = video;
  return useMemo(() => {
    const base = basePeople(state.attendance ?? [], state, { me, canManage, onlyRemote: variant === "room" });
    const parts: Participant[] = room ? [room.localParticipant, ...room.remoteParticipants.values()] : [];
    return visiblePeople(mergePeople<Participant>(base, parts.filter((p) => !!p.identity)), state.attendance ?? [], variant);
    // tick changes whenever LiveKit's participants or tracks change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, me, canManage, variant, room, tick]);
}

/** The agents of the call (ctx.agents; an older server's single `agent` as one entry). */
export function useCallAgents(): AgentInfo[] {
  const { agents, state } = useCall();
  return useMemo(() => {
    if (agents.length) return agents;
    const a = state.agent;
    if (a?.active && a.role) return [{ role: a.role, label: a.label ?? a.role, state: a.state ?? "ready", question: a.question, note: a.note }];
    return [];
  }, [agents, state.agent]);
}

/** The person speaker view shows: the last other person who spoke (kept until someone else speaks). */
export function useSpeakerKey(people: CallPerson[]): string | null {
  const { video } = useCall();
  const speakers = videoExtras(video).activeSpeakers ?? [];
  const last = useRef<string | null>(null);
  const others = new Set(people.filter((p) => !p.local).map((p) => p.key));
  const now = speakers.map(personKey).find((k) => others.has(k));
  if (now) last.current = now;
  return last.current && others.has(last.current) ? last.current : null;
}

/** The recent speakers for the strip's order, applied 2 s after a change so the strip does not jump. */
function useRecentSpeakers(): string[] {
  const { video } = useCall();
  const speakers = (videoExtras(video).activeSpeakers ?? []).map(personKey);
  const key = speakers.join("|");
  const [recent, setRecent] = useState<string[]>([]);
  useEffect(() => {
    if (!key) return;
    const list = key.split("|");
    const t = window.setTimeout(() => setRecent((r) => pushRecent(r, list)), 2000);
    return () => window.clearTimeout(t);
  }, [key]);
  return recent;
}

/** What the stage shows now (StageContent and the strip agree on it). */
export function useStageMode(people: CallPerson[]): StageMode {
  const ctx = useCall();
  const speakerKey = useSpeakerKey(people);
  const opened = ctx.variant === "member" && !ctx.following ? null : ctx.opened;
  const keys = new Set(people.map((p) => p.key));
  return stageMode({ layout: ctx.layout, pinned: ctx.pinned, spotlight: ctx.spotlight ?? [], speakerKey, opened, cid: ctx.cid, has: (k) => keys.has(k), presenting: ctx.state.presenting ?? null });
}

// ---- tiles ----------------------------------------------------------------------------------------------------------------

function reactionOf(ctx: CallCtx, user: string) {
  const r = ctx.reactions.get(user);
  if (!r) return null;
  const k = REACTIONS.find((x) => x.kind === r.kind);
  return k ? { glyph: k.glyph, word: k.word } : null;
}

const menuBtn = "grid size-7 place-items-center rounded-full bg-black/55 text-white outline-none hover:bg-black/75 focus-visible:ring-2 focus-visible:ring-primary";

/** The three-dot menu of a person tile: Pin for me; the coordinator also Spotlight for everyone. None on the room screen. */
export function TileMenu({ p }: { p: CallPerson }) {
  const ctx = useCall();
  if (ctx.variant === "room") return null;
  const pinned = ctx.pinned === p.key;
  const spot = ctx.spotlight ?? [];
  const lit = spot.includes(p.user);
  const canSpot = ctx.canManage && !p.roomScreen;
  const present = ctx.variant === "coordinator" ? presentMenuItems({ user: p.user, coordinator: ctx.me || null, canManage: ctx.canManage, allowed: ctx.state.present_allowed ?? [], presenting: ctx.state.presenting ?? null, roomScreen: p.roomScreen, defaultPresenter: ctx.state.current?.presenter?.user ?? null }) : [];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={menuBtn} aria-label={`More for ${p.name}`} title={`More for ${p.name}`} data-testid="tile-menu"><MoreVertical className="size-4" aria-hidden /></button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="truncate">{p.name}</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => ctx.setPinned(pinned ? null : p.key)} data-testid="tile-pin">
          {pinned ? <PinOff aria-hidden /> : <Pin aria-hidden />}{pinned ? "Unpin" : "Pin for me"}
        </DropdownMenuItem>
        {canSpot ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => { void ctx.actions.spotlight(spotlightToggle(spot, p.user)).catch(() => undefined); }} data-testid="tile-spotlight">
              <Sparkles aria-hidden />{lit ? "Remove from spotlight" : "Spotlight for everyone"}
            </DropdownMenuItem>
          </>
        ) : null}
        {present.length ? <DropdownMenuSeparator /> : null}
        {present.map((k) => (
          <DropdownMenuItem key={k} data-testid={`tile-present-${k}`}
            onSelect={() => { void (k === "stop" ? ctx.actions.presenting?.(false) : ctx.actions.allowPresent?.(p.user, k === "allow"))?.catch(() => undefined); }}>
            {k === "stop" ? <MonitorOff aria-hidden /> : <MonitorUp aria-hidden />}{PRESENT_ITEM_WORD[k]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function chipFor(pinned: boolean, lit: boolean, big?: boolean) {
  if (!pinned && !lit) return null;
  return (
    <>
      {pinned ? <span className={cn("inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 font-medium text-white", big ? "text-sm" : "text-[10px]")}><Pin className="size-3" aria-hidden />Pinned</span> : null}
      {lit ? <span className={cn("inline-flex items-center gap-1 rounded-full bg-primary/85 px-2 py-0.5 font-medium text-primary-foreground", big ? "text-sm" : "text-[10px]")}><Sparkles className="size-3" aria-hidden />Spotlight</span> : null}
    </>
  );
}

function LivePersonTile({ p, participant, size, big, dense, className, fit, chip }: { p: CallPerson; participant: Participant; size: TileSize; big?: boolean; dense?: boolean; className?: string; fit?: "cover" | "contain"; chip?: React.ReactNode }) {
  const ctx = useCall();
  const speaking = useSpeaking(participant);
  const micOn = micStateOf(participant);
  const quality = participant.isLocal ? ctx.video.quality : String(participant.connectionQuality);
  const pinned = ctx.pinned === p.key;
  const lit = (ctx.spotlight ?? []).includes(p.user);
  return (
    <TileFrame
      person={p} size={size} big={big} dense={dense} speaking={speaking} micOn={micOn} quality={quality} qualityMine={participant.isLocal} className={className}
      label={tileAriaLabel({ ...p, micOn, speaking, quality, pinned, spotlit: lit })}
      reaction={reactionOf(ctx, p.user)}
      menu={<TileMenu p={p} />}
      chip={chip ?? chipFor(pinned, lit, big)}
    >
      <LiveVideo participant={participant} fit={fit} />
    </TileFrame>
  );
}

/** One person tile: the LiveKit camera when the person is in the video, else the initials. */
export function CallTile({ p, size = "md", big, dense, className, fit, chip }: { p: CallPerson; size?: TileSize; big?: boolean; dense?: boolean; className?: string; fit?: "cover" | "contain"; chip?: React.ReactNode }) {
  const ctx = useCall();
  if (p.participant) return <LivePersonTile key={p.participant.identity} p={p} participant={p.participant} size={size} big={big} dense={dense} className={className} fit={fit} chip={chip} />;
  const pinned = ctx.pinned === p.key;
  const lit = (ctx.spotlight ?? []).includes(p.user);
  return (
    <TileFrame person={p} size={size} big={big} dense={dense} micOn={null} className={className}
      label={tileAriaLabel({ ...p, micOn: null, pinned, spotlit: lit })}
      reaction={reactionOf(ctx, p.user)} menu={<TileMenu p={p} />} chip={chip ?? chipFor(pinned, lit, big)} />
  );
}

/** The dashed ring of an agent per state (ready ok, preparing muted, listening indigo, thinking review, answering and speaking
 * primary, error bad). */
export const AGENT_RING: Record<string, string> = {
  ready: "border-ok/70", preparing: "border-stage-muted", listening: "border-indigo", reading_question: "border-indigo", reading: "border-indigo",
  thinking: "border-review", answering: "border-primary", speaking: "border-primary", error: "border-bad",
};


/** What "Stop" on an agent's tile stops: the answer this device plays for that agent (this device), and for the coordinator or the
 * asker the voice for everyone while the agent speaks. Null when nothing of it is being spoken. Pure. */
export function agentStopTarget(agent: Pick<AgentInfo, "role" | "state" | "question">, ctx: Pick<CallCtx, "speakingNow" | "state" | "canManage" | "me">): { question: string; everyone: boolean } | null {
  const questions = ctx.state.questions ?? [];
  const here = ctx.speakingNow && questions.find((q) => q.id === ctx.speakingNow!.question)?.role === agent.role ? ctx.speakingNow.question : null;
  const qid = here ?? (agent.state === "speaking" && agent.question ? agent.question : null);
  if (!qid) return null;
  const everyone = ctx.canManage || (!!ctx.me && questions.find((q) => q.id === qid)?.by === ctx.me);
  if (!here && !everyone) return null;
  return { question: qid, everyone };
}

/** The menu of an agent tile (three dots): Ask the agent (the Agents panel, its box focused), Stop while it speaks, Present your
 * points (disabled with the reason while the brief is prepared or has no points); the coordinator also Remove from this meeting. */
function AgentTileMenu({ agent, line }: { agent: AgentInfo; line: string }) {
  const ctx = useCall();
  const canRemove = ctx.canManage && agent.can_remove !== false;
  const canPresent = ctx.inSession && !!ctx.cid;
  const blocked = presentBlockedReason(agent);
  const stop = agentStopTarget(agent, ctx);
  const ask = () => { ctx.setPanel("agents"); window.setTimeout(() => document.getElementById(`agent-q-${agent.role}`)?.focus(), 250); };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={menuBtn} aria-label={`More for the ${line}`} title="More" data-testid="agent-tile-menu"><MoreVertical className="size-4" aria-hidden /></button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="truncate">{line}</DropdownMenuLabel>
        <DropdownMenuItem onSelect={ask} data-testid="agent-ask"><MessageSquareText aria-hidden />Ask the agent</DropdownMenuItem>
        {stop ? (
          <DropdownMenuItem onSelect={() => { ctx.stopAgentAudio(); if (stop.everyone) void ctx.actions.stopAgent(agent.role, stop.question).catch(() => undefined); }} data-testid="agent-stop">
            <Square aria-hidden />{stop.everyone ? "Stop for everyone" : "Stop on this device"}
          </DropdownMenuItem>
        ) : null}
        {canPresent ? (
          <DropdownMenuItem disabled={!!blocked} onSelect={() => { void ctx.actions.presentPoints(agent.role).catch(() => undefined); }} data-testid="agent-present">
            <Megaphone aria-hidden />
            <span className="min-w-0">
              <span className="block">Present your points</span>
              {blocked ? <span className="block text-xs text-muted-foreground" data-testid="agent-present-why">{blocked}</span> : null}
            </span>
          </DropdownMenuItem>
        ) : null}
        {canRemove ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => { void ctx.actions.setAgent(agent.role, false).catch(() => undefined); }} data-testid="agent-remove">
              <UserRoundMinus aria-hidden />Remove from this meeting
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** An AI agent in the meeting (standing in for an absent head, or called by the coordinator): dashed with a ring per state, the
 * Vaidyx mark, its title, "AI agent, support only" and its true state (with the asker's name while listening); a click opens the
 * Agents panel. Never a member of the board. */
export function AgentCallTile({ agent, big, className }: { agent: AgentInfo; big?: boolean; className?: string }) {
  const ctx = useCall();
  const reduce = useReducedMotion();
  const key = agentStateKey(agent.state);
  const word = agentStateWord(key, agent.by_name);
  const busy = agentBusy(key);
  const line = agentTitle(agent);
  const count = pointsLine(agent);
  // The first point on a big tile goes with its source and the brief's true review status and model (review 9 C, S2).
  const p0 = big && agent.brief?.status !== "preparing" ? agent.points?.[0] ?? null : null;
  const c0 = p0?.citations?.[0];
  const first = p0?.text ? `${indianDates(p0.text)}${c0 ? ` (${chipText(c0)})` : ""}` : null;
  const firstStatus = first ? pointsHeader(agent) : null;
  const interactive = ctx.variant !== "room";
  const body = (
    <>
      <motion.span animate={reduce ? {} : busy ? { scale: [1, 1.08, 1] } : { scale: 1 }} transition={busy ? { repeat: Infinity, duration: key === "thinking" || key === "preparing" ? 1.2 : 0.8 } : {}} className={cn("grid shrink-0 place-items-center rounded-full bg-stage-panel", big ? "size-14" : "size-9")} aria-hidden>
        <VaidyxIcon className={big ? "h-7" : "h-4"} />
      </motion.span>
      <span className="min-w-0 flex-1 text-left">
        <span className={cn("block truncate font-medium leading-tight text-stage-fg", big ? "text-xl" : "text-xs")} data-part="title">{line}</span>{" "}
        <span className={cn("block truncate", big ? "text-base text-stage-fg/80" : "text-[10px] text-stage-muted")}>AI agent, support only</span>{" "}
        <span className={cn("block truncate", key === "error" ? "text-bad" : "text-stage-fg", big ? "text-lg" : "text-[11px]")} aria-live="polite" data-part="state">
          <AnimatePresence mode="wait" initial={false}>
            <motion.span key={`${key}:${word}`} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} className="inline-flex items-center gap-1">{word}{busy ? <Dots /> : null}</motion.span>
          </AnimatePresence>
          {big ? <span className="text-stage-fg/80" data-part="count">{" · "}{count}</span> : null}
        </span>{" "}
        {!big ? <span className="hidden truncate text-[10px] text-stage-muted @min-[9rem]:block" data-part="count">{count}</span> : null}
        {first ? (
          <span className="block [@media(max-height:899px)]:hidden" title={`${firstStatus}: ${first}`}>
            <span className="block truncate text-xs font-semibold text-stage-fg/80" data-part="point-status">{firstStatus}</span>
            <span className="block truncate text-base text-stage-fg/80" data-part="point">{first}</span>
          </span>
        ) : null}
      </span>
    </>
  );
  // The name starts with the visible words in the same order (axe label-content-name-mismatch): the title, "AI agent, support
  // only", the state word.
  const label = agentTileLabel(line, word, count, firstStatus, first);
  return (
    <div className={cn("@container group/tile relative aspect-video overflow-hidden rounded-xl border-2 border-dashed bg-stage-raised", AGENT_RING[key] ?? "border-stage-line", className)} data-testid="agent-tile" data-agent-state={key} data-role={agent.role}>
      {interactive ? (
        <button type="button" onClick={() => ctx.setPanel("agents")} className="flex h-full w-full items-center gap-2 p-2 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary" aria-label={`${label}. Open the Agents panel`} title={`${line}: open the Agents panel`}>{body}</button>
      ) : <div className={cn("flex h-full w-full items-center gap-2", big ? "p-3" : "p-2")} role="group" aria-label={label}>{body}</div>}
      {interactive ? (
        <div className="absolute right-1.5 top-1.5 opacity-100 lg:opacity-0 lg:group-hover/tile:opacity-100 lg:group-focus-within/tile:opacity-100 [&:has([data-state=open])]:opacity-100">
          <AgentTileMenu agent={agent} line={line} />
        </div>
      ) : null}
    </div>
  );
}

/** The shared content as a tile (when a person is on the stage): what it is, and "Show" to put it back. */
export function ContentTile({ className, big }: { className?: string; big?: boolean }) {
  const ctx = useCall();
  const opened = ctx.variant === "member" && !ctx.following ? null : ctx.opened;
  const slide = ctx.slides[ctx.shownSlide];
  const sharing = ctx.state.presenting ?? null;
  const what = sharing ? `${presenterName(sharing, ctx.state.attendance ?? [], ctx.video.room)} is presenting`
    : opened?.kind === "images" ? (opened.title || "The images") : opened?.kind === "record" ? (opened.title || "A record") : slide?.title ?? (ctx.cid ? "The slides" : "The shared screen");
  const Icon = sharing ? MonitorUp : opened?.kind === "images" ? Images : MonitorPlay;
  const show = () => { ctx.setPinned(null); ctx.setLayout("auto"); };
  return (
    <div className={cn("relative flex aspect-video flex-col justify-between overflow-hidden rounded-xl border border-stage-line bg-stage-panel p-2", className)} data-testid="content-tile" role="group" aria-label={`Shared screen: ${what}`}>
      <span className={cn("inline-flex items-center gap-1 text-stage-muted", big ? "text-sm" : "text-[10px]")}><Icon className="size-3.5" aria-hidden />Shared screen</span>
      <span className={cn("line-clamp-2 font-medium text-stage-fg", big ? "text-lg" : "text-xs")}>{what}</span>
      {ctx.variant !== "room" ? (
        <button type="button" onClick={show} className="self-start rounded-full bg-primary px-2.5 py-0.5 text-[11px] font-semibold text-primary-foreground outline-none hover:bg-primary-hover focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1" aria-label={`Show ${what} on the stage`} title="Show the shared screen on the stage" data-testid="content-show">Show</button>
      ) : null}
    </div>
  );
}

/** The "Pinned" chip with an X, on the large tile on the stage. */
export function UnpinChip({ big }: { big?: boolean }) {
  const ctx = useCall();
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full bg-black/60 pl-2 font-medium text-white", big ? "text-sm" : "text-xs")}>
      <Pin className="size-3" aria-hidden />Pinned
      <button type="button" onClick={() => ctx.setPinned(null)} className="grid size-6 place-items-center rounded-full outline-none hover:bg-white/15 focus-visible:ring-2 focus-visible:ring-primary" aria-label="Unpin" title="Unpin"><X className="size-3.5" aria-hidden /></button>
    </span>
  );
}

// ---- the strip ------------------------------------------------------------------------------------------------------------

/** The room screen's column: at most `max` remote tiles in two columns, "+n more" in words, then the agents in the meeting under
 * their own heading (at most four, then "+n more"). No menus, no scroll. */
function RoomStrip({ people, agents, showContent, max, className }: { people: CallPerson[]; agents: AgentInfo[]; showContent: boolean; max: number; className?: string }) {
  const cut = roomCut(people, max - (showContent ? 1 : 0));
  const agentCut = roomCut(agents, 4);
  return (
    <div className={cn("flex min-h-0 flex-col gap-3 overflow-hidden", className)} data-testid="tile-grid" data-orientation="column" aria-label="Remote members and agents">
      {people.length || showContent ? (
        <section aria-label="Remote members" className="space-y-1.5">
          <h2 className="text-lg font-semibold text-stage-fg/80">Remote ({people.length})</h2>
          <div className="grid grid-cols-2 gap-2" role="list">
            {showContent ? <div role="listitem"><ContentTile big /></div> : null}
            {cut.shown.map((p) => <div role="listitem" key={p.key}><CallTile p={p} size="sm" big dense /></div>)}
          </div>
          {cut.more > 0 ? <p className="text-xl text-stage-fg/80" data-testid="strip-more">+{cut.more} more</p> : null}
        </section>
      ) : <p className="text-xl text-stage-fg/80">No remote members</p>}
      {agents.length ? (
        <section aria-label="AI agents in this meeting" className="space-y-1.5">
          <h2 className="text-lg font-semibold text-stage-fg/80">AI agents in this meeting</h2>
          <div className="space-y-2" role="list">
            {agentCut.shown.map((a) => <div role="listitem" key={`agent-${a.role}`}><AgentCallTile agent={a} big className="aspect-auto h-24 [@media(min-height:900px)]:h-32" /></div>)}
          </div>
          {agentCut.more > 0 ? <p className="text-xl text-stage-fg/80" data-testid="agents-more">+{agentCut.more} more</p> : null}
        </section>
      ) : null}
    </div>
  );
}

/** The participant strip: a column beside the stage (laptop; small tiles for a phone in landscape), a swipe row (phone, or while a
 * panel is open), or the room screen's column. */
export function Strip({ orientation, max, small, className }: { orientation: "row" | "column"; max?: number; small?: boolean; className?: string }) {
  const ctx = useCall();
  const people = useCallPeople();
  const agents = useCallAgents();
  const mode = useStageMode(people);
  const recent = useRecentSpeakers();
  if (!stripShownFor(mode)) return null;
  const onStage = new Set(stageKeys(mode));
  const ordered = orderBySpeakers(people.filter((p) => !onStage.has(p.key)), recent);
  const limit = max ?? (orientation === "column" ? 8 : 12);
  const showContent = onStage.size > 0;
  const room = ctx.variant === "room";
  if (room && orientation === "column") return <RoomStrip people={ordered} agents={agents} showContent={showContent} max={limit} className={className} />;
  const shownPeople = ordered.slice(0, Math.max(0, limit - agents.length));
  const hidden = ordered.length - shownPeople.length;
  const cls = orientation === "column"
    ? "scroll-thin flex min-h-0 flex-col gap-2 overflow-y-auto"
    : cn("scroll-thin flex snap-x gap-2 overflow-x-auto pb-1 [&>*]:shrink-0 [&>*]:snap-start", room ? "[&>*]:w-56" : "[&>*]:w-28 sm:[&>*]:w-40");
  if (!people.length && !agents.length) return <p className={cn("text-sm text-stage-muted", className)} data-testid="tile-grid">No one has joined yet.</p>;
  const tileSize = small ? "sm" : orientation === "column" || room ? "md" : "sm";
  return (
    <div className={cn(cls, className)} data-testid="tile-grid" data-orientation={orientation} aria-label="People in the call" role="list">
      {showContent ? <div role="listitem"><ContentTile big={room} /></div> : null}
      {shownPeople.map((p) => <div role="listitem" key={p.key}><CallTile p={p} size={tileSize} big={room} dense={small} /></div>)}
      {agents.map((a) => <div role="listitem" key={`agent-${a.role}`}><AgentCallTile agent={a} big={room} /></div>)}
      {hidden > 0 ? (
        <div role="listitem">
          {room ? <div className="grid aspect-video place-items-center rounded-xl bg-stage-raised text-sm text-stage-fg/80">+{hidden} more</div>
            : <button type="button" onClick={() => ctx.setPanel("people")} className="grid aspect-video w-full place-items-center rounded-xl bg-stage-raised text-sm text-stage-muted outline-none hover:text-stage-fg focus-visible:ring-2 focus-visible:ring-primary" aria-label={`${hidden} more people: open the People panel`} title="Open the People panel">+{hidden} more</button>}
        </div>
      ) : null}
    </div>
  );
}
