// "Plan a Tumour Board" (meetings-v2 3.3, owner D7 and D9): one small choice, Every week (the usual board: weekday, time, room) or Once
// (an extra meeting: date, time, room), then the planner page of the (first) meeting opens. A weekly series makes its next four meetings
// at once; the agenda of each fills by itself from the Case Files sent to the board. Minutes per case and video are under More on the
// planner page. Keeps the ids of the old New meeting dialog (new-meeting-dialog, nm-date, nm-time, nm-room) for the real-mode journeys.
import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CalendarPlus, Repeat } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DateInput } from "@/components/DateInput";
import { TimeInput } from "@/components/TimeInput";
import { cn } from "@/lib/utils";
import { LoadingButton, errorText, todayIso } from "@/features/casefile/components/common";
import { createMeeting, createSeries } from "../api";
import { WEEKDAYS, WEEKDAYS_SHORT, dayAndDate, nextDates, weekdayIndex } from "./util";

type Mode = "weekly" | "once";

/** The two choices as large radio cards (a phone gets them one under the other). */
function ModeCards({ mode, onMode }: { mode: Mode; onMode: (m: Mode) => void }) {
  const card = (m: Mode, Icon: typeof Repeat, title: string, text: string) => (
    <button type="button" role="radio" aria-checked={mode === m} onClick={() => onMode(m)} data-testid={`plan-${m}`}
      onKeyDown={(e) => { if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) { e.preventDefault(); onMode(m === "weekly" ? "once" : "weekly"); } }}
      tabIndex={mode === m ? 0 : -1}
      className={cn("flex min-w-0 items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
        mode === m ? "border-primary bg-secondary" : "border-border hover:bg-accent")}>
      <span aria-hidden className={cn("mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border", mode === m ? "border-primary" : "border-border-strong")}>
        {mode === m ? <span className="size-2 rounded-full bg-primary" /> : null}
      </span>
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 font-medium text-foreground"><Icon className="size-4 text-brand" aria-hidden />{title}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">{text}</span>
      </span>
    </button>
  );
  return (
    <div role="radiogroup" aria-label="How often" className="grid gap-2 sm:grid-cols-2">
      {card("weekly", Repeat, "Every week", "The usual board, on the same day and time")}
      {card("once", CalendarPlus, "Once", "An extra meeting on one date")}
    </div>
  );
}

export function PlanDialog({ open, onOpenChange, videoAvailable, hasSeries, onPlanned }: {
  open: boolean; onOpenChange: (o: boolean) => void; videoAvailable: boolean;
  /** A weekly series runs already: the dialog starts on Once (an extra meeting is then the likely ask). */
  hasSeries: boolean;
  /** The meeting to open (the first of a new series), and what was made. */
  onPlanned: (meetingId: string | null, said: string) => void;
}) {
  const today = todayIso();
  const [mode, setMode] = useState<Mode>(hasSeries ? "once" : "weekly");
  const [date, setDate] = useState(today);
  const [weekday, setWeekday] = useState(() => Math.max(0, weekdayIndex(today)));
  const [time, setTime] = useState("14:00");
  const [room, setRoom] = useState("");
  const [touched, setTouched] = useState(false);
  useEffect(() => { if (open) { setMode(hasSeries ? "once" : "weekly"); setTouched(false); } }, [open, hasSeries]);

  const plan = useMutation({
    mutationFn: async () => {
      const r = room.trim() || undefined;
      if (mode === "once") {
        const m = await createMeeting({ date, time, room: r, video: videoAvailable });
        return { id: m.id, said: `Planned for ${dayAndDate(m.date || date)} at ${m.time || time}.` };
      }
      const res = await createSeries({ weekday, time, room: r, video: videoAvailable });
      return { id: res.made[0] ?? res.series.meetings?.[0]?.id ?? null, said: `${res.series.label}: ${res.made.length} meeting${res.made.length === 1 ? "" : "s"} planned ahead.` };
    },
    onSuccess: (r) => { onOpenChange(false); onPlanned(r.id, r.said); },
  });
  const dateBad = mode === "once" ? (!date ? "Choose a date." : date < today ? "The date is in the past." : null) : null;
  const timeBad = !/^\d{2}:\d{2}$/.test(time) ? "Choose a time." : null;
  const bad = dateBad || timeBad;
  const ahead = mode === "weekly" && !timeBad ? nextDates(weekday, time) : [];

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!plan.isPending) onOpenChange(o); }}>
      <DialogContent aria-describedby="nm-desc" data-testid="new-meeting-dialog" className="max-h-[calc(100dvh-2rem)] overflow-y-auto p-4 sm:max-w-lg sm:p-6">
        <form onSubmit={(e) => { e.preventDefault(); setTouched(true); if (!bad) plan.mutate(); }} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Plan a Tumour Board</DialogTitle>
            <DialogDescription id="nm-desc">The agenda fills by itself from the Case Files sent to the board, most urgent first. You can change it after.</DialogDescription>
          </DialogHeader>
          <ModeCards mode={mode} onMode={(m) => { setMode(m); plan.reset(); }} />
          {mode === "weekly" ? (
            <div>
              <p className="text-sm font-medium" id="nm-weekday">Day of the week</p>
              <div role="radiogroup" aria-labelledby="nm-weekday" className="mt-1 grid grid-cols-7 gap-1" data-testid="plan-weekday">
                {WEEKDAYS.map((w, i) => (
                  <button key={w} type="button" role="radio" aria-checked={weekday === i} aria-label={w} onClick={() => setWeekday(i)} tabIndex={weekday === i ? 0 : -1}
                    onKeyDown={(e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); const n = (i + (e.key === "ArrowRight" ? 1 : 6)) % 7; setWeekday(n); (e.currentTarget.parentElement?.children[n] as HTMLElement | undefined)?.focus(); } }}
                    className={cn("h-9 rounded-md border text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", weekday === i ? "border-primary bg-primary text-primary-foreground font-medium" : "border-border bg-card hover:bg-accent")}>
                    {WEEKDAYS_SHORT[i]}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-3">
            {mode === "once" ? (
              <div><Label htmlFor="nm-date">Date</Label><DateInput id="nm-date" value={date} min={today} onChange={setDate} wrapperClassName="mt-1" aria-invalid={touched && !!dateBad} />{touched && dateBad ? <p className="text-xs text-bad mt-0.5">{dateBad}</p> : null}</div>
            ) : null}
            <div><Label htmlFor="nm-time">Time</Label><TimeInput id="nm-time" value={time} onChange={setTime} wrapperClassName="mt-1" aria-invalid={touched && !!timeBad} />{touched && timeBad ? <p className="text-xs text-bad mt-0.5">{timeBad}</p> : null}</div>
            <div className="col-span-2"><Label htmlFor="nm-room">Room</Label><Input id="nm-room" value={room} onChange={(e) => setRoom(e.target.value)} placeholder="for example: Oncology seminar room, 2nd floor" className="mt-1" maxLength={120} /></div>
          </div>
          {mode === "weekly" && ahead.length ? (
            <p className="rounded-md bg-muted px-3 py-2 text-xs text-body" data-testid="plan-ahead">
              Every week on {WEEKDAYS[weekday]} at {time}. The next four are made now: {ahead.map((d) => dayAndDate(d).replace(/^\w+ /, "")).join(", ")}. Skip or move one date on its own page.
            </p>
          ) : null}
          {plan.isError ? <p role="alert" className="text-sm text-bad">{errorText(plan.error)}</p> : null}
          <DialogFooter className="gap-2 sm:gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={plan.isPending}>Cancel</Button>
            <LoadingButton type="submit" loading={plan.isPending} loadingText="Planning" data-testid="plan-submit">
              {mode === "weekly" ? <Repeat className="size-4" /> : <CalendarPlus className="size-4" />}{mode === "weekly" ? "Create the weekly meeting" : "Create the meeting"}
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
