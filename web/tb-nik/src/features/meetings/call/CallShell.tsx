// The call shell (night-v3 5.1, research/04 section 6): one in-call layout for the member view, the coordinator's control view and
// (in its own variant) the room screen. It builds the call context (types.ts CallCtx) every piece reads, wires the actions to the
// meeting API, and lays out the top bar, the agenda rail, the slide tabs, the stage with its overlays, the participant strip, the
// decision strip, one side panel, the control bar, the More menu and the dialogs. The room variant has no control bar: a small bar
// at the bottom right (room microphone and camera, the summary column, the agent voices, full screen, close).
// Voice (night-v3 4.4): while the person dictates in the call, the call microphone is muted and comes back after (useDictationGuard).
// Phone and room screen (night-v3 5.5, research/04 sections 6.4, 6.5 and 7): on a phone the top bar and the control bar fade after
// 4 s without a touch and come back on a tap (never while a panel, a sheet or a dialog is open, the hand is raised, the person
// dictates or a screen is shared; the layout keeps its place), the decision strip is one line that opens on a tap, and in landscape
// the strip is a column at the right edge. The room screen (a projector, 1920 x 1080) has large type, a compact agenda column, at
// most six remote tiles with "+n more", the latest two questions, nothing that scrolls the page, and a wake lock while it is open.
// Night-v3 5.6: when the meeting is closed or cancelled the member and the room screen see "The meeting has ended" over the stage
// (the member's bar keeps Leave only); "N in the meeting" counts the admitted attendance plus anyone in the video who is not on it
// (people only, never a room screen); the call is a labelled section, not a second main landmark.
// Night-v3 6.1: the agents' voice. Each "agent_speech" event of the Case File on the floor names a sentence that this device fetches
// by reference and plays when agent voices are on here (agentSpeaker.ts), reporting playback so "Speaking" is true; "agent_stop",
// Esc, voices off, the case changing, Leave and the meeting ending stop it. A browser that blocks sound until a tap shows
// "Tap to allow agent voices". The coordinator's agent actions (add, remove, members may ask) and everyone's (listening, present
// your points, stop for everyone) go through the meeting API like the other actions.
import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, Camera, CameraOff, Footprints, LogOut, Maximize2, Mic, MicOff, Minimize2, MonitorCheck, MonitorUp, PanelLeft, Volume2, VolumeX, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { handUsers, type AgentInfo, type LiveEvent, type LiveStatus, type MeetingState, type ReactionEvent } from "@/lib/live";
import type { Me } from "@/lib/session";
import { useVideoRoom, type JoinChoice } from "@/lib/video";
import { useDictationGuard } from "@/hooks/useDictationGuard";
import { useIsDesktop, useMediaQuery } from "@/hooks/useMediaQuery";
import { SkeletonLines, errorText, useAnnounce } from "@/features/casefile/components/common";
import { admit, agentAudio, agentListening as agentListeningCall, allowPresent, askQuestion, endCase as endCaseCall, getSlides, openOnScreen, present, presentPoints as presentPointsCall, raiseHand, sendChat, sendReaction, setAgent as setAgentCall, setAgentSettings, setCurrent, setPresenting, setSpotlight, stopAgent as stopAgentCall, timer as timerCall } from "../api";
import { isSpeaking, primeAudio, speak, VOICE_TEXT } from "@/lib/voice";
import { onTheFloor, speechItem, useAgentSpeaker } from "./agentSpeaker";
import { CardDialog } from "../components/CardDialog";
import { CaseFlow } from "./CaseFlow";
import { ControlBar, DecisionStrip, SlideDots, StageFrame } from "../components/Stage";
import { QuestionsList, SlideContent } from "../components/shared";
import { CallContext, useCall } from "./context";
import type { CallActions, CallCtx, CallVariant, CallVideo, ReactionKind } from "./types";
import { ShellContext, useCallState, useControlsAutoHide, useMeetingCount, useSaveData, useShortcuts, useWakeLock, type ShellExtras } from "./useCallState";
import { TopBar } from "./TopBar";
import { AgendaRail } from "./AgendaRail";
import { StageTabs } from "./StageTabs";
import { AdmitToast } from "./AdmitToast";
import { CallBar, RoundButton } from "./CallBar";
import { ShortcutsDialog } from "./ShortcutsDialog";
import { EndMeetingDialog } from "./EndMeetingDialog";
import { StageContent } from "./StageContent";
import { Strip } from "./Strip";
import { PresentDialog, markPresentAsked, presentAsked } from "./PresentDialog";
import { SidePanel } from "./panels";
import { cn } from "@/lib/utils";

/** What the shell needs of the live channel (useMeetingLive's result; the control view builds it from its props). */
export interface CallLive {
  state: MeetingState;
  status: LiveStatus;
  statusDetail?: string;
  lastEvent?: LiveEvent | null;
  refresh: () => unknown;
}

export interface CallShellProps {
  mid: string;
  variant: CallVariant;
  live: CallLive;
  me: Me | null | undefined;
  /** The pre-join choice (the page shows PreJoin first); null when the person skipped it or there is no video. */
  joinChoice?: JoinChoice | null;
  /** Video may be used here, by the page's rule (the room: the coordinator's login on a meeting in session). */
  videoAvailable: boolean;
  /** "Join video": back to the pre-join. */
  onJoinVideo?: () => void;
  /** The page forwards its live events here (each one, in order); without it the shell watches live.lastEvent. */
  events?: MutableRefObject<((ev: LiveEvent) => void) | null>;
}

/** The stand-in agents: the list (Phase 5), or today's single agent as a list of one. */
export function agentsOf(s: MeetingState): AgentInfo[] {
  if (Array.isArray(s.agents)) return s.agents;
  const a = s.agent;
  if (a?.active && a.role) return [{ role: a.role, label: a.label || a.role, state: a.state || "ready", question: a.question ?? null, note: a.note, standing_in: true }];
  return [];
}

/** True when the meeting is over for the people in it (closed, or cancelled). */
export function meetingEnded(status: string | null | undefined): boolean {
  return status === "closed" || status === "cancelled";
}

/** "N in the meeting": the admitted attendance (in the room or remote) plus anyone in the video who is not on it (the coordinator
 * conducts without joining by code); people only, so a room screen ("<user>#room") never counts. Pure. */
export function CallShell({ mid, variant, live, me, joinChoice = null, videoAvailable, onJoinVideo, events }: CallShellProps) {
  const nav = useNavigate();
  const s = live.state;
  const stateRef = useRef(s);
  stateRef.current = s;
  const desktop = useIsDesktop();
  const phone = !desktop;
  const sideways = useMediaQuery("(orientation: landscape)");
  const [announce, liveNode] = useAnnounce();
  const myUser = variant === "room" ? "" : me?.user ?? "";

  // ---- what is on the floor ----------------------------------------------------------------------------------------------
  const order = useMemo(() => [...s.agenda.discussion, ...s.agenda.noting], [s.agenda]);
  const cid = s.current?.case_id ?? null;
  const idx = order.findIndex((r) => r.case_id === cid);
  const row = idx >= 0 ? order[idx] : null;
  const sharedSlide = s.current?.slide ?? 0;
  const admitted = s.me?.status === "present" || s.me?.status === "remote" || !!s.can?.manage;
  const waiting = s.me?.status === "waiting";
  const inSession = s.meeting.status === "in_session";
  const ended = meetingEnded(s.meeting.status) && variant !== "coordinator";
  const inRoom = s.me?.mode === "room" || s.me?.status === "present";
  const canManage = variant === "coordinator" && !!s.can?.manage;
  const canRecord = variant !== "room" && !!s.can?.record;

  const [following, setFollowing] = useState(true);
  const [mySlide, setMySlide] = useState(sharedSlide);
  useEffect(() => { if (following) setMySlide(sharedSlide); }, [sharedSlide, following]);
  useEffect(() => { setFollowing(true); }, [cid]);

  const slidesQ = useQuery({ queryKey: ["slides", mid, cid], queryFn: () => getSlides(mid, cid!), enabled: !!cid && (variant !== "member" || admitted), retry: variant === "coordinator" ? false : 1, staleTime: 60_000 });
  const slides = slidesQ.data?.slides ?? [];
  const slidesStatus: CallCtx["slidesStatus"] = !cid ? "idle" : slidesQ.isLoading ? "loading" : slidesQ.isError ? "error" : "ready";
  const member = variant === "member";
  const shownSlide = member && !following ? mySlide : sharedSlide;
  const opened = member && !following ? null : s.current?.opened ?? null;

  // ---- video -------------------------------------------------------------------------------------------------------------
  const room = variant === "room";
  const videoOn = videoAvailable && (room || !!joinChoice);
  const rawVideo: CallVideo = useVideoRoom(mid, videoOn, room ? { screen: "room", mic: false, cam: false } : joinChoice ?? {});
  // While the person dictates (a question, the decision form, the notes), the call microphone is muted and comes back after.
  const dictating = useDictationGuard(room ? { room: null, status: "off", micOn: false } : rawVideo);
  const { saveData, setSaveData } = useSaveData(rawVideo);
  useWakeLock(room);

  // ---- the shell's own state ---------------------------------------------------------------------------------------------
  const spotlight = useMemo(() => s.spotlight ?? [], [s.spotlight]);
  const cs = useCallState(mid, spotlight, { variant, inRoom });

  // ---- the agents' voice on this device (night-v3 6.1) ----------------------------------------------------------------------
  // one login may run two screens (the control view and the room screen): each reports its playback under its own id
  const deviceId = useMemo(() => Math.random().toString(36).slice(2, 10), []);
  const agent = useAgentSpeaker(mid, () => ({
    // by reference only: the app reads answer.speech[index], a sentence that is on the screen
    speak: (item, h) => speak({ ref: { kind: "meeting_answer", meeting_id: mid, id: item.question, index: item.index } }, { screen: "meeting" }, h),
    report: (question, playing) => agentAudio(mid, question, playing, deviceId),
    busy: isSpeaking,
  }), { enabled: cs.agentVoices && !ended, held: dictating });
  const speaker = agent.speaker;
  const voicesRef = useRef(cs.agentVoices);
  voicesRef.current = cs.agentVoices;
  // The case on the floor changed: the previous case's answers are not read any more.
  const floorRef = useRef(cid);
  useEffect(() => {
    if (floorRef.current && floorRef.current !== cid) speaker.stopAll();
    floorRef.current = cid;
  }, [cid, speaker]);
  useEffect(() => { if (agent.blocked) announce("The browser holds the agent voices until a tap. Tap to allow agent voices."); }, [agent.blocked, announce]);
  /** Inside a click that will make an agent speak: unlock the audio for the answer to come (and play what the browser held). */
  const primeVoices = () => {
    if (!voicesRef.current) return;
    if (!speaker.snapshot().speakingNow && !isSpeaking()) primeAudio();
    speaker.resume();
  };
  const allowVoices = () => { primeAudio(); speaker.resume(); };
  const agentName = (role: string) => { const a = agentsOf(stateRef.current).find((x) => x.role === role); return a?.department_name || a?.label || role; };
  const [error, setError] = useState<string | null>(null);
  const [card, setCard] = useState<{ caseId: string; patientLine: string } | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [endOpen, setEndOpen] = useState(false);
  const [menu, setMenu] = useState<ShellExtras["menu"]>(null);
  const [summaryOn, setSummaryOn] = useState(true);
  // the minutes the running timer was set to, else the agenda row's: a reload keeps a paused 15-minute timer (review finding 11)
  const seedMinutes = () => { const t = s.current?.timer?.total; return t ? Math.round(t / 60) : row?.minutes ?? s.meeting.minutes_per_case ?? 10; };
  const [minutes, setMinutes] = useState<number>(seedMinutes);
  useEffect(() => { setMinutes(seedMinutes()); }, [cid]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!phone) setMenu((m) => (m === "coordinator" ? null : m)); }, [phone]);

  // ---- screen share (night-v3 5.2): LiveKit carries the pixels, the meeting records who presents -----------------------------
  // Why my share stopped, from the event that stopped it (read when the state says someone else presents, or no one).
  const shareStopReason = useRef<string | null>(null);
  const nameOf = (user: string) => stateRef.current.attendance.find((a) => a.user === user)?.name || user;
  const onPresentingEvent = (ev: LiveEvent) => {
    const user = String(ev.user ?? "");
    const by = String(ev.by ?? "");
    if (!ev.on && user && user === myUser && by && by !== myUser) {
      shareStopReason.current = ev.replaced ? `Your share was stopped: ${nameOf(by)} started presenting.` : `Your share was stopped by ${nameOf(by)}.`;
    }
    if (ev.on && user && user !== myUser) announce(`${(ev.name as string | undefined) || nameOf(user)} is presenting.`);
  };

  // ---- live events -------------------------------------------------------------------------------------------------------
  const onEvent = useCallback((ev: LiveEvent) => {
    const st = stateRef.current;
    if (ev.type === "agent_speech") {
      const item = speechItem(ev);
      if (item && voicesRef.current && onTheFloor(st.questions, item.question, st.current?.case_id ?? null)) speaker.enqueue(item);
      return;
    }
    if (ev.type === "agent_stop") { speaker.stopQuestion(String(ev.question ?? "")); return; }
    if (ev.type === "presenting") { onPresentingEvent(ev); return; }
    if (ev.type === "present_allowed") { void live.refresh(); return; }  // my "may I present" (can.present) comes with the state
    if (ev.type === "current" && ev.case_id && ev.case_id !== st.current?.case_id && st.presenting && st.presenting === myUser) shareStopReason.current = "Your share was stopped: the next case is on the screen.";
    if (ev.type === "reaction") { cs.addReaction({ user: String(ev.user ?? ""), name: ev.name as string | undefined, kind: String(ev.kind ?? ""), at: ev.at as string | undefined }); return; }
    if (ev.type === "decision") { cs.markSaved(); return; }
    if (ev.type === "ended") { speaker.stopAll(); announce("The meeting has ended."); return; }
    if (variant !== "member") return;
    if (ev.type === "end_case") {
      const c = String(ev.case_id ?? "");
      const asked = Array.isArray(ev.cards_requested) ? (ev.cards_requested as string[]) : [];
      const myDept = st.me?.department ?? "";
      const isIn = st.me?.status === "present" || st.me?.status === "remote";
      if (isIn && (st.can?.card_required || (myDept && asked.includes(myDept)))) {
        const r = [...st.agenda.discussion, ...st.agenda.noting].find((x) => x.case_id === c);
        setCard({ caseId: c, patientLine: r?.patient_line || c });
        announce("The coordinator asks for your card on this case.");
      }
    }
  }, [announce, cs.addReaction, cs.markSaved, variant, myUser, speaker]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!events) return undefined;
    events.current = onEvent;
    return () => { events.current = null; };
  }, [events, onEvent]);
  const lastSeen = useRef<LiveEvent | null>(null);
  useEffect(() => {
    if (events || !live.lastEvent || live.lastEvent === lastSeen.current) return;
    lastSeen.current = live.lastEvent;
    onEvent(live.lastEvent);
  }, [events, live.lastEvent, onEvent]);

  // ---- actions -----------------------------------------------------------------------------------------------------------
  const refresh = useCallback(() => { void live.refresh(); }, [live]);
  const run = useCallback(async <T,>(fn: () => Promise<T>, said?: string | ((r: T) => string)): Promise<T> => {
    setError(null);
    try {
      const r = await fn();
      if (said) announce(typeof said === "function" ? said(r) : said);
      refresh();
      return r;
    } catch (e) { setError(errorText(e)); throw e; }
  }, [announce, refresh]);

  const goM = useMutation({ mutationFn: (v: { caseId: string; slide?: number }) => setCurrent(mid, v.caseId, v.slide) });
  const timerM = useMutation({ mutationFn: (v: { action: "start" | "stop" | "reset"; minutes?: number }) => timerCall(mid, v.action, v.minutes) });
  const endM = useMutation({ mutationFn: (c: string) => endCaseCall(mid, c) });
  const handM = useMutation({ mutationFn: (raised: boolean) => raiseHand(mid, raised) });
  const presenceM = useMutation({ mutationFn: (mode: "room" | "remote") => present(mid, mode) });

  const actions: CallActions = {
    admit: (user) => run(() => admit(mid, user), "Admitted."),
    admitAll: () => run(async () => {
      const list = stateRef.current.attendance.filter((a) => a.status === "waiting");
      for (const a of list) await admit(mid, a.user);
      return list.length;
    }, (n) => (n === 1 ? "Admitted." : `Admitted ${n} people.`)),
    go: (caseId, slide) => run(() => goM.mutateAsync({ caseId, slide }), slide !== undefined ? `Slide ${slide + 1} on the screen.` : "Next case on the screen."),
    open: (kind, docId) => run(() => openOnScreen(mid, kind, docId), kind === "none" ? "The shared screen shows the slide again." : kind === "images" ? "The images are on the shared screen." : "The record is on the shared screen."),
    timer: (action, m) => run(() => timerM.mutateAsync({ action, minutes: action === "stop" ? undefined : m ?? minutes }), action === "start" ? "Timer started." : action === "stop" ? "Timer stopped." : "Timer reset."),
    endCase: () => (cid ? run(() => endM.mutateAsync(cid), (r) => (r?.cards_requested?.length ? `Cards asked of ${r.cards_requested.length} board heads.` : "Discussion ended.")) : Promise.reject(new Error("No case on the screen."))),
    endMeeting: () => setEndOpen(true),
    ask: (text, role) => { if (role) primeVoices(); return run(() => askQuestion(mid, text, role), "Question sent to the shared screen."); },
    hand: (raised) => run(() => handM.mutateAsync(raised), raised ? "Hand raised." : "Hand lowered."),
    react: (kind: ReactionKind) => {
      if (myUser) cs.addReaction({ user: myUser, name: me?.display_name, kind } as ReactionEvent);
      return run(() => sendReaction(mid, kind));
    },
    spotlight: (users) => run(() => setSpotlight(mid, users), users.length ? "Spotlight set for everyone." : "Spotlight removed."),
    presence: (mode) => run(() => presenceM.mutateAsync(mode), mode === "room" ? "Marked as in the room." : "Marked as remote."),
    leave: () => { speaker.stopAll(); nav(variant === "coordinator" ? "/meetings" : `/meetings/${mid}`); },
    card: () => { if (cid) setCard({ caseId: cid, patientLine: row?.patient_line || cid }); },
    chat: (text) => run(() => sendChat(mid, text)),
    allowPresent: (user, allowed) => run(() => allowPresent(mid, user, allowed), allowed ? "Allowed to present." : "The right to present was withdrawn."),
    presenting: (on) => run(() => setPresenting(mid, on)),
    setAgent: (role, on) => run(() => setAgentCall(mid, role, on), on ? `${agentName(role)} agent added to this case.` : `${agentName(role)} agent removed from this case.`),
    setAgentsAsk: (on) => run(() => setAgentSettings(mid, { members_ask: on }), on ? "Members can ask the agents." : "Questions to the agents are closed for members."),
    agentListening: (role, on) => run(() => agentListeningCall(mid, role, on)),
    presentPoints: (role) => { primeVoices(); return run(() => presentPointsCall(mid, role), `${agentName(role)} agent asked to present its points.`); },
    stopAgent: (role, question) => {
      if (question) speaker.stopQuestion(question);
      return run(() => stopAgentCall(mid, role, question), `${agentName(role)} agent's voice stopped for everyone.`);
    },
  };

  // My share turned on: tell the meeting (refused: stop it again). Turned off: tell the meeting when it still names me.
  const shareOn = !!rawVideo.shareOn;
  const rawToggleShare = rawVideo.toggleShare;
  const sharePrev = useRef(false);
  const shareMine = useRef(false);
  useEffect(() => {
    if (shareOn && !sharePrev.current) {
      shareMine.current = false;
      shareStopReason.current = null;
      void actions.presenting?.(true).catch(() => { void rawToggleShare?.(); });
    } else if (!shareOn && sharePrev.current) {
      if (stateRef.current.presenting === myUser) void actions.presenting?.(false).catch(() => undefined);
      shareMine.current = false;
    }
    sharePrev.current = shareOn;
  }, [shareOn]); // eslint-disable-line react-hooks/exhaustive-deps
  // Someone else presents now, the coordinator stopped me, my right was withdrawn or the next case came: stop my share.
  useEffect(() => {
    if (!shareOn || !myUser) return;
    if (s.presenting === myUser) { shareMine.current = true; return; }
    if (!shareMine.current) return;  // not yet confirmed by the server
    shareMine.current = false;
    void rawToggleShare?.();
    announce(shareStopReason.current ?? "Your share was stopped.");
    shareStopReason.current = null;
  }, [s.presenting, shareOn]); // eslint-disable-line react-hooks/exhaustive-deps
  // After a reload the meeting may still name me while nothing is shared: clear it once the video is back.
  useEffect(() => {
    if (rawVideo.status === "connected" && !shareOn && myUser && stateRef.current.presenting === myUser) void actions.presenting?.(false).catch(() => undefined);
  }, [rawVideo.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const [presentAsk, setPresentAsk] = useState(false);
  const mayShare = !room && desktop && !!rawToggleShare;
  /** Present or stop (the bar's button and Ctrl+Alt+T): the one-line reminder before the first share of the meeting in this tab. */
  const toggleShare = async () => {
    if (!rawToggleShare) return;
    if (shareOn) { await rawToggleShare(); return; }
    if (!stateRef.current.can?.present) { announce("Ask the MDT Coordinator to allow you to present."); return; }
    if (rawVideo.status !== "connected") return;
    if (!presentAsked(mid)) { setPresentAsk(true); return; }
    await rawToggleShare();
  };
  const video: CallVideo = { ...rawVideo, toggleShare: mayShare || shareOn ? toggleShare : undefined };

  const next = () => { if (order.length && idx < order.length - 1 && !goM.isPending) void actions.go(order[idx + 1].case_id).catch(() => {}); };
  const previous = () => { if (idx > 0 && !goM.isPending) void actions.go(order[idx - 1].case_id).catch(() => {}); };

  const ctx: CallCtx = {
    mid, variant, state: s, me: myUser, cid, row, order, slides, slidesStatus, slidesError: slidesQ.error ?? undefined,
    sharedSlide, shownSlide, following, setFollowing,
    showSlide: (i) => {
      if (variant === "coordinator") { if (cid) void actions.go(cid, i).catch(() => {}); return; }
      if (variant !== "member") return;
      if (following && i === sharedSlide && !s.current?.opened) return;
      setMySlide(i); setFollowing(false);
    },
    opened, video, videoAvailable, liveStatus: live.status, liveDetail: live.statusDetail, savedNow: cs.savedNow,
    joinVideo: () => onJoinVideo?.(), dictating,
    panel: cs.panel, setPanel: cs.setPanel, togglePanel: cs.togglePanel, layout: cs.layout, setLayout: cs.setLayout,
    pinned: cs.pinned, setPinned: cs.setPinned, spotlight, agents: agentsOf(s), agentVoices: cs.agentVoices, setAgentVoices: cs.setAgentVoices,
    speakingNow: agent.speakingNow,
    stopAgentAudio: () => { if (!speaker.snapshot().speakingNow && !speaker.snapshot().queued) return; speaker.stopAll(); announce("Agent voice stopped on this device."); },
    reactions: cs.reactions, hands: handUsers(s.hands), canManage, canRecord, admitted, waiting, inSession, inRoom, phone,
    fullscreen: cs.fullscreen, toggleFullscreen: cs.toggleFullscreen, announce, refresh, error, actions,
  };

  const cardAsked = member && !!cid && (s.ended ?? []).includes(cid) && !!(s.can?.card || s.can?.card_required);
  const extras: ShellExtras = {
    joined: room || !!joinChoice, idx, minutes, setMinutes, next, previous, openShortcuts: () => setHelpOpen(true), cardAsked,
    handPending: handM.isPending, goPending: goM.isPending, timerPending: timerM.isPending, endPending: endM.isPending, presencePending: presenceM.isPending,
    menu, setMenu, saveData, setSaveData,
  };
  useShortcuts(ctx, { openHelp: () => setHelpOpen(true), next, previous });

  // Phone: the controls fade after 4 s without a touch, except while something needs them.
  const holdControls = ended || !!cs.panel || !!menu || helpOpen || endOpen || !!card || presentAsk || ctx.hands.has(myUser) || dictating || shareOn || !!s.presenting;
  const controls = useControlsAutoHide(phone && !room, holdControls);
  const landscape = phone && !room && sideways;
  const fade = cn("transition-opacity duration-300 focus-within:pointer-events-auto focus-within:opacity-100", controls.hidden && "pointer-events-none opacity-0");

  const liveText = s.decision_live && (!s.decision_live.case_id || s.decision_live.case_id === cid) ? s.decision_live.text : "";
  const voiceChip = agent.blocked && cs.agentVoices && !ended ? <AllowVoicesChip onAllow={allowVoices} big={room} /> : null;
  const testId = variant === "member" ? "member-view" : variant === "coordinator" ? "control-view" : "room-screen";
  const attrs: Record<string, string | undefined> = variant === "member" ? { "data-following": String(following), "data-video-status": video.status }
    : variant === "room" ? { "data-meeting-status": s.meeting.status } : { "data-video-status": video.status };
  attrs["data-controls"] = controls.hidden ? "hidden" : "shown";
  if (phone && !room) attrs["data-orientation"] = landscape ? "landscape" : "portrait";

  return (
    <CallContext.Provider value={ctx}>
      <ShellContext.Provider value={extras}>
        <StageFrame testId={testId} attrs={attrs}>
          {liveNode}
          {phone && !room ? <div className={fade} data-testid="top-controls"><TopBar /></div> : <TopBar />}
          {room ? <RoomBody summaryOn={summaryOn} setSummaryOn={setSummaryOn} videoOn={videoOn} liveText={liveText} ended={ended} voiceChip={voiceChip} /> : (
            <section aria-label="Call" className={cn("flex min-h-0 flex-1 gap-3 p-2 lg:p-3", phone && !landscape && "flex-col overflow-y-auto", landscape && "gap-2")}>
              {desktop ? <AgendaRail /> : null}
              <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-2">
                <StageTabs />
                <div className={cn("flex min-w-0 gap-2", phone && !landscape ? "min-h-[62.5vw] flex-1" : "min-h-0 flex-1")}>
                  <StageContent className={cn(phone && !landscape ? "min-h-[62.5vw] w-full flex-1" : "min-h-0 flex-1")}>
                    <StageOverlays ended={ended} voiceChip={voiceChip} />
                  </StageContent>
                  {desktop && !cs.panel ? <div className="scroll-thin hidden w-52 shrink-0 overflow-y-auto lg:block xl:w-60"><Strip orientation="column" /></div> : null}
                </div>
                {(phone && !landscape) || (desktop && cs.panel) ? <div className="shrink-0"><Strip orientation="row" max={phone ? 8 : 10} /></div> : null}
                <AnimatePresence>
                  {liveText || cs.savedNow ? (
                    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                      {phone ? <PhoneDecisionStrip text={liveText} saved={cs.savedNow} /> : <DecisionStrip text={liveText} saved={cs.savedNow} />}
                    </motion.div>
                  ) : null}
                </AnimatePresence>
                {error ? <p role="alert" className="flex items-center gap-2 rounded-lg bg-bad-soft px-3 py-1.5 text-xs text-bad"><span className="min-w-0 flex-1">{error}</span><button type="button" className="rounded p-1 hover:bg-bad/10" onClick={() => setError(null)} aria-label="Dismiss the message"><X className="size-3.5" /></button></p> : null}
              </div>
              {landscape ? <div className="scroll-thin w-28 shrink-0 overflow-y-auto overflow-x-hidden" data-testid="landscape-strip"><Strip orientation="column" max={8} small /></div> : null}
              <SidePanel />
            </section>
          )}
          {room ? null : ended ? <EndedBar /> : phone ? <div className={fade} data-testid="bar-controls"><CallBar /></div> : <CallBar />}
          {room ? null : <ShortcutsDialog open={helpOpen} onOpenChange={setHelpOpen} coordinator={canManage} present={!!video.toggleShare} />}
          {mayShare ? <PresentDialog open={presentAsk} onOpenChange={setPresentAsk} onShare={() => { markPresentAsked(mid); setPresentAsk(false); void rawToggleShare?.(); }} /> : null}
          {canManage ? <EndMeetingDialog open={endOpen} onOpenChange={setEndOpen} /> : null}
          {card ? <CardDialog mid={mid} caseId={card.caseId} patientLine={card.patientLine} required={!!s.can?.card_required} open onOpenChange={(o) => { if (!o) setCard(null); }} onSent={() => announce("Card sent.")} /> : null}
        </StageFrame>
      </ShellContext.Provider>
    </CallContext.Provider>
  );
}

/** The overlays on the stage: the connection banner, the "Following / Stepped away" chip (member), "What the room sees"
 * (coordinator), the slide dots and the coordinator's admit toast. */
function StageOverlays({ ended, voiceChip }: { ended: boolean; voiceChip: ReactNode }) {
  const c = useCall();
  const openedItem = c.opened && c.opened.kind !== "none";
  return (
    <>
      <CaseFlow />
      {ended ? <EndedCard /> : null}
      <div className="pointer-events-none absolute inset-x-0 top-14 z-20 flex flex-col items-center gap-1.5 px-3 [&>*]:pointer-events-auto"><PresentingBar />{voiceChip}</div>
      {c.variant === "member" ? (
        <span className={cn("pointer-events-none absolute right-3 top-3 z-10 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium", c.following ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn")}>
          {c.following ? <MonitorCheck className="size-3.5" aria-hidden /> : <Footprints className="size-3.5" aria-hidden />}<span className={c.phone ? "sr-only" : undefined}>{c.following ? "Following the shared screen" : "Stepped away"}</span>
        </span>
      ) : c.variant === "coordinator" ? <span className="pointer-events-none absolute right-3 top-3 z-10 rounded-full bg-black/70 px-2.5 py-1 text-xs font-medium text-white">What the room sees</span> : null}
      {!openedItem && !c.state.presenting ? <SlideDots slides={c.slides} index={c.shownSlide} className="absolute bottom-2 right-3 z-10" /> : null}
      <AdmitToast className="absolute bottom-3 left-3" />
    </>
  );
}

/** "The meeting has ended" over the stage (member: a link back to the meeting page; the room screen: "Meeting closed", large). */
function EndedCard() {
  const c = useCall();
  const room = c.variant === "room";
  const cancelled = c.state.meeting.status === "cancelled";
  return (
    <div className="absolute inset-0 z-40 grid place-items-center bg-stage/85 p-4 backdrop-blur-sm" data-testid="meeting-ended" role="status">
      <div className={cn("max-w-lg rounded-2xl border border-stage-line bg-stage-panel text-center shadow-[var(--shadow-lift)]", room ? "space-y-3 p-10" : "space-y-3 p-6")}>
        <p className={cn("font-semibold text-stage-fg", room ? "text-5xl" : "text-xl")}>{room ? "Meeting closed" : "The meeting has ended"}</p>
        <p className={cn("text-stage-fg/80", room ? "text-2xl" : "text-sm")}>{cancelled ? "The MDT Coordinator cancelled this meeting." : "The saved outcomes go to the owners of the Case Files."}</p>
        {room ? null : (
          <Button asChild variant="outline" className="border-stage-line bg-transparent text-stage-fg hover:bg-stage-raised hover:text-stage-fg">
            <Link to={`/meetings/${c.mid}`} data-testid="back-to-meeting"><ArrowLeft className="size-4" aria-hidden />Back to the meeting page</Link>
          </Button>
        )}
      </div>
    </div>
  );
}

/** The member's bar once the meeting has ended: Leave only. */
function EndedBar() {
  const c = useCall();
  const count = useMeetingCount();
  return (
    <ControlBar className="pb-[max(0.5rem,env(safe-area-inset-bottom))]" left={<span className="block min-w-0 truncate text-xs text-stage-muted" title={`The meeting has ended · ${count} in the meeting`}>The meeting has ended · {count} in the meeting</span>}>
      <RoundButton icon={LogOut} label="Leave" title="Leave the meeting" tone="danger" onClick={c.actions.leave} testId="leave" />
    </ControlBar>
  );
}

/** "Tap to allow agent voices": the browser held the agents' sound until a tap on the page; the tap unlocks it and plays what waits. */
function AllowVoicesChip({ onAllow, big = false }: { onAllow: () => void; big?: boolean }) {
  return (
    <button type="button" onClick={onAllow} data-testid="allow-agent-voices" title="The browser plays sound only after a tap on the page"
      className={cn("inline-flex min-h-11 items-center gap-2 rounded-full bg-primary px-3 py-1 font-medium text-primary-foreground shadow-[var(--shadow-lift)] outline-none hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-1 focus-visible:ring-offset-primary sm:min-h-8",
        big ? "px-5 py-2 text-xl" : "text-sm")}>
      <Volume2 className={big ? "size-6" : "size-4"} aria-hidden />{VOICE_TEXT.allowVoices}
    </button>
  );
}

/** "You are presenting" with Stop, at the top of the stage while my screen is shared. */
function PresentingBar() {
  const c = useCall();
  if (!c.video.shareOn) return null;
  return (
    <p role="status" className="flex items-center gap-2 rounded-full bg-primary px-3 py-1 text-sm font-medium text-primary-foreground shadow-[var(--shadow-lift)]" data-testid="presenting-bar">
      <MonitorUp className="size-4" aria-hidden />You are presenting to everyone
      <button type="button" onClick={() => void c.video.toggleShare?.()} className="rounded-full bg-white px-2.5 py-0.5 text-xs font-semibold text-primary outline-none hover:bg-white/90 focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-1 focus-visible:ring-offset-primary" aria-label="Stop presenting" title="Stop presenting (Ctrl+Alt+T)" data-testid="stop-presenting">Stop</button>
    </p>
  );
}

/** The phone's decision strip: one line; a tap opens the whole text in place and a second tap folds it again. The strip keeps its
 * live region; a transparent button over it takes the tap. */
function PhoneDecisionStrip({ text, saved }: { text: string; saved: boolean }) {
  const [open, setOpen] = useState(false);
  useEffect(() => { if (saved) setOpen(false); }, [saved]);
  const long = !saved && text.length > 0;
  return (
    <div className="relative" data-testid="decision-strip-phone" data-expanded={open ? "true" : "false"}>
      <DecisionStrip text={text} saved={saved} className={cn("min-h-11 items-center py-1.5", open ? "scroll-thin max-h-[40dvh] overflow-y-auto [&>p]:whitespace-normal" : "[&>p]:truncate")} />
      {long ? (
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="absolute inset-0 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-primary"
          aria-label={open ? "Show the decision on one line" : "Show the whole decision text"} title={open ? "Show the decision on one line" : "Show the whole decision text"} data-testid="decision-expand" />
      ) : null}
    </div>
  );
}

/** How many questions the room screen shows (the latest), and how many remote tiles (fewer on a screen under 900 px high). */
export const ROOM_QUESTIONS = 2;
export const ROOM_TILES = 6;
export const ROOM_TILES_SHORT = 4;

/** The room screen's body (a projector, 1920 x 1080; research/04 section 6.4): the summary column (a toggle, on by default, as the
 * room used it), the compact agenda column, the stage in large type (28 px and more), the latest questions, the remote members (at
 * most six tiles and "+n more") and the agents, and the footer with the count, the hands by name and the big decision strip
 * (28 px). Nothing here scrolls the page: long content is cut with "+n more" or clipped. */
function RoomBody({ summaryOn, setSummaryOn, videoOn, liveText, ended, voiceChip }: { summaryOn: boolean; setSummaryOn: (on: boolean) => void; videoOn: boolean; liveText: string; ended: boolean; voiceChip: ReactNode }) {
  const c = useCall();
  const s = c.state;
  const summary = c.slides.find((x) => x.kind === "summary") ?? c.slides[0] ?? null;
  const onStage = c.slides[c.shownSlide] ?? null;
  const openedItem = c.opened && c.opened.kind !== "none";
  // The summary column is left out while the summary itself fills the stage (it would show twice).
  const summaryOnStage = !!(onStage && summary && onStage.id === summary.id && !openedItem);
  const showColumn = summaryOn && !summaryOnStage;
  const questions = (s.questions ?? []).filter((q) => !c.cid || !q.case_id || q.case_id === c.cid);
  const latest = questions.slice(-ROOM_QUESTIONS);
  const earlier = questions.length - latest.length;
  const count = useMeetingCount();
  const handNames = s.attendance.filter((a) => c.hands.has(a.user)).map((a) => a.name);
  const tall = useMediaQuery("(min-height: 900px)");
  return (
    <>
      {/* the hover bar sits at the bottom right of this area; the stage column and the people column keep room under it */}
      <section aria-label="Call" className="relative flex min-h-0 flex-1 gap-3 overflow-hidden p-3 lg:p-4">
        {showColumn ? (
          <section className="hidden w-[30%] min-w-0 overflow-hidden rounded-xl border border-stage-line bg-stage-panel p-5 [mask-image:linear-gradient(to_bottom,#000_88%,transparent)] lg:block" aria-label="Summary" data-testid="room-summary">
            {!c.cid ? <p className="text-xl text-stage-fg/80">The summary of the current case appears here.</p> : null}
            {c.cid && c.slidesStatus === "loading" ? <SkeletonLines n={8} /> : null}
            {c.cid && c.slidesStatus === "error" ? <p className="text-xl text-warn">The slides for this case could not be loaded.</p> : null}
            {summary ? <SlideContent slide={summary} big /> : null}
          </section>
        ) : null}
        <AgendaRail room className="hidden lg:flex" />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 pb-14">
          {/* Large type on the projector: every line on the stage at 28 px or more (the slide title larger, the source chips at 20 px). */}
          <StageContent className="min-h-0 flex-1 [&_.stage-slide]:text-[28px] [&_.stage-slide_*]:[font-size:inherit] [&_.stage-slide_h3]:text-[36px] [&_.stage-slide_.quote-chip]:text-[20px] [&_p]:text-[28px] [&_p]:leading-snug" >
            {!openedItem && !s.presenting ? <SlideDots slides={c.slides} index={c.shownSlide} className="absolute bottom-3 right-4 z-10" /> : null}
            <CaseFlow />
            {voiceChip ? <div className="absolute inset-x-0 top-20 z-30 flex justify-center px-3">{voiceChip}</div> : null}
            {ended ? <EndedCard /> : null}
          </StageContent>
          <AnimatePresence initial={false}>
            {latest.length ? (
              <motion.section key="q" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="max-h-[30%] shrink-0 overflow-hidden rounded-xl border border-stage-line bg-stage-panel p-3 [&_li_p]:text-xl [&_li_p]:leading-snug" aria-label="Questions" data-testid="room-questions">
                <h2 className="mb-1 flex items-baseline gap-2 text-lg font-semibold text-stage-fg/80">Questions from members{earlier > 0 ? <span className="text-base font-normal" data-testid="room-questions-more">(the latest {latest.length}; +{earlier} more)</span> : null}</h2>
                <QuestionsList questions={latest} caseId={c.cid} big />
              </motion.section>
            ) : null}
          </AnimatePresence>
        </div>
        <aside className="flex w-72 shrink-0 flex-col gap-2 overflow-hidden pb-14 min-[1600px]:w-[24rem]" aria-label="Remote members and agents" data-testid="room-people">
          <Strip orientation="column" max={tall ? ROOM_TILES : ROOM_TILES_SHORT} />
        </aside>
        <RoomHoverBar summaryOn={summaryOn} setSummaryOn={setSummaryOn} videoOn={videoOn} summaryOnStage={summaryOnStage} />
      </section>
      <footer className="space-y-2 border-t border-stage-line px-3 py-2 lg:px-4">
        <div className="flex flex-wrap items-center gap-3 text-xl text-stage-fg/80">
          <span data-testid="room-count">{count} in the meeting</span>
          {handNames.length ? <span className="rounded-full bg-warn-soft px-3 py-0.5 text-xl font-medium text-warn" data-testid="room-hands">{handNames.length} hand{handNames.length === 1 ? "" : "s"} raised: {handNames.join(", ")}</span> : null}
          {c.video.error ? <span className="text-lg text-bad">{c.video.error}</span> : null}
        </div>
        <DecisionStrip text={liveText} saved={c.savedNow} big className={cn("[&>p]:line-clamp-2 [&>p]:text-[28px] [&>span]:text-base", !liveText && !c.savedNow && "hidden")} />
        {!liveText && !c.savedNow ? <p className="rounded-xl border border-dashed border-stage-line px-4 py-2 text-xl text-stage-fg/80">The decision appears here as the coordinator types it, until it is read back and saved.</p> : null}
      </footer>
    </>
  );
}

/** The room screen's small bar at the bottom right: it shows on hover or focus. */
function RoomHoverBar({ summaryOn, setSummaryOn, videoOn, summaryOnStage }: { summaryOn: boolean; setSummaryOn: (on: boolean) => void; videoOn: boolean; summaryOnStage: boolean }) {
  const c = useCall();
  const v = c.video;
  const btn = "text-stage-fg hover:bg-stage-raised hover:text-stage-fg";
  return (
    <div className="absolute bottom-2 right-3 z-30 flex flex-wrap items-center justify-end gap-1 rounded-xl border border-stage-line bg-stage-panel/95 p-1 opacity-30 shadow-[var(--shadow-lift)] backdrop-blur transition-opacity duration-200 hover:opacity-100 focus-within:opacity-100" role="toolbar" aria-label="Room screen controls" data-testid="room-bar">
      {videoOn ? (
        <>
          <Button variant="ghost" size="sm" className={cn(btn, v.micOn && "bg-stage-raised")} onClick={() => void v.toggleMic()} disabled={v.status !== "connected"} aria-pressed={v.micOn} title="The room's microphone, for the remote members">{v.micOn ? <Mic className="size-4" /> : <MicOff className="size-4" />}Room mic</Button>
          <Button variant="ghost" size="sm" className={cn(btn, v.camOn && "bg-stage-raised")} onClick={() => void v.toggleCam()} disabled={v.status !== "connected"} aria-pressed={v.camOn} title="The room's camera, for the remote members">{v.camOn ? <Camera className="size-4" /> : <CameraOff className="size-4" />}Room camera</Button>
        </>
      ) : null}
      <Button variant="ghost" size="sm" className={cn(btn, summaryOn && !summaryOnStage && "bg-stage-raised")} onClick={() => setSummaryOn(!summaryOn)} aria-pressed={summaryOn} disabled={summaryOnStage} title={summaryOnStage ? "The summary is on the stage now" : "The case summary in a column beside the stage"} data-testid="summary-toggle"><PanelLeft className="size-4" />Summary on the side</Button>
      <Button variant="ghost" size="sm" className={cn(btn, c.agentVoices && "bg-stage-raised")} onClick={() => c.setAgentVoices(!c.agentVoices)} aria-pressed={c.agentVoices} title={c.agentVoices ? "The agents' answers are read aloud on this screen; click to mute them" : "The agents' answers are not read aloud on this screen; click to turn them on"} data-testid="agent-voices">{c.agentVoices ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}{c.agentVoices ? "Agent voices on" : "Agent voices off"}</Button>
      <Button variant="ghost" size="icon" className={btn} onClick={c.toggleFullscreen} aria-label={c.fullscreen ? "Leave full screen" : "Full screen"} title={c.fullscreen ? "Leave full screen (F)" : "Full screen (F)"} aria-keyshortcuts="F">{c.fullscreen ? <Minimize2 className="size-5" /> : <Maximize2 className="size-5" />}</Button>
      <Button asChild variant="ghost" size="icon" className={btn} aria-label="Close the room screen" title="Close the room screen"><Link to={`/meetings/${c.mid}`}><X className="size-5" /></Link></Button>
    </div>
  );
}
