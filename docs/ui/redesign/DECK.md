# The board deck (.pptx): how it is made, how to change it

Written 19 Oct 2026 (redesign R4). Module `tumour_board/deck/` (python-pptx 1.0.2). Routes `tumour_board/api/deck.py`.

## What a reader gets
| Deck | Who | Slides |
|---|---|---|
| Meeting deck, `GET /api/tb/meetings/{mid}/deck` | the MDT Coordinator, the admitted members (never an outside expert) | cover, agenda, one chapter per Case File (discussion first, then noting); when the meeting is closed each chapter ends with its outcome and the deck ends with the minutes (outcomes table, members who took part) |
| Case deck, `GET /api/tb/cases/{cid}/deck` | anyone who may open the whole Case File (scope FULL) | cover, the chapter, the latest outcome if any |

A chapter: the case title slide (patient, cancer and setting as recorded, Responsible Department, IP / OP numbers, board date, the question for the Tumour Board), the summary (sentences with their sources in brackets; labelled "Reviewed" or "AI draft, not reviewed"; or the checklist when there is no summary yet), the values with their sources (table, paginated), imaging and pathology records (status, date, findings as recorded), gaps and waivers, points for review (numbered, "AI drafts from the records"), the outcome (decision in the board's words, rationale, intent, responsible doctor, next step, awaited, concerns, members present, cards).

Nothing on a slide comes from a model at deck time: the material is `meetings.slides(cid)` (what the room screen shows) and the case state. Every download is audited (`deck_downloaded` on the meeting or the Case File).

## The design (`Deck` in `tumour_board/deck/__init__.py`)
| Element | Rule |
|---|---|
| Page | 16:9, 13.333 x 7.5 in; 0.45 in margin; page background #F5F7FA, cards white |
| Type | Arial everywhere (on every laptop and in LibreOffice); body 13-14 pt, tables 10-11 pt, titles 26 pt, cover title 24-36 pt by length |
| Colour | ink #121A24, body #3B4754, muted #5F6B78, lines #E2E8EF; teal #00C0B5 for the title bar and the accent; navy #00183C (the logo's) for the cover band; status tones ok/warn/bad/review as on the website |
| Cover | navy band left with the white Vaidyx mark and wordmark and "TUMOUR BOARD"; right: the hospital logo (uploaded PNG/JPEG, else the demo emblem for the demo hospital), the hospital name, the title, the lines, the scope line; "SYNTHETIC DATA" pill for the demo |
| Every slide | kicker (small teal capitals), title, the footer "Vaidyx Tumour Board · hospital · meeting or case" with the Vaidyx mark and the page number; "SYNTHETIC DATA" on the right when the data is synthetic |
| Overflow | a list or table that does not fit carries on to "(2 of n)" slides; never cut |
| Closing | navy slide with the marks and the scope line, the hospital logo bottom right |

Assets: `tumour_board/deck/assets/` (the marks rendered from the brand SVGs; `demo-hospital.png` is a synthetic emblem, never a real hospital's).

## The hospital logo
`POST /api/tb/setup/hospital/logo {data: "data:image/png;base64,..."}` (root admin; PNG or JPEG, 1 MB); kept as `data/tumour_board/hospital_logo.<ext>`, recorded in `org.json hospital.logo`; `GET /api/tb/hospital/logo` serves it; `DELETE` removes it. The set-up's Hospital step has the upload (`components/LogoUpload.tsx`).

## Looking at a deck (development)
`/data/vaidyx/venv/app/bin/python -m tumour_board.deck.render case TB-2026-0001 /tmp/out` writes the .pptx, the PDF and one PNG per page. Needs the portable LibreOffice at `/data/vaidyx/tools/libreoffice/squashfs-root/AppRun` (24.2 AppImage, unpacked with `--appimage-extract`; `libs/usr/lib64/libX11-xcb.so.1` from the Rocky 8 `libX11-xcb` rpm, since the server has no X11 client libraries). Review the PNGs before changing the design.

## Changing the design
- Colours and fonts: the constants at the top of `tumour_board/deck/__init__.py`.
- A new slide kind: a method on `Deck` (use `chrome()` for the title row and footer, `bullets()` / `table()` for the body), called from `chapter()` or `build_meeting()`.
- Text fitting: `_lines()` and `_fit()` estimate lines by character count; bold display text runs about 25 % wider.
- Tests: `tumour_board/tests/test_nik_deck.py` (who may download, slide texts, the logo upload).
