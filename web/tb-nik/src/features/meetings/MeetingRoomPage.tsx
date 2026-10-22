// /meetings/:id/room: the room computer, on the projector. The summary of the case on the left, what the coordinator shares
// in the middle (a slide, a record, the images), the remote members' cameras on the right, the questions and the live
// decision below. It joins the video room under its own identity ("<user>#room") and can publish the room's camera and
// microphone, so the remote members see and hear the room.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Camera, CameraOff, Maximize2, Mic, MicOff, Minimize2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/session";
import { handUsers, useMeetingLive } from "@/lib/live";
import { useVideoRoom } from "@/lib/video";
import { getSlides } from "./api";
import { DecisionStrip, SharedScreen, SlideDots, StageFrame, StageTopBar } from "./components/Stage";
import { TileGrid, tilePeople } from "./components/VideoTiles";
import { AgentTile, LiveDot, QuestionsList, SlideContent, TimerBadge } from "./components/shared";
import { ErrorState, SkeletonLines, fmtDate } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

export default function MeetingRoomPage() {
  const { id = "" } = useParams();
  const { me } = useSession();
  const live = useMeetingLive(id);
  const s = live.state;
  const cid = s?.current?.case_id ?? null;
  const slideIdx = s?.current?.slide ?? 0;
  const opened = s?.current?.opened ?? null;
  const [fs, setFs] = useState(false);
  const slides = useQuery({ queryKey: ["slides", id, cid], queryFn: () => getSlides(id, cid!), enabled: !!cid, retry: 1, staleTime: 60_000 });
  const [savedFlash, setSavedFlash] = useState(false);
  useEffect(() => {
    if (live.lastEvent?.type !== "decision") return undefined;
    setSavedFlash(true);
    const t = window.setTimeout(() => setSavedFlash(false), 8000);
    return () => window.clearTimeout(t);
  }, [live.lastEvent]);
  useEffect(() => { const on = () => setFs(!!document.fullscreenElement); document.addEventListener("fullscreenchange", on); return () => document.removeEventListener("fullscreenchange", on); }, []);
  const videoOn = !!s?.meeting.video && !!me?.features?.video && s?.meeting.status === "in_session" && !!s?.can?.manage;
  const video = useVideoRoom(id, videoOn, { screen: "room", mic: false, cam: false });

  const toggleFs = async () => {
    try { if (!document.fullscreenElement) await document.documentElement.requestFullscreen(); else await document.exitFullscreen(); } catch { /* the browser refused; the layer still fills the window */ }
  };

  const row = s ? [...s.agenda.discussion, ...s.agenda.noting].find((r) => r.case_id === cid) : undefined;
  const all = slides.data?.slides ?? [];
  const summary = all.find((x) => x.kind === "summary") ?? all[0] ?? null;
  const current = all[slideIdx] ?? null;
  const rightSlide = current && current !== summary ? current : null;
  const liveText = s?.decision_live && (!s.decision_live.case_id || s.decision_live.case_id === cid) ? s.decision_live.text : "";
  const headline = row ? row.patient_line : s?.meeting.status === "closed" ? "Meeting closed" : s?.meeting.status === "cancelled" ? "Meeting cancelled" : s?.meeting.status === "planned" ? "Waiting for the coordinator to start" : "No case on the screen yet";
  const hands = handUsers(s?.hands);
  const people = s ? tilePeople(s.attendance.filter((a) => a.status === "remote"), hands) : [];
  const questions = (s?.questions ?? []).filter((q) => !cid || !q.case_id || q.case_id === cid);

  return (
    <StageFrame testId="room-screen" attrs={{ "data-meeting-status": s?.meeting.status }}>
      <StageTopBar
        left={<span className="text-sm text-stage-muted">Tumour Board{s ? ` · ${fmtDate(s.meeting.date)}${s.meeting.time ? ` ${s.meeting.time}` : ""}${s.meeting.room ? ` · ${s.meeting.room}` : ""}` : ""}</span>}
        center={<div className="min-w-0"><h1 className="truncate text-xl text-stage-fg lg:text-2xl">{headline}</h1>{row?.board_question ? <p className="truncate text-sm text-stage-muted lg:text-base"><span className="text-stage-muted/80">Board question: </span><span className="text-stage-fg/90">{row.board_question}</span></p> : null}</div>}
        right={<>
          <TimerBadge timer={s?.current?.timer} big />
          <LiveDot status={live.status} detail={live.statusDetail} />
          {videoOn ? (
            <>
              <Button variant="ghost" size="sm" className={cn("text-stage-fg hover:bg-stage-raised hover:text-stage-fg", video.micOn && "bg-stage-raised")} onClick={() => void video.toggleMic()} disabled={video.status !== "connected"} aria-pressed={video.micOn} title="The room's microphone, for the remote members">{video.micOn ? <Mic className="size-4" /> : <MicOff className="size-4" />}Room mic</Button>
              <Button variant="ghost" size="sm" className={cn("text-stage-fg hover:bg-stage-raised hover:text-stage-fg", video.camOn && "bg-stage-raised")} onClick={() => void video.toggleCam()} disabled={video.status !== "connected"} aria-pressed={video.camOn} title="The room's camera, for the remote members">{video.camOn ? <Camera className="size-4" /> : <CameraOff className="size-4" />}Room camera</Button>
            </>
          ) : null}
          <Button variant="ghost" size="icon" className="text-stage-fg hover:bg-stage-raised hover:text-stage-fg" onClick={() => void toggleFs()} aria-label={fs ? "Leave full screen" : "Full screen"} title={fs ? "Leave full screen" : "Full screen"}>{fs ? <Minimize2 className="size-5" /> : <Maximize2 className="size-5" />}</Button>
          <Button asChild variant="ghost" size="icon" className="text-stage-fg hover:bg-stage-raised hover:text-stage-fg" aria-label="Close the room screen" title="Close the room screen"><Link to={`/meetings/${id}`}><X className="size-5" /></Link></Button>
        </>}
      />

      {live.notBuilt ? <div className="p-8" data-theme="dark"><ErrorState error={live.error} title="The meeting rooms are not on this server yet" /></div> : null}
      {live.missing && !s ? <div className="p-8" data-theme="dark"><ErrorState error={live.error} title="This meeting does not exist" /></div> : null}
      {live.forbidden && !s ? <div className="p-8" data-theme="dark"><ErrorState error={live.error} title="This computer is not signed in as a member of the meeting" /></div> : null}
      {live.error && !s && !live.notBuilt && !live.missing && !live.forbidden ? <div className="p-8" data-theme="dark"><ErrorState error={live.error} retry={() => void live.refresh()} /></div> : null}
      {live.isLoading ? <div className="p-8" data-theme="dark"><SkeletonLines n={6} /></div> : null}

      {s ? (
        <main className="flex min-h-0 flex-1 gap-3 p-3 lg:p-4">
          <section className="scroll-thin hidden w-[30%] min-w-0 overflow-y-auto rounded-xl border border-stage-line bg-stage-panel p-5 lg:block" aria-label="Summary" data-testid="room-summary">
            {!cid ? <p className="text-lg text-stage-muted">The summary of the current case appears here.</p> : null}
            {cid && slides.isLoading ? <div data-theme="dark"><SkeletonLines n={8} /></div> : null}
            {cid && slides.isError ? <p className="text-lg text-warn">The slides for this case could not be loaded.</p> : null}
            {summary ? <div data-theme="dark"><SlideContent slide={summary} big /></div> : null}
          </section>
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
            <SharedScreen cid={cid} opened={opened} slide={rightSlide} big empty={cid ? "The coordinator can show a slide, a record or the images here." : "Waiting for the first case."}>
              <SlideDots slides={all} index={slideIdx} className="absolute bottom-3 right-4" />
            </SharedScreen>
            <AnimatePresence initial={false}>
              {questions.length ? (
                <motion.section key="q" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="scroll-thin max-h-56 shrink-0 overflow-y-auto rounded-xl border border-stage-line bg-stage-panel p-3" aria-label="Questions">
                  <h2 className="mb-1 text-sm font-semibold text-stage-muted">Questions from members</h2>
                  <div data-theme="dark"><QuestionsList questions={questions} caseId={cid} big /></div>
                </motion.section>
              ) : null}
            </AnimatePresence>
          </div>
          <aside className="scroll-thin flex w-48 shrink-0 flex-col gap-2 overflow-y-auto xl:w-60" aria-label="Remote members">
            <TileGrid room={video.room} people={people} layout="column" size="md" max={6} />
            {!people.length && !video.room ? <p className="px-1 text-xs text-stage-muted">Remote members appear here when they join.</p> : null}
            {s.agent?.active ? <div data-theme="dark"><AgentTile agent={s.agent} /></div> : null}
          </aside>
        </main>
      ) : <div className="flex-1" />}

      <footer className="space-y-2 border-t border-stage-line px-3 py-2 lg:px-4">
        <div className="flex flex-wrap items-center gap-2 text-sm text-stage-muted">
          {s ? <span>{s.attendance.filter((a) => a.status === "present" || a.status === "remote").length} in the meeting</span> : null}
          {hands.size ? <span className="rounded-full bg-warn/20 px-2 py-0.5 text-xs font-medium text-[#ffd48a]">{hands.size} hand{hands.size === 1 ? "" : "s"} raised: {s?.attendance.filter((a) => hands.has(a.user)).map((a) => a.name).join(", ")}</span> : null}
          {video.error ? <span className="text-xs text-[#ffb4a8]">{video.error}</span> : null}
        </div>
        <DecisionStrip text={liveText} saved={savedFlash} big className={!liveText && !savedFlash ? "hidden" : ""} />
        {!liveText && !savedFlash ? <p className="rounded-xl border border-dashed border-stage-line px-4 py-2 text-sm text-stage-muted">The decision appears here as the coordinator types it, until it is read back and saved.</p> : null}
      </footer>
    </StageFrame>
  );
}
