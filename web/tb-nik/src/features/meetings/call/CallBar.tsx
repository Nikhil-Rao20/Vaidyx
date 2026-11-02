// The bottom control bar of the call (research/04 section 6.8). Laptop: the call group in the middle (member: Mic, Camera, Present
// (night-v3 5.2; never on a phone, where the browser cannot capture a screen), Raise hand, Reactions, More, then Leave apart; coordinator: Mic, Camera, Raise hand, Reactions,
// Previous, Next case, Timer, End case, More, then End meeting), the side panel buttons on the right with their counts and their words
// (meetings-v2 2.5: the coordinator's panels are People, Chat, Agents and Decision; the agenda is the rail at the left); the
// coordinator's "Leave the controls" sits at the far left, apart from End meeting. Phone: five buttons (mic, camera, hand, chat or
// Coordinator, more); the rest is in the More sheet. Every button has a name, a tooltip with its key and aria-pressed on the toggles.
import { createContext, forwardRef, useContext, useState, type ButtonHTMLAttributes } from "react";
import { Camera, CameraOff, ChevronDown, ChevronLeft, ChevronRight, Hand, LogOut, Mic, MicOff, MonitorUp, Pause, Play, Smile, StopCircle, Vote, DoorOpen } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { BarButton, ControlBar } from "../components/Stage";
import { useCall } from "./context";
import { REACTIONS, type PanelKind } from "./types";
import { ShellContext, useMeetingCount } from "./useCallState";
import { MoreMenu } from "./MoreMenu";
import { DevicePopover } from "./DevicePopover";
import { PANEL_ICONS, panelBadge } from "./panels";
import { cn } from "@/lib/utils";

type RoundProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "title"> & {
  icon: LucideIcon; label: string; title?: string; keys?: string; active?: boolean; tone?: "default" | "danger" | "primary";
  badge?: number | string; testId?: string; compact?: boolean;
};

/** The coordinator's laptop bar carries the most buttons: they sit a little closer so it fits a 1366 px screen. */
const DenseBar = createContext(false);

/** BarButton's look (components/Stage.tsx) with a ref, so it can open a menu or a popover, and aria-keyshortcuts. */
export const RoundButton = forwardRef<HTMLButtonElement, RoundProps>(function RoundButton({ icon: Icon, label, title, keys, active, tone = "default", badge, testId, compact, className, ...rest }, ref) {
  const dense = useContext(DenseBar);
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
      className={cn("group relative flex flex-col items-center gap-1 outline-none disabled:opacity-40", compact ? "min-w-11" : dense ? "min-w-14" : "min-w-16", className)}
    >
      <span className={cn(
        "relative grid place-items-center rounded-full transition-[background-color,transform] duration-150 group-active:scale-95 group-focus-visible:ring-2 group-focus-visible:ring-primary",
        compact ? "size-11" : "size-11",
        tone === "danger" ? "bg-[#d64545] text-white hover:bg-[#c23b3b]" : tone === "primary" ? "bg-primary text-primary-foreground hover:bg-primary-hover" : active ? "bg-stage-fg text-stage" : "bg-stage-raised text-stage-fg hover:bg-stage-line",
      )}>
        <Icon className="size-5" aria-hidden />
      </span>
      {compact ? null : <span className="whitespace-nowrap text-[11px] font-medium leading-none text-stage-muted group-hover:text-stage-fg">{label}</span>}
      {badge ? <>{" "}<span className={cn("absolute -top-1 min-w-5 rounded-full bg-primary px-1.5 text-center text-[11px] font-bold leading-5 text-primary-foreground", compact ? "-right-1" : "right-1")}>{badge}</span></> : null}
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

/** Why Present is off for this person now, or null when they may present (pure, so it can be checked on its own). */
export function presentBlock(i: { shareOn: boolean; canPresent: boolean; connected: boolean }): string | null {
  if (i.shareOn) return null;
  if (!i.canPresent) return "Ask the MDT Coordinator to allow you to present";
  if (!i.connected) return "Join the video to present a screen";
  return null;
}

/** Present a screen (Ctrl+Alt+T), or stop. Laptop only; the shell asks once with a one-line reminder, then the browser's picker. */
function PresentButton() {
  const c = useCall();
  const x = useContext(ShellContext);
  const v = c.video;
  if (!c.videoAvailable || c.phone || !v.toggleShare) return null;
  const on = !!v.shareOn;
  const may = !!c.state.can?.present;
  const block = presentBlock({ shareOn: on, canPresent: may, connected: x.joined && v.status === "connected" });
  return (
    <RoundButton icon={MonitorUp} label={on ? "Stop presenting" : "Present"} title={on ? "Stop presenting (Ctrl+Alt+T)" : block ?? "Present a screen (Ctrl+Alt+T)"} keys="Control+Alt+T"
      active={on} tone={on ? "primary" : "default"} onClick={() => void v.toggleShare?.()} disabled={!!block} testId="present" data-may-present={String(may)} />
  );
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
  agents: { label: "Agents", title: "Show the agents" },
  decision: { label: "Decision", title: "Open the decision form" },
};
export const panelWord = (k: Exclude<PanelKind, null>) => (k === "chat" ? "Chat and questions" : PANEL_TITLE[k].label);

/** The side panels this person may open, in the bar's order. The coordinator's laptop has the agenda rail beside the Board view, so
 *  its bar leaves Agenda out (Ctrl+Alt+A still opens the panel); a phone has no rail and keeps it. */
export function panelKinds(c: { agents: unknown[]; canManage: boolean; canRecord: boolean; phone?: boolean; variant?: string }): Array<Exclude<PanelKind, null>> {
  const rail = !c.phone && c.variant === "coordinator" && c.canManage;
  const out: Array<Exclude<PanelKind, null>> = rail ? ["chat", "people"] : ["chat", "people", "agenda"];
  if (c.agents.length) out.push("agents");
  if (c.canManage || c.canRecord) out.push("decision");
  return out;
}

function PanelButton({ kind, compact = true }: { kind: Exclude<PanelKind, null>; compact?: boolean }) {
  const c = useCall();
  const t = PANEL_TITLE[kind];
  const badge = panelBadge(kind, c);
  const open = c.panel === kind;
  // the word under the button is the panel's name; its count is the bubble, and the button's name says both ("Chat 2")
  return <RoundButton icon={PANEL_ICONS[kind]} label={t.label} aria-label={badge ? `${t.label} ${badge}` : t.label} title={open ? `Close ${t.label.toLowerCase()}` : t.title} keys={t.keys} active={open} badge={badge || undefined} onClick={() => c.togglePanel(kind)} compact={compact} disabled={c.waiting && kind !== "people"} testId={`panel-${kind}`} />;
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

  const statusWords = v.error ? v.error : v.status === "connecting" ? "Joining the video" : v.status === "connected" ? "Video on the hospital's server"
    : c.inRoom && c.variant === "member" ? "In the room: video stays off on this device" : "";
  const count = useMeetingCount();
  const line = [statusWords, `${c.state.meeting.room ? `${c.state.meeting.room} · ` : ""}${count} in the meeting`].filter(Boolean).join(" · ");

  return (
    <ControlBar
      left={<>
        {coordinator ? <button type="button" className="mr-1 shrink-0 whitespace-nowrap rounded-md border border-stage-line px-2 py-1.5 text-sm text-stage-muted outline-none hover:bg-stage-raised hover:text-stage-fg focus-visible:ring-2 focus-visible:ring-primary" onClick={c.actions.leave} title="Back to the meetings list; the meeting goes on" data-testid="leave-controls">Leave the controls</button> : null}
        <p className={cn("min-w-0 truncate text-xs", v.error ? "text-bad" : "text-stage-muted")} title={line} role={v.error ? "alert" : undefined} data-testid="bar-status">{line}</p>
      </>}
      right={<>
        <div className="flex items-center gap-1" role="group" aria-label="Panels">{panelKinds(c).map((k) => <PanelButton key={k} kind={k} compact={false} />)}</div>
      </>}
    >
      <DenseBar.Provider value={coordinator}>
        <VideoButtons arrows />
        <PresentButton />
        <HandButton />
        <ReactionsButton />
        {coordinator ? <CoordinatorGroup /> : null}
        <CardButton />
        <MoreMenu mode="more" />
        <span className={cn("shrink-0", coordinator ? "w-1" : "w-4")} aria-hidden />
      </DenseBar.Provider>
      {coordinator
        ? <RoundButton icon={DoorOpen} label="End meeting" title="End the meeting for everyone (asks to confirm)" tone="danger" onClick={c.actions.endMeeting} testId="end-meeting" />
        : <RoundButton icon={LogOut} label="Leave" title="Leave the meeting" tone="danger" onClick={c.actions.leave} testId="leave" />}
    </ControlBar>
  );
}
