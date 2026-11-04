// Devices after joining (night-v3 5.1, research/04 section 6.11): the microphone, the speaker (only where the browser can route
// sound, setSinkId) and the camera, the microphone level, and "Test the speaker" (a short tone). A change goes through
// video.switchDevice (room.switchActiveDevice) and is remembered for the next join in this tab. DevicePopover wraps the small
// arrow beside Mic or Camera; DeviceSettings is the same content for the More menu.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Track } from "livekit-client";
import { Volume2 } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { MicLevel } from "@/components/MicLevel";
import { canChooseSpeaker, listDevices, listSpeakers, recallChoice, videoExtras, type DeviceKind } from "@/lib/video";
import { cn } from "@/lib/utils";
import { useCall } from "./context";

interface Devices { mics: MediaDeviceInfo[]; cameras: MediaDeviceInfo[]; speakers: MediaDeviceInfo[] }
const NONE: Devices = { mics: [], cameras: [], speakers: [] };

function useDevices(open: boolean): Devices {
  const [d, setD] = useState<Devices>(NONE);
  useEffect(() => {
    if (!open) return;
    let live = true;
    const load = () => { void Promise.all([listDevices(), listSpeakers()]).then(([a, speakers]) => { if (live) setD({ mics: a.mics, cameras: a.cameras, speakers }); }); };
    load();
    const md = typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
    md?.addEventListener?.("devicechange", load);
    return () => { live = false; md?.removeEventListener?.("devicechange", load); };
  }, [open]);
  return d;
}

/** A short, quiet tone through the chosen speaker (AudioContext.setSinkId where the browser has it). */
async function playTone(sinkId?: string): Promise<void> {
  const Ctx = window.AudioContext;
  if (!Ctx) return;
  const ctx = new Ctx();
  try {
    const withSink = ctx as AudioContext & { setSinkId?: (id: string) => Promise<void> };
    if (sinkId && sinkId !== "default" && withSink.setSinkId) { try { await withSink.setSinkId(sinkId); } catch { /* the default speaker */ } }
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 660;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.7);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.75);
    await new Promise((r) => window.setTimeout(r, 850));
  } finally {
    void ctx.close();
  }
}

const selectCls = "mt-0.5 w-full rounded-md border border-stage-line bg-stage-raised px-2 py-1.5 text-sm text-stage-fg outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50";

function DeviceSelect({ id, label, kind, list, value, onPick, disabled, fallback }: { id: string; label: string; kind: DeviceKind; list: MediaDeviceInfo[]; value: string; onPick: (kind: DeviceKind, id: string) => void; disabled?: boolean; fallback: string }) {
  return (
    <label className="block" htmlFor={id}>
      <span className="text-xs text-stage-muted">{label}</span>
      <select id={id} value={value} onChange={(e) => onPick(kind, e.target.value)} className={selectCls} disabled={disabled || !list.length} data-testid={`device-${kind}`}>
        {!list.some((d) => d.deviceId === value) ? <option value={value}>{fallback}</option> : null}
        {list.map((d, i) => <option key={d.deviceId || i} value={d.deviceId}>{d.label || `${fallback} ${i + 1}`}</option>)}
      </select>
    </label>
  );
}

/** The device choices, for the popover and for the More menu. `focus` puts the microphone or the camera first. */
export function DeviceSettings({ focus = "audio", open = true, className }: { focus?: "audio" | "video"; open?: boolean; className?: string }) {
  const { video } = useCall();
  const devices = useDevices(open);
  const extra = videoExtras(video);
  const saved = recallChoice();
  const [busy, setBusy] = useState<DeviceKind | null>(null);
  const [testing, setTesting] = useState(false);
  const connected = video.status === "connected" || video.status === "reconnecting";
  const current = (kind: DeviceKind, savedId?: string) => extra.activeDevice?.(kind) ?? savedId ?? "default";
  const pick = useCallback(async (kind: DeviceKind, id: string) => {
    if (!video.switchDevice) return;
    setBusy(kind);
    try { await video.switchDevice(kind, id); } finally { setBusy(null); }
  }, [video]);
  void video.tick; // re-read the active devices when LiveKit changes them
  const micTrack = video.micOn ? video.room?.localParticipant.getTrackPublication(Track.Source.Microphone)?.track?.mediaStreamTrack ?? null : null;
  const speaker = current("audiooutput", saved?.audioOutputDeviceId);
  const mic = (
    <div key="mic" className="space-y-1">
      <DeviceSelect id="call-dev-mic" label="Microphone" kind="audioinput" list={devices.mics} value={current("audioinput", saved?.audioDeviceId)} onPick={(k, i) => void pick(k, i)} disabled={!connected || busy === "audioinput"} fallback="Default microphone" />
      <div className="flex items-center gap-2 text-xs text-stage-muted">
        <MicLevel track={micTrack} />
        <span>{video.micOn ? "Speak to see the level" : "The microphone is off"}</span>
      </div>
    </div>
  );
  const out = canChooseSpeaker() ? (
    <DeviceSelect key="out" id="call-dev-out" label="Speaker" kind="audiooutput" list={devices.speakers} value={speaker} onPick={(k, i) => void pick(k, i)} disabled={!connected || busy === "audiooutput"} fallback="Default speaker" />
  ) : null;
  const test = (
    <button key="test" type="button" onClick={() => { setTesting(true); void playTone(speaker).finally(() => setTesting(false)); }} disabled={testing}
      className="inline-flex items-center gap-1.5 rounded-full border border-stage-line bg-stage-raised px-3 py-1 text-xs font-medium text-stage-fg outline-none hover:bg-stage-line focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
      title="Play a short tone through the speaker" data-testid="test-speaker">
      <Volume2 className="size-3.5" aria-hidden />{testing ? "Playing a tone" : "Test the speaker"}
    </button>
  );
  const cam = (
    <DeviceSelect key="cam" id="call-dev-cam" label="Camera" kind="videoinput" list={devices.cameras} value={current("videoinput", saved?.videoDeviceId)} onPick={(k, i) => void pick(k, i)} disabled={!connected || busy === "videoinput"} fallback="Default camera" />
  );
  const parts = focus === "video" ? [cam, mic, out, test] : [mic, out, test, cam];
  return (
    <div className={cn("space-y-3 text-stage-fg", className)} data-testid="device-settings">
      {!connected ? <p className="text-xs text-stage-muted">Join the video to change the devices.</p> : null}
      {parts}
      {video.error ? <p role="alert" className="text-xs text-bad">{video.error}</p> : null}
    </div>
  );
}

/** The popover from the small arrow beside Mic (kind audio) or Camera (kind video); `children` is the arrow button. */
export function DevicePopover({ kind, children }: { kind: "audio" | "video"; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent side="top" align="start" className="w-80 border-stage-line bg-stage-panel text-stage-fg" aria-label={kind === "audio" ? "Microphone and speaker" : "Camera"}>
        <h2 className="mb-2 text-sm font-semibold">{kind === "audio" ? "Microphone and speaker" : "Camera"}</h2>
        <DeviceSettings focus={kind} open={open} />
      </PopoverContent>
    </Popover>
  );
}
