# his_mock: the mock Indian hospital (SYNTHETIC)

A separate app standing in for a hospital's HIS, LIS, RIS and PACS in the Vaidyx-TB V2 demo and tests. Vaidyx-TB never imports
it; it reads the mock only through `tumour_board/his_client.py`. Data lives in `data/his_mock/` (gitignored, rebuilt from a seed).
Everything here is synthetic: fake IDs (`VXH/…`, `IP/…`, `OP/…`, `VXREG-…`), the fictitious "Vaidyx Demo CA", every patient
marked SYNTHETIC.

## scenarios.json (plan item V2-0.3)

The list of every V2 scenario the mock must generate and the outcome Vaidyx-TB must show for each. Built for item 1.1
(generator) and the e2e of Phases 3 to 6.

| Key | What it holds |
|---|---|
| `hospital` | Settings the scenarios assume: NCG level **optimal** (Essential and Optimal records required; set per mock Case File as `hospital_level`, the V1 hospital default stays essential), PM-JAY empanelled, the surgical oncology list, the four board heads |
| `identifier_patterns` | Regex and example for every synthetic identifier (UHID, temporary UHID, IP / OP No., accession, block No., barcode, ABHA, PM-JAY ID, Reg. No., CA, masked Aadhaar) |
| `document_types`, `tests` | Vaidyx-TB document types, and each orderable test with its document type and producing department (`any_treating` = clinical records) |
| `departments` | The 22 treating and 8 supporting departments of plan section 4, with code (accession prefix), the tests they produce, consultants |
| `patients` | 18 patients (P01 to P18) across the five protocols, with encounters (OP visits, IP admissions), records and Case Files |
| `scenarios` | 29 scenarios: the 11 of the plan 1.1 table (`plan_1_1: true`) and 18 that cover the orchestration checklist |
| `checklist` | The orchestration.md "V2 scenario checklist" as tags, grouped |

**A record** carries `test`, `type`, `producing_department`, `encounter` (OP or IP No.; `registration` when filed under a
temporary or duplicate UHID), `order_status` (never_ordered, ordered, scheduled, sample_collected, completed, cancelled),
`report_status` (none, preliminary, final, amended, cancelled), `signed` with its `signature` (signer, Reg. No., time, demo CA,
serial, the printed block), `accession`, `values` as printed (Indian units) and `serves` (protocol: requirement ids it is meant
to satisfy). Special fields: `versions` (amended reports, oldest first), `omitted_values` (a value the signed report leaves out),
`observation_values` (the HIS Observation disagrees with the PDF), `source: outside_upload` (not in the HIS; the doctor uploads it).
A `never_ordered` record is a placeholder: the generator must **not** create it.

**A Case File** (`patients[].case_files`) names protocol, NCG setting, owner and its `first_fetch` gate: the gaps (requirement,
level 1 / 2, reason, department, accession No. or null) Vaidyx-TB must show right after the first HIS fetch.

**A scenario** has `patients`, `setup` (what the mock holds), `expected` (in Vaidyx-TB terms: `text`, `gate`, `requests` with
or without accession No., `labels`, `flags`, `steps`, `board`, `never`), `phase` (the phase whose e2e asserts it), `also_phases`,
`checklist` tags and, where a decision is still open, `open_questions`.

## How to use it

```python
from his_mock import scenarios
data = scenarios.load()
assert scenarios.validate(data) == []          # ids, patterns, dates, departments, coverage, no Aadhaar
for s in data["scenarios"]:
    pts = scenarios.patients_for(s, data)       # 1.1 builds these; e2e asserts s["expected"]
```

- **1.1 generator:** build every patient's registrations, encounters and records exactly as listed (statuses, signatures,
  accession Nos., values), skipping `never_ordered` and `outside_upload` records (the outside ones become upload files for 3.6).
- **e2e (3.2 onward):** for each scenario of its phase, create the Case File from the UHID (or the IP / OP No. given), then
  assert `expected`.

Tests: `/data/vaidyx/venv/app/bin/python -m pytest his_mock/tests -q`. They also cross-check every first-fetch gate against
`tumour_board/protocols/*.json` (read as files, never imported), so a protocol change that moves a gap shows up here. That
cross-check is a simplified model of `rules.py` (tiers, NCG setting, hospital level, `applies_if`, facts-only records); it does not
reproduce region keywords or document-type disputes. The Phase 3 and 4 e2e is the real check.

Signatures: one certificate serial per signer (the DSC belongs to the person); `document_hash` is filled by 1.2 from the rendered PDF
and `verification_status` is `verified` unless a scenario says otherwise.

## The hospital store (plan item V2-1.1)

`python -m his_mock.build [--out DIR] [--seed N]` (app venv) replays every fixture patient through the lifecycle
transitions of `model.Store` (register, OP visit, admission, ward transfer, referral, order, schedule, sample, preliminary,
final signed, amendment, cancellation) in time order and writes `data/his_mock/` (gitignored):

| File | What |
|---|---|
| `store.json` | Tables keyed by deterministic ids (`vxh-26-004201`, `op-26-118701`, `rad-26-00981`): departments, practitioners, tests, patients (one per registration; a temporary or duplicate UHID is a separate, unlinked patient), encounters, orders, specimens, reports (every version kept), signatures, imaging studies; `hospital` settings (NCG level optimal, PM-JAY empanelled, fetch window) and `meta` (seed, fixture version, counters) |
| `events.jsonl` | One HL7 v2-style event per state change (ADT A28 / A04 / A01 / A02 / A03, REF I12 / I13, ORM O01, ORU R01 with OBR-25 O / S / I / P / F / C / X), the source of `meta.lastUpdated` (1.4 renders them) |
| `fixture_index.json` | Fixture slot (`P03`, `P03-R07`) to store id, plus the never-ordered and outside-report records the store must not hold |
| `documents/`, `dicom/` | Report PDFs (1.2) and synthetic DICOM (1.7) |
| `token` | The API token for 1.3 (mode 600, kept on rebuild) |

`model.py` is pure stdlib and never imports `tumour_board`. Allocation of new UHIDs, OP / IP Nos., accession Nos. and barcodes
starts above the fixture numbers, so the reporting desk (1.5) and the HIS screens (1.6) never collide with them. Store ids
are the identifier slugs; `Store.patient_by_identifier()` resolves a UHID, IP / OP No., ABHA number or address, and
`Store.similar_registrations()` lists the other registrations with the same name, sex and age (a person links them; nothing
is merged). The hospital's `today` is 13/10/2026; P12 has an OPD note from 14/07/2025, older than the 12-month window.

## Report documents (plan item V2-1.2)

`generator.build()` renders every version of every report to `documents/<report id>-v<n>.pdf` (`documents.render_all`, one
subprocess of the pdf venv running `render_cli.py` with WeasyPrint 69; byte-for-byte reproducible) and fills
`versions[].document {path, sha256}` and `signatures[].document_hash`. `documents.html_for(store, report, version)` builds
the page from the store only: hospital and department, a title that names one document type, an identity grid (patient, UHID,
Age / Sex, IP No. or OP No., ABHA No., Accession No. or Lab No., Sample ID, Block No., Ordered / Collected / Reported on in
DD/MM/YYYY HH:MM, Ref. by, Unit), the body in the layout of its type (NABL-style lab table with Biological reference interval;
radiology Technique / Findings / Impression; HPE Specimen / Block No. / Gross / Microscopy / Diagnosis; IHC and molecular
tables; cytology; endoscopy; OPD note; referral; discharge summary with ward / bed movements and referrals) and a footer that
starts with `Report status: FINAL | PRELIMINARY | AMENDED | CANCELLED`, then the signature block verbatim (signed), "Reported
by: Dr X (preliminary, verification awaited)" (preliminary) or "Signature pending" (final, never signed). Every value of
`values` is printed as given; `omitted_values` and `observation_values` never are. Every page carries the watermark
"SYNTHETIC - DEMO ONLY" and a SYNTHETIC footer.

- **Tamper scenario** (`signature_fails_verification`, P03-R10, the discharge summary of IP/26/01872): its signature has
  `verification_status: failed`; the store keeps the PDF untouched and records as `document_hash` the sha256 of the PDF with its
  last byte flipped, so a verifier sees the mismatch. Every other signed version's `document_hash` equals its PDF's sha256.
  `scenarios.json` keeps `document_hash: null` (the store is the source of truth for hashes).
- **Outside reports** (P06-R06, P17-R10): `documents/outside/<record id>.pdf` with the outside laboratory's name, the printed
  identifiers (the masked Aadhaar "XXXX XXXX 1234" exactly as given), printed status and signature lines, no demo CA; the
  scanned one also gets `<record id>-scan.png` (slight rotation, paper tone, noise) for the OCR path (3.6).
- **Reporting desk (1.5):** `documents.render_versions(store, files, [(report, version)])` renders only those versions with
  the same naming and hash bookkeeping (well under a second for one).
- **Check:** `python -m his_mock.documents --check [--data DIR]` (app venv, pypdf) lists missing PDFs, values not in the text
  layer, printed omitted values, signed versions without the block, hash mismatches, and any "Sahyadri", `SYN-`, em dash or
  Aadhaar-like number; `--render` re-renders into an existing store.

## The event feed (plan item V2-1.4)

`his_mock/hl7.py` renders every store event as one HL7 v2.5-style message (segments split by `\r`, pipe-delimited) and
`generator.build()` writes them to `data/his_mock/events.hl7` in event order, each followed by a blank line (`\r\n\r\n`).
MSH names `VXHIS` / `VXDEMO`, the event time (`YYYYMMDDHHMMSS+0530`) and the event id as control id.

| Event | Message | Segments |
|---|---|---|
| Registration, OP visit, admission, ward transfer, discharge | `ADT^A28` / `A04` / `A01` / `A02` / `A03` | MSH, EVN, PID, PV1 |
| Referral requested / accepted | `REF^I12` / `I13` | MSH, RF1 (status P / A, from^to department, reason), PRD RP / RT, PID, PV1 |
| Order placed, scheduled, sample collected, cancelled | `ORM^O01` | MSH, PID, PV1, ORC (NW / SC / CA, ORC-5 IP / SC / CA), OBR (OBR-25 O / S / I / X) |
| Preliminary, final signed, amended, cancelled report | `ORU^R01` | MSH, PID, PV1, ORC, OBR (OBR-22 reported, OBR-25 P / F / C / X, OBR-32 signer), one OBX per printed value (OBX-11 P / F / C), NTE with the signature block and the amendment note |

PID-3 holds the UHID (`VXH`, MR), the ABHA number (NH) and the PM-JAY ID when present; never an Aadhaar number. The name is
`SURNAME^GIVEN` with "(SYNTHETIC)" kept. `hl7.append()` adds one message after a transition (the reporting desk, 1.5),
`hl7.read_feed()` / `hl7.parse()` read it back. Deltas: `hl7.changed_since(store, since)` returns the reports whose
`meta.lastUpdated` is after the watermark, `hl7.events_since()` the events behind them (plus ADT / REF / ORM changes) and
`hl7.last_event_time()` the next watermark; the FHIR `_lastUpdated` search (1.3) gives the same reports.

