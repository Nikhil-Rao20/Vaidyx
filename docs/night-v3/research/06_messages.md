# Messages between logins (research for Phase 8)

Research for plan item 0.7 (feeds 8.1 to 8.5). Written 27/10/2026. Read-only on the code; this is the only file written. Code cited as file:line, the web as URLs. Where a web page could not be opened (the official Act PDF and two NHS pages answered 403 or did not resolve), the point is marked "not verified" and comes from a search summary.

## 1. Summary

1. D5 (PLAN.md:39): any placed login may message any person or any department of the same hospital; a department message reaches all members and any member may answer; a message never grants access; push carries no patient details.
2. Nothing for chat exists today except the shared team chat of one Case File (`tumour_board/chats.py`, that is "Ask this Case File", not person to person), the bell (`notify.py`), browser push (`push.py`) and a reusable `Hub` (`live.py:22`). There is no people directory (00_current_state.md:129).
3. Reuse: `notify` addresses (user, department, coordinator role) and `push.users_for` already do the department fan-out; `RateLimit` (`api/common.py:73`), `org.audit` (`org.py:259`), `profiles` (phone consent already stored) and the frontend list parts cover the rest.
4. Design: one conversation per direct pair, and one per (sender, department) or (sender, coordinator role); messages as append-only JSON lines (one file per conversation) plus an index; unread per person as a "last read number".
5. A Case File or meeting link is stored as an id only (a "chip"). Whether it shows a name or opens is decided when the reader looks, by `access.scope`. A sender can only attach a file the sender may see. Nothing is ever granted.
6. Edit and delete only your own message within 10 minutes; edits keep the old text in the file (history), deletes leave "This message was deleted".
7. "Resolved" per conversation, with who and when; a new message reopens it.
8. Real time: a second `Hub` on `/api/tb/messages/ws`, one room per user; events new message, typing, read, online. The bell gets one coalesced "message" item per conversation; push says only "New message from Dr X".
9. The coordinator and admins get no reading rights over other people's conversations; non-participants get 404.
10. India's DPDP Act 2023 asks for purpose limitation, security safeguards, breach notice, erasure when the purpose is served: so a stated retention period, no message text in the bell, push or audit, and a short rule about patient names. The owner must decide retention and patient names (section 8).

## 2. Today (what exists, what can be reused)

| Piece | Where | What it does | Reuse for messages |
|---|---|---|---|
| Notifications store | `tumour_board/notify.py:3` | `notifications.jsonl`, one JSON per line, address is exactly one of department, role (coordinator) or user (`notify.py:91-110`); `read_by {user: ts}` per person; rewrite is atomic with tmp and `os.replace` (`notify.py:80-88`); pruned at 90 days and 5000 lines (`notify.py:243`) | Same atomic write pattern for the index. A new kind `"message"` in `KINDS` (`notify.py:26`). |
| Who sees a notification | `notify._mine` (`notify.py:145-158`), `for_roles` (`:180`), `mark_read` (`:211`) | Department address reaches everyone placed there (admins see all departments: line 152, which is why messages must not ride on department-addressed notifications with text) | Reuse for the bell item only; the text of a message is never in a notification. |
| The bell | `web/tb-nik/src/components/NotificationBell.tsx:20`, `lib/notifications.ts:18` (`KIND_INFO`: label, icon, tone), `notificationLink` (`:50`), polling every 45 s (`hooks/useQueries.ts:67`) | A popover list, unread badge (`:53`), "Mark all read" | Add `message: {label: "Message", icon: MessageSquare}` and a link to `/messages?c=<id>`. |
| Browser push | `tumour_board/push.py:1-14`, `TEXTS` (`:21-50`), `users_for` (`:250`), `send_to_users(users, kind, text)` (`:291`), `on_notification` (`:317`, called from `notify.py:135-139`), prefs per kind (`wants`, `:243`), subscriptions with 404 or 410 removal | Generic texts per kind, "never a UHID or a name" (`push.py:6`); payload `{title: "Vaidyx-TB", body, kind, url: "/tb-nik"}` (`:278`) | `send_to_users` already accepts a `text`, so "New message from Dr Kavitha Raghunathan" needs no change of the sender; only the notify path uses the fixed text. Add `"message"` to `TEXTS` and to `PREF_KINDS` (`notifications.ts:71`). |
| The Hub | `tumour_board/live.py:22-102` | Rooms of sockets (`connect`, `disconnect`, `online`, `entries`), per-socket shaping via `shape(user, info, event)` (`:109-142`), thread-safe lock, `send_all` with a 2 s timeout that drops slow sockets (`:75`), `COOKIE`, `authenticate`, `origin_ok` (`:145-168`); `MAX_SOCKETS_PER_USER = 5` (`:16`) | A second `Hub()` instance. `broadcast()` uses the module's global `hub` (`:114`, `:132`); it needs a small `hub=` argument or a method on the class. |
| Meeting socket route | `tumour_board/api/live.py:1-60` | Authenticates from the cookie, checks Origin, re-checks session, first-password change, idle timeout and roles every minute (`_still_allowed`, `:36-49`) | Copy the pattern for `/messages/ws`; the check is "known, not disabled, not expired". |
| Frontend socket | `web/tb-nik/src/lib/live.ts:30-85` `LiveClient`: reconnect with backoff, ping every 25 s; `meetingWsUrl` (`:17`) | Reconnecting client | Reuse `LiveClient`; add `messagesWsUrl()`. |
| Roles | `org.roles` (`org.py:949-993`): `known`, `departments` (placements member, head, resident), `coordinator`, `disabled`, `expired`, `end_date`, `outside_expert`; `org.display_name` (`:931`) | "Placed" = `departments` not empty after expiry removal | "Placed login" in D5 = `known`, not `disabled`, not `expired`, with a placement. The MDT Coordinator has no placement (`org.py:20-22` doc): see open question 8. |
| Department members | `push.users_for` (`push.py:250-263`), `accounts.department_doctors` (`api/setup.py:396`) | List of logins placed in a department; disabled skipped | The recipient list of a department conversation, worked out at send and at read (membership is live). |
| Profiles | `tumour_board/profiles.py:15` fields: display_name, title, registration_no, phone, phone_visible, photo (data URL up to 200 KB, `:19`); `get()` (`:57`) | Phone has a "visible to signed-in hospital members" consent (`:4`) | Directory reads these; the phone only when `phone_visible`; the photo by its own route, never inside lists. |
| Where people are shown | People page `features/admin/PeoplePage.tsx` (SearchBox `:241`, DropdownMenu row actions `:11`); Case File Team panel `features/casefile/components/TeamPanel.tsx:29-33` (owner doctors `d.name`); meeting People `features/meetings/components/People.tsx:19-22` (avatar, name, department); request cards `features/requests/RequestCard.tsx`; owner in `features/casefile/components/HeaderStrip.tsx:83-84` (`ownerDept`, `ownerName`) | | Add a "Message" button in each (section 6.8). |
| Top bar and Dock | `app/AppShell.tsx:73-125` (header, main nav, `NotificationBell` at `:111`, `ProfileMenu` `:112`, `Dock` `:135`), `lib/nav.ts:6-15` `NavItem` with `badge`, `navItems` `:36`; `components/Dock.tsx:9-42` (badge on an icon `:28`) | | A "Messages" `NavItem` with `badge` = unread messages; a header icon beside the bell. |
| Counts | `api/me.py:80-97` `counts(r)` returns unread, waiting, open requests; `GET /me` carries it (`:100-111`) | The top bar's numbers | Add `messages_unread`. |
| Audit | `org.audit(kind, by, **fields)` (`org.py:259`) to `org_audit.jsonl`, read by the auditor in `GET /activity` (`api/me.py:242`); Case File audit `store.audit` (hash chained, `store.py:220`) | An event without a Case File goes to `org.audit` | Use `org.audit` with `kind="message_*"`; never the text. |
| Rate limits | `api/common.py:73` `RateLimit(limit, window)`, per login, in memory, 429 `rate_limited`; examples `api/chats.py:10`, `api/push.py:8`, `api/me.py:19` | | Same class. |
| Route guards | `api/common.py` `make_router`, `roles(request)` (`:30`), `fail(status, message, code)` (`:~48`), `body(request)`; `_need_known` (`routes/tumour_board_routes.py:211`) | | Same. |
| Access | `access.scope(r, case)` (`access.py:308-335`) FULL, REQUESTS or None; protected cases never named (`:315`, and `notify.py:47-52`); `access.refusal` (`:348`); `meetings.may_view` (used `api/live.py:45`) | | Decides whether a chip shows a title or opens. |
| Not yet there | `MicButton` (Phase 4; `grep` finds none) | | The composer takes it when Phase 4 lands (D1). |

Do not confuse with: `chats.py` (Case File questions to the AI, threads in `cases/<id>/chats.json`). Messages are person to person and live outside any Case File.

## 3. Patterns from Slack and Teams

Verification: Slack edit and delete, and Slack presence were read this session; the other cells are common product behaviour from general knowledge, marked "(general)", and were not opened. Teams "mark as resolved" was searched: a community request says Teams does not offer it for channel posts (not official).

| Pattern | Slack | Teams | What we take | URL |
|---|---|---|---|---|
| Direct and group messages | DMs and group DMs (general) | 1:1 and group chats (general) | Direct between two people only; no group chat (D5 has only person or department). A department conversation takes the place of a group. | n/a |
| Channels as conversations with a team | Channels (general) | Channels in a team (general) | A department conversation, started by one person, visible to all members; not a standing room for everyone. | n/a |
| Threads | Reply in thread (the help page only says "use threads to organise discussions") | Replies under a post (general) | Version 1 is one flat thread per conversation. A conversation is already a thread; real sub-threads are not needed. | https://slack.com/help/articles/360017938993-What-is-a-thread |
| Reactions | Emoji reactions (general) | Reactions (general) | A small fixed set (thumbs up, "seen", "thanks", "will do", tick), one per person per kind. | n/a |
| Mentions | `@person`, `@channel` (general) | `@person`, `@channel`, `@team` notify everyone (a training resource says so) | `@person` only; in a department conversation `@name` notifies one member more strongly. No `@everyone`. | https://my.mandarine.academy/en/training-resources/posting-in-a-channel-2 |
| Unread and badges | Bold name and count (general) | Bold chat, count (general) | Unread per person per conversation (a last-read number), a badge on "Messages", bold row. Epic does the same: bold and a count bubble. | https://www.methodisthealthsystem.org/documents/epic%20tip%20sheets/Secure-Chat-in-Rover_0729.pdf |
| Presence | Active or away; auto-away after about 10 minutes of no activity; Do Not Disturb | Available, Busy, Away, DND (general) | Online (an open socket and recent activity), away, offline; no "busy". Shown only on the Messages page and the directory. | https://docs.slack.dev/reference/methods/users.getPresence |
| Typing indicator | In channels and threads | General | "Dr Sanjay Joshi is typing" in direct and department conversations; throttled; an owner decision whether to show it (open question 7). | https://www.techradar.com/news/slack-is-making-a-tiny-but-vital-change-that-superfans-will-love |
| Search | Messages, people, files (general) | Same (general) | Search inside the person's own conversations by words and by person; server side, only conversations the person is in. | n/a |
| Done or resolved | "Later" saved items and reminders (general, not verified) | No official "mark as resolved" in channels (community request) | A "Resolved" state per conversation, with who and when, filter "Open / Resolved". This is our own, and it fits requests like "please send the PET report". | https://community.moveworks.com/ideas/feature-request-teams-channel-resolver-like-we-have-for-slack-1152 |
| Edit and delete | Members may edit and delete their own messages by default; owners and admins can restrict this; unsend only within 15 seconds on desktop; deletion is permanent; admins can delete members' messages in channels and group DMs they belong to | General | Edit and delete own within 10 minutes (D5 item 8.1); old text kept in the file, "edited" label; deleted shows a tombstone; no admin deletion in the app (open question 3). | https://slack.com/help/articles/202395258-Edit-or-delete-messages |
| Retention | Paid-plan owners can set a retention policy that deletes messages after a set time | Retention policies (general) | A hospital retention period, run by a daily job (open question 1). | https://slack.com/help/articles/202395258-Edit-or-delete-messages |
| Mute | Mute a conversation (general) | Mute a chat (general) | "Mute" per person per conversation: no push and no bell item, the unread mark stays. | n/a |
| Phone layout | List screen then thread screen (general) | Same (general) | Two screens under 1024 px: list, then thread with a back arrow. | n/a |

## 4. Clinical secure messaging

| Idea | Epic Secure Chat | TigerConnect | NHS guidance | What we take |
|---|---|---|---|---|
| Patient-linked conversations | Chat can be attached to a patient from the chart (Treatment Team section); colleagues can jump to the chart; a list of recently opened charts to attach. A legal note says chats are not formally part of the record but can be discoverable in litigation. | n/a | Messaging is not a substitute for the medical record: advice received should be put in the record and the original messages deleted. | A Case File chip, id only. The chip opens the file only if the reader may. A line under the composer: "Decisions go in the Case File, not here." |
| Role-based delivery | Not found | Messages to a role ("on-call hospitalist") go to whoever holds the role at that time; staff opt in to shifts | n/a | We have no rota, so: a message to a department reaches all members; "Message the MDT Coordinator" reaches the coordinator role. Rota-based "on call" is out of scope. |
| No patient details in push | Not found in what was read | Vendor pages do not say (not verified) | Fully encrypted services useful; clinicians stay bound by confidentiality | Push says only "New message from Dr X" (D5); the bell shows the sender and "New message" and no text. |
| Read receipts | Read receipts and typing indicators, availability (Offline, Do Not Disturb) | Sent, delivered, read; closing the loop matters for clinical messages | n/a | Read receipts shown only in direct conversations as "Seen"; not for departments (many readers). Owner decision (open question 6). |
| Escalation | Not found | Priorities, auto-escalation, fallback recipients, broadcast to teams | n/a | Not in version 1. A department conversation unanswered for a stated time may later raise a reminder through the existing scheduler (`scheduler.py`); list as a Parking lot idea. |
| Lifespan and audit | Monitoring and compliance discussed (mindbowser) | Admins adjust message lifespan, recall permissions, archiving and auditability (third-party summary) | Policy and retention set by the organisation | A retention period and an audit line per action (never the text). |

URLs: https://hmhmaestro.org/en/action-center/it-alerts/2021/04/22/epic-secure-chat-launching-on-monday-april-26 ; https://www.reedsmith.com/our-insights/blogs/viewpoints/102o1ly/when-the-chat-becomes-the-chart-radiologists-should-pause-a-beat-and-think-befor/ ; https://www.methodisthealthsystem.org/documents/epic%20tip%20sheets/Secure-Chat-in-Rover_0729.pdf ; https://it.houstonmethodist.org/secure-chat-communication-tool-epic-update-enhancements/ ; https://tigerconnect.com/wp-content/uploads/2021/09/TCCPPro-Overview-Roles.pdf ; https://tigerconnect.com/wp-content/uploads/2021/08/Collaborative-Communication-Types-in-TigerConnect.pdf ; https://zoftwarehub.com/en-bh/products/tigerconnect/zoftware-analysis ; https://www.england.nhs.uk/2018/11/instant-messaging-services-a-vital-part-of-the-nhs-toolkit-during-a-crisis/ ; https://www.digitalhealth.net/2018/11/nhs-issues-guidance-use-of-instant-messaging-apps/ ; https://sfh-tr.nhs.uk/media/qu0lptlk/instant-messaging-guidance.pdf . The current NHS England page ("Using mobile messaging software in health and care settings", on transform.england.nhs.uk) did not resolve from here: not read. The NHS 2018 points above come from search summaries.

India, clinician chat: the Telemedicine Practice Guidelines 2020 (MoHFW and NMC, https://covid19dashboard.mohfw.gov.in/pdf/Telemedicine.pdf) are about a doctor and a patient: consent, keeping a record of chats, the registration number on electronic communication (summary: https://factly.in/explainer-what-is-in-the-new-telemedicine-guidelines-notified-by-the-government). They say nothing, in what was found, about clinician to clinician messaging. ABDM guidance on it was not found. Not verified: the full text.

## 5. India's DPDP Act 2023 and this feature

Source: the Act, https://www.indiacode.nic.in/bitstream/123456789/22037/2/a2023-22.pdf (403 from here, so not read directly). Section summaries come from the ICAI note https://palakkad.icai.org/detail/56514.aspx (a secondary summary, not the Act). The Rules of 13/11/2025 come from commentary only (https://www.mondaq.com/india/data-protection/1708164/digital-personal-data-protection-rules-2025-notified). Sub-section numbers inside section 8 should be checked against the Act. Commencement: commentary says most obligations start 18 months after 13/11/2025 (about 05/2027); one source shows a phase in 11/2026: check the gazette. Build as if in force. This is not legal advice; the hospital's own data protection lead should read it.

The hospital is the data fiduciary; Vaidyx is a tool it runs on its own server (no data leaves it). Personal data here: staff names, phone, photo (directory), message text, and anything a clinician types about a patient.

Section numbers unverified until checked against the Act's text (the points stand; the numbers come from a secondary summary).

| Section | Point | What we do |
|---|---|---|
| 4 and 5 | Process on consent or a legitimate use; plain notice of purpose, data, retention, rights | A one-time notice on first use of Messages: purpose (work messages between hospital staff), what is kept and for how long, who can read, how to ask for erasure. Staff are in employment; section 7 lists "employment purposes". Wording by the hospital. |
| 6 | Consent free, specific, withdrawable | Phone and photo in the directory stay opt-in (`phone_visible`, `profiles.py:15`); a person can hide the phone any time. Messaging itself is a work duty, not consent based; the notice says so. |
| 7 | Legitimate uses, including employment and medical emergency | Staff messaging under the employment use. The emergency use is not relied on. |
| 8 (accuracy, purpose, minimisation) | Keep data for the stated purpose | Text limit 2000 characters; no files in version 1 (a file is a record: use the Case File); a soft warning on UHID, ABHA or phone-like patterns in the text (plain pattern check, not a model); the Case File chip is the way to point to a patient. |
| 8 (security safeguards; Rules summary: encryption, access control, logs, backups, logs kept at least one year) | Reasonable safeguards | Same-origin, cookie session, per-request permission check, socket re-check every minute (pattern `api/live.py:36`), 404 for non-participants, files under `data/tumour_board/messages/` mode 600 (as `profiles.py:45`), audit log of actions without text, kept at least one year (Rules, commentary). Disk encryption and backups are the host's duty: list in the security audit of Phase 9. |
| 8 (breach intimation; 72 hours to the Board per commentary) | Tell the Board and the people affected | An audit kind `message_access_denied` and counts help find a breach; the break-glass style owner notice is not needed for messages. The hospital's incident procedure applies; add one line to the runbook. |
| 8 (erasure when the purpose is served or consent is withdrawn) | Erase on request or when no longer needed | A retention period with a daily job removing message text (conversation file rewritten without text, tombstones kept) after N days; a root-admin "erase this person's messages" is not offered (open question 3). |
| 8 (grievance) | A way to complain | Link "Report a problem with a message" to the coordinator or data protection contact the hospital names in Organisation settings (a new optional field). |
| 9 | Children's data | No patient identifiers in messages by rule; the soft warning covers this. |
| 10 | Significant data fiduciary: a data protection officer, impact assessment, audit | Only if the Government designates the hospital group; nothing to build now. Note it in the Phase 9 security audit. |
| 11 to 14 | Access, correction, erasure, grievance, nominee | A person can see what they sent (their own conversations); "Download my messages" (JSON) and the erasure request go to the hospital's data protection contact (open question 1 and 3). Edit window is 10 minutes: later corrections by a new message. |
| 17 | Exemptions (legal claims, research) | None relied on. |

Rule of thumb that follows: never put message text in notifications, push, audit lines, logs or the activity page.

## 6. The proposed design (inside D5)

### 6.1 Who may use it and who may be reached

- May use Messages: `r.known` and not disabled and not expired and (placed in a department or `coordinator`). A root admin, auditor or outside expert with no placement may not (no clinical role, and the root admin must not become a back door). A Vaidyx admin with no placement may not. No message action creates or changes any account or role (CLAUDE.md "Roles").
- May be reached: the same set, in the same hospital (one hospital per install, `org.hospital()`).
- The coordinator and admins get no extra rights to read: a conversation is readable only by its participants (section 6.3).
- Open question 8: whether the unplaced coordinator counts as "placed" (this design says yes, so "Message the MDT Coordinator" works).

### 6.2 Data model

Conversation (in `index.json`, small):
```
{"id": "C7f3a91c2", "kind": "direct" | "department" | "coordinator",
 "created": "2026-10-27T10:12:00", "created_by": "dr.sanjay",
 "people": ["dr.sanjay", "dr.kavitha"],        // direct: exactly two; department / coordinator: the sender only
 "department": "radiology",                      // kind department
 "last_seq": 14, "last_ts": "...", "last_by": "dr.kavitha",
 "resolved": null | {"by": "dr.sanjay", "ts": "..."}}
```
- Direct: one per pair (found or created). Department: one per (sender, department): "Dr Sanjay Joshi to Radiology". Coordinator: one per sender. The readers of a department conversation are the sender plus everyone placed in that department now (live, like `push.users_for`); the readers of a coordinator conversation are the sender plus the coordinators. A member added later sees the earlier messages (it is a shared mailbox); a member who leaves stops seeing it (open question 9).
- Messages are events in `c_<id>.jsonl`, append only, each with `seq` (1, 2, 3...):
  - `{"seq": 1, "t": "msg", "id": "M...", "ts": "...", "by": "dr.sanjay", "text": "...", "link": {"type": "case", "id": "TB-2026-0042"} | {"type": "meeting", "id": "..."} | null, "mentions": ["dr.kavitha"]}`
  - `{"t": "edit", "of": "M...", "ts": "...", "by": "...", "old": "...", "text": "..."}` (valid only if the original is by the same person and less than 10 minutes old; the old text stays in the file: "history kept")
  - `{"t": "delete", "of": "M...", "ts": "...", "by": "..."}` (same window; the UI shows "This message was deleted"; the text stays in the file until retention removes it)
  - `{"t": "react", "of": "M...", "by": "...", "emoji": "ok" | null, "ts": "..."}` (null removes)
  - `{"t": "resolve", "by": "...", "ts": "...", "resolved": true|false}`; a new `msg` in a resolved conversation sets `resolved` to null (event `reopen`, audited).
- Read state: `reads.json` `{user: {conv_id: {"seq": 12, "muted": false}}}`. Unread of a conversation = number of `msg` events with `seq` above the person's last read and `by` not the person. Total unread = sum over the person's visible conversations (for a department conversation the person is a reader of).
- Mentions: parsed from `@login` tokens chosen from the directory, stored as ids (max 8). A mention only raises the notification; it never adds a reader.
- Limits: text 1 to 2000 characters; no HTML, shown as text; max 500 messages loaded per page (`before=` paging); a conversation file is rewritten only by the retention job.
- Case File chip: the id only. At read time the server returns for each chip `{"type", "id", "label", "can_open"}`: `label` is the Case File's title only if `access.scope(r, case)` is not None, else "A Case File you cannot open"; protected cases and deleted ones give no name. At send time the sender must have scope on the case (or `meetings.may_view` for a meeting), so a person cannot probe ids. Opening a chip is the normal `/cases/<id>` route, which refuses as today (with the break-glass offer from Phase 1 where it applies). Nothing is written to `access` or the team.

### 6.3 Storage

- `data/tumour_board/messages/index.json` (conversations), `reads.json`, `c_<id>.jsonl` (one file per conversation), all mode 600, under one process lock (as `notify._lock`, `notify.py:42`). Appends go to the jsonl with flush and fsync under the lock; the index and reads files are written to a `.tmp` and `os.replace`d (pattern `notify._rewrite`, `notify.py:80`). A malformed line is skipped, never fatal (as `notify._load`).
- Message text lives only here. Not in notifications, not in `org_audit.jsonl`.
- Kept how long: proposed default 365 days after the last message of a conversation, then the text is removed (the events stay as "removed" so unread counts and the audit still make sense); a setting in Organisation. The audit lines (no text) are kept as the activity log is. Open question 1.
- Synthetic data only in tests.

### 6.4 Routes (all under `/api/tb`, made with `common.make_router`; every one starts with `may_use(r)`, else 403 `not_placed`)

| Route | Purpose | Permission beyond may_use | Audit kind (to `org.audit`; fields: conversation id, kind, target; never text) | Rate limit per login |
|---|---|---|---|---|
| `GET /messages/conversations?filter=all\|unread\|open\|resolved&q=` | The left list: last message preview (own conversations only), unread, resolved, muted, other person's name and online state | Only conversations the person reads | none (reading the list is not audited, to avoid noise); denied access is | 120 per minute |
| `POST /messages/conversations` `{to: {user}\|{department}\|{role: "coordinator"}, text, link?}` | Start, or add to the existing one | Target must be a reachable person or an existing department; not yourself | `message_sent` (new: `conversation_started`) | 10 new per 10 minutes |
| `GET /messages/conversations/{id}?before=` | Open: messages, readers, chips | Participant, else 404 (never 403: does not reveal existence) | none; opening does not mark read | 120 per minute |
| `POST /messages/conversations/{id}/messages` `{text, link?, mentions?}` | Send | Participant | `message_sent` | 30 per minute |
| `PATCH /messages/{conv}/{mid}` `{text}` | Edit | Own message, within 10 minutes, not deleted | `message_edited` | 20 per minute |
| `DELETE /messages/{conv}/{mid}` | Delete | Own, within 10 minutes | `message_deleted` | 20 per minute |
| `POST /messages/{conv}/{mid}/react` `{emoji\|null}` | React | Participant | `message_reacted` | 60 per minute |
| `POST /messages/conversations/{id}/resolve` `{resolved: bool}` | Mark resolved or reopen | Participant (any department member may resolve) | `conversation_resolved` or `conversation_reopened` | 30 per minute |
| `POST /messages/conversations/{id}/read` `{seq}` | Mark read up to | Participant | none | 120 per minute |
| `POST /messages/conversations/{id}/mute` `{muted}` | Mute | Participant | none | 30 per minute |
| `GET /messages/search?q=` | Search text and names across my conversations | Only conversations the person reads; min 2 characters | none | 30 per minute |
| `GET /messages/unread` | The badge number (also `messages_unread` in `GET /me` counts, `api/me.py:80`) | any | none | 120 per minute |
| `GET /directory?q=&department=` | People and departments | see 6.6 | none | 60 per minute |
| `GET /directory/{user}/photo` | The photo | any user of Messages | none | 120 per minute |
| `WS /messages/ws` | Live events | session checks of `api/live.py:36` | none | typing events 1 per 3 seconds |

Denials audit `message_denied` (route, conversation id) at most once a minute per login, so probing shows in the activity log. The routes never trust a client-sent sender or time. Edit window: server clock, `now - ts <= 10 minutes`.

### 6.5 Real time

- `live.messages_hub = Hub()` (a second instance). One room per user, `"u:<login>"`; every socket of the user joins it (cap 5 sockets per user, the existing constant). A send computes the readers of the conversation now (direct: the pair; department: the members; coordinator: the coordinators and the sender) and sends one event to each reader's room. The per-socket shaping function of `live.broadcast` is used to drop a socket whose user lost access since it connected. Required small change: `broadcast` takes `hub` as an argument (`live.py:109`).
- Events to client: `message` (conversation id, seq, sender, text, link chips, mentions), `edit`, `delete`, `react`, `resolve`, `read` (direct only: "Seen"), `typing` (conversation id, person; throttled), `presence` (login, online or away), `unread` (new total for the badge), `pong`. From client: `ping`, `typing`, `active` (moves away to online; the client sends it on activity, away after 10 minutes of none, as Slack).
- Presence: online = the login has a socket in the hub (`Hub.online`-style, over all rooms); away after 10 minutes without `active`. Shown only in the Messages page and the directory, and only for people who may use Messages. Open question 7.
- Fallback: the list and the unread poll every 45 s as the bell does (`hooks/useQueries.ts:67`), so a dead socket loses nothing (a message is stored before it is pushed; a reconnect fetches the list again).
- The bell: `notify.notify({"user": login}, "message", "", "New message from Dr Kavitha Raghunathan", "", conversation_id=...)` per reader, coalesced: if the reader has an unread "message" item for this conversation, it is not duplicated. The title holds the sender name only; the text field is empty; no Case File id (so the notification is not purged with a case). It is marked read when the conversation is read (`notify.mark_read` with the ids). Muted conversations and people who are online and looking at the conversation get no bell item and no push. A department conversation is addressed per user (not `{department}`), because `notify._mine` shows department notifications to admins as well (`notify.py:152`), and admins have no right to a department conversation.
- Browser push: `push.send_to_users(users, "message", "Vaidyx-TB: New message from Dr Kavitha Raghunathan")`. Nothing else: no text, no Case File, no department of the patient. The preference `kinds.message` in `notify_prefs.json` (`push.py:243`) lets a person switch it off. Coalescing: at most one push per conversation per 5 minutes.

### 6.6 Directory

`directory.search(r, q, department)` in a new `tumour_board/directory.py` reading `org.load()["users"]` and `profiles.get`:
- Included: every login that may use Messages (placed, not disabled, not expired, plus coordinators). Excluded: disabled, expired, unplaced accounts, outside experts, auditors without a placement.
- Fields: `user`, `display_name`, `title`, `departments` [{id, name, role: "Head" | "Consultant" | "Resident"}], `coordinator` (the MDT Coordinator badge), `online`, a `photo` URL; `phone` only when `phone_visible`; never registration number, never admin flags (`root_admin`, `admin_of`, Vaidyx admin), never e-mail.
- Departments: a second list `departments: [{id, name, group, members: n}]` so a person can message "Radiology". Only departments that have at least one member.
- Search by name, title and department name, case insensitive, prefix match; at most 30 results; the 60 per minute limit and the "phone only when visible" rule protect against harvesting.

### 6.7 Screens (plain words)

Top bar: a "Messages" icon with an unread badge beside the bell (`AppShell.tsx:111`), and a "Messages" item in `navItems` for those who may use it, with `badge` (`nav.ts:14`) so the phone Dock shows it (`Dock.tsx:28`). If the Dock would pass five items, the Dock keeps the first four and "Messages" moves into the profile menu on phones; the header icon stays.

Messages page `/messages` (desktop, two columns):
- Left: a "New message" button; a SearchBox "Find a person, a department or a word"; filter tabs "All", "Unread", "Open", "Resolved"; the rows (`DataList` and `DataRow`, `components/DataList.tsx:9`): avatar with an online dot, the name (or the department name with the sender "Dr Sanjay Joshi to Radiology"), the last line, the time (`DateText`), a bold name and a count for unread, a `StatusPill` "Resolved" (tone ok) and a small bell-off icon for muted.
- Right: header with the person's name, title and department, or the department with "Reaches 6 people"; a "Mark as resolved" button (toggles to "Reopen"); "Mute". Messages grouped by day (reuse `groupByDay`, `notifications.ts:59`), own on the right; "edited" next to the time; "Seen" under the last own message in a direct conversation; reactions under a message; the hover menu "React", "Edit", "Delete" (the last two shown for 10 minutes: "You can edit for 8 more minutes"); Case File chips: "Case File: TB-2026-0042" or "A Case File you cannot open" (grey, not clickable); meeting chips the same; "Dr Kavitha Raghunathan is typing".
- Composer: a growing text box "Write a message", the MicButton (Phase 4, speech fills the box, the person edits and sends: D1), a paperclip-less "Add a Case File" picker that lists only Case Files the person can open, a counter at 1800 characters, "Send". A line under it: "Do not type patient names or numbers here. Attach the Case File. Decisions go in the Case File." A soft warning, not a block, if the text looks like a UHID, ABHA or phone number: "This looks like a patient number. Attach the Case File instead? Send anyway".
- First use: a short notice card (section 5) with "Got it".
- Empty states (`EmptyState`): "No messages yet" with "Find a person to message"; "Nothing unread" under the Unread filter; "Nothing resolved yet". Errors: "You can only edit a message for 10 minutes." "Too many messages. Please wait a moment." (the 429). "That person cannot be reached." "You cannot message yourself."
- Phone (under 1024 px): the list full width; tapping a row opens the thread full screen with a back arrow "Messages"; the composer sticks above the Dock; New message opens a full-screen finder.
- New message finder: a dialog (existing `Dialog`) with the SearchBox over the directory: two groups "People" and "Departments", plus "MDT Coordinator" at the top; each row shows name, title, department, role.

"Message" buttons (a link to `/messages/new?to=<login>`, `?dept=<id>` or `?coordinator=1`, optional `&case=<id>` to put the chip in, only when the sender may open the case):
- People page: in the row menu (`PeoplePage.tsx`, DropdownMenu): "Message".
- Case File Team panel: beside each doctor name (`TeamPanel.tsx:32`) and the department rows: "Message"; with the Case File chip pre-attached.
- Meeting People panel: a small icon on each attendee (`People.tsx:19`); in a live meeting it opens in a new tab so the room is not left.
- Request cards: "Message the department" (to the department the request went to or came from) with the Case File chip.
- Case File header: the owner's name (`HeaderStrip.tsx:84`): "Message the owner".
- Anywhere: "Message the MDT Coordinator" (Case File page menu, Meetings page, Requests page), to the coordinator role.

Components reused: `DataList`/`DataRow`/`RowSkeleton`, `SearchBox`, `EmptyState`, `ErrorState`, `StatusPill` (`Pill`), `DateText`, `Dialog`, `DropdownMenu`, `Textarea`, `ConfirmDialog` (delete), `notify` toasts, `LiveClient`, the bell (`NotificationBell`, `KIND_INFO`), `Dock` badge, `initials` and avatar helpers (`PeoplePage.tsx:31`). New: `MessagesPage`, `ConversationList`, `Thread`, `Composer`, `DirectoryPicker`, `useMessagesLive`.

## 7. Tests

Unit (`tumour_board/tests/test_messages.py`, synthetic users Dr Kavitha Raghunathan, Dr Sanjay Joshi, a Radiology member, a Pathology member, a coordinator, a root admin, an auditor, an expired resident):
- Permissions: a placed login may message another and a department; an unplaced root admin, an auditor, an outside expert, a disabled and an expired login may not (403); the coordinator and a root admin cannot read a direct conversation between two doctors (404); a non-participant opening an id gets 404, the same as a missing id.
- Department fan-out: a message to Radiology is readable by every current member and the sender; a Pathology doctor gets 404; a member added later sees the history; a member removed (or expired) loses it; any member's reply is read by the sender and the other members.
- Unread: counts by person; sending does not count for the sender; reading to `seq` clears; per-person independence in a department conversation; mute keeps the count but no bell item.
- Edit and delete: allowed at 9 minutes 59 seconds, refused at 10 minutes 1 second (patch the clock); another person's message refused; the edit keeps the old text in the file; the delete shows the tombstone.
- Resolve: by whom and when are stored; a department member other than the sender can resolve; a new message reopens and is audited.
- A link grants nothing: attach a Case File the sender may open; the recipient with no scope gets `can_open: false`, no label, `access.scope` unchanged, the Case File route still refuses, the team and participants lists unchanged; a sender with no scope cannot attach it; a protected Case File never gets a label; a deleted case gives no label.
- Push and bell text: the push text equals "Vaidyx-TB: New message from Dr Kavitha Raghunathan"; no message text, no UHID, no Case File id or patient name in the push payload, the notification record or any `org_audit.jsonl` line (assert on a message that contains a fake patient name and a fake UHID).
- Limits: 2001 characters refused; rate limits give 429 `rate_limited`; typing throttle.
- Storage: atomic index rewrite survives a crash between tmp and replace (simulate); a malformed line is skipped; two threads sending at once give distinct `seq` numbers; retention removes text only after N days.
- Directory: no phone unless `phone_visible`; no registration number or admin flags; disabled and expired excluded.
- No account is created or changed by any route (assert `org.json` and the accounts file are byte-identical after a run).

Live check, item 8.5 (two real browser logins, synthetic accounts, localhost only): Dr Sanjay Joshi (Surgical Oncology) opens Messages and writes to Dr Kavitha Raghunathan (Radiology): her badge goes to 1 within a second and her bell shows "New message from Dr Sanjay Joshi"; she opens it, "Seen" appears for him; typing shows both ways; she resolves it; he sees "Resolved". Then Dr Joshi writes to the Radiology department: both Radiology logins see it, the second answers, the first sees the answer; a Pathology login sees nothing. A Case File chip is sent to a login with no access: it shows "A Case File you cannot open" and opening the case page still refuses. Kill the socket: the 45 s poll catches up. A push subscription (if keys exist) shows only the generic text. Screenshots at 1440 and 390 px.

## 8. Open questions for the owner

1. Retention: how long are messages kept (proposed 365 days after the last message, then the text is removed)? The DPDP Rules summary says logs at least one year: a hospital data protection lead should confirm.
2. Is the first-use notice (purpose, retention, who can read) acceptable, and who is named as the contact for complaints and erasure requests?
3. May an admin or the hospital delete a message after the 10 minutes on request (for example a message with a patient name in it)? This design says no admin deletion in the app; the removal is done by the retention job, or by a hospital procedure on the server, audited. Is that enough? Also: does an erasure request under the Act remove a person's own messages even when others have replied?
4. Patient names: may a patient's name or number appear in message text at all, or only through a Case File chip? The design warns and does not block. A hard block on UHID, ABHA and phone patterns is possible.
5. Reactions: the small fixed set is enough?
6. Read receipts: shown ("Seen") in direct conversations only, never in department ones? Or not at all, or always (as Epic)?
7. Presence and typing: show online and typing to every placed login, or only inside a conversation, or not at all? (Some hospitals do not want staff to be watched.)
8. Who counts as "placed": the MDT Coordinator has no department placement (`org.py:20`). This design lets the coordinator use Messages and be messaged ("Message the MDT Coordinator"). Should a root admin, an auditor, an outside expert or a department admin with no placement also be reachable? (This design: no.)
9. Department conversations: should a doctor who joins the department later see the earlier messages (this design: yes, it is a shared mailbox), and one who leaves lose them?
10. Does a department message wait for a named person or should "unanswered for 24 hours" raise a reminder to the department (the escalation idea of TigerConnect)? Left out of version 1.
11. Bell and Dock: one "message" bell item per conversation (coalesced) is proposed. Should the Messages badge also count in the bell's badge, or only on its own icon? (Proposed: its own icon only; the bell shows the item.)
12. Groups: version 1 has only person to person and person to department. Is a small group of chosen people (for example "the lung board team") wanted later?
