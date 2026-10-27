// Before joining a meeting with video: see your own camera, check the microphone level, pick a device, then "Join now" with the
// camera and microphone as chosen (or join without video). The choice is kept for the session.
import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { Camera, CameraOff, Mic, MicOff, Settings2, Video, VideoOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VaidyxIcon, VaidyxWordmark } from "@/components/Wordmark";
import { MicLevel } from "@/components/MicLevel";
import { isAudioTrack, isVideoTrack, listDevices, previewTracks, recallChoice, rememberChoice, stopTracks, type JoinChoice } from "@/lib/video";
import type { LocalTrack } from "livekit-client";
import { cn } from "@/lib/utils";

export function PreJoin({ title, subtitle, onJoin, onSkip, allowSkip = true }: { title: string; subtitle?: string; onJoin: (c: JoinChoice) => void; onSkip?: () => void; allowSkip?: boolean }) {
  const remembered = recallChoice();
  const [cam, setCam] = useState(remembered?.cam ?? true);
  const [mic, setMic] = useState(remembered?.mic ?? true);
  const [videoDeviceId, setVideoDeviceId] = useState(remembered?.videoDeviceId);
  const [audioDeviceId, setAudioDeviceId] = useState(remembered?.audioDeviceId);
  const [devices, setDevices] = useState<{ cameras: MediaDeviceInfo[]; mics: MediaDeviceInfo[] }>({ cameras: [], mics: [] });
  const [tracks, setTracks] = useState<LocalTrack[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [showDevices, setShowDevices] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let live = true;
    let mine: LocalTrack[] = [];
    setErr(null);
    previewTracks({ audio: mic, video: cam, audioDeviceId, videoDeviceId }).then((ts) => {
      if (!live) { stopTracks(ts); return; }
      mine = ts; setTracks(ts);
      void listDevices().then((d) => { if (live) setDevices(d); });
    }).catch((e) => { if (live) setErr(e instanceof Error ? e.message : "The camera or microphone could not be opened."); });
    return () => { live = false; stopTracks(mine); setTracks([]); };
  }, [cam, mic, audioDeviceId, videoDeviceId]);

  useEffect(() => {
    const v = tracks.find(isVideoTrack);
    const el = videoRef.current;
    if (!el) return;
    if (v) { v.attach(el); return () => { v.detach(el); }; }
    return undefined;
  }, [tracks]);

  const audio = tracks.find(isAudioTrack) ?? null;
  const join = (withVideo: boolean) => {
    const c: JoinChoice = { mic: withVideo ? mic : false, cam: withVideo ? cam : false, audioDeviceId, videoDeviceId };
    rememberChoice(c);
    stopTracks(tracks);
    if (withVideo) onJoin(c); else onSkip?.();
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-stage p-4 text-stage-fg" data-testid="prejoin">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="grid w-full max-w-4xl gap-6 lg:grid-cols-[3fr_2fr] lg:items-center">
        <div className="relative aspect-video overflow-hidden rounded-2xl bg-stage-panel ring-1 ring-stage-line">
          <video ref={videoRef} autoPlay muted playsInline className={cn("h-full w-full -scale-x-100 object-cover", !cam && "hidden")} />
          {!cam ? <div className="grid h-full w-full place-items-center text-stage-muted"><span className="flex flex-col items-center gap-2"><CameraOff className="size-10" />Camera is off</span></div> : null}
          <div className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-3 bg-gradient-to-t from-black/60 to-transparent px-4 pb-4 pt-10">
            <button type="button" onClick={() => setMic((v) => !v)} aria-pressed={mic} aria-label={mic ? "Turn the microphone off" : "Turn the microphone on"} className={cn("grid size-12 place-items-center rounded-full border transition", mic ? "border-white/30 bg-white/10 text-white hover:bg-white/20" : "border-[#d64545] bg-[#d64545] text-white")}>{mic ? <Mic className="size-5" /> : <MicOff className="size-5" />}</button>
            <button type="button" onClick={() => setCam((v) => !v)} aria-pressed={cam} aria-label={cam ? "Turn the camera off" : "Turn the camera on"} className={cn("grid size-12 place-items-center rounded-full border transition", cam ? "border-white/30 bg-white/10 text-white hover:bg-white/20" : "border-[#d64545] bg-[#d64545] text-white")}>{cam ? <Camera className="size-5" /> : <CameraOff className="size-5" />}</button>
            <button type="button" onClick={() => setShowDevices((v) => !v)} aria-expanded={showDevices} aria-label="Choose the camera and microphone" className="grid size-12 place-items-center rounded-full border border-white/30 bg-white/10 text-white transition hover:bg-white/20"><Settings2 className="size-5" /></button>
          </div>
          <div className="absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/50 px-2.5 py-1 text-xs text-white">{mic ? <Mic className="size-3.5" /> : <MicOff className="size-3.5" />}<MicLevel track={mic ? audio?.mediaStreamTrack ?? null : null} /></div>
        </div>
        <div className="space-y-4">
          <div className="flex items-center gap-2"><VaidyxIcon tone="white" className="h-6" /><VaidyxWordmark tone="white" className="h-5" /></div>
          <div>
            <h1 className="text-2xl text-stage-fg">{title}</h1>
            {subtitle ? <p className="mt-1 text-sm text-stage-muted">{subtitle}</p> : null}
          </div>
          {showDevices ? (
            <div className="space-y-2 rounded-xl border border-stage-line bg-stage-panel p-3 text-sm">
              <label className="block"><span className="text-xs text-stage-muted">Camera</span>
                <select value={videoDeviceId ?? ""} onChange={(e) => setVideoDeviceId(e.target.value || undefined)} className="mt-0.5 w-full rounded-md border border-stage-line bg-stage-raised px-2 py-1.5 text-stage-fg">
                  <option value="">Default camera</option>{devices.cameras.map((d) => <option key={d.deviceId} value={d.deviceId}>{d.label || "Camera"}</option>)}
                </select>
              </label>
              <label className="block"><span className="text-xs text-stage-muted">Microphone</span>
                <select value={audioDeviceId ?? ""} onChange={(e) => setAudioDeviceId(e.target.value || undefined)} className="mt-0.5 w-full rounded-md border border-stage-line bg-stage-raised px-2 py-1.5 text-stage-fg">
                  <option value="">Default microphone</option>{devices.mics.map((d) => <option key={d.deviceId} value={d.deviceId}>{d.label || "Microphone"}</option>)}
                </select>
              </label>
            </div>
          ) : null}
          {err ? <p role="alert" className="rounded-md bg-bad/15 px-3 py-2 text-sm text-[#ffb4a8]">{err} You can still join and follow the shared screen.</p> : null}
          <div className="flex flex-wrap items-center gap-2">
            <Button size="lg" className="h-11 rounded-full px-6" onClick={() => join(true)} data-testid="prejoin-join"><Video className="size-4" />Join now</Button>
            {allowSkip ? <Button size="lg" variant="ghost" className="h-11 rounded-full text-stage-fg hover:bg-stage-raised hover:text-stage-fg" onClick={() => join(false)}><VideoOff className="size-4" />Join without video</Button> : null}
          </div>
          <p className="text-xs text-stage-muted">Video and sound stay on the hospital's own server. Nothing is recorded.</p>
        </div>
      </motion.div>
    </div>
  );
}
