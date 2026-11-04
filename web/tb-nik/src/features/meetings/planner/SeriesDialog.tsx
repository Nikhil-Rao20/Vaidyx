// "Change the series" (meetings-v2 3.3 and 3.1): the weekday, the time and the room of the weekly Tumour Board; its future meetings
// follow (a meeting changed by hand on its own page keeps that change). Pause (no new meetings for now; the ones made stay) or Resume;
// Stop, with a plain warning of what happens: no new meetings, the future meetings with no Case File cancelled, those with Case Files kept.
import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Pause, Play, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TimeInput } from "@/components/TimeInput";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { notify } from "@/components/Toasts";
import { cn } from "@/lib/utils";
import { plural } from "@/lib/format";
import { LoadingButton, StatusChip, errorText } from "@/features/casefile/components/common";
import { pauseSeries, resumeSeries, stopSeries, updateSeries } from "../api";
import type { Series } from "./types";
import { WEEKDAYS, WEEKDAYS_SHORT } from "./util";

export function SeriesDialog({ open, onOpenChange, series, onChanged }: {
  open: boolean; onOpenChange: (o: boolean) => void; series: Series; onChanged: () => void;
}) {
  const [weekday, setWeekday] = useState(series.weekday);
  const [time, setTime] = useState(series.time);
  const [room, setRoom] = useState(series.room ?? "");
  const [stopOpen, setStopOpen] = useState(false);
  useEffect(() => { if (open) { setWeekday(series.weekday); setTime(series.time); setRoom(series.room ?? ""); } }, [open, series]);
  const stopped = series.status === "stopped";
  const paused = series.status === "paused";

  const save = useMutation({
    mutationFn: () => {
      const b: { weekday?: number; time?: string; room?: string } = {};
      if (weekday !== series.weekday) b.weekday = weekday;
      if (time !== series.time) b.time = time;
      if (room.trim() !== (series.room ?? "")) b.room = room.trim();
      return updateSeries(series.id, b);
    },
    onSuccess: (r) => {
      onOpenChange(false); onChanged();
      notify.success("The weekly series changed", `${r.series.label}. ${r.changed.length ? `${plural(r.changed.length, "future meeting")} changed with it.` : "No future meeting needed a change."}${r.cancelled.length ? ` ${plural(r.cancelled.length, "meeting")} without a new date cancelled; its Case Files went to the next meeting.` : ""}`);
    },
  });
  const pause = useMutation({
    mutationFn: () => (paused ? resumeSeries(series.id) : pauseSeries(series.id)),
    onSuccess: () => { onChanged(); notify.success(paused ? "The weekly series runs again" : "The weekly series is paused", paused ? "The next four weeks of meetings are made again." : "No new meetings are made until you resume it. The meetings already made stay."); },
  });
  const timeBad = !/^\d{2}:\d{2}$/.test(time) ? "Choose a time." : null;
  const dirty = weekday !== series.weekday || time !== series.time || room.trim() !== (series.room ?? "");
  const busy = save.isPending || pause.isPending;

  return (
    <>
      <Dialog open={open && !stopOpen} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
        <DialogContent aria-describedby="series-desc" data-testid="series-dialog" className="max-h-[calc(100dvh-2rem)] overflow-y-auto p-4 sm:max-w-lg sm:p-6">
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (!timeBad && dirty) save.mutate(); }}>
            <DialogHeader>
              <DialogTitle className="flex flex-wrap items-center gap-2">Change the weekly series {paused ? <StatusChip kind="warn">paused</StatusChip> : stopped ? <StatusChip kind="bad">stopped</StatusChip> : null}</DialogTitle>
              <DialogDescription id="series-desc">{series.label}{series.room ? `, ${series.room}` : ""}. The future meetings of the series follow a change, except a date, time or room you changed on one meeting's own page.</DialogDescription>
            </DialogHeader>
            <fieldset disabled={stopped || busy} className="space-y-3">
              <div>
                <p className="text-sm font-medium" id="series-weekday">Day of the week</p>
                <div role="radiogroup" aria-labelledby="series-weekday" className="mt-1 grid grid-cols-7 gap-1">
                  {WEEKDAYS.map((w, i) => (
                    <button key={w} type="button" role="radio" aria-checked={weekday === i} aria-label={w} onClick={() => setWeekday(i)} tabIndex={weekday === i ? 0 : -1}
                      onKeyDown={(e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); const n = (i + (e.key === "ArrowRight" ? 1 : 6)) % 7; setWeekday(n); (e.currentTarget.parentElement?.children[n] as HTMLElement | undefined)?.focus(); } }}
                      className={cn("h-9 rounded-md border text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50", weekday === i ? "border-primary bg-primary text-primary-foreground font-medium" : "border-border bg-card hover:bg-accent")}>
                      {WEEKDAYS_SHORT[i]}
                    </button>
                  ))}
                </div>
                {weekday !== series.weekday ? <p className="mt-1 text-xs text-warn">The future meetings move to {WEEKDAYS[weekday]}; their Case Files go with them.</p> : null}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label htmlFor="series-time">Time</Label><TimeInput id="series-time" value={time} onChange={setTime} wrapperClassName="mt-1" aria-invalid={!!timeBad} /></div>
                <div className="col-span-2"><Label htmlFor="series-room">Room</Label><Input id="series-room" value={room} onChange={(e) => setRoom(e.target.value)} className="mt-1" maxLength={120} placeholder="for example: Oncology seminar room, 2nd floor" /></div>
              </div>
            </fieldset>
            {save.isError ? <p role="alert" className="text-sm text-bad">{errorText(save.error)}</p> : null}
            {pause.isError ? <p role="alert" className="text-sm text-bad">{errorText(pause.error)}</p> : null}
            {stopped ? <p className="rounded-md bg-muted px-3 py-2 text-sm">This weekly series was stopped. Plan a new weekly meeting from Meetings to meet every week again.</p> : (
              <div className="flex flex-wrap gap-2 border-t border-border pt-3">
                <LoadingButton type="button" size="sm" variant="outline" loading={pause.isPending} onClick={() => pause.mutate()} data-testid="series-pause">
                  {paused ? <Play className="size-4" /> : <Pause className="size-4" />}{paused ? "Resume the series" : "Pause the series"}
                </LoadingButton>
                <Button type="button" size="sm" variant="ghost" className="text-bad hover:text-bad" onClick={() => setStopOpen(true)} data-testid="series-stop"><Square className="size-4" />Stop the series</Button>
              </div>
            )}
            <DialogFooter className="gap-2 sm:gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Close</Button>
              {stopped ? null : <LoadingButton type="submit" loading={save.isPending} loadingText="Saving" disabled={!dirty || !!timeBad} data-testid="series-save">Save the change</LoadingButton>}
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <ConfirmDialog open={stopOpen} onOpenChange={setStopOpen} destructive title="Stop the weekly series?" confirmText="Stop the series" cancelText="Keep the series" doneText="Stopped"
        text={<>No new meetings are made after this. The future meetings of the series with <b>no Case File</b> are cancelled. The meetings that <b>already have Case Files</b> stay: hold them, or cancel each on its page (its Case Files then go to the next meeting). This cannot be undone; plan a new weekly meeting to start again.</>}
        onConfirm={async () => {
          const r = await stopSeries(series.id);
          onChanged();
          notify.success("The weekly series is stopped", `${plural(r.cancelled.length, "empty meeting")} cancelled.${r.kept.length ? ` ${plural(r.kept.length, "meeting")} with Case Files kept.` : ""}`);
          onOpenChange(false);
        }} />
    </>
  );
}
