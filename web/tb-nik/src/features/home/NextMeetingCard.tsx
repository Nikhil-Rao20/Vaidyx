// Coordinator home: the next meeting (GET /meetings) with its counts, Send agenda and a link to the agenda; the ready
// list; the chase list (Case Files waiting on a department); past meetings.
import { Link } from "react-router-dom";
import { CalendarDays, ChevronRight, History, Hourglass, ListChecks, Send, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ActionButton";
import { DateText } from "@/components/DateText";
import { ErrorState } from "@/components/ErrorState";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useInvalidate, useMeetings, keys, notBuiltYet } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { parseDate } from "@/lib/format";
import type { Meeting } from "@/lib/types";

function SendAgenda({ meeting }: { meeting: Meeting }) {
  const invalidate = useInvalidate();
  const send = useAsyncAction(async () => {
    await api.post(`${EP.meetings}/${encodeURIComponent(meeting.id)}/send-agenda`);
    notify.success(meeting.agenda_sent_at ? "Agenda sent again" : "Agenda sent", "The members are told in the app.");
    void invalidate(keys.meetings);
  }, { onError: (m) => notify.error("Could not send the agenda", m) });
  const empty = meeting.counts ? meeting.counts.discussion + meeting.counts.noting === 0 : false;
  return (
    <ActionButton type="button" size="sm" variant={meeting.agenda_sent_at ? "outline" : "default"} state={send.state} doneText="Sent" loadingText="Sending" disabled={empty} title={empty ? "Add Case Files to the agenda first" : undefined} onClick={() => void send.run()} icon={<Send className="size-4" aria-hidden />}>
      {meeting.agenda_sent_at ? "Send again" : "Send agenda"}
    </ActionButton>
  );
}

export function NextMeetingCard({ readyCount, waitingCount = 0 }: { readyCount: number; waitingCount?: number }) {
  const meetings = useMeetings();
  if (meetings.error && notBuiltYet(meetings.error)) return null;
  const today = new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
  const all = meetings.data?.meetings ?? [];
  const next = all
    .filter((m) => m.status !== "closed" && (parseDate(m.date) ?? today) >= today)
    .sort((a, b) => (parseDate(a.date)?.getTime() ?? 0) - (parseDate(b.date)?.getTime() ?? 0))[0];
  const past = all.filter((m) => m.status === "closed").length;
  return (
    <section aria-label="Next meeting" className="mb-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      <div className="surface p-4 md:col-span-2 xl:col-span-1">
        <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground"><CalendarDays className="size-4" aria-hidden /> Next meeting</p>
        {meetings.isLoading && !meetings.data ? (
          <div className="mt-3 space-y-2" aria-busy="true"><div className="skeleton-line h-5 w-1/2" /><div className="skeleton-line h-4 w-2/3" /></div>
        ) : meetings.error && !meetings.data ? (
          <ErrorState compact error={meetings.error} what="meetings" onRetry={() => void meetings.refetch()} retrying={meetings.isFetching} />
        ) : next ? (
          <>
            <p className="mt-2 text-lg font-bold"><DateText value={next.date} mode="words" />{next.time ? `, ${next.time}` : ""}</p>
            <p className="text-sm text-muted-foreground">
              {next.room ? `${next.room}. ` : ""}{next.counts ? `${next.counts.discussion} for discussion, ${next.counts.noting} for noting${next.counts.not_ready ? `, ${next.counts.not_ready} not ready` : ""}.` : ""}
              {next.video ? <span className="ml-1 inline-flex items-center gap-1"><Video className="size-3.5" aria-hidden /> video</span> : null}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{next.agenda_sent_at ? <>Agenda sent <DateText value={next.agenda_sent_at} mode="ago" /></> : "Agenda not sent yet"}{next.status === "in_session" ? ", in session now" : ""}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button type="button" size="sm" variant={next.agenda_sent_at ? "default" : "outline"} asChild>
                <Link to={`/meetings/${encodeURIComponent(next.id)}`}>Open the agenda <ChevronRight className="size-4" aria-hidden /></Link>
              </Button>
              {next.status === "planned" && meetings.data?.can_manage !== false ? <SendAgenda meeting={next} /> : null}
            </div>
          </>
        ) : (
          <>
            <p className="mt-2 text-sm text-muted-foreground">No meeting planned yet.</p>
            <Button type="button" size="sm" variant="outline" className="mt-3" asChild><Link to="/meetings">Plan a meeting</Link></Button>
          </>
        )}
      </div>
      <div className="surface p-4">
        <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground"><ListChecks className="size-4" aria-hidden /> Ready for the board</p>
        <p className="mt-2 text-3xl font-bold tabular-nums">{readyCount}</p>
        <p className="text-sm text-muted-foreground">Marked ready by their owners and not yet on an agenda.</p>
        <Button type="button" size="sm" variant="outline" className="mt-3" asChild>
          <Link to="/home?status=ready#cases">Show the ready list</Link>
        </Button>
      </div>
      <div className="surface p-4">
        <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground"><Hourglass className="size-4" aria-hidden /> Chase list</p>
        <p className="mt-2 text-3xl font-bold tabular-nums">{waitingCount}</p>
        <p className="text-sm text-muted-foreground">Waiting on a department's record before the board.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" asChild><Link to="/home?status=waiting_department#cases">Show them</Link></Button>
          <Button type="button" size="sm" variant="ghost" asChild><Link to="/meetings"><History className="size-4" aria-hidden /> Past meetings{past ? ` (${past})` : ""}</Link></Button>
        </div>
      </div>
    </section>
  );
}
