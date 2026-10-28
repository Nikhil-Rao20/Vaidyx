# The item in progress (checkpoint)

Item: 8.4 Screens, part 2 (session 11, 2026-10-28, 14:42). Committed: 8.1 a16146c, 8.2 85fa700, 8.3 (the directory commit).

Done and uncommitted: features/messages/* (the implementer), App.tsx include, e2e messages_mock.ts + messages.spec.ts + fixtures me(), components/MessageButton.tsx, nav.ts (Messages item, fitNav), AppShell MessagesIcon, Message buttons on TeamPanel, CaseHeader, PeoplePage, meeting People, RequestCard, RequestsPage, MeetingsListPage; static/tb-nik rebuilt by the implementer.

Sub-steps:
1. [ ] AppShell: mount useMessagesLive (from features/messages) once; the icon's count from the live unread query; key the page by /messages for conversation switches
2. [ ] tsc, vite build; the whole mocked suite (shell shots change on purpose: the Messages icon and nav item); fix what fails
3. [ ] restart :7000; real-screen check script docs/night-v3/tools/phase8_real_check.mjs (laptop and phone, light and dark; two logins)
4. [ ] commit 8.4 (git add -A static/tb-nik); then 8.5
