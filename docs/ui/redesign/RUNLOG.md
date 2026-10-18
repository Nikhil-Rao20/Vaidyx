# Redesign run log (resume from here)
| When | Phase | Done | Next |
|---|---|---|---|
| 19 Oct 00:10 | R0 | plan written | fonts, tokens, brand, shell |
| 19 Oct 00:55 | R0 | committed a4c45c4: Inter, tokens, brand, splash, nav Case Files + Meetings, floating Dock, sign-in | R1 |
| 19 Oct 01:40 | R1 | built (uncommitted): lib/search (any-part id match, server + client + Ctrl+K), ViewsBar, FilterPanel, Calendar/DateInput/TimeInput, CaseRow, CaseFileList, CaseFileHome (Join with a code), PatientLine; server ids/accessions + test | review filter/search shots, commit, then R2 Case File |
| 19 Oct 02:50 | R1 | committed 7329bf6 | |
| 19 Oct 03:05 | R2 | committed 0f3ae72 (Board brief, folded records, helper badges, sentence-case titles) | |
| 19 Oct 03:40 | R3 | built (uncommitted): lib/video (pre-join choice, room identity), Stage.tsx, VideoTiles (tiles), PreJoin, People, MemberViewPage, MeetingRoomPage, ControlView (conduct), agenda ack toast, TimeInput on new meeting; backend video-token {screen: room} | shots review, meetings.spec fixes, commit; then R4 deck |
| 19 Oct 04:30 | R3 | committed 6b4aa16 (stage, tiles, pre-join, conduct panel, room screen) | |
| 19 Oct 05:20 | R4 | built (uncommitted): tumour_board/deck (python-pptx design, assets), api/deck.py (meeting + case decks, hospital logo upload), tests 4/4, LogoUpload in set-up, Download menu on the Case File, Deck button on the meeting page; LibreOffice portable at /data/vaidyx/tools/libreoffice for rendering (deck/render.py); docs DECK.md | set-up shot, full suite, commit, restart :7000; then R5 |
