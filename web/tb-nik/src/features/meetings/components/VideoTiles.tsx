// Video tiles for remote members (LiveKit). Camera and microphone are off until the person switches them on.
import { RoomAudioRenderer, RoomContext, VideoTrack, useTracks } from "@livekit/components-react";
import { Track } from "livekit-client";
import { Camera, CameraOff, Mic, MicOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVideoRoom } from "@/lib/video";
import { StatusChip, initials } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

function Tiles() {
  const tracks = useTracks([{ source: Track.Source.Camera, withPlaceholder: true }], { onlySubscribed: false });
  if (!tracks.length) return <p className="text-xs text-muted-foreground">No one has a camera on.</p>;
  return (
    <ul className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
      {tracks.map((t) => {
        const name = t.participant.name || t.participant.identity;
        const hasVideo = "publication" in t && !!t.publication && !t.publication.isMuted;
        return (
          <li key={`${t.participant.identity}-${t.source}`} className="relative aspect-video overflow-hidden rounded-md bg-muted" aria-label={name}>
            {hasVideo ? <VideoTrack trackRef={t} className="h-full w-full object-cover" /> : <div className="grid h-full w-full place-items-center"><span className="grid size-10 place-items-center rounded-full bg-primary text-primary-foreground font-medium">{initials(name)}</span></div>}
            <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1.5 py-0.5 text-[11px] text-white">{name}{t.participant.isLocal ? " (you)" : ""}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function VideoTiles({ mid, enabled }: { mid: string; enabled: boolean }) {
  const v = useVideoRoom(mid, enabled);
  if (!enabled) return null;
  return (
    <section className="surface p-3 space-y-2" aria-label="Video" data-testid="video-tiles" data-video-status={v.status}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Video</h2>
        {v.status === "connecting" ? <StatusChip kind="info">connecting</StatusChip> : v.status === "connected" ? <StatusChip kind="ok">connected</StatusChip> : v.status === "reconnecting" ? <StatusChip kind="warn">reconnecting</StatusChip> : v.status === "failed" ? <StatusChip kind="bad">not connected</StatusChip> : null}
        <span className="flex-1" />
        <Button size="sm" variant={v.micOn ? "secondary" : "outline"} onClick={() => void v.toggleMic()} disabled={v.status !== "connected"} aria-pressed={v.micOn} aria-label={v.micOn ? "Mute the microphone" : "Unmute the microphone"}>{v.micOn ? <Mic className="size-4" /> : <MicOff className="size-4" />}{v.micOn ? "Mic on" : "Muted"}</Button>
        <Button size="sm" variant={v.camOn ? "secondary" : "outline"} onClick={() => void v.toggleCam()} disabled={v.status !== "connected"} aria-pressed={v.camOn} aria-label={v.camOn ? "Turn the camera off" : "Turn the camera on"}>{v.camOn ? <Camera className="size-4" /> : <CameraOff className="size-4" />}{v.camOn ? "Camera on" : "Camera off"}</Button>
      </div>
      {v.error ? <p role="alert" className="text-xs text-bad">{v.error}</p> : null}
      {v.status === "failed" ? <p className="text-xs text-muted-foreground">You can still follow the shared screen and type questions.</p> : null}
      <div className={cn(v.status !== "connected" && "opacity-60")}>
        {v.room ? <RoomContext.Provider value={v.room}><Tiles /><RoomAudioRenderer /></RoomContext.Provider> : <p className="text-xs text-muted-foreground">Joining the video room</p>}
      </div>
      <p className="text-[11px] text-muted-foreground">Video stays on the hospital's own server. You join muted; switch the microphone on to speak.</p>
    </section>
  );
}
