// The coordinator's view during a meeting (MeetingAgendaPage shows it while the meeting is in session), laid out as the same call as
// the member view (call/CallShell.tsx, variant "coordinator"). The laptop is mirrored to the projector (meetings-v2 D1): the Board view
// of the Case File on the floor large in the middle, led from here (every click moves the room and the remote members), the slim agenda
// rail, the slim top bar with the timer and the Record placeholder, a narrow strip of people and agents, the admit line under the
// stage, one side panel on demand (People with the waiting room, Chat and questions, Agents, Decision with the form and the cards)
// and the control bar with the case moves, the timer, End case and End meeting. The camera and microphone go through the pre-join first. While the coordinator dictates in the
// call, the call microphone is muted so the room does not hear it twice, and it comes back after (only if it was on).
import { useState, type MutableRefObject } from "react";
import { useSession } from "@/lib/session";
import type { LiveEvent, LiveStatus, MeetingState } from "@/lib/live";
import { recallChoice, type JoinChoice } from "@/lib/video";
import { PreJoin } from "./PreJoin";
import { CallShell } from "../call/CallShell";
import { fmtDate } from "@/features/casefile/components/common";

export function ControlView({ mid, state, onChanged, liveStatus = "open", liveDetail, lastEvent, events }: {
  mid: string; state: MeetingState; onChanged: () => void; liveStatus?: LiveStatus; liveDetail?: string;
  /** The last live event (useMeetingLive's lastEvent): reactions and "Decision saved" need it; optional so older callers still work. */
  lastEvent?: LiveEvent | null;
  /** Every live event in order (the agenda page forwards them): nothing is lost when two arrive in one tick. */
  events?: MutableRefObject<((ev: LiveEvent) => void) | null>;
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
      events={events}
    />
  );
}
