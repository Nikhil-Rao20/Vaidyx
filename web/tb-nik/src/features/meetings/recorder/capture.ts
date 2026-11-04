// The capture of the meeting recorder, in the coordinator's browser only (meetings-v2 5.2, T3). NO AUDIO IS EVER KEPT: each audio track
// is recorded in memory in segments of about 20 s, each segment is posted to the app as soon as it ends and the Blob is let go; nothing
// is written to IndexedDB, localStorage, the Cache or a file, and nothing is kept to send later.
//
// Why a segment is a whole MediaRecorder run and not a `timeslice`: with a timeslice only the first piece carries the WebM header, so
// the later pieces cannot be read on their own by the speech service. Each segment is therefore its own short recording (stop, then
// start again at once on the same track): every chunk is a complete file, at most 60 s and far under 4 MiB (32 kbit/s).
//
// Who is speaking: with the video call connected, one recorder per audio track: the coordinator's own microphone is the Board room
// ("room": the laptop is in the room); each remote member's microphone is that member's login (their LiveKit identity is the login;
// a room screen "<user>#room" is the Board room too). A participant who is not admitted to the meeting is never recorded. A muted
// microphone is not recorded (its recorder stops and starts again when it is unmuted). Without the video call, the laptop microphone
// only, as "room".
import { Track, type Room } from "livekit-client";
import { ApiError } from "@/lib/api";
import { identityUser, isRoomScreen } from "@/lib/video";
import { fileNameFor, pickMimeType } from "@/lib/voice";

/** The speaker word of the Board room microphone (meeting_notes.ROOM). */
export const ROOM = "room";
/** A segment's length when few tracks are recorded; more tracks get longer segments so the posts stay under the server's 30 a minute. */
export const SLICE_MS = 20_000;
export const MAX_SLICE_MS = 55_000;
export const POSTS_PER_MINUTE = 24;
/** A segment shorter than this is not posted (too short to carry words; it would only use the rate). */
export const MIN_CHUNK_MS = 1_000;
const BITS_PER_SECOND = 32_000;

/** The segment length for `tracks` tracks recorded at once: 20 s up to 8 tracks, then longer (never over 55 s). Pure. */
export function sliceFor(tracks: number): number {
  const n = Math.max(1, tracks);
  return Math.min(MAX_SLICE_MS, Math.max(SLICE_MS, Math.ceil((n * 60) / POSTS_PER_MINUTE) * 1000));
}

/** The speaker of a LiveKit participant: "room" for a room screen, the login when it is admitted to the meeting, "room" for my own
 *  login on another device (the coordinator is in the room), else null (never recorded). Pure. */
export function speakerFor(identity: string, me: string, admitted: Set<string>): string | null {
  if (!identity) return null;
  if (isRoomScreen(identity)) return ROOM;
  const login = identityUser(identity);
  if (admitted.has(login)) return login;
  if (me && login === me) return ROOM;
  return null;
}

/** One track the recorder should capture now. */
export interface WantedTrack { key: string; track: MediaStreamTrack; speaker: string; label: string }

/** The tracks of the video call to capture now, and the people left out (not admitted). */
export function callTracks(room: Room, o: { me: string; admitted: Set<string>; names: Map<string, string>; localOn: boolean }): { tracks: WantedTrack[]; skipped: string[] } {
  const tracks: WantedTrack[] = [];
  const skipped: string[] = [];
  const live = (t: MediaStreamTrack | undefined): t is MediaStreamTrack => !!t && t.readyState === "live";
  const mine = room.localParticipant?.getTrackPublication(Track.Source.Microphone);
  const own = mine?.track?.mediaStreamTrack;
  if (o.localOn && mine && !mine.isMuted && live(own)) tracks.push({ key: `${ROOM}:${own.id}`, track: own, speaker: ROOM, label: "Board room microphone" });
  for (const p of room.remoteParticipants.values()) {
    const pub = p.getTrackPublication(Track.Source.Microphone);
    const mst = pub?.track?.mediaStreamTrack;
    if (!pub || pub.isMuted || !live(mst)) continue;
    const speaker = speakerFor(p.identity, o.me, o.admitted);
    if (!speaker) { skipped.push(p.name || identityUser(p.identity)); continue; }
    const label = speaker === ROOM ? "Board room (room screen)" : o.names.get(speaker) || p.name || speaker;
    tracks.push({ key: `${speaker}:${mst.id}`, track: mst, speaker, label });
  }
  return { tracks, skipped };
}

/** One finished segment of one track, in memory until it is posted. */
export interface Chunk { blob: Blob; fileName: string; speaker: string; startedMs: number; ms: number; retried?: boolean }

/** The recording format (WebM Opus where the browser has it), "" to let the browser choose, null when it cannot record. */
export function recorderMime(): string | null {
  return pickMimeType();
}

/** One running segment: its recorder, the promise of its emitted chunk, and the guard for a recorder that never stops. */
interface Segment { rec: MediaRecorder; done: Promise<void>; guard: () => unknown }

/** Records one audio track in whole segments; each finished segment goes to `emit` and is not kept here. */
export class TrackRecorder {
  private stream: MediaStream;
  private current: Segment | null = null;
  private timer = 0;
  private ended = false;
  sliceMs: number;

  constructor(readonly key: string, readonly track: MediaStreamTrack, readonly speaker: string, readonly label: string, private readonly mime: string,
    private readonly emit: (c: Chunk) => void, private readonly onError: (message: string) => void, sliceMs = SLICE_MS) {
    this.stream = new MediaStream([track]);
    this.sliceMs = sliceMs;
  }

  start(): void { this.begin(); }

  private begin(): void {
    if (this.ended || this.track.readyState !== "live") return;
    let rec: MediaRecorder;
    try { rec = new MediaRecorder(this.stream, this.mime ? { mimeType: this.mime, audioBitsPerSecond: BITS_PER_SECOND } : { audioBitsPerSecond: BITS_PER_SECOND }); }
    catch { this.onError("This browser cannot record the meeting's sound."); return; }
    const startedMs = Date.now();
    let parts: Blob[] = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) parts.push(e.data); };
    let guard = () => undefined as unknown;
    const done = new Promise<void>((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        const type = rec.mimeType || this.mime || "audio/webm";
        const ms = Date.now() - startedMs;
        const blob = new Blob(parts, { type });
        parts = [];
        if (blob.size > 0 && ms >= MIN_CHUNK_MS) this.emit({ blob, fileName: fileNameFor(type), speaker: this.speaker, startedMs, ms });
        resolve();
      };
      rec.addEventListener("stop", finish, { once: true });
      rec.addEventListener("error", finish, { once: true });
      guard = () => window.setTimeout(finish, 3000);  // a recorder that never says it stopped
    });
    try { rec.start(); } catch { this.onError("The recording could not start on this track."); return; }
    this.current = { rec, done, guard };
    this.timer = window.setTimeout(() => { void this.rotate(); }, this.sliceMs);
  }

  private end(cur: Segment | null): Promise<void> {
    if (!cur) return Promise.resolve();
    try { if (cur.rec.state !== "inactive") cur.rec.stop(); } catch { /* already stopped */ }
    cur.guard();
    return cur.done;
  }

  /** Ends the running segment (it is emitted) and starts the next one at once. Resolves when the ended segment was emitted. */
  rotate(): Promise<void> {
    window.clearTimeout(this.timer);
    const cur = this.current;
    this.current = null;
    const done = this.end(cur);
    this.begin();
    return done;
  }

  /** Stops for good; resolves when the last segment was emitted. */
  stop(): Promise<void> {
    this.ended = true;
    window.clearTimeout(this.timer);
    const cur = this.current;
    this.current = null;
    return this.end(cur);
  }

  get running(): boolean { return !this.ended && !!this.current; }
}

/** The plain words of a chunk that failed (the server's message when it gave one). */
export function chunkError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return "No connection to the server.";
    if (e.code === "voice_unavailable" || e.status === 503) return "The speech service is not available.";
    if (e.status === 429) return "Too many recording parts at once.";
    return e.message;
  }
  return "The part could not be sent.";
}

/** A failure worth one more try a moment later (the network, the rate, the speech service). A refusal because the recorder is not on
 *  (paused or stopped meanwhile) is not. */
export function retryable(e: unknown): boolean {
  if (!(e instanceof ApiError)) return true;
  return e.status === 0 || e.status === 429 || e.status === 502 || e.status === 503 || e.status === 504;
}

/** True when the server refused because the recorder is no longer on (a pause or a stop came first): not an error to show. */
export function recorderOff(e: unknown): boolean {
  return e instanceof ApiError && e.status === 409 && (e.code === "not_recording" || e.code === "not_in_session");
}

export interface QueueResult { ok: boolean; stored?: boolean; error?: string; quiet?: boolean }

/** Posts the chunks, a few at a time, each tried at most twice; each Blob is dropped once its post settles. */
export class UploadQueue {
  private q: Chunk[] = [];
  private active = 0;
  private waiters: Array<() => void> = [];

  constructor(private readonly send: (c: Chunk) => Promise<{ stored: boolean }>, private readonly onResult: (r: QueueResult) => void,
    private readonly concurrency = 3, private readonly retryMs = 3000) {}

  push(c: Chunk): void { this.q.push(c); this.pump(); }

  get size(): number { return this.q.length + this.active; }

  private pump(): void {
    while (this.active < this.concurrency && this.q.length) {
      const c = this.q.shift()!;
      this.active += 1;
      void this.run(c).finally(() => {
        this.active -= 1;
        this.pump();
        if (this.size === 0) { const w = this.waiters; this.waiters = []; w.forEach((f) => f()); }
      });
    }
  }

  private async run(c: Chunk): Promise<void> {
    try {
      const r = await this.send(c);
      this.onResult({ ok: true, stored: !!r.stored });
    } catch (e) {
      if (!c.retried && retryable(e)) {
        c.retried = true;
        await new Promise((res) => window.setTimeout(res, this.retryMs));
        await this.run(c);
        return;
      }
      this.onResult(recorderOff(e) ? { ok: false, quiet: true } : { ok: false, error: chunkError(e) });
    } finally {
      (c as { blob: Blob | null }).blob = null;  // the audio is let go as soon as its post settles
    }
  }

  /** Resolves true when every chunk was posted, false after `ms`. */
  drain(ms = 15_000): Promise<boolean> {
    if (this.size === 0) return Promise.resolve(true);
    return new Promise((resolve) => {
      const t = window.setTimeout(() => { this.waiters = this.waiters.filter((f) => f !== done); resolve(false); }, ms);
      const done = () => { window.clearTimeout(t); resolve(true); };
      this.waiters.push(done);
    });
  }

  /** Drops the chunks not yet sent (the page is going away). */
  clear(): void { this.q = []; }
}
