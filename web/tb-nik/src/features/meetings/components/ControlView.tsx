// The coordinator's view during a meeting (MeetingAgendaPage shows it while the meeting is in session), laid out as the same call as
// the member view (call/CallShell.tsx, variant "coordinator"): the agenda rail, the slide tabs that change what the room sees, the
// stage with the admit toast, the people and the agents, one side panel (People with the waiting room, Chat and questions, Agenda,
// Case with the records and images, Agents, Decision with the form and the cards) and the control bar with the case moves, the
// timer, End case and End meeting. The camera and microphone go through the pre-join first. While the coordinator dictates in the
// call, the call microphone is muted so the room does not hear it twice, and it comes back after (only if it was on).
import { useState } from "react";
import { useSession } from "@/lib/session";
import type { LiveEvent, LiveStatus, MeetingState } from "@/lib/live";
import { recallChoice, type JoinChoice } from "@/lib/video";
import { PreJoin } from "./PreJoin";
import { CallShell } from "../call/CallShell";
import { fmtDate } from "@/features/casefile/components/common";

export function ControlView({ mid, state, onChanged, liveStatus = "open", liveDetail, lastEvent }: {
  mid: string; state: MeetingState; onChanged: () => void; liveStatus?: LiveStatus; liveDetail?: string;
  /** The last live event (useMeetingLive's lastEvent): reactions and "Decision saved" need it; optional so older callers still work. */
  lastEvent?: LiveEvent | null;
}) {
  const { me } = useSession();
  const [choice, setChoice] = useState<JoinChoice | null | "skipped">(() => recallChoice());
  const videoAvailable = !!state.meeting.video && !!me?.features?.video;
  const joinChoice = choice && choice !== "skipped" ? choice : null;

  if (videoAvailable && !choice) {
    return <PreJoin title={`Conduct the Tumour Board, ${fmtDate(state.meeting.date)}${state.meeting.time ? ` at ${state.meeting.time}` : ""}`} subtitle="The remote members see and hear you from here. Check the camera and microphone first." onJoin={(c) => setChoice(c)} onSkip={() => setChoice("skipped")} />;
  }

  return (
    <CallShell
      mid={mid}
      variant="coordinator"
      live={{ state, status: liveStatus, statusDetail: liveDetail, lastEvent, refresh: onChanged }}
      me={me}
      joinChoice={joinChoice}
      videoAvailable={videoAvailable}
      onJoinVideo={() => setChoice(null)}
    />
  );
}
