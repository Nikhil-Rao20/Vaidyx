import { useEffect, useState } from "react";
import type { Room } from "livekit-client";
import { registerDictationGuard } from "@/lib/voice";
import type { VideoStatus } from "@/lib/video";

/**
 * The dictation guard of a meeting call (night-v3 4.4): while connected with the call microphone on, dictation mutes the
 * published microphone through the room and turns it back on after, only if this guard muted it. Gone when the video
 * disconnects, the microphone is turned off or the page closes. Returns true while the call microphone is off for dictation.
 */
export function useDictationGuard(video: { room: Room | null; status: VideoStatus; micOn: boolean }): boolean {
  const [dictating, setDictating] = useState(false);
  const callRoom = video.room;
  const callLive = video.status === "connected" || video.status === "reconnecting";
  useEffect(() => {
    if (!callRoom || !callLive || !video.micOn) return;
    let mutedByUs = false;
    registerDictationGuard({
      mute: async () => {
        const lp = callRoom.localParticipant;
        if (!lp.isMicrophoneEnabled) return;
        mutedByUs = true;
        setDictating(true);
        await lp.setMicrophoneEnabled(false);
      },
      restore: async () => {
        if (!mutedByUs) return;
        mutedByUs = false;
        setDictating(false);
        await callRoom.localParticipant.setMicrophoneEnabled(true);
      },
    });
    return () => { registerDictationGuard(null); setDictating(false); };
  }, [callRoom, callLive, video.micOn]);
  return dictating;
}
