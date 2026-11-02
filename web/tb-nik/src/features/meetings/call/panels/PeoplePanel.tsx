// The People panel of the call (night-v3 5.1, research/04 section 6.9): Waiting (the coordinator admits each or all; a member sees
// the count), In the room, Remote, Expected not here, and apart the AI agents standing in for absent heads (support only, never
// counted). Each row: initials, name, role badges, department, where, hand with its order number, microphone and camera when the
// call knows them. The coordinator's row menu spotlights a person for everyone and allows or withdraws the right to present a screen
// (night-v3 5.2), or stops a share; "may present" and "presenting" stand on the rows.
import { useMemo, useState } from "react";
import type { Room } from "livekit-client";
import { Bot, MonitorOff, MonitorUp, MoreVertical, Search, Star, StarOff, UserRoundCheck, UsersRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import type { Attendee, MeetingState } from "@/lib/live";
import { identityUser, isRoomScreen } from "@/lib/video";
import { LoadingButton, fmtDateTime } from "@/features/casefile/components/common";
import { newCode } from "../../api";
import { cn } from "@/lib/utils";
import { PanelSection, PersonRow, handOrder, usePanelAction } from "../../components/People";
import { useCall } from "../context";
import { AGENT_STATE_WORD, badgesOf, type CallCtx, type RoleBadge } from "../types";
import { PRESENT_ITEM_WORD, presentMenuItems } from "../Strip";

/** Up to three people in the spotlight (the server's cap). */
export const SPOTLIGHT_MAX = 3;

/** A person's role badges in the call: the meeting's own badges plus Coordinator for the one who runs it. */
export function personBadges(a: Attendee, s: MeetingState, opts: { me?: string; canManage?: boolean } = {}): RoleBadge[] {
  const out = badgesOf(a, s, s.presenting ?? null);
  const coordinator = (!!s.meeting.created_by && a.user === s.meeting.created_by) || (!!opts.canManage && !!opts.me && a.user === opts.me);
  if (coordinator) out.splice(a.head ? 1 : 0, 0, "coordinator");
  return out;
}

/** The people split into the panel's sections, in the attendance order; `query` filters on the name and the department. */
export function peopleSections(attendance: Attendee[], query = "") {
  const q = query.trim().toLowerCase();
  const hit = (a: Attendee) => !q || `${a.name} ${a.department_name ?? ""} ${a.department ?? ""}`.toLowerCase().includes(q);
  const inRoom = (a: Attendee) => a.status === "present" || (a.status === "remote" && a.mode === "room");
  return {
    waiting: attendance.filter((a) => a.status === "waiting" && hit(a)),
    room: attendance.filter((a) => inRoom(a) && hit(a)),
    remote: attendance.filter((a) => a.status === "remote" && a.mode !== "room" && hit(a)),
    absent: attendance.filter((a) => a.status === "absent" && hit(a)),
  };
}

/** The spotlight after adding or removing one person (null when adding would go over the cap). */
export function nextSpotlight(current: string[], user: string, on: boolean): string[] | null {
  if (!on) return current.filter((u) => u !== user);
  if (current.includes(user)) return current;
  if (current.length >= SPOTLIGHT_MAX) return null;
  return [...current, user];
}

/** The microphone and camera of a person in the call, when the LiveKit room knows them (never the room screen's identity). */
function liveMedia(room: Room | null, user: string): { mic: boolean; cam: boolean } | null {
  if (!room) return null;
  const all = [room.localParticipant, ...room.remoteParticipants.values()];
  const p = all.find((x) => !!x?.identity && !isRoomScreen(x.identity) && identityUser(x.identity) === user);
  return p ? { mic: p.isMicrophoneEnabled, cam: p.isCameraEnabled } : null;
}

/** The screen share word on a row: "presenting" for the sharer, "may present" for someone the coordinator allowed. */
export function presentWord(user: string, s: Pick<MeetingState, "presenting" | "present_allowed" | "current">): string | null {
  if (s.presenting && s.presenting === user) return "presenting";
  if (s.current?.presenter?.user === user) return "presents by default";
  if ((s.present_allowed ?? []).includes(user)) return "may present";
  return null;
}

function RowMenu({ a, ctx, busy, onSpot, onPresent }: { a: Attendee; ctx: CallCtx; busy: boolean; onSpot: (on: boolean) => void; onPresent: (k: "allow" | "withdraw" | "stop") => void }) {
  const on = ctx.spotlight.includes(a.user);
  const present = presentMenuItems({ user: a.user, coordinator: ctx.me || null, canManage: ctx.canManage, allowed: ctx.state.present_allowed ?? [], presenting: ctx.state.presenting ?? null, defaultPresenter: ctx.state.current?.presenter?.user ?? null });
  const full = !on && ctx.spotlight.length >= SPOTLIGHT_MAX;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="icon-xs" variant="ghost" className={cn("text-stage-muted hover:bg-stage-raised hover:text-stage-fg", ctx.phone && "size-11")} aria-label={`More for ${a.name}`} title={`More for ${a.name}`} disabled={busy}><MoreVertical className="size-4" /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem disabled={full} onSelect={() => onSpot(!on)} title={full ? "Up to three people can be in the spotlight" : undefined}>
          {on ? <StarOff className="size-4" /> : <Star className="size-4" />}{on ? "Remove from spotlight" : full ? "Spotlight is full (three people)" : "Spotlight for everyone"}
        </DropdownMenuItem>
        {present.length ? <DropdownMenuSeparator /> : null}
        {present.map((k) => (
          <DropdownMenuItem key={k} onSelect={() => onPresent(k)} data-testid={`row-present-${k}`}>
            {k === "stop" ? <MonitorOff className="size-4" /> : <MonitorUp className="size-4" />}{PRESENT_ITEM_WORD[k]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function PeoplePanel() {
  const ctx = useCall();
  const { state: s, me, canManage, agents, video } = ctx;
  const [query, setQuery] = useState("");
  const act = usePanelAction();
  const order = useMemo(() => handOrder(s.hands), [s.hands]);
  const groups = peopleSections(s.attendance, query);
  const allWaiting = s.attendance.filter((a) => a.status === "waiting");
  const big = s.attendance.length > 12;
  const tap = ctx.phone ? "min-h-11" : "";

  const row = (a: Attendee, opts: { admit?: boolean; menu?: boolean } = {}) => {
    const media = a.status === "present" || a.status === "remote" ? liveMedia(video.room, a.user) : null;
    const word = a.status === "present" || a.status === "remote" ? presentWord(a.user, s) : null;
    return (
      <PersonRow
        key={a.user}
        a={a}
        me={a.user === me}
        badges={personBadges(a, s, { me, canManage })}
        handNo={order.get(a.user)}
        hand={ctx.hands.has(a.user)}
        mic={media ? media.mic : null}
        cam={media ? media.cam : null}
        action={!opts.admit && word ? <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium", word === "presenting" ? "bg-primary text-primary-foreground" : "bg-stage-raised text-stage-muted")} data-testid="present-word">{word}</span> : opts.admit ? <LoadingButton size={ctx.phone ? "sm" : "xs"} className={tap} loading={act.pending === `admit:${a.user}`} disabled={!!act.pending} onClick={() => void act.run(`admit:${a.user}`, () => ctx.actions.admit(a.user))}><UserRoundCheck className="size-3" />Admit</LoadingButton> : undefined}
        menu={opts.menu && canManage && ctx.variant === "coordinator" ? <RowMenu a={a} ctx={ctx} busy={!!act.pending} onSpot={(on) => { const next = nextSpotlight(ctx.spotlight, a.user, on); if (next) void act.run(`spot:${a.user}`, () => ctx.actions.spotlight(next)); }}
          onPresent={(k) => void act.run(`present:${a.user}`, () => (k === "stop" ? ctx.actions.presenting?.(false) : ctx.actions.allowPresent?.(a.user, k === "allow")) ?? Promise.resolve())} /> : undefined}
      />
    );
  };

  // the join code during the meeting, for a latecomer (it showed on the agenda page only before the start; review finding 2)
  const codeBox = canManage && ctx.variant === "coordinator" ? (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2" data-testid="call-join-code">
      <span className="text-xs text-stage-muted">Join code</span>
      {s.code?.value ? <span className="font-mono text-base font-semibold tracking-widest text-foreground">{s.code.value.replace(/(\d{3})(\d{3})/, "$1 $2")}</span>
        : <span className="text-sm text-stage-muted">No code yet</span>}
      {s.code?.expires_at ? <span className="text-[11px] text-stage-muted">until {fmtDateTime(s.code.expires_at)}</span> : null}
      <LoadingButton size="sm" variant="outline" className="ml-auto" loading={act.pending === "code"}
        onClick={() => void act.run("code", async () => { await newCode(ctx.mid); await ctx.refresh(); })}>New code</LoadingButton>
    </div>
  ) : null;

  return (
    <div className="space-y-4">
      {codeBox}
      {big ? (
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 size-4 -translate-y-1/2 text-stage-muted" aria-hidden />
          <label htmlFor="people-search" className="sr-only">Search the people</label>
          <Input id="people-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name or department" className={cn("h-9 pl-8 text-base md:text-base", tap)} />
        </div>
      ) : null}

      {allWaiting.length ? (
        canManage ? (
          <PanelSection title="Waiting" count={allWaiting.length} tone="warn" id="pp-waiting"
            right={<LoadingButton size={ctx.phone ? "sm" : "xs"} variant="outline" className={tap} loading={act.pending === "admit-all"} loadingText="Admitting" disabled={!!act.pending} onClick={() => void act.run("admit-all", () => ctx.actions.admitAll())}><UsersRound className="size-3" />Admit all</LoadingButton>}>
            <ul className="space-y-0.5" data-testid="waiting-list">{groups.waiting.map((a) => row(a, { admit: true }))}</ul>
          </PanelSection>
        ) : (
          <p className="text-xs text-warn">{allWaiting.length === 1 ? "1 person is" : `${allWaiting.length} people are`} waiting to be admitted.</p>
        )
      ) : null}

      <PanelSection title="In the room" count={groups.room.length} id="pp-room">
        {groups.room.length ? <ul className="space-y-0.5">{groups.room.map((a) => row(a, { menu: true }))}</ul> : <p className="text-sm text-stage-muted">{query ? "No one by that name in the room." : "No one is marked as in the room."}</p>}
      </PanelSection>

      <PanelSection title="Remote" count={groups.remote.length} id="pp-remote">
        {groups.remote.length ? <ul className="space-y-0.5">{groups.remote.map((a) => row(a, { menu: true }))}</ul> : <p className="text-sm text-stage-muted">{query ? "No one by that name is remote." : "No one has joined from outside the room."}</p>}
      </PanelSection>

      {groups.absent.length ? (
        <PanelSection title="Expected, not here" count={groups.absent.length} id="pp-absent">
          <ul className="space-y-0.5 opacity-70">{groups.absent.map((a) => row(a))}</ul>
        </PanelSection>
      ) : null}

      {agents.length ? (
        <PanelSection title="Agents standing in (support only, not counted)" id="pp-agents" className="rounded-lg border border-dashed border-stage-line p-2">
          <ul className="space-y-1" aria-label="AI agents standing in">
            {agents.map((g) => (
              <li key={g.role} className="flex items-center gap-2.5 px-1 py-1" data-role={g.role}>
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-stage-raised text-stage-fg" aria-hidden><Bot className="size-4" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-stage-fg">{g.label}</span>
                  <span className="block truncate text-xs text-stage-muted">{[g.department_name, "AI agent, support only", AGENT_STATE_WORD[g.state] ?? "Ready"].filter(Boolean).join(" · ")}</span>
                </span>
                <Button size={ctx.phone ? "sm" : "xs"} variant="ghost" className={cn("text-stage-fg hover:bg-stage-raised hover:text-stage-fg", tap)} onClick={() => ctx.setPanel("agents")} aria-label={`Ask ${g.label}`}>Ask</Button>
              </li>
            ))}
          </ul>
        </PanelSection>
      ) : null}

      {act.error ? <p role="alert" className="text-xs text-bad">{act.error}</p> : null}
    </div>
  );
}
