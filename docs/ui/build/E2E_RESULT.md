# End-to-end scenario: result of the last run

Run 20261018-135112 on 18/10/2026, 66 s, by `python -m tumour_board.eval.e2e_nik`. Synthetic data only; no passwords, tokens or codes are logged.

**97 of 97 checks passed.**

| What | Value |
|---|---|
| Patient (demo HIMS) | E2E Lakshmi R (SYNTHETIC), UHID VXH/26/004326, OP No. OP/26/118735 |
| Case File (scenario) | E2E-20261018-135112-A |
| Case File (outside reports of VXH/26/004219) | E2E-20261018-135112-B |
| Meeting | S20261018-1f00 (E2E scenario 20261018-135112) |
| Resident login | e2e.resident@vaidyx-demo.invalid |
| Mammogram image | synthetic (stays synthetic: every public series that fits this test is assigned to another study or patient (one source patient never serves two HIMS patients)) |
| Line marked not needed (resident proposal) | record:mri_breast |
| Models | reader Qwen3.5-4B (Chinese, non-medical), reasoner Gemma-4-31B (non-medical) |

| Step | Check | Result | Evidence |
|---|---|---|---|
| 0 services | Vaidyx, HIMS, Orthanc and LiveKit answer | PASS | Vaidyx up, HIMS up, Orthanc up, LiveKit up |
| 0 services | demo logins and the HIMS write token are on the server | PASS | 13 Vaidyx demo logins, 10 HIMS logins, write token present |
| 0 services | models answer (reader Qwen3.5-4B, Chinese, non-medical; reasoner Gemma-4-31B, non-medical) | PASS | reasoner up, reader up |
| 0 earlier runs | Case Files and meetings of earlier E2E runs cleared | PASS | Case Files removed: E2E-20261018-134403-A, E2E-20261018-134403-B; meetings ended or cancelled: none |
| 0 resident account | Breast Surgery department admin places the resident (email login) | PASS | HTTP 200, created False |
| 0 resident account | department admin resets the resident's password (mailto) | PASS | HTTP 200 |
| 0 resident account | the mailto carries the login name and a first password (kept in memory only) | PASS | existing account, password reset by the department admin; mailto to e2e.resident@vaidyx-demo.invalid, password not logged |
| 0 resident account | first sign-in: the password must be changed | PASS | must_change_password=True |
| 0 resident account | until then Case Files are refused (409 password_change_required) | PASS | HTTP 409 |
| 0 resident account | resident chooses a new password (forced change) | PASS | HTTP 200 |
| 0 resident account | the resident is placed as resident of Breast Surgery | PASS | departments {'breast_surgery': 'resident'}, primary role resident |
| 1 HIMS | registration desk registers the patient (woman, 58) and gets a UHID | PASS | E2E Lakshmi R (SYNTHETIC), VXH/26/004326, 58 F; similar registration of an earlier run confirmed as a different person |
| 1 HIMS | OPD visit opened in Breast Surgery (OP No.) | PASS | OP/26/118735 with Dr Kavitha Raghunathan |
| 1 HIMS | OPD note signed on the screen by the OPD consultant | PASS | /his/encounters/op-26-118735?flash=OPD note signed on OP/26/118735. PDF rendered (version 1). |
| 1 HIMS | orders placed: mammogram, core biopsy, CBC, LFT, CECT chest | PASS | mammogram RAD/26/01035; hpe_biopsy PATH/26/00485; cbc PATH/26/00486; lft BIO/26/02242; cect_chest_abdomen_pelvis RAD/26/01036 |
| 1 HIMS | lab CBC: sample collected, results entered, verified and signed | PASS | rep-path-26-00486 final v2, signature sig-rep-path-26-00486-v2 |
| 1 HIMS | lab LFT: sample collected, results entered, verified and signed | PASS | rep-bio-26-02242 final v2, signature sig-rep-bio-26-02242-v2 |
| 1 HIMS | radiology: mammogram scheduled today, reported and signed | PASS | rep-rad-26-01035 final; desk notes: PDF rendered (version 2) |
| 1 HIMS | imaging study recorded with its image source | PASS | study 2.25.21555180153011644327271729474170359..., MG, 2 images, source synthetic (stays synthetic: every public series that fits this test is assigned to another study or patient (one source patient never serves two HIMS patients)) |
| 1 HIMS | pathology: biopsy received (block No.), HPE final signed | PASS | block PATH/26/00485-A1, rep-path-26-00485 final |
| 1 HIMS | IHC (ER, PR, HER2, Ki-67) added on by the pathologist on the screen, left pending | PASS | /his/pathology/orders/path-26-00487?flash=Add-on order PATH/26/00487 IHC: ER, PR, HER2, Ki-67 placed. |
| 1 HIMS | worklists as planned: IHC ordered, CECT chest not done | PASS | {"lft": "completed", "opd_note": "completed", "hpe_biopsy": "completed", "cbc": "completed", "mammogram": "completed", "cect_chest_abdomen_pelvis": "ordered", "ihc_breast": "ordered"} |
| 2 PACS | the mammogram study is in Orthanc (QIDO by accession and PatientID = UHID) | PASS | 1 study, uid matches the HIMS ImagingStudy: True, modalities ['MG'], 2 instances |
| 3 Case File | Dr Breast looks the UHID up in the HIMS | PASS | E2E Lakshmi R (SYNTHETIC), 5 reports in the window, 0 older |
| 3 Case File | Case File created from the UHID (protocol breast, setting locally advanced, as recorded) | PASS | E2E-20261018-135112-A: HTTP 200 |
| 3 Case File | the first fetch job finishes | PASS | finished in 6.3 s, 8 records |
| 3 Case File | slots: mammogram found with its quote | PASS | BILATERAL MAMMOGRAPHY REPORT, 18/10/2026, final; lesion size found: "5.8 x 4.9 cm" |
| 3 Case File | slots: lesion size quote is verbatim in the mammogram report | PASS | quote "measuring 5.8 x 4.9 cm" |
| 3 Case File | slots: HPE found, histological type quoted verbatim | PASS | "Histological type: Invasive breast carcinoma of no special type" |
| 3 Case File | slots: IHC (receptor status) waiting or not found | PASS | receptor status not_found (Pending: Estrogen receptor (ER): "IHC for ER, PR, HER2 and Ki-67 to follow" in HISTOPATHOLOGY REPORT); ER not_found |
| 3 Case File | slots: CT chest not found in the file (ordered, not done) | PASS | CECT chest and abdomen not_found: No cect chest and abdomen in the Case File; Ordered in the HIS (RAD/26/01036): CECT chest, abdomen and pelvis, no report; metastatic work-up not_found |
| 3 Case File | left before the board counted | PASS | 7 lines left; blockers: The question for the Tumour Board is not recorded: type it, or ask the treating team to record it |
| 3 Case File | urgency set to 4 by the consultant | PASS | level 4 set by tb-breast-doc |
| 3 Case File | join code made (6 digits, not logged) | PASS | expires 2026-10-25T13:51:27 |
| 3 Case File | the resident joins with /case-join | PASS | joined: E2E Lakshmi R (SYNTHETIC), UHID VXH/26/004326 |
| 3 Case File | the team shows the resident | PASS | Dr Asha (E2E resident, demo) until 2027-04-16 |
| 3 Case File | a line the resident can propose as not needed | PASS | candidates ['record:mri_breast', 'record:pet_ct'] |
| 3 Case File | the resident proposes "not needed" on MRI breast | PASS | proposal Pa60175d2 by e2e.resident@vaidyx-demo.invalid |
| 3 Case File | the consultant sees the sign-off in /waiting | PASS | Sign off: mark a line not needed |
| 3 Case File | the resident cannot waive directly (403) | PASS | HTTP 403 |
| 3 Case File | the consultant approves the proposal | PASS | HTTP 200 |
| 3 Case File | the line is not needed now, the waive recorded as the consultant | PASS | not_needed: Not needed: MRI breast not needed before the first discussion: mammogram and core biopsy are in the file. (Dr Breast Surgery (demo)) |
| 3 Case File | the consultant asks Pathology for the IHC (ask-department) | PASS | HTTP 200; request A486256 to Pathology, due 25/10/2026 |
| 3 Case File | the IHC lines now say waiting on Pathology | PASS | receptor status waiting, ER waiting, asked 2026-10-18T13:51:27 |
| 3 Case File | Pathology (tb-path-head) sees the request in GET /inbox | PASS | 1 request(s) for this Case File; UHID VXH/26/004326, encounter {'op_no': 'OP/26/118735'} |
| 3 Case File | Pathology acknowledges it | PASS | HTTP 200 |
| 3 Case File | Pathology does not read the team chat | PASS | HTTP 403 |
| 4 IHC | the pathologist enters and signs the IHC on the screen | PASS | /his/pathology/orders/path-26-00487?flash=PATH/26/00487: final. PDF rendered (version 1). |
| 4 IHC | Vaidyx re-fetch started (POST his/refetch) | PASS | HTTP 200, 1 new or changed record(s) |
| 4 IHC | the re-fetch job finishes | PASS | finished in 4.0 s; result {"closed": ["A486256"], "opened": [], "summary_stale": ""} |
| 4 IHC | the request closed by itself | PASS | status completed at 2026-10-18T13:51:30; the re-fetch closed ['A486256'] |
| 4 IHC | the IHC line is found now, ER quoted verbatim | PASS | receptor status found; ER "Positive (Allred score 8/8)" from "Oestrogen receptor (ER) Positive (Allred score 8/8)" |
| 4 IHC | the owner is told what closed | PASS | Re-fetch from the HIS for E2E Lakshmi R (SYNTHETIC) (E2E-20261018-135112-A): 1 request(s) closed: Receptor status (ER / PR / HER2) |
| 5 Ask | a question through POST chats (real model) is answered | PASS | answered in 5 s, 5 statement(s), 0 dropped as unverified |
| 5 Ask | every citation is a verbatim quote of a report | PASS | 5 citation(s), 0 not verbatim; first: "Histological type: Invasive breast carcinoma of no special type" |
| 5 Ask | shared with the team: the resident sees the thread | PASS | 1 thread(s) for the resident |
| 6 Ready | the board question is typed on its line | PASS | entered: entered by Dr Breast Surgery (demo), no report |
| 6 Ready | Mark ready is allowed | PASS | left before the board 3; blockers [] |
| 6 Ready | Mark ready (POST ready) | PASS | HTTP 200 |
| 6 Ready | the ready hook prepared the summary within 3 minutes (AI draft, not reviewed) | PASS | ready after 25 s: 6 section(s), label "AI draft, not reviewed", model Gemma-4-31B-it |
| 6 Ready | the five heads' briefs are queued or ready | PASS | {"radiology": "preparing", "pathology": "preparing", "medical_oncology": "preparing", "surgical_oncology": "preparing", "radiation_oncology": "preparing", "nuclear_medicine": "none"} |
| 7 Meeting | the coordinator creates a meeting today with video | PASS | S20261018-1f00 2026-10-18 14:02, video True |
| 7 Meeting | the Case File is put in For discussion | PASS | E2E Lakshmi R (SYNTHETIC), UHID VXH/26/004326 |
| 7 Meeting | the agenda row shows the board question as typed | PASS | "Locally advanced breast cancer as recorded: neoadjuvant systemic therapy first, or upfront surgery?" |
| 7 Meeting | agenda sent | PASS | HTTP 200 {"sent_at": "2026-10-18T13:52:03", "sent_to": ["radiology", "medical_oncology", "surgical_oncology", "pathology", "radiation_oncology", "nuclear_medicine", "bre |
| 7 Meeting | meeting code made (6 digits, not logged) | PASS | expires 2026-10-19T01:52:03 |
| 7 Meeting | two members join with the code and wait to be admitted | PASS | tb-rad-doc waiting, tb-path-head waiting |
| 7 Meeting | the coordinator admits them: one in the room, one remote | PASS | tb-rad-doc present, tb-path-head remote |
| 7 Meeting | WebSocket (cookie auth) for the room screen and a remote member receives the state | PASS | room screen: 2 attendance rows; remote member: state received |
| 7 Meeting | a socket from another origin is refused | PASS | closed with code 1008 |
| 7 Meeting | the meeting starts | PASS | HTTP 200; 3 stand-in brief(s) preparing |
| 7 Meeting | the coordinator sets the current Case File (current event on the socket) | PASS | HTTP 200; event received |
| 7 Meeting | the mammogram record is in the Case File | PASS | HIS/OP_26_118735/Bilateral_mammogram_v1.pdf |
| 7 Meeting | a record on the shared screen: the members follow it (only that record) | PASS | HPE report page for tb-rad-doc HTTP 200 (image/png); a record not on the screen HTTP 403 |
| 7 Meeting | images opened on the shared screen: the viewer url arrives on the socket | PASS | /api/tb/pacs/ohif/viewer?StudyInstanceUIDs=2.25.215551801530116443272717294741703590477; granted ['tb-mdt', 'tb-path-head', 'tb-rad-doc'] |
| 7 Meeting | GET of the viewer url through /api/tb/pacs answers 200 for an admitted member | PASS | tb-rad-doc HTTP 200, 4847 bytes |
| 7 Meeting | the study's DICOMweb series answer through the proxy for that member | PASS | HTTP 200 |
| 7 Meeting | a doctor not admitted to the meeting gets no viewer (403) | PASS | tb-medonc-doc HTTP 403 |
| 7 Meeting | a member types a question; it reaches the room screen | PASS | HTTP 200; event received |
| 7 Meeting | the decision is typed live (decision_live broadcast, not saved) | PASS | event received |
| 7 Meeting | the decision is saved after the read-back (outcome decision) | PASS | HTTP 200; record B249a64 |
| 7 Meeting | end of the case: cards requested from the heads | PASS | ['radiology', 'medical_oncology', 'surgical_oncology', 'pathology', 'radiation_oncology'] |
| 7 Meeting | a head gives a card | PASS | Dr Pathology head (demo) (pathology), head True |
| 7 Meeting | the owner's team reads the cards | PASS | 1 card(s), missing ['tb-rad-doc'] |
| 7 Meeting | LiveKit: video token for a member validates against /rtc/validate | PASS | room tb-S20261018-1f00, identity tb-path-head, LiveKit 200 success |
| 7 Meeting | no video token for someone not admitted (403) | PASS | HTTP 403 |
| 7 Meeting | the coordinator ends the meeting | PASS | status closed |
| 8 Outcome | the owner gets the outcome notification | PASS | Board outcome for E2E Lakshmi R (SYNTHETIC) (E2E-20261018-135112-A): Decision recorded |
| 8 Outcome | GET /case-list shows the Case File as decided | PASS | Decided; urgency 4; residents 1 |
| 9 Outside reports | the demo patient VXH/26/004219 is in the HIMS | PASS | Priya Venkatesan (SYNTHETIC), 52 F |
| 9 Outside reports | the demo documents of that patient are on disk | PASS | 8 PDFs: p19-r01-v1.pdf, p19-r02-v1.pdf, p19-r03-v1.pdf, p19-r04-v1.pdf, p19-r05-v1.pdf, p19-r06-v1.pdf, p19-r07-v1.pdf, p19-r08-v1.pdf |
| 9 Outside reports | a second fresh Case File for that patient | PASS | E2E-20261018-135112-B: HTTP 200 |
| 9 Outside reports | the PDFs are uploaded as outside reports (POST documents) | PASS | 8 file(s), warnings [] |
| 9 Outside reports | the reading job finishes | PASS | finished in 8.0 s |
| 9 Outside reports | every document is read and filed with a type | PASS | p19-r01-v1.pdf: clinical_note (ready); p19-r02-v1.pdf: mammogram (ready); p19-r03-v1.pdf: ultrasound (ready); p19-r04-v1.pdf: histopathology (ready); p19-r05-v1.pdf: ihc (ready); p19-r06-v1.pdf: lab (ready); p19-r07-v1.pdf: lab (ready); p19-r08-v1.pdf: lab (ready) |
| 9 Outside reports | they are labelled outside reports | PASS | 8 of 8 labelled outside |
| 9 Outside reports | the Pre-Authorization gate ran on them | PASS | 3 of 4 records met |

How to look at it: sign in at http://127.0.0.1:7000/tb-nik as tb-breast-doc (the Case File), tb-mdt (the meeting), tb-path-head (the request and the card); the HIMS at http://127.0.0.1:7130/his (search the UHID).

## Bugs found and fixed

Found by running the scenario on the live services (18 Oct 2026); each fix has a unit test (tumour_board/tests/test_e2e_fixes.py, his_mock/tests/test_e2e_fixes.py).

| # | Where | Bug | Fix |
|---|---|---|---|
| 1 | tumour_board/board.py, ready_hook.py, meetings.py | Two board sessions left "in session" since 14 Oct held the ready hook (summary and briefs) and the half-hourly re-fetch back for ever: the summary never came after Mark ready. | board.running_now(): a session counts as running only within 12 hours of its start (or on its own date when it has no start time); the ready hook and the scheduler use it. |
| 2 | tumour_board/slots.py | A record of values only (Receptor status ER / PR / HER2, grade, Ki-67) showed "found" while its values were missing: the gate's source document was the HPE report that only says "IHC to follow". "Ask Pathology" then left the line "found". | Such a record is as complete as its values: not found or waiting (with the gate's problems as the note) until they are in the file; the line is not counted twice in "left before the board". |
| 3 | tumour_board/slots.py | A board question typed by the treating doctor never showed when a note carried a "clinical question": the note's line won, and a found line offered no way to type it. | The board question is the doctor's own: a typed one stands ("entered by Dr X, no report") with the note's line kept beside it (report_value); a found line offers "Type the question". Other values keep the report first. |
| 4 | tumour_board/meetings.py | The agenda rows and the room's summary slide never showed the typed board question: typed_values (a dict) was read as a list. | Read the dict (the old list shape still works), then the verified value the gate rests on. |
| 5 | his_mock/documents.py | The OPD note PDF printed the plan under "Clinical question / Plan" even with no question recorded, so the reader took the plan for the question for the board. | The heading is "Plan" when no clinical question is recorded. |
| 6 | tumour_board/helpers.py | Right after Mark ready the five heads' briefs showed "none" although the ready hook had them queued. | Briefs the ready hook still has to write show "preparing" (queued, or running for the current head). |
| 7 | tumour_board/pacs.py, meetings.py | Images opened on the shared screen: an admitted member whose department has no scope on the Case File (Radiology here) got 403 from the viewer, although the meeting granted it. | A grant made by the meeting carries its id; the viewer stays open to the meeting's admitted members while it runs (Case File on its agenda) and closes when the meeting ends. |
| 8 | routes/tumour_board_routes.py, meetings.py | A record shown on the shared screen gave 403 to such a member (the room screen and remote members follow the shared screen). | The record file on the shared screen of a running meeting is readable by its admitted members, that record only (not its data, not the Case File); an outside expert only with consent. |
| 9 | tumour_board/store.py, ready_hook.py | Deleting a Case File while its ready hook was still writing briefs re-created its directory (an orphan state.json and audit.jsonl, not listed): a later Case File with the same id (TB-0nn ids are reused) would have inherited another patient's briefs and audit. | Writes to a Case File deleted by this process are dropped until a Case File is created there again (store.gone); the ready hook stops when its Case File is gone. |

Not changed (by design or outside this brief): the mammogram of a new patient uses a synthetic image when every fitting public series is already assigned (one source patient never serves two HIMS patients); patients registered by earlier runs stay in the demo HIMS until its next rebuild (no delete in the HIMS); a held meeting stays in the history (only a planned meeting can be cancelled); the two stale sessions of 14 Oct are left for the coordinator to close.
