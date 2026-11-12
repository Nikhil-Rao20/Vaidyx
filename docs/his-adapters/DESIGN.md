# HIS adapters: connect by standard, with presets

Status: built on branch `after-healthathon`, not committed. Code: `tumour_board/his_adapters/`. Presets: `tumour_board/protocols/his_presets.json`.
Facts about products: `docs/his-adapters/RESEARCH.md` (not repeated here). All examples below use fake values.

## 1. The problem

Vaidyx-TB read one kind of hospital system: FHIR R4 in ABDM / NRCeS shapes (the demo hospital `his_mock`), plus a thin MCP connector.
Indian hospitals run many products (NIC e-Hospital, C-DAC e-Sushrut, Bahmni / OpenMRS, Insta HMS, KareXpert, MocDoc, Napier, Akhil Miracle,
a few international ones) and many small hospitals have no API at all. One connector per product cannot be built or kept working.

## 2. The decision

Connect by standard. A hospital picks its system from a list (a preset); the preset chooses the connection method (a `kind`) and fills
its defaults. A preset is data only. It never adds support the code does not have.

| Layer | What it is | Where |
|---|---|---|
| Interface | `HISClient`: ping, find_patient, encounters, reports, open_orders, document, referrals, hospital | `tumour_board/his_client.py` (unchanged) |
| Adapters | One subclass of `HISClient` per method, returning the same dict shapes as the FHIR client | `tumour_board/his_adapters/` |
| Registry | `KINDS`, `make(settings)`, `validate(...)`, `describe()`, presets | `tumour_board/his_adapters/registry.py` |
| Presets | Product -> kind + defaults + honest status and notes | `tumour_board/protocols/his_presets.json` |
| API | `GET /api/tb/his/kinds`, `POST /api/tb/setup/his`, `PUT /api/tb/his`, `POST /api/tb/his/test` | `tumour_board/api/setup.py`, `routes/tumour_board_routes.py` |

`his_case.py` and `his_overlay.py` are not changed. `his_client.client()` hands the four new kinds to `registry.make()`; with no
`his.json` the demo FHIR hospital is used exactly as before.

## 3. The adapters

| Kind | Module | Reads | Can do | Cannot do |
|---|---|---|---|---|
| `fhir` | `his_client.FHIRClient` (existing) | FHIR R4 in NRCeS shapes | Everything: versions, Provenance signature, orders, referrals, imaging links | Nothing new. Tested with the demo hospital |
| `fhir_generic` | `fhir_generic.py` | Plain FHIR R4 (HAPI, OpenMRS FHIR2 / Bahmni, Epic / Cerner style) | Patient by identifier (bare value, then `system\|value`), visits, reports, open orders, four sign-in types | No signature check on plain servers. No images on servers without ImagingStudy. The values of an earlier version are not read. No signed JWT sign-in |
| `hl7v2_folder` | `hl7v2.py` | HL7 v2.x files in a folder: ORU^R01, MDM^T02, ORM^O01 | Patient by any PID-3 identifier or visit number, visits from PV1, one report per OBR with versions, PDF from an ED OBX, open orders from ORM | No signature check. No imaging links, referrals or duplicate registration links. No network listener |
| `folder_bridge` | `folder_bridge.py` | A folder of report files with `index.csv` | Patient by UHID or visit number, visits, reports with versions and status | No open orders, no candidate values, no signature check, no imaging links |
| `abdm_bundles` | `abdm_bundle.py` | ABDM document bundles (`.json`) in a folder | Patient by MR number, ABHA number or address, visit, reports and notes, candidate values, PDF from inside the bundle | No open orders. The bundle signature is not verified. No live gateway, no consent flow |
| `mcp` | `his_client.MCPHISClient` (existing) | The MCP connector | Records and files | No visits, orders, status or signature |

### 3.1 fhir_generic: what differs from the NRCeS client

| Situation on the server | What the adapter does |
|---|---|
| FHIR API under a path | `base_path`, for example `/openmrs/ws/fhir2/R4` |
| Search needs `system\|value` | Tries `identifier=<value>`, then `identifier=<system>\|<value>` for each configured system, on Patient and then on Encounter |
| Identifiers are not typed MR | The UHID is the identifier of a configured system, else the official one, else the one that matched |
| No `Patient/$everything` | One search per resource type by patient; a type the server does not have is left out |
| No DocumentReference (OpenMRS FHIR2) | The report is built from the DiagnosticReport: the file in `presentedForm` (inline Base64 or a Binary URL on the same server) |
| No file at all | A "text only" report: its conclusion and Observations, line by line, as a `.txt` |
| No Provenance | Signature unknown (`signature: None`), never "yes" |
| No `_history` | Only the current version. An amended report still becomes a new version on re-fetch and the earlier one stays in the Case File |
| `link[next]` to another server | Refused with a plain error. Sign-in headers go only to the configured server |

Sign-in: bearer token, HTTP basic, API key in a header (name configurable), OAuth2 client credentials (client id and secret sent to the
token endpoint with HTTP basic; the access token is kept in memory until 30 seconds before it expires, asked for again once after an
HTTP 401, never logged, never in a URL or an error).

Not implemented: SMART backend services with a signed JWT (`private_key_jwt`), which Epic and Oracle Health normally ask for. It needs a
key pair, a JWKS the hospital registers, and a signing library; no new dependency was allowed in this work. Until then the
"International HIS" preset works only where the site issues a client secret or a bearer token.

### 3.2 hl7v2_folder: what is read

| Segment | Fields used |
|---|---|
| MSH | MSH-1 / MSH-2 delimiters, MSH-7 time, MSH-9 type, MSH-10 control id |
| PID | PID-3 identifiers with authority and type code (MR, PI, PT = UHID; NH, ABHA = ABHA; PMJAY), PID-5 name, PID-7 date of birth, PID-8 sex |
| PV1 | PV1-2 class (I = IP, O / E = OP), PV1-3 ward and bed, PV1-7 doctor, PV1-10 department, PV1-19 visit number, PV1-44 / 45 |
| ORC / OBR | Placer (OBR-2) and filler (OBR-3) numbers, OBR-4 service, OBR-7 observation time, OBR-22 report time, OBR-24 department, OBR-25 status, OBR-32 reporter |
| OBX | OBX-2 type, OBX-3 code, OBX-5 value, OBX-6 units, OBX-7 range, OBX-8 flag, OBX-11 status |
| TXA (MDM^T02) | TXA-2 type, TXA-12 document number, TXA-17 completion status, TXA-19 availability |
| NTE | Notes; an NTE typed AMD is the amendment note |

| Rule | Behaviour |
|---|---|
| Status | OBR-25: F final, C corrected, P preliminary, X cancelled, A partial; anything else unknown |
| Versions | One report per filler number. The latest message wins; earlier ones stay as earlier versions. The same message sent twice is counted once |
| PDF | An OBX of type ED (`source^type^subtype^encoding^data`, Base64). A PDF split over consecutive ED segments of the same set id or sub-id is joined |
| RP value | A pointer, not the bytes: recorded as "document by reference, not fetched". Never followed |
| No PDF | A "text only" report: the OBX and NTE lines are its text (`.txt`). It carries no candidate values, because a value checked against a text made from itself proves nothing; the normal reading of the text finds the values |
| Tolerated | `\r`, `\n` or `\r\n` segment ends, a UTF-8 BOM, MLLP bytes (0x0B, 0x1C 0x0D) left in a file, several messages in one file, a wrapped Base64 line, escapes `\F\ \S\ \T\ \R\ \E\ \.br\` |
| Never kept | An identifier typed as Aadhaar is dropped when the message is read |

How files reach the folder: Vaidyx-TB has no MLLP listener. The hospital's interface engine (Mirth Connect, Rhapsody, the LIS vendor's
own) adds a file writer destination, or a small relay on the hospital side receives MLLP and writes one file per message. Files are
copied to the folder on the Vaidyx-TB server (SFTP, a shared mount). Vaidyx-TB only reads; it never deletes or moves a file.

### 3.3 folder_bridge: the index file

`index.csv`, UTF-8, first line the column names:

| Column | Required | Notes |
|---|---|---|
| uhid | yes | The hospital number (UHID / MRN / CR No.) |
| patient_name | yes | |
| sex | no | M / F |
| dob or age | no | DD/MM/YYYY or ISO; age in years |
| visit_no, visit_type | no | OP / IP |
| report_id | yes | Rows with the same report_id are versions in date order; the last is current |
| report_type | yes | For example "Histopathology report" |
| report_date | yes | DD/MM/YYYY or ISO |
| status | yes | final, preliminary / provisional, corrected, amended, cancelled; anything else unknown |
| signed_by | no | A name only. The signature stays unknown; the report text decides |
| file | yes | Relative to the folder. PDF, text or image |
| department, accession | no | Optional extras |

A bad row is skipped with a counted reason (shown by the connection test) and never stops the rest.

### 3.4 abdm_bundles

One `.json` file per record: a FHIR Bundle of type `document`, Composition first, NRCeS shapes (guide 6.5.0). Read: DiagnosticReportRecord,
DischargeSummaryRecord, OPConsultRecord, HealthDocumentRecord. Other record types are skipped and counted. The patient comes from the
Patient resource: the hospital's MR number, and the ABHA number or address (the official example types the ABHA number MR under
`https://healthid.ndhm.gov.in`; that is read as an ABHA, not as the hospital number). The file comes from `presentedForm`, a
DocumentReference attachment or a Binary inside the bundle. "ABDM compliant" products push these bundles through the gateway after patient
consent; they are not a server to query. This adapter reads bundles the hospital hands over as files.

## 4. Settings per kind

`<DATA_ROOT>/his.json` (owner only). Per-kind fields live under `adapter`. Fields can be sent flat to the API.

| Kind | Example `his.json` (fake values) |
|---|---|
| `fhir` | `{"kind": "fhir", "label": "City Hospital HIS", "url": "http://127.0.0.1:7130", "token": "<token>", "enabled": true}` |
| `fhir_generic`, basic | `{"kind": "fhir_generic", "label": "Bahmni", "url": "https://bahmni.hospital.example", "enabled": true, "adapter": {"preset": "bahmni_openmrs", "base_path": "/openmrs/ws/fhir2/R4", "identifier_systems": [], "auth": "basic", "username": "vaidyx_reader", "password_file": "<DATA_ROOT>/his_secrets/password"}}` |
| `fhir_generic`, OAuth2 | `{"kind": "fhir_generic", "url": "https://fhir.hospital.example/r4", "enabled": true, "adapter": {"auth": "oauth2", "token_url": "https://login.hospital.example/token", "client_id": "vaidyx-tb", "scope": "system/*.read", "identifier_systems": ["urn:hospital:mrn"], "client_secret_file": "<DATA_ROOT>/his_secrets/client_secret"}}` |
| `fhir_generic`, API key | `{"kind": "fhir_generic", "url": "https://his.hospital.example/fhir", "enabled": true, "adapter": {"auth": "api_key", "api_key_header": "X-API-Key", "api_key_file": "<DATA_ROOT>/his_secrets/api_key"}}` |
| `hl7v2_folder` | `{"kind": "hl7v2_folder", "label": "Lab results", "enabled": true, "adapter": {"preset": "generic_hl7v2", "folder": "<DATA_ROOT>/his_inbox/hl7"}}` |
| `folder_bridge` | `{"kind": "folder_bridge", "enabled": true, "adapter": {"preset": "generic_folder", "folder": "<DATA_ROOT>/his_inbox/reports"}}` |
| `abdm_bundles` | `{"kind": "abdm_bundles", "enabled": true, "adapter": {"folder": "<DATA_ROOT>/his_inbox/abdm"}}` |

| Rule | Detail |
|---|---|
| Hosts | Every URL (the server and the OAuth2 token endpoint) must be this server, a host in `TB_HIS_ALLOW_HOSTS`, or be saved by a Vaidyx admin |
| Folders | Must be inside an allowed root: `TB_HIS_FOLDER_ROOTS` (comma separated), default `<DATA_ROOT>/his_inbox`. No `..`. A link that leaves the root or the folder is refused or skipped. Checked on save and on every read |
| Limits | 5 MiB per HL7 file, bundle or index; 50 MiB per report file; 5,000 files; 50,000 index rows. Anything over is skipped and counted |
| Secrets | Password, API key, client secret: one owner-only (600) file each under `<DATA_ROOT>/his_secrets` (700). The bearer token stays in `his.json` (600) as before. Never logged, never in a URL, never returned: the API says "set" or "not set" |
| Keeping a secret | An empty secret keeps the saved one only while the kind, the server and the sign-in type stay the same |

## 5. How a hospital with product X connects

| Product | Method (preset kind) | What to ask the vendor or the hospital IT for |
|---|---|---|
| Vaidyx demo hospital | `fhir` | Nothing. Tested |
| Bahmni / OpenMRS | `fhir_generic` | A read-only OpenMRS user; the identifier type used as hospital number; whether reports carry a file |
| HAPI FHIR or any plain FHIR R4 | `fhir_generic` | Base address, sign-in type, identifier system of the hospital number |
| Epic / Oracle Health / TrakCare style | `fhir_generic` | A client id and secret (or a token). A signed JWT sign-in is not available yet |
| NIC e-Hospital, NextGen eHospital | `folder_bridge` | No public API found; needs NIC cooperation. HL7 v2 result files or a report export with an index; or its ABDM bundles as files |
| C-DAC e-Sushrut | `folder_bridge` | No public API found; needs C-DAC cooperation. Same asks as above |
| Insta HMS | `hl7v2_folder` | ORU^R01 result files with the report PDF (ED), or FHIR R4 |
| KareXpert, MocDoc | `folder_bridge` | FHIR R4 or HL7 v2 export, or the ABDM bundles the product creates |
| Napier, Akhil Miracle | `folder_bridge` | Interface not known. FHIR R4 or HL7 v2 export; else a report export with an index |
| Any LIS / RIS | `hl7v2_folder` | ORU^R01 to a file destination; which PID-3 repetition is the UHID |
| No system, or nothing offered | `folder_bridge` | A nightly folder of PDFs with `index.csv` |
| Any ABDM provider product | `abdm_bundles` | The NRCeS bundles it creates, saved as `.json` |

Every preset except the demo says "by standard, not tested with the product". Its `interface` field says how much is known:
documented, by standard, vendor claim only, no public API found, interface not known.

## 6. Invariants kept

| Invariant | How |
|---|---|
| Read only | Adapters only GET from a server (plus one POST to the OAuth2 token endpoint) and only read folders. Nothing is written, moved or deleted in a hospital system or its folder |
| Candidates, not facts | Adapters deliver records and candidate values. They never mark anything verified. `his_overlay` checks each value against the report text. Text-only reports carry no candidates |
| Signature | No adapter added here returns a signature. Unknown is never "yes"; the report text decides (rule below) |
| Secrets | See section 4. Tests check logs, errors, answers and stored files |
| Identifiers | UHID / MRN / CR No., IP / OP No., ABHA. An Aadhaar typed identifier in HL7 is dropped on read |
| Same shapes | Reports, patients, encounters, orders and documents have the keys of the FHIR client, so `his_case` and `his_overlay` work unchanged |

Signature rule (built, `test_his_adapters_signature.py`): each client says whether its connection can carry a signature Vaidyx-TB can
verify (`HISClient.carries_signature`: true for the demo hospital and the NRCeS FHIR path, false for the four kinds added here).
`his_case.fetch` writes that on the document (`his.signature_carried`). In `his_overlay.apply_status`:

| Connection | No signature for a version means | Where "signed" comes from |
|---|---|---|
| Carries signatures (`fhir`, the demo hospital) | Not signed (unchanged rule) | The hospital system |
| Carries none (`fhir_generic`, `hl7v2_folder`, `folder_bridge`, `abdm_bundles`) | Not known | The report text, as for an uploaded report |

The hospital system's status (preliminary, final, amended) still stands on every connection: a preliminary report never counts as
signed. The connection alone never gives "yes".

## 7. Out of scope

| Item | Why | What it would take |
|---|---|---|
| MLLP network listener | A listening port on the Vaidyx-TB server; a live site is under evaluation | A small relay process that writes files into the folder |
| SMART backend services (signed JWT) | Needs a key pair and a JWT signing library | `private_key_jwt` in `fhir_generic._oauth_token` |
| Live ABDM gateway (HIU, consent) | Needs NHA registration, callbacks and consent handling | A separate project |
| Writing back to the hospital system | Project rule: read only | Not planned |
| Per-vendor HL7 field maps (accession in OBR-18 to 21) | No vendor feed to test with | A `field_map` in the preset |

## 8. How to test with the demo hospital

| Check | Steps |
|---|---|
| Unit tests | `TB_SCHEDULER=0 /data/vaidyx/venv/app/bin/python -m pytest tumour_board/tests/test_his_adapters_*.py -q -p no:cacheprovider` |
| `fhir_generic` against the demo FHIR server | Save `{"kind": "fhir_generic", "url": "http://127.0.0.1:7130", "base_path": "/fhir", "auth": "bearer", "token": "<demo token>"}` on a test instance, then look up `VXH/26/004201`. The demo is NRCeS shaped, so this checks the generic path end to end (reports come through its DocumentReferences; signatures are still read) |
| `hl7v2_folder` with the demo feed | Copy the demo hospital's `data/his_mock/events.hl7` into `<DATA_ROOT>/his_inbox/demo/`, save `{"kind": "hl7v2_folder", "folder": "<DATA_ROOT>/his_inbox/demo"}`, run the connection test (about 650 messages, 25 patients), then look up `VXH/26/004201` or `IP/26/01871`. The feed carries no PDF, so every report is text only. The unit test `test_the_demo_hospitals_own_hl7_feed_is_read` does this in memory |
| `folder_bridge` | Put two synthetic PDFs and an `index.csv` in `<DATA_ROOT>/his_inbox/reports/`, save the kind, run the test, read the skipped counts |
| `abdm_bundles` | Save one NRCeS example bundle (synthetic) as `.json` in `<DATA_ROOT>/his_inbox/abdm/` |

Do these on a test data root, not on the deployed site.
