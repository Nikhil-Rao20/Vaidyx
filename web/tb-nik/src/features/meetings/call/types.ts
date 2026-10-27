// The call shell (night-v3 Phase 5, research/04 section 6): one in-call layout for the member view, the coordinator's control view
// and the room screen. This file is the contract between the shell (CallShell.tsx), the stage and strip (StageContent.tsx,
// Strip.tsx) and the side panels (panels/*.tsx): shared kinds, the context every piece reads, and the actions the shell wires.
import type { Room } from "livekit-client";
import type { AgendaRow, AgentInfo, LiveStatus, MeetingState, Opened, ReactionEvent } from "@/lib/live";
import type { VideoStatus } from "@/lib/video";
import type { Slide } from "../types";

export type CallVariant = "member" | "coordinator" | "room";

/** One side panel at a time (null: none). */
export type PanelKind = "people" | "chat" | "agenda" | "case" | "agents" | "decision" | null;

/** Auto: stage plus strip when something is on the floor, a grid when nothing is. Speaker: the active speaker large. Grid: tiles
 * only. Spotlight: what the coordinator set (chosen by itself when a spotlight arrives and the person has no pin). */
export type LayoutKind = "auto" | "speaker" | "grid" | "spotlight";

export type ReactionKind = "agree" | "thanks" | "applause" | "question";
export const REACTIONS: Array<{ kind: ReactionKind; word: string; glyph: string }> = [
  { kind: "agree", word: "Agree", glyph: "👍" },
  { kind: "thanks", word: "Thanks", glyph: "🙏" },
  { kind: "applause", word: "Applause", glyph: "👏" },
  { kind: "question", word: "Question", glyph: "❓" },
];

/** A reaction shown on a tile for a moment (the shell keeps the last one per user for about 3 s). */
export interface ShownReaction extends ReactionEvent { shownAt: number }

/** The role badge on a tile and in the People panel. */
export type RoleBadge = "head" | "coordinator" | "presenter" | "expert";

/** What the video hook gives the shell (lib/video.ts useVideoRoom, extended in Phase 5). */
export interface CallVideo {
  room: Room | null;
  status: VideoStatus;
  error: string | null;
  micOn: boolean;
  camOn: boolean;
  toggleMic: () => Promise<void>;
  toggleCam: () => Promise<void>;
  tick: number;
  /** The local link: excellent, good, poor, lost, unknown. */
  quality?: string;
  /** True when the browser blocks remote audio until a click (room.canPlaybackAudio false). */
  audioBlocked?: boolean;
  startAudio?: () => Promise<void>;
  /** Change a device after joining (room.switchActiveDevice). */
  switchDevice?: (kind: "audioinput" | "audiooutput" | "videoinput", deviceId: string) => Promise<void>;
  /** Join again after a disconnect. */
  rejoin?: () => void;
  /** A plain sentence when a device was unplugged (lib/video.ts), or null. */
  deviceChanged?: string | null;
  /** LiveKit identities speaking now, most recent first, held for 2 s. */
  activeSpeakers?: string[];
  activeDevice?: (kind: "audioinput" | "audiooutput" | "videoinput") => string | undefined;
  /** Screen share (item 5.2). */
  shareOn?: boolean;
  toggleShare?: () => Promise<void>;
}

/** The actions a panel or a tile may call; the shell wires each to its API call, announces the result and refreshes the state.
 * Every action rejects with the server's message (errorText shows it). */
export interface CallActions {
  admit: (user: string) => Promise<unknown>;
  admitAll: () => Promise<unknown>;
  /** Coordinator: put a case (and a slide) on the floor. */
  go: (caseId: string, slide?: number) => Promise<unknown>;
  /** Coordinator (or the case's presenter): a record page, the images, or back to the slide. */
  open: (kind: "record" | "images" | "none", docId?: string) => Promise<unknown>;
  timer: (action: "start" | "stop" | "reset", minutes?: number) => Promise<unknown>;
  endCase: () => Promise<unknown>;
  /** Opens the End meeting confirmation. */
  endMeeting: () => void;
  ask: (text: string, role?: string) => Promise<unknown>;
  hand: (raised: boolean) => Promise<unknown>;
  react: (kind: ReactionKind) => Promise<unknown>;
  spotlight: (users: string[]) => Promise<unknown>;
  /** "I am in the room" or "I am remote". */
  presence: (mode: "room" | "remote") => Promise<unknown>;
  leave: () => void;
  /** Member: open the end-of-case card dialog. */
  card: () => void;
  /** Item 5.3: a meeting chat line. */
  chat?: (text: string) => Promise<unknown>;
  /** Item 5.2: allow or withdraw a person's right to present. */
  allowPresent?: (user: string, allowed: boolean) => Promise<unknown>;
  /** Item 5.2: tell the meeting that I start or stop sharing (the pixels go through LiveKit). */
  presenting?: (on: boolean) => Promise<unknown>;
}

/** Everything the shell knows, read by the panels, the strip and the stage through useCall(). */
export interface CallCtx {
  mid: string;
  variant: CallVariant;
  state: MeetingState;
  /** My login (empty on the room screen's own identity). */
  me: string;
  cid: string | null;
  row: AgendaRow | null;
  /** The agenda in order: for discussion then for noting. */
  order: AgendaRow[];
  slides: Slide[];
  slidesStatus: "idle" | "loading" | "error" | "ready";
  slidesError?: unknown;
  /** What the room shows (the coordinator's slide index). */
  sharedSlide: number;
  /** What my stage shows: the shared slide while following, else my own. */
  shownSlide: number;
  following: boolean;
  setFollowing: (f: boolean) => void;
  /** Member: look at another slide on my own (steps away); coordinator: changes the room's slide (actions.go). */
  showSlide: (i: number) => void;
  opened: Opened | null;
  video: CallVideo;
  videoAvailable: boolean;
  /** The app's live channel (WebSocket) state, apart from the video. */
  liveStatus: LiveStatus;
  liveDetail?: string;
  /** True for about 8 s after a "decision" event (the strip says "Decision saved"). */
  savedNow: boolean;
  /** The "Join video" path when the person skipped the pre-join. */
  joinVideo: () => void;
  dictating: boolean;
  panel: PanelKind;
  setPanel: (p: PanelKind) => void;
  togglePanel: (p: Exclude<PanelKind, null>) => void;
  layout: LayoutKind;
  setLayout: (l: LayoutKind) => void;
  /** The tile key I pinned for myself (sessionStorage), or null. */
  pinned: string | null;
  setPinned: (key: string | null) => void;
  spotlight: string[];
  agents: AgentInfo[];
  /** Agent voices for me (lib/voice.ts agentVoiceEnabled). */
  agentVoices: boolean;
  setAgentVoices: (on: boolean) => void;
  reactions: Map<string, ShownReaction>;
  hands: Set<string>;
  canManage: boolean;
  canRecord: boolean;
  admitted: boolean;
  waiting: boolean;
  inSession: boolean;
  inRoom: boolean;
  phone: boolean;
  fullscreen: boolean;
  toggleFullscreen: () => void;
  announce: (text: string) => void;
  refresh: () => void;
  /** The last error of an action, shown by the shell; panels may show their own as well. */
  error: string | null;
  actions: CallActions;
}

/** The role badges of an attendee, from the live state. */
export function badgesOf(a: { user: string; head?: boolean; outside_expert?: boolean }, s: MeetingState, presenting?: string | null): RoleBadge[] {
  const out: RoleBadge[] = [];
  if (a.head) out.push("head");
  if (a.user === s.current?.presenter?.user || (presenting && a.user === presenting)) out.push("presenter");
  if (a.outside_expert) out.push("expert");
  return out;
}

export const BADGE_WORD: Record<RoleBadge, string> = { head: "Head", coordinator: "Coordinator", presenter: "Presenter", expert: "Outside expert" };

/** The words of an agent's state (true states; the server names them). */
export const AGENT_STATE_WORD: Record<string, string> = {
  ready: "Ready",
  listening: "Listening",
  reading_question: "Reading the question",
  reading: "Reading the question",
  thinking: "Thinking",
  answering: "Answering",
  speaking: "Speaking",
};

/** Keyboard shortcuts of the call (research/04 section 6.10). Never while the focus is in a text box, except Esc. */
export const SHORTCUTS: Array<{ keys: string; aria: string; action: string; who?: "coordinator" }> = [
  { keys: "Ctrl+D", aria: "Control+D", action: "Microphone on or off" },
  { keys: "Ctrl+E", aria: "Control+E", action: "Camera on or off" },
  { keys: "Ctrl+Alt+H", aria: "Control+Alt+H", action: "Raise or lower hand" },
  { keys: "Ctrl+Alt+T", aria: "Control+Alt+T", action: "Present a screen, or stop" },
  { keys: "Ctrl+Alt+C", aria: "Control+Alt+C", action: "Chat and questions" },
  { keys: "Ctrl+Alt+P", aria: "Control+Alt+P", action: "People" },
  { keys: "Ctrl+Alt+A", aria: "Control+Alt+A", action: "Agenda" },
  { keys: "Esc", aria: "Escape", action: "Close the panel or menu" },
  { keys: "F", aria: "F", action: "Full screen" },
  { keys: "N / P", aria: "N", action: "Next or previous case", who: "coordinator" },
  { keys: "?", aria: "Shift+?", action: "Show the shortcuts" },
];
