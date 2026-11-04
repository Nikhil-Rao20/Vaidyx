// Shapes of the one-page planner (meetings-v2 3.3), checked against tumour_board/meetings.py (series_row, summary_row, row, view) and
// tumour_board/api/meetings.py. The meeting view itself is MeetingState (src/lib/live.ts); the fields added in 3.1 and 3.2 are here.
import type { AgendaRow, MeetingInfo, MeetingState } from "@/lib/live";

export type ListKey = "discussion" | "noting";

/** An agenda row with the 3.2 marks: `new` when it joined a list the coordinator arranged by hand; `sent_at` when it was sent. */
export type PlanRow = AgendaRow & { new?: boolean; sent_at?: string; restricted?: boolean };

/** A meeting summary row with its weekly series (3.1): the series id and the date of the series it stands for. */
export type PlanMeeting = MeetingInfo & { series_id?: string; series_date?: string };

/** The meeting view as the planner reads it: the rows with their marks and, per list, "urgency" or "hand" (arranged by hand). */
export type PlanState = Omit<MeetingState, "meeting" | "agenda"> & {
  meeting: PlanMeeting;
  agenda: { discussion: PlanRow[]; noting: PlanRow[]; not_ready: PlanRow[] };
  agenda_order?: Partial<Record<ListKey, "urgency" | "hand">>;
};

/** One weekly series (meetings.series_row). weekday: 0 = Monday .. 6 = Sunday. */
export interface Series {
  id: string;
  title?: string;
  weekday: number;
  weekday_name?: string;
  time: string;
  room?: string;
  video?: boolean;
  minutes_per_case?: number;
  active?: boolean;
  paused?: { by?: string; at?: string } | null;
  stopped?: { by?: string; at?: string } | null;
  status: "active" | "paused" | "stopped" | string;
  /** "Every week on Friday at 10:00" */
  label: string;
  /** Its meetings dated today or later (cancelled ones too). */
  meetings?: PlanMeeting[];
}

export interface SeriesList { series: Series[]; weekdays?: string[] }

export interface NewSeries { title?: string; weekday: number; time: string; room?: string; video?: boolean; minutes_per_case?: number }
