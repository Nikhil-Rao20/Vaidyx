// /meetings/:id/member: a member in the meeting, laid out like a video call. The shared screen in the middle (follow it, or
// step away to the other slides), the people beside it with their cameras, panels for the people and the questions, and the
// control bar: microphone, camera, hand, follow, questions, people, the end-of-case card, leave. Video goes through a
// pre-join screen (see your camera first). Members in the room keep video off on their own device.
// Voice (night-v3 4.4): the question box takes dictation; while the member dictates in the call, the call microphone is muted so
// the room does not hear it twice, and it comes back after (only if it was on).
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, Camera, CameraOff, Copy, Footprints, Hand, KeyRound, LogOut, MessageSquareText, Mic, MicOff, MonitorCheck, Phone, SendHorizontal, Users, Vote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { useSession } from "@/lib/session";
import { handUsers, useMeetingLive, type LiveEvent, type MeetingState } from "@/lib/live";
import { recallChoice, useVideoRoom, type JoinChoice } from "@/lib/video";
import { useDictationGuard } from "@/hooks/useDictationGuard";
import { askQuestion, getSlides, present, raiseHand } from "./api";
import { CardDialog } from "./components/CardDialog";
import { PreJoin } from "./components/PreJoin";
import { PeopleList } from "./components/People";
import { BarButton, ControlBar, DecisionStrip, SharedScreen, SlideDots, StageFrame, StagePanel, StageTopBar } from "./components/Stage";
import { TileGrid, tilePeople } from "./components/VideoTiles";
import { AgentTile, LiveDot, QuestionsList, TimerBadge } from "./components/shared";
import { EmptyState, ErrorState, LoadingButton, SkeletonLines, errorText, fmtDate, useAnnounce, useCopy } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

/** The room phone and the members who share theirs (no dialer in this build). */
function CallButton({ s }: { s: MeetingState }) {
  const [copied, copy] = useCopy();
  const room = s.meeting.room_phone ?? s.meeting.phone ?? null;
  const people = s.attendance.filter((a) => a.phone);
  const count = (room ? 1 : 0) + people.length;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="sm" variant="ghost" className="text-stage-fg hover:bg-stage-raised hover:text-stage-fg" aria-label={count ? `Phone numbers (${count})` : "Phone numbers"} data-testid="call-button"><Phone className="size-4" />{room ?? (count ? `${count} numbers` : "Call")}</Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 space-y-2">
        <p className="text-sm font-medium">Call by phone</p>
        {count === 0 ? <p className="text-xs text-muted-foreground">No phone number is shared for this meeting. Members share theirs in Settings, Profile.</p> : null}
        <ul className="space-y-1">
          {room ? <li className="flex items-center gap-2 text-sm"><span className="flex-1">Meeting room</span><a className="id text-link" href={`tel:${room}`}>{room}</a><Button size="icon-xs" variant="ghost" aria-label="Copy the number" onClick={() => void copy(room)}><Copy className="size-3" /></Button></li> : null}
          {people.map((a) => <li key={a.user} className="flex items-center gap-2 text-sm"><span className="flex-1 truncate">{a.name}</span><a className="id text-link" href={`tel:${a.phone}`}>{a.phone}</a><Button size="icon-xs" variant="ghost" aria-label={`Copy ${a.name}'s number`} onClick={() => void copy(a.phone!)}><Copy className="size-3" /></Button></li>)}
        </ul>
        {copied ? <p className="text-xs text-ok" role="status">Copied</p> : null}
      </PopoverContent>
    </Popover>
  );
}

type PanelKind = "people" | "questions" | null;

export default function MemberViewPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { me } = useSession();
  const [announce, liveNode] = useAnnounce();
  const [card, setCard] = useState<{ caseId: string; patientLine: string } | null>(null);
  const [following, setFollowing] = useState(true);
  const [mySlide, setMySlide] = useState(0);
  const [question, setQuestion] = useState("");
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const [panel, setPanel] = useState<PanelKind>(null);
  const [choice, setChoice] = useState<JoinChoice | null | "skipped">(() => recallChoice());
  const stateRef = useRef<MeetingState | null>(null);
  const live = useMeetingLive(id, {
    onEvent: (ev: LiveEvent) => {
      const st = stateRef.current;
      if (ev.type === "end_case") {
        const cid = String(ev.case_id ?? "");
        const asked = Array.isArray(ev.cards_requested) ? (ev.cards_requested as string[]) : [];
        const myDept = st?.me?.department ?? "";
        const admitted = st?.me?.status === "present" || st?.me?.status === "remote";
        if (admitted && (st?.can?.card_required || (myDept && asked.includes(myDept)))) {
          const row = st ? [...st.agenda.discussion, ...st.agenda.noting].find((r) => r.case_id === cid) : undefined;
          setCard({ caseId: cid, patientLine: row?.patient_line || cid });
          announce("The coordinator asks for your card on this case.");
        }
      }
      if (ev.type === "current" && ev.case_id && ev.case_id !== st?.current?.case_id) announce("The shared screen moved to the next case.");
      if (ev.type === "admit" && ev.user === me?.user) announce("You are admitted to the meeting.");
      if (ev.type === "ended") announce("The meeting has ended.");
    },
  });
  const s = live.state;
  stateRef.current = s;
  const cid = s?.current?.case_id ?? null;
  const sharedSlide = s?.current?.slide ?? 0;
  const opened = s?.current?.opened ?? null;
  const admitted = s?.me?.status === "present" || s?.me?.status === "remote" || !!s?.can?.manage;
  const slides = useQuery({ queryKey: ["slides", id, cid], queryFn: () => getSlides(id, cid!), enabled: !!cid && admitted, retry: 1, staleTime: 60_000 });
  useEffect(() => { if (following) setMySlide(sharedSlide); }, [sharedSlide, following]);
  useEffect(() => { setFollowing(true); }, [cid]);

  const inRoom = s?.me?.mode === "room" || s?.me?.status === "present";
  const inSession = s?.meeting.status === "in_session";
  const videoAvailable = !!s?.meeting.video && !!me?.features?.video && s?.can?.video !== false && !inRoom && admitted && s?.meeting.status !== "closed";
  const joinChoice = choice && choice !== "skipped" ? choice : null;
  const video = useVideoRoom(id, videoAvailable && !!joinChoice, joinChoice ?? {});

  // While the member dictates in the call, the call microphone is muted and comes back after (see useDictationGuard).
  const dictating = useDictationGuard(video);

  const ask = useMutation({ mutationFn: (t: string) => askQuestion(id, t), onSuccess: () => { setQuestion(""); announce("Question sent to the shared screen."); void live.refresh(); } });
  const handM = useMutation({ mutationFn: (r: boolean) => raiseHand(id, r), onSuccess: (_r, raised) => announce(raised ? "Hand raised." : "Hand lowered.") });
  const presentM = useMutation({ mutationFn: (mode: "room" | "remote") => present(id, mode), onSuccess: (_r, mode) => { announce(mode === "room" ? "Marked as in the room." : "Marked as remote."); void live.refresh(); } });

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
  const all = slides.data?.slides ?? [];
  const shownIdx = following ? sharedSlide : mySlide;
  const shown = all[shownIdx] ?? null;
  const hands = handUsers(s.hands);
  const hand = hands.has(me?.user ?? "");
  const people = tilePeople(s.attendance, hands, me?.user);
  const liveText = s.decision_live && (!s.decision_live.case_id || s.decision_live.case_id === cid) ? s.decision_live.text : "";
  const savedNow = live.lastEvent?.type === "decision";
  const questions = (s.questions ?? []).filter((q) => !cid || !q.case_id || q.case_id === cid);
  const cardAsked = !!cid && (s.ended ?? []).includes(cid) && (s.can?.card || s.can?.card_required);
  const headline = row ? row.patient_line : s.meeting.status === "planned" ? "The meeting has not started" : s.meeting.status === "closed" ? "The meeting is closed" : s.meeting.status === "cancelled" ? "The meeting was cancelled" : "Waiting for the first case";

  if (videoAvailable && !choice && !waiting) {
    return <PreJoin title={`Tumour Board, ${fmtDate(s.meeting.date)}${s.meeting.time ? ` at ${s.meeting.time}` : ""}`} subtitle={row ? `On the screen now: ${row.patient_line}` : "Check your camera and microphone, then join."} onJoin={(c) => setChoice(c)} onSkip={() => setChoice("skipped")} />;
  }

  const toggle = (p: PanelKind) => setPanel((cur) => (cur === p ? null : p));

  return (
    <StageFrame testId="member-view" attrs={{ "data-following": String(following), "data-video-status": video.status }}>
      {liveNode}
      <StageTopBar
        left={<span className="hidden text-sm text-stage-muted sm:inline">Tumour Board · {fmtDate(s.meeting.date)}{s.meeting.time ? ` ${s.meeting.time}` : ""}</span>}
        center={<div className="min-w-0"><p className="truncate text-sm font-semibold text-stage-fg">{headline}</p>{row?.board_question ? <p className="truncate text-xs text-stage-muted">Board question: {row.board_question}</p> : null}</div>}
        right={<>
          <TimerBadge timer={s.current?.timer} />
          <LiveDot status={live.status} detail={live.statusDetail} className="hidden sm:inline-flex" />
          <Button size="sm" variant="ghost" className="hidden text-stage-fg hover:bg-stage-raised hover:text-stage-fg sm:inline-flex" onClick={() => presentM.mutate(inRoom ? "remote" : "room")} disabled={presentM.isPending || s.meeting.status === "closed"} aria-pressed={inRoom} title="Tell the coordinator whether you are physically in the room">{inRoom ? "I am in the room" : "I am remote"}</Button>
          <CallButton s={s} />
        </>}
      />

      {waiting ? (
        <main className="grid flex-1 place-items-center p-6">
          <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="max-w-md rounded-2xl border border-stage-line bg-stage-panel p-8 text-center" data-testid="waiting-room">
            <span className="relative mx-auto mb-4 grid size-14 place-items-center rounded-full bg-stage-raised"><span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/30" /><Users className="relative size-6 text-primary" /></span>
            <h1 className="text-xl text-stage-fg">Waiting for the coordinator to admit you</h1>
            <p className="mt-1 text-sm text-stage-muted">Keep this page open; it moves on by itself.</p>
          </motion.div>
        </main>
      ) : (
        <main className="flex min-h-0 flex-1 gap-3 p-3">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-2">
            <SharedScreen cid={cid} opened={following ? opened : null} slide={shown} empty={cid ? (slides.isLoading ? "Loading the slides" : slides.isError ? `The slides could not be loaded: ${errorText(slides.error)}` : "Nothing on the screen yet") : inSession ? "Waiting for the first case" : headline}
              label={<span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium", following ? "bg-ok/20 text-[#8fe0b3]" : "bg-warn/20 text-[#ffd48a]")}>{following ? <MonitorCheck className="size-3.5" /> : <Footprints className="size-3.5" />}{following ? "Following the shared screen" : "Stepped away"}</span>}>
              {!following && all.length > 1 ? (
                <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-gradient-to-t from-black/60 to-transparent px-3 pb-2 pt-6">
                  <Button size="sm" variant="ghost" className="text-white hover:bg-white/15 hover:text-white" onClick={() => setMySlide((i) => Math.max(0, i - 1))} disabled={mySlide <= 0}><ArrowLeft className="size-4" />Previous</Button>
                  <span className="text-xs text-white/80">{mySlide + 1} of {all.length}{mySlide === sharedSlide ? ", same as the screen" : `, the screen shows ${sharedSlide + 1}`}</span>
                  <Button size="sm" variant="ghost" className="text-white hover:bg-white/15 hover:text-white" onClick={() => setMySlide((i) => Math.min(all.length - 1, i + 1))} disabled={mySlide >= all.length - 1}>Next<ArrowRight className="size-4" /></Button>
                </div>
              ) : <SlideDots slides={all} index={shownIdx} className="absolute bottom-2 right-3" />}
            </SharedScreen>
            <AnimatePresence>{liveText || savedNow ? <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}><DecisionStrip text={liveText} saved={savedNow} /></motion.div> : null}</AnimatePresence>
            <div className="lg:hidden"><TileGrid room={video.room} people={people} layout="row" size="sm" /></div>
          </div>
          <div className="scroll-thin hidden w-52 shrink-0 overflow-y-auto lg:block xl:w-60">
            <TileGrid room={video.room} people={people} layout="column" size="md" />
            <div className="mt-2" data-theme="dark"><AgentTile agent={s.agent} /></div>
          </div>
          <StagePanel open={panel === "people"} title={`People · ${people.length}`} onClose={() => setPanel(null)} testId="people-panel">
            <PeopleList attendance={s.attendance} hands={hands} me={me?.user} />
          </StagePanel>
          <StagePanel open={panel === "questions"} title="Questions" onClose={() => setPanel(null)} testId="questions-panel">
            <div data-theme="dark" className="space-y-3">
              <QuestionsList questions={s.questions ?? []} caseId={cid} emptyText="No questions on this case yet." />
              <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (question.trim().length >= 3) ask.mutate(question.trim()); }}>
                <label htmlFor="member-q" className="sr-only">Type a question</label>
                <Textarea ref={questionRef} id="member-q" value={question} onChange={(e) => setQuestion(e.target.value)} className="min-h-16 text-sm" placeholder="Type a question; it shows on the room screen with your name" maxLength={500} disabled={ask.isPending || !inSession || !cid} />
                <div className="flex items-center gap-2">
                  {ask.isError ? <p role="alert" className="flex-1 text-xs text-bad">{errorText(ask.error)}</p> : <span className="flex-1 text-xs text-muted-foreground">{!inSession ? "Questions open when the meeting starts." : !cid ? "Questions open when a case is on the screen." : "The stand-in answers from the records only."}</span>}
                  {inSession && cid ? <MicButton target={questionRef} screen="meeting-q" context="question" label="Dictate the question" caseId={cid} className="max-w-[60%] shrink-0" onInsert={(next) => { if (next.length > 500) setQuestion(next.slice(0, 500)); }} /> : null}
                  <LoadingButton size="sm" type="submit" loading={ask.isPending} loadingText="Sending" disabled={question.trim().length < 3 || !inSession || !cid} data-testid="send-question"><SendHorizontal className="size-4" />Send</LoadingButton>
                </div>
              </form>
            </div>
          </StagePanel>
        </main>
      )}

      <ControlBar
        left={video.error ? <p role="alert" className="truncate text-xs text-[#ffb4a8]">{video.error}</p> : video.status === "connecting" ? <span className="text-xs text-stage-muted">Joining the video</span> : video.status === "connected" ? <span className="text-xs text-stage-muted">Video on the hospital's server</span> : inRoom ? <span className="text-xs text-stage-muted">In the room: video stays off on this device</span> : null}
        right={<span className="text-xs text-stage-muted">{s.meeting.room ? `${s.meeting.room} · ` : ""}{people.length} in the meeting</span>}
      >
        {videoAvailable && joinChoice ? (
          <>
            <BarButton icon={video.micOn && !dictating ? Mic : MicOff} label={dictating ? "Dictating" : video.micOn ? "Mute" : "Unmute"} title={dictating ? "Your call microphone is off while you dictate; it comes back on after." : undefined} active={!video.micOn || dictating} onClick={() => void video.toggleMic()} disabled={video.status !== "connected" || dictating} testId="mic" />
            <BarButton icon={video.camOn ? Camera : CameraOff} label={video.camOn ? "Camera" : "Camera off"} active={!video.camOn} onClick={() => void video.toggleCam()} disabled={video.status !== "connected"} testId="cam" />
          </>
        ) : videoAvailable ? <BarButton icon={Camera} label="Join video" onClick={() => setChoice(null)} /> : null}
        <BarButton icon={Hand} label={hand ? "Lower" : "Raise hand"} active={hand} onClick={() => handM.mutate(!hand)} disabled={!inSession || handM.isPending || waiting} testId="raise-hand" />
        <BarButton icon={following ? Footprints : MonitorCheck} label={following ? "Step away" : "Follow"} onClick={() => setFollowing((f) => !f)} disabled={!cid || all.length < 2 || waiting} title={following ? "Look at the other slides on your own" : "Back to what the room shows"} testId={following ? "step-away" : "back-to-shared"} />
        <BarButton icon={MessageSquareText} label="Questions" active={panel === "questions"} onClick={() => toggle("questions")} badge={questions.length || undefined} disabled={waiting} />
        <BarButton icon={Users} label="People" active={panel === "people"} onClick={() => toggle("people")} badge={people.length || undefined} />
        {cardAsked ? <BarButton icon={Vote} label="Your card" tone="primary" onClick={() => setCard({ caseId: cid!, patientLine: row?.patient_line || cid! })} testId="give-card" /> : null}
        <BarButton icon={LogOut} label="Leave" tone="danger" onClick={() => nav(`/meetings/${id}`)} testId="leave" />
      </ControlBar>
      {card ? <CardDialog mid={id} caseId={card.caseId} patientLine={card.patientLine} required={!!s.can?.card_required} open onOpenChange={(o) => { if (!o) setCard(null); }} onSent={() => announce("Card sent.")} /> : null}
    </StageFrame>
  );
}
