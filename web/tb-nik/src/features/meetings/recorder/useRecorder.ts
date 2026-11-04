// The coordinator's recorder (meetings-v2 5.2, owner decision D11, T3): Record, Pause, Resume and Stop, and the capture that runs in
// this browser while the server says the recorder is on. Members and the room screen never capture anything: the shell calls this hook
// with `enabled` only on the coordinator's control view. NO AUDIO IS EVER KEPT (capture.ts says how).
//
// What runs when:
// - the server's state is on, this is the coordinator's control view, and this tab holds the recorder lock (one tab of the browser
//   captures, never two): one TrackRecorder per audio track (capture.ts callTracks; the laptop microphone alone without the video call);
//   the set follows the call: a member joining, leaving, muting or unmuting starts or stops the recorder of that track;
// - Pause and Stop: the recorders stop, their last segments are posted and waited for, then the action is posted (the server refuses a
//   chunk once paused or stopped); Stop asks first ("Stop recording? The text so far is kept; no audio is kept.");
// - before the case on the floor changes or ends (Next, Previous, a rail click, End case, Take up): `cut` ends every running segment
//   and waits for its post, so the words said about one Case File are stored under that Case File (the server takes the case on the
//   floor when a chunk arrives);
// - the tab closing (pagehide): "stop" is posted with keepalive; the segment not yet sent is dropped (never kept to send later);
// - the control view closing inside the app (Leave the controls): the last segments are posted, then "stop" after a short grace, unless
//   the control view opens again in this tab meanwhile (Join video goes through the pre-join and back);
// - a chunk that fails is tried once more; a failure is counted and shown as one quiet line.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Room } from "livekit-client";
import type { Attendee, RecordingStateWord, RecordingView } from "@/lib/live";
import type { VideoStatus } from "@/lib/video";
import { errorText } from "@/features/casefile/components/common";
import { postChunk, setRecording, stopOnLeave, type RecordingAction } from "./api";
import { ROOM, TrackRecorder, UploadQueue, callTracks, recorderMime, sliceFor, type Chunk, type QueueResult, type WantedTrack } from "./capture";

/** How long the control view may be away (the pre-join of Join video) before the recorder is stopped for it. */
export const LEAVE_GRACE_MS = 30_000;
/** How long Pause, Stop and a case change wait for the last segments to be posted. */
export const FLUSH_MS = 20_000;
export const CUT_MS = 12_000;

/** The words of the Stop confirmation (owner rule: the text stays, the audio never). */
export const STOP_CONFIRM = { title: "Stop recording?", text: "The text so far is kept; no audio is kept." };

const pendingStops = new Map<string, number>();

/** The time recorded, per meeting, for this tab (it survives the control view closing and opening again, e.g. for Join video). */
type Clock = { base: number; since: number | null; seeded: boolean };
const clocks = new Map<string, Clock>();
function clockOf(mid: string): Clock {
  let c = clocks.get(mid);
  if (!c) { c = { base: 0, since: null, seeded: false }; clocks.set(mid, c); }
  return c;
}
/** A server start older than this is not trusted to seed the time (a clock or time zone that differs). */
const MAX_SEED_MS = 6 * 3600_000;

export interface RecorderTrack { key: string; speaker: string; label: string }

export interface Recorder {
  /** The recorder's state as this screen knows it (the server's, or the answer to my last action until the server's state follows). */
  state: RecordingStateWord;
  view: RecordingView;
  /** True when this tab captures (another tab of this browser may hold the recorder instead). */
  here: boolean;
  /** The tracks recorded now, each with its speaker and a plain label. */
  tracks: RecorderTrack[];
  /** People in the call who are not admitted to the meeting: never recorded. */
  skipped: string[];
  /** Why nothing or less than expected is recorded now ("Your microphone is off in the call ..."), or null. */
  note: string | null;
  /** Seconds recorded (counted while on). */
  seconds: number;
  sent: number;
  stored: number;
  failed: number;
  /** The last failure in plain words (a quiet line), or null. */
  error: string | null;
  dismissError: () => void;
  /** The action running now (start, pause, resume, stop), "cut" while the last words of a case are posted, else null. */
  busy: RecordingAction | "cut" | null;
  act: (action: RecordingAction) => Promise<boolean>;
  /** Before the case on the floor changes or ends: the running segments are posted first. Never rejects. */
  cut: () => Promise<void>;
}

/** One tab of this browser holds the recorder of a meeting (Web Locks); where the browser has no locks, every tab may capture. */
function useRecorderLock(name: string, want: boolean): boolean {
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (!want) { setHeld(false); return undefined; }
    const locks = (typeof navigator !== "undefined" ? (navigator as Navigator & { locks?: LockManager }).locks : undefined);
    if (!locks?.request) { setHeld(true); return undefined; }
    const ac = new AbortController();
    let release: (() => void) | null = null;
    locks.request(name, { signal: ac.signal }, () => new Promise<void>((res) => { release = res; setHeld(true); })).catch(() => undefined);
    return () => { ac.abort(); release?.(); setHeld(false); };
  }, [name, want]);
  return held;
}

export function useRecorder(o: {
  mid: string; enabled: boolean; recording: RecordingView | null | undefined; inSession: boolean;
  room: Room | null; videoStatus: VideoStatus; videoWanted: boolean; micOn: boolean; dictating: boolean;
  attendance: Attendee[]; me: string; tick: number; announce: (text: string) => void; refresh: () => void;
}): Recorder {
  const { mid, enabled, announce, refresh } = o;
  const server: RecordingView = o.recording ?? { state: "off" };

  // ---- the state: the server's, or my last action's answer until the server's state changes -----------------------------------
  const [override, setOverride] = useState<RecordingView | null>(null);
  const serverKey = `${server.state}|${server.started_at ?? ""}|${server.paused_at ?? ""}|${server.stopped_at ?? ""}`;
  useEffect(() => { setOverride(null); }, [serverKey]);
  const view = override ?? server;
  const state: RecordingStateWord = o.inSession ? view.state : "off";

  const here = useRecorderLock(`tbnik-recorder-${mid}`, enabled);
  const [hold, setHold] = useState(false);
  const active = enabled && here && state === "on" && !hold;

  // ---- the time recorded (counted here while on; kept for this tab across the pre-join; seeded from the server's start, a local time,
  //      when this screen first sees it on, if that start is plausible) -------------------------------------------------------------
  const clock = useRef(clockOf(mid));
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const c = clock.current;
    if (state === "on") {
      if (c.since === null) {
        const started = view.started_at ? Date.parse(view.started_at) : NaN;
        const ago = Date.now() - started;
        c.since = !c.seeded && Number.isFinite(started) && ago >= 0 && ago <= MAX_SEED_MS ? started : Date.now();
      }
      c.seeded = true;
    } else {
      if (c.since !== null) { c.base += Date.now() - c.since; c.since = null; }
      if (state === "off") { c.base = 0; c.seeded = false; }
    }
    setNow(Date.now());
  }, [state]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (state !== "on") return undefined;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [state]);
  const seconds = Math.max(0, Math.floor((clock.current.base + (clock.current.since !== null ? now - clock.current.since : 0)) / 1000));

  // ---- the posts -------------------------------------------------------------------------------------------------------------
  const [counts, setCounts] = useState({ sent: 0, stored: 0, failed: 0 });
  const [error, setError] = useState<string | null>(null);
  const onResult = useCallback((r: QueueResult) => {
    setCounts((c) => ({ sent: c.sent + (r.ok ? 1 : 0), stored: c.stored + (r.ok && r.stored ? 1 : 0), failed: c.failed + (!r.ok && !r.quiet ? 1 : 0) }));
    if (!r.ok && !r.quiet && r.error) setError(r.error);
  }, []);
  const queue = useMemo(() => new UploadQueue((c: Chunk) => postChunk(mid, c.blob, c.fileName, c.speaker, c.startedMs), onResult), [mid, onResult]);

  // ---- the tracks ------------------------------------------------------------------------------------------------------------
  const recorders = useRef(new Map<string, TrackRecorder>());
  const [tracks, setTracks] = useState<RecorderTrack[]>([]);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const callMode = o.videoWanted && (o.videoStatus === "connecting" || o.videoStatus === "connected" || o.videoStatus === "reconnecting");
  const admittedKey = o.attendance.filter((a) => a.status === "present" || a.status === "remote").map((a) => `${a.user}=${a.name}`).join("|");

  const stopAll = useCallback(async (): Promise<void> => {
    const all = [...recorders.current.values()];
    recorders.current.clear();
    setTracks([]);
    await Promise.all(all.map((r) => r.stop()));
  }, []);

  // without the video call: the laptop microphone, opened while capturing and closed after
  const needMic = active && !callMode;
  useEffect(() => {
    if (!needMic) return undefined;
    let gone = false;
    let mine: MediaStream | null = null;
    if (!navigator.mediaDevices?.getUserMedia) { setCaptureError("This browser cannot open the microphone here."); return undefined; }
    navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } }).then((s) => {
      if (gone) { s.getTracks().forEach((t) => t.stop()); return; }
      mine = s; setMicStream(s); setCaptureError(null);
    }).catch((e: unknown) => {
      if (gone) return;
      const name = (e as { name?: string } | null)?.name ?? "";
      setCaptureError(name === "NotAllowedError" ? "The browser did not allow the microphone, so nothing is being recorded." : "The microphone could not be opened, so nothing is being recorded.");
    });
    return () => { gone = true; mine?.getTracks().forEach((t) => t.stop()); setMicStream(null); };
  }, [needMic]);

  // reconcile: start a recorder for each track wanted now, stop (and post the last segment of) each one no longer wanted
  useEffect(() => {
    if (!active) {
      if (recorders.current.size) void stopAll();
      setSkipped([]);
      return;
    }
    const mime = recorderMime();
    if (mime === null) { setCaptureError("This browser cannot record. Use Chrome or Edge on the laptop."); return; }
    const admitted = new Set<string>();
    const names = new Map<string, string>();
    for (const a of o.attendance) if (a.status === "present" || a.status === "remote") { admitted.add(a.user); names.set(a.user, a.name); }
    let wanted: WantedTrack[] = [];
    let left: string[] = [];
    if (callMode) {
      if (o.room && o.videoStatus === "connected") ({ tracks: wanted, skipped: left } = callTracks(o.room, { me: o.me, admitted, names, localOn: o.micOn && !o.dictating }));
    } else {
      const t = micStream?.getAudioTracks()[0];
      if (t && t.readyState === "live" && !o.dictating) wanted = [{ key: `${ROOM}:${t.id}`, track: t, speaker: ROOM, label: "Laptop microphone (Board room)" }];
    }
    const keys = new Set(wanted.map((w) => w.key));
    for (const [k, r] of recorders.current) {
      if (!keys.has(k) || r.track.readyState !== "live") { recorders.current.delete(k); void r.stop(); }
    }
    const slice = sliceFor(wanted.length);
    for (const w of wanted) {
      let r = recorders.current.get(w.key);
      if (!r) {
        r = new TrackRecorder(w.key, w.track, w.speaker, w.label, mime, (c) => queue.push(c), (m) => setCaptureError(m), slice);
        recorders.current.set(w.key, r);
        r.start();
      }
      r.sliceMs = slice;
    }
    setTracks(wanted.map((w) => ({ key: w.key, speaker: w.speaker, label: w.label })));
    setSkipped(left);
  }, [active, callMode, o.room, o.videoStatus, o.micOn, o.dictating, o.tick, admittedKey, micStream, queue, stopAll]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- leaving -------------------------------------------------------------------------------------------------------------------
  const live = useRef({ capturing: false, mid });
  live.current = { capturing: enabled && here && (state === "on" || state === "paused"), mid };
  useEffect(() => {
    if (!enabled) return undefined;
    const t = pendingStops.get(mid);
    if (t !== undefined) { window.clearTimeout(t); pendingStops.delete(mid); }
    // the tab closing: stop for everyone with keepalive; what was not sent is dropped
    const onHide = () => {
      if (!live.current.capturing) return;
      queue.clear();
      for (const r of recorders.current.values()) void r.stop();
      recorders.current.clear();
      stopOnLeave(mid);
    };
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      const wasCapturing = live.current.capturing;
      const rs = [...recorders.current.values()];
      recorders.current.clear();
      // the control view closes inside the app: the last segments go, then "stop" after the grace unless it opens again here
      void Promise.all(rs.map((r) => r.stop())).then(() => queue.drain(FLUSH_MS));
      if (wasCapturing) {
        const id = window.setTimeout(() => { pendingStops.delete(mid); void queue.drain(FLUSH_MS).then(() => setRecording(mid, "stop")).catch(() => undefined); }, LEAVE_GRACE_MS);
        pendingStops.set(mid, id);
      }
    };
  }, [enabled, mid, queue]);

  // ---- the actions ---------------------------------------------------------------------------------------------------------------
  const [busy, setBusy] = useState<Recorder["busy"]>(null);
  const act = useCallback(async (action: RecordingAction): Promise<boolean> => {
    setBusy(action); setError(null); setCaptureError(null);
    if (action === "start" && recorderMime() === null) { setError("This browser cannot record. Use Chrome or Edge on the laptop."); setBusy(null); return false; }
    try {
      if (action === "pause" || action === "stop") {
        // the server refuses a chunk once paused or stopped: the last segments go first
        setHold(true);
        await stopAll();
        await queue.drain(FLUSH_MS);
      }
      const r = await setRecording(mid, action);
      setOverride(r.recording ?? { state: action === "stop" ? "off" : action === "pause" ? "paused" : "on" });
      if (action === "start") setCounts({ sent: 0, stored: 0, failed: 0 });
      announce(action === "start" ? "Recording started: text only, no audio kept." : action === "pause" ? "Recording paused." : action === "resume" ? "Recording resumed." : "Recording stopped. The text so far is kept; no audio is kept.");
      return true;
    } catch (e) {
      setError(errorText(e));
      refresh();
      return false;
    } finally {
      setHold(false);
      setBusy(null);
    }
  }, [mid, queue, stopAll, announce, refresh]);

  const cut = useCallback(async (): Promise<void> => {
    if (!recorders.current.size && queue.size === 0) return;
    setBusy((b) => b ?? "cut");
    try {
      await Promise.all([...recorders.current.values()].map((r) => r.rotate()));
      await queue.drain(CUT_MS);
    } catch { /* never block the meeting */ } finally {
      setBusy((b) => (b === "cut" ? null : b));
    }
  }, [queue]);

  // ---- what this screen says -------------------------------------------------------------------------------------------------
  let note: string | null = captureError;
  if (!note && enabled && state === "on" && !here) note = "The recorder runs in another tab of this browser.";
  if (!note && active && callMode && o.videoStatus === "connected" && (!o.micOn || o.dictating)) note = o.dictating ? "Your microphone is off while you dictate: the room's voices are not recorded until it is back." : "Your microphone is off in the call, so the room's voices are not recorded.";
  if (!note && active && callMode && o.videoStatus !== "connected") note = "Waiting for the video call before recording.";

  return {
    state, view, here, tracks, skipped, note, seconds, sent: counts.sent, stored: counts.stored, failed: counts.failed, error,
    dismissError: () => setError(null), busy, act, cut,
  };
}
