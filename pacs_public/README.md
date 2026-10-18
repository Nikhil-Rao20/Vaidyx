# pacs_public: the public image library for the demo PACS

Real (but public and de-identified) radiology images for the demo PACS, in place of the abstract test patterns that
`his_mock/dicom_studies.py` draws today. The images come from The Cancer Imaging Archive (TCIA), CC BY 3.0 and CC BY
4.0 collections only. They are relabelled with the synthetic identities of the mock hospital before they reach Orthanc.
Owner exception of 17 Oct 2026 (project rules, Mock hospital section): open licence, public, de-identified, licence checked and
logged in a manifest, relabelled with our fake IDs, marked as public dataset images, never the real case. The images
are for humans to view in the PACS; no model ever reads them, and nothing here interprets pixels.

Phase 1 (this folder, done): download, privacy QA, manifest and licences, assignment plan, relabel library and tests.
Phase 2 (not done, see the end): the image source switch in `his_mock/dicom_studies.py` and the Orthanc upload.

## Where things live

| Path | What |
|---|---|
| `pacs_public/picks.json`, `picks_extra.json` | The chosen series (plan `docs/ui/build/pacs/tcia_plan.md` section 2, plus 6 chest radiographs added in Phase 1) |
| `pacs_public/series_list.tsv` | Download list written from the picks (`manifest.py --series-list`) |
| `pacs_public/download_tcia.sh` | Downloader (public NBIA API, no login; retries, count check, `.complete` markers) |
| `pacs_public/qa_check.py` | Face check and burned-in text renders; applies the recorded crop decisions |
| `pacs_public/qa_decisions.json` | The recorded decision for every series (face clear or crop level, text check) |
| `pacs_public/manifest.py` | Collection facts, roles, MANIFEST.json / .csv, LICENCES.md, ATTRIBUTION.txt |
| `pacs_public/relabel.py` | `plan_assignment`, `relabel_series`, `verify_relabelled` (library, no side effects on import) |
| `pacs_public/assignment.json` | Which public series goes with which HIMS accession (or why it stays synthetic) |
| `/data/vaidyx/tb_resources/dicom_public/raw/<Collection>/<SeriesUID>.zip` | Original download, the provenance record; never imported |
| `/data/vaidyx/tb_resources/dicom_public/raw/<Collection>/<SeriesUID>/*.dcm` | Extracted series after the face crop; Phase 2 reads these |
| `/data/vaidyx/tb_resources/dicom_public/qa/<SeriesUID>/` | QA renders (top / bottom slices, mid slice, sagittal reformat, `sheet.png`); `qa_results.json` |
| `/data/vaidyx/tb_resources/dicom_public/MANIFEST.json`, `MANIFEST.csv` | One row per series (fields below) |
| `/data/vaidyx/tb_resources/dicom_public/LICENCES.md`, `ATTRIBUTION.txt` | Licence record and the short credit text |
| `/data/vaidyx/tb_resources/dicom_public/download.log` | Every download attempt |

Size: 77 series, 37 source patients, 19 collections, 9610 DICOM files (4.2 GB) plus 1.97 GB of zips.

## How it was built

All commands from the repo root; Python on downloaded data always with `-I` (downloaded files are untrusted data and
are only parsed with pydicom).

```
python -I pacs_public/manifest.py --series-list          # picks -> series_list.tsv
bash pacs_public/download_tcia.sh                         # -> raw/, download.log (TCIA_JOBS=3 parallel)
python -I pacs_public/qa_check.py --render                # -> qa/<series>/*.png, qa/render_index.json
#   look at the renders, record decisions in pacs_public/qa_decisions.json
python -I pacs_public/qa_check.py --apply                 # removes the face slices, writes qa/qa_results.json
python -I pacs_public/manifest.py --licences --build      # LICENCES.md, ATTRIBUTION.txt, MANIFEST.json / .csv
python -I pacs_public/relabel.py --plan                   # pacs_public/assignment.json (reads data/his_mock/store.json)
python -I pacs_public/relabel.py --check <slot or uid> --out <scratch dir>   # dry run of one relabel + verify
/data/vaidyx/venv/app/bin/python -m pytest pacs_public/tests -q
```

Download history: the first run (18 Oct, 04:15 to 04:20 UTC) completed 71 of 77. The 6 missing series were the chest
radiographs CXR-01 to CXR-06 (LIDC-IDRI DX): they were added to `series_list.tsv` from `picks_extra.json` three minutes
after that run had read the list, so they were never attempted (no failure in the log). One retry at 05:29 UTC fetched
all 6. Every series matches its TCIA image count.

Manifest fields (MANIFEST.csv, one row per series): slot, group, collection, licence_name, licence_url,
collection_doi, collection_page_url, collection_citation, tcia_citation, origin_country, stand_in, source_patient_id,
source_study_uid, source_series_uid, source_study_date, modality, body_part, series_description, role, source_sex,
source_age, expected_instances, instances (after the crop), bytes (zip), dcm_bytes, downloaded_at (from the log),
sha256 (of the zip), transfer_syntax, photometric, rows, columns, burned_in_annotation (the tag), burned_in
(yes / no / unknown), face_check_required, face_check_method, deface_check (pending / clear / cropped:<n>),
instances_removed, text_check, z_extent_mm, status, download_url, notes, raw_dir. `role` drives the planner
(mg, mr_breast, ct_chest, ct_cap_contrast, ct_cap, ct_cap_petct, ct_ap, ct_ap_coronal, ct_neck, ct_neck_lower,
ct_neck_coronal, mr_pelvis, mr_rectum, pt_wb, cr_chest).

## Licence duties (CC BY 3.0 and 4.0, TCIA policy)

1. Credit every collection with its full data citation and DOI, plus the TCIA paper (Clark et al. 2013), wherever the
   images are shown: the OHIF / PACS about page and the HIMS radiology module footer. Text: `ATTRIBUTION.txt` (short
   form; first line is the credit line) and `LICENCES.md` (full record). `manifest.CREDIT_LINE` is the one line footer.
2. State the changes (header rewritten, private tags removed, new UIDs, top slices removed in 9 series). Done in the
   about text and in every file's ImageComments ("Public de-identified research image from TCIA, relabelled for
   demonstration; see PACS about page").
3. No suggestion of endorsement; never try to re-identify anyone. Both are in the about text.
4. Acknowledgements the collection pages ask for: TCGA (TCGA-BRCA, TCGA-LUAD, TCGA-CESC, TCGA-READ, TCGA-COAD) and
   LIDC-IDRI; both are in LICENCES.md and ATTRIBUTION.txt.
5. Our own labelling rules: CMMD, Lung-PET-CT-Dx and StageII-Colorectal-CT are Chinese collections (tagged in the
   manifest notes); the head and neck series are stand-ins from patients without head and neck cancer, because every
   TCIA head and neck image collection is under NIH controlled access (plan section 0).

The about page text in LICENCES.md is section 5 of the plan, verbatim (a test checks it). The LIDC-IDRI and
CC-Tumor-Heterogeneity author lists were completed from their collection pages on 18 Oct; the Clark et al. author list
matches the TCIA policy page. Dashes inside citation titles are written as commas or colons (house style).

## Face check (privacy, our own step, not a licence condition)

Series that may reach the head (the plan's FACE CHECK slots, body part NECK / HEAD / WHOLEBODY, every PET and PET-CT,
and, wider than the plan, every CT that covers the chest or has no body part, and every chest radiograph) were
rendered: top 3 and bottom 3 slices, a mid slice, a mid sagittal reformat with z marks every 20 mm. The renders were
viewed one by one during the Phase 1 build. Rule: where the orbits, nose or mouth are in the field, every slice from the
top of the series down to just below the lowest teeth is removed from the extracted series (the zip keeps the original);
the PET of the same PET-CT is cut at the same level. A PET alone at PET resolution shows no recognisable face and is
left whole unless its CT was cut.

Result: 9 series cropped, 68 clear.

| Slot | Series | Removed | Why |
|---|---|---|---|
| HN-01 | CT NECK 3.0 | 56 (instances 1 to 56) | brain and orbit slices, plus 38 slices the submitter had already blanked over the nose and mouth |
| LU-01 | CT lung 3.0 B70f, PET WB | 17, 24 | nose and mouth at the top of the field |
| LU-03 | CTAC, WB MAC PET | 39, 39 | whole head in the field |
| LU-05 | Abd.CT 5.0 B30s, PET WB | 55, 55 | whole head in the field |
| LU-R1 (reserve) | CT Images, PET_BODY_CTAC | 29, 29 | whole head in the field |

Already safe at source: the FDG-PET-CT-Lesions series (HN-04, CUP-01, CUP-02) are defaced (head region emptied);
CPTAC and CC-Tumor-Heterogeneity removed the head slices of LU-04 and CX-04; the HN-01 coronal series has the head
region blacked out in every slice. A human confirmation pass on the cropped and head reaching series
(`qa/<series>/sheet.png`) is advised before the Phase 2 import.

Burned-in text: BurnedInAnnotation is NO or absent in all 77 series, and one mid slice of every series (all images of
the 2 to 4 image radiograph and mammogram series) shows no name, date or ID. The LIDC chest radiographs carry the lead
marker letters of the radiograph (laterality and technologist marker, for example LADC); they identify no patient and
stay (`burned_in = no` in the DICOM sense). Overlay planes are removed by the relabeller anyway.

## The assignment (assignment.json)

`plan_assignment(store_json_path, manifest_path)` reads every HIMS imaging study (accession, test key, modality,
patient sex and age, study date; cancelled studies skipped) and picks public series by test:

| HIMS test | Public series |
|---|---|
| mammogram | MG, women only |
| cect_chest_abdomen_pelvis, cect_tap | contrast CT chest to pelvis, else chest plus abdomen CT of one study, else CT chest, else the CT of a PET-CT |
| cect_abdomen_pelvis | CT abdomen and pelvis (with its coronal companion) |
| cect_face_neck | head and neck stand-in CT (true neck CT first, lower neck CT second) |
| chest_xray | LIDC-IDRI DX (PA and lateral) |
| mri_pelvis, mri_pelvis_rectum | pelvic MR (cervix collections), rectal protocol MR |
| pet_ct | whole-body PET with the CT of the same PET-CT |
| usg_*, bone_scan, mri_brain, mri_oral_cavity_neck | none in the library: stay synthetic |

Rules: a known source sex must equal the patient's; the patient's cancer group (from `his_mock/scenarios.json`, read
only, else from the orders) is preferred; every source series is used once; one source patient never serves two HIMS
patients (the permanent and temporary registrations of one person count as one patient, so they share a body); one
patient may get several source patients when one cannot cover all its studies. A local search maximises the number of
studies with public images first, then the fit. Deterministic.

Today (store of 14 Oct): 27 of 44 studies get public images. Synthetic: 6 ultrasounds, 2 bone scans, 3 brain MRIs,
1 oral cavity MRI (none in the library); 2 mammograms (4 mammogram source patients for 6 orders); 2 female chest
radiographs (2 female radiographs for 4 orders); 1 rectal MRI for a woman (2 rectal MR source patients: one is a man, the other serves the other woman). 15
source patients stay unused (mostly the female lung PET-CTs: every HIMS lung patient is a man); they are the reserve
for orders placed live at the HIMS desk. Images do not match the synthetic report text (different patients, some from
other cancer types); say so when demonstrating.

## Relabelling (relabel_series)

Per instance: PatientName, PatientID (UHID), IssuerOfPatientID, PatientBirthDate (from dob_iso, or from the age),
PatientSex, PatientAge rewritten; StudyInstanceUID, SeriesInstanceUID, SOPInstanceUID, FrameOfReferenceUID set with the
his_mock UID rules (2.25.<uuid5>, same namespace; a test checks they equal `his_mock.ids` / `dicom_studies`); every
other non-standard UID (references, vendor UIDs) mapped deterministically; StudyID, AccessionNumber, StudyDescription,
InstitutionName, InstitutionAddress, ReferringPhysicianName set; PerformingPhysicianName, OperatorsName, StationName,
DeviceSerialNumber and every nested person name blanked; all dates and times shifted by one offset so the study lands
on the HIMS date and time and intervals stay true (PET injection time included); ImageComments set to the provenance
note; DeidentificationMethod gets "Vaidyx demo relabel". Removed: private tags, overlays and curves, every (0010,xxxx)
not rewritten (OtherPatientIDs, PatientAddress, PatientTelephoneNumbers, EthnicGroup, PatientComments and the rest;
PatientWeight is kept, rounded, for PET only, for SUV display), clinical trial tags (0012, they hold the collection name
and TCIA patient ID), visit tags (0038), request and referenced patient / study sequences. Pixels and geometry are
unchanged; source instance numbers are kept (cropped series keep their gaps). Written as Explicit VR Little Endian (8
series are Implicit VR at source; none is compressed; a compressed series is decompressed, and one that cannot be is a
`RelabelError`: keep that study synthetic). `verify_relabelled` checks that no string element holds the source
PatientID, the collection name or an original UID, no private tag, no extra patient element, no date before 2020 except
the birth date, the identity, accession, Study UID, provenance note and unchanged pixels. A dry run relabelled and
verified all 77 series cleanly (output deleted; nothing went to Orthanc or data/his_mock).

## Phase 2 plug-in (not done in Phase 1)

An image source switch in `his_mock/dicom_studies.py`, `build_study` (called by `build_all` and by the desk when a
report is entered). Orthanc upload stays as it is (`upload_all` posts every `.dcm` under `dicom/<accession slug>/`).

```python
# his_mock/dicom_studies.py (sketch)
PUBLIC_ASSIGNMENT = Path(__file__).resolve().parent.parent / "pacs_public" / "assignment.json"
PUBLIC_MANIFEST = Path("/data/vaidyx/tb_resources/dicom_public/MANIFEST.json")

def public_entry(study):
    if not PUBLIC_ASSIGNMENT.exists():
        return None
    e = json.loads(PUBLIC_ASSIGNMENT.read_text()).get(study.get("accession"))
    return e if e and e.get("source_series_uid") else None

def build_study(store, study, dicom_dir, when=None):
    d = Path(dicom_dir) / study_dirname(study)
    ...                                              # clear d as today
    entry = public_entry(study)
    if entry:
        from pacs_public import relabel
        acc, patient = study_key(study), store.patients[study["patient_id"]]
        t0 = study_time(store, study)
        rows = {r["source_series_uid"]: r for r in relabel.load_manifest_rows(PUBLIC_MANIFEST)}
        identity = {"name": patient["name"], "uhid": patient["uhid"], "sex": patient.get("sex"),
                    "dob_iso": patient.get("dob_iso"), "issuer": INSTITUTION}
        uid_map, series, source_uids = {}, [], []
        try:
            for n, s in enumerate(entry["series"], start=1):
                res = relabel.relabel_series(
                    rows[s["source_series_uid"]]["raw_dir"], d, identity, study["study_uid"],
                    lambda k: series_uid(acc, k), lambda k, m: instance_uid(acc, k, m), acc, t0.date(),
                    t0.strftime("%H%M%S"), INSTITUTION, consultant_name_or_empty, study.get("description"),
                    series_number=n, institution_address=hospital_address, uid_map=uid_map)
                source_uids += res["source_uids"]
                series.append({"uid": res["series_uid"], "number": n, "modality": res["modality"],
                               "instances": [{"uid": u, "sop_class": c, "number": k} for u, c, k in
                                             zip(res["sop_uids"], res["sop_classes"], res["instance_numbers"])]})
            problems = relabel.verify_relabelled(d, {"source_patient_id": entry["source_patient_id"],
                                                     "collection": entry["collection"], "source_uids": source_uids,
                                                     "patient_id": patient["uhid"], "accession": acc,
                                                     "study_uid": study["study_uid"]})
            if problems:
                raise relabel.RelabelError("; ".join(problems[:5]))
        except relabel.RelabelError:
            ...                                      # clear d, fall back to the synthetic pattern, log it
        study["public_images"] = {"collection": entry["collection"], "slot": entry["slot"]}
    else:
        ...                                          # synthetic series as today
    ...                                              # same store fields: status registered, counts, series, path,
                                                     # orthanc_id (UHID | Study UID); upload_all unchanged
```

Notes for Phase 2: the store says CR for chest_xray while the public files are DX (keep the DICOM Modality and record
`res["modality"]` in the series); a live desk order with no assignment can rerun `plan_assignment` (deterministic; the
reserve source patients are free) or stay synthetic; add `manifest.CREDIT_LINE` to the HIMS radiology footer and the
PACS about page with `ATTRIBUTION.txt`; the Vaidyx-TB side keeps reading images only through the PACS proxy.
