# The item in progress (checkpoint)

Item: 8.2 Real time (session 11, 2026-10-28, 14:38). 8.1 committed a16146c.

Sub-steps:
1. [done by the 8.1 implementer] tumour_board/api/messages_ws.py (WS /messages/ws, presence, typing), live.py (messages_hub, broadcast hub_, online_users), tests/test_messages_ws.py (12)
2. [done by the orchestrator] web lib: live.ts messagesWsUrl, notifications.ts message kind + link + pref, types.ts Notification.conversation, session.tsx counts.messages_unread + me.messages
3. [ ] commit 8.2 (those files + this log); then 8.3 commit (directory.py, api/directory.py, tests/test_directory.py; done, 20 tests); then 8.4 part 2: mount useMessagesLive in AppShell, live badge, page key for /messages, build, mocked suite (shell shots change on purpose: the Messages icon and item), restart :7000, real-screen check; 8.5 live two-login check.
