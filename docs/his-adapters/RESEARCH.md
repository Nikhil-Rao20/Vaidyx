# HIS adapters: what Indian hospital systems expose

Date of research: 12 Nov 2026. Method: web search and vendor / official pages only. Time box: 15 minutes.
Nothing here was tested against a real product.

How to read this file:

- "not found" means no source in this session stated it. It does not mean the product lacks it.
- "vendor claim" means the only source is the vendor's own page or press release.
- "[std]" marks facts taken from the published standard from background knowledge, not re-fetched in this session. Check them against the linked reference before coding.
- Source numbers like [S12] point to section 4.

Pages that could not be opened in this session (so their facts are missing): the ABDM integrators list (sandbox.abdm.gov.in now redirects to sandbox.nha.gov.in, which shows no list), the official HIP / HIU guidelines PDF (abdm.gov.in:8081 refused the connection), the NIC e-Hospital brochure PDF, the PIB press releases (HTTP 403), the Bahmni and OpenMRS Confluence page bodies (only navigation came back), the NCG EMR paper on PMC (captcha).

## 1. Product table

### 1a. Government and public sector

| Product | Who uses it | Interfaces offered | Auth | Sources |
|---|---|---|---|---|
| NIC e-Hospital (with ORS and e-BloodBank) | Central, state, autonomous and cooperative government hospitals, as cloud SaaS. Counts differ: 700+ hospitals in 29 states / UTs (NIC, Apr 2022), about 1,093 (Healthcare IT News, undated snippet). | FHIR R4 API: not found. HL7: NIC says it is "HL7 Development Framework compliant" and uses HL7, SNOMED CT, ICD-10, LOINC and MDDS. The brochure says lab analysers push data through HL7 interfaces (fragment only). Public REST API: not found. ABDM: on the NHA integrated list (May 2022), production key dated 2022-01-18. ORS is ABDM building-block compliant (ABHA based booking, lab report access). DB / file export: not found. | not found | [S1] [S2] [S3] [S4] [S5] |
| NIC NextGen eHospital | 68 health facilities live (NIC project page). Microservices, managed SaaS. Modules include ORS, Lab, Radiology, e-BloodBank. | Standards named by NIC: DICOM, LOINC, SNOMED CT, FHIR, ICD-10, ABDM. HL7 v2 is not mentioned. FHIR endpoint or API spec: not found. ABDM: "integrated", HIP / HIU role not stated. | not found | [S6] |
| C-DAC e-Sushrut (HMIS) | Reported at 17 AIIMS and 4,000+ health facilities (press, 2025 to 2026). Also the base of the Railways HMIS. | FHIR API: not found. HL7: the e-Sushrut Clinic site says "HL7 + MDDS" are built in for data exchange and device interoperability. ABDM: production key dated 2023-02-16 (C-DAC Noida), e-Sushrut Clinic says "compliant with M1-M4". REST API, DB / file export: not found. | not found | [S7] [S8] [S5] [S4] |
| C-DAC e-Sushrut@Clinic (light HMIS) | Small clinics. NHA and C-DAC MoU Aug 2025, launched June 2026. Cloud hosted in government approved centres. | Same claims as above (HL7 + MDDS, ABHA, HPR / HFR, M1 to M4). APIs or export: not stated. | not found | [S7] [S8] |
| Railways HMIS (RailTel + C-DAC e-Sushrut) | Indian Railways: target 129 hospitals and 586 health units. 156 facilities live by Sep 2021. Later status not found. | About 20 modules (OPD, IPD, labs, OT, blood bank, pharmacy). Linked to UMID. Described as "fully integrable" with NDHM (now ABDM). FHIR / HL7 / API details: not found. | not found | [S9] |
| ESIC Dhanwantri (Panchdeep) | All ESIC hospitals and dispensaries. Built by Wipro under Project Panchdeep (contract 2009, Rs 1,182 crore). | "ESIC" is on the NHA list of ABDM integrated government systems (May 2023). App uses the Panchdeep database with mobile OTP. FHIR / HL7 / API: not found. | not found (app: mobile OTP) | [S10] [S11] [S12] |
| Kerala e-Health | Kerala government facilities. Press counts: 751 hospitals (Apr 2025), about 800 institutions later. | ABDM: the State Digital Health Mission is tasked to "drive integration of HMIS ... with ABDM". Interfaces, API, standards: not found. | not found | [S13] |
| Tamil Nadu HMIS (HMIS 3.0) | Tamil Nadu government hospitals and medical colleges. Built with World Bank assistance (TNHSP). | ABDM enabled outpatient registration, ABHA linked to HMIS 3.0. Vendor (TCS was suggested) not confirmed. FHIR / HL7 / API: not found. | not found | [S14] |
| AIIMS | AIIMS New Delhi is moving to all modules of NIC e-Hospital (Healthcare IT News). e-Sushrut is reported at 17 AIIMS. | As per the product in use (rows above). Site specific interfaces: not found. | not found | [S3] [S7] |
| Other government systems on the NHA ABDM list | A-HMIS (Ministry of Ayush), Haryana e-Upchaar, Andhra Pradesh EHR, West Bengal Integrated HMS, CGHS HMIS, e-Aarogya (DNH and DD). | ABDM integrated per NHA (2022 to 2023). Other interfaces: not found. | not found | [S4] [S12] |

### 1b. Open source

| Product | Who uses it | Interfaces offered | Auth | Sources |
|---|---|---|---|---|
| Bahmni (OpenMRS + OpenELIS + Odoo + dcm4chee) | Low resource hospitals, NGOs. Live at JSS (India). Maintained with Thoughtworks. | FHIR R4 (and DSTU3) through the OpenMRS FHIR2 module, plain FHIR, not NRCeS shaped. OpenMRS REST API. Atom feeds (patient, encounter) for sync between OpenMRS, OpenELIS, Odoo, PACS: a consumer polls the feed, then calls REST. HL7 v2: ORM orders out, ORU results in some cases (Senaite LIMS via Mirth, PACS). DICOM / WADO through dcm4chee. ABDM: certified, on the NHA list. The India distro (BahmniIndiaDistro) adds hip-atomfeed-listener and openmrs-module-hip. HIP record types: Prescription, OPConsultation, DiagnosticReport, DischargeSummary, ImmunizationRecord, HealthDocumentRecord. | HTTP Basic with an OpenMRS user (wiki example: curl -u "user:password" .../openmrs/ws/fhir2/R4/Patient/{uuid}) | [S15] [S16] [S17] [S18] [S19] |
| OpenMRS | Global open source EMR. Base of Bahmni. India use outside Bahmni: not found. | FHIR2 module: R4 at /openmrs/ws/fhir2/R4, DSTU3 at /R3. CapabilityStatement at /ws/fhir2/R4/metadata. REST API. Resource list in section 3. SMART on FHIR: only a separate community module using Keycloak, not standard. | HTTP Basic (see Bahmni row). Session cookie reuse: not confirmed. | [S20] [S21] [S22] |
| GNU Health | India deployment: not found. | Separate FHIR server (Flask, pip install), described as work in progress with 12 resources. Thalamus REST message server (GET / PUT / PATCH / DELETE) for the Federation. FHIR version: not found. | Same user name and password as the GNU Health login. TLS advised. | [S23] |
| HospitalRun | Project archived. Repos archived Jan 2023, organisation archived Oct 2025. Not relevant for new work. | PouchDB in the browser, CouchDB on the server. No FHIR / HL7 found. | not found | [S24] |

### 1c. Commercial products in India

| Product | Who uses it | Interfaces offered | Auth | Sources |
|---|---|---|---|---|
| Practo Insta HMS | Private hospitals and clinics in India and the Gulf. Counts not stated. | Vendor claim: "out-of-the-box HL7 and API based integrations" with devices, diagnostic equipment, PACS, HRMS, CRM, accounting. Lab equipment links are "HL7-compliant", one-way and two-way. HL7 over API / HTTPS to UAE exchanges (NABIDH). FHIR: not found. ABDM for Insta: not found (Practo Ray, the clinic product, was announced ABDM compliant in May 2023, Practo is on the NHA list). | not found | [S25] [S26] [S4] |
| KareXpert | Private hospitals. NABH certified (HIS and EMR, Advanced). | ABDM integration announced, with "a standard ABDM connector". Milestone level, FHIR, HL7, API docs: not found. | not found | [S27] [S28] |
| MocDoc (Yro Systems) | Small and mid private hospitals, clinics, labs. NABH certified (HIS and EMR, Advanced). | Vendor claim: ABDM M1, M2, M3, "FHIR R4 compatible", FHIR claim bundles for PM-JAY. A third-party review rates its FHIR as "partial". HL7 v2 and API docs: not found. | not found | [S28] [S29] |
| Napier Healthcare | not found | not found | not found | (no result in two searches) |
| Akhil Systems Miracle HIS | Private hospitals. NABH certified (HIS and EMR, Advanced). Vendor cites 31+ years. | Third-party ranking says ABDM "yes", FHIR "partial". No primary source. HL7 / API: not found. | not found | [S28] |
| Birlamedisoft Quanta | Private hospitals. | Vendor slides: "interfaces with standards like ICD-10, HL7". ABDM, FHIR, API: not found. | not found | [S30] |
| MediXcel (Plus91) | Hospitals and clinic chains. NABH certified (valid May 2025 to May 2027). | ABDM: NHA certificate, vendor says all 3 milestones, on the NHA list (May 2022). HL7 v2, FHIR endpoint, API docs: not found. | not found | [S31] [S28] [S4] |
| Suvarna HIMS (Suvarna Technosoft) | Private hospitals. NABH certified (HIS and EMR, Advanced). | not found | not found | [S28] |
| Attune (LIS / HIS) | Diagnostic chains (Metropolis, Medall named) and hospitals. | LIS feature list includes "HL7 integration". Separate device integration product. ABDM, FHIR, ASTM: not found. | not found | [S32] |
| DocPulse | Clinics and hospitals. | not found (an ABDM result belonged to a different firm, DocPlix) | not found | (no usable source) |
| Eka Care (Orbi Health) | Clinic EMR and PHR app. NABH certified (CMS). | Registered as both HIP and HIU. Public developer API "ABDM Connect": records as FHIR R4 bundles in NRCeS profiles. Hosts: api.eka.care (production), api.dev.eka.care (sandbox). Webhook set-up goes through Eka support. | Client ID and client secret | [S33] [S28] [S4] |
| HealthPlix | Clinic EMR. NABH certified (CMS). | NABH listing says ABDM compliant. Milestone, API: not found. | not found | [S28] |
| Paras HMIS (Srishti Software) | Multi-location hospitals. | not found | not found | [S34] |
| Karkinos | Oncology network platform. | ABDM: approved for all three milestones, 30,000+ records linked by May 2023. Architecture (CTO interview): openEHR for storage, FHIR for exchange with outside systems, on Google Cloud. API docs: not found. | not found | [S35] |
| 21 CSC | not found | not found | not found | (not found) |
| Wipro HIS | Wipro built the ESIC hospital information system under Panchdeep. A branded Wipro HIS product: not confirmed. | not found | not found | [S10] |
| Apollo Hospitals: MedMantra | In-house HIS across the Apollo network. | "Medmantra, Apollo Hospitals" is on the NHA ABDM integrated list (May 2022). Public API, FHIR, HL7: not found. | not found | [S4] [S36] |
| Narayana Health: Athma | In-house HIS (name is Athma). | "Athma, Narayana Health Limited" is on the NHA ABDM integrated list (May 2022). Public API: not found. | not found | [S4] |
| Manipal Hospitals | InterSystems TrakCare. Go-live at Manipal Hospital Bangalore in 2008, later enterprise agreement. Sources are old, current state not verified. | See TrakCare row. | not found | [S37] |
| HCG | not found | not found | not found | (not found) |
| Tata Memorial Centre | Own EMR details: not found. TMH is a pilot site for an ABDM enabled EMR under the NHA and NCG partnership. | NCG-KCDO empanelled six oncology EMR vendors (two names seen: Amrita Technologies, Manorama Infosolutions), deployed in 16 NCG hospitals. Requirements stress interoperability and ABDM. Exact interface list: not read. | not found | [S38] |
| Other names seen on official lists | NABH list: eClinicalWorks, SRIT RHES, HISTree, Mednet, Hospedia (ITdose), Lifeline HIMS (Manorama), ohumSKY, MyHealthcare, Healthray, DigiCure, Presco (incl. an Oncology Workstation). NHA list: DrucareOne, DocOn, Amrit (Piramal), CrelioHealth, SRL CLIMS, Dr Lal PathLabs. | NABH or ABDM listed. Interfaces: not researched. | not found | [S28] [S4] |

### 1d. International products

| Product | Presence in India | Standards | Auth | Sources |
|---|---|---|---|---|
| InterSystems TrakCare | Sir Ganga Ram Hospital, New Delhi (2009). Manipal Hospital Bangalore and Pushpanjali Crosslay Hospital, Ghaziabad (2008 go-lives). No 2025 to 2026 India announcement found. | not found in this session | not found | [S37] |
| Epic | No Indian hospital deployment found. One unverified page mentions Sun Pharma. | Third-party blogs: FHIR R4 for most data, HL7 v2 through the Bridges engine. | [std] SMART Backend Services (signed JWT) for system access | [S39] |
| Oracle Health (Cerner) | Karuna Trust, Karnataka: 35+ primary health centres on Cerner Millennium. No hospital-level site found. Oracle said in 2023 it plans to bring Cerner to India. | Third-party blogs: mainly FHIR R4 (US Core), some sites R3. | [std] SMART / OAuth2 | [S40] [S39] |
| MEDITECH | No Indian hospital found. | Third-party blog: Expanse has FHIR R4, version 6.x and older are HL7 v2 only. | not found | [S39] |

## 2. What this means for connectors

Main findings:

1. No source shows any Indian HIMS product with a public, documented, local FHIR REST endpoint for a hospital's own data, except Bahmni / OpenMRS (FHIR2 module), GNU Health (separate FHIR server) and Eka Care (cloud API).
2. "ABDM compliant" means the product can create NRCeS FHIR document bundles and push them through the ABDM gateway after patient consent. It does not mean the product has a FHIR server we can query.
3. HL7 v2 is the interface most vendors name (Insta, Attune, Birlamedisoft, NIC e-Hospital, e-Sushrut Clinic). It is mostly cited for lab analysers, devices and PACS. It needs the vendor or hospital IT to switch on an outbound feed to us.
4. Government SaaS (e-Hospital, NextGen, e-Sushrut) has no public read API in any source. Access would need NIC or C-DAC to agree.
5. An HIU needs patient consent for every pull through ABDM. No source gives an exception for a facility reading its own records. So ABDM is not a way to read the hospital's own HIMS. It is a way to fetch a patient's records from other facilities, with consent.

Proposed connection methods (5 plus 1 optional):

| # | Method | Presets | Serves | Cannot cover |
|---|---|---|---|---|
| 1 | FHIR R4, ABDM / NRCeS profile (exists today) | HAPI with NRCeS shapes | Any site that stands up a local FHIR store fed by its ABDM bundle generator. Our own demo instance. | Products that only push bundles to the gateway and have no local store (most of them). |
| 2 | Plain FHIR R4 REST | OpenMRS FHIR2 (Bahmni, OpenMRS), HAPI, GNU Health FHIR, SMART backend services profile for Epic / Oracle / MEDITECH Expanse | Bahmni and OpenMRS sites now. Any future international EHR site. | Bahmni data that is not mapped to FHIR (forms kept as obs groups, uploaded documents). FHIR2 resource coverage is partial, check /metadata. |
| 3 | HL7 v2 results in: ORU^R01 (and MDM with PDF, ADT for demographics) over MLLP listener or a watched folder | Generic LIS, generic RIS, per-vendor field maps (where PID-3 and accession live) | LIS and RIS in most private hospitals, products that claim HL7 (Insta, Attune, Birlamedisoft, analyser middleware, PACS / RIS). | Needs an outbound feed set up by the vendor. It is a stream, not a query: no history unless the vendor replays. Read only is natural here (we only receive). |
| 4 | ABDM health record bundles (Bundle type "document", Composition first) from file, folder or upload | The 8 NRCeS record types | Any ABDM M2 product that can hand over the bundles it creates (e-Hospital, e-Sushrut, MediXcel, MocDoc, KareXpert, Bahmni HIP, Eka Care API). Records a patient shares from other hospitals. | A live HIU pull needs HIU registration, certification and patient consent each time. Many ABDM records are a PDF inside a DocumentReference, not structured data. |
| 5 | Report folder with an index file (PDF, images, plus CSV or JSON manifest: patient id, report type, date, file name) | Folder watch, SFTP drop | Small hospitals and every product with no documented interface (Napier, DocPulse, Paras, Suvarna, Miracle, HCG, in-house systems). LIS that only print branded PDF reports. | Needs a person or script on the hospital side to export. Content is unstructured, so it needs our document reading step. |
| 6 (optional) | Read only database view, or MCP server wrapping a vendor REST API | Per site | Sites whose vendor grants a SQL view or a private REST API. | Per site work, not reusable. No source describes any vendor's schema. |

Coverage note: methods 3 and 5 together are the realistic path for most Indian private hospitals. Method 2 covers the open source group fully. Methods 1 and 4 keep us aligned with the national rail. Government SaaS stays uncovered until NIC or C-DAC offers access.

Evidence on how common each path is:

- HL7 v2 in India: no India-specific survey was found. Signals: vendor pages cite HL7 for analysers, devices and PACS. One Indian reference says legacy LIS / RIS often still run HL7 v2.x while ABDM requires FHIR R4. Indian LIS vendors advertise HL7 and ASTM analyser links (RS232, TCP/IP) and "branded PDF" reports. [S41] [S42]
- No API at all: an HMPI article (July 2026) says many facilities run proprietary software with no ABDM compliant API layer, and integration costs a mid-size provider about Rs 30 to 50 lakh. [S43]
- Export habits of small hospitals (PDF folder, CSV / Excel, database view): PDF reports are documented by LIS vendors. CSV / Excel export and database views: no source found in this session. Treat as an assumption to confirm with pilot sites.
- ABDM scale: 100+ integrations by May 2023, of which 53 apps had M2 (HIP) and 45 had M3 (HIU). By May 2026: 880+ million ABHA, 500,000+ facilities, 1,000+ integrated private companies, but cross-facility record retrieval "remains extremely low". [S12] [S43]
- NMC order of 3 Mar 2026: all medical colleges must integrate the HMIS of attached hospitals with the ABDM HMIS portal within 15 days. The annexure covers ABHA creation, ABHA search and Scan and Share. So teaching hospitals will have ABHA numbers on file. [S44]

Auth styles seen in sources:

| Style | Where seen |
|---|---|
| HTTP Basic (user and password) | OpenMRS FHIR2 and REST, Bahmni, GNU Health FHIR server |
| Client ID + client secret (token) | Eka Care developer API. [std] ABDM gateway sessions work the same way. |
| SMART Backend Services (signed JWT, OAuth2 client credentials) | [std] Epic, Oracle Health. Not seen for any Indian product. OpenMRS has only a community SMART module (Keycloak). |
| API key | Not seen in any source for the products above. |
| No auth on the wire | [std] HL7 v2 over MLLP has none. Protect with network allow-list, VPN or TLS wrapped MLLP. |

## 3. Facts needed to implement each method

### 3a. OpenMRS FHIR2 module (Bahmni, OpenMRS)

- Base path: {host}/openmrs/ws/fhir2/R4/ . DSTU3 is at /openmrs/ws/fhir2/R3/ . Example: /openmrs/ws/fhir2/R4/Patient/{uuid}. [S20]
- Capability check: GET /openmrs/ws/fhir2/R4/metadata . The supported set depends on module version, so read this at connect time. [S20]
- Auth: HTTP Basic with an OpenMRS user. Bahmni wiki example: curl -u "superman:Admin123" -H "Content-Type: application/json" https://{host}/openmrs/ws/fhir2/R4/Patient/{uuid}. Create a read only OpenMRS user for us. [S21]
- R4 resource providers in the module source (GitHub, master, list may be incomplete): AllergyIntolerance, Condition, DiagnosticReport, Encounter, EpisodeOfCare, Group, Immunization, Location, Medication, MedicationDispense, MedicationRequest, Observation, Patient, Person, Practitioner, RelatedPerson, ServiceRequest, Task, ValueSet. [S22]
- Not in that provider list: Composition, DocumentReference, ImagingStudy, Procedure, Specimen. So do not expect NRCeS record bundles from this endpoint. Confirm with /metadata on the site.
- IDs are OpenMRS UUIDs. The hospital number is in Patient.identifier.
- Coding: OpenMRS concepts (CIEL), with maps to LOINC, ICD-10, SNOMED where the site has loaded them. [S17]
- Bahmni extras: lab results flow from OpenELIS into OpenMRS through the Atom feed, so they appear as OpenMRS data. Radiology images sit in dcm4chee (DICOM / WADO). [S16] [S17]
- [std] OpenMRS REST base is /openmrs/ws/rest/v1 and Bahmni feeds are under /openmrs/ws/atomfeed/{patient|encounter}/recent. Not re-verified in this session.

### 3b. HL7 v2 ORU^R01 [std]

Reference for all fields: HL7 v2.5.1 chapter 7, browsable at [S45]. The field positions below are the same from v2.3 to v2.5.1. Which version Indian vendors send: not found.

Message shape: MSH, PID, [PV1], { [ORC], OBR, {OBX}, [NTE] }.

| Need | Field | Notes |
|---|---|---|
| Message type | MSH-9 | ORU^R01 (v2.5: ORU^R01^ORU_R01). MDM^T02 carries a document with TXA + OBX. |
| Message id, version | MSH-10, MSH-12 | Echo MSH-10 in the ACK (MSA-2). |
| Character set | MSH-18 | Often empty. Assume UTF-8 or ISO 8859-1 by site preset. |
| Patient id | PID-3 | Repeating CX: id^^^assigning authority^type. Pick the repeat with type MR (hospital UHID). Some old feeds use PID-2 or PID-4. |
| Name, DOB, sex | PID-5, PID-7, PID-8 | |
| Visit | PV1-19 | Visit number. PV1-2 patient class (I, O, E). |
| Placer order no. | OBR-2 (also ORC-2) | Order number from the HIS. |
| Filler order no. | OBR-3 (also ORC-3) | Number from the LIS / RIS. Often the accession number for labs. |
| Test or procedure | OBR-4 | code^text^coding system. |
| Times | OBR-7, OBR-22 | Observation time, result report / status change time. |
| Accession (radiology) | OBR-18, OBR-19, OBR-20, OBR-21 | Placer field 1, placer field 2, filler field 1, filler field 2. IHE radiology puts the accession number in OBR-18 and the requested procedure id in OBR-19. Vendors vary: make this a preset. |
| Department | OBR-24 | Diagnostic service section (LAB, RAD, HM, CH, MB, SP ...). |
| Report status | OBR-25 | F final, P preliminary, C corrected, X cancelled, I pending, A partial. |
| Value type | OBX-2 | NM number, ST / TX / FT text, CE / CWE coded, SN structured numeric, ED embedded data, RP pointer to a file. |
| What was measured | OBX-3 | code^text^coding system (LN means LOINC, often a local code in India). |
| Sub id | OBX-4 | Groups related OBX (cultures, report sections). |
| Value | OBX-5 | Meaning depends on OBX-2. May repeat with ~. |
| Units | OBX-6 | |
| Reference range | OBX-7 | Free text like 4.0-11.0. |
| Abnormal flag | OBX-8 | H, L, HH, LL, A, N. |
| Result status | OBX-11 | F, P, C (corrected, replaces the earlier value), X, D (deleted), W (wrong, withdrawn). |
| Observation time | OBX-14 | |

Embedded PDF:

- OBX-2 = ED. OBX-5 has five components: source application ^ type of data ^ data subtype ^ encoding ^ data. Encoding is A (none), Hex or Base64. [S46]
- Common forms: ^application^pdf^Base64^JVBERi0x... and ^AP^PDF^Base64^... . Some senders move the fields by one place, so find the component that says Base64 and take the next one. [S46]
- Some senders use OBX-2 = RP with a file path or URL in place of the bytes. Support both. [S46]
- Large PDFs: some engines limit a segment to about 32K characters, and senders then split the Base64 over several OBX segments. Join by OBX-1 / OBX-4 order before decoding. [S46]
- Base64 text must not contain the HL7 delimiters. Un-escape \F\ \S\ \T\ \R\ \E\ in text fields, and treat \.br\ as a line break in FT.

Text reports (radiology, histopathology) often come as many OBX segments of type TX or FT, one line each. Join them in order.

Transport:

- MLLP frame: 0x0B (VT, start block), the message, 0x1C (FS, end block), 0x0D (CR). Segments inside the message end with 0x0D. [S47]
- Reply on the same connection with an ACK in the same frame: MSH + MSA, MSA-1 = AA (accept), AE (error) or AR (reject), MSA-2 = the incoming MSH-10. [std]
- MLLP is not formally part of the HL7 standard, it comes from v2.3.1 appendix C. Multi-byte encodings such as UTF-16 are not supported. [S47]
- Folder drop: one message per file (.hl7), same content without the frame bytes. Batch files may wrap messages in FHS / BHS ... BTS / FTS. [std]
- Corrections: a later message with OBR-25 = C or OBX-11 = C replaces the earlier result for the same filler order number. Keep the latest by OBR-3 + OBX-3 + OBX-4.

### 3c. ABDM / NRCeS

- Guide: "FHIR Implementation Guide for ABDM", by NRCeS, on FHIR R4. Current published version: 6.5.0, status active, page generated 2025-05-08. A 7.0.0 build exists only under a preview path. [S48]
- Record types, all profiles on Composition: DiagnosticReportRecord, DischargeSummaryRecord, OPConsultRecord, PrescriptionRecord, HealthDocumentRecord, WellnessRecord, ImmunizationRecord, InvoiceRecord. [S48]
- Supporting profiles include DocumentBundle (Bundle), DiagnosticReportLab, DiagnosticReportImaging, DocumentReference, Binary, ImagingStudy, Observation (plus vital signs, body measurement, lifestyle, women health, general assessment, physical activity), Condition, Procedure, MedicationRequest, MedicationStatement, Specimen, ServiceRequest, Encounter, Patient, Practitioner, PractitionerRole, Organization, CarePlan, Appointment, Immunization, AllergyIntolerance, FamilyMemberHistory, Invoice, ChargeItem, Media. [S48]
- Bundle rules (DocumentBundle): Bundle.type = "document". identifier with system and value is required. timestamp is required. The first entry must be a Composition. entry.fullUrl should have a value. signature is optional. [S49]
- Profile URL pattern: https://nrces.in/ndhm/fhir/r4/StructureDefinition/{Name}, for example .../StructureDefinition/Patient. [S50]
- Patient identifier in the official example: type coding system http://terminology.hl7.org/CodeSystem/v2-0203, code MR, system "https://healthid.ndhm.gov.in", value "22-7225-4829-5255" (the 14 digit ABHA number format). [S50]
- Identifier type value set: 138 codes from v2-0203 (MR, ACSN, VN ...) plus 35 NDHM codes in https://nrces.in/ndhm/fhir/r4/CodeSystem/ndhm-identifier-type-code , including ABHA ("Ayushman Bharat Health Account (ABHA) ID") and HIN ("Health ID issued by NDHM"). There is no separate code for the ABHA address. [S51]
- In practice: match a patient by ABHA number (14 digits, with or without hyphens) when present, else by the hospital MR number. The ABHA address looks like name@abdm (name@sbx in sandbox) [std]. Whether senders also put it in Patient.identifier: not found, so accept both as a precaution.
- Roles: HIP holds and shares records. HIU is "any permitted entity that would like to access health records of an individual with their informed consent" (official guidelines, 24 Oct 2022). One hospital is usually both. [S52] [S53]
- Flow: (1) HIU sends a consent request through the gateway, the patient approves in a PHR app. (2) The Consent Manager issues one consent artefact per HIP (consent id, HI types, purpose code, date range, expiry / dataEraseAt). (3) HIU sends a data request with the consent id, its public key, a nonce and a data push URL. (4) HIP checks the artefact, builds FHIR bundles, encrypts them (ECDH on Curve25519, "Fidelius", AES-GCM) and posts them to the push URL. The gateway routes messages and stores no records. [S53] [S54]
- Purpose codes: CAREMGT, BTG, PUBHLTH, HPAYMT, DSRCH, PATRQT. If consent is revoked the HIU must delete its copy. [S54]
- Milestones: M1 ABHA creation and verification, M2 HIP (link care contexts, share records), M3 HIU (request consent, fetch records). Some sources add M4. Certification testing is done by empanelled agencies before production keys are issued. [S12] [S33] [S55]
- Own records question: every source says an HIU needs a consent artefact for each pull. No source gives an exception for a facility's own records. A hospital reads its own records from its own HIMS, not through ABDM. [S52] [S53] [S54]
- Caveat: bundles must follow NRCeS profiles to pass validation, but a plain PDF inside a DocumentReference is valid, so expect many PDF-only records. [S53]

## 4. Sources

- [S1] NIC Informatics, e-Hospital article and April 2022 issue: https://informaticsweb.nic.in/article/e-hospitalnic-simplifying-health-care-delivery , https://informatics.nic.in/files/informatics-flipbook-Apr-2022/files/basic-html/page10.html
- [S2] NIC e-Hospital suite brochure (search snippet only, PDF not opened): https://informatics.nic.in/uploads/pdfs/4d85cc7c_04_11_ehospital_suite_folder_new.pdf , about page: https://ehospital.nic.in/ehospitalcloud/CloudHome/aboutus.jsp
- [S3] Healthcare IT News, AIIMS Delhi to fully implement e-Hospital: https://healthcareitnews.com/node/551970
- [S4] NHA list of 40 ABDM integrated applications, 13 May 2022 (reprint of the PIB release): https://medicaldialogues.in/news/health/nha-40-digital-health-services-integrated-with-ayushman-bharat-digital-mission-abdm-92843 , PIB original (403 here): https://www.pib.gov.in/PressReleasePage.aspx?PRID=1824411
- [S5] ABDM successful integrators list (search snippet only, page now redirects): https://sandbox.abdm.gov.in/applications/Integrators/production_approved , partner list: https://abdm.gov.in/our-partners
- [S6] NIC NextGen eHospital: https://www.nic.gov.in/project/nextgen-ehospital/ (read via the s3waas mirror), https://nextgen.ehospital.nic.in/onboarding/
- [S7] e-Sushrut and e-Sushrut@Clinic press: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2156603 , https://www.pib.gov.in/PressReleasePage.aspx?PRID=2278996 , https://www.business-standard.com/industry/news/nha-cdac-esushrut-clinic-hmis-small-healthcare-providers-125081500689_1.html
- [S8] e-Sushrut Clinic site: https://ehmis-lite.in/
- [S9] Railways HMIS: https://biospectrumindia.com/news/22/19510/indian-railways-rolls-out-hmis-across-129-railway-hospitals-and-586-health-units.html , https://www.ibef.org/news/indian-railways-rolls-out-hospital-management-information-system-hmis-over-156-health-facilities-across-indian-railways
- [S10] Wipro and ESIC Panchdeep: https://www.wipro.com/newsroom/press-releases/archives/wipro-completes-implementation-of-employees-state-insurance-corp/ , https://www.business-standard.com/article/companies/wipro-wins-rs-1-182-crore-project-from-esic-109031200123_1.html
- [S11] ESI Dhanwantri app listing: https://apps.apple.com/in/app/esi-dhanwantri/id1580299295
- [S12] 100+ programmes and apps integrated with ABDM, May 2023: https://medicaldialogues.in/news/health/over-100-health-programmes-and-apps-integrated-with-ayushman-bharat-digital-mission-111367
- [S13] Kerala e-Health: https://keralakaumudi.com/en/kerala/general/treatment-at-your-fingertips-751-hospitals-adopt-e-health-system-in-kerala-1512863 , https://arogyakeralam.gov.in/wp-content/uploads/2023/02/careers-SDHM-Ehealth2-08.02.23.pdf
- [S14] Tamil Nadu HMIS 3.0: https://www.digitalhealthnews.com/tamil-nadu-accelerates-abha-rollout-as-2-54-cr-residents-join-the-state-s-digital-health-network , https://medicaldialogues.in/news/health/hospital-diagnostics/coimbatore-medical-college-hospital-rolls-out-hmis-30-to-simplify-patient-registration-178843 , https://www.dtnext.in/news/tamilnadu/tamil-nadu-introduces-online-outpatient-registration-at-government-hospitals
- [S15] Bahmni India distro repos: https://github.com/bahmniindiadistro
- [S16] Bahmni Atom feed sync: https://bahmni.atlassian.net/wiki/spaces/BAH/pages/3506200 , https://github.com/Bahmni/openerp-atomfeed-service
- [S17] Bahmni standards and interoperability (2023 roadmap): https://bahmni.atlassian.net/wiki/spaces/BAH/pages/3176333313/Bahmni+support+for+Open+Global+Standards+Interoperability+OpenHIE+-+2023+Roadmap
- [S18] Bahmni as ABDM HIP: https://bahmni.atlassian.net/wiki/spaces/BAH/pages/2901114904
- [S19] Bahmni support for Health Information types: https://bahmni.atlassian.net/wiki/spaces/BAH/pages/3162079253
- [S20] OpenMRS FHIR docs: https://openmrs.atlassian.net/wiki/spaces/projects/pages/26935684/FHIR+101+OpenMRS+Strategy+Tools+FHIR+API+and+Help , IG: https://fhir.openmrs.org/toc.html
- [S21] Bahmni REST API and FHIR APIs (basic auth curl example, via search snippet): https://bahmni.atlassian.net/wiki/spaces/BAH/pages/6488066/Bahmni+REST+API+FHIR+APIs
- [S22] OpenMRS FHIR2 module source: https://github.com/openmrs/openmrs-module-fhir2 , providers: https://github.com/openmrs/openmrs-module-fhir2/tree/master/api/src/main/java/org/openmrs/module/fhir2/providers/r4 , community SMART module: https://github.com/VaishSiddharth/openmrs-module-smartonfhir/blob/master/README.md
- [S23] GNU Health FHIR server: https://docs.gnuhealth.org/his/techguide/fhir/installation.html , https://pypi.org/project/gnuhealth-fhir-server
- [S24] HospitalRun: https://github.com/HospitalRun/hospitalrun , https://opencollective.com/hospitalrun
- [S25] Insta HMS: https://www.instahms.com/hospital , https://www.practo.com/providers/hospitals/insta/features , https://www.instahms.com/health-information-exchange
- [S26] Practo Ray and ABDM: https://cxotoday.com/press-release/practo-joins-the-ayushman-bharat-digital-mission-abdm-ecosystem-with-practice-management-software-ray/
- [S27] KareXpert and ABDM: https://www.digitalhealthnews.com/jio-backed-digital-healthcare-platform-karexpert-completes-integration-with-abdm , https://karexpert.com/blogs/ayushman-bharat-digital-mission-pioneering-digital-healthcare-in-india-with-karexpert
- [S28] NABH certified healthcare software list: https://nabh.co/nabh-certified-healthcare-software/ , entries: https://nabh.co/software/yro-systems-pvt-ltd/ , https://nabh.co/software/akhil-systems-pvt-ltd/ , https://nabh.co/software/plus91-technologies-pvt-ltd/ , https://nabh.co/software/healthplix/
- [S29] MocDoc: https://mocdoc.com/pmjay-integrated-hospital-software , https://mocdoc.com/blog/abdm-milestone-certified-hospital-software , third-party comparison: https://connect.nuvertos.com/blog/top-10-hospital-software-india-2026-ranked-size-budget
- [S30] Birlamedisoft Quanta: https://www.slideshare.net/slideshow/hims-pptquanta-v3-0/47668963 , https://www.techjockey.com/detail/birlamedisoft-quanta-hims-v2
- [S31] Plus91 MediXcel and ABDM: https://www.pr.com/press-release/852383 , https://www.pr.com/company-profile/press-releases/487959
- [S32] Attune: https://www.slideshare.net/attunetechnologies/attune-lab-information-system , https://ehealth.eletsonline.com/2015/12/attune-technologies-pvt-ltd/
- [S33] Eka Care developer docs: https://developer.eka.care/api-reference/user-app/abdm-connect/overview , https://info.eka.care/services/abdm-enabling-ecosystems
- [S34] Paras HMIS: https://srishtisoft.com/wp-content/uploads/2012/04/01.PARAS_Product_Overview-THIT_2015-Srishti_Software.pdf
- [S35] Karkinos: https://www.karkinos.in/tag/abdm/ , https://biospectrumindia.com/article/pdf/22543
- [S36] Apollo MedMantra: https://www.apollohospitals.com/clinical-quality-and-outcomes/it-excellence , https://www.healthcareitnews.com/news/asia/apollo-hospitals-enters-next-phase-digital-transformation (403 here)
- [S37] TrakCare in India: https://www.siliconindia.com/shownews/sir-ganga-ram-hospital-adopts-intersystems-trakcare-nid-55819-cid-2.html , https://ehealth.eletsonline.com/?p=10154 , https://ehealth.eletsonline.com/?p=10121 , https://businesschief.asia/company-reports/indias-doctor-watson
- [S38] NCG EMR initiative: https://pmc.ncbi.nlm.nih.gov/articles/PMC12057217/ , https://tmc.gov.in/ncg-old/index.php/ncgemr1 , https://www.digitalhealthnews.com/nha-ncg-to-launch-pilot-program-to-streamline-cancer-care-record-sharing
- [S39] Epic / Cerner / MEDITECH standards (third-party blogs): https://www.hl7-integration.co/post/epic-cerner-integration-guide , https://interexy.com/fhir-integration-guide-epic-cerner-meditech
- [S40] Oracle Health in India: https://www.oracle.com/customers/karuna-trust/ , https://www.bizzbuzz.news/technology/have-big-plans-to-get-oracles-healthcare-arm-cerner-to-india-top-exec-1253911
- [S41] HL7 v2 in legacy Indian LIS / RIS: https://kcdh-book-2026.pages.dev/technical/interoperability
- [S42] Indian LIS vendors (HL7 / ASTM analyser links, PDF reports): https://relyhealthtech.com/solutions/relylis , https://www.ayuslab.com/capabilities.html , https://caho.in/files/Principles%20of%20choosing%20a%20software%20including%20communications%20standards%20&%20legal%20requirements%20by%20Dr%20Divye%20Chhabra.pdf
- [S43] HMPI, operationalising ABDM (9 July 2026): https://hmpi.org/2026/07/09/from-infrastructure-to-impact-operationalizing-indias-ayushman-bharat-digital-mission/
- [S44] NMC circular, 3 Mar 2026, HMIS integration with ABDM: https://medicaldialogues.in/pdf_upload/2026/03/05/nmc-implementation-of-hmis-health-management-information-system-for-attached-hospitals-331086.pdf
- [S45] HL7 v2.5.1 ORU^R01 field reference (not fetched in this session): https://hl7-definition.caristix.com/v2/HL7v2.5.1/TriggerEvents/ORU_R01
- [S46] ED data type and embedded PDF practice: https://hexdocs.pm/hl7v2/HL7v2.Type.ED.md , https://help.interfaceware.com/code/details/embed-a-binary-file-in-an-hl7-message , https://groups.google.com/g/ensemble-in-healthcare/c/MCKd8noqYQY , https://hl7.org.au/archive/hl7v2wg/2622059.html
- [S47] MLLP framing: https://hapifhir.github.io/hapi-hl7v2/base/apidocs/ca/uhn/hl7v2/llp/MinLowerLayerProtocol.html , https://hexdocs.pm/hl7v2/HL7v2.MLLP.html , https://docs.oracle.com/cd/E19509-01/821-0377/ghcvq/index.html
- [S48] NRCeS FHIR IG for ABDM, profiles (v6.5.0): https://nrces.in/ndhm/fhir/r4/profiles.html , home: https://nrces.in/ndhm/fhir/r4/index.html
- [S49] DocumentBundle profile: https://nrces.in/ndhm/fhir/r4/StructureDefinition-DocumentBundle.html
- [S50] Patient profile and example: https://nrces.in/ndhm/fhir/r4/StructureDefinition-Patient.html , https://nrces.in/ndhm/fhir/r4/Patient-example-01.json.html
- [S51] Identifier type value set: https://nrces.in/ndhm/fhir/r4/ValueSet-ndhm-identifier-type-code.html
- [S52] ABDM HIP / HIU guidelines, 24 Oct 2022 (quoted via search snippet, PDF not opened): https://abdm.gov.in:8081/uploads/HIP_HIU_Guidelines_f85df336ec.pdf , HIE-CM: https://abdm.gov.in:8081/uploads/ABDM_HIE_CM_ea5d4c0559.pdf
- [S53] How clinical data flows under ABDM (vendor blog, June 2026): https://caladriushealth.ai/blog/2026/06/19/How-Records-Move/
- [S54] ABDM consent docs (community mirror): https://kiranma72.github.io/abdm-docs/3-milestone2/understanding-consents
- [S55] ABDM sandbox exit and certification process (community doc): https://docs.coronasafe.network/abdm-documentation/implementers-guide/abdm-sandbox-integration-and-exit-process
