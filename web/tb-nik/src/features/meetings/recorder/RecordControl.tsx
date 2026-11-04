// The recorder on the meeting screens (meetings-v2 5.2, owner decision D11): NO AUDIO IS EVER KEPT; speech becomes text in memory.
// - RecordControl: the coordinator's top bar (replaces the placeholder of 2.5): Record; while on a red "Recording 3:12" with Pause and
//   Stop; while paused an amber "Paused 3:12" with Resume and Stop. The pill opens what is recorded now (each track and its speaker,
//   who is left out, the parts turned into text). Stop asks first: "Stop recording? The text so far is kept; no audio is kept."
// - RecordSheetRows: the same actions in the phone's Coordinator sheet.
// - RecordingBadge: the red "Recording: text only, no audio kept" line on every screen while on (amber while paused): the coordinator's
//   (mirrored to the room), the members' and the room screen's.
// - RecorderLine: the coordinator's quiet line under the stage when something is not recorded or a part failed.
// - RecordingNotice (notice.tsx, kept small for the join page): "This meeting is being recorded as text. No audio is kept."
import { useContext, useState, type ComponentType, type ReactNode } from "react";
import { Circle, CircleStop, Mic, Pause, Play, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { LoadingButton } from "@/features/casefile/components/common";
import { isRecording } from "@/lib/live";
import { useCall } from "../call/context";
import { ShellContext } from "../call/useCallState";
import { fmtClock } from "../components/shared";
import { STOP_CONFIRM, type Recorder } from "./useRecorder";
import { BADGE_ON, BADGE_PAUSED } from "./notice";
import { cn } from "@/lib/utils";

export { BADGE_ON, BADGE_PAUSED, JOIN_NOTICE, RecordingNotice } from "./notice";
export const RECORD_TITLE = "Record the meeting as text: speech becomes text on the hospital's server and no audio is kept";

/** The Stop confirmation. */
function StopDialog({ open, onOpenChange, rec }: { open: boolean; onOpenChange: (o: boolean) => void; rec: Recorder }) {
  const stopping = rec.busy === "stop";
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!stopping) onOpenChange(o); }}>
      <DialogContent aria-describedby="stop-rec-desc" data-testid="stop-recording-dialog" className="text-foreground">
        <DialogHeader><DialogTitle>{STOP_CONFIRM.title}</DialogTitle><DialogDescription id="stop-rec-desc">{STOP_CONFIRM.text}</DialogDescription></DialogHeader>
        <p className="text-sm text-muted-foreground">The last words still being turned into text are sent first. The discussion notes of each Case File are written from the text.</p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={stopping}>Keep recording</Button>
          <LoadingButton variant="destructive" loading={stopping} loadingText="Stopping" onClick={() => void rec.act("stop").then((ok) => { if (ok) onOpenChange(false); })} data-testid="confirm-stop-recording">Stop recording</LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** What the recorder takes now, in plain words (the pill's popover and the phone sheet). */
function RecordingDetails({ rec }: { rec: Recorder }) {
  return (
    <div className="space-y-2 text-sm" data-testid="recording-details">
      <p className="font-medium">{rec.state === "paused" ? BADGE_PAUSED : BADGE_ON}</p>
      <p className="text-xs text-muted-foreground">Speech becomes text on the hospital's server and the sound is dropped at once. Each Case File's discussion notes are written from the text, labelled AI draft, not reviewed.</p>
      {rec.state === "on" && rec.here ? (
        rec.tracks.length ? (
          <div>
            <p className="text-xs font-medium text-muted-foreground">Turned into text now</p>
            <ul className="mt-0.5 space-y-0.5" data-testid="recording-tracks">{rec.tracks.map((t) => <li key={t.key} className="flex items-center gap-1.5"><Mic className="size-3.5 text-muted-foreground" aria-hidden />{t.label}</li>)}</ul>
          </div>
        ) : <p className="text-xs">No microphone is on in this call yet.</p>
      ) : null}
      {rec.skipped.length ? <p className="text-xs text-muted-foreground">Not recorded (not admitted to the meeting): {rec.skipped.join(", ")}</p> : null}
      {rec.note ? <p className="text-xs text-warn">{rec.note}</p> : null}
      <p className="text-xs text-muted-foreground" data-testid="recording-counts">{rec.sent} part{rec.sent === 1 ? "" : "s"} sent, {rec.stored} with words{rec.failed ? `, ${rec.failed} not turned into text` : ""}.</p>
    </div>
  );
}

/** The coordinator's Record button and, once started, the recording pill with Pause or Resume and Stop. */
export function RecordControl() {
  const c = useCall();
  const x = useContext(ShellContext);
  const rec = x.recorder;
  const [confirm, setConfirm] = useState(false);
  if (!rec) return null;
  const busy = !!rec.busy && rec.busy !== "cut";
  if (rec.state === "off") {
    return (
      <Button size="sm" variant="outline" className="hidden border-stage-line bg-transparent text-stage-fg hover:bg-stage-raised hover:text-stage-fg md:inline-flex"
        onClick={() => void rec.act("start")} disabled={!c.inSession || busy} title={c.inSession ? RECORD_TITLE : "The recorder works while the meeting is in session"} aria-label="Record the meeting as text, no audio kept" data-testid="record" data-state="off">
        <Circle className="size-3.5 fill-[#d64545] text-[#d64545]" aria-hidden />{rec.busy === "start" ? "Starting" : "Record"}
      </Button>
    );
  }
  const on = rec.state === "on";
  const time = fmtClock(rec.seconds);
  const iconBtn = "grid size-8 place-items-center rounded-md text-stage-fg outline-none hover:bg-stage-raised focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-40";
  return (
    <span className="hidden items-center gap-0.5 md:inline-flex" data-testid="record-controls" data-state={rec.state}>
      <Popover>
        <PopoverTrigger asChild>
          <button type="button" className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-primary", on ? "bg-[#c23b3b] text-white hover:bg-[#ad3434]" : "bg-warn-soft text-warn hover:bg-warn/20")}
            aria-label={`${on ? "Recording" : "Recording paused"}, ${time} recorded. Text only, no audio kept. Show what is recorded`} title={on ? BADGE_ON : BADGE_PAUSED} data-testid="recording-pill" data-state={rec.state}>
            {on ? <span className="relative flex size-2"><span className="absolute inline-flex size-full animate-ping rounded-full bg-white/70 motion-reduce:animate-none" /><span className="relative inline-flex size-2 rounded-full bg-white" /></span> : <Pause className="size-3" aria-hidden />}
            {on ? "Recording" : "Paused"} <span data-testid="recording-time">{time}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-80" aria-label="The recorder">
          <RecordingDetails rec={rec} />
        </PopoverContent>
      </Popover>
      {on
        ? <button type="button" className={iconBtn} onClick={() => void rec.act("pause")} disabled={busy} aria-label="Pause recording" title="Pause recording: the last words are sent first" data-testid="record-pause"><Pause className="size-4" aria-hidden /></button>
        : <button type="button" className={iconBtn} onClick={() => void rec.act("resume")} disabled={busy} aria-label="Resume recording" title="Resume recording" data-testid="record-resume"><Play className="size-4" aria-hidden /></button>}
      <button type="button" className={iconBtn} onClick={() => setConfirm(true)} disabled={busy} aria-label="Stop recording" title="Stop recording (asks first)" data-testid="record-stop"><CircleStop className="size-4 text-bad" aria-hidden /></button>
      <StopDialog open={confirm} onOpenChange={setConfirm} rec={rec} />
    </span>
  );
}

/** The recorder in the phone's Coordinator sheet: the state, then Record, or Pause / Resume and Stop. */
export function RecordSheetRows({ row: Row }: { row: ComponentType<{ icon: typeof Circle; children: ReactNode; onClick: () => void; disabled?: boolean; testId?: string; hint?: string }> }) {
  const c = useCall();
  const x = useContext(ShellContext);
  const rec = x.recorder;
  const [confirm, setConfirm] = useState(false);
  if (!rec) return null;
  const busy = !!rec.busy && rec.busy !== "cut";
  return (
    <>
      {rec.state === "off"
        ? <Row icon={Circle} onClick={() => void rec.act("start")} disabled={!c.inSession || busy} testId="sheet-record" hint="text only">Record the meeting as text</Row>
        : (
          <>
            <p className="px-3 py-1 text-xs text-stage-muted" data-testid="sheet-recording-state">{rec.state === "on" ? BADGE_ON : BADGE_PAUSED} · {fmtClock(rec.seconds)}</p>
            {rec.state === "on"
              ? <Row icon={Pause} onClick={() => void rec.act("pause")} disabled={busy} testId="sheet-record-pause">Pause recording</Row>
              : <Row icon={Play} onClick={() => void rec.act("resume")} disabled={busy} testId="sheet-record-resume">Resume recording</Row>}
            <Row icon={CircleStop} onClick={() => setConfirm(true)} disabled={busy} testId="sheet-record-stop">Stop recording</Row>
          </>
        )}
      <StopDialog open={confirm} onOpenChange={setConfirm} rec={rec} />
    </>
  );
}

/** The red line on every screen while the recorder is on (amber while paused): the room reads it on the projector. */
export function RecordingBadge() {
  const c = useCall();
  const r = c.state.recording;
  if (!isRecording(r) || c.state.meeting.status !== "in_session") return null;
  const on = r?.state === "on";
  const room = c.variant === "room";
  return (
    <div className="flex shrink-0 justify-center border-b border-stage-line px-3 py-0.5" data-testid="recording-badge" data-state={r?.state}>
      <p role="status" className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 font-semibold", room ? "py-1 text-base lg:text-xl" : "py-0.5 text-xs", on ? "bg-[#c23b3b] text-white" : "bg-warn-soft text-warn")}>
        {on ? <span className={cn("inline-block rounded-full bg-white", room ? "size-3" : "size-2")} aria-hidden /> : <Pause className={room ? "size-4" : "size-3"} aria-hidden />}
        {on ? BADGE_ON : BADGE_PAUSED}
      </p>
    </div>
  );
}

/** The coordinator's quiet line: a part that could not be turned into text, or why a voice is not recorded now. */
export function RecorderLine() {
  const x = useContext(ShellContext);
  const rec = x.recorder;
  if (!rec || rec.state === "off") return null;
  const text = rec.error ? `Recorder: ${rec.error.replace(/\.$/, "")}.${rec.failed ? ` ${rec.failed} part${rec.failed === 1 ? "" : "s"} not turned into text.` : ""}` : rec.note;
  if (!text) return null;
  return (
    <p className={cn("flex items-center gap-2 rounded-lg px-3 py-1 text-xs", rec.error ? "bg-warn-soft text-warn" : "bg-stage-raised text-stage-muted")} role="status" data-testid="recorder-line">
      <Mic className="size-3.5 shrink-0" aria-hidden /><span className="min-w-0 flex-1">{text}</span>
      {rec.error ? <button type="button" className="rounded p-1 hover:bg-warn/10" onClick={rec.dismissError} aria-label="Dismiss the recorder message"><X className="size-3.5" /></button> : null}
    </p>
  );
}

