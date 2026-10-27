// The participant strip of the call (night-v3 5.1, research/04 section 6.7): the people (the admitted attendance and the
// LiveKit participants), the active speakers first after a 2 s delay so the strip does not jump, then the AI agents standing in
// for absent heads (dashed, the Vaidyx mark, never a member), then "+n more". When the stage shows a person (pin, spotlight,
// speaker) the first tile is the shared content with "Show" to put it back. Every tile has a menu: Pin for me, and for the
// coordinator Spotlight for everyone. The pure helpers at the top are checked by a small node script.
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Track, type Participant, type Room } from "livekit-client";
import type { TrackReference } from "@livekit/components-react";
import { Images, MessageSquareText, MonitorOff, MonitorPlay, MonitorUp, MoreVertical, Pin, PinOff, Sparkles, X } from "lucide-react";
import type { AgendaRow, AgentInfo, Attendee, MeetingState, Opened } from "@/lib/live";
import { identityUser, isRoomScreen, videoExtras } from "@/lib/video";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { VaidyxIcon } from "@/components/Wordmark";
import { cn } from "@/lib/utils";
import { LiveVideo, TileFrame, micStateOf, useSpeaking, type TilePerson, type TileSize } from "../components/VideoTiles";
import { useCall } from "./context";
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

/** The label of an agent tile: "Radiology, AI agent standing in". */
export function agentLine(a: Pick<AgentInfo, "label" | "department" | "department_name" | "role">): string {
  const dept = a.department_name || a.department || a.label || a.role.replace(/_/g, " ");
  return `${dept}, AI agent standing in`;
}

export function agentStateWord(state: string | undefined | null): string {
  return (state && AGENT_STATE_WORD[state]) || "Ready";
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
  if (i.layout === "spotlight") {
    const keys = i.spotlight.filter(i.has).slice(0, 3);
    if (keys.length) return { kind: "spotlight", keys };
  }
  if (i.presenting) return { kind: "share" };
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
export function presentMenuItems(i: { user: string; coordinator: string | null; canManage: boolean; allowed: string[]; presenting: string | null; roomScreen?: boolean }): Array<"allow" | "withdraw" | "stop"> {
  if (!i.canManage || i.roomScreen || !i.user || i.user === i.coordinator) return [];
  const out: Array<"allow" | "withdraw" | "stop"> = [i.allowed.includes(i.user) ? "withdraw" : "allow"];
  if (i.presenting === i.user) out.push("stop");
  return out;
}
export const PRESENT_ITEM_WORD: Record<"allow" | "withdraw" | "stop", string> = { allow: "Allow to present", withdraw: "Withdraw the right to present", stop: "Stop their share" };

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

// ---- hooks ----------------------------------------------------------------------------------------------------------------

export type CallPerson = TilePerson & { participant: Participant | null };

/** Every person tile of the call, recomputed when the attendance, the hands or the LiveKit room change. */
export function useCallPeople(): CallPerson[] {
  const { state, me, canManage, variant, video } = useCall();
  const { room, tick } = video;
  return useMemo(() => {
    const base = basePeople(state.attendance ?? [], state, { me, canManage, onlyRemote: variant === "room" });
    const parts: Participant[] = room ? [room.localParticipant, ...room.remoteParticipants.values()] : [];
    return mergePeople<Participant>(base, parts.filter((p) => !!p.identity));
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
  const present = ctx.variant === "coordinator" ? presentMenuItems({ user: p.user, coordinator: ctx.me || null, canManage: ctx.canManage, allowed: ctx.state.present_allowed ?? [], presenting: ctx.state.presenting ?? null, roomScreen: p.roomScreen }) : [];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={menuBtn} aria-label={`More for ${p.name}`} title={`More for ${p.name}`} data-testid="tile-menu"><MoreVertical className="size-4" aria-hidden /></button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56" data-theme="dark">
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

function LivePersonTile({ p, participant, size, big, className, fit, chip }: { p: CallPerson; participant: Participant; size: TileSize; big?: boolean; className?: string; fit?: "cover" | "contain"; chip?: React.ReactNode }) {
  const ctx = useCall();
  const speaking = useSpeaking(participant);
  const micOn = micStateOf(participant);
  const quality = participant.isLocal ? ctx.video.quality : String(participant.connectionQuality);
  const pinned = ctx.pinned === p.key;
  const lit = (ctx.spotlight ?? []).includes(p.user);
  return (
    <TileFrame
      person={p} size={size} big={big} speaking={speaking} micOn={micOn} quality={quality} qualityMine={participant.isLocal} className={className}
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
export function CallTile({ p, size = "md", big, className, fit, chip }: { p: CallPerson; size?: TileSize; big?: boolean; className?: string; fit?: "cover" | "contain"; chip?: React.ReactNode }) {
  const ctx = useCall();
  if (p.participant) return <LivePersonTile key={p.participant.identity} p={p} participant={p.participant} size={size} big={big} className={className} fit={fit} chip={chip} />;
  const pinned = ctx.pinned === p.key;
  const lit = (ctx.spotlight ?? []).includes(p.user);
  return (
    <TileFrame person={p} size={size} big={big} micOn={null} className={className}
      label={tileAriaLabel({ ...p, micOn: null, pinned, spotlit: lit })}
      reaction={reactionOf(ctx, p.user)} menu={<TileMenu p={p} />} chip={chip ?? chipFor(pinned, lit, big)} />
  );
}

const AGENT_RING: Record<string, string> = {
  ready: "border-ok/70", listening: "border-indigo", reading_question: "border-indigo", reading: "border-indigo",
  thinking: "border-review", answering: "border-primary", speaking: "border-primary",
};

function Dots() {
  return <span className="ml-0.5 inline-flex gap-0.5" aria-hidden>{[0, 1, 2].map((i) => <motion.span key={i} className="size-1 rounded-full bg-current" animate={{ opacity: [0.2, 1, 0.2] }} transition={{ repeat: Infinity, duration: 1, delay: i * 0.2 }} />)}</span>;
}

/** An AI agent standing in for an absent head: dashed, the Vaidyx mark, its true state; a click opens the Agents panel. */
export function AgentCallTile({ agent, big, className }: { agent: AgentInfo; big?: boolean; className?: string }) {
  const ctx = useCall();
  const reduce = useReducedMotion();
  const key = agent.state && AGENT_STATE_WORD[agent.state] ? agent.state : "ready";
  const word = agentStateWord(key);
  const busy = key !== "ready";
  const line = agentLine(agent);
  const interactive = ctx.variant !== "room";
  const body = (
    <>
      <motion.span animate={reduce ? {} : busy ? { scale: [1, 1.08, 1] } : { scale: 1 }} transition={busy ? { repeat: Infinity, duration: key === "thinking" ? 1.2 : 0.8 } : {}} className={cn("grid shrink-0 place-items-center rounded-full bg-stage-panel", big ? "size-14" : "size-9")} aria-hidden>
        <VaidyxIcon tone="white" className={big ? "h-7" : "h-4"} />
      </motion.span>
      <span className="min-w-0 text-left">
        <span className={cn("block truncate font-medium leading-tight text-stage-fg", big ? "text-lg" : "text-xs")}>{line}</span>
        <span className={cn("block truncate text-stage-muted", big ? "text-sm" : "text-[10px]")}>AI agent, support only</span>
        <span className={cn("block text-stage-fg", big ? "text-base" : "text-[11px]")} aria-live="polite">
          <AnimatePresence mode="wait" initial={false}>
            <motion.span key={key} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} className="inline-flex items-center gap-1">{word}{busy ? <Dots /> : null}</motion.span>
          </AnimatePresence>
        </span>
      </span>
    </>
  );
  const label = `${line}, AI agent, support only, ${word}`;
  return (
    <div className={cn("group/tile relative aspect-video overflow-hidden rounded-xl border-2 border-dashed bg-stage-raised", AGENT_RING[key] ?? "border-stage-line", className)} data-testid="agent-tile" data-agent-state={key} data-role={agent.role}>
      {interactive ? (
        <button type="button" onClick={() => ctx.setPanel("agents")} className="flex h-full w-full items-center gap-2 p-2 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary" aria-label={`${label}. Open the Agents panel`} title={`${line}: open the Agents panel`}>{body}</button>
      ) : <div className={cn("flex h-full w-full items-center gap-2", big ? "p-3" : "p-2")} role="group" aria-label={label}>{body}</div>}
      {interactive ? (
        <div className="absolute right-1.5 top-1.5 opacity-100 lg:opacity-0 lg:group-hover/tile:opacity-100 lg:group-focus-within/tile:opacity-100 [&:has([data-state=open])]:opacity-100">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button type="button" className={menuBtn} aria-label={`More for the ${line}`} title="More"><MoreVertical className="size-4" aria-hidden /></button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56" data-theme="dark">
              <DropdownMenuItem onSelect={() => ctx.setPanel("agents")}><MessageSquareText aria-hidden />Ask the agent</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
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

/** The participant strip: a column beside the stage (laptop) or a swipe row (phone, or while a panel is open). */
export function Strip({ orientation, max, className }: { orientation: "row" | "column"; max?: number; className?: string }) {
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
  const shownPeople = ordered.slice(0, Math.max(0, limit - agents.length));
  const hidden = ordered.length - shownPeople.length;
  const cls = orientation === "column"
    ? "scroll-thin flex min-h-0 flex-col gap-2 overflow-y-auto"
    : cn("scroll-thin flex snap-x gap-2 overflow-x-auto pb-1 [&>*]:shrink-0 [&>*]:snap-start", room ? "[&>*]:w-56" : "[&>*]:w-28 sm:[&>*]:w-40");
  if (!people.length && !agents.length) return <p className={cn("text-sm text-stage-muted", className)} data-testid="tile-grid">No one has joined yet.</p>;
  return (
    <div className={cn(cls, className)} data-testid="tile-grid" data-orientation={orientation} aria-label="People in the call" role="list">
      {showContent ? <div role="listitem"><ContentTile big={room} /></div> : null}
      {shownPeople.map((p) => <div role="listitem" key={p.key}><CallTile p={p} size={orientation === "column" || room ? "md" : "sm"} big={room} /></div>)}
      {agents.map((a) => <div role="listitem" key={`agent-${a.role}`}><AgentCallTile agent={a} big={room} /></div>)}
      {hidden > 0 ? (
        <div role="listitem">
          {room ? <div className="grid aspect-video place-items-center rounded-xl bg-stage-raised text-sm text-stage-muted">+{hidden} more</div>
            : <button type="button" onClick={() => ctx.setPanel("people")} className="grid aspect-video w-full place-items-center rounded-xl bg-stage-raised text-sm text-stage-muted outline-none hover:text-stage-fg focus-visible:ring-2 focus-visible:ring-primary" aria-label={`${hidden} more people: open the People panel`} title="Open the People panel">+{hidden} more</button>}
        </div>
      ) : null}
    </div>
  );
}
