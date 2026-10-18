// /meetings/:id/room: the room computer. Full screen, big type, no shell chrome (a fixed layer above the shell plus a
// class on body). The summary on the left; the opened record, the image viewer or the picked slide on the right; timer,
// members online, the stand-in tile only when active, questions and answers, the live decision strip at the bottom.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Maximize2, Minimize2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useMeetingLive } from "@/lib/live";
import { getSlides, recordPageUrl, viewerSrc } from "./api";
import { AgentTile, LiveDot, MembersStrip, QuestionsList, SlideContent, TimerBadge } from "./components/shared";
import { ErrorState, SkeletonLines, fmtDate } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

function useFullScreenLayer() {
  useEffect(() => {
    document.body.classList.add("tbnik-fullscreen");
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.classList.remove("tbnik-fullscreen"); document.body.style.overflow = prev; };
  }, []);
}

export default function MeetingRoomPage() {
  const { id = "" } = useParams();
  useFullScreenLayer();
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

  const toggleFs = async () => {
    try { if (!document.fullscreenElement) await document.documentElement.requestFullscreen(); else await document.exitFullscreen(); } catch { /* the browser refused; the layer still fills the window */ }
  };

  const row = s ? [...s.agenda.discussion, ...s.agenda.noting].find((r) => r.case_id === cid) : undefined;
  const all = slides.data?.slides ?? [];
  const summary = all.find((x) => x.kind === "summary") ?? all[0] ?? null;
  const current = all[slideIdx] ?? null;
  const rightSlide = current && current !== summary ? current : null;
  const viewer = opened?.kind === "images" ? viewerSrc(opened) : null;
  const live_text = s?.decision_live && (!s.decision_live.case_id || s.decision_live.case_id === cid) ? s.decision_live.text : "";
  const headline = row ? row.patient_line : s?.meeting.status === "closed" ? "Meeting closed" : s?.meeting.status === "cancelled" ? "Meeting cancelled" : s?.meeting.status === "planned" ? "Waiting for the coordinator to start" : "No case on the screen yet";

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background text-foreground overflow-hidden" data-testid="room-screen" data-meeting-status={s?.meeting.status}>
      <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border px-3 py-2 lg:px-5 lg:py-3">
        <div className="min-w-0 flex-1 basis-64">
          <p className="text-sm text-muted-foreground">Tumour Board{s ? `, ${fmtDate(s.meeting.date)}${s.meeting.time ? ` ${s.meeting.time}` : ""}${s.meeting.room ? `, ${s.meeting.room}` : ""}` : ""}</p>
          <h1 className="text-2xl lg:text-3xl truncate">{headline}</h1>
          {row?.board_question ? <p className="text-lg lg:text-xl text-foreground/90 truncate"><span className="text-muted-foreground">Board question: </span>{row.board_question}</p> : null}
        </div>
        <TimerBadge timer={s?.current?.timer} big />
        <LiveDot status={live.status} detail={live.statusDetail} />
        <Button variant="ghost" size="icon" onClick={() => void toggleFs()} aria-label={fs ? "Leave full screen" : "Full screen"} title={fs ? "Leave full screen" : "Full screen"}>{fs ? <Minimize2 className="size-5" /> : <Maximize2 className="size-5" />}</Button>
        <Button asChild variant="ghost" size="icon" aria-label="Close the room screen" title="Close the room screen"><Link to={`/meetings/${id}`}><X className="size-5" /></Link></Button>
      </header>

      {live.notBuilt ? <div className="p-8"><ErrorState error={live.error} title="The meeting rooms are not on this server yet" /></div> : null}
      {live.missing && !s ? <div className="p-8"><ErrorState error={live.error} title="This meeting does not exist" /></div> : null}
      {live.forbidden && !s ? <div className="p-8"><ErrorState error={live.error} title="This computer is not signed in as a member of the meeting" /></div> : null}
      {live.error && !s && !live.notBuilt && !live.missing && !live.forbidden ? <div className="p-8"><ErrorState error={live.error} retry={() => void live.refresh()} /></div> : null}
      {live.isLoading ? <div className="p-8"><SkeletonLines n={6} /></div> : null}

      {s ? (
        <main className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-3 lg:gap-4 p-3 lg:p-5 overflow-y-auto lg:overflow-hidden">
          <section className="lg:col-span-5 min-h-0 overflow-y-auto surface p-4 lg:p-5" aria-label="Summary" data-testid="room-summary">
            {!cid ? <p className="text-xl text-muted-foreground">The summary of the current case appears here.</p> : null}
            {cid && slides.isLoading ? <SkeletonLines n={8} /> : null}
            {cid && slides.isError ? <p className="text-lg text-warn">The slides for this case could not be loaded.</p> : null}
            {summary ? <SlideContent slide={summary} big /> : null}
          </section>
          <section className="lg:col-span-7 min-h-0 flex flex-col gap-3">
            <div className="flex-1 min-h-[50dvh] lg:min-h-0 surface overflow-hidden relative" aria-label="Shared screen" data-testid="shared-screen" data-opened={opened?.kind ?? "slide"}>
              <AnimatePresence mode="wait">
                {viewer ? (
                  <motion.iframe key={`img-${viewer}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} title={`Image viewer${opened?.title ? `: ${opened.title}` : ""}`} src={viewer} className="absolute inset-0 h-full w-full bg-black" allow="fullscreen" />
                ) : opened?.kind === "record" && opened.doc_id && cid ? (
                  <motion.div key={`rec-${opened.doc_id}-${opened.page ?? 0}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 overflow-auto bg-muted p-2">
                    {opened.title ? <p className="sticky top-0 mb-2 inline-block rounded-md bg-card/90 px-2 py-1 text-base font-medium shadow-[var(--shadow-outer)]">{opened.title}</p> : null}
                    <img src={recordPageUrl(cid, opened.doc_id, opened.page ?? 0)} alt={`${opened.title ?? "Record"}, page ${(opened.page ?? 0) + 1}`} className="mx-auto h-auto max-w-full" />
                  </motion.div>
                ) : rightSlide ? (
                  <motion.div key={`slide-${rightSlide.id}`} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} className="absolute inset-0 overflow-y-auto p-6">
                    <SlideContent slide={rightSlide} big />
                  </motion.div>
                ) : (
                  <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 grid place-items-center p-6 text-center">
                    <p className="text-xl text-muted-foreground">{cid ? "The coordinator can show a slide, a record or the images here." : "Waiting for the first case."}</p>
                  </motion.div>
                )}
              </AnimatePresence>
              {all.length > 1 ? (
                <ol className="absolute bottom-2 right-3 flex gap-1" aria-label="Slides">
                  {all.map((x, i) => <li key={x.id} className={cn("h-1.5 rounded-full transition-all", i === slideIdx ? "w-6 bg-primary" : "w-2 bg-border-strong")} aria-current={i === slideIdx ? "true" : undefined} title={x.title} />)}
                </ol>
              ) : null}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 lg:max-h-56 min-h-0">
              <div className={cn("surface p-3 overflow-y-auto", s.agent?.active ? "sm:col-span-8" : "sm:col-span-12")} aria-label="Questions">
                <h2 className="text-base mb-1">Questions from members</h2>
                <QuestionsList questions={s.questions ?? []} caseId={cid} big emptyText="Members type their questions; they appear here with the answer." />
              </div>
              {s.agent?.active ? <div className="sm:col-span-4"><AgentTile agent={s.agent} big /></div> : null}
            </div>
          </section>
        </main>
      ) : <div className="flex-1" />}

      <footer className="border-t border-border px-3 py-2 lg:px-5 lg:py-3 space-y-2">
        <MembersStrip attendance={s?.attendance ?? []} hands={s?.hands} big />
        <div className={cn("rounded-md border-2 px-4 py-2 min-h-14 flex items-start gap-3", savedFlash ? "border-ok bg-ok-soft" : live_text ? "border-warn bg-warn-soft/60" : "border-dashed border-border")} role="status" aria-live="polite" data-testid="decision-strip" data-saved={savedFlash}>
          <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-sm font-medium mt-0.5", savedFlash ? "status-ok" : "status-warn")}>{savedFlash ? "saved" : "not saved"}</span>
          <p className="text-base lg:text-xl leading-snug text-foreground min-w-0">{savedFlash ? "The decision was read back and saved." : live_text || <span className="text-muted-foreground">The decision appears here as the coordinator types it, until it is read back and saved.</span>}</p>
        </div>
      </footer>
    </div>
  );
}
