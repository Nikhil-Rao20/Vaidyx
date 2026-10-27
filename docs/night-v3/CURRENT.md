# The item in progress (checkpoint)

Item 5.1 The call shell (Phase 5, session 7, started 12:09 IST 27 Oct 2026).

Done so far (uncommitted, in the tree):
- Backend: meetings.py agents_view() (every absent head's agent as a list), spotlight() (coordinator, max 3, cleared on the next case, audited), react() (four kinds, 2 s gap, broadcast only, audited without the kind); view() carries agents and spotlight; the current, admit and start events carry agents (and spotlight [] on a case change); routes POST /meetings/{mid}/spotlight and /reaction; 3 tests in test_nik_meetings.py (35 green in the meeting, live and video suites).
- Frontend contract: lib/live.ts (AgentInfo, QuorumInfo, PresenterInfo, ChatMessage, ReactionEvent; MeetingState.agents/spotlight/quorum/chat/presenting/present_allowed, current.presenter/elapsed_seconds; applyLiveEvent merges agents, spotlight, agent_state by role, chat, presenting, present_allowed), api.ts (setSpotlight, sendReaction), call/types.ts (CallCtx, CallActions, CallVideo, REACTIONS, SHORTCUTS...), call/context.ts (useCall). tsc clean.
- Brief: /data/vaidyx/night-v3/runs/briefs/5.1_call_shell.md (sections A shell+pages, B stage+strip+video lib, C panels).

Next: three implementers launched at once on the brief's sections (A, B, C). Then: tsc, vite build, the mocked meetings spec, real screens (member, coordinator, room at 1366 and 390), commit N3-5.1.
If resumed mid-way: check `git status` for call/*.tsx files; finish what is missing per the brief.
