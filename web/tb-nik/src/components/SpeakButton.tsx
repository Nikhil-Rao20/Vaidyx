// The read-aloud button (night-v3 item 4.3, research 08 section 6.2): reads a saved statement (a reference the server loads and
// checks) or text already on screen, one sentence at a time through the page's single audio element, and stops on a second tap.
// One voice at a time on the page. A failure never hides the text: the button says "Voice unavailable, text only". On-screen
// text over 1,000 characters is refused before any request (the server's cap is per text, and the text goes one sentence per
// request).
import { useEffect, useId, useRef, useState } from "react";
import { Loader2, Square, Volume2, VolumeX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAudioStatus } from "@/hooks/useAudioStatus";
import { cn } from "@/lib/utils";
import { audioPrimed, autoplayPolicy, primeAudio, speak, stopSpeaking, VOICE_TEXT, type SpeakHandle, type TtsRef } from "@/lib/voice";

type SpeakState = "idle" | "preparing" | "speaking" | "error";

export interface SpeakButtonProps {
  /** A saved statement the server loads ({ref}) or text already on the screen ({text}). */
  source: { ref: TtsRef } | { text: string };
  /** A short id of the screen for the audit line. */
  screen: string;
  /** The button's accessible name when idle (default "Read aloud"). */
  label?: string;
  size?: "icon-xs" | "icon-sm";
  className?: string;
  /** Start reading as soon as the button is drawn (talk mode); the caller decides, for example from agentVoiceEnabled(). */
  autoplay?: boolean;
  /** Reading is over: finished, stopped or failed. */
  onEnd?: () => void;
  voice?: string;
}

/** On-screen text the server reads aloud, at most (the same cap and words as the server's, for the whole text). */
const TEXT_MAX = 1000;
const TOO_LONG = "That text is too long to read aloud. Read it in shorter parts.";

const isNotAllowed = (e: unknown) => !!e && typeof e === "object" && "name" in e && (e as { name: unknown }).name === "NotAllowedError";

const TONE: Record<SpeakState, string> = {
  idle: "text-muted-foreground hover:bg-accent hover:text-foreground",
  preparing: "text-primary hover:text-primary",
  speaking: "bg-accent text-primary hover:bg-accent hover:text-primary",
  error: "text-warn hover:text-warn",
};

export function SpeakButton({ source, screen, label = VOICE_TEXT.readAloud, size = "icon-sm", className, autoplay, onEnd, voice }: SpeakButtonProps) {
  const status = useAudioStatus();
  const uid = useId();
  const [state, setState] = useState<SpeakState>("idle");
  const [blocked, setBlocked] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const handle = useRef<SpeakHandle | null>(null);
  const autoplayed = useRef(false);
  const live = useRef({ source, screen, voice, onEnd });
  useEffect(() => { live.current = { source, screen, voice, onEnd }; });

  const ended = () => live.current.onEnd?.();

  const begin = () => {
    const old = handle.current;
    handle.current = null;
    old?.stop();
    setBlocked(false);
    setErrorText(null);
    const { source: src, screen: scr, voice: v } = live.current;
    if ("text" in src && src.text.length > TEXT_MAX) { setErrorText(TOO_LONG); setState("error"); ended(); return; }
    setState("preparing");
    const h: SpeakHandle = speak(src, { screen: scr, voice: v }, {
      onSpeaking: () => { if (handle.current === h) setState("speaking"); },
      onEnd: () => { if (handle.current !== h) return; handle.current = null; setState("idle"); ended(); },
      onStop: () => { if (handle.current !== h) return; handle.current = null; setState("idle"); ended(); },
      onError: (e) => {
        if (handle.current !== h) return;
        handle.current = null;
        if (isNotAllowed(e)) { setBlocked(true); setState("idle"); } else setState("error");
        ended();
      },
    });
    handle.current = h;
  };

  const stopMine = () => {
    const h = handle.current;
    handle.current = null;
    h?.stop();
  };

  const ready = status.enabled && status.tts === "ready";
  const unavailable = status.enabled && (status.tts === "down" || status.tts === "loading");

  const onClick = () => {
    if (!ready) return;
    if (state === "preparing" || state === "speaking") { stopMine(); setState("idle"); ended(); return; }
    stopSpeaking();
    primeAudio(); // inside the click, so the browser lets the fetched speech play
    begin();
  };

  const allow = () => { primeAudio(); begin(); };

  // Talk mode: start on mount once voice is ready; if the browser will not play without a tap, offer the tap instead of trying.
  useEffect(() => {
    if (!autoplay || !ready || autoplayed.current) return;
    autoplayed.current = true;
    if (autoplayPolicy() === "disallowed" && !audioPrimed()) { setBlocked(true); return; }
    begin();
    // begin reads the latest props through a ref; it runs once per mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoplay, ready]);

  // Leaving the screen stops this button's voice (not another button's).
  useEffect(() => () => { const h = handle.current; handle.current = null; h?.stop(); }, []);

  if (!status.enabled || status.tts === "off") return null;

  const speaking = state === "speaking";
  const downText = status.tts === "loading" ? VOICE_TEXT.sttLoading : VOICE_TEXT.ttsDown;
  const title = unavailable ? downText
    : speaking ? VOICE_TEXT.stopReading
      : state === "preparing" ? `${VOICE_TEXT.preparing}. Tap to stop.`
        : state === "error" ? (errorText ?? `${VOICE_TEXT.ttsError}. Tap to try again.`)
          : label;
  const spoken = state === "preparing" ? VOICE_TEXT.preparing : speaking ? VOICE_TEXT.reading : "";
  const tap = size === "icon-xs" ? "min-h-11 min-w-11 sm:min-h-6 sm:min-w-6" : "min-h-11 min-w-11 sm:min-h-8 sm:min-w-8";
  const icon =
    state === "preparing" ? <Loader2 className="animate-spin" aria-hidden />
      : speaking ? <Square className="size-3.5 fill-current" aria-hidden />
        : state === "error" || unavailable ? <VolumeX aria-hidden />
          : <Volume2 aria-hidden />;
  const lineId = `${uid}-line`;

  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1.5", className)} data-state={state}>
      <Button
        type="button"
        variant="ghost"
        size={size}
        onClick={onClick}
        aria-label={speaking ? VOICE_TEXT.stopReading : label}
        title={title}
        aria-pressed={speaking}
        aria-busy={state === "preparing" || undefined}
        aria-disabled={unavailable || undefined}
        aria-describedby={unavailable ? lineId : undefined}
        className={cn(tap, TONE[state], unavailable && "cursor-not-allowed opacity-50 hover:bg-transparent")}
      >
        {icon}
      </Button>
      {unavailable ? <span id={lineId} className="text-xs text-muted-foreground">{downText}</span> : null}
      {state === "preparing" ? <span className="text-xs text-muted-foreground" aria-hidden>{VOICE_TEXT.preparing}</span> : null}
      {speaking ? <span className="text-xs font-medium text-primary" aria-hidden>{VOICE_TEXT.reading}</span> : null}
      {state === "error" ? <span role="status" className="text-xs font-medium text-warn">{errorText ?? VOICE_TEXT.ttsError}</span> : null}
      {blocked ? (
        <Button type="button" variant="outline" size="xs" onClick={allow} className="min-h-11 sm:min-h-6">
          <Volume2 aria-hidden /> {VOICE_TEXT.allowVoices}
        </Button>
      ) : null}
      <span className="sr-only" aria-live="polite">{spoken}</span>
    </span>
  );
}
