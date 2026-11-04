// /meetings/:id. The MDT Coordinator: the one-page planner while the meeting is planned (meetings-v2 3.3, planner/Planner.tsx), the
// meeting screen while it is in session (ControlView). Everyone else, and every meeting that is closed or cancelled: the read view (when
// and where, the series line, the agenda without its controls, the members, the meeting PDF for the admitted members and the coordinator).
// The old board session shows read-only when the new route is not on the server.
import { useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, KeyRound, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/session";
import { useMeetingLive, type LiveEvent } from "@/lib/live";
import { getOldSession } from "./api";
import { ControlView } from "./components/ControlView";
import { MeetingStatusChip } from "./components/shared";
import { EmptyState, ErrorState, NotYetState, SkeletonLines, fmtDate } from "@/features/casefile/components/common";
import { useLightForMeeting } from "@/lib/appearance";
import { Planner } from "./planner/Planner";
import { PlanHeader } from "./planner/PlanHeader";
import { PlanLists } from "./planner/PlanLists";
import { MembersCard, PdfCard } from "./planner/PlanSide";
import type { PlanState } from "./planner/types";
import { useCancerLabel } from "./planner/util";

function OldSessionView({ sid }: { sid: string }) {
  const q = useQuery({ queryKey: ["old-session", sid], queryFn: () => getOldSession(sid), retry: false });
  if (q.isLoading) return <SkeletonLines n={4} />;
  if (q.isError) return <ErrorState error={q.error} retry={() => void q.refetch()} />;
  const s = q.data!.session;
  return (
    <div className="space-y-3" data-testid="old-session">
      <NotYetState what="The new meeting page" fallback="This is the old board session, read-only. Run it from /tb." />
      <div className="surface p-4">
        <h1>{fmtDate(s.date)}{s.title ? `, ${s.title}` : ""}</h1>
        <div className="mt-1"><MeetingStatusChip status={s.status} /></div>
        <ol className="mt-3 space-y-1 text-sm list-decimal pl-5">{(s.agenda ?? []).map((a) => <li key={a.case_id}><Link className="text-link underline" to={`/cases/${a.case_id}`}>{a.case_id}</Link>{a.owner_ready ? " (ready)" : ""}</li>)}</ol>
      </div>
    </div>
  );
}

export default function MeetingAgendaPage() {
  useLightForMeeting();  // the meeting is always light (owner, 2 Nov 2026)
  const { id = "" } = useParams();
  const { me } = useSession();
  const controlEvents = useRef<((ev: LiveEvent) => void) | null>(null);  // the control view's shell takes every event in order
  const live = useMeetingLive(id, { onEvent: (ev) => controlEvents.current?.(ev) });
  const cancer = useCancerLabel();

  if (live.notBuilt) return <div className="max-w-4xl mx-auto"><OldSessionView sid={id} /></div>;
  if (live.isLoading) return <div className="max-w-5xl mx-auto space-y-3" aria-busy="true"><div className="skeleton-line h-8 w-1/3" /><div className="surface p-4"><SkeletonLines n={5} /></div></div>;
  const s = live.state as PlanState | null;
  if (!s) {
    return (
      <div className="max-w-xl mx-auto py-8">
        {live.missing ? <EmptyState title="This meeting does not exist" text="The link may be old, or the meeting was removed." action={<Button asChild variant="outline"><Link to="/meetings"><ArrowLeft className="size-4" />All meetings</Link></Button>} />
          : live.forbidden ? <EmptyState title="You are not on this meeting" text="Join with the 6-digit code from the MDT Coordinator; you wait until they admit you." action={<Button asChild><Link to="/meetings/join"><KeyRound className="size-4" />Join with a code</Link></Button>} />
          : <ErrorState error={live.error} retry={() => void live.refresh()} />}
      </div>
    );
  }

  const canManage = !!(s.can?.manage ?? me?.roles?.coordinator);
  const status = s.meeting.status;
  const inSession = status === "in_session";
  const closed = status === "closed";
  const cancelled = status === "cancelled";
  const amIn = s.me?.status === "present" || s.me?.status === "remote";

  if (inSession && canManage) {
    return (
      <div className="max-w-6xl mx-auto" data-testid="meeting-page" data-meeting-status={status}>
        <ControlView mid={id} state={live.state!} onChanged={() => void live.refresh()} liveStatus={live.status} liveDetail={live.statusDetail} lastEvent={live.lastEvent} events={controlEvents} />
      </div>
    );
  }
  if (canManage && status === "planned") {
    return <Planner mid={id} state={s} setState={live.setState} refresh={() => live.refresh()} liveStatus={live.status} liveDetail={live.statusDetail} />;
  }

  // The read view: members before and during the meeting; everyone (the coordinator too) after it or when it was cancelled.
  const mayPdf = (canManage || amIn) && !cancelled && !me?.roles?.outside_expert;
  return (
    <div className="space-y-4 max-w-6xl mx-auto pb-24 lg:pb-8" data-testid="meeting-page" data-meeting-status={status} data-planner="read">
      <PlanHeader m={s.meeting} canEdit={false} onSeriesChanged={() => undefined} onSave={async () => undefined} liveStatus={live.status} liveDetail={live.statusDetail}
        extra={!closed && !cancelled ? (
          <div className="flex flex-wrap gap-2 pt-1">
            <Button asChild size="sm" variant="outline"><Link to={`/meetings/${id}/member`}><Users className="size-4" />{inSession ? "Open the member view" : "Member view"}</Link></Button>
            {!amIn ? <Button asChild size="sm" variant="ghost"><Link to="/meetings/join"><KeyRound className="size-4" />Join with a code</Link></Button> : null}
          </div>
        ) : null} />
      {cancelled ? <div className="surface p-4" data-testid="meeting-cancelled"><EmptyState kind="wait" title="This meeting was cancelled" text={s.meeting.cancelled?.reason ? `Reason: ${s.meeting.cancelled.reason}` : "The members were told."} /></div> : null}

      {closed ? (
        <div className="grid items-start gap-4 lg:grid-cols-12">
          <div className="surface p-4 lg:col-span-8" data-testid="meeting-closed">
            <h2 className="text-base">This meeting is closed</h2>
            <p className="text-sm text-muted-foreground">Outcomes were sent to the owners. The Case Files keep their board records.</p>
            <ol className="mt-2 space-y-1 text-sm">
              {[...s.agenda.discussion, ...s.agenda.noting].map((r) => <li key={r.case_id} className="flex flex-wrap items-center gap-x-2"><Link className="text-link underline" to={`/cases/${r.case_id}`}>{r.patient_line || r.case_id}</Link><span className="text-xs text-muted-foreground">{r.outcome_label ?? (r.outcome ? r.outcome.replace(/_/g, " ") : "no outcome saved")}</span></li>)}
            </ol>
          </div>
          {mayPdf ? <div className="lg:col-span-4"><PdfCard mid={id} after /></div> : null}
        </div>
      ) : null}

      {!closed && !cancelled ? (
        <div className="grid items-start gap-4 lg:grid-cols-12">
          <div className="min-w-0 space-y-2 lg:col-span-8">
            {inSession ? <p className="rounded-md px-3 py-2 text-sm status-ok">The meeting is in session. <Link className="font-medium underline" to={`/meetings/${id}/member`}>Open the member view</Link> to follow the Case File on the board.</p> : null}
            <PlanLists state={s} canManage={false} cancer={cancer} />
          </div>
          <aside className="min-w-0 space-y-3 lg:col-span-4" aria-label="The meeting's members">
            <MembersCard state={s} />
            {mayPdf ? <PdfCard mid={id} after={false} /> : null}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
