// The call shell's own state (night-v3 5.1): which side panel is open, the layout, my pin (this browser only), the agent voices
// for me, full screen, the reactions shown for a moment, "Decision saved" for 8 s, and the keyboard shortcuts of the call.
import { createContext, useCallback, useEffect, useRef, useState } from "react";
import { agentVoiceEnabled, onAgentVoiceChange, setAgentVoice } from "@/lib/voice";
import type { ReactionEvent } from "@/lib/live";
import type { CallCtx, LayoutKind, PanelKind, ShownReaction } from "./types";

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
}
const noop = () => {};
export const ShellContext = createContext<ShellExtras>({ joined: false, idx: -1, minutes: 10, setMinutes: noop, next: noop, previous: noop, openShortcuts: noop, cardAsked: false, handPending: false, goPending: false, timerPending: false, endPending: false, presencePending: false, menu: null, setMenu: noop });

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

export function useCallState(mid: string, spotlight: string[]) {
  const [panel, setPanelRaw] = useState<PanelKind>(null);
  const setPanel = useCallback((p: PanelKind) => setPanelRaw(p), []);
  const togglePanel = useCallback((p: Exclude<PanelKind, null>) => setPanelRaw((cur) => (cur === p ? null : p)), []);

  const [layout, setLayout] = useState<LayoutKind>("auto");
  const [pinned, setPinnedRaw] = useState<string | null>(() => readPin(mid));
  const setPinned = useCallback((key: string | null) => {
    setPinnedRaw(key);
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

  const [agentVoices, setAgentVoicesRaw] = useState<boolean>(() => agentVoiceEnabled());
  useEffect(() => onAgentVoiceChange(setAgentVoicesRaw), []);
  const setAgentVoices = useCallback((on: boolean) => { setAgentVoice(on); setAgentVoicesRaw(on); }, []);

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
          if (c.panel && !layerOpen()) { c.setPanel(null); e.preventDefault(); }
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
