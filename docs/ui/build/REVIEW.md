# Review guide: demo HIMS, demo PACS and the new Vaidyx-TB website

Built 17 to 18 Oct 2026 on branch `the-ui`, all commits local as Nikhil-Rao20, nothing pushed. Everything runs on this server, localhost only, synthetic patients only (the PACS images are public research scans relabelled with our fake IDs).

## 1. Open everything

Use VS Code port forwarding for ports 7000, 7130 and 7880 (and 8042 only if you want Orthanc itself).

| System | Address | Sign in with |
|---|---|---|
| New Vaidyx-TB website | http://127.0.0.1:7000/tb-nik | the demo logins in `~/vaidyx/.tb_v2_demo_logins` (username, then password; tab separated) |
| Old website (unchanged) | http://127.0.0.1:7000/tb | the same logins |
| Demo HIMS ("Vaidyx Demo Hospital") | http://127.0.0.1:7130/his | `data/his_mock/logins.tsv` (email, role, password) |
| Images (OHIF viewer) | opens from a Radiology order in the HIMS, or "Open images" in a Case File, or from the meeting room screen | the same sign-in as the page you came from |

Demo roles on the website:

| Login | Role | Good for checking |
|---|---|---|
| tb-breast-doc | Breast Surgery consultant (treating) | home list, new Case File, the Case File page, sign-off requests from residents |
| tb-medonc-doc, tb-gynonc-doc, tb-crs-doc, tb-pulmo-doc | other treating consultants | the same, other departments |
| tb-mdt | MDT Coordinator | meetings: agenda, room screen, live decision, member cards |
| tb-rad-doc, tb-micro-doc | supporting doctors | request cards (only what they were asked) |
| tb-path-head | Pathology head | requests, board head card at the end of a case |
| tb-breast-admin, tb-rad-admin, tb-path-admin | department admins | People: add a resident, reset a password (mail draft) |
| tb-root | root admin | Admin: the five-step hospital set-up |

Every demo login shows the first-login set-up (Welcome) once: that is the intended flow (name, photo, theme, text size, start page).

HIMS roles: reception, opd.doctor (Breast Surgery consultant, also ward), ward.doctor, lab.tech, lab.doctor (signs lab), rad.tech, radiologist (signs radiology), pathologist, admin.

Start, stop or check all services: `scripts/demo_services.sh status|start|stop|restart [app|his|pacs|video]`. Models are separate (`tumour_board/serve_models.sh`).

## 2. What to check, in order (about 45 minutes)

1. **The patient in the hospital system.** Sign in to the HIMS as reception, register a patient (name must end with "(SYNTHETIC)"). As opd.doctor: OP visit, OPD note, order a mammogram, a core biopsy, CBC, LFT. As lab.tech then lab.doctor: collect, enter results, sign. As rad.tech then radiologist: schedule, report, sign; click "Open images". As pathologist: receive the specimen, HPE, sign. Leave IHC pending.
2. **The Case File.** On the website as tb-breast-doc: "+ New Case File", type the UHID, pick Breast cancer, setting, urgency. Watch the records arrive. The Case File page is the fill-in summary: each line has its source quote (click it to see the page with the quote highlighted) or a blank with its button right there ("Ask Pathology", "Not needed", "Enter a value").
3. **Resident sign-off.** Make a join code (Team), sign in as a resident (create one as tb-breast-admin under People; the login comes as a mail draft), join with the code, ask the consultant to sign off a "Not needed". Back as tb-breast-doc, approve it from the strip on top.
4. **The loop.** In the HIMS sign the IHC as pathologist. In the Case File click Re-fetch: the line fills in and the request to Pathology closes by itself.
5. **Ask and helpers.** Ask a question in "Ask this Case File" (answers quote the reports; the chat is shared with the team). Open Specialty helpers and pick one.
6. **Ready.** Type the board question, Mark ready. The summary text and the five briefs are prepared in the background (labelled "AI draft, not reviewed").
7. **The meeting.** As tb-mdt: Meetings, New meeting (video on), add the Case File to For discussion, Send agenda, copy the code. Open the room screen (`/tb-nik/meetings/<id>/room`) in one browser and the member view in another as tb-path-head (join with the code, admit from the control view). Show the case, open the images on the shared screen, type a question as a member, type the decision (it appears live at the bottom of the room screen), save after read-back, end the case (the heads get their card).
8. **Phone.** Open any page at phone width: the Dock at the bottom is the menu.

The same story runs automatically: `/data/vaidyx/venv/app/bin/python -m tumour_board.eval.e2e_nik` (97 checks, last run all passed; results in `docs/ui/build/E2E_RESULT.md`). Its Case Files (E2E-...) and meeting stay on the server for you to open.

## 3. What was built (short)

(filled in at the end of the run)

## 4. Decisions I took where answers collided

(filled in at the end of the run)

## 5. Known gaps and things for you to decide

(filled in at the end of the run)
