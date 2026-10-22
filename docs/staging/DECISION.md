# Decision: Vaidyx works out a draft stage, with proof (22 Oct 2026)

**Decided by the owner (Nikhil-Rao20), 22 Oct 2026**, after the radiologist's input ("to reduce errors in the staging of the cancer";
"the agent will tell the stage based on the guidelines and provide proof") and the owner's own words: "the staging is eventually done by
the doctor whose role is to see that case and search what is there in the books and all the guidelines accordingly, that is what we are
replacing here ... with the proof ... Vaidyx works it out is the one, and then we need to show the written and the guidelines properly".

This changes the signed scope, which said Vaidyx never computes a stage. Everything else in the scope stands: no image interpretation, no
diagnosis, no treatment advice; images are for people.

## What Vaidyx does

For breast (AJCC 8th edition, chapter 48), lung (chapter 36) and cervix (FIGO 2018 with AJCC chapter 52): the doctor's manual work of
opening the book and walking the T, N and M tables to the stage group. Each step shows the report line and the book line side by side;
the book opens at the page with the line highlighted. The stage the reports wrote, and its history, are shown with it.

## The six guards (owner's confirmation, 22 Oct)

1. Always labelled **"Vaidyx draft stage, for the board to confirm"**; it counts only after a doctor taps Confirm (audited).
2. The book's tables are fixed rules in code, written from the book with their page; the model only picks which report line fits a
   category, quoting the line (verified against the report like every value). The stage group is a table lookup in code, never a guess.
3. Missing or unclear inputs give "Cannot stage: <what is missing>", never a guess.
4. A stage written in a report that differs from the draft is shown beside it and flagged; nothing is overridden.
5. A clinician checks each cancer's rule tables before they are switched on. **Sign-off: the owner decides later.** Until then the
   feature is off by default; the internal instance (:7000) shows it as a labelled preview ("Rule tables not yet checked by a
   clinician"); the public demo does not show it.
6. No treatment advice comes with the stage.

## Wording for the website and the deck

"Vaidyx works out a draft stage from the guidelines, with the report line and the book page behind every step; the board confirms it."
Never "Vaidyx stages the cancer" or any accuracy claim.
