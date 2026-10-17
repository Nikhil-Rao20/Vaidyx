# API contract for the new interface (/api/tb, added 18 Oct 2026)

Existing endpoints stay as they are (list: scratchpad maps/backend_map.md, and routes/tumour_board_routes.py). New routers live in tumour_board/api/<area>.py (each exports `router`, built with common.make_router()); routes/tumour_board_routes.py includes them. Conventions: JSON in and out; errors {"detail": {"message", "code"}} or {"detail": "message"}; every change audited; permissions through common.need / need_case; ids are strings; times ISO 8601 with offset (+05:30); dates DD/MM/YYYY are for display only (the API sends ISO). The frontend sends X-Requested-With: tb-nik on every call; unsafe methods are refused when a cross-site Origin is present.

## me.py (B1)
- GET /me -> {user, display_name, roles: {admin, root_admin, coordinator, auditor, departments{id: member|head|resident}, treating[], supporting[], admin_of[], outside_expert, disabled}, primary_role, must_change_password, profile{title, registration_no, phone, phone_visible, photo, theme, text_size, start_page, saved_filters[]}, setup_needed (bool: profile not completed), counts{unread, waiting_for_me, open_requests}, hospital{name, level}, features{video: bool, push: bool}}
- POST /me/password {current_password, new_password} -> {ok}; 400 weak; clears must_change_password. Rate limited.
- PUT /me/profile {display_name?, title?, registration_no?, phone?, phone_visible?, photo? (data URL <= 200 KB), theme?, text_size?, start_page?, saved_filters?} -> profile. Marks setup complete when display_name and (for doctors) registration_no are present.
- GET /me/activity?limit=100 -> {events[{ts, kind, case_id?, title, detail}]} (this person's own audited actions across Case Files and the organisation).
- GET /activity?case_id?&user?&limit -> full log, coordinator / auditor / root admin only.
- Profile fields are stored in data/tumour_board/profiles.json {username: {...}}; theme/text_size/start_page also in localStorage on the client.

## cases_list.py (B1)
- GET /cases/list?q&urgency&status&department&organ&owner&board_from&board_to&imaging&mine -> {cases[{case_id, patient{name, agesex, uhid}, protocol, protocol_label, setting, owner{department, department_label, doctor, doctor_name}, urgency{level, set_by, set_by_name, at, proposed?}, status{key: needs_me|waiting_department|ready|scheduled|decided|archived|draft, label, detail}, board_date, meeting_id?, left_before_board, imaging_present, last_change, created, residents_count}], filters{departments[], organs[], owners[], statuses[]}} sorted newest first (created desc). Server-side filters are simple matches; the client may also filter.
- Archived Case Files are listed only with status=archived.

## team.py (B1)
- PUT /cases/{id}/urgency {level 1..5, note?} -> {urgency}. Owner's consultant sets; a resident's call creates a proposal instead (returns {proposal}).
- GET /cases/{id}/team -> {owner{department, doctors[{user, name}]}, residents[{user, name, end_date, added_by, since}], departments[{id, label, since}], join_code{code, expires_at, uses} | null, pending[{user, name, requested_at}]}
- POST /cases/{id}/team/code -> {code (6 digits), expires_at} (owner; replaces the old code); DELETE /cases/{id}/team/code.
- POST /cases/join {code} -> {status: joined|pending, case_id, patient_line}. Rate limited 5 per 15 min per user; wrong code -> 404 {code: "no_such_code"}. A resident of the owner's department joins at once; another department's resident waits for approval.
- POST /cases/{id}/team/pending/{user}/approve | /reject {note?}; DELETE /cases/{id}/team/residents/{user} (owner, department admin, or the resident themself).
- Proposals (resident asks the consultant): POST /cases/{id}/proposals {action, payload, note?} where action in waive | not_needed | confirm | mark_ready | send_request | urgency | refer | typed_value | published_case; -> {proposal{id, action, payload, note, by, by_name, at, status pending}}. GET /cases/{id}/proposals -> {proposals[]}. POST /cases/{id}/proposals/{pid}/approve {note?} -> runs the action as the consultant and returns {proposal, result}; POST .../return {note} -> status returned. Consultant gets a notification kind "sign_off" with title "Dr X asks you to sign off: <action> (<patient>)".
- GET /waiting -> {items[{id, kind: proposal|join|review, case_id, patient_line, title, by_name, at}]} for the home.
- POST /cases/{id}/archive {reason} -> {case}; owner's consultant, or coordinator with a reason. GET /cases/list?status=archived lists them; POST /cases/{id}/unarchive.
- PUT /cases/{id}/consent {outside_discussion: bool, note?} -> {consent}. Outside experts (role outside_expert) see initials, age and sex unless true.
- POST /break-glass {case_id, reason} (Vaidyx admin only) -> {until}; audited "break_glass"; the owner is notified. access.scope grants FULL to a Vaidyx admin only inside an open break-glass window; outside it a Vaidyx admin has no clinical scope.

## setup.py (B1)
- GET /setup -> {steps[{id: hospital|departments|people|his|board, label, done, summary}], complete, hospital, departments[{id, name, group, enabled, email, phone}], board{coordinators[], heads[]}, his{url, tested_at, ok}}
- POST /setup/hospital {name, level, type, pmjay_empanelled}; POST /setup/departments {enabled[], contacts{dept: {email, phone}}}; POST /setup/people {accounts[{email, display_name, departments{dept: role}, coordinator?, admin_of[], root_admin?, end_date?}]} -> {created[{email, mailto}], errors[]}; POST /setup/his {url} -> runs the test; POST /setup/board {coordinators[], heads[], meeting_defaults{weekday?, time?, room?, minutes_per_case}}. Each step saves at once.
- POST /his/test -> {ok, hospital_name, patients, reports, latency_ms, error?}.
- Accounts: POST /accounts {email, display_name, departments{dept: member|head|resident}, coordinator?, admin_of[], root_admin?, auditor?, end_date?} -> {username, mailto} (random 14-char password inside the mailto body only; must_change set); POST /accounts/{username}/reset-password -> {mailto} (department admin for their department's people, root admin for anyone); PUT /accounts/{username} {disabled?, end_date?, roles...}. Login names are email addresses (lower case); accounts.py rule widened.
- Roles added to org.json users: "resident" placement value (departments{dept: resident}), "auditor": true, "outside_expert": true, "end_date". A resident cannot: waive, confirm, mark_ready, send_request, create_request, refer, sign anything; they can read FULL scope on their Case Files, upload, ask, propose.

## slots.py (B2)
- GET /cases/{id}/slots -> {sections[{id, label, slots[{id, label, status: found|not_found|waiting|needs_confirmation|entered|not_needed|pending_ready, value, unit?, as_of?, quote{text, doc_id, doc_title, page, fact_id}|null, request{action_id, department, department_label, sent_at, due, status}|null, confirmation{type, key}|null, actions[{kind: ask_department|not_needed|enter_value|review|remind|open_source, label, department?, action_id?}], typed_by?, note?}]}], left_before_board, blockers[{slot_id, why}], ready_allowed, prose{status: none|pending|ready|stale, paragraphs[], reviewed}}. Built from protocol records + required_facts + rules.resolve_facts + state.gate + state.actions, no model.
- POST /cases/{id}/slots/{slot}/value {value, note?} (allowed facts only: ecog, menopausal_status, weight, height, clinical_question, and any protocol fact flagged "typable") -> slot; DELETE removes. Audited "typed_value"; shown "entered by Dr X, no report".
- POST /cases/{id}/slots/{slot}/not-needed {reason} -> slot (a waive confirmation).
- POST /cases/{id}/slots/{slot}/ask-department {message?, due?} -> {slot, request} (drafts and sends the suggested request for that slot's record; the draft text comes from dept_requests.draft).
- GET /cases/{id}/documents/{doc}/quote?fact=<id> or ?text=<quote> -> {page, boxes[{x, y, w, h}] (fractions of the page), found} for highlighting in the viewer.

## chats.py (B2)
- GET /cases/{id}/chats -> {threads[{id, by, by_name, at, question, status, statements[{text, citations[{doc_id, doc_title, page, quote}]}], message?, pinned, stale, seconds}]} visible to the owner's team and participating departments (never REQUESTS scope).
- POST /cases/{id}/chats {question} -> thread (runs qa.ask; rate limit 20 per 10 min per user); POST /cases/{id}/chats/{tid}/pin {pinned: bool}; stale = case_signature changed since the answer.

## helpers.py (B2)
- GET /cases/{id}/helpers -> {helpers[{role, label, department, brief{status: none|preparing|ready|stale, at, sections, points_for_review, reviewed_by?}, thread_count, prepare_allowed}]}. Five heads prepared at the ready mark (service hook), nuclear_medicine on click.
- POST /cases/{id}/helpers/{role}/prepare -> {job} (uses agents.run_agent in the background; GET /jobs/{id} to poll; or stream the existing endpoint).
- GET /cases/{id}/helpers/{role}/chat -> {messages[]}; POST /cases/{id}/helpers/{role}/chat {question} -> message (agents.ask; saved per role, shared with the team).

## published.py (B2)
- GET /cases/{id}/published -> {items[{id, title, authors, journal, year, doi, url, source: local|pubmed|europepmc, peer_reviewed, kind: paper|preprint|white_paper|book, added_by, at, quotes[{text, where}]}], searches[]}
- POST /cases/{id}/published/search {terms} -> {results[...same shape without id...]} (local library index first, then PubMed E-utilities / Europe PMC with the terms only; logged; 15 s timeout; failures return {results: [], error}).
- POST /cases/{id}/published {result, quotes?} -> item (doctor adds; residents propose). DELETE /cases/{id}/published/{pid}.

## meetings.py (B3)
- GET /meetings -> {meetings[{id, date, time, room, status: planned|in_session|closed, video, counts{discussion, noting, not_ready}, agenda_sent_at}], can_manage}
- POST /meetings {date, time, room?, video: bool, minutes_per_case?} -> meeting (coordinator). PUT /meetings/{mid} same fields. POST /meetings/{mid}/cancel.
- GET /meetings/{mid} -> {meeting, agenda{discussion[row], noting[row], not_ready[row]}, code{value, expires_at}|null (coordinator only), attendance[{user, name, department, status: present|remote|absent|waiting}], current{case_id, slide, opened{kind, doc_id, study_uid}|null, timer{seconds_left, running}}, decision_live{text, by}, questions[{id, by_name, text, at, answer?}], hands[], agent{active, role, state}, can{manage, record, ask}} where row = {case_id, patient_line, owner_name, presenter_name, board_question, left_before_board, minutes, order}.
- PUT /meetings/{mid}/agenda {discussion[case_id], noting[case_id]} (order as given); POST /meetings/{mid}/agenda/add {case_id, list, reason?} (not-ready with reason); POST /meetings/{mid}/send-agenda -> notifies members; POST /meetings/{mid}/remind {case_id}.
- POST /meetings/{mid}/code -> {value, expires_at}; POST /meetings/join {code} -> {meeting_id, status: admitted|waiting} (rate limited 5 per 15 min); POST /meetings/{mid}/admit {user}; POST /meetings/{mid}/present {mode: room|remote}.
- POST /meetings/{mid}/start, /end; POST /meetings/{mid}/current {case_id, slide?}; POST /meetings/{mid}/open {kind: record|images|none, doc_id?} (coordinator or presenter; images -> grants the viewer for everyone admitted and broadcasts the viewer url); POST /meetings/{mid}/timer {action: start|stop|reset, minutes?}; POST /meetings/{mid}/questions {text} (members; shown on the room screen; answered by the stand-in agent when active via agents.ask); POST /meetings/{mid}/hand {raised}; PUT /meetings/{mid}/decision-live {text} (coordinator; broadcast, not saved); POST /meetings/{mid}/cases/{cid}/decision {outcome: decision|deferred|referred|not_discussed|noted, decision_text, rationale?, intent_as_stated?, responsible_doctor?, next_step?, next_step_date?, awaited?, awaited_from?, referred_to?, members_present[], concerns[{by, text}]} -> record (also writes the existing board record through postboard.record_decision); POST /meetings/{mid}/cases/{cid}/end -> asks the heads for their card; POST /meetings/{mid}/cases/{cid}/card {agree: bool, note?} -> card; GET /meetings/{mid}/cards -> coordinator and owner's team.
- Slides for the room: GET /meetings/{mid}/cases/{cid}/slides -> {slides[{id, title, kind: summary|values|gaps|imaging|pathology|points|published, content}]} built from slots + summary + briefs; summary first.
- Outcome message to the owner on decision (notify kind "outcome").

## live.py (B3)
- WebSocket /api/tb/meetings/{mid}/ws: authenticates from the vaidyx_session cookie (auth_manager.get_username_for_token), checks Origin == host, checks the user may open the meeting; sends {"type": "state", ...GET /meetings/{mid} payload} on connect, then events {"type": current|open|timer|decision_live|question|hand|presence|admit|end_case|agent_state|ended, ...}. Clients send {"type": "ping"} every 25 s; the server answers pong. One hub per meeting in memory.

## video.py (B3)
- GET /video/status -> {enabled, url} ; POST /meetings/{mid}/video-token -> {url: "ws://127.0.0.1:7880", token, room: "tb-<mid>", identity, name}. Keys from data/tumour_board/livekit.json (created by scripts/livekit.sh with random api key and secret, mode 600). livekit-server config in /data/vaidyx/tools/livekit/config.yaml (port 7880, rtc udp 50000-50200, dev mode off, keys file). Token signed with the LiveKit JWT (HS256) using PyJWT if installed else a small HMAC JWT.

## push.py (B3)
- GET /push/key -> {public_key}; POST /push/subscribe {subscription}; DELETE /push/subscribe {endpoint}; PUT /me/notifications {digest_time: "08:00", kinds{...}} ; GET /me/notifications. Push text never includes a UHID or name: "You have 2 new requests" style.
- Notifications store stays notifications.jsonl; new kinds: sign_off, join_request, outcome, agenda, meeting_starting, reminder_automatic, summary_stale, record_arrived.

## scheduler (B3, no endpoints except GET /scheduler/status for admins)
- tumour_board/scheduler.py: a single daemon thread started from setup_tumour_board_routes() (guarded so tests do not start it: env TB_SCHEDULER=0): every 30 min re-fetch active HIS Case Files (skip while a meeting is in_session, skip when a job is already running for the case), automatic reminders for sent requests at due date (audited by "Vaidyx (automatic)"), 08:00 digests, expiry of join codes and break-glass windows, prune. Writes data/tumour_board/scheduler.json with the last run.
