// The five-bar microphone level meter (moved out of the meeting's PreJoin for the dictation button). It reads either a live
// microphone track (its own small analyser, closed when the track changes) or a level from 0 to 1 that the caller measures.
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const STEPS = [0.15, 0.35, 0.55, 0.75, 0.95];

/** The level of a live microphone track, 0 to 1 (0 when there is no track or no audio context). */
function useTrackLevel(track: MediaStreamTrack | null): number {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    if (!track) { setLevel(0); return; }
    let ctx: AudioContext | null = null;
    let raf = 0;
    try {
      ctx = new AudioContext();
      const src = ctx.createMediaStreamSource(new MediaStream([track]));
      const an = ctx.createAnalyser(); an.fftSize = 512;
      src.connect(an);
      const buf = new Uint8Array(an.frequencyBinCount);
      const loop = () => { an.getByteTimeDomainData(buf); let sum = 0; for (const v of buf) { const d = (v - 128) / 128; sum += d * d; } setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4)); raf = requestAnimationFrame(loop); };
      loop();
    } catch { /* no audio context */ }
    return () => { cancelAnimationFrame(raf); void ctx?.close(); };
  }, [track]);
  return level;
}

export function MicLevel({ track = null, level, className, onClassName = "bg-primary", offClassName = "bg-stage-line" }: {
  /** A live microphone track to measure; ignored when `level` is given. */
  track?: MediaStreamTrack | null;
  /** A level from 0 to 1 measured by the caller. */
  level?: number;
  className?: string;
  /** The colour of a lit bar and of an unlit one (the meeting's dark stage by default). */
  onClassName?: string;
  offClassName?: string;
}) {
  const measured = useTrackLevel(level === undefined ? track : null);
  const value = Math.max(0, Math.min(1, level ?? measured));
  const pct = Math.round(value * 100);
  return (
    <span className={cn("flex items-end gap-0.5", className)} aria-label={`Microphone level ${pct} percent`} role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      {STEPS.map((t, i) => <span key={i} className={cn("w-1 rounded-sm transition-colors", value >= t ? onClassName : offClassName)} style={{ height: 6 + i * 3 }} />)}
    </span>
  );
}
