// /meetings/:id/room: the room computer, on the projector, as the call shell's room variant (call/CallShell.tsx): the summary of the
// case in a column on the left (a toggle, "Summary on the side", on by default), what the coordinator shares in the middle (a slide,
// a record, the images), the remote members' cameras and the agents standing in on the right, the questions and the live decision
// below. No control bar: a small bar at the bottom right (room microphone and camera, the summary column, the agent voices, full
// screen, close). It joins the video room under its own identity ("<user>#room"); its microphone and camera stay off until the
// coordinator turns them on here, so the remote members see and hear the room.
import { useParams } from "react-router-dom";
import { useSession } from "@/lib/session";
import { useMeetingLive } from "@/lib/live";
import { StageFrame, StageTopBar } from "./components/Stage";
import { LiveDot } from "./components/shared";
import { CallShell } from "./call/CallShell";
import { ErrorState, SkeletonLines } from "@/features/casefile/components/common";

export default function MeetingRoomPage() {
  const { id = "" } = useParams();
  const { me } = useSession();
  const live = useMeetingLive(id);
  const s = live.state;

  if (!s) {
    return (
      <StageFrame testId="room-screen" attrs={{ "data-meeting-status": undefined }}>
        <StageTopBar left={<span className="text-sm text-stage-muted">Tumour Board</span>} right={<LiveDot status={live.status} detail={live.statusDetail} />} />
        {live.notBuilt ? <div className="p-8" data-theme="dark"><ErrorState error={live.error} title="The meeting rooms are not on this server yet" /></div>
          : live.missing ? <div className="p-8" data-theme="dark"><ErrorState error={live.error} title="This meeting does not exist" /></div>
          : live.forbidden ? <div className="p-8" data-theme="dark"><ErrorState error={live.error} title="This computer is not signed in as a member of the meeting" /></div>
          : live.error ? <div className="p-8" data-theme="dark"><ErrorState error={live.error} retry={() => void live.refresh()} /></div>
          : <div className="p-8" data-theme="dark"><SkeletonLines n={6} /></div>}
        <div className="flex-1" />
      </StageFrame>
    );
  }

  const videoOn = !!s.meeting.video && !!me?.features?.video && s.meeting.status === "in_session" && !!s.can?.manage;
  return <CallShell mid={id} variant="room" live={{ ...live, state: s }} me={me} videoAvailable={videoOn} />;
}
