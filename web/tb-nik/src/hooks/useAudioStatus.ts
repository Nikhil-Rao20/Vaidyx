// Whether voice is on for this app and the dictation and read-aloud services are ready (night-v3 item 4.3). A missing route
// (404), a network error or any other failure means "no voice": the microphone and speaker buttons draw nothing. While a
// service is starting or down the status is asked again every 30 s and on window focus, so the buttons come back by themselves.
import { useQuery } from "@tanstack/react-query";
import { AUDIO_OFF, DEFAULT_LIMITS, getAudioStatus, type AudioLimits, type AudioStatus, type ServiceState } from "@/lib/voice";

const waiting = (s: ServiceState | undefined) => s === "down" || s === "loading";

export function useAudioStatus(): { enabled: boolean; stt: ServiceState; tts: ServiceState; limits: AudioLimits; voices: string[]; isLoading: boolean } {
  const q = useQuery<AudioStatus, Error>({
    queryKey: ["audio-status"],
    queryFn: ({ signal }) => getAudioStatus(signal),
    staleTime: 30_000,
    retry: false,
    refetchOnWindowFocus: true,
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && d.enabled && (waiting(d.stt) || waiting(d.tts)) ? 30_000 : false;
    },
  });
  const d = q.error || !q.data || typeof q.data !== "object" ? AUDIO_OFF : q.data;
  const enabled = d.enabled === true;
  return {
    enabled,
    stt: enabled ? d.stt ?? "off" : "off",
    tts: enabled ? d.tts ?? "off" : "off",
    limits: { ...DEFAULT_LIMITS, ...(d.limits ?? {}) },
    voices: Array.isArray(d.voices) ? d.voices : [],
    isLoading: q.isLoading,
  };
}
