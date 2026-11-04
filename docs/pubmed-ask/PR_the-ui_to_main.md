Title: Meetings v2 and Ask PubMed

## What this brings to main
32 commits from `the-ui`, merging cleanly into `main`.

**Meetings v2 (2 to 3 Nov)**
- One-page planner for the MDT Coordinator: weekly series plus extra meetings; the agenda builds itself by urgency; an unplanned Case File can be taken up during the meeting.
- The Case File itself on screen instead of slides (Board view). Everyone follows the coordinator; "Look around" lets a member browse; the meeting is in the light theme.
- Recorder started by the coordinator: speech becomes text live and no audio is ever stored. AI discussion notes per case, each line backed by the exact words said.
- "Summary after the board" with the decisions, next to the summary before the board.
- Meeting record and board record as PDF (the PowerPoint deck is removed).

**Ask PubMed (3 Nov, the professor's suggestion)**
- General questions answered only from PubMed. Papers come from NCBI E-utilities; the model never names a paper.
- Every line must quote the paper's abstract word for word with its PMID; code checks each quote, number and name, and drops a line that fails.
- In the Case File Ask (records and PubMed tabs), on the home screen (`/pubmed`, in the nav and the phone Dock) and in the meeting panel.
- Labelled "Published evidence, not advice for this patient".
- Design, proof and test reports in `docs/pubmed-ask/` (PROOF.md, LIVE_EVAL.md, HOW_TO_TRY.md).

## Checks
- Unit suite: 4858 passed.
- Mocked browser screens: 157 passed.
- Live run on the real app, desktop and phone, all roles: 0 problems.
- PubMed proof: every cited paper found in PubMed's own search, every quote found on the paper's PubMed page, 0 invented PMIDs.

## For deployment (Eswar)
- New outbound host needed: `eutils.ncbi.nlm.nih.gov` (Ask PubMed).
- New setting, not in git: `data/tumour_board/pubmed.json` with `{"email": ..., "api_key": ...}`. The API key is optional: without it the limit is 3 calls a second, with it 10.
- New router `pubmed` is loaded by `routes/tumour_board_routes.py`.
- `static/tb-nik` is the rebuilt website.

## Known small issues (follow-up)
- The decision form does not fill in the responsible clinician by default.
- The message Case File picker finds a file by id only, not by patient name.
- The meeting PDF gives 403 to a treating consultant who was not admitted to the meeting.
- The case summary shows "Being written" above a version that is already written.
- The Ask PubMed wording check does not catch "should not be used".
