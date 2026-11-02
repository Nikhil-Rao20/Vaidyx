# What exists on 27 Oct 2026 (before the night run)

Read-only findings of three code surveys on branch `night-v3` (= `main` after PR #2). File references are to the repo root. Later phases
start from these facts; each phase checks the parts it changes again before editing.

## 1. Cancer checklists (protocols)

| id | label | version | records (+optional) | settings |
|---|---|---|---|---|
| breast | Breast cancer | 0.7 | 14 (+2) | early / locally_advanced / metastatic |
| cervix | Cervix cancer | 0.2 | 13 (+2) | early / locally advanced / metastatic (FIGO 2018) |
| colorectal_rectum | Rectal cancer | 0.6 | 11 (+2) | non_metastatic / metastatic |
| lung_nsclc | Lung cancer (NSCLC) | 0.8 | 13 (+4) | non_metastatic / metastatic |
| oral_cavity | Oral cavity cancer | 0.3 | 7 (+3) | early / locally advanced / metastatic |
| cup | Cancer of Unknown Primary | 0.1-draft | 23 (+4) | muo / provisional_cup / confirmed_cup (`approval.status: draft`) |
| generic | Other cancer | 0.1 | 4 (+2) | as_recorded (`approval.status: owner_decision`): histopathology, staging imaging, clinical note, board question |

None has a clinician sign-off; the five cancer files say "to be confirmed by the hospital Tumour Board".

**The picker** (`web/tb-nik/src/lib/cancers.ts:59-84`, NCRP 2020 top-10 lists): 19 of 26 entries have no checklist and fall back to
`generic`: prostate, stomach, oesophagus, liver, larynx, NHL, ovary, corpus uteri, gallbladder, thyroid, leukaemia, childhood lymphoma,
brain, bone, kidney, retinoblastoma, soft tissue, germ cell, other childhood. Colon falls back to generic (the colorectal checklist is
rectal only). Tongue maps to oral_cavity.

**Guidelines in the library for those 19** (`/data/vaidyx/tb_resources/guidelines`): only NCG India files and the ICRI / IRIA imaging book.

| Cancer | NCG India file |
|---|---|
| Prostate, kidney, germ cell (testis) | ncg-guidelines-for-urological-malignancies-2019.pdf |
| Stomach | ncg-gi-draft-2021-gastric-cancer.pdf |
| Gallbladder | ncg-gi-draft-2021-gall-bladder-cancer.pdf + radiology synoptic |
| Liver (HCC) | ncg-gi-hepatocellular-carcinoma.docx (hepatoblastoma: paediatric 2019) |
| Oesophagus | ncg-guidelines-for-thoracic-cancer-2019.pdf |
| Larynx | ncg-guidelines-for-head-neck-cancer-2019.pdf |
| Ovary, corpus uteri | ncg-guidelines-for-gynecological-cancer-2019.docx |
| NHL, adult leukaemia | ncg-guidelines-for-adult-hematolymphoid-2019.pdf |
| Childhood leukaemia, lymphoma, retinoblastoma, Wilms, germ cell, hepatoblastoma, rhabdomyosarcoma | ncg-guidelines-for-pediatric-haematolymphoid-solid-tumours-2019.pdf |
| Bone, soft tissue | ncg-guidelines-for-bone-soft-tissue-tumours-2019.pdf |
| Thyroid | no dedicated file (head and neck 2019 mentions thyroid only in passing) |
| Brain | none (IRIA imaging only) |

ICMR, TMC, MoHFW STG, ESMO, NCI PDQ, CAP, ICCR, ACR and the AJCC chapters cover only the five built cancers (and CUP).

**What a new protocol needs to work end to end:**
- File fields: `id, label, version, note, settings[], records[]`.
- Each record: `id, label, department` (must exist in org), `doc_types` (or `facts_only` + `fact_doc_types`), `required_facts` (each in `facts.json`), `tier`/`tiers`, and `sources` with an NCG quote and an integer page (`test_tiers.py:18-45`).
- Optional keys: `optional, extract_facts, core_data, post_board, policy_basis, site` (pipe-separated organ words, `test_rules.py:586`).
- A new fact needs a `facts.json` entry. A new document type must be added to `facts.json doc_types`, `doc_type_keywords.json types` (`test_doctype.py:26`) and, if it comes from the HIS, `his_codes.json`.

**Hard-coded cancer lists to extend:**
- `steps.py` `SITE_WORDS` / `SITE_NAME` (lines 46-52, the cancer-against-reports warning)
- `guidelines.py` `CANCER_WORDS` and queries (38, 402)
- `staging PROTOCOL_RULES` (breast, lung, cervix)
- `packs.py` / `specialty_packs.json` (checklists must name existing protocols)
- tests: `test_tiers.py:9` PIDS, `test_routes.py:9` PROTOCOLS, and `test_listing.py:117-121`, which asserts that no `ovary` protocol exists and must change.

**Dose references:** `dose_references.json` has 301 rows covering only breast 77, cervix 15, colorectal 107, lung 82 and oral 20.

## 2. Specialty agents ("specialty helpers", "stand-in agents")

- **agents.py**
  - 6 roles: Radiology, Pathology, Medical Oncology, Surgical Oncology, Radiation Oncology, Nuclear Medicine.
  - `run_agent` is a ReAct loop of up to 5 steps with read-only tools, which writes a brief (quote-checked, guardrails, stored as `artefacts.brief_<role>`).
  - `ask()` (654-716) answers one question from the case context (40k characters) plus guideline-pack passages, keeping only exact quotes. Status is answered, not_documented, out_of_scope or not_listed. It takes 1.6 to 4.2 s.
- **helpers.py:** 6 "<Dept> records check" cards; the five heads are prepared at the ready mark, Nuclear Medicine on click. Chat keeps the last 2 exchanges as history and is saved per Case File (`helper_chats.json`).
- **board.py:** DEFAULT_HEADS = 5 and ON_DEMAND = Radiation Oncology and Nuclear Medicine. `absent_roles`: a head not marked present is active. The surgical seat is Surgical Oncology or the case's own surgeon.
- **meetings.py**
  - `agent_state` (419-441) is active only in session, with a case on the floor and a head absent, and uses **only the first absent head**.
  - `ask` (999-1018) goes to that one agent.
  - `answer` (1021-1064) broadcasts reading_question, thinking, answering and ready, and calls `agents.ask` with no history.
  - `start()` prepares the absent heads' briefs. Agent state is kept in memory only.
- **Frontend**
  - HelpersPanel cards sit in the Summary section of the guided Case File.
  - In meetings, `AgentTile` is a separate card (members' tile column, the room screen's side column, and the coordinator's People tab only).
  - Members ask through the Questions panel with no role. The coordinator has no question box.
  - The answer's references and time are not shown.
- **Intent (owner's own words in the interview):**
  - R12-Q09: agent points "shown from the start", labelled AI support.
  - R17-Q12: "an active Vaidyx agent logo listening to each and every discussion ... listening, then a thinking animation, then a speaking action" (states must be true).
  - R17-Q20: "The Ask is a general one. The 6 agents are there separately ... gives a brief ... then the doctor's questions can be taken."
  - V2 6.2: an absent head's agent is active automatically; Radiation Oncology and Nuclear Medicine are on demand; an agent never counts as a member.
  - Voice was deferred then (R12-Q10/Q11); the owner lifted that on 27 Oct.
- **Gaps:**
  - The agent is not a participant in the grid.
  - Only one stand-in per case.
  - Points are not shown from the start.
  - Text only.
  - The meeting thread and the Case File thread are separate.
  - The coordinator cannot ask.
  - References and time are not shown.

## 3. Meetings and video

- **Screens:**
  - **JoinPage:** code entry, then a waiting room.
  - **MeetingAgendaPage:** before the meeting.
  - **ControlView:** the coordinator. Shared screen, Admit banner, a tile row of at most 10, and tabs Share / Decision / People / Questions / Agenda. The bar has mic, cam, Previous/Next, Timer, End case and End meeting.
  - **MeetingRoomPage:** the projector. Summary on the left, the shared screen, at most 6 tiles, the agent tile, questions, hands, the decision strip.
  - **MemberViewPage:** members. Shared screen with Follow / Step away, a tile column, People and Questions panels. The bar has mic, cam, hand, Follow, Questions, People, card and Leave.
  - Also PreJoin, Stage, VideoTiles, CardDialog, People and DecisionForm.
- **LiveKit** (self-hosted v1.13.10 on :7880, at most 50 participants)
  - Used: adaptive stream, mic and camera toggles, device choice at join, active speakers, the RoomAudioRenderer.
  - **Not used:** screen share (the "shared screen" is app state), the data channel or chat, captions, reactions (hands go over the app WebSocket), pin / spotlight / speaker layouts, recording, device change after join, connection quality.
- **Live channel:** WebSocket `/meetings/{mid}/ws`, broadcast per socket. Events: meeting, agenda, admit, presence, current, open, timer, question, agent_state, hand, decision_live, decision, end_case, card, ended.

## 4. Decision record

- **The DecisionForm asks for:**
  - outcome (decision, deferred, referred, not_discussed, noted)
  - decision_text, rationale, intent_as_stated (free text), responsible_doctor, next_step, next_step_date
  - awaited / awaited_from (deferred only), referred_to (referred only)
  - members_present, concerns
- **postboard accepts more:** COMMUNICATION_FIELDS (patient_informed_date, informed_by, key_worker, intent_as_recorded, trial_considered, consent_recorded), divergent_opinions and actions. The form never asks for them, so every decision raises "info" flags.
- **Mismatches:** the maximum field lengths differ between UI and backend, and the label for not_discussed differs between postboard and meetings.

## 5. Summary, search, access, notifications

- **Summary:** `summary.build` makes one reasoner call over 60k characters of context in the 6 NCG VTB sections. Every sentence is quote-checked, and the result is stored as `artefacts.summary`, **overwritten** on rebuild with the review reset (no versions). **Nothing is summarised after the board:** minutes, the deck and the VTB export are assembled by code; the VTB export reuses the pre-board summary.
- **Board records:**
  - Stored in `state.json board_records[]` by postboard.record_decision.
  - Fields:
    - the decision: text, outcome, rationale, intent, concerns, divergent opinions
    - follow-up: actions, next step, attendance
    - communication fields
    - checks and history: adjudication, versions
- **Search:** the list search (`api/cases_list.py:198-213`, `web/.../lib/search.ts`) covers identity, ids, cancer, owner, status and board date. **No clinical text and no summary line**; no per-case summary field exists.
- **Indexes:** `search.py CaseIndex` (BM25 + `snowflake-arctic-embed-m-long` via fastembed on CPU, fused by RRF, chunk vectors cached by content) is one index per Case File; `guidelines.py` has one global index. **There is no cross-Case File index.**
- **Access:** `access.scope` gives FULL to the coordinator, the owner's consultants, participating departments, linked-case owners, team residents and an open referral; REQUESTS to a department with a sent request. **Doctor break-glass (R03-Q02, "open with a reason, owner told") is not implemented**: only the Vaidyx admin has one.
- **Notifications:** `notifications.jsonl` with 30 kinds; the bell polls every 45 s; browser push via VAPID with generic texts.
- **Real time:** `live.py` has a reusable `Hub` class (rooms, per-socket shaping, thread-safe), so a second hub can serve chat.
- **People:** there is no people or department directory for ordinary doctors. `profiles.json` holds display name, title, registration number, phone and photo.
- **Browser:** `core/middleware.py` sends `Permissions-Policy: camera=(self), microphone=(self)`, so the microphone works on /tb-nik.

## 6. Voice (research done 12 to 15 Oct, `docs/tumour-board/audio_feature.md`)

- **Speech to text:** faster-whisper large-v3-turbo, **fp16**, with Silero VAD and a clinical initial prompt (2.3 GB GPU, about 0.2 s per utterance, WER 0.079 on clinical sentences). Switchable second engine: Cohere Transcribe (better on Indian accents). CPU fallback: Parakeet v2.
- **Text to speech:** Kokoro-82M on GPU (about 1 GB, first audio under 100 ms) with a clinical text normaliser and lexicon (drug names), and a CPU fallback.
- **Architecture:** a separate audio service on **:7120** in `/data/vaidyx/venv/audio`, proxied by the app, off unless `TB_AUDIO_URL` is set; audio is never stored.
- **Installed and cached:** faster-whisper 1.2.1, Kokoro, CUDA, and the model caches (whisper turbo, Kokoro-82M, Cohere, Parakeet).
- **GPU:** 125.8 of 143.8 GB in use by the two models, so about 18 GB is free; the voice models fit.

## 7. Known bugs and the not-built list (owner walkthrough, 21 to 26 Oct)

**Bugs**
1. Duplicate Case Files: New Case File gives no warning when the same patient and cancer already have a file (seen when Haematology created a second Kavitha breast file); decided design R05-Q11 is "show it, offer to join".
2. Leftover test duplicates in the demo data (two Priya Venkatesan breast files; the extra Kavitha file).
3. A linked file of another department shows in Breast Surgery's list.
4. The mocked `e2e/shots/casefile.spec.ts` still targets the previous Case File page.
5. The previous `CaseFilePage.tsx` is kept only as a fallback.

**Not built**
- A multi-step "Send to the board" (meeting, discussion or noting, presenter, note, a reason when open; enforced by the server).
- After sending: summary and slides updated automatically and the coordinator told; a changed value shows both and gives the doctor a task.
- The doctor moving or withdrawing a case from a meeting.
- The agenda filled automatically from the ready mark (R10-Q04/Q07).
- Picking the value when two reports differ (today only "noted").
- Residents' sign-off for key checks and the reason.
- Staging: the clinician check, the FIGO PDF (owner to download) and the breast prognostic stage.
