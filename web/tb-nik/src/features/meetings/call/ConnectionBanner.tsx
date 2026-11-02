// The connection banner at the top of the stage (night-v3 5.1, research/04 section 6.12): the video reconnecting, back online
// for 3 s, disconnected with Rejoin, the live updates paused, the browser blocking the meeting's sound, a device that went away,
// and a poor connection for 10 s. The video and the live updates are told apart. Nothing is drawn when all is well.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CameraOff, Check, Loader2, PlugZap, Volume2, WifiOff } from "lucide-react";
import { videoExtras, type VideoStatus } from "@/lib/video";
import { cn } from "@/lib/utils";
import { useCall } from "./context";

/** True for `ms` after the video came back from reconnecting or a rejoin. */
function useBackOnline(status: VideoStatus, ms = 3000): boolean {
  const prev = useRef<VideoStatus>(status);
  const [on, setOn] = useState(false);
  useEffect(() => {
    const was = prev.current;
    prev.current = status;
    if (status === "connected" && (was === "reconnecting" || was === "disconnected")) {
      setOn(true);
      const t = window.setTimeout(() => setOn(false), ms);
      return () => window.clearTimeout(t);
    }
    if (status !== "connected") setOn(false);
  }, [status, ms]);
  return on;
}

/** True once the quality has been poor (or lost) for `ms` without a break. */
function usePoorFor(quality: string | undefined, ms = 10_000): boolean {
  const poor = quality === "poor" || quality === "lost";
  const [long, setLong] = useState(false);
  useEffect(() => {
    if (!poor) { setLong(false); return; }
    const t = window.setTimeout(() => setLong(true), ms);
    return () => window.clearTimeout(t);
  }, [poor, ms]);
  return poor && long;
}

const btn = "rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-semibold text-white outline-none hover:bg-white/25 focus-visible:ring-2 focus-visible:ring-primary";

function Line({ tone, icon, children, testId }: { tone: "warn" | "bad" | "ok" | "info"; icon: ReactNode; children: ReactNode; testId?: string }) {
  return (
    <motion.p
      layout
      initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
      className={cn("pointer-events-auto flex max-w-full items-center gap-2 rounded-full px-3 py-1 text-xs font-medium text-white shadow-lg sm:text-sm",
        tone === "bad" ? "bg-[#b33a3a]" : tone === "warn" ? "bg-[#8a5a00]" : tone === "ok" ? "bg-[#1d6a44]" : "bg-[#2a3644]")}
      data-testid={testId}
    >
      <span aria-hidden className="shrink-0">{icon}</span>
      <span className="flex min-w-0 flex-wrap items-center gap-2">{children}</span>
    </motion.p>
  );
}

export function ConnectionBanner() {
  const ctx = useCall();
  const v = ctx.video;
  const extra = videoExtras(v);
  const back = useBackOnline(v.status);
  const poor = usePoorFor(v.status === "connected" ? v.quality : undefined);
  const lines: ReactNode[] = [];
  if (v.status === "reconnecting") lines.push(<Line key="rec" tone="warn" icon={<Loader2 className="size-4 animate-spin" />} testId="banner-reconnecting">Reconnecting to the video</Line>);
  if (v.status === "disconnected") {
    lines.push(
      <Line key="off" tone="bad" icon={<PlugZap className="size-4" />} testId="banner-disconnected">
        You are disconnected from the video
        {v.rejoin ? <button type="button" className={btn} onClick={() => v.rejoin?.()} title="Join the video again" data-testid="rejoin">Rejoin</button> : null}
      </Line>,
    );
  }
  if (back) lines.push(<Line key="back" tone="ok" icon={<Check className="size-4" />} testId="banner-back">Back online</Line>);
  if (ctx.liveStatus === "unavailable") {
    lines.push(<Line key="live" tone="info" icon={<WifiOff className="size-4" />} testId="banner-live">Live updates paused: checking every 10 seconds</Line>);
  }
  if (v.audioBlocked && v.startAudio && (v.status === "connected" || v.status === "reconnecting")) {
    lines.push(
      <Line key="audio" tone="warn" icon={<Volume2 className="size-4" />} testId="banner-audio">
        The browser is holding back the sound
        <button type="button" className={btn} onClick={() => void v.startAudio?.()} title="Play the meeting's sound" data-testid="start-audio">Click to hear the meeting</button>
      </Line>,
    );
  }
  if (extra.deviceChanged) lines.push(<Line key="dev" tone="info" icon={<PlugZap className="size-4" />} testId="banner-device">{extra.deviceChanged}</Line>);
  if (poor) {
    lines.push(
      <Line key="poor" tone="warn" icon={<WifiOff className="size-4" />} testId="banner-poor">
        Your connection is poor: turn the camera off to save bandwidth
        {v.camOn ? <button type="button" className={btn} onClick={() => void v.toggleCam()} title="Turn the camera off (Ctrl+E)" aria-keyshortcuts="Control+E"><CameraOff className="mr-1 inline size-3.5" aria-hidden />Camera off</button> : null}
      </Line>,
    );
  }
  return (
    <div className="pointer-events-none absolute inset-x-0 top-2 z-20 flex flex-col items-center gap-1.5 px-3" role="status" aria-live="polite" data-testid="connection-banner">
      <AnimatePresence initial={false}>{lines}</AnimatePresence>
    </div>
  );
}
