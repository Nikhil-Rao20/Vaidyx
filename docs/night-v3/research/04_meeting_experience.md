# The meeting experience (research for Phase 5)

Item 0.5 of `docs/night-v3/PLAN.md`; feeds items 5.1 to 5.6. Read-only research on 27 Oct 2026. Code paths are relative to the repository root; `web/tb-nik/src/features/meetings` is shortened to `mt/` and `web/tb-nik/src/lib` to `lib/`. Baseline screenshots: `/data/vaidyx/night-v3/baseline/2026-10-27/`.

## 1. Summary

1. Today there are three separate in-call screens (member `MemberViewPage.tsx`, coordinator `components/ControlView.tsx`, room `MeetingRoomPage.tsx`) that share only small pieces (`Stage.tsx`, `VideoTiles.tsx`). Each has its own layout and its own button set, so a person who changes role sees a different product.
2. LiveKit carries only camera and microphone. The "shared screen" is app state (a slide, a record page, or the image viewer in an iframe), pushed over the app WebSocket. Screen share, chat, reactions, pin or spotlight, device change after joining and connection quality are not used (`lib/video.ts:54-110`).
3. The proposal is one `CallShell` used by all three: a main stage, a participant strip, a bottom control bar, one side panel at a time, and an agenda rail. The room screen is a variant (large type, no bar, no own camera tiles by default).
4. The stage shows one of: a case summary slide, a record page, the images, the Staging card, a shared screen (LiveKit), or a grid when nothing is presented. Everything the coordinator shows today still works; "present a screen" is added beside it.
5. Pin is per person (local only, as in Zoom "Pin" and Teams "Pin for me"); spotlight is by the coordinator for everyone (Zoom "Spotlight for everyone", Teams "Spotlight for everyone"). Spotlight is stored on the server so it survives a reload.
6. The bottom bar follows Meet and Teams order: mic, camera, present, raise hand, reactions, chat, people, agenda, more, leave. The coordinator adds next case, timer, decision, end meeting. Leave sits away from mic and camera, as Meet does.
7. Specialty agents (D2) are tiles in the strip and rows in the People and Agents panels, labelled "Radiology, AI agent standing in", with true states (ready, listening, thinking, speaking), never counted in "in the room" or in the quorum.
8. A quorum line sits in the agenda rail: heads present out of the hospital's heads, agents standing in (shown apart), and the PM-JAY composition (Surgical, Radiation and Medical Oncology present as people). It is information, not a gate.
9. New backend pieces: chat messages kept with the meeting record, a screen-share permission, a spotlight field, reactions, token grants for screen share and data, and a few live events. Chat and reactions go on the existing app WebSocket (audited and kept), not on LiveKit's data channel, so they are stored and replayable; LiveKit data is used only for transient things.
10. Open questions for the owner are in section 9 (chat kept in the record, who may present, whether agents speak in the call audio or only on the room screen, captions).

## 2. Today's screens

### 2.1 Member view (`/meetings/:id/member`, `mt/MemberViewPage.tsx`)

Frame: `StageFrame` (full-window dark `fixed inset-0 z-50`, `components/Stage.tsx:25-32`), top bar, main area, control bar.

- Top bar (`MemberViewPage.tsx:141-150`): Vaidyx mark; "Tumour Board · date time" (hidden under 640 px); the current case headline and "Board question"; then `TimerBadge`, `LiveDot` (live channel state), "I am remote / I am in the room" button (calls `present`), and `CallButton` (a popover of phone numbers to dial in, lines 27-48).
- Waiting state (152-159): a card "Waiting for the coordinator to admit you".
- Main (161-196): left column holds `SharedScreen` (the stage) with a Follow or Step away badge, previous and next slide arrows while stepped away, `SlideDots`, the live `DecisionStrip`, and (below 1024 px) a row of tiles. At 1024 px and above a right column (`w-52 xl:w-60`) holds `TileGrid` as a column and the `AgentTile` (lines 176-179). Panels `People` and `Questions` are `StagePanel`s that open to the right of the stage (180-195); both may be asked for through the bar, one per toggle (`toggle`, line 136), so only one is open.
- Control bar (199-215), in order: Mute/Unmute, Camera (or "Join video" if the person skipped the pre-join), Raise hand / Lower, Follow / Step away, Questions (badge = count), People (badge = count), "Your card" (only after the coordinator ends a case and asks for it), Leave. Left of the bar: video error or "Joining the video"; right: room name and count. Leave simply navigates to `/meetings/:id` (line 214); it does not end the audio tracks explicitly, the hook cleanup does (`lib/video.ts:94`).
- Works: pre-join with preview, device choice and mic meter (`mt/components/PreJoin.tsx`); follow or step away through the slide set; question to the room (`askQuestion`); hand over the app channel; end-of-case card (`CardDialog.tsx`); screen-reader announcements through `useAnnounce` (lines 56, 75-80).
- Missing: no screen share, no chat, no reactions, no pin or spotlight, no device change after joining, no connection-quality indicator, no reconnect banner (only the small `LiveDot`), no agenda, no case panel, no keyboard shortcuts, no full screen, no captions. The agent tile is a separate card, not a participant.
- Baseline: `real-treating-meeting-demo-member-view-dark-1366.png` and `...-390.png` show only "You have not joined this meeting" (the baseline user was not admitted, so the in-call member screen is not captured; `real-treating-meeting-ui-review-member-view-light-1366.png` shows the waiting card with Raise hand, Step away, Questions, People, Leave greyed). Phase 5 screenshots must admit the member first.

### 2.2 Coordinator control view (`mt/components/ControlView.tsx`, shown by `MeetingAgendaPage.tsx:157` when the meeting is in session)

- Top bar (86-94): "Conducting · date", "n of N: patient line", board question, `TimerBadge`, `LiveDot`, "Room screen" link (opens `/meetings/:id/room`).
- Main (96-216): left, `SharedScreen` labelled "What the room sees", with an Admit banner (up to three waiting people, lines 100-110), the `DecisionStrip`, and a tile row of up to 10 (`TileGrid layout="row" max={10}`). Right, a fixed 26 rem panel with five tabs (`TABS`, lines 28-34): Share (timer minutes, Stop, Reset; the slide picker; records and images list with Show and Images buttons; "Back to the slide"), Decision (the `DecisionForm`, End case, cards summary), People (`PeopleList` with Admit, plus `AgentTile`), Questions (read only list, no answer box and no ask box), Agenda (ordered list, click to go to a case, Case File link).
- Control bar (218-233), in order: Mute, Camera, Previous, Next (or "First case"), Timer / Stop timer, End case, End meeting (confirm dialog, lines 235-245). Right: "Leave the controls".
- Works: admit; case navigation (`setCurrent`); timer start, stop, reset; open record or images on the shared screen; decision form with the live strip; card requests; end meeting.
- Missing: the panel is always on (not one at a time, not closable) so on a phone the stage and the panel stack and the bar covers content (screenshot `real-coordinator-meeting-demo-control-dark-390.png`); no screen share; no chat; no hands list except in People; no agenda rail with times; no quorum line; no presenter shown; no way to add or remove an agent; no spotlight.
- Bug seen in the baseline: with no study linked, the images view shows the raw JSON `{"detail":"Open the images from the imaging report in the Case File first."}` inside the stage (`real-coordinator-meeting-demo-control-dark-1366.png`, same on the room screen at 1920). The stage must show a plain message instead of an iframe of an API error (the 5.1 fix: check `viewerSrc` result before opening, and show "No images are linked to this Case File yet").

### 2.3 Room screen (`/meetings/:id/room`, `mt/MeetingRoomPage.tsx`)

- Top bar (59-74): date and room, the case headline in large type (`text-xl lg:text-2xl`), a big timer, `LiveDot`, room mic and camera buttons (only when the coordinator opened it and video is on, line 39), full screen, close.
- Main (82-109): left 30% "Summary" panel (the summary slide in big type, hidden under 1024 px); centre `SharedScreen` showing the current slide, record or images (big) with `SlideDots`, and "Questions from members" below; right column of up to 6 remote tiles and the `AgentTile` (only when active).
- Footer (111-119): count in the meeting, hands raised, video error, and the `DecisionStrip` (or a dashed placeholder).
- Joins LiveKit as `<user>#room` and may publish the room camera and microphone (`lib/video.ts:23-27`, `tumour_board/api/video.py:32-37`). Audio of everyone is played by `RoomAudioRenderer` inside `Live` (`VideoTiles.tsx:92`).
- Missing: no agenda, no quorum, no hands names, no chat, no reactions; no agent spoken answers (D2 needs this); in-room participants without laptops appear as initials tiles only.

### 2.4 Join and waiting room (`mt/JoinPage.tsx`, `PreJoin.tsx`)

- Join: six-digit code boxes (`JoinPage.tsx:57-71`), error texts for wrong code (404), expired (410), too many tries (429). After success: admitted goes to the member view; otherwise `WaitingRoom` (lines 13-27) with "Connected, waiting" or "Checking every 10 seconds", which moves on when an `admit` event for this user arrives.
- Pre-join (`PreJoin.tsx`): camera preview, mic and camera toggles, device menu (camera and microphone lists), mic level meter (`role="meter"`), "Join now" and "Join without video"; choice kept in `sessionStorage` (`lib/video.ts:13-16`). No speaker (output) choice, no "test sound", no name or role shown, no "you are joining X as Y".
- Screenshots: `real-treating-meetings-join-empty-light-1366.png`, `...-waiting-room-light-1366.png`, `...-wrong-code-light-1366.png`.

### 2.5 Agenda page (`mt/MeetingAgendaPage.tsx`)

- Before the meeting: header with title, room, count, "video on", "agenda sent", status chip, buttons (deck, "Member view", "Room screen", "Start the meeting"); `AgendaLists` (discussion, noting, not ready; reorder; remind owner); "Before the meeting" box (send agenda, join code with copy and new code, cancel); `MembersStrip`; add-case dialog (`AddCaseDialog`, lines 38-74).
- During the meeting it becomes the control view for the coordinator and a link to the member view for everyone else (162). After: a closed list of outcomes (195-203).
- Missing for Phase 5: nothing here is in the call; the agenda in the call is only a plain list in the control view's fifth tab.

### 2.6 The live channel and its events

WebSocket `/api/tb/meetings/{mid}/ws` (hub in `tumour_board/live.py:22-142`; client `lib/live.ts`, reconnect with backoff, 25 s ping, poll every 10 s). Events sent by `tumour_board/meetings.py` through `_send` (line 183): `meeting` (527), `ended` (547, 865), `agenda` (582, 669), `presence` (768, 809), `admit` (787), `current` (841, 891), `open` (946), `timer` (988), `agent_state` (996), `question` (1017, 1059), `hand` (1087), `decision_live` (1096), `decision` (1194), `end_case` (1245), `card` (1266), plus the first message `state` (the `view()` payload, lines 444-478). The typed list is `LiveEventType` (`lib/live.ts:9-11`). Each socket gets a per-user shaped copy (`shape`, `live.py:109-142`), so a waiting person gets no live content.

State fields a call shell can use today: `attendance` (user, name, department, status present, remote, waiting, absent; mode room or remote; head; online; card_holder; outside_expert), `current` (case, slide, opened, timer), `hands`, `questions`, `agent` (active, role, label, state, roles, question), `heads`, `absent_roles`, `outcomes`, `ended`, `cards_given`, `can` (manage, record, ask, card, card_required, video, member), `me` (`meetings.py:444-478`).

### 2.7 LiveKit: used and not used

- Server: self-hosted v1.13.10 on 127.0.0.1:7880, `max_participants: 50`, UDP 50000 to 50200, TCP 7881 (`scripts/livekit.sh:7,16`; `scripts/livekit-config.yaml.example`). No TURN, no recording.
- Token (`tumour_board/video.py:72-86`): HS256, TTL 2 h, grants `roomJoin`, `room`, `canPublish`, `canSubscribe` only. No `canPublishData`, `canPublishSources`, metadata or attributes. Identity is the Vaidyx username; the room screen is `<user>#room` (`api/video.py:32-37`). Room name `tb-<meeting id>`.
- Client (`lib/video.ts`): `new Room({ adaptiveStream: true, dynacast: true, videoCaptureDefaults 960x540 at 24 fps })` (line 19); events bumped: ParticipantConnected, ParticipantDisconnected, TrackSubscribed, TrackUnsubscribed, TrackMuted, TrackUnmuted, ActiveSpeakersChanged, LocalTrackPublished, LocalTrackUnpublished, Reconnecting, Reconnected, Disconnected (72-78). `switchActiveDevice` is called only at join (84-85). Mic and camera toggles (97-106). Components used: `RoomAudioRenderer`, `RoomContext`, `VideoTrack`, `isTrackReference`, `useIsSpeaking`, `useTracks` (`VideoTiles.tsx:5`).
- Not used: screen share, data channel and text streams, participant metadata and attributes, `usePinnedTracks`, `FocusLayout`, `GridLayout`, `CarouselLayout`, `ConnectionQualityIndicator`, `useConnectionState`, `MediaDeviceMenu`, `useStartAudio` (autoplay-blocked audio), `RoomEvent.MediaDevicesChanged`, `ActiveDeviceChanged`, `ConnectionQualityChanged`.
- Tile ring: `TileFrame` has a ring class and `useIsSpeaking` (`VideoTiles.tsx:36-70`), so the active-speaker ring exists; check it stays visible on a dark stage.

## 3. Patterns from Google Meet, Zoom and Teams

Sources (official pages unless said): Meet layouts and controls https://support.google.com/meet/answer/10550593 ; Meet present https://support.google.com/meet/answer/9308856 ; Meet shortcuts https://support.google.com/a/users/answer/9896256 ; Meet raise hand https://support.google.com/meet/answer/10159750 ; Meet reactions https://support.google.com/meet/answer/13151720 ; Meet accessibility https://support.google.com/meet/answer/16175468 ; Zoom spotlight https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0066300 ; Zoom pinning https://support.zoom.us/hc/en-us/articles/201362743-Pinning-participants-videos ; Teams controls https://support.microsoft.com/en-us/teams/meetings/use-meeting-controls-in-microsoft-teams ; Teams present https://support.microsoft.com/en-us/office/present-content-in-microsoft-teams-meetings-fcc2bf59-aecd-4481-8f99-ce55dd836ce8 ; Teams attendee view https://support.microsoft.com/en-us/teams/meetings/manage-what-attendees-see-in-microsoft-teams . Details marked (secondary) come from search summaries of support pages, not read in full. The official pages for Zoom's toolbar order and Teams' lobby and "Spotlight for everyone" could not be fetched in this run (404 or truncated); items from them are marked (to confirm).

| Pattern | Meet | Zoom | Teams | What we take |
|---|---|---|---|---|
| Bottom bar | Middle: mic, camera, captions, raise hand, present, More, leave; leave placed far from mic and camera; meeting details, people, chat, activities at bottom right (10550593) | Toolbar at the bottom, appears on hover (secondary) | Order given on the page: Mic, Camera, Share, Chat, People, Raise hand, React, View, More actions, Leave; core controls fixed, others can be dragged into More (use-meeting-controls) | One bar: mic, camera, present, hand, reactions, chat, people, agenda, more, leave, with panel toggles on the right on laptop; leave in red and apart |
| What "More" holds | "Change layout" and others (page lists only layout) | More menu (to confirm) | Unpinned controls, record, background effects, turn off incoming video | More: devices, layout, full screen, shortcuts, mute agent voices, captions later |
| Layouts | Auto (default), Tiled (up to 49, 16 default), Spotlight (speaker or shared screen fills), Sidebar (speaker big, thumbnails at side); "Hide tiles without video" (10550593, secondary) | Speaker view and Gallery view toggle top right; gallery 25 or 49 (secondary) | View menu: more or fewer people, prioritise people with video (use-meeting-controls) | Layout choices: Auto, Speaker (stage plus strip), Grid, Spotlight; Auto is default |
| Pin vs spotlight | Pin on a tile keeps one person large for you (secondary) | Pin is only your view, up to 9; Spotlight is host or co-host only, changes the view for everyone, up to 9, needs 3 with video (KB0066300; pin page) | "Pin for me" only you; "Spotlight for everyone" (Teams Free help, secondary) | Pin for me (local); Spotlight by the coordinator for all (stored); a "removed" control on the pinned tile |
| Presenting | "Present now": tab, window or whole screen; tab audio shared by default in Chrome; starting while someone presents pauses theirs; "Stop presenting" (9308856) | Share Screen on the toolbar (secondary) | Share: screen, window, PowerPoint or whiteboard; presenter layouts Content only, Standout, Side-by-side, Reporter (secondary) | Present a tab, window or screen; one presenter at a time; the presenter sees a "You are presenting" bar with Stop; others get it on the main stage; tab audio if offered |
| Side panels | People, Chat, Activities, each from the bottom right; one at a time (10550593) | Participants and Chat panels (secondary) | People and Chat panels (use-meeting-controls) | One panel at a time: People, Chat and questions, Agenda, Case, Agents, Decision |
| Raise hand | Hand button; also shortcut Ctrl+Alt+H (9896256) | Raise Hand in Reactions (secondary) | Raise hand; others see the order in which hands were raised (use-meeting-controls) | Hand with order shown to the coordinator (queue list in People), lower on a second press |
| Reactions | "Send a reaction" button with an emoji panel (13151720) | Reactions (to confirm) | React menu: Like, Love, Applause, Laugh, Surprise (secondary) | Four plain reactions only (agree, thanks, applause, question mark), short-lived on the tile; kept out of the record |
| Captions | Captions button in the bar; key C (9896256) | Live transcript (to confirm) | Captions (to confirm) | Not in 5.x (voice is Phase 4); leave a place in More |
| Shortcuts | Ctrl+D mic, Ctrl+E camera, C captions, Ctrl+Alt+H hand, Ctrl+Alt+C chat, Ctrl+Alt+P people, Ctrl+Alt+T present, Shift+? help (9896256) | Alt-key set (to confirm) | Ctrl+Shift+M mute, Ctrl+Shift+O video, hand Ctrl+Shift+K (sources disagree with Ctrl+Shift+L; secondary) | Our own table in section 6.10; avoid browser-reserved keys; Shift+? shows help |
| Waiting room | Host admits from a pop-up and the People panel (secondary) | Waiting room, admit one or all (to confirm) | Lobby notification, Ctrl+Shift+Y to admit (secondary) | Admit toast on the coordinator's stage (exists) plus Admit all, a count on the People button |
| Device settings in call | Settings from More: audio, video, devices (secondary) | Up arrow beside mic and camera: choose device (secondary) | Device settings from More (to confirm) | A small arrow beside mic and camera opens a device popover (mic, speaker, camera) |
| Connection | "Poor connection" hints and a reconnect message (secondary, to confirm) | Network indicator (to confirm) | Network indicator (to confirm) | Per-tile quality bars; a top banner "Reconnecting" with a clear state; show audio-only fallback |
| Phone | Tap the screen to show controls; More holds Share screen (9308856) | Toolbar on tap (to confirm) | Controls on tap (to confirm) | Controls hide after 4 s and return on tap; the strip goes into a swipe row; panels become bottom sheets |
| Accessibility | Buttons show their name on pointing; screen reader page (15738543) | to confirm | Controls are real buttons with names | Every button has an `aria-label` and a tooltip; panels are labelled regions; live announcements for admit, next case, hand, agent answers |

## 4. Tumour board products

Public product documentation for these tools is thin, so this section is limited to what pages say and is marked where inferred.

- NAVIFY Tumor Board (Roche, launched 2017): a cloud tool that puts patient data from EMR, labs, PACS and pathology reports in one dashboard, supports review as a team and lets experts at other sites join remotely (https://www.roche.com/media/releases/med-cor-2017-10-03). Version 2 with GE Healthcare added an image viewer in the same dashboard (https://www.roche.com/investors/updates/inv-update-2019-05-31). The pages do not describe an agenda rail or timer. Take: the case summary and the images belong inside the meeting screen, not in separate tabs of the hospital system (Vaidyx already opens records and the viewer on the stage).
- Philips IntelliSpace Precision Medicine Oncology Platform, "Multidisciplinary Team Orchestrator": scheduling, preparing cases, dashboards, structured patient data; sessions may be attended in person, virtually, synchronously or asynchronously (https://www.philips.com.au/healthcare/product/HC881088/intellispace-precision-medicine-oncology-platform). Take: an asynchronous option exists in the market; Vaidyx's pre-meeting Case File preparation and Points for review play this part.
- Trak MDT module (a UK and US style MDT tool, used here as the available documented example because Infoflex and Somerset had no public manuals): four tabs General, Create Roster, Attendees, Conduct Meeting; roster order and "Auto-Calculate Times" per case; attendees invited from the cases' people; Conduct Meeting records who attended, recommendations and comments for each case, and adjourning makes results read-only (https://intercom.help/trak/en/articles/14863572-multidisciplinary-team-mdt-management). Take: per-case times on the agenda, per-case attendance, and read-only after adjourn (Vaidyx already closes the meeting).
- Somerset Cancer Register: job postings show MDT outcomes are entered in it with lead clinician sign-off; no module manual was found (search result only). No design taken.
- Quorum evidence from the UK: "no longer a requirement for a minimum attendance by individual members", meetings are to be quorate on 95% or more occasions, core membership differs by tumour group (`/data/vaidyx/night-v3/research_text/gm-mdt-standards-v3-2023.txt` lines 197-206; Greater Manchester standards v3.0, https://gmcancer.org.uk/wp-content/uploads/2023/06/V3.0-GM-MDT-Standards-June-23.pdf). A 2023 lung MDT study found 21% of observed meetings quorate (search summary, https://doaj.org/article/c92e172138c54d1b88d112fa0a14cf7a). Take: show quorum as a plain line for the record; do not block a decision.
- What a board-specific screen adds over Meet or Zoom (our synthesis, inferred): the agenda with the case on the floor and its time; who is presenting this case; the case summary and the images on the stage; the decision form beside the stage; attendance and quorum; the outcome kept with the Case File.

## 5. LiveKit capabilities we will use

Installed versions (`web/tb-nik/package.json:19,46`; `node_modules/.../package.json`): `livekit-client` ^2.23.0 (installed 2.23.0), `@livekit/components-react` ^2.9.24 (installed 2.9.24). Server v1.13.10.

| Need | API (version above) | Caveat |
|---|---|---|
| Present a screen | `room.localParticipant.setScreenShareEnabled(true, options?, publishOptions?)`; `ScreenShareCaptureOptions` has `audio`, `resolution` (default 1080 except Safari), `selfBrowserSurface`, `surfaceSwitching`, `systemAudio` (`livekit-client/dist/src/room/track/options.d.ts:192-217`; `LocalParticipant.d.ts:105,130`). Docs: https://docs.livekit.io/transport/media/screenshare/ | The browser asks the person to choose; audio only if a tab is picked with tab audio on; the receiver gets a video track with source `Track.Source.ScreenShare` and an audio track `ScreenShareAudio`, played by `RoomAudioRenderer`. Docs give no resolution limit; we cap at 1080p, 15 fps text-friendly. Needs the token to allow screen share (see below). A mobile browser cannot share, so hide Present on phones. |
| Show it on the stage | `useTracks([{ source: Track.Source.ScreenShare, withPlaceholder: false }])`, `VideoTrack` | The stage must prefer: a LiveKit screen share if present, else the app's `opened` item, else the slide. One at a time; a new share replaces the old one (as Meet does). Use `adaptiveStream` (already on) so a hidden stage costs nothing; `Track.attach()` must be used (docs, https://docs.livekit.io/transport/media/subscribe/). |
| Chat | `useChat()` (components-react) or `publishData`/`sendText` (client `LocalParticipant.d.ts:166,191`); `RoomEvent.DataReceived` | Data packets are best effort, reliable up to 15 KiB, lossy 1300 bytes, `topic`, `destinationIdentities` (https://docs.livekit.io/transport/data/packets/). Not stored by the server and not seen by someone who joins late. So the plan uses the app WebSocket and the database for chat (kept in the record) and keeps LiveKit data only for light signals (for example "someone is typing"). |
| Reactions, agent events | App WebSocket (kept); optionally lossy `publishData` with topic `reaction` | Lossy is fine for a 3 s emoji; but keeping one channel is simpler to test and audit. Recommend app WebSocket for all. |
| Participant info | `setAttributes`, `setMetadata` (`LocalParticipant.d.ts:85`), `RoomEvent.ParticipantAttributesChanged`, `useParticipantAttributes` | Can be set by the client unless the token forbids it; do not trust it for roles. Roles come from the app state `attendance`. Use only the token `name`. Keep attributes empty in v1. |
| Speakers | `useIsSpeaking`, `RoomEvent.ActiveSpeakersChanged` (already used) | Ring and speaker view order. |
| Pin and focus layouts | `usePinnedTracks`, `FocusLayout`, `CarouselLayout`, `GridLayout` (`components-react.d.ts`) | These use a `LayoutContext` and the library's pin state, which is local (good: pin is per person). They bring default styles; our tiles are custom (`TileFrame`), so prefer our own layout code driven by `useTracks` and a small pin state, and borrow only `useTracks`/`isTrackReference`. Decide at build time; both are possible. |
| Device change after join | `room.switchActiveDevice(kind, deviceId)` (`Room.d.ts:267`), `Room.getLocalDevices` (188), `RoomEvent.MediaDevicesChanged`, `ActiveDeviceChanged`; or `useMediaDeviceSelect`, `MediaDeviceMenu` | Output device selection works only in browsers that support `setSinkId` (Chrome, Edge; not Safari or Firefox). Handle a device unplugged: listen for `MediaDevicesChanged` and show a message. |
| Connection quality | `RoomEvent.ConnectionQualityChanged`, `participant.connectionQuality`, `useConnectionQualityIndicator`, `ConnectionQualityIndicator` | Values excellent, good, poor, lost, unknown. Shows the local person's link and each remote tile. |
| Reconnect | `RoomEvent.SignalReconnecting`, `Reconnecting`, `Reconnected`, `Disconnected`, `ConnectionStateChanged`; `useConnectionState` | Already partly used (`video.ts:77-78`); needs a banner and a manual "Rejoin" button after `Disconnected` (today status goes to "off" silently). |
| Simulcast and adaptive stream | `adaptiveStream`, `dynacast` (already set, `video.ts:19`); `publication.setVideoQuality` | Strip tiles are small, so adaptive stream picks low layers. Set `videoCaptureDefaults` 960x540 (exists). |
| Start audio | `useStartAudio`, `room.startAudio()` | Browsers can block remote audio until a click. Add a "Click to hear the meeting" button when `room.canPlaybackAudio` is false; today there is none. |
| Permissions | token `video` grant: `canPublish`, `canPublishData`, `canPublishSources` (token builder `tumour_board/video.py:72-86`; server permission update docs https://docs.livekit.io/intro/basics/rooms-participants-tracks/participants/) | Today the token cannot restrict sources. For "the coordinator may allow others to present", issue the token with `canPublishSources` camera, microphone for most, plus screen_share for the coordinator and the case presenter; when the coordinator allows someone else, the server calls LiveKit's `UpdateParticipant` permission (needs the server API, a small new function in `video.py` that signs a service JWT and posts to the Twirp endpoint). A simpler first version: every admitted member's token allows screen share, and the app enforces "one presenter, only allowed people" in the UI and in `meetings.py` (the stage ignores a share from a person not allowed). Choice for the owner (section 9). |
| Limits | `max_participants: 50` in our config; the server doc limits are by hardware | A board is 10 to 25; the 50 cap is fine. The strip shows at most 8 to 12 tiles plus "+n". |

## 6. The proposed design

### 6.1 One shell, three variants

A `CallShell` component (new, in `mt/components/CallShell.tsx`) takes `variant`: `member`, `coordinator`, `room`. The same parts, in the same places, with the same names:

1. Top bar: meeting title and date, case headline and board question, timer, quorum chip, connection chip.
2. Stage (centre).
3. Strip (participants and agents).
4. Agenda rail (collapsible, left on laptop).
5. Side panel (right, one at a time).
6. Bottom control bar.
7. Banners (reconnecting, admit, "you are presenting", "hand raised").

### 6.2 Laptop, member (1366 x 768)

```
+--------------------------------------------------------------------------------------------------------------+
| [V] Tumour Board 27/10 16:00 | 3 of 8: Anitha Reddy (SYNTHETIC) 46 Y/F  Board question: Primary plan | 07:42 | Quorum 4/5 | (live) |
+--------+--------------------------------------------------------------------------------+--------------------+
| AGENDA |  [ Summary | Key values | Gaps | Imaging | Pathology | Points | Staging ]  <- what the room sees      |
| 1 done |  +--------------------------------------------------------------------------+  | PEOPLE  (in panel)|
| 2 done |  |                                                                          |  | In the room  3    |
|>3 7:42 |  |                       M A I N   S T A G E                                |  | Remote       4    |
| 4  10m |  |    case summary slide / report page / images / Staging card /            |  | Waiting      0    |
| 5  10m |  |    shared screen from Dr X  (badge: "Dr X is presenting")                |  | Agents       2    |
| ...    |  |                                                                          |  | Dr A  Radiology   |
|        |  +--------------------------------------------------------------------------+  | ...               |
| Quorum |  [tile][tile][tile][tile][tile][ AI Radiology ][ AI Pathology ] ... +2      |                    |
| 4 of 5 |  Decision strip (live text from the coordinator, "not saved")                 |                    |
+--------+--------------------------------------------------------------------------------+--------------------+
|  (mic v) (cam v) (Present) (Hand) (React) (Chat) (People) (Agenda) (Case) (More)            [Leave]          |
+--------------------------------------------------------------------------------------------------------------+
```

- The side panel is closed by default and opens over the strip's right edge pushing the stage narrower; the agenda rail shows only a thin column of numbers under 1280 px and expands on click.
- The stage tab strip above the stage ("Summary, Key values, ...") is what a member sees to step away from the shared item (today's "Follow / Step away" folded into it: choosing another tab shows "Step away, return to the room's screen" chip; one click on the chip follows again).

### 6.3 Laptop, coordinator

Same layout. Differences:
- The top bar adds the timer controls (a small menu from the timer chip: start, stop, reset, minutes).
- The stage tab strip is also the coordinator's picker: choosing a tab, a record or the images changes the room's shared item (today's Share tab). A "Records and images" popover from a button on the strip replaces the long list.
- The bottom bar adds, after Agenda and Case: Previous, Next case, Decision, End case, and at the far right End meeting (red). Leave becomes "Leave the controls" and sits beside End meeting but not adjacent (a gap and a different colour).
- The Admit toast sits top right of the stage, stays until acted on, with "Admit" and "Admit all".
- Each tile has a menu (three dots): Pin for me, Spotlight for everyone, Make presenter (allow to present), Remove from spotlight.

Layout (1366 x 768); the stage, strip, rail and one side panel are the member's, with the coordinator's additions marked:

```
+--------------------------------------------------------------------------------------------------------------+
| [V] Conducting 27/10 16:00 | 3 of 8: Anitha Reddy (SYNTHETIC) 46 Y/F  Board question: Primary plan | [07:42 v] Quorum 4/5 (live) |
+--------+---------------------------------------------------------------------------+-------------------------+
| AGENDA | [ Summary | Key values | Gaps | Imaging | Pathology | Points | Staging ] [Records and images v]       |
| 1 done | +---------------------------------------------------------------------+   | DECISION  (one panel)   |
| 2 done | |                                                                     |   | Outcome: (o) Decision   |
|>3 7:42 | |                     M A I N   S T A G E                             |   | Text: [................]|
| 4  10m | |         what the room sees; badge "Room sees this"                  |   | Rationale, next step,   |
| 5  10m | |                                                    [Admit: Dr X]    |   | responsible doctor ...  |
| 6  10m | |                                                    [Admit] [All]    |   | [Save]  Cards 2 of 4    |
| Quorum | +---------------------------------------------------------------------+   | [End case]              |
| 4 of 5 | [tile][tile][tile][tile][tile][AI Radiology][AI Nuc. Med.] +2 (tile menu)| Live text goes to strip |
+--------+---------------------------------------------------------------------------+-------------------------+
| (mic v)(cam v)(Present)(Hand)(React)(Chat)(People)(Agenda)(Case)(Agents)(Decision)                            |
|      [Previous] [Next case] [Timer] [End case] (More)                      [End meeting]   [Leave the controls] |
+--------------------------------------------------------------------------------------------------------------+
```

The tile menu (three dots on each tile): Pin for me, Spotlight for everyone, Make presenter, Remove from spotlight; on an agent tile: Remove agent. The bar has two rows below 1280 px wide (as drawn) and one row above it.

### 6.4 Room screen (projector, large type, 1920 x 1080, variant `room`)

```
+----------------------------------------------------------------------------------------------------------------+
| [V]  Tumour Board 27/10 16:00 Room 2        3 of 8: Anitha Reddy, 46 Y/F, UHID ...         07:42     Quorum 4 of 5 |
|      Board question: Primary management plan                                       Presenter: Dr Priya (Radiology) |
+---------+------------------------------------------------------------------------------------+-------------------+
| 1 done  |                                                                                    |  REMOTE (4)       |
| 2 done  |                                                                                    |  [tile]           |
|>3 now   |                       M A I N   S T A G E   (large type)                           |  [tile]           |
| 4       |                                                                                    |  [tile]           |
| 5       |                                                                                    |  AGENTS STANDING IN|
| 6       |                                                                                    |  Radiology  ready |
|         |                                                                                    |  Pathology  speaking|
+---------+------------------------------------------------------------------------------------+-------------------+
| Hands: Dr Meera, Dr Suresh   | Questions to the board (latest 2)  | Decision (as typed, not saved)             |
+----------------------------------------------------------------------------------------------------------------+
```

- No bottom control bar; a small hover-only bar at the bottom right (full screen, volume, close). The coordinator's control view runs the meeting.
- Text sizes: stage text 28 px or more, agenda rail 20 px, tiles' names 20 px, decision strip 28 px. Contrast at least 7:1 on the dark stage. Nothing relies on colour alone.
- When someone shares a screen, the stage shows it full, with the summary shrunk into the case chip at the top. The existing 30% summary column is kept as a toggle ("Summary on the side") because the owner's room used it (`MeetingRoomPage.tsx:84`).
- Agent answers are spoken here by default (D2), with the text and sources on screen; the room screen has a "Mute agent voices" in its hover bar.

### 6.5 Phone, member (390 x 844)

```
+------------------------------+
| 3 of 8  Anitha R., 46 Y/F  07:42 [conn] |
+------------------------------+
|                              |
|   MAIN STAGE (16:10)         |
|   summary / report / share   |
|                              |
+------------------------------+
| [tile][tile][tile][AI][AI] > |  swipe row, 64 px high
+------------------------------+
| Decision strip (1 line, tap) |
+------------------------------+
| (mic)(cam)(hand)(chat)(...) |  5 buttons
| More: present*, react, people,|
|  agenda, case, devices, leave |
+------------------------------+
```

- The bar has five buttons: mic, camera, hand, chat, More. More opens a bottom sheet: reactions, people, agenda, case, agents, devices, layout, full screen, shortcuts, Leave (red, last). Present is hidden on phones (no browser screen capture).
- Panels (People, Chat, Agenda, Case, Agents) open as a bottom sheet to 85% height, one at a time, with a visible Close and a drag handle; Android back closes the sheet.
- Controls fade after 4 s with no touch and return on tap; they never hide while a panel is open or while hand is raised.
- Landscape: the strip moves to the right edge.

### 6.5b Phone, coordinator

A coordinator on a phone gets the member phone layout above plus a "Coordinator" sheet, because the Decision form, the agenda moves and the timer need room that a phone bar does not have; the sheet is a bottom sheet like the others (one at a time) and the bar keeps its five buttons, with Coordinator as the fifth in place of Chat (chat stays in More).

```
+------------------------------+
| 3 of 8  Anitha R., 46 Y/F  07:42 [conn] |
+------------------------------+
|   MAIN STAGE (16:10)         |
|   summary / report / share   |
+------------------------------+
| [tile][tile][AI][AI] >   (1) |  (1) Admit toast: "Dr X waiting [Admit]"
+------------------------------+
| (mic)(cam)(hand)(Coord.)(...) |
+------------------------------+
   Coordinator sheet (85% high, drag handle, Close)
   +--------------------------------------------+
   | Case 3 of 8      Timer 07:42 [Start][Stop] |
   | [ Previous ]  [ Next case ]   [ End case ] |
   | Show on the stage: Summary | Values | Gaps |
   |   Imaging | Pathology | Points | Staging    |
   |   Records and images (Show, Images)        |
   | Decision: outcome, text (mic in Phase 4),  |
   |   [ Save ]   cards: 2 of 4 given           |
   | Agents: Radiology [Remove]  [Add agent]    |
   | Waiting: Dr X [Admit]   [Admit all]        |
   | [ End meeting ] (red, asks to confirm)     |
   +--------------------------------------------+
```

### 6.6 The main stage

What it shows, in this order of precedence (all rules in `StageContent`, new):

1. A LiveKit screen share from the allowed presenter ("Dr X is presenting", with "Stop" for that person and the coordinator).
2. The item the coordinator opened (`current.opened`: a record page or the image viewer), unless it has no content (then a plain message, see the bug in 2.2).
3. The current slide (summary, key values, gaps, imaging, pathology, points for review, published cases, and the Staging card when it exists), taken from `getSlides`.
4. If nothing is on the floor (no case, break, meeting not started): a grid of participants (the "tiled" view) with the next case named.

The stage is always a single item. A member may "Step away" to browse the slide tabs on their own (today's Follow), with a chip "Back to the room's screen". The stage never shows model output as a decision; the Staging card keeps its label "Vaidyx draft stage, for the board to confirm" (docs/staging/DECISION.md) and the Points for review keep "AI drafts".

### 6.7 Participant strip, tiles, layouts, pin and spotlight

- Layout choices (More, Layout): Auto (default: stage plus strip when something is presented; grid when nothing is), Speaker (stage replaced by the active speaker, strip below), Grid (tiles only, up to 25 per page), and Spotlight (what the coordinator set). On a phone only Auto and Grid.
- Speaker view: the active speaker (from `ActiveSpeakersChanged`) gets a green ring (2 px, not colour alone: a small "speaking" bars icon) and moves first in the strip after a 2 s delay so the strip does not jump.
- Pin for me: the tile menu or a click on the pin icon puts that person's tile large on my stage until I unpin; stored in my browser only (`sessionStorage`), not sent. A "Pinned" chip with an X on the tile.
- Spotlight for everyone: coordinator only; up to 3 people; stored server side as `meeting.spotlight: [user, ...]` and sent as an event `spotlight`. Everyone's layout becomes Spotlight with those people large, unless a person has pinned someone (their own pin wins for them; a note "The coordinator spotlighted Dr X, show" appears). Removed by the coordinator or when the meeting moves to the next case.
- Tile contents (`TileFrame` today shows name, department, mic, "room" tag, hand, room screen icon): add a role badge, one of Head (the department head for the board), Coordinator, Presenter (the case's presenter or the one sharing), Expert (outside expert), plus the department; keep mic state, hand, connection bars (lower right) and the "speaking" icon. The text in the tile `aria-label` reads: "Dr Priya, Radiology, head, presenter, remote, microphone on, hand raised".
- No camera: coloured initials (exists). In-room people without a laptop: a "room" tag and only a count in the quorum line.
- Agent tiles (D2): a tile with the department's initials replaced by the Vaidyx mark and the label "Radiology, AI agent standing in", the line "AI agent, support only", a state word and animation (ready, listening, thinking, speaking). States are true: "listening" only while a question is being spoken to it (voice in), "thinking" while `agents.ask` runs, "speaking" while the answer is played, "ready" otherwise. They never show a camera, never a mic icon, never a hand, never count in "in the meeting". They sit after the people in the strip, with a dashed border so they cannot be mistaken for a member. The coordinator's tile menu: Add agent (any of the six; always Radiation Oncology and Nuclear Medicine), Remove agent. The current `agent_state` event carries only one agent (`meetings.py:419-441`); it must carry a list (see 6.15).

### 6.8 The bottom control bar, in order

Member (left to right): Mic (with a small arrow for devices), Camera (arrow), Present, Raise hand, Reactions, Chat, People, Agenda, Case, More, then Leave (red, set apart at the right). Right of the bar on laptop: room and count text as today.

Coordinator: Mic, Camera, Present, Hand, Reactions, Chat, People, Agenda, Case, Agents, Decision, then a gap, Previous, Next case, Timer, End case, More, then End meeting (red) and Leave the controls.

Labels and tooltips (each button has `aria-label` and a tooltip with the key): "Turn the microphone off (Ctrl+D)", "Turn the camera on (Ctrl+E)", "Present a screen (Ctrl+Alt+T)", "Stop presenting", "Raise hand (Ctrl+Alt+H)", "Lower hand", "Send a reaction", "Open chat (Ctrl+Alt+C)", "Show people (Ctrl+Alt+P)", "Show the agenda", "Show the case", "Show the agents", "Open the decision form", "More options", "Leave the meeting". The `BarButton` already has `aria-label`, `aria-pressed` and a tooltip via `title` (`Stage.tsx:48-72`). Keep its look; add `aria-keyshortcuts`.

More menu: Devices (microphone, speaker, camera), Layout (Auto, Speaker, Grid), Full screen, Mute agent voices (for me), Show shortcuts, Call by phone (the existing `CallButton`), "I am in the room" or "I am remote" (the existing present-mode switch), Report a problem later.

### 6.9 One side panel at a time

One `SidePanel` slot with a `panel` state: `people | chat | agenda | case | agents | decision | null`. Opening one closes the other. Toggle buttons show a count badge.

- People: sections Waiting (coordinator sees Admit and Admit all; members see a count), In the room, Remote (with a hand order number, mic and camera state, role badge), Expected, not here, and a separate section Agents standing in (support only, not counted). A search box when more than 12 people. Coordinator row menu: Spotlight, Make presenter, Remove from meeting later.
- Chat and questions: two tabs. "Meeting chat" is for people (new, 5.3). "Questions to the board" is today's `QuestionsList` and ask box (`MemberViewPage.tsx:183-195`); the questions to the agents are asked here with a role chip (Ask Radiology, Ask Pathology, or "Ask the board"); the chat is not sent to agents. A note under the chat box: "Meeting chat is kept with the meeting record." (to confirm, section 9). Agent answers show text, sources with quotes and time (gap from `00_current_state.md` section 2, "The answer's references and time are not shown") and a "Read aloud" button; voice is Phase 4.
- Agenda: the list with per-case time (planned minutes and elapsed), done marks and outcome words, the current case highlighted; coordinator clicks a row to move the room to it (`setCurrent`). Not-ready cases are shown greyed.
- Case: the stage tab list as a vertical list (summary, values, gaps, imaging, pathology, points, staging) plus the records and images list with Show for the coordinator (today's Share tab content) and a read-only list for members, plus "Open the Case File" link.
- Agents: for each of the six departments: standing in (yes, no), state, the brief's headline, an input "Ask" (text, mic button in Phase 4), and for the coordinator Add and Remove. Label "AI agent, support only; answers from the records and guidelines; never a decision".
- Decision: coordinator only (or anyone with `can.record`): today's `DecisionForm`, live text strip, End case and the cards summary (`ControlView.tsx:175-190`). Members see the live decision text on the strip only.

### 6.10 Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+D | Mute or unmute the microphone (Meet uses the same) |
| Ctrl+E | Camera on or off (Meet) |
| Ctrl+Alt+H | Raise or lower hand (Meet) |
| Ctrl+Alt+C | Chat panel |
| Ctrl+Alt+P | People panel |
| Ctrl+Alt+A | Agenda panel |
| Ctrl+Alt+T | Present or stop presenting (Meet) |
| Esc | Close the open panel or menu |
| F | Full screen (when focus is not in a text box) |
| Space (held, push to talk) | Optional, off by default |
| N, P | Next and previous case (coordinator only, with a confirm if a decision is unsaved) |
| ? (Shift+/) | Show this list |

Shortcuts never fire while the focus is in a text box, textarea or the decision form (except Esc). The keys avoid Ctrl+W, Ctrl+T and browser-reserved ones. Meet's own table is the source for the first rows (https://support.google.com/a/users/answer/9896256); the rest are ours.

### 6.11 Device change after joining

A small arrow beside Mic and Camera opens a popover with three selects: Microphone, Speaker (hidden when `setSinkId` is not supported), Camera, a mic level meter (reuse `MicLevel` from `PreJoin.tsx:12-34`) and "Test the speaker". It calls `room.switchActiveDevice`. A `MediaDevicesChanged` listener shows a toast "The camera you were using was unplugged, switched to X" and falls back to the default. The choice is saved in `sessionStorage` as today.

### 6.12 Connection quality and the reconnect banner

- Per tile and in the top bar: three or four bars from `connectionQuality` (excellent, good, poor, lost) with an `aria-label` ("Your connection is poor"). "Poor" for 10 s shows a hint "Turn the camera off to save bandwidth".
- Banner at the top of the stage (role `status`): "Reconnecting to the video" (from `Reconnecting`), "Back online" for 3 s (from `Reconnected`), and when `Disconnected` or the live channel is `closed`: "You are disconnected" with a Rejoin button. Today `useVideoRoom` sets status "off" on `Disconnected` without a message (`lib/video.ts:78`); the app WebSocket state `LiveDot` is small. Two distinct states are shown separately: "Video" and "Live updates".
- "Click to hear the meeting" button when the browser blocks audio.

### 6.13 The agenda rail and case flow (5.4)

- Left rail on laptop (collapsible): each row is `n. patient initials or name (as allowed), state, time`. The state is one of Done (with the outcome word), Now (with a running clock), Next, Later, Not ready. Time is planned minutes, and for Now the elapsed and remaining from the timer (`current.timer`), turning amber at 2 minutes left and red at 0 (also a word, not colour alone).
- "Next case moves everyone": the coordinator's Next calls `setCurrent`; the server sends `current`; every member's stage changes, their "stepped away" state resets, and a polite announcement says "The meeting moved to case 4: initials". Today this is done (`MemberViewPage.tsx:78,91`); keep and add a 3 s toast "Moved to case 4 of 8".
- Presenter shown: the case's presenter (`meetings.presenter_of(case)`, `meetings.py:227`) appears as a chip "Presenter: Dr Priya, Radiology" in the top bar and as the Presenter badge on their tile; the person sharing a screen gets "Presenting" for the moment.
- Hands: the hand order list in People and a count badge on the People button.

### 6.14 The quorum line

A chip in the top bar and a block at the foot of the agenda rail. It reads, for example: "Heads present 4 of 5: Radiology, Medical Oncology, Surgical Oncology, Pathology. Radiation Oncology not here (AI agent standing in, support only). PM-JAY composition: Surgical, Radiation and Medical Oncology: 2 of 3 present as people."

- Heads: `board.heads()` and `attendance.head` (`meetings.py:405-416`, `board.py:114-127`): a head counts only when a person of that department has status present or remote. Never an agent.
- PM-JAY: the NHA HBP 2.2 manual (2021), section 3.9 Medical Oncology, says treatment decisions for cancer care are "advised" to be taken by a multidisciplinary tumor board, or sent to the nearest regional cancer centre, "that should include a highly trained team of Surgical, Radiation and Medical Oncologist" (`/data/vaidyx/night-v3/research_text/NHA-HBP-2.2-manual-2021.pdf.txt` lines 1050-1052; repeated at 1263-1265 and 1283-1285 for other packages). So the composition line has three entries: Surgical Oncology, Radiation Oncology, Medical Oncology. Each shows present (a person) or missing. It states a fact about who is present; it does not say a decision is valid or invalid. The manual's wording is "advised", so the line says "PM-JAY advises" and not "requires".
- UK comparison (for the owner's note only): the UK has no minimum individual attendance and measures quoracy over meetings, core members by tumour group (`gm-mdt-standards-v3-2023.txt` 197-206).
- The hospital's heads come from the hospital setting `board_heads`, so the line follows the setting.
- The quorum is saved in the board record per case (names present, heads present, composition met or not) since `DecisionForm` already records `members_present` (`DecisionForm.tsx:28`); add `heads_present`, `agents_standing_in` and `pmjay_composition` as lists of ids. Agents are listed apart and never count.

### 6.15 Existing components: kept, merged, new; backend needs

Kept as they are (restyled only if needed): `StageFrame`, `StageTopBar`, `BarButton`, `ControlBar`, `StagePanel` (becomes the one side panel), `SlideDots`, `DecisionStrip`, `SharedScreen` (becomes the stage's body), `PreJoin`, `CardDialog`, `DecisionForm`, `AgendaLists`, `JoinPage`, `MeetingsListPage`, `shared.tsx` (`TimerBadge`, `LiveDot`, `QuestionsList`, `SlideContent`).

Merged: `MemberViewPage` + `ControlView` + `MeetingRoomPage` into `CallShell` with three role configs; the member's People and Questions panels and the coordinator's five tabs into the single side panel; `AgentTile` into the strip (`TileGrid` renders agent tiles); `CallButton` and the present-mode toggle into More.

New: `CallShell`, `Stage` (the precedence rules and the screen-share track), `Strip` (tile layouts, pin, spotlight, speaker order), `AgentParticipantTile`, `SidePanel` with `PeoplePanel`, `ChatPanel`, `AgendaPanel`, `CasePanel`, `AgentsPanel`, `DecisionPanel`, `AgendaRail`, `QuorumLine`, `ReactionsMenu`, `DevicePopover`, `ConnectionBanner`, `ShortcutsDialog`, `useShortcuts`, `useCallState` (panel, layout, pin, local), and a phone `MoreSheet`.

Backend events and fields needed (all in `tumour_board/meetings.py` and `live.py`, none outside `tumour_board/`):

| Need | Event or field | Notes |
|---|---|---|
| Chat | `POST /meetings/{mid}/chat` {text}; event `chat` {id, by, by_name, text, at, case_id}; state field `chat` (last 200) and file `chat` inside the meeting JSON | Kept with the meeting record; limit 1000 characters; audited (`board.audit_event`); members only; no patient data rules beyond the existing (a chat line can contain patient details, so it is kept in the meeting, not sent to push or notifications). Apart from `questions`. |
| Reactions | `POST /meetings/{mid}/reaction` {kind}; event `reaction` {user, kind}; not stored (rate limit 1 per 2 s) | Four kinds. Permission: an admitted member (`meetings.is_member`). Audited (no content): `board.audit_event(mid, "reaction", user)` records who and when, not the kind. |
| Screen share permission | `meeting.present_allowed: [user]`; `POST /meetings/{mid}/present-allow` {user, allowed}; event `present_allowed`; `POST /meetings/{mid}/presenting` {on} to record who shares, event `presenting` {user, on} | LiveKit carries the pixels, the app carries who and whether it is allowed. The coordinator and the case presenter are allowed by default; the coordinator may add others (5.2). Audited. |
| Spotlight | `meeting.spotlight: [user]`; `POST /meetings/{mid}/spotlight`; event `spotlight` | Permission: the coordinator only (`can.manage`). Audited (no content): who set or removed it and for which users. Cleared on case change. |
| Pin | none | Per person, browser only. |
| Agents (D2) | `agent_state` becomes `agents: [{role, label, state, question}]`, events `agents` (list) and per-agent `agent_state` with `role`; `POST /meetings/{mid}/agents` {role, on}; `meeting.agents_added: [role]` | Today only the first absent head (`meetings.py:419-441`). States: ready, listening, thinking, speaking. Phase 6 builds the backend; Phase 5 builds the tiles from the list shape and shows today's single agent in the same list. |
| Quorum | `quorum` object in `view()`: `{heads: [{id, name, present}], agents: [role], pmjay: {surgical, radiation, medical: present}}` | Computed on the server so room and members agree. |
| Presenter | `current.presenter` {user, name, department} | From `presenter_of`. |
| Agenda times | `agenda[].minutes`, `elapsed_seconds` per case | Elapsed per case kept when the case ends (today the timer resets per case). |
| Token | `video.token(... can_publish_sources=[camera, microphone, screen_share, screen_share_audio], can_publish_data=True)` | Add parameters to `token()` (`video.py:72`). Keep identity as the username. Room-screen tokens: microphone and camera only. |
| Consistency | meeting record stores `chat`, `attendance with times`, `quorum at decision` | Required for the "kept with the meeting record" line of item 5.3. |

## 7. Phone and room screen specifics

- Phone (390 px wide, as in the screenshots): the current control view puts a 26 rem panel under the stage and the bar covers it (`real-coordinator-meeting-demo-control-dark-390.png`); the new layout uses sheets. Tap targets 44 px at least (the bar buttons are 44 px, `Stage.tsx:63`); five bar buttons only; text 16 px in inputs to stop browser zoom; safe-area padding at the bottom for notched phones; stage 16:10 on top, not scrolling the page; the keyboard opening pushes the sheet up.
- Phones cannot present or capture a screen in the browser, so Present is hidden; they can still watch a share.
- Data use: on cellular, the strip tiles ask for the low simulcast layer (adaptive stream does this); a "Save data" option in More sets camera off and stage at 720p.
- Room screen: dark theme only, no bottom bar (hover bar), minimum 28 px stage text, agenda 20 px, name tiles 20 px; reads agent answers aloud by default (D2), a visible "Agent voices on" chip (clicking it mutes them for this screen); the full screen button; no scrolling, content truncated with a "+n more" instead; a wake-lock request so the projector does not sleep (`navigator.wakeLock`, where supported); the room screen's own microphone and camera remain off until the coordinator turns them on (today `{ mic: false, cam: false }`, `MeetingRoomPage.tsx:40`).

## 8. Tests

Existing: `web/tb-nik/e2e/live/video.spec.ts` (one test, "two people in a meeting with video", Chromium fake devices via `playwright.live.config.ts`); backend `tumour_board/tests/test_nik_video.py`; `tumour_board/eval/e2e_nik.py` step 7 (LiveKit token validates against `/rtc/validate`, 403 for a person not admitted, WebSocket events); meetings unit tests under `tumour_board/tests/`. All stay green (5.6).

The two-person live test (new, extends `video.spec.ts`; coordinator and one member, fake camera and microphone, real LiveKit on :7880, synthetic Case Files only):
1. Coordinator starts the meeting; member joins with the code, waits, coordinator admits (toast, Admit); the member's screen leaves the waiting card.
2. Pre-join: both turn camera and mic on; each sees the other's tile with a live video element (non-zero `videoWidth`), the mic icon and the speaking ring (the fake mic beeps).
3. Layout: Auto shows stage plus strip; Grid shows tiles only; Pin for me on one side does not change the other side; Spotlight by the coordinator changes the member's layout.
4. Present: the coordinator clicks Present with Chromium's `--auto-select-desktop-capture-source` or `--use-fake-ui-for-media-stream` plus `--auto-select-tab-capture-source-by-title`; the member's stage shows the screen track (video element with non-zero size, "X is presenting"); the member cannot present until allowed; the coordinator allows the member, who presents and the first presenter's share stops; Stop presenting returns the stage to the slide.
5. Chat: the member sends a line; the coordinator sees it in Chat; reload the member page and the line is still there; the line is in the meeting record GET; a question to an agent does not appear in chat.
6. Hand and reaction: the member raises a hand; the coordinator sees the hand and its order; a reaction appears on the tile and disappears.
7. Case flow: Next case moves the member's stage and rail; the timer chip is the same on both; the presenter chip changes.
8. Quorum: with Radiology head absent the line shows "Radiology: AI agent standing in", the agent tile appears in the strip, "in the meeting" does not count it, and the PM-JAY composition line counts three Oncology departments by people only.
9. Devices and network: switching the microphone in the popover keeps the call; `context.setOffline(true)` for 5 s shows the Reconnecting banner, then "Back online"; a forced disconnect shows Rejoin.
10. Keyboard: Ctrl+D toggles mute, Esc closes a panel, `?` shows the list; focus in the chat box does not trigger shortcuts.
11. Accessibility: tab through the bar (every button has a name); `aria-live` announcements for admit and next case; run axe on the stage with a panel open.
12. Ending: Leave removes the tile on the other side; End meeting shows "The meeting has ended" for the member.

Screenshots to take (light and dark, each at 1366 laptop, 1920 for the room screen, 390 for phone), named `real-<role>-call-<state>-<theme>-<width>.png`:
- member: waiting; in the call with stage and strip; panel People; panel Chat; panel Agenda; panel Case; panel Agents; More menu; device popover; reconnect banner; stepped away; presenting by another; screen shared; spotlight; no one presented (grid); phone sheet More; phone with Chat.
- coordinator: control layout; Decision panel; admit toast; tile menu; presenter allow; End meeting dialog; phone.
- room screen: summary and stage; screen shared; agents standing in; questions and hands; decision typed; empty (no case).
- join and waiting room, pre-join with device menu, agenda page before start (unchanged but re-shot).
Fix the baseline gap: admit the baseline member first so `member-view` shows the real call (current baseline files show "You have not joined this meeting", section 2.1). Use only synthetic Case Files (never `TB-2026-bharath`).

## 9. Open questions for the owner

1. Chat: kept with the meeting record for how long, and who may read it afterwards (the meeting's members, or the coordinator only)? Chat can contain patient details; the proposal keeps it inside the meeting record with the same access as the meeting.
2. Who may present a screen by default: only the coordinator and the case's presenter (proposed), or every admitted member? May the coordinator remove a share immediately (proposed: yes)?
3. Screen sharing shows whatever the person picks, including other windows with patient data from outside Vaidyx. Is a one-line warning on starting ("Only share what the board needs; the share is not recorded") enough?
4. Agent voices (D2: spoken by default): should the answer be spoken only on the room screen, or also in each remote member's browser? (Proposed: both, with a per-person mute.) Should an agent's spoken answer be heard by remote members who joined by phone? (Not possible in this build.)
5. Quorum line: show the PM-JAY three (Surgical, Radiation, Medical Oncology) in addition to the hospital's five heads (proposed), or only one of them? Should the line turn amber when the PM-JAY composition is not met, or stay neutral (proposed: a plain word, no colour alarm)?
6. Captions: leave out for now (proposed; voice is Phase 4).
7. Reactions: keep four, or drop them for a clinical meeting? (Proposed: keep, hand and thumbs-up style only, off by a setting.)
8. Spotlight limit: 3 people (proposed) or 9 (Zoom)?
9. Recording: none today and none proposed ("Nothing is recorded" is on the pre-join page, `PreJoin.tsx:114`). Confirm.
10. Room screen: keep the 30% summary column as the default, or put the stage first with the summary one click away (proposed: stage first, summary column on)?
11. Outside experts: may an admitted outside expert chat and present? (Proposed: chat yes, present only if allowed; they follow the shared screen only today, `api/deck.py:37`.)
