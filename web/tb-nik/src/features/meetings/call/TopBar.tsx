// The top bar of the call: the Vaidyx mark, "Tumour Board · DD/MM/YYYY HH:MM" ("Conducting · ..." for the coordinator), the case
// headline ("3 of 8: patient line") and the board question, the case timer (the coordinator opens its controls from it), the presenter
// and quorum chips when the server sends them, the live-channel dot, the video chip and, for the coordinator, the room screen link.
import { useContext } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, MonitorUp, Pause, Play, RotateCcw, Signal, SignalHigh, SignalLow, SignalMedium, Users, Video, VideoOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { fmtDate } from "@/features/casefile/components/common";
import { StageTopBar } from "../components/Stage";
import { LiveDot, TimerBadge } from "../components/shared";
import { useCall } from "./context";
import type { CallCtx } from "./types";
import { ShellContext } from "./useCallState";
import { cn } from "@/lib/utils";

/** "Tumour Board · 27/10/2026 16:00" (the coordinator: "Conducting · ..."), with the room when asked. */
export function meetingLine(c: Pick<CallCtx, "state" | "variant">, withRoom = false): string {
  const m = c.state.meeting;
  const lead = c.variant === "coordinator" ? "Conducting" : "Tumour Board";
  return `${lead} · ${fmtDate(m.date)}${m.time ? ` ${m.time}` : ""}${withRoom && m.room ? ` · ${m.room}` : ""}`;
}

/** The headline: "3 of 8: patient line", or what the meeting is doing when no case is on the screen. */
export function headlineOf(c: Pick<CallCtx, "state" | "variant" | "order" | "row" | "cid">): string {
  if (c.row) {
    const i = c.order.findIndex((r) => r.case_id === c.cid);
    return i >= 0 ? `${i + 1} of ${c.order.length}: ${c.row.patient_line || c.row.case_id}` : c.row.patient_line || c.row.case_id;
  }
  const st = c.state.meeting.status;
  if (c.variant === "coordinator") return "No case on the screen yet: pick one from the agenda or press Next case.";
  if (st === "planned") return c.variant === "room" ? "Waiting for the coordinator to start" : "The meeting has not started";
  if (st === "closed") return c.variant === "room" ? "Meeting closed" : "The meeting is closed";
  if (st === "cancelled") return c.variant === "room" ? "Meeting cancelled" : "The meeting was cancelled";
  return c.variant === "room" ? "No case on the screen yet" : "Waiting for the first case";
}

const QUALITY_WORD: Record<string, string> = { excellent: "excellent", good: "good", poor: "poor", lost: "lost" };

/** The video chip: the call's state and the link quality in words (never colour alone). */
export function videoWords(status: string, quality?: string): string {
  const q = quality && QUALITY_WORD[quality] ? `, connection ${QUALITY_WORD[quality]}` : "";
  if (status === "connected") return `Video on${q}`;
  if (status === "connecting") return "Joining the video";
  if (status === "reconnecting") return "Video reconnecting";
  if (status === "disconnected") return "Video disconnected";
  if (status === "failed") return "Video failed";
  return "";
}

function VideoChip() {
  const c = useCall();
  const v = c.video;
  const words = videoWords(v.status, v.quality);
  if (!words) return null;
  const Bars = v.status !== "connected" ? VideoOff : v.quality === "excellent" ? SignalHigh : v.quality === "good" ? SignalMedium : v.quality === "poor" ? SignalLow : v.quality === "lost" ? Signal : Video;
  const bad = v.status !== "connected" || v.quality === "poor" || v.quality === "lost";
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs", bad ? "bg-warn/20 text-[#ffd48a]" : "bg-stage-raised text-stage-muted")} role="status" aria-label={words} title={words} data-testid="video-chip" data-video-status={v.status}>
      <Bars className="size-3.5" aria-hidden /><span className="hidden xl:inline">{words}</span>
    </span>
  );
}

function TimerControl() {
  const c = useCall();
  const x = useContext(ShellContext);
  const t = c.state.current?.timer;
  const running = !!t?.running;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-stage-fg outline-none hover:bg-stage-raised focus-visible:ring-2 focus-visible:ring-primary" aria-label="The case timer: start, stop, reset and the minutes" title="The case timer: start, stop, reset and the minutes" data-testid="timer-menu">
          <TimerBadge timer={t} /><ChevronDown className="size-3.5 text-stage-muted" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 space-y-3" aria-label="Case timer">
        <p className="text-sm font-medium">Case timer</p>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">Minutes for this case <Input type="number" min={1} max={60} value={x.minutes} onChange={(e) => x.setMinutes(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} className="h-8 w-16 text-sm" aria-label="Minutes for this case" /></label>
        <div className="flex flex-wrap gap-2">
          {running
            ? <Button size="sm" variant="outline" onClick={() => void c.actions.timer("stop").catch(() => {})} disabled={x.timerPending}><Pause className="size-4" />Stop</Button>
            : <Button size="sm" variant="outline" onClick={() => void c.actions.timer("start", x.minutes).catch(() => {})} disabled={x.timerPending || !c.cid}><Play className="size-4" />Start</Button>}
          <Button size="sm" variant="ghost" onClick={() => void c.actions.timer("reset", x.minutes).catch(() => {})} disabled={x.timerPending || !c.cid}><RotateCcw className="size-4" />Reset</Button>
        </div>
        {!c.cid ? <p className="text-xs text-muted-foreground">Put a case on the screen first.</p> : null}
      </PopoverContent>
    </Popover>
  );
}

export function TopBar() {
  const c = useCall();
  const s = c.state;
  const room = c.variant === "room";
  const coordinator = c.variant === "coordinator" && c.canManage;
  const presenter = s.current?.presenter;
  const q = s.quorum;
  const headline = headlineOf(c);
  const question = c.row?.board_question;

  return (
    <StageTopBar
      left={<span className={cn("text-stage-muted", room ? "text-sm" : "hidden text-sm sm:inline")}>{meetingLine(c, room || coordinator)}</span>}
      center={(
        <div className="min-w-0">
          {room ? <h1 className="truncate text-xl text-stage-fg lg:text-2xl">{headline}</h1> : <p className="truncate text-sm font-semibold text-stage-fg" data-testid="case-headline">{headline}</p>}
          {question ? <p className={cn("truncate text-stage-muted", room ? "text-sm lg:text-base" : "text-xs")}><span className="text-stage-muted/80">Board question: </span><span className="text-stage-fg/90">{question}</span></p>
            : coordinator && c.row ? <p className="truncate text-xs text-stage-muted">The board question is not written on this Case File</p> : null}
        </div>
      )}
      right={(
        <>
          {coordinator ? <TimerControl /> : <TimerBadge timer={s.current?.timer} big={room} />}
          {presenter ? <span className={cn("hidden items-center gap-1 rounded-full bg-stage-raised px-2 py-0.5 text-stage-fg lg:inline-flex", room ? "text-sm" : "text-xs")} data-testid="presenter-chip">Presenter: {presenter.name}{presenter.department_name || presenter.department ? ` (${presenter.department_name ?? presenter.department})` : ""}</span> : null}
          {q ? <span className={cn("hidden items-center gap-1 rounded-full bg-stage-raised px-2 py-0.5 text-stage-fg md:inline-flex", room ? "text-sm" : "text-xs")} title="Heads of the board present as people; AI agents never count" data-testid="quorum-chip"><Users className="size-3.5" aria-hidden />Heads {q.present} of {q.total}</span> : null}
          <LiveDot status={c.liveStatus} detail={c.liveDetail} className={c.phone && !room ? "hidden" : undefined} />
          {room ? null : <VideoChip />}
          {coordinator ? <Button asChild size="sm" variant="ghost" className="hidden text-stage-fg hover:bg-stage-raised hover:text-stage-fg md:inline-flex"><Link to={`/meetings/${c.mid}/room`} target="_blank" rel="noopener" title="Opens the full-screen room screen in a new tab, for the room computer"><MonitorUp className="size-4" />Room screen</Link></Button> : null}
        </>
      )}
    />
  );
}
