// The recorder's words, and the notice on the join page, the waiting rooms and the pre-join while the meeting is recorded (meetings-v2
// 5.2). Kept apart from the call's code so the join page stays small.
import { Circle } from "lucide-react";
import { isRecording } from "@/lib/live";
import { cn } from "@/lib/utils";

export const BADGE_ON = "Recording: text only, no audio kept";
export const BADGE_PAUSED = "Recording paused: text only, no audio kept";
export const JOIN_NOTICE = "This meeting is being recorded as text. No audio is kept.";

/** The join page's and the pre-join's notice while the meeting is recorded (on or paused); nothing otherwise. */
export function RecordingNotice({ state, className }: { state?: string | null; className?: string }) {
  if (!isRecording(state ?? "off")) return null;
  return (
    <p role="status" className={cn("flex items-start gap-2 rounded-md bg-bad-soft px-3 py-2 text-sm font-medium text-bad", className)} data-testid="recording-notice">
      <Circle className="mt-0.5 size-3.5 shrink-0 fill-current" aria-hidden />{JOIN_NOTICE}
    </p>
  );
}
