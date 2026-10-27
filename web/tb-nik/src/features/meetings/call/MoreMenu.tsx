// The More menu of the call (research/04 section 6.8): Devices, Layout, Full screen, the agent voices for me, the shortcuts, Call by
// phone and "I am in the room" / "I am remote" for a member. A dropdown on a laptop; on a phone a bottom sheet (85 % high, a visible
// Close) that also carries what the five-button bar leaves out: reactions, the panels, the card and Leave (red, last). The phone's
// Coordinator button opens the same sheet with the coordinator's part only: the case, the timer, Previous, Next case, End case,
// the Decision form, the records, the waiting room and End meeting.
import { useContext, useState, type ReactNode } from "react";
import { Check, ChevronLeft, ChevronRight, Copy, DoorOpen, Ellipsis, Keyboard, LayoutGrid, LogOut, Maximize2, Minimize2, MonitorCheck, Pause, Phone, Play, RotateCcw, Settings2, ShieldCheck, StopCircle, Volume2, VolumeX, Vote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import type { MeetingState } from "@/lib/live";
import { useCopy } from "@/features/casefile/components/common";
import { useCall } from "./context";
import { REACTIONS, type LayoutKind, type PanelKind } from "./types";
import { ShellContext } from "./useCallState";
import { DeviceSettings } from "./DevicePopover";
import { PANEL_ICONS } from "./panels";
import { RoundButton, panelKinds, panelWord } from "./CallBar";
import { TimerBadge } from "../components/shared";
import { cn } from "@/lib/utils";

/** The room phone and the members who share theirs (no dialer in this build); today's CallButton content. */
export function CallNumbers({ s }: { s: MeetingState }) {
  const [copied, copy] = useCopy();
  const room = s.meeting.room_phone ?? s.meeting.phone ?? null;
  const people = s.attendance.filter((a) => a.phone);
  const count = (room ? 1 : 0) + people.length;
  return (
    <div className="space-y-2">
      {count === 0 ? <p className="text-sm text-muted-foreground">No phone number is shared for this meeting. Members share theirs in Settings, Profile.</p> : null}
      <ul className="space-y-1">
        {room ? <li className="flex items-center gap-2 text-sm"><span className="flex-1">Meeting room</span><a className="id text-link" href={`tel:${room}`}>{room}</a><Button size="icon-xs" variant="ghost" aria-label="Copy the number" onClick={() => void copy(room)}><Copy className="size-3" /></Button></li> : null}
        {people.map((a) => <li key={a.user} className="flex items-center gap-2 text-sm"><span className="flex-1 truncate">{a.name}</span><a className="id text-link" href={`tel:${a.phone}`}>{a.phone}</a><Button size="icon-xs" variant="ghost" aria-label={`Copy ${a.name}'s number`} onClick={() => void copy(a.phone!)}><Copy className="size-3" /></Button></li>)}
      </ul>
      {copied ? <p className="text-xs text-ok" role="status">Copied</p> : null}
    </div>
  );
}

export function phoneCount(s: MeetingState): number {
  return (s.meeting.room_phone ?? s.meeting.phone ? 1 : 0) + s.attendance.filter((a) => a.phone).length;
}

const LAYOUT_WORD: Record<LayoutKind, string> = { auto: "Auto", speaker: "Speaker", grid: "Grid", spotlight: "Spotlight" };

/** The layouts offered: Auto, Speaker and Grid on a laptop (Auto and Grid on a phone), Spotlight while one is set. */
export function layoutChoices(phone: boolean, spotlightSet: boolean): LayoutKind[] {
  const out: LayoutKind[] = phone ? ["auto", "grid"] : ["auto", "speaker", "grid"];
  if (spotlightSet) out.push("spotlight");
  return out;
}

/** A row of the phone sheet: 44 px high, an icon and a plain word. */
function SheetRow({ icon: Icon, children, onClick, tone, disabled, testId, pressed, hint }: { icon: typeof Phone; children: ReactNode; onClick: () => void; tone?: "danger"; disabled?: boolean; testId?: string; pressed?: boolean; hint?: string }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-pressed={pressed} data-testid={testId} className={cn("flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm outline-none hover:bg-stage-raised focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-40", tone === "danger" ? "bg-[#d64545] font-semibold text-white hover:bg-[#c23b3b]" : "text-stage-fg")}>
      <Icon className="size-5 shrink-0" aria-hidden /><span className="min-w-0 flex-1">{children}</span>{hint ? <span className="shrink-0 text-xs text-stage-muted">{hint}</span> : null}
      {pressed ? <Check className="size-4 shrink-0" aria-hidden /> : null}
    </button>
  );
}

function SheetHeading({ children }: { children: ReactNode }) {
  return <h3 className="px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-stage-muted">{children}</h3>;
}

/** The coordinator's part: the case, the timer, the case moves, the decision, the records, the waiting room and End meeting. */
function CoordinatorPart({ close, heading = true }: { close: () => void; heading?: boolean }) {
  const c = useCall();
  const x = useContext(ShellContext);
  const running = !!c.state.current?.timer?.running;
  const waiting = c.state.attendance.filter((a) => a.status === "waiting").length;
  const openPanel = (p: Exclude<PanelKind, null>) => { close(); c.setPanel(p); };
  return (
    <section aria-label="Coordinator">
      {heading ? <SheetHeading>Coordinator</SheetHeading> : null}
      <div className={cn("flex flex-wrap items-center gap-2 px-3 pb-2 text-sm", !heading && "pt-3")}>
        <span className="min-w-0 flex-1 truncate">{x.idx >= 0 ? `Case ${x.idx + 1} of ${c.order.length}` : "No case on the screen yet"}</span>
        <TimerBadge timer={c.state.current?.timer} />
      </div>
      <div className="flex flex-wrap items-center gap-2 px-3 pb-2">
        <label className="inline-flex items-center gap-1 text-xs text-stage-muted">minutes <Input type="number" min={1} max={60} value={x.minutes} onChange={(e) => x.setMinutes(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} className="h-9 w-16 text-base" aria-label="Minutes for this case" /></label>
        {running
          ? <Button size="sm" variant="outline" onClick={() => void c.actions.timer("stop").catch(() => {})} disabled={x.timerPending}><Pause className="size-4" />Stop</Button>
          : <Button size="sm" variant="outline" onClick={() => void c.actions.timer("start", x.minutes).catch(() => {})} disabled={x.timerPending || !c.cid}><Play className="size-4" />Start</Button>}
        <Button size="sm" variant="ghost" onClick={() => void c.actions.timer("reset", x.minutes).catch(() => {})} disabled={x.timerPending || !c.cid}><RotateCcw className="size-4" />Reset</Button>
      </div>
      <SheetRow icon={ChevronLeft} onClick={x.previous} disabled={x.idx <= 0 || x.goPending} testId="sheet-previous">Previous case</SheetRow>
      <SheetRow icon={ChevronRight} onClick={x.next} disabled={c.order.length === 0 || x.idx >= c.order.length - 1 || x.goPending} testId="sheet-next">{x.idx < 0 ? "First case" : "Next case"}</SheetRow>
      <SheetRow icon={StopCircle} onClick={() => void c.actions.endCase().catch(() => {})} disabled={!c.cid || x.endPending}>End case, ask for cards</SheetRow>
      <SheetRow icon={PANEL_ICONS.decision} onClick={() => openPanel("decision")}>Decision form</SheetRow>
      <SheetRow icon={PANEL_ICONS.case} onClick={() => openPanel("case")}>Slides, records and images</SheetRow>
      <SheetRow icon={PANEL_ICONS.people} onClick={() => openPanel("people")} hint={waiting ? `${waiting} waiting` : undefined}>People and the waiting room</SheetRow>
      <div className="px-1 pt-2"><SheetRow icon={DoorOpen} tone="danger" onClick={() => { close(); c.actions.endMeeting(); }} testId="sheet-end-meeting">End meeting</SheetRow></div>
    </section>
  );
}

/** The More menu: a dropdown on a laptop, a bottom sheet on a phone. */
export function MoreMenu({ mode = "more" }: { mode?: "more" | "coordinator" }) {
  const c = useCall();
  const x = useContext(ShellContext);
  const [devices, setDevices] = useState(false);
  const [numbers, setNumbers] = useState(false);
  const open = x.menu === mode;
  const setOpen = (o: boolean) => x.setMenu(o ? mode : null);
  const close = () => x.setMenu(null);
  const member = c.variant === "member";
  const coordinator = c.variant === "coordinator" && c.canManage;
  const spotlightSet = c.spotlight.length > 0;
  const voices = c.agentVoices;
  const phones = phoneCount(c.state);
  const presence = (m: "room" | "remote") => { if ((m === "room") !== c.inRoom) void c.actions.presence(m).catch(() => {}); };

  const dialogs = (
    <>
      <Dialog open={devices} onOpenChange={setDevices}>
        <DialogContent aria-describedby="devices-desc" data-testid="devices-dialog">
          <DialogHeader><DialogTitle>Devices</DialogTitle><DialogDescription id="devices-desc">The microphone, the speaker and the camera of this call.</DialogDescription></DialogHeader>
          <DeviceSettings />
        </DialogContent>
      </Dialog>
      <Dialog open={numbers} onOpenChange={setNumbers}>
        <DialogContent aria-describedby="numbers-desc" data-testid="call-numbers">
          <DialogHeader><DialogTitle>Call by phone</DialogTitle><DialogDescription id="numbers-desc">The meeting room and the members who share their number.</DialogDescription></DialogHeader>
          <CallNumbers s={c.state} />
        </DialogContent>
      </Dialog>
    </>
  );

  if (c.phone) {
    const trigger = mode === "coordinator"
      ? <RoundButton icon={ShieldCheck} label="Coordinator" title="The case, the timer, the decision and the waiting room" active={open} onClick={() => setOpen(!open)} testId="coordinator-sheet" aria-haspopup="dialog" aria-expanded={open} />
      : <RoundButton icon={Ellipsis} label="More" title="More options" active={open} onClick={() => setOpen(!open)} testId="more" aria-haspopup="dialog" aria-expanded={open} />;
    return (
      <>
        {trigger}
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent side="bottom" showCloseButton={false} data-theme="dark" className="max-h-[85vh] gap-0 rounded-t-2xl border-stage-line bg-stage-panel p-0 text-stage-fg" data-testid={mode === "coordinator" ? "coordinator-menu" : "more-menu"}>
            <div className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-stage-line" aria-hidden />
            <div className="flex items-center gap-2 border-b border-stage-line px-4 py-2">
              <SheetTitle className="min-w-0 flex-1 text-base text-stage-fg">{mode === "coordinator" ? "Coordinator" : "More"}</SheetTitle>
              <SheetDescription className="sr-only">{mode === "coordinator" ? "Run the meeting from here." : "More options of the call."}</SheetDescription>
              <Button size="sm" variant="ghost" onClick={close} className="min-h-11 text-stage-fg hover:bg-stage-raised hover:text-stage-fg">Close</Button>
            </div>
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-1 pb-[max(1rem,env(safe-area-inset-bottom))]">
              {mode === "coordinator" ? <CoordinatorPart close={close} heading={false} /> : (
                <>
                  {x.cardAsked ? <div className="px-1 pt-2"><SheetRow icon={Vote} onClick={() => { close(); c.actions.card(); }} testId="sheet-card">Your card on this case</SheetRow></div> : null}
                  {c.inSession && c.admitted ? (
                    <section aria-label="Reactions">
                      <SheetHeading>React</SheetHeading>
                      <ul className="flex gap-1 px-2">
                        {REACTIONS.map((r) => (
                          <li key={r.kind} className="flex-1"><button type="button" className="flex min-h-11 w-full flex-col items-center gap-0.5 rounded-lg bg-stage-raised px-1 py-1.5 text-xs text-stage-fg outline-none focus-visible:ring-2 focus-visible:ring-primary" onClick={() => { close(); void c.actions.react(r.kind).catch(() => {}); }} aria-label={`React: ${r.word}`}><span className="text-xl leading-none" aria-hidden>{r.glyph}</span>{r.word}</button></li>
                        ))}
                      </ul>
                    </section>
                  ) : null}
                  <SheetHeading>Panels</SheetHeading>
                  {panelKinds(c).filter((k) => coordinator || k !== "chat").map((k) => <SheetRow key={k} icon={PANEL_ICONS[k]} onClick={() => { close(); c.setPanel(k); }} pressed={c.panel === k} testId={`sheet-panel-${k}`}>{panelWord(k)}</SheetRow>)}
                  {coordinator ? <CoordinatorPart close={close} /> : null}
                  <SheetHeading>This device</SheetHeading>
                  {c.videoAvailable && x.joined ? <SheetRow icon={Settings2} onClick={() => setDevices(true)}>Devices</SheetRow> : null}
                  <div role="radiogroup" aria-label="Layout" className="flex gap-1 px-2 py-1">
                    {layoutChoices(true, spotlightSet).map((l) => (
                      <button key={l} type="button" role="radio" aria-checked={c.layout === l} onClick={() => c.setLayout(l)} className={cn("flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-lg px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-primary", c.layout === l ? "bg-stage-fg text-stage" : "bg-stage-raised text-stage-fg")}><LayoutGrid className="size-4" aria-hidden />{LAYOUT_WORD[l]}</button>
                    ))}
                  </div>
                  <SheetRow icon={c.fullscreen ? Minimize2 : Maximize2} onClick={c.toggleFullscreen}>{c.fullscreen ? "Leave full screen" : "Full screen"}</SheetRow>
                  <SheetRow icon={voices ? VolumeX : Volume2} onClick={() => c.setAgentVoices(!voices)}>{voices ? "Mute agent voices for me" : "Unmute agent voices"}</SheetRow>
                  <SheetRow icon={Keyboard} onClick={() => { close(); x.openShortcuts(); }}>Show shortcuts</SheetRow>
                  <SheetRow icon={Phone} onClick={() => setNumbers(true)} testId="call-button" hint={phones ? `${phones} number${phones === 1 ? "" : "s"}` : undefined}>Call by phone</SheetRow>
                  {member ? (
                    <div role="radiogroup" aria-label="Where you are" className="flex gap-1 px-2 py-1" data-testid="presence">
                      {(["room", "remote"] as const).map((m) => {
                        const on = m === "room" ? c.inRoom : !c.inRoom;
                        return <button key={m} type="button" role="radio" aria-checked={on} onClick={() => { if (!on) presence(m); }} disabled={x.presencePending || c.state.meeting.status === "closed"} className={cn("flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-lg px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-40", on ? "bg-stage-fg text-stage" : "bg-stage-raised text-stage-fg")}><MonitorCheck className="size-4" aria-hidden />{m === "room" ? "I am in the room" : "I am remote"}</button>;
                      })}
                    </div>
                  ) : null}
                  <div className="px-1 pt-3">
                    {coordinator
                      ? <SheetRow icon={LogOut} onClick={() => { close(); c.actions.leave(); }} testId="sheet-leave-controls">Leave the controls</SheetRow>
                      : <SheetRow icon={LogOut} tone="danger" onClick={() => { close(); c.actions.leave(); }} testId="sheet-leave">Leave</SheetRow>}
                  </div>
                </>
              )}
            </div>
          </SheetContent>
        </Sheet>
        {dialogs}
      </>
    );
  }

  return (
    <>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <RoundButton icon={Ellipsis} label="More" title="More options" testId="more" />
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" align="end" className="w-64" data-testid="more-menu">
          {c.videoAvailable && x.joined ? <DropdownMenuItem onSelect={() => setDevices(true)}><Settings2 />Devices</DropdownMenuItem> : null}
          <DropdownMenuLabel className="text-xs text-muted-foreground">Layout</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={c.layout} onValueChange={(v) => c.setLayout(v as LayoutKind)}>
            {layoutChoices(false, spotlightSet).map((l) => <DropdownMenuRadioItem key={l} value={l}>{LAYOUT_WORD[l]}</DropdownMenuRadioItem>)}
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={c.toggleFullscreen}>{c.fullscreen ? <Minimize2 /> : <Maximize2 />}{c.fullscreen ? "Leave full screen" : "Full screen"}<DropdownMenuShortcut>F</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuItem onSelect={() => c.setAgentVoices(!voices)}>{voices ? <VolumeX /> : <Volume2 />}{voices ? "Mute agent voices for me" : "Unmute agent voices"}</DropdownMenuItem>
          <DropdownMenuItem onSelect={x.openShortcuts}><Keyboard />Show shortcuts<DropdownMenuShortcut>?</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setNumbers(true)} data-testid="call-button" aria-label={phones ? `Call by phone (${phones} number${phones === 1 ? "" : "s"})` : "Call by phone"}><Phone />Call by phone{phones ? <DropdownMenuShortcut>{phones}</DropdownMenuShortcut> : null}</DropdownMenuItem>
          {member ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs text-muted-foreground">Tell the coordinator where you are</DropdownMenuLabel>
              <DropdownMenuRadioGroup value={c.inRoom ? "room" : "remote"} onValueChange={(v) => presence(v as "room" | "remote")} data-testid="presence">
                <DropdownMenuRadioItem value="room" disabled={x.presencePending || c.state.meeting.status === "closed"}>I am in the room</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="remote" disabled={x.presencePending || c.state.meeting.status === "closed"}>I am remote</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      {dialogs}
    </>
  );
}
