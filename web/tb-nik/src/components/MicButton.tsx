// The dictation button (night-v3 item 4.3, research 08 section 6.1): tap to talk, tap again to stop; the words heard go into the
// box at the cursor as a normal, editable edit and are never sent by themselves. Every state is true (driven by the browser and
// the request) and shown with an icon and a word, never colour alone. Esc cancels; Ctrl+Alt+M toggles from the box it serves.
// The recording stays in memory and is sent once, then dropped; the microphone is turned off as soon as recording ends.
import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { AlertCircle, Check, Loader2, Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MicLevel } from "@/components/MicLevel";
import { useAudioStatus } from "@/hooks/useAudioStatus";
import { cn } from "@/lib/utils";
import {
  insertAtSelection, messageFor, muteForDictation, restoreAfterDictation, startRecording, stopSpeaking, transcribe, VOICE_TEXT,
  VoiceError, writeIntoBox, type Recording, type SttContext,
} from "@/lib/voice";

type Box = HTMLTextAreaElement | HTMLInputElement;
type MicState = "idle" | "asking" | "listening" | "transcribing" | "added" | "error";

type Common = {
  /** A short id of the screen for the audit line ("ask", "decision", "reason", ...). */
  screen: string;
  context?: SttContext;
  caseId?: string;
  size?: "icon-xs" | "icon-sm";
  /** The button's accessible name (default "Dictate"). */
  label?: string;
  className?: string;
  /** Show "Heard this. Check it before you send." for 6 s after the words go in (default true). */
  hint?: boolean;
  hintText?: string;
  /** Called after the words went in, with the box's new value and the words added. */
  onInsert?: (next: string, inserted: string) => void;
};
export type MicButtonProps = Common & (
  | { target: RefObject<Box>; value?: never; onChange?: never }
  | { value: string; onChange: (next: string) => void; target?: never }
);

interface Session {
  cancelled: boolean;
  rec: Recording | null;
  ac: AbortController | null;
  sel: [number | null, number | null];
  muting: Promise<void>;
  restored: boolean;
  startedAt: number;
  lastSound: number;
}

/** A level above this counts as sound (the meter's scale: 0 to 1). */
const SOUND = 0.05;
const SILENT_MS = 3000;

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function selectionOf(el: Box): [number | null, number | null] {
  try { return [el.selectionStart, el.selectionEnd]; } catch { return [null, null]; }
}

const TONE: Record<MicState, string> = {
  idle: "text-muted-foreground hover:bg-accent hover:text-foreground",
  asking: "text-primary hover:text-primary",
  listening: "bg-bad-soft text-bad hover:bg-bad-soft hover:text-bad",
  transcribing: "text-primary hover:text-primary",
  added: "bg-ok-soft text-ok hover:bg-ok-soft hover:text-ok",
  error: "text-warn hover:text-warn",
};
const PILL: Partial<Record<MicState, string>> = {
  asking: "bg-accent text-foreground",
  listening: "bg-bad-soft text-bad",
  transcribing: "bg-accent text-primary",
  added: "bg-ok-soft text-ok",
};

export function MicButton(props: MicButtonProps) {
  const { screen, context, caseId, size = "icon-sm", label = VOICE_TEXT.dictate, className, hint = true, hintText = VOICE_TEXT.heard } = props;
  const status = useAudioStatus();
  const reduce = useReducedMotion();
  const uid = useId();
  const [state, setState] = useState<MicState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showHint, setShowHint] = useState(false);
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const btnRef = useRef<HTMLButtonElement>(null);
  const sessRef = useRef<Session | null>(null);
  const timers = useRef<number[]>([]);

  const maxSeconds = status.limits.stt_seconds > 0 ? status.limits.stt_seconds : 60;
  const autoStopAt = Math.max(5, maxSeconds - 5);
  const countdownFrom = autoStopAt - 5;

  const later = (fn: () => void, ms: number) => { timers.current.push(window.setTimeout(fn, ms)); };
  const clearTimers = () => { timers.current.forEach((t) => window.clearTimeout(t)); timers.current = []; };

  const restoreOnce = async (sess: Session) => {
    if (sess.restored) return;
    sess.restored = true;
    await sess.muting;
    await restoreAfterDictation();
  };

  const reset = () => { setLevel(0); setNotice(null); setElapsed(0); };

  const fail = (sess: Session, err: unknown) => {
    if (sessRef.current !== sess) return;
    sessRef.current = null;
    reset();
    setError(messageFor(err));
    setState("error");
  };

  const insert = (text: string, sel: [number | null, number | null]) => {
    const p = live.current.props; // the latest value, not the one when recording began
    if (p.target) {
      const el = p.target.current;
      if (!el) return;
      const r = writeIntoBox(el, sel[0], sel[1], text);
      if (r) p.onInsert?.(r.next, r.inserted);
    } else if (p.onChange) {
      const v = p.value ?? "";
      const { next, start, end } = insertAtSelection(v, v.length, v.length, text);
      p.onChange(next);
      p.onInsert?.(next, next.slice(start, end));
    }
  };

  const begin = async () => {
    clearTimers();
    setError(null);
    setShowHint(false);
    reset();
    const el = props.target?.current ?? null;
    const sess: Session = {
      cancelled: false, rec: null, ac: null, sel: el ? selectionOf(el) : [null, null],
      muting: Promise.resolve(), restored: false, startedAt: 0, lastSound: 0,
    };
    sessRef.current = sess;
    setState("asking");
    stopSpeaking(); // a voice reading aloud would be heard by the microphone
    sess.muting = muteForDictation();
    await sess.muting;
    if (sess.cancelled) return;
    let rec: Recording;
    try {
      rec = await startRecording({
        onLevel: (l) => {
          if (sessRef.current !== sess) return;
          setLevel(l);
          if (l > SOUND) sess.lastSound = Date.now();
        },
        onEnded: () => {
          if (sessRef.current !== sess || !sess.rec) return;
          sess.rec.cancel();
          sess.rec = null;
          void restoreOnce(sess);
          fail(sess, new VoiceError("track_ended"));
        },
      });
    } catch (e) {
      await restoreOnce(sess);
      if (!sess.cancelled) fail(sess, e);
      return;
    }
    if (sess.cancelled || sessRef.current !== sess) { rec.cancel(); await restoreOnce(sess); return; }
    if (!rec.isLive()) { rec.cancel(); await restoreOnce(sess); fail(sess, new DOMException("The microphone did not start", "AbortError")); return; }
    sess.rec = rec;
    sess.startedAt = Date.now();
    sess.lastSound = Date.now();
    setState("listening");
  };

  const finish = async () => {
    const sess = sessRef.current;
    if (!sess || !sess.rec) return;
    const rec = sess.rec;
    sess.rec = null;
    reset();
    const blob = await rec.stop();
    void restoreOnce(sess);
    if (sess.cancelled || sessRef.current !== sess) return;
    if (blob.size === 0) { fail(sess, new VoiceError("no_speech")); return; }
    if (blob.size > status.limits.stt_bytes) { fail(sess, new VoiceError("too_long")); return; }
    const ac = new AbortController();
    sess.ac = ac;
    setState("transcribing");
    let text = "";
    try {
      const res = await transcribe(blob, { screen, caseId, context, signal: ac.signal });
      if (sess.cancelled || ac.signal.aborted || sessRef.current !== sess) return;
      if (res?.code === "no_speech" || !(res?.text ?? "").trim()) { fail(sess, new VoiceError("no_speech")); return; }
      text = res.text.trim();
    } catch (e) {
      if (sess.cancelled || ac.signal.aborted) return;
      fail(sess, e);
      return;
    }
    sessRef.current = null;
    insert(text, sess.sel);
    setState("added");
    later(() => setState((s) => (s === "added" ? "idle" : s)), 1000);
    if (hint) { setShowHint(true); later(() => setShowHint(false), 6000); }
  };

  /** Esc, leaving the page, unmounting: stop everything and drop the recording or ignore the reply. */
  const cancel = (message?: string) => {
    const sess = sessRef.current;
    if (!sess) return;
    sess.cancelled = true;
    sessRef.current = null;
    sess.rec?.cancel();
    sess.rec = null;
    sess.ac?.abort();
    void restoreOnce(sess);
    reset();
    setError(message ?? null);
    setState(message ? "error" : "idle");
  };

  /** The recording died while listening: drop it, give the call microphone back and say so in plain words. */
  const dead = (sess: Session) => {
    if (sessRef.current !== sess || !sess.rec) return;
    sess.rec.cancel();
    sess.rec = null;
    void restoreOnce(sess);
    fail(sess, new DOMException("The microphone stopped", "AbortError"));
  };

  const toggle = () => {
    if (status.stt !== "ready") return;
    if (state === "listening") void finish();
    else if (state === "asking" || state === "transcribing") return;
    else void begin();
  };

  // The listeners read the latest functions and state through this ref.
  const live = useRef({ state, toggle, cancel, finish, dead, props });
  useEffect(() => { live.current = { state, toggle, cancel, finish, dead, props }; });

  // The clock, the count-down, the auto stop and the "no sound" line while listening.
  useEffect(() => {
    if (state !== "listening") return;
    const t = window.setInterval(() => {
      const sess = sessRef.current;
      if (!sess?.rec) return;
      // The recorder stopped on its own (an error, the track gone) without the stop path: never show "Listening" over nothing.
      if (!sess.rec.isLive()) { live.current.dead(sess); return; }
      const secs = (Date.now() - sess.startedAt) / 1000;
      setElapsed(Math.floor(secs));
      if (secs >= autoStopAt) { void live.current.finish(); return; }
      setNotice(Date.now() - sess.lastSound > SILENT_MS ? VOICE_TEXT.silent : null);
    }, 250);
    return () => window.clearInterval(t);
  }, [state, autoStopAt]);

  // Esc cancels while asking, listening or transcribing (before a dialog around the box would close).
  useEffect(() => {
    if (state !== "asking" && state !== "listening" && state !== "transcribing") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      live.current.cancel();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [state]);

  // Leaving the page while recording stops and drops it (a locked phone would otherwise send half a clip).
  useEffect(() => {
    const onVis = () => {
      const s = live.current.state;
      if (document.visibilityState === "hidden" && (s === "asking" || s === "listening")) live.current.cancel(VOICE_TEXT.leftPage);
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  // Ctrl+Alt+M from this button's own box (or the button), so several buttons on a page never fire together.
  const target = props.target;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.ctrlKey || !e.altKey || e.shiftKey || e.metaKey) return;
      if (e.code !== "KeyM" && e.key.toLowerCase() !== "m") return;
      const active = document.activeElement;
      if (!active || (active !== target?.current && active !== btnRef.current)) return;
      e.preventDefault();
      live.current.toggle();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [target]);

  // Unmounting stops the microphone and ignores any reply.
  useEffect(() => () => { live.current.cancel(); timers.current.forEach((t) => window.clearTimeout(t)); }, []);

  if (!status.enabled || status.stt === "off") return null;

  const unavailable = status.stt !== "ready";
  const downText = status.stt === "loading" ? VOICE_TEXT.sttLoading : VOICE_TEXT.sttDown;
  const listening = state === "listening";
  const left = autoStopAt - elapsed;
  const countdown = listening && elapsed >= countdownFrom ? (left <= 1 ? "1 second left" : `${left} seconds left`) : null;
  const word =
    state === "asking" ? VOICE_TEXT.asking
      : listening ? `${VOICE_TEXT.listening} ${fmt(elapsed)} of ${fmt(maxSeconds)}`
        : state === "transcribing" ? VOICE_TEXT.transcribing
          : state === "added" ? VOICE_TEXT.added
            : null;
  const spoken = state === "asking" ? VOICE_TEXT.asking : listening ? VOICE_TEXT.listening : state === "transcribing" ? VOICE_TEXT.transcribing : state === "added" ? VOICE_TEXT.added : "";
  const shortcut = "Ctrl+Alt+M";
  const title = unavailable ? downText
    : listening ? `Stop and add the text (${shortcut}). Esc cancels.`
      : state === "transcribing" ? `${VOICE_TEXT.transcribing}. Esc cancels.`
        : state === "asking" ? `${VOICE_TEXT.asking}. Esc cancels.`
          : state === "error" ? `Try again (${shortcut})`
            : `${label} (${shortcut})`;
  const lineId = `${uid}-line`;
  const tap = size === "icon-xs" ? "min-h-11 min-w-11 sm:min-h-6 sm:min-w-6" : "min-h-11 min-w-11 sm:min-h-8 sm:min-w-8";
  const icon =
    listening ? <Square className="size-3.5 fill-current" aria-hidden />
      : state === "transcribing" ? <Loader2 className="animate-spin" aria-hidden />
        : state === "added" ? <Check aria-hidden />
          : state === "error" ? <AlertCircle aria-hidden />
            : <Mic aria-hidden />;
  const line = unavailable ? <p id={lineId} className="text-xs text-muted-foreground">{downText}</p>
    : error ? <p id={lineId} role="alert" className="text-xs font-medium text-warn">{error}</p>
      : null;

  return (
    <span className={cn("inline-flex max-w-full flex-col items-end gap-1 text-right", className)} data-state={state}>
      <span className="inline-flex items-center gap-1.5">
        <AnimatePresence initial={false} mode="popLayout">
          {word ? (
            <motion.span
              key={state}
              aria-hidden
              className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums whitespace-nowrap", PILL[state])}
              initial={reduce ? false : { opacity: 0, x: 4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduce ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              {listening ? <MicLevel level={level} onClassName="bg-bad" offClassName="bg-bad/25" /> : null}
              {word}
            </motion.span>
          ) : null}
        </AnimatePresence>
        <Button
          ref={btnRef}
          type="button"
          variant="ghost"
          size={size}
          onClick={toggle}
          aria-label={label}
          title={title}
          aria-pressed={listening}
          aria-busy={state === "transcribing" || undefined}
          aria-disabled={unavailable || undefined}
          aria-keyshortcuts="Control+Alt+M"
          aria-describedby={line ? lineId : undefined}
          className={cn("relative overflow-hidden", tap, TONE[state], unavailable && "cursor-not-allowed opacity-50 hover:bg-transparent")}
        >
          {listening && !reduce ? (
            <motion.span
              aria-hidden
              className="pointer-events-none absolute inset-0 rounded-md bg-bad/20"
              animate={{ opacity: [0.9, 0.1, 0.9] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            />
          ) : null}
          <span className="relative inline-flex">{icon}</span>
        </Button>
      </span>
      {line}
      {!unavailable && notice ? <p role="status" className="text-xs text-warn">{notice}</p> : null}
      {countdown ? <p className="text-xs font-medium text-bad" aria-live="polite">{countdown}</p> : null}
      {!unavailable && showHint && state !== "error" ? <p className="text-xs text-muted-foreground">{hintText}</p> : null}
      <span className="sr-only" aria-live="polite">{spoken}</span>
    </span>
  );
}
