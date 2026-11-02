# 07: Phase 5 spec (the recorder that keeps no audio, the AI notes, the summary after the board)

Written 2 Nov 2026 from the owner's decisions D11 to D14 and T3, T4 (PLAN.md section 2). Rules: NO AUDIO EVER TOUCHES THE DISK; only
text is kept; every note line carries the exact spoken words behind it; the notes summarise what people said and never decide or
advise in Vaidyx's own voice; labelled "AI draft, not reviewed"; readable by the meeting's members; the transcript itself is never
served as a whole.

## 5.1 Backend: recording state, chunks, transcript (new module `tumour_board/meeting_notes.py`, router `tumour_board/api/meeting_notes.py`)
- Recording state kept in the meeting record: `recording = {state: off|on|paused, by, started_at, paused_at, stopped_at, chunks}`.
  `POST /meetings/{mid}/recording {action: start|pause|resume|stop}`: the MDT Coordinator only (`session`), in session only; audited
  (`recording_started`, `_paused`, `_resumed`, `_stopped`); a socket event `{"type": "recording", "recording": {...}}`; the meeting
  view carries it. Ending the meeting stops it.
- `POST /meetings/{mid}/transcribe` (multipart: `audio` one chunk of at most 4 MiB and 60 s, `speaker` = a login of the meeting or
  `room`, `started_ms` the client's time of the chunk's start): the coordinator only, recording `on` only; rate limited (about 30 a
  minute); the bytes are passed in memory to the audio service's `/stt` exactly as `tumour_board/audio_proxy.py` does for dictation
  (read it; English, the token from `data/tumour_board/audio_token.json` read in code) and dropped; an empty or failed transcription
  stores nothing. A segment `{id, at, started_ms, speaker, speaker_name, case_id (the case on the floor when it arrived), text}` is
  appended to the meeting's transcript file (one JSON line each, mode 600, next to the meeting's own file). Audited without the text.
- Nothing serves the transcript as a whole. One segment's words are served only as the "said" of a note line (5.3), to a member.

## 5.3 Backend: the AI notes per case
- `build_notes(mid, case_id)`: the segments of that case, in order, with speaker names, go to the reasoner (Gemma-4-31B, non-medical)
  asking for short lines of what was said and asked ("Radiology noted ...", "The board asked Pathology to ..."), each line with
  `{text, segment_id, quote}` where `quote` is copied word for word from that segment. Each line is checked: the segment exists for
  that case and `quote` is in its text (whitespace and case relaxed only); a line that fails is dropped and counted. The existing
  advice guardrail runs on the line's own words outside its quote (tumour_board/guardrails.py): Vaidyx never advises in its own voice;
  what a doctor said stays attributed to them. No numbers that are not in the quote.
- Stored per case in the meeting record: `notes[case_id] = {lines: [{id, text, said: {segment_id, speaker_name, at, quote}}], model,
  generated_at, dropped, review: {status: draft|reviewed, by, at}, edits: [...]}`. The coordinator may edit a line (kept as edited by
  them, the "said" stays) and mark the notes reviewed; audited.
- Built when a case is ended (`cases/{cid}/end`) and when the meeting ends, in the background (one at a time per meeting); and on
  demand `POST /meetings/{mid}/cases/{cid}/notes/build` (coordinator). `GET /meetings/{mid}/notes` (every member of that meeting,
  never an outside expert without consent, never someone not admitted) returns every case's notes with the "said" words; the Case File
  shows its own notes to whoever may read the Case File fully: `GET /cases/{case_id}/meeting-notes`.

## 5.2 Frontend: the Record button and the capture
- The coordinator's top bar: Record (start), then Pause / Resume and Stop; a red "Recording: text only, no audio kept" badge on every
  screen while on; the join page says "This meeting is being recorded as text (no audio is kept)" while on.
- Capture in the coordinator's browser (the laptop is in the room and in the call): with the video call connected, one MediaRecorder per
  audio track: the laptop's microphone is `room`, each remote member's track is that member; without video, the laptop microphone only.
  Chunks of about 20 s (`timeslice`), posted to `/transcribe` with the speaker; failures shown quietly; the tab closing posts `stop`
  (keepalive). Never stored in the browser either.

## 5.4 The summary after the board
The Case summary (tumour_board/case_summary.py) is labelled "Summary after the board" next to "Summary before the board", and takes the
meeting notes as a source: a new citation kind for a note line (shown as "Board discussion DD/MM/YYYY", its quote on hover). The
meeting PDF (4.1) adds "Discussion notes (AI draft, not reviewed)" per case at its hook.

## 5.5 Evaluation
Kokoro on :7120 reads a scripted synthetic board discussion as WAV files; two browsers (the coordinator as `room`, a member as a remote
track) with Chromium's fake microphones play them in a test meeting; the transcript segments and the notes are checked: speakers right,
every note line verified, no advice in Vaidyx's own voice, nothing on disk but text (check the meeting folder for any audio file).
