"""The image source switch of the mock PACS (pacs_public phase 2): public library series relabelled with the HIMS identity
where the plan maps the accession, live picks for accessions the plan does not know, synthetic everywhere else, and the
quiet fallback when the library is missing. The "public library" here is a tiny synthetic one made in a temporary folder
(never a downloaded file); nothing reaches Orthanc."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

pydicom = pytest.importorskip("pydicom")

from pydicom.dataset import FileDataset, FileMetaDataset  # noqa: E402
from pydicom.uid import ExplicitVRLittleEndian  # noqa: E402

from his_mock import app as app_module  # noqa: E402
from his_mock import build, dicom_studies, fhir, generator, ids, scenarios, ui  # noqa: E402
from his_mock.eval import conformance  # noqa: E402
from his_mock.model import Store  # noqa: E402
from his_mock.tests import helpers  # noqa: E402
from pacs_public import relabel  # noqa: E402

ROOT_UID = "1.3.6.1.4.1.99999.7"
SOP = {"CT": "1.2.840.10008.5.1.4.1.1.2", "PT": "1.2.840.10008.5.1.4.1.1.128", "MG": "1.2.840.10008.5.1.4.1.1.1.2",
       "DX": "1.2.840.10008.5.1.4.1.1.1.1"}
CREDIT = "Images: tiny test library of synthetic stand-ins, CC BY 4.0, relabelled. Sources and citations: PACS about page."
LICENCES = ("# Licences of the tiny test library\n\nTest record, see https://doi.org/10.0000/test-alpha.\n\n"
            "## Collections\n\n- TESTCOLL-ALPHA: CC BY 4.0\n- <script>alert(1)</script>\n\n### Notes\n\nA **bold** word.\n")
# source patient -> (sex, group, collection, [(study, series key, modality, role, instances, description)])
SOURCES = {
    "SRC-A": ("F", "A Breast", "TESTCOLL-ALPHA", [("sa", "a-mg", "MG", "mg", 2, "MG views"),
                                                 ("sa", "a-ct", "CT", "ct_cap_contrast", 3, "CT body contrast")]),
    "SRC-B": ("M", "B Lung", "TESTCOLL-BETA", [("sb", "b-pt", "PT", "pt_wb", 3, "PET WB"),
                                              ("sb", "b-ct", "CT", "ct_cap_petct", 3, "CTAC")]),
    "SRC-C": ("M", "G Chest X-ray", "TESTCOLL-GAMMA", [("sc", "c-dx", "DX", "cr_chest", 1, "PA chest")]),
    "SRC-D": ("F", "D Colorectal", "TESTCOLL-DELTA", [("sd", "d-ch", "CT", "ct_chest", 2, "Thorax"),
                                                     ("sd", "d-ap", "CT", "ct_ap", 2, "Abdomen")]),
}
UNIQUE = {"SRC-A": 1, "SRC-B": 2, "SRC-C": 3, "SRC-D": 4}


def suid(*parts):
    return ".".join([ROOT_UID] + [str(p) for p in parts])


def series_key_uid(key):
    return suid(9, int(hashlib.sha1(key.encode()).hexdigest()[:8], 16))


def make_series(folder, pid, sex, collection, study, key, modality, n, desc):
    """n source images with the identifying clutter a public series can carry (source name and ID, trial tags, a
    private block, an old date)."""
    folder.mkdir(parents=True, exist_ok=True)
    u = UNIQUE[pid]
    study_uid, series_uid = suid(u, 1, sum(map(ord, study))), series_key_uid(key)
    frame = suid(u, 3, sum(map(ord, study)))           # one frame of reference per source study
    for k in range(1, n + 1):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = SOP[modality]
        meta.MediaStorageSOPInstanceUID = series_uid + f".{k}"
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID, ds.SOPInstanceUID = SOP[modality], series_uid + f".{k}"
        ds.PatientName, ds.PatientID, ds.PatientSex, ds.PatientAge = pid, pid, sex, "050Y"
        ds.OtherPatientIDs = pid + "-OLD"
        ds.ClinicalTrialProtocolID = collection
        ds.add_new(0x00130010, "LO", "CTP")
        ds.add_new(0x00131010, "LO", collection)
        ds.StudyInstanceUID, ds.SeriesInstanceUID = study_uid, series_uid
        ds.StudyDate, ds.StudyTime = "20110304", "101500"
        ds.SeriesDate, ds.SeriesTime = "20110304", "102000"
        ds.AccessionNumber, ds.StudyID = "SRC123", "S1"
        ds.StudyDescription, ds.SeriesDescription = "source study", desc
        ds.InstitutionName, ds.ReferringPhysicianName = "Source Hospital", "Source^Doctor"
        ds.Modality, ds.SeriesNumber, ds.InstanceNumber = modality, 5, k
        if modality in ("CT", "PT"):
            ds.FrameOfReferenceUID = frame
            ds.ImagePositionPatient = [-8.0, -8.0, -5.0 * (k - 1)]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.SliceThickness = 5.0
        ds.PixelSpacing = [1.0, 1.0]
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.Rows = ds.Columns = 16
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
        ds.PixelData = (np.arange(256, dtype=np.uint16).reshape(16, 16) * (k + u)).tobytes()
        ds.save_as(folder / f"{k:08d}.dcm", implicit_vr=False, little_endian=True, enforce_file_format=True)
    return study_uid, series_uid


def make_library(root):
    """MANIFEST.json, raw/<collection>/<series uid>/*.dcm, ATTRIBUTION.txt, LICENCES.md. Returns {series key: row}."""
    root = Path(root)
    rows, by_key = [], {}
    for pid, (sex, group, collection, series) in SOURCES.items():
        for study, key, modality, role, n, desc in series:
            src_study, src_series = make_series(root / "_tmp" / key, pid, sex, collection, study, key, modality, n, desc)
            raw = root / "raw" / collection / src_series
            raw.parent.mkdir(parents=True, exist_ok=True)
            (root / "_tmp" / key).rename(raw)
            row = {"slot": pid.replace("SRC-", "T-"), "group": group, "collection": collection,
                   "licence_name": "Creative Commons Attribution 4.0 International License",
                   "licence_url": "https://creativecommons.org/licenses/by/4.0/",
                   "collection_doi": f"https://doi.org/10.0000/{collection.lower()}", "source_patient_id": pid,
                   "source_study_uid": src_study, "source_series_uid": src_series, "modality": modality, "role": role,
                   "source_sex": sex, "source_age": "050Y", "series_description": desc, "status": "downloaded",
                   "instances": n, "deface_check": "clear", "text_check": "pass", "burned_in": "no",
                   "stand_in": False, "raw_dir": str(raw)}
            rows.append(row)
            by_key[key] = row
    (root / "_tmp").rmdir()
    (root / "MANIFEST.json").write_text(json.dumps({"series": rows}))
    (root / "ATTRIBUTION.txt").write_text(CREDIT + "\n\nLonger text.\n")
    (root / "LICENCES.md").write_text(LICENCES)
    return by_key


def plan_entry(rows):
    prim = rows[0]
    return {"collection": prim["collection"], "source_series_uid": prim["source_series_uid"],
            "source_patient_id": prim["source_patient_id"], "slot": prim["slot"], "reason": "test plan",
            "source_study_uid": prim["source_study_uid"],
            "series": [{"source_series_uid": r["source_series_uid"], "role": r["role"], "modality": r["modality"],
                        "series_description": r["series_description"], "instances": r["instances"],
                        "deface_check": "clear"} for r in rows]}


@pytest.fixture(scope="module")
def fx():
    return scenarios.load()


@pytest.fixture(scope="module")
def lib_files(tmp_path_factory):
    root = tmp_path_factory.mktemp("public_lib")
    rows = make_library(root / "library")
    plan = {"RAD/26/00983": plan_entry([rows["a-mg"]]),                       # mammogram, F 004202
            "NM/26/00154": plan_entry([rows["b-pt"], rows["b-ct"]]),           # PET-CT, M 004213
            "RAD/26/00982": {"collection": None, "source_series_uid": None, "source_patient_id": None,
                             "reason": "stays synthetic: no ultrasound series in the public library"}}
    (root / "assignment.json").write_text(json.dumps(plan))
    return root, rows


def library(lib_files, live_name="live.json"):
    root, _ = lib_files
    live = root / live_name
    if live.exists():
        live.unlink()
    return dicom_studies.PublicLibrary(root / "library", root / "assignment.json", live)


@pytest.fixture(scope="module")
def built(tmp_path_factory, fx, lib_files):
    out = tmp_path_factory.mktemp("his_public")
    store = generator.build(out, fixtures=fx, documents=False, hl7=False, dicom=False)
    lib = library(lib_files)
    n = dicom_studies.build_all(store, out / "dicom", source="public", library=lib)
    store.save(out / "store.json", out / "events.jsonl")
    return out, store, lib, n


def study(store, acc):
    return next(s for s in store.imaging_studies.values() if s["accession"] == acc)


def src_of(store, acc):
    return study(store, acc).get("image_source") or {}


# ------------------------------------------------------------------ the switch
def test_planned_studies_get_public_images(built, lib_files):
    out, store, lib, n = built
    _, rows = lib_files
    mg = src_of(store, "RAD/26/00983")
    assert mg["kind"] == "public" and mg["assignment"] == "planned" and mg["verified"] is True
    assert mg["collection"] == "TESTCOLL-ALPHA" and mg["source_series_uid"] == rows["a-mg"]["source_series_uid"]
    assert mg["licence"].startswith("Creative Commons Attribution 4.0") and mg["doi"] == "https://doi.org/10.0000/testcoll-alpha"
    pet = study(store, "NM/26/00154")
    assert pet["image_source"]["kind"] == "public" and pet["number_of_series"] == 2 and pet["number_of_instances"] == 6
    assert [s["modality"] for s in pet["series"]] == ["PT", "CT"]
    assert pet["image_source"]["source_series_uids"] == [rows["b-pt"]["source_series_uid"], rows["b-ct"]["source_series_uid"]]
    files = sorted(p.name for p in (out / "dicom" / "nm-26-00154").glob("*.dcm"))
    assert files == ["1-1.dcm", "1-2.dcm", "1-3.dcm", "2-1.dcm", "2-2.dcm", "2-3.dcm"]
    assert store.meta["image_source"] == "public"
    assert n == sum(1 for s in store.imaging_studies.values() if dicom_studies.performed(store, s))


def test_relabelled_files_carry_the_hims_identity(built, lib_files):
    out, store, lib, _ = built
    _, rows = lib_files
    s = study(store, "NM/26/00154")
    acc, patient = s["accession"], store.patients[s["patient_id"]]
    t0 = dicom_studies.study_time(store, s)
    order = store.orders[s["order_id"]]
    cid = store.encounters[order["encounter_id"]].get("consultant_id")
    referring = dicom_studies._person_name(store.practitioners[cid]["name"], prefix="Dr") if cid else ""
    for f in sorted((out / "dicom" / ids.slug(acc)).glob("*.dcm")):
        series_no, inst_no = (int(x) for x in f.stem.split("-"))
        ds = pydicom.dcmread(f)
        assert ds.PatientID == patient["uhid"] and str(ds.PatientName) == dicom_studies._person_name(patient["name"])
        assert ds.PatientSex == patient["sex"] and ds.PatientBirthDate == patient["dob_iso"].replace("-", "")
        assert ds.StudyInstanceUID == ids.study_uid(acc) == s["study_uid"]
        assert ds.SeriesInstanceUID == dicom_studies.series_uid(acc, series_no)
        assert ds.SOPInstanceUID == dicom_studies.instance_uid(acc, series_no, inst_no)
        assert ds.AccessionNumber == acc and ds.StudyDescription == s["description"]
        assert ds.InstitutionName == dicom_studies.INSTITUTION
        assert str(ds.ReferringPhysicianName) == referring
        assert ds.StudyDate == t0.strftime("%Y%m%d") and ds.StudyTime == t0.strftime("%H%M%S")
        assert ds.ImageComments == relabel.IMAGE_COMMENTS
        text = str(ds)
        assert "SRC-B" not in text and "TESTCOLL-BETA" not in text and "Source Hospital" not in text
        key = "b-pt" if series_no == 1 else "b-ct"
        src = pydicom.dcmread(sorted(Path(rows[key]["raw_dir"]).glob("*.dcm"))[inst_no - 1])
        assert ds.PixelData == src.PixelData and ds.Modality == src.Modality
    pt = pydicom.dcmread(out / "dicom" / "nm-26-00154" / "1-1.dcm")
    ct = pydicom.dcmread(out / "dicom" / "nm-26-00154" / "2-1.dcm")
    assert pt.FrameOfReferenceUID == ct.FrameOfReferenceUID == dicom_studies.frame_of_reference_uid(acc)  # one source frame


def test_verify_relabelled_is_clean_on_the_built_study(built, lib_files):
    out, store, _, _ = built
    _, rows = lib_files
    s = study(store, "RAD/26/00983")
    src = rows["a-mg"]
    source_uids = [src["source_study_uid"], src["source_series_uid"]] + \
        [str(pydicom.dcmread(p).SOPInstanceUID) for p in sorted(Path(src["raw_dir"]).glob("*.dcm"))]
    expected = {"source_patient_id": "SRC-A", "collection": "TESTCOLL-ALPHA", "source_uids": source_uids,
                "patient_id": store.patients[s["patient_id"]]["uhid"], "accession": s["accession"],
                "study_uid": s["study_uid"], "instances": 2}
    assert relabel.verify_relabelled(out / "dicom" / ids.slug(s["accession"]), expected) == []
    assert relabel.verify_relabelled(out / "dicom" / ids.slug(s["accession"]), dict(expected, accession="X")) != []


def test_unplanned_studies_get_live_picks_or_stay_synthetic(built, lib_files):
    _, store, lib, _ = built
    _, rows = lib_files
    same_person = src_of(store, "RAD/26/00985")       # CT CAP of 004202: her own source patient (SRC-A) is preferred
    assert same_person["kind"] == "public" and same_person["assignment"] == "live"
    assert same_person["source_series_uid"] == rows["a-ct"]["source_series_uid"]
    other = src_of(store, "RAD/26/00989")              # CT CAP of 004204: SRC-A serves 004202, so SRC-D
    assert other["kind"] == "public" and other["collection"] == "TESTCOLL-DELTA"
    assert study(store, "RAD/26/00989")["number_of_series"] == 2
    cxr = study(store, "RAD/26/00992")                 # chest radiograph of a man: the male DX source
    assert cxr["image_source"]["collection"] == "TESTCOLL-GAMMA" and cxr["series"][0]["modality"] == "DX"
    assert cxr["modality"] == "CR"                     # the store keeps the order's modality
    for acc, why in (("RAD/26/00994", "another study or patient"),    # SRC-C already serves 004206
                     ("RAD/26/00996", "suits a female patient"),      # a woman: the only DX source is a man
                     ("RAD/26/01006", "another study or patient"),    # SRC-B's CT serves the planned PET-CT
                     ("RAD/26/00981", "another study or patient"),    # the only MG source serves 004202
                     ("RAD/26/00990", "no public series in the library fits"),   # no neck CT in the tiny library
                     ("RAD/26/00982", "no ultrasound"),               # the plan says synthetic
                     ("NM/26/00151", "bone scan")):
        src = src_of(store, acc)
        assert src["kind"] == "synthetic" and why in src["reason"], (acc, src)
        assert study(store, acc)["series"][0]["instances"][0]["sop_class"] == dicom_studies.SPECS[study(store, acc)["modality"]]["sop"]


def test_live_picks_are_recorded_and_never_share_a_source_patient(built):
    _, store, lib, _ = built
    live = lib.live()
    planned = lib.plan()
    assert set(live) & set(planned) == set()
    assert {a for a, e in live.items() if e["source_series_uid"]} == {"RAD/26/00985", "RAD/26/00989", "RAD/26/00992"}
    for acc, e in live.items():
        s = study(store, acc)
        assert e["uhid"] == store.patients[s["patient_id"]]["uhid"] and e["test"] == store.orders[s["order_id"]]["test"]
        assert e["store_built_at"] == store.meta["built_at"] and e["reason"]
    owner, used = {}, set()
    for acc, e in list(planned.items()) + list(live.items()):
        if not e.get("source_series_uid"):
            continue
        person = relabel._person_key(store.patients[study(store, acc)["patient_id"]])
        assert owner.setdefault(e["source_patient_id"], person) == person, acc
        for s in e["series"]:
            assert s["source_series_uid"] not in used, acc
            used.add(s["source_series_uid"])
    text = lib.live_path.read_text()
    assert chr(0x2014) not in text and chr(0x2013) not in text           # no em or en dash


def test_rebuild_reuses_live_picks_and_gives_identical_files(built, tmp_path):
    out, store, lib, _ = built
    before = lib.live_path.read_text()
    s2 = Store(copy.deepcopy(store.data))
    dicom_studies.build_all(s2, tmp_path / "dicom", library=lib)        # no source: the store's choice (public)
    assert lib.live_path.read_text() == before
    for acc in ("RAD/26/00983", "NM/26/00154", "RAD/26/00985", "RAD/26/00982"):
        mine = out / "dicom" / ids.slug(acc)
        other = tmp_path / "dicom" / ids.slug(acc)
        names = sorted(p.name for p in mine.glob("*.dcm"))
        assert names == sorted(p.name for p in other.glob("*.dcm"))
        assert all((mine / n).read_bytes() == (other / n).read_bytes() for n in names), acc
        assert study(s2, acc)["image_source"] == study(store, acc)["image_source"]


def test_a_new_store_repicks_stale_live_entries(built, tmp_path):
    _, store, lib, _ = built
    s2 = Store(copy.deepcopy(store.data))
    s2.meta["built_at"] = "2026-10-19T08:00:00+05:30"                 # a rebuilt HIMS store
    st = study(s2, "RAD/26/00994")                                      # synthetic before: SRC-C served 004206
    st["series"] = []
    old = lib.live()
    dicom_studies.build_study(s2, st, tmp_path, library=lib)
    entry = lib.live()["RAD/26/00994"]
    assert entry["store_built_at"] == "2026-10-19T08:00:00+05:30"
    assert entry["source_patient_id"] == "SRC-C"                       # the old picks belong to the old store
    assert st["image_source"]["kind"] == "public"
    lib.save_live(old)


def test_desk_build_follows_the_store_choice(built, tmp_path):
    """A study reported live at the desk: build_study without a source uses store.meta.image_source."""
    _, store, lib, _ = built
    s2 = Store(copy.deepcopy(store.data))
    base = study(s2, "RAD/26/00992")
    acc = "RAD/26/09001"
    oid, sid = ids.order_id(acc), ids.imaging_study_id(acc)
    s2.orders[oid] = dict(copy.deepcopy(s2.orders[base["order_id"]]), id=oid, accession=acc, imaging_study_id=sid,
                          report_id=None)
    s2.imaging_studies[sid] = {k: v for k, v in copy.deepcopy(base).items() if k not in ("series", "image_source")}
    s2.imaging_studies[sid].update(id=sid, order_id=oid, accession=acc, study_uid=ids.study_uid(acc))
    new = s2.imaging_studies[sid]
    dicom_studies.build_study(s2, new, tmp_path, when=s2.now(), library=lib)
    assert new["image_source"]["kind"] == "synthetic"                  # SRC-C's only series is taken
    assert "another study or patient" in new["image_source"]["reason"]
    assert lib.live()[acc]["uhid"] == s2.patients[new["patient_id"]]["uhid"]
    s2.meta["image_source"] = "synthetic"
    dicom_studies.build_study(s2, new, tmp_path, library=lib)
    assert new["image_source"] == {"kind": "synthetic"}
    live = lib.live()
    live.pop(acc)
    lib.save_live(live)


def test_fhir_imaging_study_of_public_images_conforms(built):
    _, store, _, _ = built
    for acc in ("NM/26/00154", "RAD/26/00992"):
        s = study(store, acc)
        res = fhir.imaging_study(store, s)
        assert res["numberOfSeries"] == len(res["series"]) == s["number_of_series"]
        assert res["numberOfInstances"] == s["number_of_instances"]
        problems = []
        conformance._imaging_study(res, problems.append)
        assert problems == []


# ------------------------------------------------------------------ fallbacks
def test_default_build_stays_synthetic_even_with_a_library(tmp_path, fx, lib_files, monkeypatch):
    monkeypatch.delenv(dicom_studies.IMAGES_ENV, raising=False)
    store = generator.build(tmp_path, fixtures=fx, documents=False, hl7=False, dicom=False)
    dicom_studies.build_all(store, tmp_path / "dicom", library=library(lib_files, "live2.json"))
    assert "image_source" not in store.meta
    assert all(s["image_source"] == {"kind": "synthetic"} for s in store.imaging_studies.values() if s.get("series"))
    assert not (lib_files[0] / "live2.json").exists()


def test_missing_library_falls_back_quietly(tmp_path, fx, lib_files):
    store = generator.build(tmp_path / "a", fixtures=fx, documents=False, hl7=False, dicom=False)
    gone = dicom_studies.PublicLibrary(tmp_path / "no-library", lib_files[0] / "assignment.json", tmp_path / "live.json")
    dicom_studies.build_all(store, tmp_path / "a" / "dicom", source="public", library=gone)
    srcs = [s["image_source"] for s in store.imaging_studies.values() if s.get("series")]
    assert srcs and all(x == {"kind": "synthetic", "reason": "public image library not installed"} for x in srcs)
    assert store.meta["image_source"] == "public" and not (tmp_path / "live.json").exists()
    plain = generator.build(tmp_path / "b", fixtures=fx, documents=False, hl7=False, dicom=True)
    a, b = tmp_path / "a" / "dicom", tmp_path / "b" / "dicom"
    names = sorted(p.relative_to(a) for p in a.rglob("*.dcm"))
    assert names == sorted(p.relative_to(b) for p in b.rglob("*.dcm"))
    assert all((a / n).read_bytes() == (b / n).read_bytes() for n in names)
    assert all(s["number_of_instances"] == p["number_of_instances"] for s, p in
               zip(sorted(store.imaging_studies.values(), key=lambda s: s["id"]),
                   sorted(plain.imaging_studies.values(), key=lambda s: s["id"])))


def test_a_broken_source_series_falls_back_to_synthetic(tmp_path, fx, lib_files):
    root = tmp_path / "lib"
    rows = make_library(root)
    bad = Path(rows["a-mg"]["raw_dir"])
    sorted(bad.glob("*.dcm"))[1].write_bytes(b"not a dicom file at all")
    (tmp_path / "plan.json").write_text(json.dumps({"RAD/26/00983": plan_entry([rows["a-mg"]])}))
    lib = dicom_studies.PublicLibrary(root, tmp_path / "plan.json", tmp_path / "live.json")
    store = generator.build(tmp_path / "h", fixtures=fx, documents=False, hl7=False, dicom=False)
    s = study(store, "RAD/26/00983")
    dicom_studies.build_study(store, s, tmp_path / "dicom", source="public", library=lib)
    assert s["image_source"]["kind"] == "synthetic" and s["image_source"]["reason"].startswith("public series not used")
    files = sorted((tmp_path / "dicom" / "rad-26-00983").glob("*.dcm"))
    assert [f.name for f in files] == ["1-1.dcm", "1-2.dcm"]
    assert all(pydicom.dcmread(f).ImageComments == dicom_studies.IMAGE_COMMENTS for f in files)
    assert dicom_studies.image_counts(store)["fallback"][0][0] == "RAD/26/00983"


def test_a_stale_plan_never_gives_a_mammogram_to_a_man(tmp_path, fx, lib_files):
    store = generator.build(tmp_path, fixtures=fx, documents=False, hl7=False, dicom=False)
    lib = library(lib_files, "live3.json")
    s = study(store, "RAD/26/00983")
    store.patients[s["patient_id"]]["sex"] = "M"
    dicom_studies.build_study(store, s, tmp_path / "dicom", source="public", library=lib)
    assert s["image_source"]["kind"] == "synthetic" and "sex" in s["image_source"]["reason"]
    cxr = study(store, "RAD/26/00992")
    plan = lib.plan()
    lib2 = dicom_studies.PublicLibrary(lib.root, tmp_path / "plan.json", tmp_path / "live.json")
    (tmp_path / "plan.json").write_text(json.dumps({"RAD/26/00992": plan["RAD/26/00983"]}))     # MG for a radiograph
    dicom_studies.build_study(store, cxr, tmp_path / "dicom", source="public", library=lib2)
    assert cxr["image_source"]["kind"] == "synthetic" and "do not fit" in cxr["image_source"]["reason"]


def test_env_overrides_the_store_choice(tmp_path, fx, lib_files, monkeypatch):
    store = generator.build(tmp_path, fixtures=fx, documents=False, hl7=False, dicom=False)
    store.meta["image_source"] = "public"
    monkeypatch.setenv(dicom_studies.IMAGES_ENV, "synthetic")
    s = study(store, "RAD/26/00983")
    dicom_studies.build_study(store, s, tmp_path / "dicom", library=library(lib_files, "live4.json"))
    assert s["image_source"] == {"kind": "synthetic"}
    monkeypatch.setenv(dicom_studies.IMAGES_ENV, "bogus")
    with pytest.raises(ValueError):
        dicom_studies.image_mode(store)


# ------------------------------------------------------------------ the build CLI flag
def test_build_cli_images_flag(tmp_path, lib_files, monkeypatch, capsys):
    root, _ = lib_files
    monkeypatch.delenv(dicom_studies.IMAGES_ENV, raising=False)
    monkeypatch.setattr(ui, "PUBLIC_LIBRARY", root / "library")
    monkeypatch.setattr(dicom_studies, "PUBLIC_ASSIGNMENT", root / "assignment.json")
    monkeypatch.setattr(dicom_studies, "LIVE_ASSIGNMENT", tmp_path / "live.json")
    assert build.main(["--out", str(tmp_path / "s"), "--no-pdf", "--no-hl7", "--images", "synthetic"]) == 0
    out = capsys.readouterr().out
    assert "(0 with public library images" in out and "password" in out and "VXH" not in out
    assert Store.load(tmp_path / "s" / "store.json").meta["image_source"] == "synthetic"
    assert build.main(["--out", str(tmp_path / "p"), "--no-pdf", "--no-hl7"]) == 0       # default: public
    out = capsys.readouterr().out
    saved = Store.load(tmp_path / "p" / "store.json")
    n = sum(1 for s in saved.imaging_studies.values() if (s.get("image_source") or {}).get("kind") == "public")
    assert saved.meta["image_source"] == "public" and n == 5 and f"({n} with public library images" in out
    assert (tmp_path / "p" / dicom_studies.LIVE_NAME).exists()          # a data dir other than data/his_mock: its own
    assert not (tmp_path / "live.json").exists()


def test_live_picks_file_belongs_to_the_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dicom_studies, "REPO", tmp_path)
    monkeypatch.setenv("TB_HIS_MOCK_DATA", str(tmp_path / "copy"))          # a throw-away copy still keeps its own
    demo = tmp_path / "data" / "his_mock" / "dicom"
    assert dicom_studies.PublicLibrary.for_dicom(demo).live_path == dicom_studies.LIVE_ASSIGNMENT
    other = dicom_studies.PublicLibrary.for_dicom(tmp_path / "copy" / "dicom")
    assert other.live_path == (tmp_path / "copy" / dicom_studies.LIVE_NAME).resolve()


def test_dicom_studies_cli_images_flag(tmp_path, fx, lib_files, monkeypatch, capsys):
    root, _ = lib_files
    monkeypatch.delenv(dicom_studies.IMAGES_ENV, raising=False)
    monkeypatch.setattr(ui, "PUBLIC_LIBRARY", root / "library")
    monkeypatch.setattr(dicom_studies, "PUBLIC_ASSIGNMENT", root / "assignment.json")
    monkeypatch.setattr(dicom_studies, "LIVE_ASSIGNMENT", tmp_path / "live.json")
    generator.build(tmp_path, fixtures=fx, documents=False, hl7=False, dicom=False)
    assert dicom_studies.main(["--build", "--data", str(tmp_path), "--images", "public"]) == 0
    assert (tmp_path / dicom_studies.LIVE_NAME).exists()
    assert "5 with public library images" in capsys.readouterr().out
    assert dicom_studies.main(["--build", "--data", str(tmp_path)]) == 0           # the store's choice is kept
    assert "5 with public library images" in capsys.readouterr().out


# ------------------------------------------------------------------ Orthanc: an older build is replaced
def test_upload_replaces_an_older_copy(built, monkeypatch):
    _, store, _, _ = built
    s2 = Store(copy.deepcopy(store.data))
    st = study(s2, "RAD/26/00983")
    calls = []
    held = [{"MainDicomTags": {"SOPInstanceUID": i["uid"]}} for i in st["series"][0]["instances"]]

    def fake(url, data=None, method=None, headers=None, timeout=30):
        calls.append((method or "GET", url.split("8042", 1)[1]))
        if url.endswith("/instances") and method is None:
            return held
        if method == "DELETE":
            return {}
        return {"Status": "Success", "ParentStudy": st["orthanc_id"]}
    monkeypatch.setattr(dicom_studies, "_request", fake)
    d = built[0] / "dicom"
    c = dicom_studies.upload_all(s2, d, studies=[st])
    assert c["replaced"] == 0 and c["stored"] == 2 and not any(m == "DELETE" for m, _ in calls)
    held.append({"MainDicomTags": {"SOPInstanceUID": dicom_studies.instance_uid("RAD/26/00983", 1, 8)}})  # synthetic leftover
    calls.clear()
    c = dicom_studies.upload_all(s2, d, studies=[st])
    assert c["replaced"] == 1 and ("DELETE", f"/studies/{st['orthanc_id']}") in calls
    assert calls.index(("DELETE", f"/studies/{st['orthanc_id']}")) < [m for m, _ in calls].index("POST")


# ------------------------------------------------------------------ credit line and the PACS about page
@pytest.fixture
def screen_app(built, lib_files, monkeypatch):
    root, _ = lib_files
    monkeypatch.setattr(ui, "PUBLIC_LIBRARY", root / "library")
    return app_module.create_app(built[0])          # ensures the 9 demo logins in the temporary build


def test_about_page_shows_credit_studies_and_licences(screen_app):
    c = helpers.login(screen_app, "radiologist")
    r = c.get("/his/about/images")
    assert r.status_code == 200
    helpers.clean(r.text)
    assert ui.credit_html(CREDIT) in r.text and '<a href="/his/about/images">PACS about page</a>' in r.text
    assert "<b>5 of" in r.text and "TESTCOLL-ALPHA" in r.text and "https://doi.org/10.0000/testcoll-delta" in r.text
    assert "<h2>Licences of the tiny test library</h2>" in r.text and "<b>bold</b>" in r.text
    assert '<a href="https://doi.org/10.0000/test-alpha" rel="noopener noreferrer" target=_blank>' in r.text
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    assert ui.credit_html(CREDIT) in r.text.split("<footer>", 1)[1]          # the footer of every page


def test_about_page_needs_a_login(screen_app):
    from fastapi.testclient import TestClient
    r = TestClient(screen_app).get("/his/about/images", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/his/login")


def test_radiology_footer_and_study_panel_show_the_source(screen_app):
    c = helpers.login(screen_app, "radiologist")
    r = c.get("/his/radiology?tab=signed")
    assert r.status_code == 200 and 'id=image-credit' in r.text
    assert "5 of " in r.text and "imaging studies show public dataset images" in r.text
    order = study(screen_app.state.hospital.store, "NM/26/00154")["order_id"]
    page = c.get(f"/his/radiology/orders/{order}").text
    assert "Public research images, TESTCOLL-BETA (CC BY 4.0), relabelled for this demo" in page
    synth = study(screen_app.state.hospital.store, "RAD/26/00982")["order_id"]
    assert "Synthetic test pattern, no clinical content" in c.get(f"/his/radiology/orders/{synth}").text


def test_without_the_library_no_credit_is_shown(screen_app, tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "PUBLIC_LIBRARY", tmp_path / "none")
    c = helpers.login(screen_app, "radiologist")
    r = c.get("/his/about/images")
    assert r.status_code == 200 and "not installed on this server" in r.text and "id=licences" not in r.text
    assert "Sources and citations" not in r.text.split("<footer>", 1)[1]
    assert ui.image_credit() == ""
