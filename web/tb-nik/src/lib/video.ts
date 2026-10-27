// Video for a meeting: a LiveKit room per meeting (video.py gives the token). The person chooses on the pre-join screen whether
// to arrive with the camera and microphone on; the room screen joins under its own identity (<user>#room) and may publish the
// room's camera and microphone. Everything stays on the hospital's own LiveKit server.
import { useCallback, useEffect, useRef, useState } from "react";
import { ConnectionState, Room, RoomEvent, Track, createLocalTracks, type LocalTrack, type RemoteParticipant } from "livekit-client";
import { api, TB } from "@/lib/api";

export interface VideoToken { url: string; token: string; room: string; identity: string; name?: string }

export const getVideoToken = (mid: string, screen?: "room") => api.post<VideoToken>(`${TB}/meetings/${encodeURIComponent(mid)}/video-token`, screen ? { screen } : {});
export const getVideoStatus = () => api.get<{ enabled: boolean; url?: string }>(`${TB}/video/status`);

export interface JoinChoice { mic: boolean; cam: boolean; audioDeviceId?: string; videoDeviceId?: string; audioOutputDeviceId?: string }
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

/** "disconnected": LiveKit dropped the call after it had been connected (the banner offers Rejoin); "off": never joined. */
export type VideoStatus = "off" | "connecting" | "connected" | "reconnecting" | "disconnected" | "failed";

export interface VideoOptions {
  mic?: boolean;
  cam?: boolean;
  audioDeviceId?: string;
  videoDeviceId?: string;
  audioOutputDeviceId?: string;
  /** The room computer joins under its own identity. */
  screen?: "room";
}

export type DeviceKind = "audioinput" | "audiooutput" | "videoinput";

/** Fields of useVideoRoom beyond the call shell's CallVideo contract (night-v3 5.1): read with `videoExtras(ctx.video)`. */
export interface VideoExtras {
  /** A plain sentence when a device in use went away ("The camera you were using was unplugged ..."), for about 12 s. */
  deviceChanged?: string | null;
  /** LiveKit identities that spoke in the last 2 s, the most recent first. */
  activeSpeakers?: string[];
  /** The device ids in use, for the device selects. */
  activeDevice?: (kind: DeviceKind) => string | undefined;
}
export function videoExtras(v: object): VideoExtras {
  return v as VideoExtras;
}

const DEVICE_WORD: Record<DeviceKind, string> = { audioinput: "microphone", audiooutput: "speaker", videoinput: "camera" };

/** The sentence for a device that went away; `fallback` is the label of the device used now. */
export function deviceGoneSentence(kind: DeviceKind, fallback?: string | null): string {
  const w = DEVICE_WORD[kind];
  return `The ${w} you were using was unplugged${fallback ? `; switched to ${fallback}` : `; switched to the default ${w}`}.`;
}

/** Speakers kept for `holdMs` after they stop (so the ring and the order do not flicker), the most recent first. */
export function stickySpeakers(lastSpoke: Map<string, number>, now: number, holdMs = 2000): string[] {
  return [...lastSpoke.entries()].filter(([, t]) => now - t <= holdMs).sort((a, b) => b[1] - a[1]).map(([id]) => id);
}

/** The plain words of a device failure: "Microphone: <the browser's words>", or `fallback` when the browser gave no words. */
export function deviceErrorText(prefix: string, e: unknown, fallback: string): string {
  const msg = e instanceof Error ? e.message.trim() : "";
  return msg ? `${prefix}: ${msg}` : fallback;
}

/** The call's status for a LiveKit connection state (a signal drop is a reconnect too); null keeps the current status. */
export function statusForConnection(state: ConnectionState | string): VideoStatus | null {
  if (state === ConnectionState.Reconnecting || state === ConnectionState.SignalReconnecting) return "reconnecting";
  if (state === ConnectionState.Connected) return "connected";
  return null;
}

/** The screen share capture (night-v3 5.2): 1080p at 15 frames a second (sharp text, little bandwidth), the tab's audio when the
 * browser offers it, and never this tab itself (a mirror of the call). */
export const SCREEN_SHARE_OPTIONS = { audio: true, resolution: { width: 1920, height: 1080, frameRate: 15 }, selfBrowserSurface: "exclude" as const };

/** True when the person said no in the browser's picker (or cancelled it): not an error to show. */
export function isShareRefusal(e: unknown): boolean {
  const name = (e as { name?: string } | null)?.name ?? "";
  return name === "NotAllowedError" || name === "AbortError";
}

/** The plain words of a screen share failure. */
export function shareErrorText(e: unknown, starting = true): string {
  const name = (e as { name?: string } | null)?.name ?? "";
  if (name === "DeviceUnsupportedError" || name === "NotSupportedError") return "This browser cannot present a screen. Use Chrome or Edge on a laptop.";
  if (name === "NotReadableError") return "The screen could not be captured. Close other apps that share the screen and try again.";
  const msg = e instanceof Error && e.message ? `: ${e.message}` : ".";
  return starting ? `The screen could not be shared${msg}` : `The share could not be stopped${msg}`;
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
  const [quality, setQuality] = useState<string>("unknown");
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [deviceChanged, setDeviceChanged] = useState<string | null>(null);
  const [activeSpeakers, setActiveSpeakers] = useState<string[]>([]);
  const [attempt, setAttempt] = useState(0);
  const [shareOn, setShareOn] = useState(false);
  const shareRef = useRef(false);
  shareRef.current = shareOn;
  const micRef = useRef(false);
  const camRef = useRef(false);
  micRef.current = micOn;
  camRef.current = camOn;

  useEffect(() => {
    if (!enabled || !mid) { setStatus("off"); return; }
    let cancelled = false;
    let wasConnected = false;
    const r = newRoom();
    roomRef.current = r;
    setStatus("connecting"); setError(null); setQuality("unknown"); setAudioBlocked(false); setDeviceChanged(null); setActiveSpeakers([]);
    const bump = () => setTick((n) => n + 1);
    const timers: number[] = [];
    const later = (fn: () => void, ms: number) => { timers.push(window.setTimeout(() => { if (!cancelled) fn(); }, ms)); };
    // the speakers stay for 2 s after they stop
    const lastSpoke = new Map<string, number>();
    const showSpeakers = () => setActiveSpeakers((old) => { const next = stickySpeakers(lastSpoke, Date.now()); return old.join("|") === next.join("|") ? old : next; });
    // the devices in use, to tell which one went away
    const known: Record<DeviceKind, string[]> = { audioinput: [], audiooutput: [], videoinput: [] };
    const learnDevices = async () => {
      for (const k of ["audioinput", "audiooutput", "videoinput"] as DeviceKind[]) {
        try { known[k] = (await Room.getLocalDevices(k, false)).map((d) => d.deviceId); } catch { known[k] = []; }
      }
    };
    const onDevicesChanged = async () => {
      for (const k of ["audioinput", "videoinput", "audiooutput"] as DeviceKind[]) {
        let list: MediaDeviceInfo[] = [];
        try { list = await Room.getLocalDevices(k, false); } catch { continue; }
        const active = r.getActiveDevice(k);
        const inUse = k === "audioinput" ? micRef.current : k === "videoinput" ? camRef.current : true;
        if (inUse && active && active !== "default" && known[k].includes(active) && !list.some((d) => d.deviceId === active)) {
          const next = list.find((d) => d.deviceId === "default") ?? list[0];
          if (next) { try { await r.switchActiveDevice(k, next.deviceId); } catch { /* the browser picks one */ } }
          if (cancelled) return;
          setDeviceChanged(deviceGoneSentence(k, next?.label || null));
          later(() => setDeviceChanged(null), 12_000);
        }
        known[k] = list.map((d) => d.deviceId);
      }
      bump();
    };
    r.on(RoomEvent.ParticipantConnected, bump).on(RoomEvent.ParticipantDisconnected, bump)
      .on(RoomEvent.TrackSubscribed, bump).on(RoomEvent.TrackUnsubscribed, bump)
      .on(RoomEvent.TrackMuted, bump).on(RoomEvent.TrackUnmuted, bump)
      .on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const now = Date.now();
        for (const p of speakers) lastSpoke.set(p.identity, now);
        showSpeakers();
        later(showSpeakers, 2100);
        bump();
      })
      .on(RoomEvent.LocalTrackPublished, (pub) => { if (pub.source === Track.Source.ScreenShare) setShareOn(true); bump(); })
      // the browser's own "Stop sharing" ends the track; LiveKit then unpublishes it
      .on(RoomEvent.LocalTrackUnpublished, (pub) => { if (pub.source === Track.Source.ScreenShare) setShareOn(false); bump(); })
      .on(RoomEvent.ConnectionQualityChanged, (q, p) => { if (p.isLocal) setQuality(String(q)); bump(); })
      .on(RoomEvent.AudioPlaybackStatusChanged, () => setAudioBlocked(!r.canPlaybackAudio))
      .on(RoomEvent.MediaDevicesChanged, () => { void onDevicesChanged(); })
      .on(RoomEvent.ActiveDeviceChanged, bump)
      // LiveKit 2.23 reports a signal drop as SignalReconnecting; both kinds show the reconnecting banner
      .on(RoomEvent.Reconnecting, () => { setStatus("reconnecting"); setError(null); })
      .on(RoomEvent.SignalReconnecting, () => { setStatus("reconnecting"); setError(null); })
      .on(RoomEvent.Reconnected, () => { setStatus("connected"); setError(null); })
      .on(RoomEvent.ConnectionStateChanged, (state) => {
        // before the first connect the join itself sets the status
        if (cancelled || !wasConnected) return;
        const next = statusForConnection(state);
        if (next) setStatus(next);
      })
      .on(RoomEvent.Disconnected, () => {
        if (cancelled) return;
        setStatus(wasConnected ? "disconnected" : "off");
        setMicOn(false); setCamOn(false); setShareOn(false); setQuality("unknown"); setError(null);
      });
    const o = optsRef.current;
    connectVideo(mid, r, o.screen).then(async () => {
      if (cancelled) { void r.disconnect(); return; }
      wasConnected = true;
      setRoom(r); setStatus("connected");
      setAudioBlocked(!r.canPlaybackAudio);
      try {
        if (o.audioDeviceId) await r.switchActiveDevice("audioinput", o.audioDeviceId);
        if (o.videoDeviceId) await r.switchActiveDevice("videoinput", o.videoDeviceId);
        if (o.audioOutputDeviceId) await r.switchActiveDevice("audiooutput", o.audioOutputDeviceId);
      } catch { /* the default device then */ }
      try { await r.localParticipant.setMicrophoneEnabled(!!o.mic); setMicOn(!!o.mic); } catch (e) { setMicOn(false); if (o.mic) setError(deviceErrorText("Microphone", e, "The microphone could not be used.")); }
      try { await r.localParticipant.setCameraEnabled(!!o.cam); setCamOn(!!o.cam); } catch (e) { setCamOn(false); if (o.cam) setError(deviceErrorText("Camera", e, "The camera could not be used.")); }
      void learnDevices();
    }).catch((e) => {
      if (cancelled) return;
      setStatus("failed");
      setError(e instanceof Error ? e.message : "Could not join the video room.");
    });
    return () => {
      cancelled = true;
      for (const t of timers) window.clearTimeout(t);
      void disconnectVideo(r); roomRef.current = null; setRoom(null); setMicOn(false); setCamOn(false); setShareOn(false); setActiveSpeakers([]);
    };
  }, [mid, enabled, attempt]);

  const toggleMic = useCallback(async () => {
    const r = roomRef.current; if (!r) return;
    try { const on = !micOn; await r.localParticipant.setMicrophoneEnabled(on); setMicOn(on); setError(null); }
    catch (e) { setError(deviceErrorText("Microphone", e, "The microphone could not be used.")); }
  }, [micOn]);
  const toggleCam = useCallback(async () => {
    const r = roomRef.current; if (!r) return;
    try { const on = !camOn; await r.localParticipant.setCameraEnabled(on); setCamOn(on); setError(null); }
    catch (e) { setError(deviceErrorText("Camera", e, "The camera could not be used.")); }
  }, [camOn]);

  /** Present a screen, or stop (night-v3 5.2). The browser asks which tab, window or screen; a refusal or a cancelled picker
   * leaves the share off without a message; the browser's own "Stop sharing" turns it off too (LocalTrackUnpublished). */
  const toggleShare = useCallback(async () => {
    const r = roomRef.current; if (!r) return;
    const on = !shareRef.current;
    try {
      await r.localParticipant.setScreenShareEnabled(on, on ? SCREEN_SHARE_OPTIONS : undefined);
      setShareOn(on && r.localParticipant.isScreenShareEnabled);
      setError(null);
    } catch (e) {
      setShareOn(r.localParticipant.isScreenShareEnabled);
      if (on && isShareRefusal(e)) return;
      setError(shareErrorText(e, on));
    }
  }, []);

  /** Change a device after joining; the choice is remembered for the next join in this tab. */
  const switchDevice = useCallback(async (kind: DeviceKind, deviceId: string) => {
    const r = roomRef.current; if (!r) return;
    try {
      await r.switchActiveDevice(kind, deviceId);
      setError(null);
      const prev = recallChoice() ?? { mic: micRef.current, cam: camRef.current };
      rememberChoice({
        ...prev,
        mic: micRef.current,
        cam: camRef.current,
        ...(kind === "audioinput" ? { audioDeviceId: deviceId } : kind === "videoinput" ? { videoDeviceId: deviceId } : { audioOutputDeviceId: deviceId }),
      });
      setTick((n) => n + 1);
    } catch (e) {
      setError(deviceErrorText(`The ${DEVICE_WORD[kind]} could not be changed`, e, `The ${DEVICE_WORD[kind]} could not be changed.`));
    }
  }, []);

  const startAudio = useCallback(async () => {
    const r = roomRef.current; if (!r) return;
    try { await r.startAudio(); } catch { /* still blocked */ }
    setAudioBlocked(!r.canPlaybackAudio);
  }, []);

  /** Join again after a disconnect (a new LiveKit room with the same choice). */
  const rejoin = useCallback(() => setAttempt((n) => n + 1), []);

  const activeDevice = useCallback((kind: DeviceKind) => roomRef.current?.getActiveDevice(kind), []);

  const remote: RemoteParticipant[] = room ? Array.from(room.remoteParticipants.values()) : [];
  return { room, status, error, micOn, camOn, toggleMic, toggleCam, remote, tick, quality, audioBlocked, startAudio, switchDevice, rejoin, deviceChanged, activeSpeakers, activeDevice, shareOn, toggleShare };
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

/** The speakers (audio outputs), only where the browser can route audio (setSinkId: Chrome and Edge). */
export function canChooseSpeaker(): boolean {
  return typeof HTMLMediaElement !== "undefined" && "setSinkId" in HTMLMediaElement.prototype;
}
export async function listSpeakers(): Promise<MediaDeviceInfo[]> {
  if (!canChooseSpeaker()) return [];
  try { return await Room.getLocalDevices("audiooutput", false); } catch { return []; }
}
