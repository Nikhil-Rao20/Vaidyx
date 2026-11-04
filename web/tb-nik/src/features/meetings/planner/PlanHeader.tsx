// The top of the planner (meetings-v2 3.3, owner D9): when and where. The title, the date, the time and the room are edited in place by
// the MDT Coordinator; the weekly series line ("Every week on Friday at 16:00") with "Change the series"; on the right the two steps of
// the page: Send agenda (with the time it was sent) and Start meeting (when a Case File is listed and the day has come). Members read the
// same lines without the pencils and the buttons.
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, CalendarDays, CalendarPlus, Clock, MapPin, Play, Repeat, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DateInput } from "@/components/DateInput";
import { TimeInput } from "@/components/TimeInput";
import type { LiveStatus } from "@/lib/live";
import { LoadingButton, StatusChip, fmtDateTime, todayIso } from "@/features/casefile/components/common";
import { LiveDot, MeetingStatusChip } from "../components/shared";
import { InlineField } from "./InlineField";
import { SeriesDialog } from "./SeriesDialog";
import type { PlanMeeting, Series } from "./types";
import { dayAndDate, dayHasCome, everyWeekOn } from "./util";

export interface PlanSteps {
  total: number;
  sending: boolean; onSend: () => void;
  starting: boolean; onStart: () => void;
}

export function PlanHeader({ m, canEdit, series, onSeriesChanged, onSave, liveStatus, liveDetail, steps, extra }: {
  m: PlanMeeting; canEdit: boolean;
  /** The weekly series this meeting belongs to (the coordinator reads it); undefined for a member or a one-off meeting. */
  series?: Series; onSeriesChanged: () => void;
  onSave: (fields: { title?: string; date?: string; time?: string; room?: string }) => Promise<unknown>;
  liveStatus: LiveStatus; liveDetail?: string;
  /** The coordinator's two steps (planned meetings only). */
  steps?: PlanSteps;
  extra?: ReactNode;
}) {
  const [seriesOpen, setSeriesOpen] = useState(false);
  const today = todayIso();
  const startReady = !!steps && steps.total > 0 && dayHasCome(m.date);
  const startHint = !steps ? "" : steps.total === 0 ? "Add a Case File first." : !dayHasCome(m.date) ? `Opens on the day, ${dayAndDate(m.date)}.` : "Everyone with the code can join.";
  return (
    <header className="surface p-4 sm:p-5" data-testid="plan-header">
      <p className="text-xs text-muted-foreground"><Link to="/meetings" className="inline-flex items-center gap-1 hover:underline"><ArrowLeft className="size-3" aria-hidden />Meetings</Link></p>
      <div className="mt-1.5 flex flex-col gap-4 lg:flex-row lg:items-start">
        <div className="min-w-0 flex-1 space-y-2.5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <InlineField heading label="title" value={m.title ?? ""} shown={m.title || "Tumour Board"} canEdit={canEdit} testId="plan-title"
              textClassName="text-2xl font-semibold tracking-tight text-foreground" onSave={(v) => onSave({ title: v.trim() })}
              validate={(v) => (v.trim().length > 200 ? "Keep the title to 200 characters." : null)}
              editor={(d, set, id) => <Input id={id} value={d} onChange={(e) => set(e.target.value)} maxLength={200} placeholder="Tumour Board" className="h-9 text-base" />} />
            <span className="inline-flex items-center gap-2"><MeetingStatusChip status={m.status} /><LiveDot status={liveStatus} detail={liveDetail} /></span>
          </div>
          <div className="flex flex-col gap-1.5 text-[15px] text-foreground sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-5" data-testid="plan-when">
            <InlineField label="date" icon={CalendarDays} value={m.date} shown={dayAndDate(m.date)} canEdit={canEdit && m.status === "planned"} testId="plan-date"
              onSave={(v) => onSave({ date: v })} validate={(v) => (!v ? "Choose a date." : v < today ? "That date has passed: choose today or a later date." : null)}
              editor={(d, set, id) => <DateInput id={id} value={d} onChange={set} wrapperClassName="w-44" />} />
            <InlineField label="time" icon={Clock} value={m.time ?? ""} shown={m.time || "Time not set"} canEdit={canEdit} testId="plan-time"
              onSave={(v) => onSave({ time: v })} validate={(v) => (/^\d{2}:\d{2}$/.test(v) ? null : "Choose a time.")}
              editor={(d, set, id) => <TimeInput id={id} value={d} onChange={set} wrapperClassName="w-28" />} />
            <InlineField label="room" icon={MapPin} value={m.room ?? ""} shown={m.room || <span className="text-muted-foreground">Room not set</span>} canEdit={canEdit} testId="plan-room"
              onSave={(v) => onSave({ room: v.trim() })}
              editor={(d, set, id) => <Input id={id} value={d} onChange={(e) => set(e.target.value)} maxLength={120} placeholder="for example: Seminar hall 2" className="h-9 w-full min-w-[12rem] sm:w-64" />} />
          </div>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-body" data-testid="plan-series">
            {m.series_id ? (
              <>
                <Repeat className="size-4 text-brand" aria-hidden />
                <span>{series?.label ?? everyWeekOn(m.date)}{series?.room && series.room !== m.room ? `, usually ${series.room}` : ""}</span>
                {series?.status === "paused" ? <StatusChip kind="warn">series paused</StatusChip> : series?.status === "stopped" ? <StatusChip kind="bad">series stopped</StatusChip> : null}
                {canEdit && series ? <Button size="sm" variant="link" className="h-auto px-0" onClick={() => setSeriesOpen(true)} data-testid="change-series">Change the series</Button> : null}
              </>
            ) : (
              <><CalendarPlus className="size-4 text-muted-foreground" aria-hidden /><span className="text-muted-foreground">One meeting, not weekly</span></>
            )}
          </p>
          {extra}
        </div>
        {steps ? (
          <div className="grid grid-cols-2 gap-2 lg:w-64 lg:grid-cols-1" data-testid="plan-steps">
            <div className="min-w-0">
              <LoadingButton className="w-full" variant={startReady ? "outline" : "default"} loading={steps.sending} loadingText="Sending" onClick={steps.onSend} disabled={steps.total === 0} data-testid="send-agenda">
                <Send className="size-4" />{m.agenda_sent_at ? "Send again" : "Send agenda"}
              </LoadingButton>
              <p className="mt-1 text-xs text-muted-foreground" data-testid="agenda-sent">{m.agenda_sent_at ? `Sent ${fmtDateTime(m.agenda_sent_at)}` : "Not sent yet"}</p>
            </div>
            <div className="min-w-0">
              <LoadingButton className="w-full" variant={startReady ? "default" : "outline"} loading={steps.starting} loadingText="Starting" onClick={steps.onStart} disabled={!startReady} data-testid="start-meeting"
                title={startReady ? "Starts the meeting; this page becomes the meeting screen" : startHint}>
                <Play className="size-4" />Start meeting
              </LoadingButton>
              <p className="mt-1 text-xs text-muted-foreground" data-testid="start-hint">{startHint}</p>
            </div>
          </div>
        ) : null}
      </div>
      {series && canEdit ? <SeriesDialog open={seriesOpen} onOpenChange={setSeriesOpen} series={series} onChanged={onSeriesChanged} /> : null}
    </header>
  );
}
