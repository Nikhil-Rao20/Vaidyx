// /meetings/:id/member: a remote member follows the shared screen (can step away and come back), types a question,
// raises a hand, joins video when the meeting has it, and answers the end-of-case card.
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, Copy, Footprints, Hand, KeyRound, MonitorCheck, Phone, SendHorizontal, Vote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/lib/session";
import { handUsers, useMeetingLive, type LiveEvent, type MeetingState } from "@/lib/live";
import { askQuestion, getSlides, present, raiseHand, recordPageUrl, viewerSrc } from "./api";
import { CardDialog } from "./components/CardDialog";
import { AgentTile, LiveDot, MembersStrip, QuestionsList, SlideContent, TimerBadge } from "./components/shared";
// Video (LiveKit) loads only when the meeting has it, so the member view stays light.
const VideoTiles = lazy(() => import("./components/VideoTiles").then((m) => ({ default: m.VideoTiles })));
import { EmptyState, ErrorState, LoadingButton, SkeletonLines, errorText, fmtDate, useAnnounce, useCopy } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

/** "Laptop: the call icon shows the number" (no dialer in this build): the room phone and the members who share theirs. */
function CallButton({ s }: { s: MeetingState }) {
  const [copied, copy] = useCopy();
  const room = s.meeting.room_phone ?? s.meeting.phone ?? null;
  const people = s.attendance.filter((a) => a.phone);
  const count = (room ? 1 : 0) + people.length;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="sm" variant="outline" aria-label={count ? `Phone numbers (${count})` : "Phone numbers"} data-testid="call-button"><Phone className="size-4" />{room ?? (count ? `${count} numbers` : "Call")}</Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 space-y-2">
        <p className="text-sm font-medium">Call by phone</p>
        {count === 0 ? <p className="text-xs text-muted-foreground">No phone number is shared for this meeting. Members share theirs in Settings, Profile.</p> : null}
        <ul className="space-y-1">
          {room ? <li className="flex items-center gap-2 text-sm"><span className="flex-1">Meeting room</span><a className="mono text-link" href={`tel:${room}`}>{room}</a><Button size="icon-xs" variant="ghost" aria-label="Copy the number" onClick={() => void copy(room)}><Copy className="size-3" /></Button></li> : null}
          {people.map((a) => <li key={a.user} className="flex items-center gap-2 text-sm"><span className="flex-1 truncate">{a.name}</span><a className="mono text-link" href={`tel:${a.phone}`}>{a.phone}</a><Button size="icon-xs" variant="ghost" aria-label={`Copy ${a.name}'s number`} onClick={() => void copy(a.phone!)}><Copy className="size-3" /></Button></li>)}
        </ul>
        {copied ? <p className="text-xs text-ok" role="status">Copied</p> : null}
      </PopoverContent>
    </Popover>
  );
}

export default function MemberViewPage() {
  const { id = "" } = useParams();
  const { me } = useSession();
  const [announce, liveNode] = useAnnounce();
  const [card, setCard] = useState<{ caseId: string; patientLine: string } | null>(null);
  const [following, setFollowing] = useState(true);
  const [mySlide, setMySlide] = useState(0);
  const [question, setQuestion] = useState("");
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

  const ask = useMutation({ mutationFn: (t: string) => askQuestion(id, t), onSuccess: () => { setQuestion(""); announce("Question sent to the shared screen."); void live.refresh(); } });
  const handM = useMutation({ mutationFn: (r: boolean) => raiseHand(id, r), onSuccess: (_r, raised) => announce(raised ? "Hand raised." : "Hand lowered.") });
  const presentM = useMutation({ mutationFn: (mode: "room" | "remote") => present(id, mode), onSuccess: (_r, mode) => { announce(mode === "room" ? "Marked as in the room." : "Marked as remote."); void live.refresh(); } });

  if (live.notBuilt) return <div className="max-w-xl mx-auto py-8"><ErrorState error={live.error} title="The member view is not on this server yet" /></div>;
  if (live.isLoading) return <div className="max-w-4xl mx-auto surface p-4" aria-busy="true"><SkeletonLines n={6} /></div>;
  if (!s) {
    return (
      <div className="max-w-xl mx-auto py-8">
        {live.missing ? <EmptyState title="This meeting does not exist" action={<Button asChild variant="outline"><Link to="/meetings">All meetings</Link></Button>} />
          : live.forbidden ? <EmptyState title="You have not joined this meeting" text="Type the 6-digit code from the MDT Coordinator first." action={<Button asChild><Link to="/meetings/join"><KeyRound className="size-4" />Join with a code</Link></Button>} />
          : <ErrorState error={live.error} retry={() => void live.refresh()} />}
      </div>
    );
  }

  const waiting = s.me?.status === "waiting";
  const notJoined = !s.me?.status && !s.can?.manage;
  const row = [...s.agenda.discussion, ...s.agenda.noting].find((r) => r.case_id === cid);
  const all = slides.data?.slides ?? [];
  const shownIdx = following ? sharedSlide : mySlide;
  const shown = all[shownIdx] ?? null;
  const inRoom = s.me?.mode === "room" || s.me?.status === "present";
  const videoOn = !!s.meeting.video && !!me?.features?.video && s.can?.video !== false && !inRoom && admitted && s.meeting.status !== "closed";
  const hand = handUsers(s.hands).has(me?.user ?? "");
  const inSession = s.meeting.status === "in_session";
  const viewer = following && opened?.kind === "images" ? viewerSrc(opened) : null;

  return (
    <div className="space-y-3 max-w-6xl mx-auto pb-24 lg:pb-8" data-testid="member-view" data-following={following}>
      {liveNode}
      <header className="surface p-3 flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1 basis-56">
          <p className="text-xs text-muted-foreground"><Link to="/meetings" className="hover:underline">Meetings</Link> / <Link to={`/meetings/${id}`} className="hover:underline">{fmtDate(s.meeting.date)}{s.meeting.time ? ` ${s.meeting.time}` : ""}</Link></p>
          <h1 className="text-lg truncate">{row ? row.patient_line : s.meeting.status === "planned" ? "The meeting has not started" : s.meeting.status === "closed" ? "The meeting is closed" : s.meeting.status === "cancelled" ? "The meeting was cancelled" : "Waiting for the first case"}</h1>
          {row?.board_question ? <p className="text-sm truncate"><span className="text-muted-foreground">Board question: </span>{row.board_question}</p> : null}
        </div>
        <TimerBadge timer={s.current?.timer} />
        <LiveDot status={live.status} detail={live.statusDetail} />
        <CallButton s={s} />
      </header>

      {notJoined ? (
        <div className="surface p-6"><EmptyState title="You have not joined this meeting" text="Type the 6-digit code from the MDT Coordinator; you wait until they admit you." action={<Button asChild><Link to="/meetings/join"><KeyRound className="size-4" />Join with a code</Link></Button>} /></div>
      ) : waiting ? (
        <div className="surface p-6" data-testid="waiting-room"><EmptyState kind="wait" title="Waiting for the coordinator to admit you" text="Keep this page open; it moves on by itself." /></div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-12 items-start">
          <div className="lg:col-span-8 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              {following ? <span className="inline-flex items-center gap-1 text-sm text-ok"><MonitorCheck className="size-4" aria-hidden />Following the shared screen</span> : <span className="inline-flex items-center gap-1 text-sm text-warn"><Footprints className="size-4" aria-hidden />You stepped away; the screen moves on without you</span>}
              <span className="flex-1" />
              {following ? <Button size="sm" variant="outline" onClick={() => setFollowing(false)} disabled={!cid || all.length < 2} title="Look at the other slides on your own"><Footprints className="size-4" />Step away</Button> : <Button size="sm" onClick={() => setFollowing(true)} data-testid="back-to-shared"><MonitorCheck className="size-4" />Back to the shared screen</Button>}
              <Button size="sm" variant="ghost" onClick={() => presentM.mutate(inRoom ? "remote" : "room")} disabled={presentM.isPending || s.meeting.status === "closed"} aria-pressed={inRoom} title="Tell the coordinator whether you are physically in the room">{inRoom ? "I am remote" : "I am in the room"}</Button>
            </div>
            {presentM.isError ? <p role="alert" className="text-xs text-bad">{errorText(presentM.error)}</p> : null}
            <section className="surface min-h-72 overflow-hidden relative" aria-label="Shared screen" data-testid="member-screen">
              <AnimatePresence mode="wait">
                {viewer ? (
                  <motion.iframe key="img" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} title={`Image viewer${opened?.title ? `: ${opened.title}` : ""}`} src={viewer} className="h-[60dvh] w-full bg-black" allow="fullscreen" />
                ) : following && opened?.kind === "record" && opened.doc_id && cid ? (
                  <motion.div key="rec" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="max-h-[60dvh] overflow-auto bg-muted p-2">
                    {opened.title ? <p className="mb-1 text-sm font-medium">{opened.title}</p> : null}
                    <img src={recordPageUrl(cid, opened.doc_id, opened.page ?? 0)} alt={`${opened.title ?? "Record"}, page ${(opened.page ?? 0) + 1}`} className="mx-auto max-w-full h-auto" />
                  </motion.div>
                ) : shown ? (
                  <motion.div key={shown.id} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} className="p-4"><SlideContent slide={shown} /></motion.div>
                ) : (
                  <motion.div key="none" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-6 text-center text-sm text-muted-foreground">{cid ? (slides.isLoading ? "Loading the slides" : slides.isError ? `The slides could not be loaded: ${errorText(slides.error)}` : "Nothing on the screen yet.") : "The shared screen is empty until the coordinator picks a case."}</motion.div>
                )}
              </AnimatePresence>
              {!following && all.length > 1 ? (
                <div className="flex items-center justify-between border-t border-border px-3 py-2">
                  <Button size="sm" variant="ghost" onClick={() => setMySlide((i) => Math.max(0, i - 1))} disabled={mySlide <= 0}><ArrowLeft className="size-4" />Previous</Button>
                  <span className="text-xs text-muted-foreground">{mySlide + 1} of {all.length}{mySlide === sharedSlide ? ", same as the screen" : `, the screen shows ${sharedSlide + 1}`}</span>
                  <Button size="sm" variant="ghost" onClick={() => setMySlide((i) => Math.min(all.length - 1, i + 1))} disabled={mySlide >= all.length - 1}>Next<ArrowRight className="size-4" /></Button>
                </div>
              ) : null}
            </section>
            <section className="surface p-3" aria-label="Questions">
              <h2 className="text-sm font-semibold mb-1">Questions</h2>
              <QuestionsList questions={s.questions ?? []} caseId={cid} emptyText="No questions on this case yet." />
              <form className="mt-2 flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (question.trim().length >= 3) ask.mutate(question.trim()); }}>
                <label htmlFor="member-q" className="sr-only">Type a question</label>
                <Textarea id="member-q" value={question} onChange={(e) => setQuestion(e.target.value)} className="min-h-12 text-sm" placeholder="Type a question; it shows on the room screen with your name" maxLength={500} disabled={ask.isPending || !inSession || !cid} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (question.trim().length >= 3) ask.mutate(question.trim()); } }} />
                <div className="flex items-center gap-2">
                  {ask.isError ? <p role="alert" className="text-xs text-bad flex-1">{errorText(ask.error)}</p> : <span className="flex-1 text-xs text-muted-foreground">{!inSession ? "Questions open when the meeting starts." : !cid ? "Questions open when a case is on the screen." : s.agent?.active ? "The stand-in answers from the records only." : ""}</span>}
                  <LoadingButton size="sm" type="submit" loading={ask.isPending} loadingText="Sending" disabled={question.trim().length < 3 || !inSession || !cid} data-testid="send-question"><SendHorizontal className="size-4" />Send question</LoadingButton>
                </div>
              </form>
            </section>
          </div>
          <div className="lg:col-span-4 space-y-3">
            <section className="surface p-3 space-y-2" aria-label="Taking part">
              <LoadingButton className="w-full" variant={hand ? "secondary" : "default"} loading={handM.isPending} onClick={() => handM.mutate(!hand)} aria-pressed={hand} disabled={!inSession} data-testid="raise-hand"><Hand className={cn("size-4", hand && "animate-bounce")} />{hand ? "Lower hand" : "Raise hand"}</LoadingButton>
              {handM.isError ? <p role="alert" className="text-xs text-bad">{errorText(handM.error)}</p> : null}
              {cid && (s.ended ?? []).includes(cid) && (s.can?.card || s.can?.card_required) ? <Button size="sm" variant="outline" className="w-full" onClick={() => setCard({ caseId: cid, patientLine: row?.patient_line || cid })}><Vote className="size-4" />Give your card for this case</Button> : null}
              <MembersStrip attendance={s.attendance} hands={s.hands} />
              <AgentTile agent={s.agent} />
            </section>
            {videoOn ? <Suspense fallback={<div className="surface p-3 text-xs text-muted-foreground">Loading the video</div>}><VideoTiles mid={id} enabled={videoOn} /></Suspense> : null}
            {s.meeting.video && !me?.features?.video ? <p className="text-xs text-muted-foreground px-1">Video is on for this meeting but not set up on this server. You can follow the screen and type questions.</p> : null}
            {s.meeting.video && inRoom ? <p className="text-xs text-muted-foreground px-1">You are in the room, so video stays off on this device.</p> : null}
          </div>
        </div>
      )}
      {card ? <CardDialog mid={id} caseId={card.caseId} patientLine={card.patientLine} required={!!s.can?.card_required} open onOpenChange={(o) => { if (!o) setCard(null); }} onSent={() => announce("Card sent.")} /> : null}
    </div>
  );
}
