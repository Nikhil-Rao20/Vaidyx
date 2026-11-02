# The specialty agents in the meeting (research for Phase 6)

Item 0.6 of docs/night-v3/PLAN.md. Written 27 Oct 2026. Read-only research: no code was changed. Models are named as the project names them: the reasoner is Gemma-4-31B (non-medical), the reader is Qwen3.5-4B (Chinese, non-medical). No accuracy or validation claim is made anywhere in this note.

Sources inside the repository are cited as file:line. Web sources are listed with their URLs in the tables and in the notes below. Web figures from vendor blogs are marked as such.

## 1. Summary

1. Today one stand-in agent exists per meeting. The backend already accepts a `role` on a question (tumour_board/meetings.py:1012, tumour_board/api/meetings.py:229) but the website never sends it (web/tb-nik/src/features/meetings/api.ts:33), and `agent_state` picks only the first absent head (meetings.py:432).
2. The briefs of all absent agents are already prepared at the start for every Case File on the agenda and are kept inside the meeting record (service.py:553-575, board.py:811-816). Only the live tile state is memory-only (meetings.py:44).
3. The live answer path is a single non-streamed JSON call to the reasoner, 1.6 to 4.2 s for the whole answer (00_current_state.md:64). Streaming statement by statement is feasible without breaking the quote rule, because each statement is verified on its own.
4. Two states shown today are not true: "Reading the question" lasts for one event loop turn (meetings.py:1034-1036) and there is one shared state per meeting, so two questions to two agents overwrite each other (meetings.py:995).
5. The three big products (Zoom AI Companion, Teams Copilot, Gemini in Meet) all use a side panel, tell everyone the AI is on, cite the transcript, and leave control with the host. None of them speaks aloud in the call. The spoken, named, in-the-grid agent is the Vaidyx idea, so the labelling has to be stronger than theirs.
6. Turn-taking recommendation: push to talk on the asker's own device, text shown and editable before sending, "listening" shown only while that device is capturing speech for that agent. No open microphone and no LiveKit agent participant in Phase 6.
7. Speaking recommendation: option (a). The app broadcasts the answer, each device fetches the audio from `/api/tb/audio/tts` sentence by sentence and plays it, the room screen included. Members who joined in the room (`mode: "room"`) start with agent voices muted on their own device, because they hear the room screen.
8. The first words can reach about 4 to 6 s after "Send" by streaming statements from the reasoner, holding the first one only until the scope check has passed, and sending it to Kokoro at once (first audio about 70 ms on the GPU, audio_feature.md:145).
9. Agent quality needs work: Medical Oncology, Surgical Oncology and Radiation Oncology search the very same guideline sources (specialty_packs.json), and only Radiology and Pathology have reporting checklists. A 40-question set per role (240 questions) with three labels (grounded, no advice, correct refusal) is proposed in section 7.
10. Eleven open questions for the owner are in section 9. The main ones: the in-room default mute, whether an agent may speak without being asked ("Present your points"), and whether a short audio cache in memory is allowed under "audio never stored".

## 2. Today: how an agent is prepared, asked and answered

### 2.1 Preparation (the brief)

1. A meeting starts: `meetings.start` (meetings.py:821) calls `board.start`, then `service.prepare_session_agents(mid, by)` (meetings.py:837).
2. `prepare_session_agents` (service.py:553-575) takes every Case File on the agenda and every role from `board.absent_roles(session, case_id)` and runs `_prepare_one` for each pair in parallel; the reasoner's queue spaces the model calls. Each pair is marked `queued` (board.set_agent, board.py:811).
3. `board.absent_roles` (board.py:607-621): a role is active when its department is marked "absent", or when it is a board head and not marked "present". Surgical Oncology is dropped when a surgeon fills the seat for that Case File (board.py:616-619). The heads default to five: Radiology, Medical Oncology, Surgical Oncology, Pathology, Radiation Oncology (board.py:46); `ON_DEMAND` is Radiation Oncology and Nuclear Medicine (board.py:31). Under the default heads Radiation Oncology is therefore already a head; only Nuclear Medicine is truly on demand.
4. `agents.run_agent` (agents.py:444-610) is the ReAct loop, up to 5 steps, read-only tools (agents.py:67-78): list_documents, read_document, search, find_values, get_facts, get_gaps, search_guidelines, finish. It writes the brief with verified quotes and stores it as `state.artefacts.brief_<role>` (agents.py:600-603). A Case File with no documents of the specialty returns at once without a model call (agents.py:458-462). A brief is reused only when `agents.fresh` holds (agents.py:627-634).
5. The session keeps the status per Case File and role in `session["agents"][case_id][role]` (board.py:816): queued, running, ready, no_documents, error (board.py:36). This is saved with the meeting.

Role definitions: six roles with focus text and `doc_types` (agents.py:17-43), plus a skill file per role (tumour_board/skills/<role>/SKILL.md, 25 to 30 lines each) loaded by `agents.spec` (agents.py:47-59). The hard rules are in `_system` (agents.py:112-124) and never come from the skill.

### 2.2 Asking in a meeting

1. A member opens the Questions panel and types a question (MemberViewPage.tsx:185-195). The call is `askQuestion(mid, text)` with no role (meetings/api.ts:33). The coordinator's ControlView has a Questions tab that only lists (ControlView.tsx:199), so the coordinator cannot ask.
2. `POST /meetings/{mid}/questions` (api/meetings.py:226-233) calls `meetings.ask` (meetings.py:999-1018). It builds the question record, and when `agent_state` is active it sets `q["role"]` to the role asked if that role is in the active list, otherwise to the first one (meetings.py:1010-1013). Then it saves, audits (`question`) and broadcasts `question`.
3. The route starts `answer_in_background` when `q["role"]` is set (api/meetings.py:230-231).

### 2.3 Answering

`meetings.answer` (meetings.py:1021-1064):
1. One answer per question, guarded by `_ANSWERING` (meetings.py:1028-1030).
2. States: `reading_question`, then `await asyncio.sleep(0)`, then `thinking` (meetings.py:1034-1036), then `agents.ask(cid, role, text, None, user)` with history `None` (meetings.py:1038), then `answering` (meetings.py:1039), then in the `finally` block `ready` (meetings.py:1063).
3. The answer record: status, joined statement text, statements with citations, references, label, model, time, and the note "From the records only; the agent is not a member of the board" (meetings.py:1040-1043).
4. `board.log_answer` writes an "answer" entry into the session log with the question, statements, references, `asked_by` and the removed statements (board.py:866-883). The question record keeps the answer (meetings.py:1056-1059) and broadcasts it.

`agents.ask` (agents.py:654-716), step by step:
1. Unknown role raises; no protocol returns `not_listed` with the message "This Case File is not listed yet: list it before preparing a brief" (agents.py:62, 665-666).
2. Audit `agent_question` (agents.py:667).
3. `guardrails.rule_check` (regex rules, guardrails.py:17-27) and, in parallel, `guardrails.check_input` (rules then a reasoner classifier, guardrails.py:51-67). A rule hit returns `out_of_scope` at once with no retrieval (agents.py:670-674). If the classifier is unreachable the question is allowed (guardrails.py:66, fail open; the output scan below is the second layer).
4. Context: `search.find_values` and `search.context_for(case_id, question, 40000)` (agents.py:675-679). The whole Case File when it fits, otherwise whole documents in relevance order and the best passages (search.py:198-225). Matching lines are appended.
5. Guideline passages: `_search_guidelines` goes to `packs.search(role, question, protocol)`, 3 Indian and 2 international passages from this role's pack, each given an id G1, G2 ... (agents.py:285-294, packs.py:155-159); skipped when the guideline index is not ready (agents.py:682).
6. The prompt: `_live_system(role)` (agents.py:644-651), up to 4 history messages of 2,000 characters (agents.py:693-695), then "DOCUMENTS ... QUESTION FROM THE BOARD" (agents.py:696).
7. One `llm.chat("reasoner", ..., json_schema=LIVE_SCHEMA, max_tokens=1200)` (agents.py:697). The schema is `answer_found`, `statements[{text, citations[{doc_id, quote}]}]`, `references[{ref_id, quote}]` (agents.py:638-642, qa.py:12-21).
8. If the scope check fails, the answer call is cancelled and `out_of_scope` is returned with the category's refusal text (agents.py:698-702).
9. `qa.verify` keeps only statements whose quotes are found exactly in the Case File (agents.py:704; exact only, no near match, qa.py:150-206). Each kept statement goes through `guardrails.scan_output` (agents.py:707-713; prescriptive wording, stage patterns). References are verified verbatim and kept only beside a verified answer (agents.py:716, 307-325).
10. Status: `answered` when at least one statement survives, otherwise `not_documented` with "Not documented in the Case File. No statement could be verified against the source documents." (agents.py:719-723). The four statuses of the plan's task are answered, not_documented, out_of_scope, not_listed; the meeting adds a fifth, `error` (meetings.py:1050).
11. Audit `agent_answer` (counts, seconds).

Refusal wording today (guardrails.py:29-36): treatment: "I can't recommend or choose treatment. Treatment decisions belong to the Tumour Board. I can show what the signed records document, list pending results, and surface the relevant guideline sections for the board to review."; diagnosis, scan interpretation, stage and prognosis have their own sentences that offer what is recorded instead.

Which guideline sources each role searches (tumour_board/protocols/specialty_packs.json, read by folder):
| Role | Folders | Reporting checklists |
|---|---|---|
| Radiology | iria, ncg_india (the synoptic radiology template only), acr_appropriateness, acr_rads, rcr, recist | lung, breast, rectum, oral cavity, cervix |
| Pathology | ncg_india, icmr, tmc, cap_protocols, rcpath, iccr, asco_cap | lung, breast, rectum, oral cavity |
| Medical Oncology | ncg_india, icmr, tmc, pmjay, esmo, nice | none |
| Surgical Oncology | the same six as Medical Oncology | none |
| Radiation Oncology | the same six as Medical Oncology | none |
| Nuclear Medicine | ncg_india, iria, acr_appropriateness | none |

### 2.4 The Case File side (the six "records checks")

`helpers.py`: six cards "<Department> records check" (helpers.py:26-27). `list_helpers` returns brief status, thread count, whether preparing or queued at the ready mark (helpers.py:62-82). `ask` (helpers.py:171-199) keeps the last two exchanges as history (helpers.py:179-183), calls `agents.ask`, saves the message to `cases/<id>/helper_chats.json` (cap 200 messages per role, helpers.py:20, 190-196), audits `helper_asked`. The page is HelpersPanel.tsx (casefile/components): a card list with "brief ready / preparing / stale" chips and a detail view with the brief, "Points for review", "Not documented" and the "Ask the <name> helper" box (HelpersPanel.tsx:48-216).

### 2.5 Data kept

| Where | What | Survives restart |
|---|---|---|
| `state.artefacts.brief_<role>` in the Case File | the brief, signature, review status | yes |
| session `agents[case][role]` | brief status per Case File and role | yes |
| session `questions[]` | question, asker, role, answer record | yes |
| session `log[]` (board.log_answer) | "answer" entries with statements, references, removed statements | yes |
| `cases/<id>/helper_chats.json` | the Case File's agent thread | yes |
| `AGENT_STATE[mid]` (meetings.py:44) | the live tile state | no (popped at the end, meetings.py:862, 880) |
| Case File and session audit | `agent_question`, `agent_answer`, `question`, `question_answered`, `answer_logged`, `helper_asked` | yes |

### 2.6 States broadcast and UI places

Broadcast: WebSocket event `agent_state` with `{active, role, state, question}` (meetings.py:995-996) and the `agent` block inside `meeting`, `admit` and `current` events (meetings.py:470, 787, 841). The front end maps ready, reading_question, thinking, answering to the words "Ready", "Reading the question", "Thinking", "Answering" (shared.tsx:85-91).

UI places: AgentTile (shared.tsx:94-120), shown in the coordinator's People tab only (ControlView.tsx:196), in the members' tile column (MemberViewPage.tsx:178) and in the room screen's side column (MeetingRoomPage.tsx:106). It reads "Stand-in: <label>" and "AI support: answers from the records only; not a member of the board." QuestionsList (shared.tsx:130-200) shows the question, "<name>, to the <label> stand-in", the statements with a chip of document title and page, and the line "From the records only; the stand-in is not a member of the board." It does not show references or the time taken. While waiting it shows "The stand-in is reading the records".

### 2.7 The gaps of 00_current_state.md section 2, confirmed or corrected

| Gap in 00_current_state.md | Verdict | Evidence |
|---|---|---|
| The agent is not a participant in the grid | Confirmed | AgentTile is a separate card outside TileGrid (MemberViewPage.tsx:177-178) |
| Only one stand-in per case | Confirmed | `role = head_roles[0]` (meetings.py:432); `head_roles` also drops any absent role that is not a head, so an absent Nuclear Medicine never gets a tile (meetings.py:428-430) |
| Points are not shown from the start | Confirmed | briefs are in the session (board.py:816) but no component renders them in a meeting |
| Text only | Confirmed | no audio routes exist yet (Phase 4 is todo) |
| Meeting thread and Case File thread are separate | Confirmed | meeting answers go to session log and questions (meetings.py:1041-1059); Case File answers go to helper_chats.json (helpers.py:190-196); the meeting passes no history (meetings.py:1038) |
| The coordinator cannot ask | Confirmed | ControlView has the Questions list only (ControlView.tsx:199); the route allows any member including the coordinator (api/meetings.py:227-229 `_member`) |
| References and time are not shown | Confirmed | QuestionsList renders statements and chips only (shared.tsx:130-200); the answer record does carry `references` and `seconds` (meetings.py:1040-1043) |
| "Members ask through the Questions panel with no role" | Corrected: the backend already takes a role | meetings.ask `role if role in ag.roles` (meetings.py:1012); route passes `b.get("role")` (api/meetings.py:229). Only the website's `askQuestion` lacks it |
| "Agent state is kept in memory only" | Partly corrected | the briefs and statuses are saved with the meeting (board.py:816); only the live tile state is memory-only |
| Found now: "reading the question" is not a true state | New | set and replaced within one loop turn (meetings.py:1034-1036) |
| Found now: one state per meeting, not per agent | New | `AGENT_STATE[mid]` (meetings.py:995); and each finishing answer sets `ready` for the whole meeting (meetings.py:1063) even if another answer is running |
| Found now: the answering state is set after the answer exists | New | `answering` follows `agents.ask` (meetings.py:1039); for a spoken answer "speaking" must mean audio is playing |
| Found now: question length limits differ | New | server 1,000 (meetings.py:37), member box 500 (MemberViewPage.tsx:190) |
| Found now: the eval measures briefs, not live answers for refusals | New | agent_refs_eval.py counts Indian references on briefs (agent_refs_eval.py:1-10, 43-54); qa_eval.py probes are for the Case File Q&A, not per role (qa_eval.py:1-20) |

## 3. Patterns from Zoom, Teams and Meet

| Pattern | Product | What we take | URL |
|---|---|---|---|
| Questions go into a side panel so nobody interrupts the speaker | Zoom AI Companion in-meeting questions | The agent is asked from a panel or a tile, text first, without stopping the meeting | https://library.zoom.com/zoom-workplace/artificial-intelligence/artificial-intelligence-bluepaper/ai-companion/ai-companion-features/zoom-meetings |
| Suggested questions plus free typing | Zoom (panel), Teams Copilot ("More prompts") | Suggested questions per role on the tile ("Present your points", "What is pending in your reports?") | https://uis.georgetown.edu/?p=19921 ; https://support.microsoft.com/en-US/teams/meetings-events/welcome-to-copilot-in-microsoft-teams |
| Answers carry timestamped citations from the transcript | Zoom, Teams | Every sentence carries chips to a document, page and the exact quote; ours point to records, theirs to a transcript | https://support.microsoft.com/en-us/copilot-teams |
| The host controls whether and from when participants may ask | Zoom | The coordinator adds or removes each agent and may switch off asking (a "pause questions" switch) | https://services.css.edu/TDClient/354/Portal/KB/ArticleDet?ID=20117 |
| Everyone is told when the AI is on | Zoom, Teams (a transcription notice to all), Meet (a notice and a pencil icon for all) | A banner at the start of the case and a permanent label on each tile: "AI agent, support only" | https://support.google.com/meet/answer/14754724 |
| Catch-up for late joiners ("Summary so far", a catch-up offer after 5 minutes late) | Meet, Teams | A late joiner can tap "Present your points" quietly (text only) or read the brief points | https://support.google.com/meet/answer/14754724 ; https://support.microsoft.com/en-us/copilot-teams |
| Admin and host can turn the feature off; internal participants can stop it | Meet, Teams | Coordinator removes an agent; any member may mute agent voices for themselves | https://support.google.com/meet/answer/14754724 |
| Honest limits stated: notes can be incomplete or inaccurate | Meet | A fixed line under each answer: "From the records and guidelines only. Check the source." No accuracy claim | https://support.google.com/meet/answer/14754724 |
| Reads the transcript or the meeting chat, and only what the meeting held | Teams | The agent reads only this Case File and its own pack, never the call audio. It does not listen to the discussion (say so on the tile) | https://support.microsoft.com/en-us/copilot-teams |
| AI answers are not spoken into the call | Zoom, Teams, Meet (all three show text in a panel or a document) | The spoken agent is new ground; the voice must be muted per person, announced and stoppable | the same pages |

What the three products never do: they do not give the AI a seat, a name or a department in the participant grid, they do not speak in the call, and none claims to stand in for an absent person. The honesty cost of the tile idea is on us: the name must say "AI agent standing in", never the specialist's title alone.

Note on sources: Zoom's own bluepaper was reached only through search results; most Zoom detail comes from university help pages that repeat it. The Google page was read directly. Teams detail is from Microsoft's support pages in the search result.

## 4. Voice turn-taking

### 4.1 What the engineering sources say

- LiveKit Agents: the agent code registers as an agent server, a job joins the room as a participant and talks over WebRTC (https://docs.livekit.io/agents/). Turn detection modes are: a turn-detector model (default) layered on VAD, VAD only for minimal latency, STT endpointing, realtime-model server detection, and manual or push to talk where the app calls `interrupt()`, `clear_user_turn()` and `commit_user_turn()` from a talk button (https://docs.livekit.io/agents/build/turns/). Interruptions pause the agent when user speech is detected, and the history is cut to what the user actually heard (same page).
- LiveKit states: agent `initializing`, `idle`, `listening`, `thinking`, `speaking`, exposed to the front end as the `lk.agent.state` attribute on the agent participant; user states `speaking`, `listening`, `away` come from VAD (https://docs.livekit.io/agents/build/events/). A state label there comes from the pipeline itself, which is the point: it is true by construction.
- Human conversation: the median gap between turns is about 200 ms (Stivers et al., PNAS 2009; reached through blog summaries, to be checked against the paper). Voice-product guides put "feels natural" at under 500 to 800 ms and "wrong" above one second, and warn that tail latency (p95, p99) matters more than the average (https://picovoice.ai/guide/voice-agents/voice-ux-latency-turn-taking/ ; https://www.twig.so/blog/voice-ai-agents-latency-budget-800ms ; https://dasha.ai/blog/voice-ai-latency). These are vendor numbers for phone agents with no document reading and are not our target. Our colleague is answering a question about a file: a few seconds is natural.
- Confirming what was heard: Google's conversation design guidance prefers implicit confirmation (the reply repeats the key parts), reserves explicit confirmation for costly misunderstandings, and says the point of confirming is to show the user how the input was understood so errors are fixed fast (https://developers.google.com/assistant/conversation-design/confirmations). For us a mis-heard drug name, number or date is costly, and D1 already says speech fills an editable box, so the text is always shown and editable before it is sent. That is explicit confirmation by construction.

### 4.2 The options

| Option | How it works | Latency added | True "listening"? | Fits D1 and D2? | Cost |
|---|---|---|---|---|---|
| A. Push to talk on the asker's device (recommended) | Tap the mic on the agent's tile or in the question box; the browser records up to 60 s; stop; `/api/tb/audio/stt` returns text into the editable box; the person edits and sends | faster-whisper large-v3-turbo about 0.2 s per utterance (00_current_state.md:136) plus the tap; WER 0.079 on clinical sentences in the October test (same line) | Yes: the device is capturing audio for that agent exactly while the button is held or toggled | Yes: STT only fills an editable box (D1); "listening" only while a question is being spoken to it (D2) | MicButton is already planned (plan 4.3); one new broadcast event |
| B. Open microphone with VAD in the app | The browser listens all the time and cuts utterances by VAD | VAD under 1 ms per chunk (audio_feature.md:95); end-of-turn wait adds 0.4 to 0.8 s | No: the microphone is open when nobody is asking; picks up the room and other people | No: it hears the discussion; violates "listening only while a question is being spoken to it" and the privacy of a patient case | Echo, false triggers in a room with several people |
| C. A LiveKit agent participant (STT, reasoner, TTS pipeline in the room) | A worker joins the room, listens to the room's audio tracks with VAD and a turn model, answers by publishing a track | 0.3 to 0.8 s turn detection plus pipeline | Only if the pipeline is limited to the asker's track; the framework's "listening" is true for the agent's pipeline but the agent is subscribed to all audio | Partly: it needs a gate that opens only when a person asks; and our answer path is the grounded, quote-verified `agents.ask`, which is not a plain chat completion | The LiveKit agents SDK is not in the app environment (no livekit package found in /data/vaidyx/venv/app; video.py mints tokens by hand, video.py:1-14); a worker per meeting; the cited-statement pipeline must be wrapped; the Phase 4 audio service would be called by the worker |

### 4.3 Recommendation

Option A for Phase 6, exactly:
1. The asker taps the microphone on an agent's tile. The device sends `agent_listening: {role, on: true}` and starts recording. The server sets that agent's state to `listening` with the asker's name and a hard expiry of 60 s (the clip limit of plan item 4.1), so a closed tab never leaves a false state.
2. The asker taps stop (or presses Esc to cancel). The audio goes to `/api/tb/audio/stt`; the text appears in the question box under the tile, editable. The state returns to `ready` as soon as recording stops, not when the text arrives.
3. The asker reads, edits and presses "Ask". Only now does the question go to the agent: `thinking`, `speaking`, `ready`.
4. Barge-in is a tap, not a voice: "Stop" on the speaking agent stops the audio on that device (local) and, for the coordinator, for the room (a broadcast `agent_stop`, the answer text stays). Speech is split into sentences, so stopping leaves the unspoken sentences as text.
5. A second question to an agent that is speaking waits in a queue of one per agent; it does not interrupt the first answer.
6. Later (not Phase 6): option C can be built by an optional worker that only joins a room on the coordinator's request, once Phase 5 is stable. Nothing in A prevents it, because the question and answer events do not depend on how the text was typed.

Confirmation of what was heard: the transcribed text appears in the box with a short line "Heard this. Check it before asking." Numbers, units and dates are plain text so the asker can correct them.

## 5. Speaking the answer

The plan says answers are "spoken aloud by default (on the room screen and in the call)", muted per person. Kokoro-82M is the planned engine, first audio 63 to 78 ms on the H200, 1.0 to 3.3 s on the CPU fallback, sentence by sentence (audio_feature.md:145-146). `/api/tb/audio/tts` is Phase 4 item 4.2, not built yet.

| | (a) Each device fetches the audio and plays it | (b) A server-side LiveKit participant publishes the audio | (c) Both |
|---|---|---|---|
| How | The app broadcasts the answer as sentence events; each device (and the room screen) calls `/api/tb/audio/tts` per sentence and plays it | A worker joins the room as "Radiology, AI agent" and publishes an audio track; devices hear it through the call; mute means turning that participant's audio off on that device | The tile voice through (b), and (a) as a fallback |
| Latency | First sentence about 100 ms for TTS plus the request; every device renders on its own | One render, published once; plus WebRTC about 100 to 300 ms | Worst of both |
| Sync across devices | Each device starts when its own event arrives (skew in the order of hundreds of ms); in one physical room an echo is possible | Everyone hears the same stream at nearly the same time | |
| Simplicity | Uses the existing app proxy and the existing WebSocket; works when LiveKit is down; no new service | Needs the LiveKit server SDK in an environment, a worker per meeting, token and permission handling, and the audio service reached by a second client | Highest |
| Members on the phone | They hear it if the page is open on that phone (a dial-in by telephone is not set up here) | They hear it if they are in the call | |
| Per-person mute | A local switch, plus a setting kept in the browser | Local unsubscribe of one participant | |
| In the recording | The app does not record the call (00_current_state.md:103: recording not used); a recording of the room screen or of the room's microphone would hold what the speaker played | Any later call recording would hold the agent's voice as its own track, which is clean and attributable | |
| Audit | The answer is already logged as text (board.log_answer); the spoken text equals the logged text | Same | |
| Risk | Echo when a member sits in the room next to the room screen and their own device also plays | Agent dies with the worker; more moving parts in a live clinical meeting | |

Recommendation: (a) for Phase 6.
1. Play-out rules: sentence events `agent_speech: {answer_id, index, text}` go to every device. The audio is fetched per sentence when the device is not muted, and played in order. A device that has agent voices muted never fetches, so there is no extra load.
2. Echo rule: a member admitted in the room (`mode: "room"`, meetings.py:762) starts with agent voices muted on their own device; remote members start with them on (the plan's "on the room screen and in the call"). One switch "Agent voices" on every device. This default needs the owner's yes (section 9).
3. Same text as screen: only the answer's statements as shown (D1: text to speech only reads text on screen or a grounded agent answer). References are not read aloud; the voice says "Sources are on the screen." once per answer.
4. The `agent_stop` for the coordinator.
5. If a TTS call fails, the answer is still shown as text and the tile shows "Voice unavailable, text only", never "speaking".
6. Reconsider (b) after Phase 5 if the owner reports echo or skew in real rooms. The sentence event stream is the same input to a worker, so (a) does not close the door.

Open point: a short in-memory cache of rendered sentences (two minutes, keyed by answer id and index) would let every device fetch identical audio without N renders. It is memory only and is deleted at once, but it should be agreed because the invariant says audio is never stored (section 9).

## 6. The proposed behaviour (within D2)

### 6.1 The agent tile

One tile per active agent, placed in the same participant strip or grid as people (Phase 5 TileGrid), with a different frame (dashed outline) so it is never mistaken for a person.

- The mark: the Vaidyx agent mark (the existing Bot icon is a placeholder, shared.tsx:104-106).
- Title line: "Radiology, AI agent standing in" (the department's name, then ", AI agent standing in"). For an agent called to a meeting although the head is present: "Radiology, AI agent, called by the coordinator".
- Permanent label under it: "AI agent, support only".
- Second line, always visible: "Reads this Case File and the guidelines. Does not decide or advise. Not a member of the board."
- The state word (section 6.3) and a count: "4 points from the records".
- The brief's points: shown from the start. The tile opens a short list (up to 5) of the brief's "Points for review" and "Not documented" items (HelpersPanel's data, brief_view in helpers.py:35-50) with their chips. Label of the list: "Points from the records, AI draft, not reviewed" until a doctor marks the brief reviewed (helpers.py:47). While a brief is still preparing: "Reading the records for Radiology" (existing text, HelpersPanel.tsx:140). With no documents: "No Radiology reports in this Case File" (agents.no_documents_brief, agents.py:421).
- Buttons: "Present your points", "Ask" (opens the question box under the tile), a microphone, "Stop" while speaking. The coordinator also sees "Remove from this meeting".

### 6.2 Who can ask and how

- Any admitted member and the coordinator (the route's `_member`, api/meetings.py:229). Not the people on the waiting list.
- Three ways to the same endpoint: click the tile and type or speak into its box; type "@Radiology" at the start of any text in the meeting's Questions panel (the panel parses the mention against the active agents' names and pre-selects the role); the microphone on the tile.
- The request carries `role` (this is the one front end change needed, meetings/api.ts:33). With no role and exactly one active agent the route may keep the current default; with more than one the box asks "Which agent?" and shows the active ones as chips. A question to an agent that is not active in this meeting is refused with "That agent is not in this meeting. The coordinator can add it."
- One question at a time per agent; a second asker sees "Radiology is answering <name>. Yours is next."
- Questions are visible to everybody in the Questions panel with the asker's name (as today) so the room knows who asked what.
- A switch for the coordinator: "Members can ask the agents: on / off" (like Zoom's host control, section 3).

### 6.3 The states and their exact triggers

State is kept per agent (not per meeting) and broadcast as `agent_state: {role, state, by, question, at}`. A state is shown only when its trigger is true; an expiry exists for every state that depends on a client.

| State | Word on the tile | Trigger to enter | Trigger to leave |
|---|---|---|---|
| preparing | "Reading the records" | the brief for this Case File is queued or running (session `agents` status queued or running) | status ready, no_documents or error |
| ready | "Ready" | the brief is ready and nothing else is happening | any trigger below |
| listening | "Listening to <name>" | the asker's device has begun recording a question for this agent (the `agent_listening on` event and the microphone permission granted; the device confirms capture started) | recording stopped, Esc, the clip limit of 60 s, the asker disconnected, or a server timer of 65 s |
| thinking | "Thinking" | the question was sent and accepted (after the scope check began) and no answer text has been produced yet | the first verified statement is ready (go to speaking) or the answer ends (status not_documented, out_of_scope, error) |
| speaking | "Speaking" (when audio plays on at least one device) or "Answering" (text only, voice off everywhere or unavailable) | a statement has passed the scope check, the quote check and the output guard, and its sentence is being shown (and played) | the last sentence has ended on the device that began first, or "Stop" |
| error | "Could not answer, try again" | the model or the audio failed | next question |

"Reading the question" is removed (it was a placeholder state, section 2.7). "Speaking" is only shown while at least one device reports audio playing: each device sends `agent_audio: {answer_id, playing: true/false}`; the server combines them and times them out. If nobody reports audio (voice is muted everywhere), the word is "Answering", so the tile never claims a voice that nobody hears.

### 6.4 The answer

Shown as streamed text under the tile and in the Questions panel; each sentence appears when it has been verified:
1. The statement text, then chips (document title, date, page), a click opens the source with the quote highlighted (the same SourceTarget as HelpersPanel.tsx:161).
2. The statements are short: at most 3 sentences for a simple question; "Say more" asks a follow-up in the same thread.
3. Below the statements, "Guideline references" when present: the reference's source, year, page and the verbatim quote, with the label "Reference text, not about this patient" (agents.py:80-95 rules).
4. A footer: "AI agent, support only. From the records and guidelines only. <seconds> s. Gemma-4-31B, non-medical model."
5. Colleague tone, no new facts in the tone: the spoken sentence is exactly the verified statement, and a deterministic lead-in is added by code, never by the model: "In the report of 12/03/2026: ..." where the date comes from the citation. Example answers (no advice):
   - Q: "What does the CT say about the right hilar node?" A: "The CT chest report of 12/03/2026 records 'right hilar node 1.8 cm in short axis'. Sources are on the screen."
   - Q: "Is the PD-L1 result back?" A: "The pathology report of 04/03/2026 records 'PD-L1: pending'. No later PD-L1 result is in this Case File."
   - Q: "What is the haemoglobin?" A: "The lab report of 10/03/2026 records 'Hb 11.8 g/dL'."
6. Not documented, spoken and shown: "This is not documented in the Case File. I could not find a record line that supports an answer. The board may want to ask the treating team." (the second sentence is a fixed string; the existing message is "Not documented in the Case File. No statement could be verified against the source documents.", agents.py:722; one wording should win, see 6.9.)
7. The refusal for a decision or treatment question, from guardrails.REFUSALS (guardrails.py:30): "I can't recommend or choose treatment. Treatment decisions belong to the Tumour Board. I can show what the signed records document, list pending results, and surface the relevant guideline sections for the board to review." For a stage, diagnosis, image, prognosis question the existing sentences are kept (guardrails.py:31-35). A refusal is spoken as it is. After a refusal the tile offers two quick questions: "What do the records document?" and "What is pending?".
8. A question that looks like a request for a decision phrased gently ("Which one would you pick?", "What would you do?") is a refusal by the same rule. The classifier handles it; the rule list should gain a few patterns (item 6.4 below), because the classifier fails open (guardrails.py:66).
9. The scope reminder at the start of each case: "AI agents are in this meeting for support. They read records and guidelines only. They do not decide or advise."

### 6.5 Memory

- The thread is one per Case File and role, shared by the meeting and the Case File page: meeting answers are also written to `helper_chats.json` through one function (the helper's `ask`'s write block, helpers.py:187-196), with `source: "meeting:<mid>"`. The session log keeps its own entry (board.log_answer) so the meeting record is self-contained.
- Context passed to the model: the last 3 exchanges of that thread (the question and the joined statements), cut to 2,000 characters each, as `agents.ask` already supports up to 4 messages (agents.py:693-695). Today the meeting passes none (meetings.py:1038) and the Case File passes 2 exchanges (helpers.py:179). History serves follow-ups ("and its size?") and is never treated as a fact: every new statement still needs a quote from the records.
- Stale answers: a message keeps the Case File signature (helpers.py:184, 189); history from an older signature is passed only as the question text, not as the answer text, and the tile says "Records changed since this answer" (the existing `stale` flag, helpers.py:158-161).
- The agent does not hear the meeting. It remembers only the questions asked of agents.

### 6.6 Saving

- With the meeting record: the session `questions[]` item with the answer, the session `log[]` entry (board.py:866-883), `question`, `question_answered`, `answer_logged` audits (meetings.py:1008, 1058; board.py:881). New audit kinds: `agent_listening` (start, end, seconds, no audio, no text), `agent_speech` (answer id, sentences played count per device class, never content).
- With the Case File: the agent thread (helper_chats.json), `helper_asked` audit.
- Audio is never saved. A mic click is audited only as a count of seconds.
- The "Present your points" answer is saved as an "answer" entry with the question text "Present your points", and the points spoken are the brief's items, not a new model call.

### 6.7 Adding and removing agents (the coordinator)

- Default: every absent head's agent is active (D2), for each case on the floor. A head's agent leaves the tile list as soon as its head is marked present for that Case File; the tile fades with "Radiology is here: the agent has stepped back" and the brief remains in the record.
- "Agents" panel (a Phase 5 side panel, the same list in the People tab): the six roles as rows with a switch: "In this meeting" on or off, and a note on why it is on ("Head absent", "Added by <coordinator>"). Radiation Oncology and Nuclear Medicine are always in the list, even when the head is not on the attendance sheet (D2: "always Radiation Oncology and Nuclear Medicine"; today attendance_list adds them, board.py:152-153).
- Switching on a role that has no brief for this Case File starts its preparation with the progress words of 6.1. Switching off does not delete the brief or the thread.
- The state is saved in the meeting: add to the session a map `agents_active: {case_id: {role: {on, by, at}}}` (the on-demand additions and removals) and keep the broadcasts as hints only. The existing `s["agents"]` holds brief status and stays. `absent_roles` provides the default and the map overrides it. Audited: `agent_added`, `agent_removed` with who.
- Only the coordinator adds or removes. No agent action creates or grants any account or role (CLAUDE.md invariants).
- Persistence of the live state: on a restart the tile state returns to `ready` (or `preparing` per session status), computed from the saved session, never from memory (`AGENT_STATE` is memory only today).

### 6.8 The quorum rule and labels

- An agent is never a person in `people`, never in `attendance`, never counted for the PM-JAY composition or the quorum. Today this holds because agents exist only as `agent_state` (meetings.py:13, board.py:678). Keep it so: the agent tile is derived at read time, never written into `people`. A unit test asserts the quorum line is the same with and without agents.
- The quorum line (Phase 5.4) shows "Present: 4 of 5 heads. Agents standing in: Radiology, Pathology (not counted)".
- Labels, in plain words and always visible: "AI agent, support only" on the tile; "Radiology, AI agent standing in" as the title; "Past exchange with an AI agent" in the record; "AI agent" before its name in the Questions panel, the decision strip and every export (the board report already marks live answers with `LIVE_LABEL = "AI support (role-specific)"`, agents.py:637, which should become "AI agent, support only" for agent answers).
- The regulatory reading: India first: ICMR's 2023 ethical guidelines on AI in biomedical research and healthcare ask for transparency and human oversight (https://www.icmr.gov.in/ethical-guidelines-for-application-of-artificial-intelligence-in-biomedical-research-and-healthcare); and the Central Drugs Standard Control Organisation (CDSCO) finalised guidance on medical device software in July 2026 (second-hand reports only, to be checked against the document: https://www.emergobyul.com/news/india-cdsco-finalizes-guidance-medical-device-software). Then the international sources: the EU AI Act requires a system meant to interact directly with people to make clear they are dealing with AI, at the latest at first interaction and in a clear and distinguishable way, with reminders where useful (Article 50; the Commission's guidelines are non-binding; see https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act , https://www.mccannfitzgerald.com/knowledge/technology-and-innovation/european-commission-publishes-draft-guidelines-on-transparency-obligations-under-the-eu-ai-act). A voice that speaks aloud in a room makes "obvious AI" harder to claim, so the voice should say who it is: the first sentence after a long silence begins with "AI agent, Radiology:" (a fixed prefix, kept very short). The FDA's clinical decision support criteria expect software to let the clinician independently review the basis of what it says (https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software); the quote chips and the verbatim references are exactly that basis. This keeps to the signed scope declaration: the agent checks, routes, summarises, flags; it does not decide. This note is not legal advice; whether Vaidyx-TB is regulated software is a question for the owner and counsel.

### 6.9 Exact UI strings (no em dashes)

| Place | String |
|---|---|
| Tile title | "Radiology, AI agent standing in" |
| Tile title, added by the coordinator | "Nuclear Medicine, AI agent, called by <name>" |
| Tile label | "AI agent, support only" |
| Tile line | "Reads this Case File and the guidelines. Does not decide or advise. Not a member of the board." |
| States | "Reading the records", "Ready", "Listening to <name>", "Thinking", "Speaking", "Answering", "Could not answer, try again" |
| Buttons | "Present your points", "Ask", "Stop", "Agent voices: on" / "Agent voices: off", "Remove from this meeting", "Add an agent" |
| Question box | placeholder "Ask Radiology about this Case File"; after the microphone: "Heard this. Check it before asking." |
| Mention hint | "Type @ and a department to ask one agent, for example @Radiology" |
| Brief points header | "Points from the records, AI draft, not reviewed" |
| Case start banner | "AI agents in this case: Radiology, Pathology. They read records and guidelines only. They do not decide or advise." |
| Not documented | "This is not documented in the Case File. I could not find a record line that supports an answer." |
| Refusal | the existing sentences of guardrails.REFUSALS (guardrails.py:29-36) |
| Answer footer | "AI agent, support only. From the records and guidelines only. Check the source. Gemma-4-31B, non-medical." |
| Reference label | "Reference text, not about this patient" |
| Past exchange | "Asked of the Radiology AI agent in the board meeting of <date>" |
| Voice unavailable | "Voice unavailable, text only" |
| Voice mute | "Agent voices are off on this device. Answers still appear as text." |
| Queue | "Radiology is answering <name>. Yours is next." |
| Not in meeting | "That agent is not in this meeting. The coordinator can add it." |
| Quorum line | "Agents standing in (not counted): Radiology, Pathology" |
| Coordinator switch | "Members can ask the agents" |

## 7. Agent quality (item 6.4)

### 7.1 Per-role prompt review points

Read: agents.py `_system` and `_live_system`, each skills/<role>/SKILL.md, specialty_packs.json.
1. Medical Oncology, Surgical Oncology and Radiation Oncology share one pack; no checklists for them. Review whether each needs its own folder weighting (the folder list is the same six) and its own `ROLE_QUERY` terms (agents.py:222-228, used only for briefs). For live questions the pack is searched with the question text only (agents.py:683-686), so the role's focus does not steer retrieval; consider prefixing the role's guideline query.
2. Only Radiology and Pathology have reporting checklists (five and four cancers); the new cancers of Phase 2 will not have pack checklists either. Live answers about "what should the report contain" for a new cancer fall back to NCG passages only.
3. The live prompt repeats "short factual statements" but not "like a colleague"; tone is best added in code (lead-in with the citation's date) not by asking the model to be chatty, because chatty text is where unquoted claims creep in.
4. `doc_types` (agents.py:17-43) limit which documents a brief reads, but `ask` reads the whole Case File regardless of role (agents.py:677). Decide: should a Radiology agent answer a pathology question? Recommended: yes, from the records (they are the same file), with the line "This is a pathology report; Pathology's agent can say more" as a fixed suffix when the cited document's type is outside the role's doc_types.
5. `out_of_scope` is decided by rules plus a classifier that fails open (guardrails.py:51-67). Add a short list of colleague-style requests to the rules: "what would you do", "which would you choose", "do you agree with", "is it operable", "is she fit for", "can we go ahead with".
6. Output guard: `scan_output` (guardrails.py:70-90) checks prescriptive wording and stage patterns; test it on spoken-style sentences (lead-ins) because the lead-in is code, not model text.
7. Quoted dates: dates from the citation are in the record's date; format dd/mm/yyyy in speech through the Phase 4 normaliser.

### 7.2 Pre-loading when a case opens

- When `meetings.open_current`/`start` puts a Case File on the floor (meetings.py:837-841, 891), warm each active agent: (i) the brief is already there; (ii) prefetch the Case File context for the role once, in the same order every time (`context_for` returns the whole Case File when it fits within the budget, search.py:198-206), so the document block is a stable text prefix; (iii) send a one-token "warm" call with `max_tokens=1` and that stable prefix so the reasoner's key-value cache holds it. Whether this helps depends on prefix caching being on in the reasoner: serve_models.sh sets no prefix-caching flag (serve_models.sh:18-19), and the default depends on the vLLM version; check on the running server before relying on it. If it holds, the prompt order should change so the prefix does not include the question: system, the full Case File, then "GUIDELINE REFERENCES", then history and the question at the end (today the guideline block and matching lines follow the documents, but the question-dependent lines sit between, agents.py:677-696).
- Keep the pack search result cached per (role, protocol, question hash) for repeated "Present your points".
- Prepare the six briefs at the ready mark (already done for the five heads, helpers.py:17) and Nuclear Medicine on first add.

### 7.3 First words in about 6 seconds

Budget from "Ask" to first audio:
| Step | Target |
|---|---|
| Question accepted, state to thinking | under 0.2 s |
| Rule check (no model) | under 0.01 s |
| Scope classifier (reasoner, 120 tokens, parallel) | 0.5 to 1.5 s (in parallel with retrieval and the answer call) |
| Retrieval: find_values, context_for, pack search | under 0.5 s |
| Reasoner: prefill and the first statement | 1.5 to 3 s (the whole answer takes 1.6 to 4.2 s today, 00_current_state.md:64, so the first statement is inside that) |
| Verify the first statement (qa.verify) and the output guard | under 0.1 s |
| TTS first audio (Kokoro GPU) | about 0.1 s |
| Network and playout | about 0.2 s |
| Total | about 3 to 5 s typical; 6 s as the p90 target |

How to stream and keep the rules:
1. Replace the single JSON object with a line protocol the model writes one statement at a time. `llm.stream` exists (llm.py:195-224) but takes no JSON schema (llm.py:196 passes `None`); so either extend it to accept a schema for guided decoding, or ask for one JSON object per line (`{"text":..., "citations":[...]}`), parse each line as it completes, and treat a malformed line as not shown. Both keep the rule that nothing is shown before its quote is verified.
2. For every completed statement: `qa.verify` for just that statement (exact quotes only), then `scan_output`; only kept statements are emitted as `agent_answer_part` and, if voice is on, as a sentence for TTS.
3. Hold the first statement until the scope check returns. Today the answer call is cancelled if the scope check fails (agents.py:698-702); with streaming the same applies, and the scope task starts first. The first statement waits at most the classifier time, which runs in parallel.
4. References and the "Not documented" case are decided at the end (references only beside a verified answer, agents.py:716); they appear after the statements.
5. A stream that fails halfway is not restarted (llm.py:213-214 does this already); the statements already shown stand, and the tile shows "Could not answer, try again" for the rest. This case needs a test.
6. Do not skip verification to speed up; the saving comes from overlap, not from fewer checks.
7. A speculative decoding option already exists in the server script (`SPEC`, serve_models.sh:19); measure it for this path.

### 7.4 Evaluation design: 40 synthetic questions per role

Why a new eval: agent_refs_eval.py counts Indian references on briefs and calls itself a measurement, not a gate (agent_refs_eval.py:1-4). qa_eval.py has answerable, absent and scope probes for the Case File assistant only (qa_eval.py:1-20). Neither scores a per-role live answer.

Design (a measurement, no pass mark and no accuracy claim, in the style of the earlier evals):
- Cases: the demo Case Files TB-001 to TB-008 only (synthetic; never the real case), those that have documents of the role's type.
- Per role 40 questions, written by a person (a clinician reviews them) and stored as a JSON file, `tumour_board/eval/agent_live_gold.json`:
  - 16 answerable (a value, a date, a status that is in the records); the label lists the document id and the expected quote or the expected value substring (as qa_eval does).
  - 6 answerable across documents or needing the date order ("which is the latest CT?").
  - 6 not documented (a value that is absent; the right answer is not_documented). Three of these look as if they should be in the file.
  - 6 out of scope: two treatment ("what should we give"), one diagnosis, one scan reading ("look at the CT and tell me"), one stage derivation, one prognosis; plus colleague-style phrasing for three of them ("what would you do").
  - 4 guideline-reference questions ("what should a pathology report of this cancer contain?"), expecting reference text with an Indian source first and no statement about this patient.
  - 2 follow-ups that need history ("and its size?").
- Labels per question: expected status (answered, not_documented, out_of_scope), expected value substrings, the documents that must be cited, whether a reference is expected.
- Scores logged per role and overall, as counts with the list of misses:
  1. Status match (is the status the expected one?).
  2. Quote verification (all shown statements have a located quote: should be 100 percent by construction; log anything else as a bug).
  3. Value correctness: expected substrings found in a verified statement (as in qa_eval).
  4. Citation precision, in the spirit of the ALCE citation metrics (https://arxiv.org/pdf/2305.14627 ): does each cited quote support its sentence? Judged by a person on a sample of 10 per role, not by a model, because the ALCE paper notes the automatic NLI check misses partial support.
  5. Faithfulness, in the Ragas sense (supported claims divided by claims, https://docs.ragas.io/en/v0.3.3/concepts/metrics/available_metrics/faithfulness/): here supported means the statement's claim is in the quote; a person checks the same sample. Note that Ragas itself says faithfulness is not truth and that "I don't know" scores as faithful, so it is read next to the status match.
  6. Refusal correctness: out-of-scope questions must be refused (category and message), and answerable ones must not be refused (false refusals).
  7. No advice: the output guard finds no prescriptive wording in any shown statement; a person reads all shown statements of the out-of-scope and guideline questions.
  8. Latency: the time to the first verified statement, the total, p50 and p90 (the target of 6 s above).
  9. Voice path (with item 4.5's check): the spoken text equals the shown text.
- Logged: the question, the role, the Case File, the status, the statements and quotes, the references, removed statements with reasons (agents.py `removed`), the guardrail layer (rule or classifier), the seconds, the model label, the commit. Output: a JSON file and a Markdown table in the run folder, like agent_refs_eval's report. Run one GPU eval at a time (CLAUDE.md "How to run").

## 8. Tests

Unit (no GPU, no network):
1. A fake reasoner (a stub replacing `llm.chat` and `llm.stream`) returning statements with correct, wrong and missing quotes: only verified statements are emitted, in order, with the lead-in date from the citation.
2. A fake reasoner that returns an out-of-scope request: no statement is ever emitted and the state never reaches speaking.
3. A stream cut off half way: the shown statements stay, the state ends in `error`, no restart.
4. A fake audio service (the Phase 4 `/tts` stub): the sentence events produce one fetch per sentence per unmuted device; a device that is muted fetches nothing; a failed fetch gives "Voice unavailable, text only" and the state "Answering", not "Speaking".
5. State machine per agent: two agents answering at once keep separate states; `listening` expires after 65 s with no stop event; `listening` ends when recording stops; "reading the question" does not exist.
6. Roles: the coordinator can ask; a person on the waiting list cannot; a question to an inactive role is refused; "@Radiology" parsing; the role is sent from the front end.
7. Active agents: every absent head is active, the coordinator adds Nuclear Medicine, removes Radiology, the map survives a reload of the session; Radiation Oncology and Nuclear Medicine are always offered.
8. Quorum: the same with and without agents; no agent appears in `people` or `attendance`.
9. Memory: the third question uses the last three exchanges; a changed Case File signature drops the older answer text; the meeting answer appears in the Case File's thread and in the session log.
10. Refusal strings equal guardrails.REFUSALS; no em dash in any new UI string (a grep test).
11. `test_phase6_agents.py`, `test_agents_live.py`, `test_nik_meetings.py` and `test_nik_helpers.py` already exist and must stay green.

Live (two people with fake camera and microphone, as in plan item 5.6):
1. Coordinator and a member join; Radiology and Pathology agents show as tiles with the labels of 6.9; the brief points are visible.
2. The member taps the microphone on the Radiology tile with a fake microphone file ("What does the CT report record about the hilar node?"): the tile shows "Listening to <name>" only on that clip, the text fills the box, the member edits and asks; "Thinking", "Speaking", "Ready"; the coordinator's page shows the same states; the sentence audio plays on the coordinator's device and not on a device with voices muted (check by counting `/api/tb/audio/tts` calls and by the `agent_audio` events).
3. A treatment question gets the refusal in text and voice.
4. The coordinator removes Pathology and adds Nuclear Medicine; reload the page; the state holds.
5. Restart the app mid-meeting; the tiles return as `ready` from the saved session.
6. Screenshots at member, coordinator, room and phone sizes, reviewed.

## 9. Open questions for the owner

1. In-room default: should a device of a member who joined "in the room" start with agent voices muted (they hear the room screen), and remote members' devices start with voices on? The plan says "spoken aloud by default"; this is the only exception proposed.
2. "Present your points": should the agent only speak after a tap (proposed), or may the coordinator set "present points at the start of each case" so it speaks unprompted? Unprompted speech is the nearest the agent gets to joining the discussion.
3. May the agent say "AI agent, Radiology:" at the start of a spoken answer after silence, so a person in the room who did not see the screen knows who is speaking? Proposed yes.
4. Is a two-minute in-memory cache of rendered sentences (so that every device fetches the same audio) acceptable under "audio never stored", given that nothing is written to disk? If not, each device calls the audio service itself.
5. Should an agent answer a question about a record outside its own specialty (for example the Radiology agent about a pathology report), with the suffix "Pathology's agent can say more", or refuse it as outside its role? Proposed: answer from the records, with the suffix.
6. Should members be able to switch off agent asking for everybody (a coordinator switch "Members can ask the agents")? Proposed yes.
7. Meeting questions and the Case File thread: one shared thread per Case File and role (proposed), or separate? A shared thread means a question asked in a meeting appears on the Case File page for anyone who can open it.
8. Wording of the "not documented" answer in speech: keep the existing "Not documented in the Case File. No statement could be verified against the source documents." (more technical) or the plainer proposal in 6.4? Proposed: the plainer one in speech and the existing one as the detail line.
9. Radiation Oncology: it is a default head today (board.py:46), but the plan also lists it as on demand. Keep both: active when its head is absent, and addable otherwise?
10. A Vaidyx-wide voice for each role (one voice per department, so listeners can tell Radiology from Pathology), or one voice for all agents? Proposed: one voice per role from the Kokoro presets, clearly different from each other, never a human-like name.
11. Is a LiveKit agent worker (option C and option b) wanted as a later phase, for a call with people who join only by audio? It needs the LiveKit server SDK in an environment and a decision on recording the call.

## 10. Web sources used

- LiveKit Agents overview: https://docs.livekit.io/agents/ ; turn detection and interruptions: https://docs.livekit.io/agents/build/turns/ ; agent and user states and events: https://docs.livekit.io/agents/build/events/
- Zoom AI Companion in-meeting questions (university help pages repeating Zoom's text): https://services.css.edu/TDClient/354/Portal/KB/ArticleDet?ID=20117 , https://uis.georgetown.edu/?p=19921 ; Zoom bluepaper: https://library.zoom.com/zoom-workplace/artificial-intelligence/artificial-intelligence-bluepaper/ai-companion/ai-companion-features/zoom-meetings
- Microsoft Teams Copilot in meetings: https://support.microsoft.com/en-us/copilot-teams , https://support.microsoft.com/en-US/teams/meetings-events/welcome-to-copilot-in-microsoft-teams
- Google Meet "Take notes for me": https://support.google.com/meet/answer/14754724
- Voice latency (vendor guides, not standards): https://picovoice.ai/guide/voice-agents/voice-ux-latency-turn-taking/ , https://www.twig.so/blog/voice-ai-agents-latency-budget-800ms , https://dasha.ai/blog/voice-ai-latency ; the 200 ms human gap is Stivers et al. 2009 (PNAS), cited through these guides, not read at source
- Confirmation in conversation design: https://developers.google.com/assistant/conversation-design/confirmations
- Citation and faithfulness evaluation: https://arxiv.org/pdf/2305.14627 (ALCE, Gao et al., EMNLP 2023); https://docs.ragas.io/en/v0.3.3/concepts/metrics/available_metrics/faithfulness/
- Transparency: EU AI Act Article 50 and guidelines: https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act ; FDA clinical decision support guidance: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software (revised January 2026 per secondary sources, the revised text was not opened); India: https://www.emergobyul.com/news/india-cdsco-finalizes-guidance-medical-device-software (secondary), https://www.icmr.gov.in/ethical-guidelines-for-application-of-artificial-intelligence-in-biomedical-research-and-healthcare
- Repository research used: docs/tumour-board/audio_feature.md (Kokoro and Whisper figures, lines 36-60, 143-146), docs/night-v3/research/00_current_state.md sections 2 and 6.

## 11. The contract as built (Phase 6, session 8, 27 Oct 2026)

The orchestrator's design for items 6.1 to 6.5, within D2 and the recommendations above. The safer reading of every open question of section 9 (logged `[DECISION]`): in-room members start with agent voices muted on their own device and the room screen plays them (1); an agent speaks only after a tap, never unprompted (2); the spoken answer begins with the tile's own title line "AI agent, Radiology" (3); no audio cache, each device fetches its own sentences (4); an agent answers from any record of the file, with a fixed note when the cited record is outside its specialty (5); the coordinator has a "Members can ask the agents" switch (6); one shared thread per Case File and role (7); the plainer "not documented" sentence in speech and on the card, the technical one as the detail line (8); Radiation Oncology stands in when its head is absent and can be added otherwise (9); one voice for every agent, the department named first (10, Phase 4 decision 2); no LiveKit agent worker (11).

### 11.1 Backend (tumour_board/meetings.py, api/meetings.py)

Saved with the meeting (session file):
- `agents_active`: `{case_id: {role: {"on": bool, "by": user, "by_name": name, "at": iso}}}`, the coordinator's additions and removals. The default per Case File is `board.absent_roles(session, case_id)`; the map overrides it. Order: the order of `agents.ROLES`.
- `agents_ask`: bool, default true: members may ask the agents (the coordinator always may).
- `agents` (existing): brief status per Case File and role (queued, running, ready, no_documents, error).
- `questions[]`: a question asked of an agent carries `role`, `queued` (waiting for that agent's earlier answer) and `answer`, which fills statement by statement: `{status: answering | answered | not_documented | out_of_scope | not_listed | error, text, statements[], references[], role, label, model, at, seconds, first_seconds, note, category?, message?, kind?: "present_points", speech: ["AI agent, Radiology.", ...statement texts..., "Sources are on the screen."]}`. `speech` is the exact list the devices read, each entry a text that is on the screen.

Live only (rebuilt after a restart from the saved session): `AGENT_STATE[mid][role] = {state, by, by_name, question, at, expires}` and `AGENT_AUDIO[mid][qid] = {user: expires}` (the devices that report playing).

The states (true by construction):
| State | Word | Enter | Leave |
|---|---|---|---|
| preparing | Reading the records | the session's brief status is queued or running | ready, no_documents or error |
| ready | Ready | nothing else holds | |
| listening | Listening to <name> | POST agents/{role}/listening {on: true} by an admitted member (expires 65 s) | {on: false} by that member, the expiry, or a question sent |
| thinking | Thinking | the question is accepted and the answer task runs | the first verified statement, or the end |
| answering | Answering | a verified statement is on the screen and no device reports audio | the end of the answer |
| speaking | Speaking | at least one device reported playing this answer (reports expire 30 s, renewed every 15 s) | no device reports playing |
| error | Could not answer, try again | the model or the stream failed | the next question or 60 s |

`agents_view(s)` gives one entry per active agent for the Case File on the floor: `{role, label, department, department_name, state, by, by_name, question, standing_in, added, added_by, added_by_name, reason ("Head absent" | "Marked absent" | "Added by <name>"), title ("Radiology, AI agent standing in" | "Nuclear Medicine, AI agent, called by <name>"), brief {status none|preparing|ready|stale|no_documents|error, label, at, reviewed_by}, points [{text, citations[{doc_id, doc_title, date, page, quote}]}] (at most 5, from the brief's points for review), points_count, not_documented_count, voice, can_remove, note}`. Agents never appear in `people`, `attendance` or the quorum counts (quorum_view lists them apart, as in Phase 5). A viewer who is not admitted gets the list without `points`.

Routes (all audited, `common.fail` codes in brackets):
- `POST /meetings/{mid}/agents` `{role, on}`: the coordinator adds or removes an agent for the Case File on the floor (`agent_added`, `agent_removed`); adding starts the brief when none stands (`service.prepare_session_agents(sid, user, roles=[role], case_ids=[cid])`); removing clears its live state and stops its audio everywhere; 409 `no_current` outside a case. Answers `{agents}`.
- `PUT /meetings/{mid}/agents/settings` `{members_ask}`: the coordinator's switch (`agents_settings`). Answers `{members_ask}`; the state carries `can.ask_agents`.
- `POST /meetings/{mid}/agents/{role}/listening` `{on}`: an admitted member says its device records a question for this agent; audited as `agent_listening` with seconds only. 409 `agent_not_in_meeting` for an inactive role.
- `POST /meetings/{mid}/questions` `{text, role?}` (existing): with `role` the agent must be active for the Case File on the floor (409 `agent_not_in_meeting`: "That agent is not in this meeting. The coordinator can add it."); members only while `agents_ask` is on (403 `agents_ask_off`: "The MDT Coordinator has closed questions to the agents for now."); one answer at a time per agent (a later question waits with `queued: true`, the word "Radiology is answering <name>. Yours is next.").
- `POST /meetings/{mid}/agents/{role}/present` (item 6.2): "Present your points": a question record with `kind: "present_points"` and an answer built by code from the brief's points for review (each a statement with its citations; no model call); `no_documents` and an empty brief give `not_documented` with the brief's message.
- `POST /meetings/{mid}/agents/{role}/stop` `{question?}`: the asker or the coordinator stops the voice for everyone (`agent_stop` event; the text stays; no further `agent_speech` for that answer).
- `POST /meetings/{mid}/agents/audio` `{question, playing}`: a device reports that it plays or stopped playing an answer (the room screen included); drives "speaking".

Events on the live channel (private to the admitted members and the coordinator, like `question`): `agents` `{agents}` after an add, a remove, a settings change or a brief status change; `agent_state` `{role, state, by, by_name, question, at}` per agent; `question` `{question}` after every statement (the partial answer); `agent_speech` `{role, question, index, final}` (no text: the device speaks by reference, `{kind: "meeting_answer", meeting_id, id: <question id>, index}` on `/api/tb/audio/tts`, which reads `answer.speech[index]`, one sentence per request with X-Parts); `agent_stop` `{role, question, by}`.

`answer()`: takes the agent's lock, state thinking, `agents.ask(cid, role, text, history, user, on_statement=cb)`; `cb` appends the verified statement to the saved answer, sends `question` and `agent_speech`; the end fills references, status, seconds, logs the answer (`board.log_answer`), records the exchange on the shared thread (`helpers.record_exchange(cid, role, m, source="meeting:<mid>")`), sends the last `agent_speech` with `final`, and the state returns to ready (or stays speaking while devices report). History: `helpers.history_for(cid, role, 3)` (the shared thread: the Case File page and every meeting).

### 11.2 agents.py, guardrails.py, helpers.py, audio_proxy.py (an implementer)
- `agents.ask(..., on_statement=None)`: with a callback the reasoner is streamed (`llm.stream`) with a line protocol: one JSON object per line `{"text": ..., "citations": [{"doc_id": ..., "quote": ...}]}`, a last line `{"end": true, "answer_found": bool, "references": [{"ref_id": ..., "quote": ...}]}`. Each complete statement line is verified on its own (`qa.verify`, exact quotes only) and scanned (`guardrails.scan_output`); only a kept statement reaches the callback, in order; the first one waits for the scope check. A malformed line is dropped and counted (`removed`, reason `malformed`); a stream that yields no parseable line falls back to today's single JSON call (never a second stream after text went out). Without a callback the behaviour is today's. The record gains `first_seconds` and `streamed`. `LIVE_LABEL` becomes "AI agent, support only".
- A statement whose cited document type is outside the role's `doc_types` gets `note: "This is a <type> record; the <Department> agent can say more."` (code, not the model; not spoken).
- `guardrails._RULES`: colleague-style requests refused by rule: "what would you do", "which (one )?would you (pick|choose|go for)", "do you agree (with|that)", "is (it|he|she|the patient|this) (operable|resectable|curable|fit for)", "can we (go ahead|proceed) with", "would you (recommend|suggest|advise|give|offer|operate)".
- `helpers.record_exchange(case_id, role, m, source="case")`, `helpers.history_for(case_id, role, n=3)` (a changed signature keeps the question and drops the answer text), `messages()` with `source` and `meeting_date`; `ask()` uses both.
- `audio_proxy._meeting_text`: with `index` the answer's `speech[index]` (or the i-th statement when `speech` is missing); without it the joined text as today.

### 11.3 Frontend (web/tb-nik)
- `lib/live.ts`: `AgentInfo` with the fields of 11.1; `MeetingState.can.ask_agents`; the events `agents`, `agent_state` (merged by role with by, by_name, question, at), `agent_speech`, `agent_stop` pass through `lastEvent`.
- `features/meetings/api.ts`: `setAgent(mid, role, on)`, `setAgentSettings(mid, {members_ask})`, `agentListening(mid, role, on)`, `presentPoints(mid, role)`, `stopAgent(mid, role, question?)`, `agentAudio(mid, question, playing)`.
- `call/agentSpeaker.ts` (new): a queue of `{question, index}` played one after the other through `voice.speak({ref: {kind: "meeting_answer", meeting_id, id, index}}, {screen: "meeting"})`; reports `agentAudio` true at the first start, renews every 15 s, false at the end or on stop; `agent_stop` clears the queue for that question; switching agent voices off clears everything; a NotAllowedError shows the "Tap to allow agent voices" chip (primes the audio element and resumes). Default: on, except a member admitted as "in the room" (`me.mode === "room"`) with no stored choice, who starts muted; the room screen starts on.
- `call/types.ts`: `AGENT_STATE_WORD` gains preparing, listening, speaking, error; `CallActions` gains `setAgent`, `setAgentsAsk`, `agentListening`, `presentPoints`, `stopAgent`; `CallCtx` gains `speakingNow: {question, index} | null` and `stopAgentAudio()`.
- `components/MicButton.tsx`: `onListening?: (on: boolean) => void` (true when recording starts, false when it stops, cancels or errors).
- `CaseFlow.tsx`: at the start of each case with agents, a 6 s notice "AI agents in this case: Radiology, Pathology. They read records and guidelines only. They do not decide or advise." (announced politely).
- `Strip.tsx` (the tiles, the room column), `panels/AgentsPanel.tsx`, `panels/ChatPanel.tsx`: the strings of section 6.9; the tile shows the title, "AI agent, support only", the state word (with the name while listening), the points count ("4 points from the records"), and a menu (Ask, Present your points, Stop, Remove from this meeting for the coordinator). The Agents panel: the six roles as rows with "In this meeting" (a switch for the coordinator with the reason; words for members), the active agents' cards with the points (chips: document, date, page; the quote as the title), the question box with the microphone (listening on while it records) and "Heard this. Check it before asking.", the answer streaming statement by statement with its chips, the references under "Reference text, not about this patient", the footer "AI agent, support only. From the records and guidelines only. Check the source. Gemma-4-31B, non-medical.", Stop while speaking, the queue line, the refusal's two quick questions. The Questions tab of the Chat panel: "@Radiology" at the start of the text picks that agent's chip; "Members can ask the agents" for the coordinator.
- `e2e/shots/meetings-agents.spec.ts` (mocked) and the live spec's agent steps (item 6.3).

## 12. Agent quality as built (item 6.4, session 8, 27 Oct 2026)

The review of section 7.1, point by point, and what changed:
1. The three oncology roles share one pack and the live pack search uses the question text alone: left as it is for this run (the guideline questions of the evaluation name the report or the work-up they ask about, so the question text steers the search); a per-role query prefix stays a Parking lot idea to measure.
2. Only Radiology and Pathology have reporting checklists: unchanged (the packs are the owner's library).
3. Tone: no "like a colleague" wording in the model prompt; the colleague's voice is code: the spoken answer opens with the tile's own title ("AI agent, Radiology."), the statements follow as verified, and "Sources are on the screen." closes it.
4. A statement citing a record outside the role's document types carries the fixed note "This is a CT record; the Radiology agent can say more." (code, never spoken).
5. Colleague-style decision requests are refused by rule ("what would you do", "which one would you pick", "do you agree with", "is it operable", "is she fit for", "can we go ahead with", "would you recommend"), because the classifier fails open. The first evaluation found the opposite gap: every question about what a report or a work-up should contain was refused by the classifier as out of scope, so the rule `guardrails.reference_check` now marks such a question (an opener, a record word, a contents verb, no refusal rule) as in scope by rule, the classifier's text says the same, and the guideline passages are kept for such a question even when no statement about the patient survives (message "Not documented about this patient. The guideline passages below are reference text, not about this patient."). Indication-style questions ("when PET/CT is used in staging", "how toxicity should be graded") still go to the classifier and may be refused: by design.
6. `scan_output` on spoken lead-ins: tested (the lead-ins are code, not model text).
7. Dates in speech: the audio service's normaliser reads DD/MM/YYYY (Phase 4).
8. The six SKILL.md files read: no advice words, no em dashes, the focus lists and the points to raise within scope.

Pre-loading when a case opens: the live prompt now sends the documents block first (system, then "DOCUMENTS: ..." as the first user turn, then the thread's turns, then the question with its matching lines and guideline passages; the reasoner's chat template accepts two user turns in a row, checked on the running server). `agents.warm(case_id, role)` sends that same documents block once with one output token when a Case File comes on the floor, on the next case and when the coordinator adds an agent (meetings._warm_agents, background tasks), once per Case File signature and role, audited as an llm_call with purpose "agent warm"; vLLM 0.30.0's V1 engine keeps prefixes by default, so the next question's prefill reuses it. The streamed answer (section 11.2) gives the first verified statement well inside the 6 s target without it (the evaluation: p50 2.4 s, p90 4.8 s on the first run), so the warm-up is a margin, not a need.

The evaluation (section 7.4 as built): `tumour_board/eval/agent_live_gold.json` (240 questions, every quote checked word for word by `check_agent_live_gold.py`; no clinician has reviewed them yet) and `tumour_board/eval/agent_live_eval.py` (in-process through `agents.ask` with streaming, one question at a time, the eight scores, a JSON and a Markdown report under /data/vaidyx/night-v3/runs/evals/, `--dry` to re-score). A measurement on synthetic Case Files with Gemma-4-31B, a non-medical model: no accuracy claim, no pass mark. The citation precision and faithfulness samples (7.4 points 4 and 5) are for a person to judge and were not done tonight.
