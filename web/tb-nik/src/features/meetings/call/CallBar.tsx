// The bottom control bar of the call (research/04 section 6.8, without Present until item 5.2). Laptop: the call group in the
// middle (member: Mic, Camera, Raise hand, Reactions, More, then Leave apart; coordinator: Mic, Camera, Raise hand, Reactions,
// Previous, Next case, Timer, End case, More, then End meeting), the side panel buttons on the right with their counts; the
// coordinator's "Leave the controls" sits at the far left, apart from End meeting. Phone: five buttons (mic, camera, hand, chat or Coordinator, more); the rest is in
// the More sheet. Every button has a name, a tooltip with its key and aria-pressed on the toggles.
import { forwardRef, useContext, useState, type ButtonHTMLAttributes } from "react";
import { Camera, CameraOff, ChevronDown, ChevronLeft, ChevronRight, Hand, LogOut, Mic, MicOff, Pause, Play, Smile, StopCircle, Vote, DoorOpen } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { BarButton, ControlBar } from "../components/Stage";
import { useCall } from "./context";
import { REACTIONS, type PanelKind } from "./types";
import { ShellContext } from "./useCallState";
import { MoreMenu } from "./MoreMenu";
import { DevicePopover } from "./DevicePopover";
import { PANEL_ICONS, panelBadge } from "./panels";
import { cn } from "@/lib/utils";

type RoundProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "title"> & {
  icon: LucideIcon; label: string; title?: string; keys?: string; active?: boolean; tone?: "default" | "danger" | "primary";
  badge?: number | string; testId?: string; compact?: boolean;
};

/** BarButton's look (components/Stage.tsx) with a ref, so it can open a menu or a popover, and aria-keyshortcuts. */
export const RoundButton = forwardRef<HTMLButtonElement, RoundProps>(function RoundButton({ icon: Icon, label, title, keys, active, tone = "default", badge, testId, compact, className, ...rest }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      title={title ?? label}
      aria-label={label}
      aria-pressed={active}
      aria-keyshortcuts={keys}
      data-testid={testId}
      {...rest}
      className={cn("group flex flex-col items-center gap-1 outline-none disabled:opacity-40", compact ? "min-w-11" : "min-w-16", className)}
    >
      <span className={cn(
        "relative grid place-items-center rounded-full transition-[background-color,transform] duration-150 group-active:scale-95 group-focus-visible:ring-2 group-focus-visible:ring-primary",
        compact ? "size-11" : "size-11",
        tone === "danger" ? "bg-[#d64545] text-white hover:bg-[#c23b3b]" : tone === "primary" ? "bg-primary text-primary-foreground hover:bg-primary-hover" : active ? "bg-stage-fg text-stage" : "bg-stage-raised text-stage-fg hover:bg-[#232d38]",
      )}>
        <Icon className="size-5" aria-hidden />
        {badge ? <span className="absolute -right-1 -top-1 min-w-5 rounded-full bg-primary px-1.5 text-center text-[11px] font-bold leading-5 text-primary-foreground" aria-hidden>{badge}</span> : null}
      </span>
      {compact ? null : <span className="whitespace-nowrap text-[11px] font-medium leading-none text-stage-muted group-hover:text-stage-fg">{label}</span>}
    </button>
  );
});

/** The small arrow beside Mic and Camera that opens the device popover (section B). */
function DeviceArrow({ kind }: { kind: "audio" | "video" }) {
  const label = kind === "audio" ? "Microphone and speaker settings" : "Camera settings";
  return (
    <DevicePopover kind={kind}>
      <button type="button" aria-label={label} title={label} className="-ml-3 mb-4 grid size-6 place-items-center self-start rounded-full border border-stage-line bg-stage-panel text-stage-fg hover:bg-stage-raised focus-visible:ring-2 focus-visible:ring-primary outline-none" data-testid={`${kind === "audio" ? "mic" : "cam"}-devices`}>
        <ChevronDown className="size-3.5" aria-hidden />
      </button>
    </DevicePopover>
  );
}

function MicCam({ arrows }: { arrows: boolean }) {
  const c = useCall();
  const v = c.video;
  const ready = v.status === "connected";
  const micLabel = c.dictating ? "Dictating" : v.micOn ? "Mute" : "Unmute";
  const micTitle = c.dictating ? "Your call microphone is off while you dictate; it comes back on after." : v.micOn ? "Turn the microphone off (Ctrl+D)" : "Turn the microphone on (Ctrl+D)";
  return (
    <>
      <div className="flex items-end">
        <RoundButton icon={v.micOn && !c.dictating ? Mic : MicOff} label={micLabel} title={micTitle} keys="Control+D" active={!v.micOn || c.dictating} onClick={() => void v.toggleMic()} disabled={!ready || c.dictating} testId="mic" />
        {arrows ? <DeviceArrow kind="audio" /> : null}
      </div>
      <div className="flex items-end">
        <RoundButton icon={v.camOn ? Camera : CameraOff} label={v.camOn ? "Camera" : "Camera off"} title={v.camOn ? "Turn the camera off (Ctrl+E)" : "Turn the camera on (Ctrl+E)"} keys="Control+E" active={!v.camOn} onClick={() => void v.toggleCam()} disabled={!ready} testId="cam" />
        {arrows ? <DeviceArrow kind="video" /> : null}
      </div>
    </>
  );
}

/** Mic and camera when joined; "Join video" when the person skipped the pre-join; nothing without video. */
function VideoButtons({ arrows }: { arrows: boolean }) {
  const c = useCall();
  const x = useContext(ShellContext);
  if (!c.videoAvailable) return null;
  if (x.joined) return <MicCam arrows={arrows} />;
  return <BarButton icon={Camera} label="Join video" title="Check your camera and microphone, then join the video" onClick={c.joinVideo} />;
}

function HandButton() {
  const c = useCall();
  const x = useContext(ShellContext);
  const raised = c.hands.has(c.me);
  return <RoundButton icon={Hand} label={raised ? "Lower" : "Raise hand"} title={raised ? "Lower hand (Ctrl+Alt+H)" : "Raise hand (Ctrl+Alt+H)"} keys="Control+Alt+H" active={raised} onClick={() => void c.actions.hand(!raised).catch(() => {})} disabled={!c.inSession || x.handPending || c.waiting || !c.admitted} testId="raise-hand" />;
}

/** A small popover of the four reactions; mine shows on my tile at once. */
export function ReactionsButton() {
  const c = useCall();
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <RoundButton icon={Smile} label="React" title="Send a reaction" disabled={!c.inSession || !c.admitted} testId="reactions" />
      </PopoverTrigger>
      <PopoverContent side="top" align="center" className="w-auto p-1.5" aria-label="Reactions">
        <ul className="flex gap-1">
          {REACTIONS.map((r) => (
            <li key={r.kind}>
              <button type="button" className="flex min-h-11 min-w-14 flex-col items-center gap-0.5 rounded-md px-2 py-1 text-xs hover:bg-muted focus-visible:ring-2 focus-visible:ring-primary outline-none" onClick={() => { setOpen(false); void c.actions.react(r.kind).catch(() => {}); }} aria-label={`React: ${r.word}`} title={r.word} data-testid={`reaction-${r.kind}`}>
                <span className="text-xl leading-none" aria-hidden>{r.glyph}</span>{r.word}
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

const PANEL_TITLE: Record<Exclude<PanelKind, null>, { label: string; title: string; keys?: string }> = {
  chat: { label: "Chat", title: "Open chat and questions to the board (Ctrl+Alt+C)", keys: "Control+Alt+C" },
  people: { label: "People", title: "Show people (Ctrl+Alt+P)", keys: "Control+Alt+P" },
  agenda: { label: "Agenda", title: "Show the agenda (Ctrl+Alt+A)", keys: "Control+Alt+A" },
  case: { label: "Case", title: "Show the case" },
  agents: { label: "Agents", title: "Show the agents" },
  decision: { label: "Decision", title: "Open the decision form" },
};
export const panelWord = (k: Exclude<PanelKind, null>) => (k === "chat" ? "Chat and questions" : PANEL_TITLE[k].label);

/** The side panels this person may open, in the bar's order. */
export function panelKinds(c: { agents: unknown[]; canManage: boolean; canRecord: boolean }): Array<Exclude<PanelKind, null>> {
  const out: Array<Exclude<PanelKind, null>> = ["chat", "people", "agenda", "case"];
  if (c.agents.length) out.push("agents");
  if (c.canManage || c.canRecord) out.push("decision");
  return out;
}

function PanelButton({ kind, compact = true }: { kind: Exclude<PanelKind, null>; compact?: boolean }) {
  const c = useCall();
  const t = PANEL_TITLE[kind];
  const badge = panelBadge(kind, c);
  const open = c.panel === kind;
  return <RoundButton icon={PANEL_ICONS[kind]} label={badge ? `${t.label} (${badge})` : t.label} title={open ? `Close ${t.label.toLowerCase()}` : t.title} keys={t.keys} active={open} badge={badge || undefined} onClick={() => c.togglePanel(kind)} compact={compact} disabled={c.waiting && kind !== "people"} testId={`panel-${kind}`} />;
}

function CardButton() {
  const c = useCall();
  const x = useContext(ShellContext);
  if (!x.cardAsked) return null;
  return <BarButton icon={Vote} label="Your card" title="Give your card on this case: agree or a concern" tone="primary" onClick={c.actions.card} testId="give-card" />;
}

function CoordinatorGroup() {
  const c = useCall();
  const x = useContext(ShellContext);
  const running = !!c.state.current?.timer?.running;
  return (
    <>
      <RoundButton icon={ChevronLeft} label="Previous" title="The previous case on the screen (P)" keys="P" onClick={x.previous} disabled={x.idx <= 0 || x.goPending} testId="previous-case" />
      <RoundButton icon={ChevronRight} label={x.idx < 0 ? "First case" : "Next case"} title={x.idx < 0 ? "Put the first case on the screen (N)" : "The next case on the screen (N)"} keys="N" tone={x.idx < 0 ? "primary" : "default"} onClick={x.next} disabled={c.order.length === 0 || x.idx >= c.order.length - 1 || x.goPending} testId="next-case" />
      <RoundButton icon={running ? Pause : Play} label={running ? "Stop timer" : "Timer"} title={running ? "Stop the case timer" : `Start the case timer (${x.minutes} minutes)`} active={running} onClick={() => void c.actions.timer(running ? "stop" : "start", running ? undefined : x.minutes).catch(() => {})} disabled={x.timerPending || !c.cid} testId="timer-button" />
      <RoundButton icon={StopCircle} label="End case" title="End the discussion and ask each board head for their card" onClick={() => void c.actions.endCase().catch(() => {})} disabled={!c.cid || x.endPending} testId="bar-end-case" />
    </>
  );
}

export function CallBar() {
  const c = useCall();
  const coordinator = c.variant === "coordinator" && c.canManage;
  const v = c.video;

  if (c.phone) {
    return (
      <footer className="flex min-h-[4.5rem] items-center justify-center gap-1 border-t border-stage-line px-2 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]" aria-label="Call controls">
        <VideoButtons arrows={false} />
        <HandButton />
        {coordinator ? <MoreMenu mode="coordinator" /> : <PanelButton kind="chat" compact={false} />}
        <MoreMenu mode="more" />
      </footer>
    );
  }

  const status = v.error ? <p role="alert" className="truncate text-xs text-[#ffb4a8]">{v.error}</p>
    : v.status === "connecting" ? <span className="text-xs text-stage-muted">Joining the video</span>
    : v.status === "connected" ? <span className="truncate text-xs text-stage-muted">Video on the hospital's server</span>
    : c.inRoom && c.variant === "member" ? <span className="truncate text-xs text-stage-muted">In the room: video stays off on this device</span> : null;
  const count = c.state.attendance.filter((a) => a.status === "present" || a.status === "remote").length;

  return (
    <ControlBar
      left={<>
        {coordinator ? <button type="button" className="mr-1 shrink-0 whitespace-nowrap rounded-md border border-stage-line px-2 py-1.5 text-sm text-stage-muted outline-none hover:bg-stage-raised hover:text-stage-fg focus-visible:ring-2 focus-visible:ring-primary" onClick={c.actions.leave} title="Back to the meetings list; the meeting goes on" data-testid="leave-controls">Leave the controls</button> : null}
        <div className="flex min-w-0 flex-col">{status}<span className="truncate text-xs text-stage-muted">{c.state.meeting.room ? `${c.state.meeting.room} · ` : ""}{count} in the meeting</span></div>
      </>}
      right={<>
        <div className="flex items-center gap-1" role="group" aria-label="Panels">{panelKinds(c).map((k) => <PanelButton key={k} kind={k} />)}</div>
      </>}
    >
      <VideoButtons arrows />
      <HandButton />
      <ReactionsButton />
      {coordinator ? <CoordinatorGroup /> : null}
      <CardButton />
      <MoreMenu mode="more" />
      <span className="w-4 shrink-0" aria-hidden />
      {coordinator
        ? <RoundButton icon={DoorOpen} label="End meeting" title="End the meeting for everyone (asks to confirm)" tone="danger" onClick={c.actions.endMeeting} testId="end-meeting" />
        : <RoundButton icon={LogOut} label="Leave" title="Leave the meeting" tone="danger" onClick={c.actions.leave} testId="leave" />}
    </ControlBar>
  );
}
