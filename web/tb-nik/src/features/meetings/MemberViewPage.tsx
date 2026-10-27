// /meetings/:id/member: a member in the meeting, laid out like a video call (the call shell, call/CallShell.tsx): the shared screen
// with the slide tabs (follow it, or step away to the other slides), the people and the agents beside it, one side panel at a time
// (people, chat and questions, agenda, case, agents) and the control bar. Video goes through a pre-join screen (see your camera
// first). Members in the room keep video off on their own device. This page keeps the states before the call: not on this server,
// loading, missing, not joined, waiting to be admitted, and the pre-join.
// Voice (night-v3 4.4): the question box takes dictation; while the member dictates in the call, the call microphone is muted so
// the room does not hear it twice, and it comes back after (only if it was on); the shell keeps that guard.
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { motion } from "motion/react";
import { KeyRound, LogOut, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/session";
import { useMeetingLive, type LiveEvent } from "@/lib/live";
import { recallChoice, type JoinChoice } from "@/lib/video";
import { PreJoin } from "./components/PreJoin";
import { BarButton, ControlBar, StageFrame, StageTopBar } from "./components/Stage";
import { LiveDot } from "./components/shared";
import { CallShell } from "./call/CallShell";
import { EmptyState, ErrorState, SkeletonLines, fmtDate, useAnnounce } from "@/features/casefile/components/common";

export default function MemberViewPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { me } = useSession();
  const [announce, liveNode] = useAnnounce();
  const [choice, setChoice] = useState<JoinChoice | null | "skipped">(() => recallChoice());
  // The call shell takes every live event in order (the card request, the next case, the reactions); the page keeps "admitted".
  const shellEvents = useRef<((ev: LiveEvent) => void) | null>(null);
  const live = useMeetingLive(id, {
    onEvent: (ev: LiveEvent) => {
      if (ev.type === "admit" && ev.user === me?.user) announce("You are admitted to the meeting.");
      shellEvents.current?.(ev);
    },
  });
  const s = live.state;
  const cid = s?.current?.case_id ?? null;
  const admitted = s?.me?.status === "present" || s?.me?.status === "remote" || !!s?.can?.manage;
  const inRoom = s?.me?.mode === "room" || s?.me?.status === "present";
  const videoAvailable = !!s?.meeting.video && !!me?.features?.video && s?.can?.video !== false && !inRoom && admitted && s?.meeting.status !== "closed";
  const joinChoice = choice && choice !== "skipped" ? choice : null;

  if (live.notBuilt) return <div className="mx-auto max-w-xl py-8"><ErrorState error={live.error} title="The member view is not on this server yet" /></div>;
  if (live.isLoading) return <div className="mx-auto max-w-4xl surface p-4" aria-busy="true"><SkeletonLines n={6} /></div>;
  if (!s) {
    return (
      <div className="mx-auto max-w-xl py-8">
        {live.missing ? <EmptyState title="This meeting does not exist" action={<Button asChild variant="outline"><Link to="/meetings">All meetings</Link></Button>} />
          : live.forbidden ? <EmptyState title="You have not joined this meeting" text="Type the 6-digit code from the MDT Coordinator first." action={<Button asChild><Link to="/meetings/join"><KeyRound className="size-4" />Join with a code</Link></Button>} />
          : <ErrorState error={live.error} retry={() => void live.refresh()} />}
      </div>
    );
  }

  const waiting = s.me?.status === "waiting";
  const notJoined = !s.me?.status && !s.can?.manage;
  if (notJoined) return <div className="mx-auto max-w-xl py-8"><EmptyState title="You have not joined this meeting" text="Type the 6-digit code from the MDT Coordinator; you wait until they admit you." action={<Button asChild><Link to="/meetings/join"><KeyRound className="size-4" />Join with a code</Link></Button>} /></div>;

  const row = [...s.agenda.discussion, ...s.agenda.noting].find((r) => r.case_id === cid);

  if (waiting) {
    return (
      <StageFrame testId="member-view" attrs={{ "data-following": "true", "data-video-status": "off" }}>
        {liveNode}
        <StageTopBar
          left={<span className="hidden text-sm text-stage-muted sm:inline">Tumour Board · {fmtDate(s.meeting.date)}{s.meeting.time ? ` ${s.meeting.time}` : ""}</span>}
          center={<p className="truncate text-sm font-semibold text-stage-fg">Waiting to be admitted</p>}
          right={<LiveDot status={live.status} detail={live.statusDetail} />}
        />
        <main className="grid flex-1 place-items-center p-6">
          <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="max-w-md rounded-2xl border border-stage-line bg-stage-panel p-8 text-center" data-testid="waiting-room">
            <span className="relative mx-auto mb-4 grid size-14 place-items-center rounded-full bg-stage-raised"><span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/30" /><Users className="relative size-6 text-primary" /></span>
            <h1 className="text-xl text-stage-fg">Waiting for the coordinator to admit you</h1>
            <p className="mt-1 text-sm text-stage-muted">Keep this page open; it moves on by itself.</p>
          </motion.div>
        </main>
        <ControlBar right={<span className="text-xs text-stage-muted">{s.meeting.room ?? ""}</span>}>
          <BarButton icon={LogOut} label="Leave" title="Leave the meeting" tone="danger" onClick={() => nav(`/meetings/${id}`)} testId="leave" />
        </ControlBar>
      </StageFrame>
    );
  }

  if (videoAvailable && !choice) {
    return <PreJoin title={`Tumour Board, ${fmtDate(s.meeting.date)}${s.meeting.time ? ` at ${s.meeting.time}` : ""}`} subtitle={row ? `On the screen now: ${row.patient_line}` : "Check your camera and microphone, then join."} onJoin={(c) => setChoice(c)} onSkip={() => setChoice("skipped")} />;
  }

  return (
    <>
      {liveNode}
      <CallShell mid={id} variant="member" live={{ ...live, state: s }} me={me} joinChoice={joinChoice} videoAvailable={videoAvailable} onJoinVideo={() => setChoice(null)} events={shellEvents} />
    </>
  );
}
