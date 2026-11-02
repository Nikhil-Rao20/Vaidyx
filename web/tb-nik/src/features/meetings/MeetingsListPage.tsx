// Meetings: the weekly series and the upcoming meetings, then the past ones. The MDT Coordinator plans with "Plan a Tumour Board": Every
// week (the usual board) or Once (an extra meeting), then the planner page of the meeting opens (meetings-v2 3.3, owner D7 and D9).
// A meeting of a weekly series says "Every week on Friday". When meetings.py is not on the server, the old board sessions show read-only.
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, ChevronRight, KeyRound, Repeat, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { notify } from "@/components/Toasts";
import { useSession } from "@/lib/session";
import { MessageButton } from "@/components/MessageButton";
import { listMeetings, listOldSessions, listSeries, notBuiltYet } from "./api";
import { EmptyState, ErrorState, NotYetState, SkeletonLines, StatusChip, fmtDate, fmtDateTime, todayIso } from "@/features/casefile/components/common";
import { MeetingStatusChip } from "./components/shared";
import { useLightForMeeting } from "@/lib/appearance";
import { PlanDialog } from "./planner/PlanDialog";
import type { PlanMeeting, Series } from "./planner/types";
import { dayAndDate, everyWeekOn } from "./planner/util";

function OldSessions() {
  const q = useQuery({ queryKey: ["old-sessions"], queryFn: listOldSessions });
  if (q.isLoading) return <SkeletonLines n={3} />;
  if (q.isError) return <ErrorState error={q.error} retry={() => void q.refetch()} compact />;
  const rows = q.data?.sessions ?? [];
  return (
    <div className="space-y-3">
      <NotYetState what="The new meeting rooms (agenda lists, join by code, live screen)" fallback="Showing the board sessions the old interface keeps, read-only. Open /tb to run one." />
      {rows.length === 0 ? <EmptyState kind="wait" title="No board sessions yet" /> : null}
      <ul className="surface divide-y divide-border">
        {rows.map((s) => (
          <li key={s.id} className="flex items-center gap-3 px-4 py-3 text-sm">
            <div className="flex-1 min-w-0">
              <p className="font-medium text-foreground">{fmtDate(s.date)}{s.title ? `, ${s.title}` : ""}</p>
              <p className="text-xs text-muted-foreground">{s.cases ?? 0} Case File{s.cases === 1 ? "" : "s"}{s.created_by ? `, created by ${s.created_by}` : ""}</p>
            </div>
            <MeetingStatusChip status={s.status} />
            <a className="text-link text-xs underline" href={`/tb#session=${encodeURIComponent(s.id)}`}>open in /tb</a>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The coordinator's weekly series in one line each, with the next meeting of each. */
function SeriesStrip({ series }: { series: Series[] }) {
  const today = todayIso();
  const shown = series.filter((x) => x.status !== "stopped");
  if (!shown.length) return null;
  return (
    <section aria-label="Weekly series" className="surface divide-y divide-border" data-testid="series-strip">
      {shown.map((x) => {
        const next = (x.meetings ?? []).filter((m) => m.status === "planned" && (m.date ?? "") >= today).sort((a, b) => `${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`))[0];
        return (
          <div key={x.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
            <Repeat className="size-4 text-brand" aria-hidden />
            <span className="font-medium text-foreground">{x.label}</span>
            {x.room ? <span className="text-muted-foreground">{x.room}</span> : null}
            {x.status === "paused" ? <StatusChip kind="warn">paused</StatusChip> : null}
            <span className="flex-1" />
            {next ? <Link className="text-link text-sm underline underline-offset-2" to={`/meetings/${next.id}`}>Next: {dayAndDate(next.date)}</Link> : <span className="text-xs text-muted-foreground">no meeting ahead</span>}
          </div>
        );
      })}
    </section>
  );
}

export default function MeetingsListPage() {
  useLightForMeeting();  // the meeting is always light (owner, 2 Nov 2026)
  const { me } = useSession();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ["meetings"], queryFn: listMeetings, retry: false, refetchInterval: 30_000 });
  const notBuilt = q.isError && notBuiltYet(q.error);
  const canManage = q.data?.can_manage ?? !!me?.roles?.coordinator;
  const seriesQ = useQuery({ queryKey: ["meeting-series"], queryFn: listSeries, enabled: canManage && !notBuilt, retry: false, staleTime: 30_000 });
  const series = seriesQ.data?.series ?? [];
  const labelOf = (m: PlanMeeting) => (m.series_id ? series.find((x) => x.id === m.series_id)?.label?.replace(/ at \d{2}:\d{2}$/, "") ?? everyWeekOn(m.date) : "");
  const rows = (q.data?.meetings ?? []) as PlanMeeting[];
  const key = (m: PlanMeeting) => `${m.date} ${m.time ?? ""}`;
  // In session first, then the planned ones by date and time.
  const rank = (m: PlanMeeting) => (m.status === "in_session" ? 0 : 1);
  const upcoming = rows.filter((m) => m.status === "planned" || m.status === "in_session").sort((a, b) => rank(a) - rank(b) || key(a).localeCompare(key(b)));
  const today = todayIso();
  const past = rows.filter((m) => m.status !== "planned" && m.status !== "in_session").sort((a, b) => key(b).localeCompare(key(a)));
  const planButton = (testId?: string) => <Button size="sm" onClick={() => setOpen(true)} data-testid={testId}><CalendarPlus className="size-4" />Plan a Tumour Board</Button>;
  return (
    <div className="space-y-4 max-w-5xl mx-auto" data-testid="meetings-page">
      <header className="flex flex-wrap items-center gap-2">
        <h1>Meetings</h1>
        <span className="flex-1" />
        {!canManage ? <MessageButton target={{ coordinator: true }} label="Message the MDT Coordinator" variant="outline" size="sm" /> : null}
        <Button asChild variant="outline" size="sm"><Link to="/meetings/join"><KeyRound className="size-4" />Join with a code</Link></Button>
        {canManage && !notBuilt ? planButton("new-meeting") : null}
      </header>
      {q.isLoading ? <div className="surface p-4"><SkeletonLines n={4} /></div> : null}
      {q.isError && !notBuilt ? <ErrorState error={q.error} retry={() => void q.refetch()} /> : null}
      {notBuilt ? <OldSessions /> : null}
      {canManage ? <SeriesStrip series={series} /> : null}
      {q.data ? (
        rows.length === 0 ? (
          <EmptyState kind="wait" title="No meetings yet" text={canManage ? "Plan the Tumour Board: every week, or once. The agenda fills by itself from the Case Files sent to the board." : "The MDT Coordinator has not planned a meeting yet."} action={canManage ? planButton() : undefined} />
        ) : (
          <div className="space-y-4">
          {([["Upcoming", upcoming], ["Past", past]] as const).map(([title, list]) => list.length ? (
          <section key={title} aria-label={title}>
          <h2 className="text-sm font-semibold text-muted-foreground mb-1.5">{title}</h2>
          <ul className="surface divide-y divide-border" data-testid={title === "Upcoming" ? "meetings-list" : "meetings-past"}>
            {list.map((m) => (
              <li key={m.id}>
                <Link to={`/meetings/${m.id}`} className="row-lift group flex items-center gap-3 px-4 py-3 text-sm rounded-md" data-testid="meeting-row" data-series={m.series_id || undefined}>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-foreground truncate">{m.title || m.room || "Tumour Board"}</p>
                    <p className="text-sm text-body">
                      {dayAndDate(m.date)}{m.time ? `, ${m.time}` : ""}{m.room && m.title ? `, ${m.room}` : ""}
                      {m.status === "planned" && m.date && m.date < today ? <span className="ml-2 rounded-md status-warn px-1.5 py-0.5 text-xs font-medium">date passed, not started</span> : null}
                    </p>
                    {m.series_id || m.status !== "cancelled" ? (
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                        {m.series_id ? <span className="inline-flex items-center gap-1 text-brand-text" data-testid="row-series"><Repeat className="size-3.5" aria-hidden />{labelOf(m)}</span> : null}
                        {m.counts && m.status !== "cancelled" ? <span>{m.counts.discussion} for discussion, {m.counts.noting} for noting{m.counts.not_ready ? `, ${m.counts.not_ready} not ready` : ""}</span> : null}
                        {m.status === "planned" ? <span>{m.agenda_sent_at ? `agenda sent ${fmtDateTime(m.agenda_sent_at)}` : "agenda not sent"}</span> : null}
                      </p>
                    ) : null}
                    {m.status === "cancelled" && m.cancelled?.reason ? <p className="text-xs text-muted-foreground">Cancelled: {m.cancelled.reason}</p> : null}
                  </div>
                  {m.video ? <Video className="size-4 text-muted-foreground" aria-label="video on" /> : null}
                  <MeetingStatusChip status={m.status} />
                  <ChevronRight className="size-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
          </section>
          ) : null)}
          </div>
        )
      ) : null}
      <PlanDialog open={open} onOpenChange={setOpen} videoAvailable={!!me?.features?.video} hasSeries={series.some((x) => x.status === "active")}
        onPlanned={(id, said) => {
          void qc.invalidateQueries({ queryKey: ["meetings"] });
          void qc.invalidateQueries({ queryKey: ["meeting-series"] });
          notify.success("Planned", said);
          if (id) nav(`/meetings/${id}`);
        }} />
    </div>
  );
}
