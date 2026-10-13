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
| `hospital` | Settings the scenarios assume: NCG level **optimal** (Essential and Optimal records required), PM-JAY empanelled, the surgical oncology list, the four board heads |
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
`tumour_board/protocols/*.json` (read as files, never imported), so a protocol change that moves a gap shows up here.
