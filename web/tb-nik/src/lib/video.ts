// Video for remote members: a LiveKit room per meeting (video.py gives the token). Muted and camera off by default;
// the person switches them on. Everything stays on the hospital's own LiveKit server.
import { useCallback, useEffect, useRef, useState } from "react";
import { Room, RoomEvent, type RemoteParticipant } from "livekit-client";
import { api, TB } from "@/lib/api";

export interface VideoToken { url: string; token: string; room: string; identity: string; name?: string }

export const getVideoToken = (mid: string) => api.post<VideoToken>(`${TB}/meetings/${encodeURIComponent(mid)}/video-token`, {});
export const getVideoStatus = () => api.get<{ enabled: boolean; url?: string }>(`${TB}/video/status`);

export function newRoom(): Room {
  return new Room({ adaptiveStream: true, dynacast: true, videoCaptureDefaults: { resolution: { width: 640, height: 360, frameRate: 24 } } });
}

/** Connect to the meeting's room; the microphone and camera stay off until toggled. */
export async function connectVideo(mid: string, room: Room = newRoom()): Promise<{ room: Room; info: VideoToken }> {
  const info = await getVideoToken(mid);
  await room.connect(info.url, info.token, { autoSubscribe: true });
  return { room, info };
}

export async function disconnectVideo(room: Room | null | undefined): Promise<void> {
  if (!room) return;
  try { await room.disconnect(true); } catch { /* already gone */ }
}

export type VideoStatus = "off" | "connecting" | "connected" | "reconnecting" | "failed";

/** React hook: connect when enabled, expose toggles and the participant list. */
export function useVideoRoom(mid: string, enabled: boolean) {
  const roomRef = useRef<Room | null>(null);
  const [room, setRoom] = useState<Room | null>(null);
  const [status, setStatus] = useState<VideoStatus>("off");
  const [error, setError] = useState<string | null>(null);
  const [micOn, setMicOn] = useState(false);
  const [camOn, setCamOn] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!enabled || !mid) { setStatus("off"); return; }
    let cancelled = false;
    const r = newRoom();
    roomRef.current = r;
    setStatus("connecting"); setError(null);
    const bump = () => setTick((n) => n + 1);
    r.on(RoomEvent.ParticipantConnected, bump).on(RoomEvent.ParticipantDisconnected, bump)
      .on(RoomEvent.TrackSubscribed, bump).on(RoomEvent.TrackUnsubscribed, bump)
      .on(RoomEvent.LocalTrackPublished, bump).on(RoomEvent.LocalTrackUnpublished, bump)
      .on(RoomEvent.Reconnecting, () => setStatus("reconnecting")).on(RoomEvent.Reconnected, () => setStatus("connected"))
      .on(RoomEvent.Disconnected, () => { if (!cancelled) setStatus("off"); });
    connectVideo(mid, r).then(() => {
      if (cancelled) { void r.disconnect(); return; }
      setRoom(r); setStatus("connected");
      void r.localParticipant.setMicrophoneEnabled(false);
      void r.localParticipant.setCameraEnabled(false);
    }).catch((e) => {
      if (cancelled) return;
      setStatus("failed");
      setError(e instanceof Error ? e.message : "Could not join the video room.");
    });
    return () => { cancelled = true; void disconnectVideo(r); roomRef.current = null; setRoom(null); setMicOn(false); setCamOn(false); };
  }, [mid, enabled]);

  const toggleMic = useCallback(async () => {
    const r = roomRef.current; if (!r) return;
    try { const on = !micOn; await r.localParticipant.setMicrophoneEnabled(on); setMicOn(on); setError(null); }
    catch (e) { setError(e instanceof Error ? `Microphone: ${e.message}` : "The microphone could not be used."); }
  }, [micOn]);
  const toggleCam = useCallback(async () => {
    const r = roomRef.current; if (!r) return;
    try { const on = !camOn; await r.localParticipant.setCameraEnabled(on); setCamOn(on); setError(null); }
    catch (e) { setError(e instanceof Error ? `Camera: ${e.message}` : "The camera could not be used."); }
  }, [camOn]);

  const remote: RemoteParticipant[] = room ? Array.from(room.remoteParticipants.values()) : [];
  return { room, status, error, micOn, camOn, toggleMic, toggleCam, remote, tick };
}
