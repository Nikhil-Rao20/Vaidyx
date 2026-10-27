// The agents' voice on this device (night-v3 6.1, research/05 sections 5 and 11.3). Every sentence an agent says is fetched by
// reference ({kind: "meeting_answer", meeting_id, id: <question>, index}) from the app, which reads answer.speech[index], a text that
// is on the screen: nothing is ever spoken from the text of a live event. The speaker plays one sentence after the other as the
// "agent_speech" events name them, tells the server when this device starts and stops playing an answer (so the tile's "Speaking"
// is true; renewed every 15 s while it plays), waits while the person dictates or another voice of the page reads aloud, keeps the
// queue when the browser blocks sound until a tap ("Tap to allow agent voices"), and stops on "agent_stop", on Esc, when the agent
// voices are switched off, on Leave and when the call closes. Framework-free (checked in node), with a small React hook.
import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import type { SpeakHandle, SpeakHandlers } from "@/lib/voice";
import type { MeetingQuestion } from "@/lib/live";

/** One sentence of an agent's answer: the question it answers and its place in answer.speech. */
export interface SpeakItem { question: string; index: number; role?: string }

/** What the shell shows: the sentence playing now, whether the browser waits for a tap, and how many sentences wait. */
export interface SpeakerSnapshot { speakingNow: { question: string; index: number } | null; blocked: boolean; queued: number }

type TimerId = ReturnType<typeof setTimeout>;
export interface SpeakerTimers {
  setInterval: (fn: () => void, ms: number) => TimerId;
  clearInterval: (id: TimerId) => void;
  setTimeout: (fn: () => void, ms: number) => TimerId;
  clearTimeout: (id: TimerId) => void;
}

export interface SpeakerDeps {
  /** Plays one sentence by reference (lib/voice.ts speak) and calls the handlers as it goes. */
  speak: (item: SpeakItem, handlers: SpeakHandlers) => SpeakHandle;
  /** Tells the server this device plays (true) or stopped playing (false) an answer (api.agentAudio). Errors are swallowed. */
  report: (question: string, playing: boolean) => unknown;
  /** Another voice of the page reads aloud now (a read-aloud button): wait instead of cutting it off. */
  busy?: () => boolean;
  timers?: SpeakerTimers;
  renewMs?: number;
  retryMs?: number;
}

/** How often a device renews "I am playing this answer" (the server forgets a report after 30 s). */
export const RENEW_MS = 15_000;
/** How long to wait before trying again while another voice of the page reads aloud. */
export const BUSY_RETRY_MS = 1000;

const defaultTimers: SpeakerTimers = {
  setInterval: (fn, ms) => globalThis.setInterval(fn, ms),
  clearInterval: (id) => globalThis.clearInterval(id),
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (id) => globalThis.clearTimeout(id),
};

/** The browser refused to play sound before a tap on the page (play() rejected with NotAllowedError). */
export function isAutoplayBlock(err: unknown): boolean {
  return !!err && typeof err === "object" && "name" in err && (err as { name: unknown }).name === "NotAllowedError";
}

const keyOf = (i: { question: string; index: number }) => `${i.question}#${i.index}`;

type Entry = { item: SpeakItem; handle: SpeakHandle | null };

export class AgentSpeaker {
  private deps: SpeakerDeps;
  private timers: SpeakerTimers;
  private queue: SpeakItem[] = [];
  private current: Entry | null = null;
  private selfStop = false;
  /** Questions this device told the server it plays. */
  private reporting = new Set<string>();
  /** Sentences played, failed or dropped (never played again on this device). */
  private done = new Set<string>();
  /** Questions stopped on this device: later sentences of them are not played. */
  private stopped = new Set<string>();
  private renewTimer: TimerId | null = null;
  private retryTimer: TimerId | null = null;
  private held = false;
  private enabled = true;
  private blocked = false;
  private closed = false;
  private now: SpeakerSnapshot["speakingNow"] = null;
  private listeners = new Set<() => void>();
  private snap: SpeakerSnapshot = { speakingNow: null, blocked: false, queued: 0 };

  constructor(deps: SpeakerDeps) {
    this.deps = deps;
    this.timers = deps.timers ?? defaultTimers;
  }

  // ---- reading ----------------------------------------------------------------------------------------------------------
  /** The same object until something changes (useSyncExternalStore). */
  readonly snapshot = (): SpeakerSnapshot => this.snap;
  readonly subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => { this.listeners.delete(fn); };
  };

  // ---- commands ---------------------------------------------------------------------------------------------------------
  /** A sentence named by an "agent_speech" event. False when it is not taken (voices off, already played, stopped here). */
  readonly enqueue = (item: SpeakItem): boolean => {
    if (this.closed || !this.enabled || !item.question || !Number.isInteger(item.index) || item.index < 0) return false;
    if (this.stopped.has(item.question)) return false;
    const k = keyOf(item);
    if (this.done.has(k) || (this.current && keyOf(this.current.item) === k) || this.queue.some((x) => keyOf(x) === k)) return false;
    // A question's sentences keep their order even when an event arrives late; other questions keep the order of arrival.
    const at = this.queue.findIndex((x) => x.question === item.question && x.index > item.index);
    if (at >= 0) this.queue.splice(at, 0, item); else this.queue.push(item);
    this.emit();
    this.pump();
    return true;
  };

  /** "agent_stop" for a question (or a Stop on this screen): its queued sentences go, the one playing stops, the rest is ignored. */
  readonly stopQuestion = (question: string): void => {
    if (!question) return;
    this.stopped.add(question);
    this.queue = this.queue.filter((x) => x.question !== question);
    if (this.current?.item.question === question) this.halt(true);
    this.endReport(question);
    this.emit();
    this.pump();
  };

  /** Esc, voices off, Leave, the case changed, the call closed: everything stops and the answers heard so far are not resumed. */
  readonly stopAll = (): void => {
    for (const x of this.queue) this.stopped.add(x.question);
    if (this.current) this.stopped.add(this.current.item.question);
    this.queue = [];
    this.halt(true);
    for (const q of [...this.reporting]) this.endReport(q);
    this.blocked = false;
    this.clearRetry();
    this.emit();
  };

  /** While the person dictates nothing new starts; a sentence playing is stopped and played again after. */
  readonly setHeld = (held: boolean): void => {
    if (held === this.held) return;
    this.held = held;
    if (held && this.current) {
      const item = this.current.item;
      this.halt(false);
      this.queue.unshift(item);
      if (!this.queue.slice(1).some((x) => x.question === item.question)) this.endReport(item.question);
    }
    this.emit();
    if (!held) this.pump();
  };

  /** Agent voices on or off on this device (off stops everything). */
  readonly setEnabled = (on: boolean): void => {
    if (on === this.enabled) return;
    this.enabled = on;
    if (!on) this.stopAll();
  };

  /** After a tap that primed the audio ("Tap to allow agent voices"): play the waiting sentences. */
  readonly resume = (): void => {
    if (!this.blocked) return;
    this.blocked = false;
    this.emit();
    this.pump();
  };

  /** The hook mounts the speaker (again, under React's strict mode). */
  readonly open = (): void => { this.closed = false; };

  /** The call closed: stop and report, keep nothing playing. */
  readonly close = (): void => {
    this.stopAll();
    this.closed = true;
    this.clearRetry();
    if (this.renewTimer !== null) { this.timers.clearInterval(this.renewTimer); this.renewTimer = null; }
  };

  // ---- inside -----------------------------------------------------------------------------------------------------------
  private pump(): void {
    if (this.closed || !this.enabled || this.held || this.blocked || this.current || !this.queue.length) return;
    if (this.deps.busy?.()) {
      if (this.retryTimer === null) this.retryTimer = this.timers.setTimeout(() => { this.retryTimer = null; this.pump(); }, this.deps.retryMs ?? BUSY_RETRY_MS);
      return;
    }
    const item = this.queue.shift()!;
    const entry: Entry = { item, handle: null };
    this.current = entry;
    const mine = () => this.current === entry;
    const handlers: SpeakHandlers = {
      onSpeaking: () => {
        if (!mine()) return;
        this.now = { question: item.question, index: item.index };
        this.startReport(item.question);
        this.emit();
      },
      onEnd: () => { if (mine()) this.finish(entry, false); },
      // Stopped by someone else on this page (a read-aloud button, the microphone starting): the rest of this answer is not read here.
      onStop: () => { if (mine() && !this.selfStop) this.finish(entry, true); },
      onError: (err) => {
        if (!mine()) return;
        if (isAutoplayBlock(err)) {
          this.current = null;
          this.now = null;
          this.blocked = true;
          this.queue.unshift(item);
          if (!this.queue.slice(1).some((x) => x.question === item.question)) this.endReport(item.question);
          this.emit();
          return;
        }
        this.finish(entry, false);
      },
    };
    this.emit();
    try {
      const h = this.deps.speak(item, handlers);
      entry.handle = h;
      if (!mine()) return; // the handlers already ran
    } catch (e) {
      handlers.onError?.(e);
    }
  }

  private finish(entry: Entry, external: boolean): void {
    const q = entry.item.question;
    this.current = null;
    this.now = null;
    this.done.add(keyOf(entry.item));
    if (external) {
      this.stopped.add(q);
      this.queue = this.queue.filter((x) => x.question !== q);
    }
    if (!this.queue.some((x) => x.question === q)) this.endReport(q);
    this.emit();
    this.pump();
  }

  /** Stops the sentence playing without the handlers taking it as someone else's stop; `drop` marks it as heard. */
  private halt(drop: boolean): void {
    const e = this.current;
    if (!e) return;
    this.current = null;
    this.now = null;
    if (drop) this.done.add(keyOf(e.item));
    this.selfStop = true;
    try { e.handle?.stop(); } catch { /* already stopped */ } finally { this.selfStop = false; }
  }

  private send(question: string, playing: boolean): void {
    try {
      const r = this.deps.report(question, playing) as { catch?: (f: () => void) => unknown } | null | undefined;
      if (r && typeof r.catch === "function") r.catch(() => undefined);
    } catch { /* best effort: the server forgets a report after 30 s */ }
  }

  private startReport(question: string): void {
    if (!this.reporting.has(question)) {
      this.reporting.add(question);
      this.send(question, true);
    }
    if (this.renewTimer === null) {
      this.renewTimer = this.timers.setInterval(() => { for (const q of this.reporting) this.send(q, true); }, this.deps.renewMs ?? RENEW_MS);
    }
  }

  private endReport(question: string): void {
    if (this.reporting.delete(question)) this.send(question, false);
    if (!this.reporting.size && this.renewTimer !== null) { this.timers.clearInterval(this.renewTimer); this.renewTimer = null; }
  }

  private clearRetry(): void {
    if (this.retryTimer !== null) { this.timers.clearTimeout(this.retryTimer); this.retryTimer = null; }
  }

  private emit(): void {
    const next: SpeakerSnapshot = { speakingNow: this.now, blocked: this.blocked, queued: this.queue.length };
    const s = this.snap;
    if (s.blocked === next.blocked && s.queued === next.queued && s.speakingNow?.question === next.speakingNow?.question && s.speakingNow?.index === next.speakingNow?.index) return;
    this.snap = next;
    for (const fn of [...this.listeners]) fn();
  }
}

// ---- rules the shell applies -------------------------------------------------------------------------------------------------

/** Agent voices for this person: their stored choice when they made one; otherwise on, except a member in the room (the room
 * screen plays the answers for them: Phase 4 decision 6). The room screen never reads the stored choice of the login it runs under,
 * so the caller passes only the choice made on that screen. */
export function agentVoicesFor(variant: string, inRoom: boolean, stored: boolean | null): boolean {
  if (stored !== null) return stored;
  if (variant === "room") return true;
  return !(variant === "member" && inRoom);
}

/** The sentence an "agent_speech" event names ({role, question, index, final}), or null when it names none. The event never
 * carries text: the sentence is fetched by reference. */
export function speechItem(ev: { [k: string]: unknown }): SpeakItem | null {
  const question = typeof ev.question === "string" ? ev.question : "";
  const index = typeof ev.index === "number" ? ev.index : Number.NaN;
  if (!question || !Number.isInteger(index) || index < 0) return null;
  return typeof ev.role === "string" && ev.role ? { question, index, role: ev.role } : { question, index };
}

/** True when the question belongs to the Case File on the floor (a question not yet in the state is a new one, so it does). */
export function onTheFloor(questions: MeetingQuestion[] | undefined, question: string, cid: string | null): boolean {
  if (!cid) return false;
  const q = (questions ?? []).find((x) => x.id === question);
  if (!q) return true;
  return !q.case_id || q.case_id === cid;
}

// ---- the hook --------------------------------------------------------------------------------------------------------------

/** One speaker per meeting (`key`), on while `enabled`, waiting while `held`; closed when the call unmounts. */
export function useAgentSpeaker(key: string, makeDeps: () => SpeakerDeps, opts: { enabled: boolean; held: boolean }): { speaker: AgentSpeaker } & SpeakerSnapshot {
  const make = useRef(makeDeps);
  make.current = makeDeps;
  const speaker = useMemo(() => new AgentSpeaker(make.current()), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { speaker.open(); return () => speaker.close(); }, [speaker]);
  useEffect(() => { speaker.setEnabled(opts.enabled); }, [speaker, opts.enabled]);
  useEffect(() => { speaker.setHeld(opts.held); }, [speaker, opts.held]);
  const snap = useSyncExternalStore(speaker.subscribe, speaker.snapshot, speaker.snapshot);
  return { speaker, ...snap };
}
