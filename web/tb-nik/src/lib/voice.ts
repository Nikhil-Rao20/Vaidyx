// Voice for the new interface (night-v3 Phase 4, docs/night-v3/research/08_voice.md section 6): the recorder behind the
// microphone button, the player queue behind the speaker button, the plain-words error table, the sentence splitter (the same
// rule as the server's), the text insertion at the cursor, the per-person agent-voice setting and the dictation guard.
// Audio never leaves memory: the recording is held as in-memory chunks until it is sent once, the spoken sentences live as
// blob: URLs that are revoked after use, and nothing is written to storage or offered for download.
import { api, ApiError } from "@/lib/api";
import { EP } from "@/lib/endpoints";

// ---------------------------------------------------------------------------------------------------------------- status

export type ServiceState = "ready" | "loading" | "down" | "off";
export interface AudioLimits { stt_seconds: number; stt_bytes: number; tts_chars: number }
export interface AudioStatus {
  enabled: boolean;
  stt: ServiceState;
  tts: ServiceState;
  limits: AudioLimits;
  cohere?: boolean;
  voices?: string[];
}
export const DEFAULT_LIMITS: AudioLimits = { stt_seconds: 60, stt_bytes: 4_194_304, tts_chars: 2000 };
/** What the page assumes when the app has no voice at all (no route, an error): draw nothing. */
export const AUDIO_OFF: AudioStatus = { enabled: false, stt: "off", tts: "off", limits: DEFAULT_LIMITS, cohere: false, voices: [] };

export const getAudioStatus = (signal?: AbortSignal) => api.get<AudioStatus>(EP.audioStatus, { signal });

// ----------------------------------------------------------------------------------------------------------------- words

/** Every sentence the voice controls show (no em dashes; nothing names a model). */
export const VOICE_TEXT = {
  dictate: "Dictate",
  asking: "Allow the microphone",
  listening: "Listening",
  transcribing: "Transcribing",
  added: "Added, check it",
  heard: "Heard this. Check it before you send.",
  readAloud: "Read aloud",
  stopReading: "Stop reading",
  preparing: "Preparing the voice",
  reading: "Reading aloud",
  ttsError: "Voice unavailable, text only",
  allowVoices: "Tap to allow agent voices",
  sttDown: "Voice is not running on this server. You can type instead.",
  sttLoading: "Voice is starting. Try again in a moment.",
  ttsDown: "Voice is not running. The text is on screen.",
  blocked: "The microphone is blocked. Allow the microphone for this site in the address bar, then try again.",
  noMic: "No microphone found. Plug one in or choose one in your system settings.",
  inUse: "The microphone is in use or not working. Close other apps that use it and try again.",
  noStart: "The microphone could not start. Try again.",
  insecure: "The microphone needs a secure connection. Open Vaidyx through localhost or https.",
  noRecorder: "This browser cannot record sound. You can type instead.",
  silent: "No sound heard. Check that the right microphone is selected.",
  noSpeech: "No speech heard. Try again closer to the microphone.",
  tooLong: "That was longer than one minute. Record in shorter parts.",
  unsupported: "This recording format could not be read. You can type instead.",
  busy: "Too many voice requests. Wait a minute, or type.",
  unavailable: "Voice is not available right now. You can type instead.",
  leftPage: "Recording stopped because you left the page.",
} as const;

export type VoiceCode = "insecure" | "no_recorder" | "silent" | "no_speech" | "too_long" | "left_page" | "track_ended" | "playback";

/** An error raised by this module itself (not by the browser or the server). */
export class VoiceError extends Error {
  code: VoiceCode;
  constructor(code: VoiceCode, message: string = code) {
    super(message);
    this.name = "VoiceError";
    this.code = code;
  }
}

/** The plain-words line for any error of the microphone, the recorder or the voice routes (research 08 section 6.1). */
export function messageFor(err: unknown): string {
  if (err instanceof VoiceError) {
    switch (err.code) {
      case "insecure": return VOICE_TEXT.insecure;
      case "no_recorder": return VOICE_TEXT.noRecorder;
      case "silent": return VOICE_TEXT.silent;
      case "no_speech": return VOICE_TEXT.noSpeech;
      case "too_long": return VOICE_TEXT.tooLong;
      case "left_page": return VOICE_TEXT.leftPage;
      case "track_ended": return VOICE_TEXT.inUse;
      case "playback": return VOICE_TEXT.unavailable;
    }
  }
  if (err instanceof ApiError) {
    const code = err.code;
    if (code === "no_speech") return VOICE_TEXT.noSpeech;
    if (code === "too_long" || err.status === 413) return VOICE_TEXT.tooLong;
    if (code === "unsupported_audio" || err.status === 415) return VOICE_TEXT.unsupported;
    if (code === "busy" || code === "rate_limited" || err.status === 429) return VOICE_TEXT.busy;
    return VOICE_TEXT.unavailable; // voice_unavailable (503), voice_failed (502), network (0) and anything else from the server
  }
  const name = err && typeof err === "object" && "name" in err ? String((err as { name: unknown }).name) : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError": return VOICE_TEXT.blocked;
    case "NotFoundError": return VOICE_TEXT.noMic;
    case "NotReadableError": return VOICE_TEXT.inUse;
    case "TypeError": return VOICE_TEXT.insecure; // getUserMedia outside https or localhost
    default: return VOICE_TEXT.noStart; // OverconstrainedError, AbortError, anything else
  }
}

// ------------------------------------------------------------------------------------------------------------- sentences

const ABBREVIATIONS = new Set(["dr", "mr", "mrs", "no", "reg", "e.g", "i.e", "vs"]);
// A mark, at most one closing quote or bracket, one space, then an upper-case letter, a digit, a quote or an opening bracket.
const BREAK = /([.?!])(["'\u201d\u2019)\]]?) (?=[A-Z0-9"'\u201c\u2018([])/g;
const OPENERS = /^[("'[\u201c\u2018]+/;
const LINE_BREAKS = /\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/;
const LONG = 400;
const CUT_FROM = 300;
const CUT_UNTIL = 1000;
const HARD = 400;

/** A piece over 400 characters: cut at the first ", " or "; " between characters 300 and 1000 (the mark stays with the first
 *  part); with none there, at the first space between 300 and 1000; with none, at character 400. Repeated on the rest. */
function cutLong(piece: string): string[] {
  const out: string[] = [];
  let s = piece;
  while (s.length > LONG) {
    const hits = [s.indexOf(", ", CUT_FROM), s.indexOf("; ", CUT_FROM)].filter((j) => j >= 0 && j <= CUT_UNTIL);
    let i: number;
    if (hits.length) i = Math.min(...hits) + 1;
    else {
      const sp = s.indexOf(" ", CUT_FROM);
      i = sp >= 0 && sp <= CUT_UNTIL ? sp : HARD;
    }
    const head = s.slice(0, i).trim();
    s = s.slice(i).trim();
    if (head) out.push(head);
  }
  if (s) out.push(s);
  return out;
}

/**
 * The sentences a statement is read in: the same fixed rule as the server's (tumour_board/audio_proxy.py split_sentences).
 * 1. Every line is its own piece; spaces inside a line are collapsed; empty lines are dropped.
 * 2. A line is cut after ".", "?" or "!" (and one closing quote or bracket right after it) followed by one space and then an
 *    upper-case letter, a digit, a quote or an opening bracket.
 * 3. Never after "Dr.", "Mr.", "Mrs.", "No.", "Reg.", "e.g.", "i.e.", "vs." (any case, an opening bracket or quote before ignored).
 * 4. Never inside a decimal number ("5.2 cm" has no space after the point).
 * 5. A piece over 400 characters is cut as cutLong says.
 */
export function splitSentences(text: string): string[] {
  const out: string[] = [];
  for (const raw of String(text ?? "").split(LINE_BREAKS)) {
    const line = raw.split(/\s+/).filter(Boolean).join(" ");
    if (!line) continue;
    let start = 0;
    for (const m of line.matchAll(BREAK)) {
      const at = m.index ?? 0;
      if (m[1] === "." && !m[2]) {
        const before = line.slice(start, at).split(" ").filter(Boolean);
        const word = before.length ? before[before.length - 1].replace(OPENERS, "").toLowerCase() : "";
        if (ABBREVIATIONS.has(word)) continue;
      }
      const end = at + m[0].length;
      const piece = line.slice(start, end).trim();
      if (piece) out.push(...cutLong(piece));
      start = end;
    }
    const rest = line.slice(start).trim();
    if (rest) out.push(...cutLong(rest));
  }
  return out;
}

// ------------------------------------------------------------------------------------------------------------- insertion

const NO_SPACE_BEFORE = /^[,.;:!?)\]}]/;
/** The selection as a valid range of a value of length `len` (missing means the end; reversed means swapped). */
function clampRange(len: number, selStart: number | null, selEnd: number | null): [number, number] {
  const clamp = (n: number | null, d: number) => (n === null || !Number.isFinite(n) ? d : Math.max(0, Math.min(len, Math.floor(n))));
  const s = clamp(selStart, len);
  const e = clamp(selEnd, s);
  return e < s ? [e, s] : [s, e];
}
const NO_SPACE_AFTER = /[\s([{"'“‘/-]$/;

/**
 * Put dictated text into a box's value at the remembered selection (a selected range is replaced), with one space added where
 * needed on either side and the capital letters left as they are. Returns the new value and the range of the inserted words
 * (the cursor goes to `end`).
 */
export function insertAtSelection(value: string, selStart: number | null, selEnd: number | null, text: string): { next: string; start: number; end: number } {
  const v = value ?? "";
  const [s, e] = clampRange(v.length, selStart, selEnd);
  const words = (text ?? "").replace(/\s+/g, " ").trim();
  if (!words) return { next: v, start: s, end: s };
  const before = v.slice(0, s);
  const after = v.slice(e);
  const lead = before && !NO_SPACE_AFTER.test(before) && !NO_SPACE_BEFORE.test(words) ? " " : "";
  const trail = after && !/^\s/.test(after) && !NO_SPACE_BEFORE.test(after) ? " " : "";
  const next = before + lead + words + trail + after;
  const start = before.length + lead.length;
  return { next, start, end: start + words.length };
}

/**
 * Write a new value into a React-controlled textarea or input so its onChange runs as if typed: the browser's own insertText
 * first (the edit joins the undo history), else the native value setter and an "input" event (the usual trick for controlled
 * boxes). Then the inserted words are selected for a moment and the cursor placed after them.
 */
export function writeIntoBox(el: HTMLTextAreaElement | HTMLInputElement, selStart: number | null, selEnd: number | null, text: string): { next: string; inserted: string } | null {
  const old = el.value;
  const { next, start, end } = insertAtSelection(old, selStart, selEnd, text);
  if (next === old) return null;
  const inserted = next.slice(start, end);
  const [s, e] = clampRange(old.length, selStart, selEnd);
  const piece = next.slice(s, next.length - (old.length - e)); // the words with the spaces added around them
  el.focus({ preventScroll: true });
  let done = false;
  try {
    el.setSelectionRange(s, e);
    done = typeof document.execCommand === "function" && document.execCommand("insertText", false, piece);
  } catch { done = false; }
  if (!done) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(el, next); else el.value = next;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  if (el.value === next) {
    try {
      el.setSelectionRange(start, end);
      window.setTimeout(() => { try { if (document.activeElement === el && el.value === next) el.setSelectionRange(end, end); } catch { /* not a text box */ } }, 900);
    } catch { /* an input type without a selection */ }
  }
  return { next: el.value, inserted };
}

// -------------------------------------------------------------------------------------------------------------- recorder

const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
const AUDIO_BITS_PER_SECOND = 32000;

/** The first recording format this browser supports, "" to let the browser choose, null when it cannot record at all. */
export function pickMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  for (const t of MIME_TYPES) {
    try { if (MediaRecorder.isTypeSupported(t)) return t; } catch { /* old browser */ }
  }
  return "";
}

export function fileNameFor(mime: string): string {
  if (mime.includes("mp4")) return "clip.mp4";
  if (mime.includes("ogg")) return "clip.ogg";
  return "clip.webm";
}

export interface Recording {
  track: MediaStreamTrack;
  mimeType: string;
  /** True only while the recorder records and the microphone track is live. */
  isLive(): boolean;
  /** Stops recording, turns the microphone off and gives the recording (held in memory only). */
  stop(): Promise<Blob>;
  /** Stops recording, turns the microphone off and drops what was recorded. */
  cancel(): void;
}

/** Opens the microphone and starts recording. Throws the browser's own error (NotAllowedError, ...) or a VoiceError. */
export async function startRecording(opts: { onLevel?: (level: number) => void; onEnded?: () => void } = {}): Promise<Recording> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) throw new VoiceError("insecure");
  const mime = pickMimeType();
  if (mime === null) throw new VoiceError("no_recorder");
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  const stopTracks = () => stream.getTracks().forEach((t) => { try { t.stop(); } catch { /* already stopped */ } });
  const track = stream.getAudioTracks()[0];
  if (!track) { stopTracks(); throw new DOMException("No microphone track", "NotFoundError"); }
  let rec: MediaRecorder;
  // 32 kbit/s keeps a one-minute clip near 240 KB, far under the 4 MiB cap, and plenty for speech.
  try { rec = new MediaRecorder(stream, mime ? { mimeType: mime, audioBitsPerSecond: AUDIO_BITS_PER_SECOND } : { audioBitsPerSecond: AUDIO_BITS_PER_SECOND }); }
  catch { stopTracks(); throw new VoiceError("no_recorder"); }
  let chunks: Blob[] = [];
  rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };

  let ctx: AudioContext | null = null;
  let timer = 0;
  if (opts.onLevel) {
    const onLevel = opts.onLevel;
    try {
      ctx = new AudioContext();
      void ctx.resume().catch(() => undefined);
      const an = ctx.createAnalyser(); an.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.frequencyBinCount);
      timer = window.setInterval(() => {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) { const d = (v - 128) / 128; sum += d * d; }
        onLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4));
      }, 80);
    } catch { /* no audio context: no meter */ }
  }

  let finished = false;
  const cleanup = () => {
    if (finished) return;
    finished = true;
    window.clearInterval(timer);
    if (ctx) void ctx.close().catch(() => undefined);
    stopTracks();
  };
  track.addEventListener("ended", () => { if (!finished) opts.onEnded?.(); });

  try { rec.start(); } catch (e) { cleanup(); throw e; }
  if (rec.state !== "recording") { cleanup(); throw new DOMException("The recorder did not start", "AbortError"); }

  return {
    track,
    mimeType: rec.mimeType || mime || "audio/webm",
    isLive: () => !finished && rec.state === "recording" && track.readyState === "live",
    stop: () => new Promise<Blob>((resolve) => {
      const type = rec.mimeType || mime || "audio/webm";
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        cleanup();
        const blob = new Blob(chunks, { type });
        chunks = [];
        resolve(blob);
      };
      if (rec.state === "inactive") { finish(); return; }
      rec.addEventListener("stop", finish, { once: true });
      window.setTimeout(finish, 2000); // a recorder that never says it stopped
      try { rec.stop(); } catch { finish(); }
    }),
    cancel: () => {
      rec.ondataavailable = null;
      try { if (rec.state !== "inactive") rec.stop(); } catch { /* already stopped */ }
      chunks = [];
      cleanup();
    },
  };
}

export type SttContext = "question" | "decision" | "note" | "reason";
export interface SttResult {
  text: string;
  segments: { start: number; end: number; text: string }[];
  duration: number;
  engine: string;
  took_ms: number;
  code: null | "no_speech";
}

/** Sends one recording to be turned into text (multipart, the custom header through api()). */
export function transcribe(blob: Blob, o: { screen: string; caseId?: string; context?: SttContext; signal?: AbortSignal }): Promise<SttResult> {
  const form = new FormData();
  form.append("audio", blob, fileNameFor(blob.type));
  form.append("screen", o.screen);
  if (o.caseId) form.append("case_id", o.caseId);
  if (o.context) form.append("context", o.context);
  return api.upload<SttResult>(EP.audioStt, form, { signal: o.signal });
}

// --------------------------------------------------------------------------------------------------------- dictation guard

export interface DictationGuard { mute: () => Promise<void> | void; restore: () => Promise<void> | void }
let guard: DictationGuard | null = null;

/** The meeting registers its call microphone here, so dictation is not heard by the room (owner decision 3). */
export function registerDictationGuard(g: DictationGuard | null): void { guard = g; }
export async function muteForDictation(): Promise<void> { try { await guard?.mute(); } catch { /* the call carries on */ } }
export async function restoreAfterDictation(): Promise<void> { try { await guard?.restore(); } catch { /* the call carries on */ } }

// --------------------------------------------------------------------------------------------------------------- speaker

export interface TtsRef { kind: string; case_id?: string; id: string; index?: number; meeting_id?: string; role?: string }
export type TtsBody = { ref: TtsRef; part: number; voice?: string } | { text: string; screen: string; voice?: string };
export type SpeakSource = { ref: TtsRef } | { text: string };

function codeOf(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const d = data as Record<string, unknown>;
  if (typeof d.code === "string") return d.code;
  const inner = d.detail;
  if (inner && typeof inner === "object" && typeof (inner as Record<string, unknown>).code === "string") return String((inner as Record<string, unknown>).code);
  return "";
}

/** One sentence of speech as a WAV blob, with the same header and cookies as api() (the server refuses a POST without it). */
export async function fetchAudio(body: TtsBody, signal?: AbortSignal): Promise<{ blob: Blob; parts: number; part: number }> {
  let res: Response;
  try {
    res = await fetch(EP.audioTts, {
      method: "POST",
      headers: { "X-Requested-With": "tb-nik", "Content-Type": "application/json", Accept: "audio/wav, application/json" },
      body: JSON.stringify(body),
      credentials: "same-origin",
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, VOICE_TEXT.unavailable, "network");
  }
  if (!res.ok) {
    let data: unknown = null;
    try { data = await res.json(); } catch { /* not JSON */ }
    throw new ApiError(res.status, VOICE_TEXT.ttsError, codeOf(data), data);
  }
  const blob = await res.blob();
  const parts = Number.parseInt(res.headers.get("X-Parts") ?? "", 10);
  const part = Number.parseInt(res.headers.get("X-Part") ?? "", 10);
  return { blob, parts: Number.isFinite(parts) && parts > 0 ? parts : 1, part: Number.isFinite(part) ? part : "part" in body ? body.part : 0 };
}

let audioEl: HTMLAudioElement | null = null;
let primed = false;

/** The one audio element the whole page plays through (created on first use). */
function audioElement(): HTMLAudioElement | null {
  if (typeof document === "undefined") return null;
  if (!audioEl) {
    audioEl = document.createElement("audio");
    audioEl.preload = "auto";
    audioEl.setAttribute("playsinline", "");
    (audioEl as HTMLAudioElement & { playsInline?: boolean }).playsInline = true;
  }
  return audioEl;
}

/** A silent WAV of 0.1 s built in code (a data: URL would not play under the page's media policy, so it goes as a blob:). */
function silentWav(seconds = 0.1, rate = 8000): Blob {
  const n = Math.round(seconds * rate);
  const buf = new ArrayBuffer(44 + n * 2);
  const v = new DataView(buf);
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, n * 2, true);
  return new Blob([buf], { type: "audio/wav" });
}

/** Call inside a click: plays a short silence so a later play() of fetched speech is allowed by the browser. */
export function primeAudio(): void {
  const el = audioElement();
  if (!el || (current && !el.paused)) return; // already playing speech: nothing to unlock
  const url = URL.createObjectURL(silentWav());
  el.src = url;
  el.play().then(() => { primed = true; }, () => undefined).finally(() => URL.revokeObjectURL(url));
}

export function audioPrimed(): boolean { return primed; }

/** What the browser says about playing sound without a click ("unknown" where it cannot say). */
export function autoplayPolicy(): "allowed" | "allowed-muted" | "disallowed" | "unknown" {
  try {
    const nav = navigator as Navigator & { getAutoplayPolicy?: (type: string) => string };
    const p = nav.getAutoplayPolicy?.("mediaelement");
    return p === "allowed" || p === "allowed-muted" || p === "disallowed" ? p : "unknown";
  } catch { return "unknown"; }
}

export interface SpeakHandlers {
  /** The first sentence has started playing. */
  onSpeaking?: () => void;
  /** Sentence `index` of `total` has started. */
  onPart?: (index: number, total: number) => void;
  /** Every sentence was read. */
  onEnd?: () => void;
  /** Stopped by a person, by another speaker or by stopSpeaking(). */
  onStop?: () => void;
  /** The voice failed (a NotAllowedError from play() means the page needs a tap first). */
  onError?: (err: unknown) => void;
}
export interface SpeakHandle { stop: () => void }

class Session implements SpeakHandle {
  private ac = new AbortController();
  private stopped = false;
  private urls = new Set<string>();
  private playingUrl: string | null = null;
  private settle: (() => void) | null = null;
  private source: SpeakSource;
  private opts: { screen: string; voice?: string };
  private h: SpeakHandlers;

  constructor(source: SpeakSource, opts: { screen: string; voice?: string }, h: SpeakHandlers) {
    this.source = source;
    this.opts = opts;
    this.h = h;
  }

  start() {
    this.run().then(
      () => { if (!this.stopped) { this.release(); this.h.onEnd?.(); } },
      (e) => { if (!this.stopped) { this.release(); this.h.onError?.(e); } },
    );
  }

  stop() {
    if (this.stopped) return;
    this.stopped = true;
    this.release();
    this.h.onStop?.();
  }

  private release() {
    this.ac.abort();
    const settle = this.settle;
    this.settle = null;
    settle?.();
    const el = audioEl;
    if (el && this.playingUrl && el.src === this.playingUrl) {
      el.pause();
      el.removeAttribute("src");
      el.load();
    }
    this.playingUrl = null;
    for (const u of this.urls) URL.revokeObjectURL(u);
    this.urls.clear();
    if (current === this) current = null;
  }

  private body(i: number, texts: string[] | null): TtsBody {
    const voice = this.opts.voice ? { voice: this.opts.voice } : {};
    if (texts) return { text: texts[i], screen: this.opts.screen, ...voice };
    return { ref: (this.source as { ref: TtsRef }).ref, part: i, ...voice };
  }

  private fetchPart(i: number, texts: string[] | null) {
    const p = fetchAudio(this.body(i, texts), this.ac.signal);
    p.catch(() => undefined); // a prefetch dropped by a stop is not an unhandled rejection
    return p;
  }

  private playUrl(el: HTMLAudioElement, url: string): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      let settled = false;
      const done = (err?: unknown) => {
        if (settled) return;
        settled = true;
        el.removeEventListener("ended", onEnded);
        el.removeEventListener("error", onError);
        if (this.settle === settleNow) this.settle = null;
        if (err) reject(err); else resolve();
      };
      const onEnded = () => done();
      const onError = () => done(new VoiceError("playback"));
      const settleNow = () => done();
      this.settle = settleNow;
      el.addEventListener("ended", onEnded);
      el.addEventListener("error", onError);
      el.src = url;
      this.playingUrl = url;
      el.play().catch((e) => done(e));
    });
  }

  private async run() {
    const el = audioElement();
    if (!el) throw new VoiceError("playback");
    const texts = "text" in this.source ? splitSentences(this.source.text) : null;
    if (texts && texts.length === 0) return;
    let total: number | null = texts ? texts.length : null;
    let next = this.fetchPart(0, texts);
    for (let i = 0; total === null || i < total; i++) {
      const got = await next;
      if (this.stopped) return;
      if (total === null) total = got.parts;
      if (i + 1 < total) next = this.fetchPart(i + 1, texts);
      const url = URL.createObjectURL(got.blob);
      this.urls.add(url);
      if (i === 0) this.h.onSpeaking?.();
      this.h.onPart?.(i, total);
      try { await this.playUrl(el, url); }
      finally { URL.revokeObjectURL(url); this.urls.delete(url); }
      if (this.stopped) return;
    }
  }
}

let current: Session | null = null;

/** Reads a statement aloud, sentence by sentence (the next one fetched while the current one plays). One voice at a time. */
export function speak(source: SpeakSource, opts: { screen: string; voice?: string }, handlers: SpeakHandlers = {}): SpeakHandle {
  stopSpeaking();
  const s = new Session(source, opts, handlers);
  current = s;
  s.start();
  return s;
}

/** Stops whatever is being read aloud on this page. */
export function stopSpeaking(): void {
  const s = current;
  current = null;
  s?.stop();
}

export function isSpeaking(): boolean { return current !== null; }

// ---------------------------------------------------------------------------------------------------------- agent voices

const AGENT_VOICE_KEY = "vx.agentVoice";
const AGENT_VOICE_EVENT = "vx-agent-voice";

let agentVoiceHere: boolean | null = null;

/** Whether this person hears the specialty agents aloud (a per-viewer choice kept in this browser; on by default). */
export function agentVoiceEnabled(): boolean {
  try {
    const v = localStorage.getItem(AGENT_VOICE_KEY);
    return v === null ? agentVoiceHere ?? true : v !== "0";
  } catch { return agentVoiceHere ?? true; }
}

export function setAgentVoice(on: boolean): void {
  agentVoiceHere = on;
  try { localStorage.setItem(AGENT_VOICE_KEY, on ? "1" : "0"); } catch { /* no storage: the choice lasts this page only */ }
  try { window.dispatchEvent(new CustomEvent<boolean>(AGENT_VOICE_EVENT, { detail: on })); } catch { /* no window */ }
}

/** Runs `fn` when the agent-voice setting changes on this page; returns the unsubscribe. */
export function onAgentVoiceChange(fn: (on: boolean) => void): () => void {
  const h = (e: Event) => fn(Boolean((e as CustomEvent<boolean>).detail));
  window.addEventListener(AGENT_VOICE_EVENT, h);
  return () => window.removeEventListener(AGENT_VOICE_EVENT, h);
}

/** The agent-voice choice this person made (kept in this browser), or null when they never chose (night-v3 6.1: the call then
 *  decides by where they are; a member in the room starts muted, the room screen plays). */
export function agentVoiceChoice(): boolean | null {
  try {
    const v = localStorage.getItem(AGENT_VOICE_KEY);
    return v === null ? agentVoiceHere : v !== "0";
  } catch { return agentVoiceHere; }
}
