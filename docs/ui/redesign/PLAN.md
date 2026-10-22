# Vaidyx-TB redesign (the UI/UX phase), 19 Oct 2026

Owner's brief (19 Oct, free hand): professional, not "AI slop"; search that matches any part of any id; nav = Case Files + Meetings;
simpler rows for the doctor; advanced filters; the Case File with the important things on top and open items in one place; a great PPT
with the hospital logo and the Vaidyx logo; a Google Meet / Zoom-like meeting with video and mic that work; the Vaidyx logo and animation
for light and dark; strong UI components, a good amount of animation; UX research per role. Roles played: designer, frontend engineer,
psychologist, honest third-party user.

Rules that stay: scope (no diagnosis / staging / treatment advice, verbatim quotes only), terminology, no em dashes, teal theme as the
brand colour, laptop first + Dock on the phone, commit per piece as Nikhil-Rao20, never push, memory at every checkpoint.

## Design direction: "clinical calm"
| Element | Decision |
|---|---|
| Type | Inter (variable, self-hosted) for everything; ids in Inter with tabular figures, never mono; a 5-step type scale |
| Colour | Teal #00c0b5 is the brand and the ONE primary action per screen; status by soft tints (ok / warn / bad / review); greys calmer |
| Surfaces | One card level; 12 px radius; hairline borders; shadow only on floating things |
| Brand | Real icon + wordmark (wordmark black on light, light-blue on dark); splash on sign-in (port of the main app's); favicon |
| Motion | Page and panel transitions, staggered row entrance, count-ups, the Dock pill, skeletons; 150-300 ms; reduced-motion respected |
| Density | Fewer chips; quotes as quiet source marks; "as recorded" said once per section, not per row |

## Phases
| # | Phase | Pieces | Check |
|---|---|---|---|
| R0 | Foundation | fonts, tokens, brand components, splash, shell + nav (Case Files, Meetings, role items), motion primitives, shot harness | shots of shell light/dark, 1366 + 390 |
| R1 | Worklist | search (server + list + Ctrl+K: any substring, case-insensitive, separators ignored, highlights), rows, filter panel, saved views, empty states | shots per role; search tests |
| R2 | Case File | Board brief on top (question, status, open items with actions, staging as recorded, summary), collapsed sections with counts, helpers in background with badges, date/time picker, agenda-add confirmation | shots; slots tests unchanged |
| R3 | Meeting | pre-join, stage, tiles, control bar, side panels (people, questions, cards), conduct panel, room screen, join page, agenda page | 2-participant Playwright run with fake camera/mic |
| R4 | Board deck | tumour_board/deck/ (python-pptx design system), hospital logo upload in set-up, meeting deck + case deck + minutes downloads, skill doc | slides rendered to PDF/PNG if LibreOffice portable installs; else content tests |
| R5 | Rest | Requests, People, Admin set-up, Settings, Activity, sign-in, first login, errors, phone | shots |
| R6 | QA | all roles, both sizes, both themes; e2e; REVIEW guide for the owner | e2e green |

## Run log
See RUNLOG.md (resume from it after a limit or a compaction).
