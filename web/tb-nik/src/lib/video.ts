// Video for a meeting: a LiveKit room per meeting (video.py gives the token). The person chooses on the pre-join screen whether
// to arrive with the camera and microphone on; the room screen joins under its own identity (<user>#room) and may publish the
// room's camera and microphone. Everything stays on the hospital's own LiveKit server.
import { useCallback, useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, createLocalTracks, type LocalTrack, type RemoteParticipant } from "livekit-client";
import { api, TB } from "@/lib/api";

export interface VideoToken { url: string; token: string; room: string; identity: string; name?: string }

export const getVideoToken = (mid: string, screen?: "room") => api.post<VideoToken>(`${TB}/meetings/${encodeURIComponent(mid)}/video-token`, screen ? { screen } : {});
export const getVideoStatus = () => api.get<{ enabled: boolean; url?: string }>(`${TB}/video/status`);

export interface JoinChoice { mic: boolean; cam: boolean; audioDeviceId?: string; videoDeviceId?: string }
const CHOICE_KEY = "tbnik.video.choice";
export function rememberChoice(c: JoinChoice) { try { sessionStorage.setItem(CHOICE_KEY, JSON.stringify(c)); } catch { /* no storage */ } }
export function recallChoice(): JoinChoice | null { try { const v = sessionStorage.getItem(CHOICE_KEY); return v ? (JSON.parse(v) as JoinChoice) : null; } catch { return null; } }

export function newRoom(): Room {
  return new Room({ adaptiveStream: true, dynacast: true, videoCaptureDefaults: { resolution: { width: 960, height: 540, frameRate: 24 } } });
}

/** Connect to the meeting's room; the microphone and camera follow the choice given (off by default). */
export async function connectVideo(mid: string, room: Room = newRoom(), screen?: "room"): Promise<{ room: Room; info: VideoToken }> {
  const info = await getVideoToken(mid, screen);
  await room.connect(info.url, info.token, { autoSubscribe: true });
  return { room, info };
}

export async function disconnectVideo(room: Room | null | undefined): Promise<void> {
  if (!room) return;
  try { await room.disconnect(true); } catch { /* already gone */ }
}

/** The LiveKit identity "<user>" or "<user>#room" back to the Vaidyx login. */
export function identityUser(identity: string): string {
  return identity.split("#")[0];
}
export function isRoomScreen(identity: string): boolean {
  return identity.endsWith("#room");
}

export type VideoStatus = "off" | "connecting" | "connected" | "reconnecting" | "failed";

export interface VideoOptions {
  mic?: boolean;
  cam?: boolean;
  audioDeviceId?: string;
  videoDeviceId?: string;
  /** The room computer joins under its own identity. */
  screen?: "room";
}

/** React hook: connect when enabled, expose the toggles and a tick that changes whenever the participants or tracks change. */
export function useVideoRoom(mid: string, enabled: boolean, opts: VideoOptions = {}) {
  const roomRef = useRef<Room | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;
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
      .on(RoomEvent.TrackMuted, bump).on(RoomEvent.TrackUnmuted, bump)
      .on(RoomEvent.ActiveSpeakersChanged, bump)
      .on(RoomEvent.LocalTrackPublished, bump).on(RoomEvent.LocalTrackUnpublished, bump)
      .on(RoomEvent.Reconnecting, () => setStatus("reconnecting")).on(RoomEvent.Reconnected, () => setStatus("connected"))
      .on(RoomEvent.Disconnected, () => { if (!cancelled) setStatus("off"); });
    const o = optsRef.current;
    connectVideo(mid, r, o.screen).then(async () => {
      if (cancelled) { void r.disconnect(); return; }
      setRoom(r); setStatus("connected");
      try {
        if (o.audioDeviceId) await r.switchActiveDevice("audioinput", o.audioDeviceId);
        if (o.videoDeviceId) await r.switchActiveDevice("videoinput", o.videoDeviceId);
      } catch { /* the default device then */ }
      try { await r.localParticipant.setMicrophoneEnabled(!!o.mic); setMicOn(!!o.mic); } catch (e) { setMicOn(false); if (o.mic) setError(e instanceof Error ? `Microphone: ${e.message}` : "The microphone could not be used."); }
      try { await r.localParticipant.setCameraEnabled(!!o.cam); setCamOn(!!o.cam); } catch (e) { setCamOn(false); if (o.cam) setError(e instanceof Error ? `Camera: ${e.message}` : "The camera could not be used."); }
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

/** A camera and microphone preview for the pre-join screen: the tracks are created on demand and stopped on release. */
export async function previewTracks(opts: { audio: boolean; video: boolean; audioDeviceId?: string; videoDeviceId?: string }): Promise<LocalTrack[]> {
  if (!opts.audio && !opts.video) return [];
  return createLocalTracks({
    audio: opts.audio ? (opts.audioDeviceId ? { deviceId: opts.audioDeviceId } : true) : false,
    video: opts.video ? { deviceId: opts.videoDeviceId, resolution: { width: 640, height: 360, frameRate: 24 } } : false,
  });
}

export function stopTracks(tracks: LocalTrack[]) {
  for (const t of tracks) { try { t.stop(); } catch { /* already stopped */ } }
}

export const isVideoTrack = (t: LocalTrack) => t.kind === Track.Kind.Video;
export const isAudioTrack = (t: LocalTrack) => t.kind === Track.Kind.Audio;

export async function listDevices(): Promise<{ cameras: MediaDeviceInfo[]; mics: MediaDeviceInfo[] }> {
  try {
    const [cameras, mics] = await Promise.all([Room.getLocalDevices("videoinput"), Room.getLocalDevices("audioinput")]);
    return { cameras, mics };
  } catch { return { cameras: [], mics: [] }; }
}
