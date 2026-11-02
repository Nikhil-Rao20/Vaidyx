// The call shell's own state (night-v3 5.1): which side panel is open, the layout, my pin (this browser only), the agent voices
// for me, full screen, the reactions shown for a moment, "Decision saved" for 8 s, and the keyboard shortcuts of the call.
// Night-v3 5.5: the phone's controls fading after 4 s without a touch (useControlsAutoHide), "Save data" (useSaveData: camera off,
// the remote video at the lower quality, remembered for this tab) and the room screen's wake lock (useWakeLock).
// Night-v3 6.1: the agent voices follow the person's stored choice; with none, a member in the room starts muted (the room screen
// plays the answers) and everyone else hears them; the room screen starts on and keeps its own choice for this page only.
import { createContext, useCallback, useEffect, useRef, useState } from "react";
import { identityUser, isRoomScreen } from "@/lib/video";
import { useCall } from "./context";
import { Track, VideoQuality, type Room } from "livekit-client";
import { agentVoiceChoice, onAgentVoiceChange, setAgentVoice } from "@/lib/voice";
import { agentVoicesFor } from "./agentSpeaker";
import type { ReactionEvent } from "@/lib/live";
import type { CallCtx, CallVariant, CallVideo, LayoutKind, PanelKind, ShownReaction } from "./types";

/** How long a reaction stays on a tile, and how long "Decision saved" stays on the strip. */
export const REACTION_MS = 3000;
export const SAVED_MS = 8000;

/** What the shell's own pieces share beyond the call context (the bar, the menus, the top bar): pending flags, the case index, the
 * timer minutes, next and previous case, the shortcuts dialog and whether the end-of-case card is asked of me. */
export interface ShellExtras {
  /** Joined the video through the pre-join (mic and camera buttons) rather than skipped it (Join video). */
  joined: boolean;
  idx: number;
  minutes: number;
  setMinutes: (m: number) => void;
  next: () => void;
  previous: () => void;
  openShortcuts: () => void;
  cardAsked: boolean;
  handPending: boolean;
  goPending: boolean;
  timerPending: boolean;
  endPending: boolean;
  presencePending: boolean;
  /** The More menu (laptop dropdown, phone sheet) and the phone's Coordinator sheet; kept here so it survives a resize. */
  menu: "more" | "coordinator" | null;
  setMenu: (m: "more" | "coordinator" | null) => void;
  /** "Save data" (night-v3 5.5): camera off and the remote video at the lower quality, remembered for this tab. */
  saveData: boolean;
  setSaveData: (on: boolean) => void;
}
const noop = () => {};
export const ShellContext = createContext<ShellExtras>({ joined: false, idx: -1, minutes: 10, setMinutes: noop, next: noop, previous: noop, openShortcuts: noop, cardAsked: false, handPending: false, goPending: false, timerPending: false, endPending: false, presencePending: false, menu: null, setMenu: noop, saveData: false, setSaveData: noop });

export const pinKey = (mid: string) => `tbnik.call.pin.${mid}`;

function readPin(mid: string): string | null {
  try { return sessionStorage.getItem(pinKey(mid)); } catch { return null; }
}

/** The reactions still to show at `now` (each lasts REACTION_MS); the same map when nothing expired. */
export function pruneReactions(m: Map<string, ShownReaction>, now: number): Map<string, ShownReaction> {
  let changed = false;
  const next = new Map<string, ShownReaction>();
  for (const [k, v] of m) { if (now - v.shownAt < REACTION_MS) next.set(k, v); else changed = true; }
  return changed ? next : m;
}

export function useCallState(mid: string, spotlight: string[], where: { variant: CallVariant; inRoom: boolean } = { variant: "member", inRoom: false }) {
  const [panel, setPanelRaw] = useState<PanelKind>(null);
  const setPanel = useCallback((p: PanelKind) => setPanelRaw(p), []);
  const togglePanel = useCallback((p: Exclude<PanelKind, null>) => setPanelRaw((cur) => (cur === p ? null : p)), []);

  const [layout, setLayout] = useState<LayoutKind>("auto");
  const [pinned, setPinnedRaw] = useState<string | null>(() => readPin(mid));
  const spotRef = useRef(spotlight);
  spotRef.current = spotlight;
  const setPinned = useCallback((key: string | null) => {
    setPinnedRaw(key);
    if (!key && spotRef.current.length) setLayout("spotlight");  // unpinning shows the coordinator's spotlight again
    try { if (key) sessionStorage.setItem(pinKey(mid), key); else sessionStorage.removeItem(pinKey(mid)); } catch { /* no storage: the pin lasts this page only */ }
  }, [mid]);

  // A spotlight from the coordinator changes my layout unless I pinned someone; when it is removed, back to Auto.
  const spotKey = spotlight.join("|");
  const pinnedRef = useRef(pinned);
  pinnedRef.current = pinned;
  useEffect(() => {
    if (spotKey && !pinnedRef.current) setLayout("spotlight");
    if (!spotKey) setLayout((l) => (l === "spotlight" ? "auto" : l));
  }, [spotKey]);

  // The person's choice (null: none yet). The room screen runs under the coordinator's login, often in the same browser: it never
  // reads nor writes that stored choice, so muting the control view does not mute the room.
  const roomScreen = where.variant === "room";
  const [voiceChoice, setVoiceChoice] = useState<boolean | null>(() => (roomScreen ? null : agentVoiceChoice()));
  useEffect(() => (roomScreen ? undefined : onAgentVoiceChange(setVoiceChoice)), [roomScreen]);
  const agentVoices = agentVoicesFor(where.variant, where.inRoom, voiceChoice);
  const setAgentVoices = useCallback((on: boolean) => { if (!roomScreen) setAgentVoice(on); setVoiceChoice(on); }, [roomScreen]);

  const [fullscreen, setFullscreen] = useState<boolean>(() => typeof document !== "undefined" && !!document.fullscreenElement);
  useEffect(() => {
    const on = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", on);
    return () => document.removeEventListener("fullscreenchange", on);
  }, []);
  const toggleFullscreen = useCallback(() => {
    void (async () => {
      try { if (!document.fullscreenElement) await document.documentElement.requestFullscreen(); else await document.exitFullscreen(); }
      catch { /* the browser refused; the stage still fills the window */ }
    })();
  }, []);

  const [reactions, setReactions] = useState<Map<string, ShownReaction>>(() => new Map());
  const addReaction = useCallback((r: ReactionEvent) => {
    if (!r.user) return;
    setReactions((m) => { const next = new Map(m); next.set(r.user, { ...r, shownAt: Date.now() }); return next; });
  }, []);
  const hasReactions = reactions.size > 0;
  useEffect(() => {
    if (!hasReactions) return undefined;
    const t = window.setInterval(() => setReactions((m) => pruneReactions(m, Date.now())), 1000);
    return () => window.clearInterval(t);
  }, [hasReactions]);

  const [savedNow, setSavedNow] = useState(false);
  const savedTimer = useRef<number | null>(null);
  const markSaved = useCallback(() => {
    setSavedNow(true);
    if (savedTimer.current) window.clearTimeout(savedTimer.current);
    savedTimer.current = window.setTimeout(() => setSavedNow(false), SAVED_MS);
  }, []);
  useEffect(() => () => { if (savedTimer.current) window.clearTimeout(savedTimer.current); }, []);

  return { panel, setPanel, togglePanel, layout, setLayout, pinned, setPinned, agentVoices, setAgentVoices, fullscreen, toggleFullscreen, reactions, addReaction, savedNow, markSaved };
}

// ---- phone: the controls fade after a while without a touch (research/04 section 6.5) ----------------------------------------

/** How long the phone's controls stay after the last touch. */
export const CONTROLS_MS = 4000;

/** The phone's top bar and control bar fade out CONTROLS_MS after the last touch, click or key and come back on the next one. They
 * never fade while `hold` is true (a panel, a sheet or a dialog open, the hand raised, dictating, a screen share on). Off: always
 * shown. The layout keeps its place: the shell only changes the opacity. */
export function useControlsAutoHide(enabled: boolean, hold: boolean, ms = CONTROLS_MS): { hidden: boolean; poke: () => void } {
  const [hidden, setHidden] = useState(false);
  const timer = useRef<number | null>(null);
  const live = useRef({ enabled, hold });
  live.current = { enabled, hold };
  const clear = () => { if (timer.current !== null) { window.clearTimeout(timer.current); timer.current = null; } };
  const poke = useCallback(() => {
    setHidden(false);
    clear();
    const { enabled: on, hold: held } = live.current;
    if (on && !held) timer.current = window.setTimeout(() => { timer.current = null; setHidden(true); }, ms);
  }, [ms]);
  useEffect(() => { poke(); return clear; }, [enabled, hold, poke]);
  useEffect(() => {
    if (!enabled) return undefined;
    const on = () => poke();
    window.addEventListener("pointerdown", on, true);
    window.addEventListener("keydown", on, true);
    return () => { window.removeEventListener("pointerdown", on, true); window.removeEventListener("keydown", on, true); };
  }, [enabled, poke]);
  return { hidden: enabled && !hold && hidden, poke };
}

// ---- Save data (research/04 section 7) ------------------------------------------------------------------------------------

export const SAVE_DATA_KEY = "tbnik.call.savedata";

export function readSaveData(): boolean {
  try { return sessionStorage.getItem(SAVE_DATA_KEY) === "on"; } catch { return false; }
}

/** The highest quality asked of a remote video under Save data: the cameras at the low layer, a shared screen at the middle one
 * (it carries text); without Save data, the high layer (LiveKit's adaptive stream still sizes it to the tile). */
export function savedQuality(source: Track.Source, saveData: boolean): VideoQuality {
  if (!saveData) return VideoQuality.HIGH;
  return source === Track.Source.ScreenShare ? VideoQuality.MEDIUM : VideoQuality.LOW;
}

function applyQuality(room: Room | null, saveData: boolean) {
  if (!room) return;
  for (const p of room.remoteParticipants.values()) {
    for (const pub of p.videoTrackPublications.values()) {
      if (pub.isSubscribed) pub.setVideoQuality(savedQuality(pub.source, saveData));
    }
  }
}

/** "Save data": on turns my camera off (once, and again when the video connects with it on) and keeps the remote video at the lower
 * quality; the choice lasts for this tab (sessionStorage). The person may still turn the camera back on. */
export function useSaveData(video: Pick<CallVideo, "room" | "status" | "camOn" | "toggleCam" | "tick">) {
  const [saveData, setRaw] = useState<boolean>(readSaveData);
  const v = useRef(video);
  v.current = video;
  const setSaveData = useCallback((on: boolean) => {
    setRaw(on);
    try { if (on) sessionStorage.setItem(SAVE_DATA_KEY, "on"); else sessionStorage.removeItem(SAVE_DATA_KEY); } catch { /* no storage: this page only */ }
    if (on && v.current.status === "connected" && v.current.camOn) void v.current.toggleCam().catch(() => undefined);
  }, []);
  // Joined with the camera on while Save data is remembered: turn it off once.
  useEffect(() => {
    if (saveData && video.status === "connected" && v.current.camOn) void v.current.toggleCam().catch(() => undefined);
  }, [video.status]); // eslint-disable-line react-hooks/exhaustive-deps
  // The remote video's quality follows the choice (tick changes when tracks come and go).
  useEffect(() => { applyQuality(video.room, saveData); }, [video.room, video.tick, saveData]);
  return { saveData, setSaveData };
}

// ---- the room screen keeps the projector awake ----------------------------------------------------------------------------

type WakeLockLike = { release: () => Promise<void> };
type WakeLockApi = { request: (type: "screen") => Promise<WakeLockLike> };

/** Asks the browser to keep the screen awake while `enabled` (the room screen), again when the tab comes back (the browser drops the
 * lock when the tab is hidden), and releases it on close. Where the browser has no wake lock, or refuses, nothing happens. */
export function useWakeLock(enabled: boolean) {
  useEffect(() => {
    if (!enabled || typeof navigator === "undefined") return undefined;
    const api = (navigator as Navigator & { wakeLock?: WakeLockApi }).wakeLock;
    if (!api?.request) return undefined;
    let lock: WakeLockLike | null = null;
    let done = false;
    const ask = async () => {
      if (done || document.visibilityState !== "visible") return;
      try {
        const l = await api.request("screen");
        if (done) { void l.release().catch(() => undefined); return; }
        lock = l;
      } catch { /* refused (battery saver, not allowed): the projector's own settings decide */ }
    };
    const onVisible = () => { if (document.visibilityState === "visible") void ask(); };
    void ask();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      done = true;
      document.removeEventListener("visibilitychange", onVisible);
      if (lock) void lock.release().catch(() => undefined);
      lock = null;
    };
  }, [enabled]);
}

/** True when the key press comes from a place where people type (shortcuts then stay quiet, except Esc). */
export function isTypingTarget(t: EventTarget | null): boolean {
  if (!t || !(t instanceof HTMLElement)) return false;
  const tag = t.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return t.isContentEditable || !!t.closest("[contenteditable=''], [contenteditable='true']");
}

/** The shortcut a key press asks for, per SHORTCUTS (types.ts); null when none. Pure, so it can be checked on its own. */
export type ShortcutId = "mic" | "cam" | "hand" | "present" | "chat" | "people" | "agenda" | "escape" | "fullscreen" | "next" | "previous" | "help";
export function shortcutOf(e: { key: string; code?: string; ctrlKey: boolean; metaKey?: boolean; altKey: boolean; shiftKey: boolean }, coordinator: boolean): ShortcutId | null {
  const ctrl = e.ctrlKey || !!e.metaKey;
  const code = e.code ?? "";
  const letter = code.startsWith("Key") ? code.slice(3).toLowerCase() : e.key.toLowerCase();
  if (e.key === "Escape") return "escape";
  if (ctrl && e.altKey) {
    if (letter === "h") return "hand";
    if (letter === "t") return "present";
    if (letter === "c") return "chat";
    if (letter === "p") return "people";
    if (letter === "a") return "agenda";
    return null;
  }
  if (ctrl && !e.altKey && !e.shiftKey) {
    if (letter === "d") return "mic";
    if (letter === "e") return "cam";
    return null;
  }
  if (ctrl || e.altKey) return null;
  if (e.key === "?") return "help";
  if (e.shiftKey) return null;
  if (letter === "f") return "fullscreen";
  if (coordinator && letter === "n") return "next";
  if (coordinator && letter === "p") return "previous";
  return null;
}

/** A Radix dialog, menu or popover is open: Esc belongs to it. */
function layerOpen(): boolean {
  return !!document.querySelector("[role=dialog][data-state=open], [role=menu][data-state=open], [data-radix-popper-content-wrapper]");
}

/** The keyboard shortcuts of the call. `extra` carries what lives outside the context (the dialog, next and previous case). */
export function useShortcuts(ctx: CallCtx | null, extra: { openHelp: () => void; next: () => void; previous: () => void }) {
  const ref = useRef({ ctx, extra });
  ref.current = { ctx, extra };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { ctx: c, extra: x } = ref.current;
      if (!c || c.variant === "room" && e.key !== "f" && e.key !== "F" && e.key !== "Escape") return;
      const id = shortcutOf(e, c.variant === "coordinator" && c.canManage);
      if (!id) return;
      if (id !== "escape" && isTypingTarget(e.target)) return;
      if (e.repeat && id !== "escape") return;
      const v = c.video;
      const videoLive = v.status === "connected" && !!v.room;
      switch (id) {
        case "escape":
          if (layerOpen()) return;
          if (isTypingTarget(e.target)) return;  // Esc in a text box (the decision form) never closes its panel (review finding 6)
          // an agent speaking on this device stops first (here only; the others keep hearing it), the next Esc closes the panel
          if (c.speakingNow) { c.stopAgentAudio(); e.preventDefault(); return; }
          if (c.panel) { c.setPanel(null); e.preventDefault(); }
          return;
        case "mic": e.preventDefault(); if (videoLive && !c.dictating) void v.toggleMic(); return;
        case "cam": e.preventDefault(); if (videoLive) void v.toggleCam(); return;
        case "hand": e.preventDefault(); if (c.inSession && c.admitted) void c.actions.hand(!c.hands.has(c.me)).catch(() => {}); return;
        case "present": e.preventDefault(); if (v.toggleShare) void v.toggleShare(); return;
        case "chat": e.preventDefault(); c.togglePanel("chat"); return;
        case "people": e.preventDefault(); c.togglePanel("people"); return;
        case "agenda": e.preventDefault(); c.togglePanel("agenda"); return;
        case "fullscreen": e.preventDefault(); c.toggleFullscreen(); return;
        case "help": e.preventDefault(); x.openHelp(); return;
        case "next": e.preventDefault(); x.next(); return;
        case "previous": e.preventDefault(); x.previous(); return;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

export function meetingCount(attendance: Array<{ user: string; status: string }>, identities: Array<string | null | undefined>): number {
  const users = new Set(attendance.filter((a) => a.status === "present" || a.status === "remote").map((a) => a.user));
  for (const id of identities) {
    if (!id || isRoomScreen(id)) continue;
    users.add(identityUser(id));
  }
  return users.size;
}

/** The count of the call for the bar and the room screen's footer (recomputed when LiveKit's participants change). */
export function useMeetingCount(): number {
  const c = useCall();
  const room = c.video.room;
  const ids = room ? [room.localParticipant?.identity, ...Array.from(room.remoteParticipants.values()).map((p) => p.identity)] : [];
  return meetingCount(c.state.attendance ?? [], ids);
}
