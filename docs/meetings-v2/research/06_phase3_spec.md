# 06: Phase 3 spec (planning: weekly series, the agenda that fills itself, one-page planner, unplanned cases)

Written 2 Nov 2026 from the owner's decisions D7 to D9 and T6 (PLAN.md section 2) and the API check's notes (research/02).

## 3.1 Weekly series (T6)
- A series: `{id, title, weekday (0 = Monday .. 6), time "HH:MM", room, video, minutes_per_case, active, created_by, created_at,
  updated_at}` kept with the meetings data (one JSON file, written atomically under the meetings lock). Coordinator only (`session`).
- Routes: `GET /meeting-series`, `POST /meeting-series {title?, weekday, time, room?, video?, minutes_per_case?}`,
  `PUT /meeting-series/{id}` (the same fields; changes the future planned meetings of the series that were not moved by hand),
  `POST /meeting-series/{id}/pause` and `/resume`, `POST /meeting-series/{id}/stop` (no new meetings; future planned meetings with an
  empty agenda are cancelled with the reason "series stopped"; those with cases stay and are listed in the answer).
- The meetings of a series are ordinary meetings with `series_id` and `series_date`. A job makes the next four weeks (today included
  when the time has not passed) on create, edit, resume and every day from the scheduler; never twice for one date; never again for a
  date whose meeting was cancelled or moved (skip or move one date = cancel or reschedule that meeting as today). An extra one-off
  meeting is created as now, with no `series_id`.
- Audited like meetings (`series_created`, `series_updated`, `series_paused`, `series_resumed`, `series_stopped`). Tests for every rule.

## 3.2 The agenda fills itself (D8) and the API check's leftovers
- A Case File sent to the board without a meeting chosen goes on the next planned meeting (the earliest planned, not cancelled, today
  or later, not past its time) for the list chosen; when there is none, it waits (as today) and joins the first meeting made later
  (create, or a series job). The coordinator is told as today; the treating doctor's answer says which meeting.
- The order of a list: urgency (5 first), then the time it was sent. Once the coordinator reorders a list by hand (PUT agenda), the
  list keeps that order and new Case Files are added at its end (marked new for the coordinator).
- Cancelling a meeting moves its listed Case Files to the next planned meeting (or back to waiting when there is none); each owner is
  told (API check note 8).
- A Case File moved by "Not discussed" keeps a ready mark, so its owner and the coordinator can move or withdraw it (note 9).
- Tests for each rule, including a reorder by hand followed by a new send.

## 3.3 The one-page planner (D9), frontend
Replaces the New meeting dialog and the agenda page for the coordinator (members keep a read view): when and where at the top (edit in
place: date, time, room; "Every week on Friday" when it belongs to a series, with "Change the series"), the case list below (For
discussion, For noting) with drag to reorder (and keyboard Up and Down), Move to another meeting, Remove with a reason, Add a Case File;
members (the board heads and the case teams) and the join code made by themselves and shown; one Send agenda; one Start meeting; More:
minutes per case, video, cancel this meeting. The Meetings page: "Plan a Tumour Board" with Once (date and time) or Every week
(weekday and time), then the planner opens. Light theme, laptop and phone, plain words.

## 3.4 Take up another Case File during the meeting (D7), frontend
The backend already takes a Case File not on the agenda during the meeting (agenda add while in session, then `current`; the API check
proved it). The coordinator's screen gets "Take up another Case File": a search over the Case Files the coordinator may list (name,
UHID, cancer), added as "taken up during the meeting" and put on the floor; the minutes say so.
