# his_mock: DemoHIMS, the hospital system of the Vaidyx Demo Hospital (SYNTHETIC)

A separate app that stands in for an Indian hospital's HIMS (registration, OPD, IPD), LIS, RIS, pathology system and the
link to the PACS, in the look of the government systems many doctors know (e-Hospital, e-Sushrut). It is named "Vaidyx
Demo Hospital", product label "DemoHIMS", and runs on 127.0.0.1:7130 only (never tunnelled). Vaidyx-TB never imports it:
it reads the hospital only through the FHIR API with the bearer token (`tumour_board/his_client.py`), exactly as it would
read a real HIS. Data lives in `data/his_mock/` (gitignored, rebuilt from a seed).

**Everything is synthetic.** Every patient name ends in "(SYNTHETIC)"; identifiers are invented (`VXH/26/...` UHIDs,
`VXH/T/26/...` temporary UHIDs, `OP/26/...`, `IP/26/...`, accessions `RAD/26/...`, sample barcodes `VXS...`, block Nos.
`PATH/26/00412-A1`, ABHA sandbox numbers and `@sbx` addresses, `PMJAY-VX-...`, council numbers `VXREG-...`); signatures
come from the fictitious "Vaidyx Demo CA"; every page carries the yellow SYNTHETIC DATA ribbon and every PDF the
watermark "SYNTHETIC - DEMO ONLY". No Aadhaar number is ever asked for or shown. The PACS holds synthetic test patterns
(and, when loaded, public research images relabelled with these fake IDs, credited in the PACS); no model ever reads them.

## Run it

```bash
/data/vaidyx/venv/app/bin/python -m his_mock.build --upload   # rebuild data/his_mock from the fixtures, PDFs, HL7, DICOM,
                                                              # upload the studies to Orthanc (127.0.0.1:8042), logins
his_mock/serve.sh restart                                     # uvicorn on 127.0.0.1:7130 (start | stop | status | restart)
curl -s http://127.0.0.1:7130/health                          # public JSON: {"ok": true, "patients": ..., "accounts": 9}
```

Then open http://127.0.0.1:7130/his and sign in. Orthanc: `his_mock/orthanc.sh start | stop | status | load`. Log:
`~/vaidyx/logs/his_mock.log`. A rebuild replaces the store (every change made on the screens is gone) but keeps the token,
the accounts and their passwords, the sessions and the audit files.

## Logins and roles

The build (and `python -m his_mock.auth`) creates 9 synthetic staff accounts in `data/his_mock/accounts.json` (bcrypt
hashes). Their passwords (12 random characters) are written once to **`data/his_mock/logins.tsv`** (email, role,
password; mode 600) and never printed or logged. `python -m his_mock.auth --reset` gives every account a new password
(the file is rewritten, every session ends). A password reset in the Admin module is shown once on the screen; the file
then says that the account was reset.

| Email (`@vaidyx-demo.invalid`) | Role | Signs as | What the role does |
|---|---|---|---|
| `reception` | Registration desk | cannot sign | registers (permanent or temporary UHID), opens OP visits, admits, transfers |
| `opd.doctor` | OPD consultant, also ward work | Dr Kavitha Raghunathan, Breast Surgery | OP visits, OPD note, order entry, referral, admission, transfer, discharge summary, discharge |
| `ward.doctor` | Ward doctor | the same Breast Surgery consultant | the ward round: orders, transfer, discharge summary, discharge |
| `lab.tech` | Laboratory technician | cannot sign | collects samples, enters results, receives pathology specimens, cancels |
| `lab.doctor` | Laboratory consultant | Dr Anil Saxena, Biochemistry | collects samples, enters results, verifies and signs, amends, cancels |
| `rad.tech` | Radiology technician | cannot sign | schedules studies, saves preliminary reports, cancels |
| `radiologist` | Radiologist | Dr Sanjay Joshi, Radiology | everything of the technician plus sign and addendum |
| `pathologist` | Pathologist | Dr Revathi Krishnan, Pathology | specimen receipt, HPE / IHC / molecular / cytology entry, sign, add-on orders, addendum |
| `admin` | Hospital IT admin | cannot sign | the Admin module only (departments, practitioners, accounts, audit) |

A signature carries the practitioner's Reg. No. and the demo CA serial. A consultant writes and signs only the notes and
reports of their own department (the Breast Surgery consultant cannot sign an ENT discharge summary or a Pulmonology
bronchoscopy report; the page says so). Every signed-in user may look at every module; each action is checked against
the role and a refusal is a plain page: "Your role cannot do this: only the Radiologist can sign a radiology report."

**Security.** Session cookie `vxhis_session` (HttpOnly, SameSite=Lax, 12 hours; sessions survive a restart in
`sessions.json`). Five wrong passwords lock an account for 15 minutes, said plainly on the login page; more than 30 failed
sign-ins from one address in 15 minutes pause sign-ins from it. Every form carries a per-session CSRF token, next to the
same-origin check on every POST. Pages are `no-store`, framed only by the same origin, `nosniff`. Every login, logout and
screen action is a line of `his_audit.jsonl`; every reporting action also of `desk_audit.jsonl`; neither ever holds a
password or the token. What stays without a login: `GET /` and `/health` (JSON), `/fhir` (its own bearer token;
`/fhir/metadata` open), `/documents/...` (bearer token, the path Vaidyx-TB uses), the JSON APIs `/his/api/...` and
`/desk/api/...` (localhost only, used by the tests, the e2e and `tumour_board/eval/demo_v2.py`). `/view/reports/...`
takes the login cookie or the bearer token.

## The screens

Classic look (`ui.py`): dark blue header band with the hospital name, the DemoHIMS label, the signed-in user and role and
Logout; a grey module bar with the active module underlined; a yellow patient banner on every patient page (Name, UHID,
Age / Sex, IP / OP No., Ward / Bed, Consultant); dense bordered tables with alternating rows; 13 px Verdana / Arial;
grey buttons (hover, pressed, disabled and "working" states; a form is sent once), blue links, small status pills;
validation errors next to the field with what was typed kept; an empty-state line in every list. No teal: it is clearly
not Vaidyx. Readable at 1024 px; tables scroll inside their box on a phone.

| Module | Path | What it holds |
|---|---|---|
| Registration | `/his` | search by UHID (permanent or temporary), IP / OP No., ABHA number or address, accession / Lab No. (an exact hit opens the patient) or name; recent registrations; new registration (Indian address fields, PIN, mobile, ABHA optional and permanent only, PM-JAY ID optional, permanent or temporary; a possible duplicate is shown first, "Register anyway"); patient page with demographics, similar registrations (linked in Vaidyx-TB, never merged here) and the timeline of OP visits and admissions with their orders and PDFs |
| OPD | `/his/opd` | today's OPD list by date, department and unit; recent visits; the clinical and procedure reports still to write. The visit page (`/his/encounters/{id}`) holds the OPD consultation note (an `opd_note` record signed at once: PDF, HL7 ORU, FHIR DocumentReference), **order entry** (tick tests grouped by performing department, supporting departments first, consultations included; one order and accession each through `model.place_order`), referral and accept referral |
| IPD | `/his/ipd` | ward census with the PM-JAY Pre-Authorization line, recent discharges. Admit is on the patient page; transfer, the discharge summary form (diagnosis, course, advice; signed once) and discharge on the admission page, which also has order entry |
| Laboratory | `/his/lab` | work list tabs Ordered / Sample collected / Results entered / Verified, by laboratory (Pathology CBC, Biochemistry LFT / RFT / CEA, Microbiology viral markers); collect sample (barcode allocated, printable label); result entry per test template (`templates.py`: value keys, Indian units, reference intervals, sex-specific haemoglobin; numbers checked, choices from a list); verify and sign by the laboratory consultant only; amendment with a note; cancel with a reason; PDF links |
| Radiology | `/his/radiology` | work list tabs Ordered / Scheduled / Reported (preliminary) / Signed (Radiology and Nuclear Medicine); schedule with date, time and room (registers the ImagingStudy and its Study UID under the accession; a study booked for a later day takes no report yet); report entry Technique / Comparison / Findings / Impression saved as preliminary; sign by the radiologist; addendum; cancel; **Open images** once the study has images |
| Pathology | `/his/pathology` | work list tabs Ordered / Specimen received / Entered / Signed; specimen receipt with block No. (an add-on offers the block already received); HPE entry (specimen, gross, microscopy, type, grade, diagnosis); IHC panels per template (ER, PR, HER2, Ki-67; PD-L1) or as `marker: result` lines; molecular; cytology; preliminary or sign; add-on IHC / molecular orders by the pathologist on the same encounter; addendum |
| Exchange | `/his/exchange` | the HL7 v2 viewer (last 200 messages of `events.hl7`, newest first, filter by patient and type, raw text per message at `/his/exchange/hl7/{control id}`), the FHIR R4 base and example searches, the events log, whether the token file exists (never its value) |
| Admin | `/his/admin` | departments (30), practitioners with an add form, the 9 accounts with a password reset shown once, the audit of `his_audit.jsonl` and `desk_audit.jsonl` |

The old reporting desk links still work: `/desk` lists the supporting departments with their counts and links into the
modules; `/desk/{code}`, `/desk/{code}/orders/{id}` and `/desk/{code}/reports/{id}` open the module page.

Every action runs one `model.Store` transition under the hospital lock. Report actions go through the reporting engine
(`desk.run_action`): render the new version's PDF, build the synthetic DICOM of an imaging order that is now reported and
upload it when Orthanc answers (a PACS that is down never fails a sign: an amber message says "images not uploaded"),
append the HL7 message, save, audit. Results a technician enters are recorded under the performing department's first
consultant until the laboratory consultant verifies and signs (the audit names the technician).

## The PACS viewer through the HIMS

`GET / HEAD /api/tb/pacs/{path}` (`pacs_proxy.py`, login required) streams to Orthanc at 127.0.0.1:8042, for
`ohif/...` (the viewer) and `dicom-web/...` (QIDO / WADO-RS) only; Orthanc's REST API, the explorer, plugins and odd paths
are refused with a plain message; writes get 405. The path looks like the Vaidyx one on purpose: the OHIF plugin is built
with `RouterBasename /api/tb/pacs/ohif/` and the DICOMweb `PublicRoot /api/tb/pacs/dicom-web/` because the Vaidyx app
proxies the viewer under that prefix, so any second host must serve the same prefix. "Open images" therefore links
`/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=<study uid>`, which opens OHIF on :7130 as on :7000. Orthanc answers HEAD
with 404, so a HEAD is sent upstream as a GET and only its headers are returned. `TB_HIS_MOCK_ORTHANC` overrides the URL.

## Data and build

`python -m his_mock.build [--out DIR] [--seed N] [--no-pdf] [--no-hl7] [--no-dicom] [--upload]` replays every fixture of
`scenarios.json` (v0.3.5: 19 patients, 21 registrations, 31 scenarios; 30 departments, 22 treating and 8 supporting;
38 tests; 22 practitioners) through the transitions of `model.Store` in time order, deterministic per seed, and writes:

| File | What |
|---|---|
| `store.json` | departments, practitioners, tests, patients (one per registration), encounters, orders, specimens, reports (every version), signatures, imaging studies, `hospital` settings, `meta` (seed, counters) |
| `events.jsonl`, `events.hl7` | one event and one HL7 v2.5-style message per change (ADT A28 / A04 / A01 / A02 / A03, REF I12 / I13, ORM O01, ORU R01) |
| `fixture_index.json` | fixture slot (`P03`, `P03-R07`) to store id |
| `documents/` | one PDF per report version (`documents.py`, WeasyPrint in the pdf venv): NABL-style lab tables, radiology, HPE, IHC, molecular, cytology, OPD note, discharge summary layouts; signature block of the demo CA |
| `dicom/` | synthetic DICOM per performed imaging study (`dicom_studies.py`; `--upload` sends them to Orthanc and verifies them by QIDO) |
| `token` | the FHIR bearer token (mode 600, kept on rebuild) |
| `accounts.json`, `logins.tsv`, `sessions.json`, `his_audit.jsonl`, `desk_audit.jsonl` | logins (kept on rebuild) and the audit |

New UHIDs, visit and admission numbers, accessions and barcodes are allocated above the fixture numbers. The build refuses
to wipe a store without the SYNTHETIC marker and never writes under `data/tumour_board/`. The fixture hospital's "today"
is 13/10/2026; actions on the screens carry the real time.

## FHIR, HL7 and the JSON APIs (what Vaidyx-TB and the scripts use)

- **FHIR R4** at `/fhir` in NRCeS (ABDM) IG v6.5.0 shapes, bearer token in the `Authorization` header only (a token in the
  query is refused): Patient, Encounter, ServiceRequest, Specimen, DiagnosticReport (versioned, `_history`), Observation,
  DocumentReference (one per version, PDF inside), Provenance (the signature), ImagingStudy (viewer and DICOMweb links),
  Media, Practitioner, Organization; `$document`, `Patient/$everything`, `Patient/$similar`; search by identifier,
  patient, encounter, status, `_lastUpdated` (the delta re-fetch), `_count` / `_offset`. Notes and discharge summaries
  written on the screens appear as DocumentReferences, reports as DiagnosticReports, at once.
- **Conformance:** `python -m his_mock.eval.conformance --data data/his_mock` (or `--url ... --token-file ...`) prints
  `CONFORMANCE OK: <n> resources checked`.
- **HL7 v2** feed in `data/his_mock/events.hl7` (no network endpoint), shown in Exchange; `hl7.py` reads and parses it.
- **JSON:** `/his/api/search`, `/his/api/patients/{id}`, `/his/api/encounters`, POST `/his/api/registrations`,
  `/his/api/patients/{id}/visits | admissions`, `/his/api/encounters/{id}/refer | accept | transfer | discharge | orders`;
  `/desk/api/{code}/pending`, POST `/desk/api/{code}/orders/{id}/schedule | collect | preliminary | sign | cancel`,
  `/desk/api/{code}/reports/{id}/addendum` (409 lifecycle, 400 or 422 bad input, 404 unknown).

## Tests

```bash
/data/vaidyx/venv/app/bin/python -m pytest his_mock/tests -q
/data/vaidyx/venv/app/bin/python -m his_mock.eval.conformance --data data/his_mock
LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib /data/vaidyx/venv/app/bin/python -m his_mock.eval.ui_test \
    --base http://127.0.0.1:7130 --data data/his_mock          # Playwright, 1366 / 1920 / 1024 / 390 px
```

`test_auth.py` (accounts, login file, lock-out, cookie, CSRF, role refusals, /view/reports, reset), `test_modules.py`
(OPD order entry and note, IPD, Laboratory templates and signing, Radiology, Pathology, Exchange, Admin, the classic
shell), `test_screens.py` (registration, timeline, ADT forms, JSON API), `test_desk.py` (reporting engine JSON, desk
aliases), `test_pacs_proxy.py` (allow-list, login, HEAD, Orthanc down), `test_templates.py`, `test_documents.py`,
`test_fhir.py`, `test_conformance.py`, `test_hl7.py`, `test_dicom.py` (Orthanc tests run only when 8042 answers),
`test_model.py`, `test_generator.py`, `test_scenarios.py`, `test_app.py`. Tests build into temporary directories; none
touches `data/his_mock` or the live Orthanc studies they did not add.

**The demo story:** `python -m tumour_board.eval.demo_v2 --fresh` rebuilds this store and runs the V2 story on it; a demo
changes the live store, so rebuild before the scenario check (`python -m tumour_board.eval.his_scenarios`).
