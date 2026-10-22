# Demo video version 2: Vaidyx-centric

Status: **planned, not recorded.** The owner records it later ("lets just keep this later on"). Written 20 Oct 2026.

## Why

Feedback on version 1, from the owner's radiologist: the hospital-system (HIS) screens are confusing for an external viewer. Version 1
spends about 2.5 of its 14 minutes in the mock hospital (registration, OPD, laboratory, radiology, pathology) and a split screen.

The owner's direction:
- **Vaidyx-centric.** Show Vaidyx working; the hospital system stays in the background.
- **The main pitch: Vaidyx connects to the hospital's existing systems** (HIS, LIS / RIS, PACS). Nothing is re-entered, nothing is
  copied by hand.
- In the video, **say** that the pathologist updates the hospital system and the treating doctor re-fetches; do not show the HIS forms.

## What changes from version 1

| Version 1 | Version 2 |
|---|---|
| Chapters 1 and 2: reception, OPD, lab, radiology, pathology in the HIS (2.5 min) | gone; replaced by one 25-second "Connected to your hospital" scene |
| Chapter 4: split screen, Vaidyx left, HIS right | Vaidyx only; a short card says what happens in the hospital system |
| Images in the PACS viewer, near the end | moved up as a pitch moment: "your PACS, opened from the Case File" |
| 14 min | about 8 to 9 min |

## Storyboard

| # | Scene | Shows | Narration (draft) |
|---|---|---|---|
| 0 | Title | Vaidyx Tumour Board, synthetic data note | "Vaidyx Tumour Board prepares each patient for the Tumour Board, from the hospital's own records." |
| 1 | **Connected to your hospital** | a designed diagram (not the HIS UI): HIS, LIS / RIS and PACS on the left, read-only lines into Vaidyx; then the admin's Hospital system step with "Test again" passing | "Vaidyx connects to the systems the hospital already has: the HIS, the lab and radiology systems, and the PACS. It reads them; it never writes back, and nobody types a report twice." |
| 2 | A Case File from a UHID | New Case File, Look up, the registration found, Create; the reports arrive | "The doctor types the patient's UHID. Vaidyx finds the registration and fetches every report in seconds." |
| 3 | The Board brief | question, still open, a value and its source line | "Every value carries its quote, one click from the source document." |
| 4 | **The report that is missing** | "Ask Pathology"; the Pathology inbox in Vaidyx (Acknowledge); then a **card**: "Pathology signs the IHC in the hospital system, as they do today"; back in Vaidyx: Re-fetch, the results arrive, the item closes | "The receptor results are not in yet, so the surgeon asks Pathology in one click. The pathologist signs the report in the hospital system as usual. The surgeon presses Re-fetch, and the results arrive with their quotes." |
| 5 | **Images from your PACS** | Open images on the mammogram report: the hospital's PACS viewer | "Images stay in the hospital's PACS. Vaidyx opens them for the doctors from the report; no model reads them." |
| 6 | Ready for the Board | confirm a value, enter one, Ask this Case File, Mark ready, the summary, a specialty brief | as version 1 |
| 7 | The meeting | create, agenda, join code, cameras, room screen (slide, signed report), decision, cards, minutes deck | as version 1, shorter |
| 8 | After the Board | Board form, downloads, activity log | as version 1 |
| 9 | Close | the pitch again: "Your HIS, your PACS, one Case File for the Board" | |

Optional, by the owner's choice: the phone (30 s) and the public website (60 s) from version 1.

## How to make it

Most of version 1's footage is Vaidyx-only and can be reused (`/data/vaidyx/demo_video/raw/run2`): scenes 2, 3, 6, 7 and 8, and the
Vaidyx side of scene 4 (the surgeon's Ask Pathology and Re-fetch, the Pathology head's inbox). New material:
- scene 1: the diagram (an overlay page in `rec/edit.py`, like the chapter cards) and a short recording of the admin's Hospital system
  step (`admin` chapter, a new mark on the "Test again" moment);
- scene 4: the card instead of the right pane; the left pane at full width (the doctor's and head's sessions were recorded at
  1080 x 1215 for the split; re-record those two shots at full size for the best result, about 5 minutes);
- scene 5: the images shot exists (`images` session); add a 2-second "Open images" click on the report first.

So version 2 is mostly a new `plan.py` and two or three short re-recordings: about half a day with review, not a full re-record.

## Wording to check before recording

- **Pathology reports live in the HIS or LIS; the PACS holds images.** Say "the pathologist signs the report in the hospital system",
  and keep "PACS" for the images, so a radiologist or pathologist watching does not stop at it.
- **What is proven:** Vaidyx reads a hospital system over FHIR R4 (read only, bearer token; `tumour_board/his_client.py`) and opens
  images from a PACS through DICOMweb and the OHIF viewer (`tumour_board/pacs.py`). Both are shown working against the demo hospital
  and Orthanc. It has not yet been connected to a real hospital's HIS or PACS. Suggested line: "built on the standard interfaces
  hospital systems use (FHIR and DICOMweb), so it connects to your existing HIS and PACS" rather than naming vendors or claiming a
  tested integration.
- No accuracy or validation claims (project rule).

## Open for the owner

1. Keep the phone and website chapters, or end at the Board?
2. Voice: Kokoro again, or Maya1 once the GPU has room (about 6 minutes of narration takes about 2 hours on the CPU)?
3. Audience: still the tech team, or external (hospitals)? For external, drop the "recorded on localhost" line and the tech details.
