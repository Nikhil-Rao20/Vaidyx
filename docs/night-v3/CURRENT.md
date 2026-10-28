# The item in progress (checkpoint)

Item: 8.1 Messages backend (with 8.3 directory and the 8.4 feature files started in parallel; session 11, 2026-10-28).

Sub-steps:
1. [done] explorers wrote /data/vaidyx/night-v3/runs/briefs/8_facts_backend.md and 8_facts_web.md
2. [done 13:20] orchestrator wrote the contract (research/06 section 9, corrected from the fact sheets) and the briefs; shared files pre-edited (notify.KINDS, push.TEXTS + on_notification skip, live.messages_hub + broadcast hub_ + online_users, org message_retention_days, me.py counts/messages flag/_DETAIL_KEYS, routes tuple, scheduler job, web lib/live.ts messagesWsUrl, notifications.ts, types.ts, session.tsx; test_nik_me updated); messages.py skeleton (may_use, presence, Refused, constants): docs/night-v3/research/06_messages.md section 9 (routes, shapes, events, audit, limits, screens) and briefs 8.1_messages_backend.md, 8.3_directory.md, 8.4_messages_web.md under runs/briefs/
3. [doing 13:25] three implementers launched (background) (disjoint files): 8.1 tumour_board/messages.py + api/messages.py + tests/test_messages.py; 8.3 tumour_board/directory.py + api/directory.py + tests/test_directory.py; 8.4 web/tb-nik/src/features/messages/* + e2e mock + spec
4. [ ] orchestrator registers the routers in routes/tumour_board_routes.py, reviews the diffs, runs the tests, commits 8.1 then 8.3
5. [ ] 8.2 real time (live.py hub param, api/messages_ws.py, notify kind, push text, me counts, lib/live.ts, notifications.ts), commit
6. [ ] 8.4 wiring (nav, AppShell, Dock, bell, Message buttons on People/Team/meeting People/RequestCard/HeaderStrip, coordinator), build, mocked spec, real-screen check, commit
7. [ ] 8.5 live two-login check script + shots, commit; gate; reviewer; fixes; Morning summary

Files involved: see the briefs. Uncommitted work at any moment: check `git status`; the log's [PAUSED] supervisor line is expected.

Orchestrator meanwhile (13:25): the 8.4 wiring in shared web files that no agent touches: nav.ts Messages item, AppShell icon with badge, Message buttons on PeoplePage, TeamPanel, CaseHeader, meeting People, RequestCard, the Requests and Meetings page headers. The useMessagesLive mount in AppShell waits for the feature folder.

13:50: the shared wiring is DONE and type-checks (uncommitted, goes into the 8.4 commit): nav.ts (Messages item + fitNav), AppShell MessagesIcon with badge (me.counts.messages_unread), components/MessageButton.tsx (messageHref, useMayMessage, MessageButton), TeamPanel (owner, residents, consultants, department chips), CaseHeader (owner icon + "Message the MDT Coordinator" in More), PeoplePage row menu, meeting People row (new tab), RequestCard (asker or coordinator), RequestsPage and MeetingsListPage headers. Still to do after the 8.4 agent returns: mount useMessagesLive in AppShell and switch the icon's count to the live unread query; build; mocked suite; real-screen check.

14:30: all three implementers returned (8.1: 25 + 12 tests; 8.3: 20; 8.4 part 1: 8 mocked tests, 20 shots). Reviewed. Committing in order: 8.1 (backend + shared backend edits), 8.2 (live.py, messages_ws, web lib), 8.3 (directory), then the 8.4 wiring part 2 (AppShell mount, build, mocked suite, real check), 8.5.
