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

| Part | What you get | Checked by |
|---|---|---|
| Demo HIMS (his_mock, :7130) | "Vaidyx Demo Hospital": its own sign-in (9 roles, lock-out after 5 wrong tries), classic blue-grey screens, modules Registration, OPD (notes, order entry, referral), IPD (admit, transfer, discharge summary), Laboratory (worklist, sample barcode, result templates in Indian units, verify and sign), Radiology (schedule, report, sign, open images), Pathology (block No., HPE, IHC, molecular, add-on orders), Exchange (HL7 v2 messages, FHIR), Admin. Every signed report is a PDF with the demo signature block, and goes out over FHIR R4 the same way as before. | 416 tests, conformance check, a browser walk of 80 pages |
| Demo PACS (Orthanc + OHIF, :8042) | 27 of 43 studies are real-looking public scans (19 open-licence collections from The Cancer Imaging Archive, relabelled with our fake IDs, faces cropped in 9 series, credits page at /his/about/images); 16 stay synthetic where no public scan fits | relabel tests, QIDO check of every study, viewer opened through the HIMS and through Vaidyx |
| Vaidyx backend (/api/tb) | residents and Case File teams with join codes, urgency set by the consultant, "ask Dr X to sign off" for residents, fill-in summary lines from verified quotes, shared Ask chat, six specialty helpers, published cases, guided hospital set-up, email logins with a mailed first password and a forced change, meetings with a live room channel, LiveKit video tokens, browser push, a scheduler (re-fetch every 30 minutes, automatic reminders, digests), a checklist for Cancer of Unknown Primary (draft) and "four core records" for cancers with no checklist | 2,551 tests; the end-to-end scenario (97 checks) |
| New website (/tb-nik) | sign-in, first-login set-up, home list (newest first, filters, urgency), New Case File, the Case File page as a fill-in summary with sources, side panels, helpers, team, board form and published cases; requests for supporting doctors; meetings (agenda, coordinator control, room screen, member view, join by code); settings, activity, admin set-up, people; light and dark; Dock menu on phones | type check and build; Playwright journeys for 6 roles at 1366, 1920 and 390 wide (screenshots in docs/ui/build/shots, index in INDEX.md, kept out of git); accessibility check with no serious issues |
| Security | live audit script (31 checks) and a code review with 23 findings, all fixed except one for you (see SECURITY_REVIEW.md) | `python -m tumour_board.eval.security_audit` |

Everything is in 37 local commits on `the-ui` after 9c28ad6, all authored Nikhil-Rao20. The briefs each part was built from are in docs/ui/build/briefs/, so any part can be rebuilt or extended.

## 4. Decisions I took where answers collided (real hospital practice first)

| Topic | Decision |
|---|---|
| Summary timing | Lines from verified quotes are live from the first fetch; AI-written text and the five head briefs come at Mark ready (your check answer) |
| Ownerless Case Files | Only the coordinator and the creator see them (your 16 Oct rule: every Case File has an owner). Side effect: the old demo Case Files TB-001 to TB-003 are no longer open to every doctor |
| The real patient's Case File | Visible only to the login that created it (and a Vaidyx admin inside a break-glass window). Found during the UI review and fixed the same hour |
| Vaidyx admin | No clinical or meeting rights; reads a Case File only inside a break-glass window with a reason, read only, the owner is told |
| Outside experts | Slides of the current case only, while the meeting runs; name, UHID and dates withheld without the owner's consent tick |
| Request drafts | No "Level 1 / Level 2" wording for departments |
| Meetings left open | A meeting counts as running only for 12 hours after it starts, so a forgotten meeting never blocks summaries or the scheduler |
| Idle sessions | The Tumour Board pages sign out after 8 hours without use |
| HIMS data API | Needs a login (with the screen's role rules) or the integration token; a separate write token for scripts |
| Departments | Vaidyx: 23 treating and 6 supporting as you listed; the demo HIMS keeps its 30 hospital departments (a hospital has them) |
| Published cases | Only verbatim quotes the doctor adds are shown (no abstract snippets), labelled "Published case, not advice for this patient" |

## 5. Known gaps and things for you to decide

For you to decide:
1. Old data files committed before this work (data/uploads/*, data/scheduled_emails.db, data/user_prefs.json, data/note_pings_nikhil.json, data/vaidyx-tmux/*): untrack them? They stay in the history either way.
2. The admin password in ~/vaidyx/.vaidyx_admin_login no longer signs in as admin. I did not look further; the old gate scripts that use it will fail until it is fixed.
3. A person should look once at the face-check sheets of the cropped scans (/data/vaidyx/tb_resources/dicom_public/qa/<series>/sheet.png) before doctors see the demo.
4. The CUP checklist and the "four core records" rule are drafts: a named doctor must approve them before real use.

Known gaps:
- "Sign and lock" of the decision record has no backend yet; the after-the-board screens stay parked as you decided.
- Text only: no voice anywhere (as decided). The stand-in agent answers typed questions.
- All HIMS lung patients are men while most public lung scans are from women; 16 studies stay synthetic (ultrasound, bone scan, brain and oral cavity MRI, and a few mammograms and chest X-rays for women).
- Starting a meeting can prepare stand-in briefs at the same time as the ready step: extra GPU work, no harm.
- Two old meetings from 14 to 16 Oct are still marked in session; close them as the coordinator. The E2E patients stay in the HIMS until its next rebuild.
- The old /tb interface is unchanged, but the new access rules apply to it too (admin, ownerless Case Files). Its old gate script (tumour_board/eval/e2e_api.py) was not rerun and will need updating for those rules.
- Before sharing the website beyond this server: the list at the end of SECURITY_REVIEW.md (TLS and secure cookies, allowed-origin list, account lock-out and two-step sign-in for admins, Orthanc authentication, configurable LiveKit and PACS addresses, its own hostname for the HIMS).
