// The coordinator's view during a meeting, laid out like a call with a conduct panel: on the left what the room sees (the shared
// screen) with the people's tiles under it; on the right the panel with its tabs: Share (the case, the slide, a record, the
// images, the timer), Decision (the form, the cards), People (admit, hands), Questions, Agenda. The control bar carries the
// microphone and camera, previous and next case, the timer, End case and End meeting.
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Camera, CameraOff, ChevronLeft, ChevronRight, ClipboardList, DoorOpen, Images, ListOrdered, MessageSquareText, Mic, MicOff, MonitorOff, MonitorUp, Pause, Play, RotateCcw, StopCircle, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useSession } from "@/lib/session";
import { handUsers, type LiveStatus, type MeetingState } from "@/lib/live";
import { recallChoice, useVideoRoom, type JoinChoice } from "@/lib/video";
import { admit, endCase, endMeeting, getCards, getSlides, openOnScreen, setCurrent, timer as timerCall } from "../api";
import { getCase } from "@/features/casefile/api";
import { DecisionForm } from "./DecisionForm";
import { PeopleList } from "./People";
import { PreJoin } from "./PreJoin";
import { BarButton, ControlBar, DecisionStrip, SharedScreen, SlideDots, StageFrame, StageTopBar } from "./Stage";
import { TileGrid, tilePeople } from "./VideoTiles";
import { AgentTile, LiveDot, QuestionsList, TimerBadge } from "./shared";
import { LoadingButton, StatusChip, errorText, fmtDate, niceTitle, useAnnounce } from "@/features/casefile/components/common";
import { docStatusChip } from "@/features/casefile/components/SourceViewer";
import { cn } from "@/lib/utils";

type Tab = "share" | "decision" | "people" | "questions" | "agenda";
const TABS: Array<{ id: Tab; label: string; icon: typeof MonitorUp }> = [
  { id: "share", label: "Share", icon: MonitorUp },
  { id: "decision", label: "Decision", icon: ClipboardList },
  { id: "people", label: "People", icon: Users },
  { id: "questions", label: "Questions", icon: MessageSquareText },
  { id: "agenda", label: "Agenda", icon: ListOrdered },
];

export function ControlView({ mid, state, onChanged, liveStatus = "open", liveDetail }: { mid: string; state: MeetingState; onChanged: () => void; liveStatus?: LiveStatus; liveDetail?: string }) {
  const nav = useNavigate();
  const { me } = useSession();
  const order = useMemo(() => [...state.agenda.discussion, ...state.agenda.noting], [state.agenda]);
  const cid = state.current?.case_id ?? null;
  const idx = order.findIndex((r) => r.case_id === cid);
  const row = idx >= 0 ? order[idx] : null;
  const [minutes, setMinutes] = useState<number>(row?.minutes ?? state.meeting.minutes_per_case ?? 10);
  useEffect(() => { setMinutes(row?.minutes ?? state.meeting.minutes_per_case ?? 10); }, [cid]); // eslint-disable-line react-hooks/exhaustive-deps
  const [tab, setTab] = useState<Tab>("share");
  const [endOpen, setEndOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [announce, liveNode] = useAnnounce();
  const [choice, setChoice] = useState<JoinChoice | null | "skipped">(() => recallChoice());
  const wrap = <T,>(fn: () => Promise<T>) => async () => { setErr(null); try { const r = await fn(); onChanged(); return r; } catch (e) { setErr(errorText(e)); throw e; } };

  const go = useMutation({ mutationFn: (c: { case_id: string; slide?: number }) => wrap(() => setCurrent(mid, c.case_id, c.slide))(), onSuccess: (_r, c) => announce(c.slide !== undefined ? `Slide ${c.slide + 1} on the screen.` : "Next case on the screen.") });
  const tm = useMutation({ mutationFn: (a: "start" | "stop" | "reset") => wrap(() => timerCall(mid, a, a === "start" || a === "reset" ? minutes : undefined))() });
  const adm = useMutation({ mutationFn: (u: string) => wrap(() => admit(mid, u))(), onSuccess: () => announce("Admitted.") });
  const open = useMutation({ mutationFn: (o: { kind: "record" | "images" | "none"; doc_id?: string }) => wrap(() => openOnScreen(mid, o.kind, o.doc_id))(), onSuccess: (_r, o) => announce(o.kind === "none" ? "The shared screen shows the slide again." : o.kind === "images" ? "The images are on the shared screen." : "The record is on the shared screen.") });
  const end = useMutation({ mutationFn: () => wrap(() => endCase(mid, cid!))(), onSuccess: (r) => announce(r?.cards_requested?.length ? `Cards asked of ${r.cards_requested.length} board heads.` : "Discussion ended.") });
  const finish = useMutation({ mutationFn: () => wrap(() => endMeeting(mid))(), onSuccess: () => setEndOpen(false) });

  const slides = useQuery({ queryKey: ["slides", mid, cid], queryFn: () => getSlides(mid, cid!), enabled: !!cid, retry: false, staleTime: 60_000 });
  const cf = useQuery({ queryKey: ["case", cid], queryFn: () => getCase(cid!), enabled: !!cid, retry: false, staleTime: 60_000 });
  const cards = useQuery({ queryKey: ["cards", mid], queryFn: () => getCards(mid), retry: false, refetchInterval: 15_000 });
  const videoAvailable = !!state.meeting.video && !!me?.features?.video;
  const joinChoice = choice && choice !== "skipped" ? choice : null;
  const video = useVideoRoom(mid, videoAvailable && !!joinChoice, joinChoice ?? {});

  const waiting = state.attendance.filter((a) => a.status === "waiting");
  const hands = handUsers(state.hands);
  const people = tilePeople(state.attendance, hands, me?.user);
  const docs = (cf.data?.documents ?? []).filter((d) => d.state === "ready" && !d.superseded);
  const opened = state.current?.opened;
  const caseCards = cid ? cards.data?.cards?.[cid] : undefined;
  const ended = !!cid && (state.ended ?? []).includes(cid);
  const outcome = cid ? state.outcomes?.[cid] : undefined;
  const all = slides.data?.slides ?? [];
  const slideIdx = state.current?.slide ?? 0;
  const liveText = state.decision_live && (!state.decision_live.case_id || state.decision_live.case_id === cid) ? state.decision_live.text : "";
  const questions = (state.questions ?? []).filter((q) => !cid || !q.case_id || q.case_id === cid);

  if (videoAvailable && !choice) {
    return <PreJoin title={`Conduct the Tumour Board, ${fmtDate(state.meeting.date)}${state.meeting.time ? ` at ${state.meeting.time}` : ""}`} subtitle="The remote members see and hear you from here. Check the camera and microphone first." onJoin={(c) => setChoice(c)} onSkip={() => setChoice("skipped")} />;
  }

  return (
    <StageFrame testId="control-view">
      {liveNode}
      <StageTopBar
        left={<span className="hidden text-sm text-stage-muted sm:inline">Conducting · {fmtDate(state.meeting.date)}{state.meeting.time ? ` ${state.meeting.time}` : ""}{state.meeting.room ? ` · ${state.meeting.room}` : ""}</span>}
        center={<div className="min-w-0">{row ? <><p className="truncate text-sm font-semibold text-stage-fg">{idx + 1} of {order.length}: {row.patient_line}</p><p className="truncate text-xs text-stage-muted">{row.board_question ? `Board question: ${row.board_question}` : "The board question is not written on this Case File"}</p></> : <p className="text-sm text-stage-muted">No case on the screen yet: pick one from the Agenda tab or press Next.</p>}</div>}
        right={<>
          <TimerBadge timer={state.current?.timer} />
          <LiveDot status={liveStatus} detail={liveDetail} />
          <Button asChild size="sm" variant="ghost" className="hidden text-stage-fg hover:bg-stage-raised hover:text-stage-fg md:inline-flex"><Link to={`/meetings/${mid}/room`} target="_blank" rel="noopener" title="Opens the full-screen room screen in a new tab, for the room computer"><MonitorUp className="size-4" />Room screen</Link></Button>
        </>}
      />

      <main className="scroll-thin flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 lg:flex-row lg:overflow-hidden">
        <div className="flex min-h-[46vh] min-w-0 flex-1 flex-col gap-2 lg:min-h-0">
          <SharedScreen cid={cid} opened={opened} slide={all[slideIdx] ?? null} empty={cid ? "Pick a slide, a record or the images in the Share tab." : "Waiting for the first case."} label={<span className="rounded-full bg-black/50 px-2.5 py-1 text-xs font-medium text-white">What the room sees</span>}>
            <SlideDots slides={all} index={slideIdx} className="absolute bottom-2 right-3" />
            {waiting.length && tab !== "people" ? (
              <ul className="absolute bottom-3 left-3 z-10 space-y-1.5" data-testid="waiting-banner" aria-label="Waiting to be admitted">
                {waiting.slice(0, 3).map((a) => (
                  <li key={a.user} className="flex items-center gap-2 rounded-xl border border-stage-line bg-stage-panel/95 px-3 py-2 text-sm shadow-[var(--shadow-lift)] backdrop-blur">
                    <span className="min-w-0"><span className="font-medium">{a.name}</span>{a.department_name || a.department ? <span className="text-stage-muted"> ({a.department_name ?? a.department})</span> : null} wants to join</span>
                    <LoadingButton size="xs" loading={adm.isPending && adm.variables === a.user} onClick={() => adm.mutate(a.user)}>Admit</LoadingButton>
                  </li>
                ))}
                {waiting.length > 3 ? <li className="px-1 text-xs text-stage-muted">and {waiting.length - 3} more in People</li> : null}
              </ul>
            ) : null}
          </SharedScreen>
          {liveText ? <DecisionStrip text={liveText} saved={false} /> : null}
          <div className="shrink-0"><TileGrid room={video.room} people={people} layout="row" size="sm" max={10} /></div>
        </div>

        <aside className="flex min-h-[50vh] w-full shrink-0 flex-col rounded-xl border border-stage-line bg-stage-panel lg:min-h-0 lg:w-[26rem]" data-testid="conduct-panel">
          <div className="scroll-thin flex items-center gap-0.5 overflow-x-auto border-b border-stage-line p-1" role="tablist" aria-label="Conduct">
            {TABS.map((t) => {
              const badge = t.id === "people" ? waiting.length : t.id === "questions" ? questions.filter((q) => !q.answer).length : 0;
              return (
                <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} className={cn("relative flex min-w-[4.2rem] flex-1 flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 text-[11px] font-medium transition-colors", tab === t.id ? "bg-stage-raised text-stage-fg" : "text-stage-muted hover:text-stage-fg")}>
                  <t.icon className="size-4" aria-hidden />{t.label}
                  {badge ? <span className="absolute right-1.5 top-1 min-w-4 rounded-full bg-warn px-1 text-center text-[10px] font-bold leading-4 text-white">{badge}</span> : null}
                </button>
              );
            })}
          </div>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3" data-theme="dark">
            {tab === "share" ? (
              <div className="space-y-4">
                <section>
                  <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Timer</h3>
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="inline-flex items-center gap-1 text-xs text-muted-foreground">minutes <Input type="number" min={1} max={60} value={minutes} onChange={(e) => setMinutes(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} className="h-7 w-16 text-sm" aria-label="Minutes for this case" /></label>
                    {state.current?.timer?.running ? <Button size="xs" variant="outline" onClick={() => tm.mutate("stop")} disabled={tm.isPending}><Pause className="size-3" />Stop</Button> : <Button size="xs" variant="outline" onClick={() => tm.mutate("start")} disabled={tm.isPending || !cid}><Play className="size-3" />Start</Button>}
                    <Button size="xs" variant="ghost" onClick={() => tm.mutate("reset")} disabled={tm.isPending || !cid}><RotateCcw className="size-3" />Reset</Button>
                  </div>
                </section>
                <section>
                  <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Slide on the screen</h3>
                  {slides.isLoading ? <div className="skeleton-line h-7 w-64" /> : null}
                  {slides.isError ? <p className="text-xs text-warn">Slides are not available for this case: {errorText(slides.error)}</p> : null}
                  <div className="flex flex-wrap gap-1" role="group" aria-label="Slide picker">
                    {all.map((s, i) => (
                      <button key={s.id} type="button" aria-pressed={slideIdx === i && (!opened || opened.kind === "none")} onClick={() => go.mutate({ case_id: cid!, slide: i })} disabled={go.isPending} className={cn("rounded-md border px-2 py-1 text-xs transition active:scale-95 disabled:opacity-60", slideIdx === i ? "border-primary bg-secondary text-secondary-foreground" : "border-border hover:bg-muted")}>{i + 1}. {s.title}</button>
                    ))}
                  </div>
                </section>
                <section>
                  <div className="mb-1 flex items-center gap-2">
                    <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Records and images</h3>
                    <span className="flex-1" />
                    {opened && opened.kind !== "none" ? <Button size="xs" variant="outline" onClick={() => open.mutate({ kind: "none" })} disabled={open.isPending}><MonitorOff className="size-3" />Back to the slide</Button> : <StatusChip kind="muted">slide only</StatusChip>}
                  </div>
                  <ul className="divide-y divide-border rounded-md border border-border" aria-label="Records of this Case File">
                    {cf.isLoading ? <li className="p-2"><div className="skeleton-line h-4 w-3/4" /></li> : null}
                    {cf.isError ? <li className="p-2 text-xs text-warn">The records could not be listed: {errorText(cf.error)}</li> : null}
                    {!cf.isLoading && !cf.isError && docs.length === 0 ? <li className="p-2 text-xs text-muted-foreground">No records to open{cid ? "" : ": pick a case first"}.</li> : null}
                    {docs.map((d) => {
                      const title = niceTitle(d.classification?.title ?? d.filename);
                      const onScreen = opened?.doc_id === d.doc_id;
                      return (
                        <li key={d.doc_id} className={cn("flex items-center gap-2 px-2 py-1.5 text-xs", onScreen && "bg-secondary/60")}>
                          <span className="min-w-0 flex-1 truncate">{title}</span>
                          {docStatusChip(d)}
                          <Button size="xs" variant={onScreen && opened?.kind === "record" ? "secondary" : "ghost"} onClick={() => open.mutate({ kind: "record", doc_id: d.doc_id })} disabled={open.isPending} aria-label={`Show ${title} on the screen`}><MonitorUp className="size-3" />Show</Button>
                          {d.his?.imaging_study_ref ? <Button size="xs" variant={onScreen && opened?.kind === "images" ? "secondary" : "ghost"} onClick={() => open.mutate({ kind: "images", doc_id: d.doc_id })} disabled={open.isPending} aria-label={`Show the images of ${title} on the screen`}><Images className="size-3" />Images</Button> : null}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              </div>
            ) : null}
            {tab === "decision" ? (
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-foreground">Decision{row ? ` for ${row.patient_line}` : ""}</h3>
                {outcome ? <p className="rounded-md status-ok px-2 py-1 text-sm">Recorded: {outcome.label ?? outcome.outcome}. Saving again records a correction.</p> : null}
                {cid ? <DecisionForm mid={mid} caseId={cid} attendance={state.attendance} onSaved={onChanged} liveText={state.decision_live?.case_id && state.decision_live.case_id !== cid ? undefined : state.decision_live?.text} canRecord={state.can?.record !== false} compact /> : <p className="text-sm text-muted-foreground">Pick a case first.</p>}
                <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
                  <LoadingButton size="sm" variant="outline" loading={end.isPending} onClick={() => end.mutate()} disabled={!cid} title="Asks each board head for their card (Agree / Concern)" data-testid="end-case"><StopCircle className="size-4" />{ended ? "Ask for the cards again" : "End case, ask for cards"}</LoadingButton>
                  {caseCards ? (
                    <span className="text-xs text-muted-foreground" data-testid="cards-summary">
                      {caseCards.cards.length ? `Cards: ${caseCards.cards.map((c) => `${c.name ?? c.user} ${c.agree ? "agrees" : "has a concern"}`).join("; ")}.` : "No cards yet."}
                      {caseCards.missing.length ? ` Waiting for ${caseCards.missing.length}.` : caseCards.cards.length ? " Every head has given a card." : ""}
                    </span>
                  ) : null}
                </div>
              </div>
            ) : null}
            {tab === "people" ? (
              <div className="space-y-3">
                <div className="-m-3 mb-0 p-3" data-theme="dark">
                  <PeopleList attendance={state.attendance} hands={hands} me={me?.user} canAdmit onAdmit={(u) => adm.mutate(u)} admitting={adm.isPending ? (adm.variables as string) : null} />
                </div>
                <AgentTile agent={state.agent} />
              </div>
            ) : null}
            {tab === "questions" ? <QuestionsList questions={state.questions ?? []} caseId={cid} emptyText="No questions on this case yet." /> : null}
            {tab === "agenda" ? (
              <ol className="space-y-1 text-sm">
                {order.map((r, i) => (
                  <li key={r.case_id} className={cn("flex items-center gap-2 rounded-md px-2 py-1.5", r.case_id === cid ? "bg-secondary" : "")}>
                    <span className="w-5 text-xs tabular-nums text-muted-foreground">{i + 1}.</span>
                    <button type="button" className="flex-1 truncate text-left hover:underline underline-offset-2 disabled:opacity-60" onClick={() => go.mutate({ case_id: r.case_id })} disabled={go.isPending || r.case_id === cid} title={r.case_id === cid ? "On the screen" : "Put this case on the screen"}>{r.patient_line || r.case_id}</button>
                    {r.decided || r.outcome ? <StatusChip kind="ok">{r.outcome_label ?? r.outcome?.replace(/_/g, " ") ?? "decided"}</StatusChip> : null}
                    <Link to={`/cases/${r.case_id}`} className="shrink-0 text-xs text-link underline" title="Open the Case File">Case File</Link>
                  </li>
                ))}
                {state.meeting.started_at ? <li className="pt-2 text-xs text-muted-foreground">Started {fmtDate(state.meeting.started_at)}</li> : null}
              </ol>
            ) : null}
            {err ? <p role="alert" className="mt-3 text-xs text-bad">{err}</p> : null}
          </div>
        </aside>
      </main>

      <ControlBar
        left={video.error ? <p role="alert" className="truncate text-xs text-[#ffb4a8]">{video.error}</p> : video.status === "connected" ? <span className="text-xs text-stage-muted">Video on the hospital's server</span> : null}
        right={<Button size="sm" variant="ghost" className="text-stage-muted hover:bg-stage-raised hover:text-stage-fg" onClick={() => nav("/meetings")}>Leave the controls</Button>}
      >
        {videoAvailable && joinChoice ? (
          <>
            <BarButton icon={video.micOn ? Mic : MicOff} label={video.micOn ? "Mute" : "Unmute"} active={!video.micOn} onClick={() => void video.toggleMic()} disabled={video.status !== "connected"} testId="mic" />
            <BarButton icon={video.camOn ? Camera : CameraOff} label={video.camOn ? "Camera" : "Camera off"} active={!video.camOn} onClick={() => void video.toggleCam()} disabled={video.status !== "connected"} testId="cam" />
          </>
        ) : videoAvailable ? <BarButton icon={Camera} label="Join video" onClick={() => setChoice(null)} /> : null}
        <BarButton icon={ChevronLeft} label="Previous" onClick={() => idx > 0 && go.mutate({ case_id: order[idx - 1].case_id })} disabled={idx <= 0 || go.isPending} />
        <BarButton icon={ChevronRight} label={idx < 0 ? "First case" : "Next"} tone={idx < 0 ? "primary" : "default"} onClick={() => go.mutate({ case_id: order[Math.min(order.length - 1, idx + 1)].case_id })} disabled={order.length === 0 || idx >= order.length - 1 || go.isPending} testId="next-case" />
        <BarButton icon={state.current?.timer?.running ? Pause : Play} label={state.current?.timer?.running ? "Stop timer" : "Timer"} onClick={() => tm.mutate(state.current?.timer?.running ? "stop" : "start")} disabled={tm.isPending || !cid} />
        <BarButton icon={StopCircle} label="End case" onClick={() => end.mutate()} disabled={!cid || end.isPending} />
        <BarButton icon={DoorOpen} label="End meeting" tone="danger" onClick={() => setEndOpen(true)} testId="end-meeting" />
      </ControlBar>

      <Dialog open={endOpen} onOpenChange={(o) => { if (!finish.isPending) setEndOpen(o); }}>
        <DialogContent aria-describedby="end-desc">
          <DialogHeader><DialogTitle>End the meeting?</DialogTitle><DialogDescription id="end-desc">The outcomes already saved go to the owners. Case Files without a saved outcome keep their place; mark them Not discussed first to move them to the next meeting.</DialogDescription></DialogHeader>
          <p className="text-sm">{order.filter((r) => r.decided || r.outcome).length} of {order.length} Case Files have a saved outcome.</p>
          {finish.isError ? <p role="alert" className="text-sm text-bad">{errorText(finish.error)}</p> : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEndOpen(false)} disabled={finish.isPending}>Keep going</Button>
            <LoadingButton variant="destructive" loading={finish.isPending} loadingText="Ending" onClick={() => finish.mutate()}>End meeting</LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </StageFrame>
  );
}
