"""Tests of the public-image library code with tiny synthetic DICOM made here (never a downloaded file).

    /data/vaidyx/venv/app/bin/python -m pytest pacs_public/tests -q
"""
import json
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian, RLELossless

from pacs_public import manifest as M
from pacs_public import qa_check as Q
from pacs_public import relabel as R

SRC_PID = "SYNTH-SRC-0042"
COLLECTION = "TCGA-FAKE"
ROOT = "1.3.6.1.4.1.99999.1"
ACC = "RAD/26/00981"
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)      # written as code points so this file holds neither
INSTITUTION = "Vaidyx Demo Hospital (SYNTHETIC)"
IDENTITY = {"name": "Anitha Reddy (SYNTHETIC)", "uhid": "VXH/26/004201", "sex": "F", "dob_iso": "1980-03-15"}


# ------------------------------------------------------------------------ synthetic series
def make_series(folder, n=3, modality="CT", implicit=False, rle=False, study_date="19600105", study_time="101500"):
    """n axial slices with the identifying clutter a public series can carry. Returns the source UIDs."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    study, series, frame = f"{ROOT}.10", f"{ROOT}.20", f"{ROOT}.30"
    sops = [f"{ROOT}.40.{k}" for k in range(1, n + 1)]
    sop_class = {"CT": "1.2.840.10008.5.1.4.1.1.2", "PT": "1.2.840.10008.5.1.4.1.1.128"}[modality]
    for k in range(1, n + 1):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = sop_class
        meta.MediaStorageSOPInstanceUID = sops[k - 1]
        meta.TransferSyntaxUID = ImplicitVRLittleEndian if implicit else ExplicitVRLittleEndian
        meta.ImplementationVersionName = "SRC_TOOL"
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SpecificCharacterSet = "ISO_IR 100"
        ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sops[k - 1]
        ds.PatientName, ds.PatientID = SRC_PID, SRC_PID
        ds.PatientBirthDate, ds.PatientSex, ds.PatientAge = "", "O", "061Y"
        ds.OtherPatientIDs = "OLD-ID-9"
        ds.PatientAddress = "1 Source Street"
        ds.PatientTelephoneNumbers = "555-0100"
        ds.EthnicGroup = "X"
        ds.PatientComments = "source comment"
        ds.PatientMotherBirthName = "Mother^Name"
        ds.PatientWeight = "70.4"
        ds.ClinicalTrialSponsorName = COLLECTION
        ds.ClinicalTrialProtocolID = COLLECTION
        ds.ClinicalTrialSubjectID = SRC_PID
        ds.PatientIdentityRemoved = "YES"
        ds.DeidentificationMethod = "Per DICOM PS 3.15 AnnexE"
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = study, series, frame
        ds.StudyDate, ds.StudyTime = study_date, study_time
        ds.SeriesDate, ds.SeriesTime = study_date, "102000"
        ds.AcquisitionDate, ds.AcquisitionTime = study_date, f"1021{k:02d}"
        ds.ContentDate, ds.ContentTime = study_date, f"1022{k:02d}.500000"
        ds.AccessionNumber, ds.StudyID = "9876543210", "S1"
        ds.StudyDescription = f"{COLLECTION} study"
        ds.SeriesDescription = "AXIAL 5.0"
        ds.InstitutionName, ds.InstitutionAddress = "Source Hospital", "Source Road"
        ds.ReferringPhysicianName, ds.PerformingPhysicianName = "Ref^Doc", "Perf^Doc"
        ds.OperatorsName, ds.StationName, ds.DeviceSerialNumber = "Op^One", "STATION7", "SN123"
        ds.Modality, ds.SeriesNumber, ds.InstanceNumber = modality, 3, k
        ds.ImagePositionPatient = [-100.0, -100.0, -5.0 * (k - 1)]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing, ds.SliceThickness = [0.8, 0.8], 5.0
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.Rows = ds.Columns = 16
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
        ds.RescaleIntercept, ds.RescaleSlope = -1024, 1
        ds.PixelData = (np.arange(256, dtype=np.uint16).reshape(16, 16) * k).tobytes()
        ds.add_new(0x00131010, "LO", COLLECTION)                     # TCIA CTP private block
        ds.add_new(0x00130010, "LO", "CTP")
        ds.add_new(0x60000010, "US", 16)                               # an overlay plane
        ref = Dataset()
        ref.ReferencedSOPClassUID = sop_class
        ref.ReferencedSOPInstanceUID = sops[0]
        other = Dataset()
        other.ReferencedSOPClassUID = sop_class
        other.ReferencedSOPInstanceUID = f"{ROOT}.99.1"                # outside this series
        ds.ReferencedImageSequence = Sequence([ref, other])
        rq = Dataset()
        rq.RequestedProcedureID = "RP77"
        ds.RequestAttributesSequence = Sequence([rq])
        if modality == "PT":
            rad = Dataset()
            rad.RadiopharmaceuticalStartTime = "091500"
            ds.RadiopharmaceuticalInformationSequence = Sequence([rad])
            ds.Units = "BQML"
        if rle:
            ds.compress(RLELossless)
        ds.save_as(folder / f"{k:08d}.dcm", implicit_vr=implicit, little_endian=True, enforce_file_format=True)
    return {"study": study, "series": series, "frame": frame, "sops": sops}


def relabel(src, out, **kw):
    args = dict(identity=IDENTITY, study_uid=R.study_uid(ACC), series_uid_fn=R.series_uid_fn_for(ACC),
                instance_uid_fn=R.instance_uid_fn_for(ACC), accession=ACC, study_date="2026-09-02",
                study_time="093000", institution=INSTITUTION, referring="Dr Arvind Menon",
                description="Bilateral mammogram")
    args.update(kw)
    return R.relabel_series(src, out, **args)


def expected_for(res, uids, **kw):
    e = {"source_patient_id": SRC_PID, "collection": COLLECTION,
         "source_uids": [uids["study"], uids["series"], uids["frame"], *uids["sops"]],
         "patient_id": IDENTITY["uhid"], "accession": ACC, "study_uid": R.study_uid(ACC),
         "instances": len(uids["sops"]), "pixel_sha256": res["pixel_sha256"]}
    e.update(kw)
    return e


# ------------------------------------------------------------------------ UIDs and names
def test_uid_conventions_match_his_mock():
    ids = pytest.importorskip("his_mock.ids")
    assert R.UID_NAMESPACE == ids.STUDY_UID_NAMESPACE
    assert R.study_uid(ACC) == ids.study_uid(ACC)
    assert R.slug(ACC) == ids.slug(ACC) == "rad-26-00981"
    try:
        from his_mock import dicom_studies as D
    except Exception:          # the other builder may be mid-edit; the ids check above still holds
        pytest.skip("his_mock.dicom_studies not importable right now")
    assert R.series_uid(ACC, 1) == D.series_uid(ACC, 1)
    assert R.instance_uid(ACC, 1, 7) == D.instance_uid(ACC, 1, 7)
    assert R.frame_of_reference_uid(ACC) == D.frame_of_reference_uid(ACC)
    assert R.person_name("Venkatesh Rao (SYNTHETIC)") == D._person_name("Venkatesh Rao (SYNTHETIC)")


def test_uids_are_short_and_valid():
    for u in (R.study_uid(ACC), R.series_uid(ACC, 1), R.instance_uid(ACC, 12, 999)):
        assert u.startswith("2.25.") and len(u) <= 64 and pydicom.uid.UID(u).is_valid


def test_person_name():
    assert R.person_name("Venkatesh Rao (SYNTHETIC)") == "Rao (SYNTHETIC)^Venkatesh"
    assert R.person_name("Dr Arvind Menon", prefix="Dr") == "Menon^Arvind^^Dr"
    assert R.person_name("Already^Done") == "Already^Done"


# ------------------------------------------------------------------------ relabel_series
@pytest.fixture
def ct(tmp_path):
    src = tmp_path / "src"
    uids = make_series(src, implicit=True)
    out = tmp_path / "out"
    return src, out, uids, relabel(src, out)


def test_relabel_identity_and_study(ct):
    src, out, uids, res = ct
    assert res["instances"] == 3 and len(res["files"]) == 3
    assert res["sop_classes"] == ["1.2.840.10008.5.1.4.1.1.2"] * 3 and res["modality"] == "CT"
    assert sorted(Path(f).name for f in res["files"]) == ["1-1.dcm", "1-2.dcm", "1-3.dcm"]
    ds = pydicom.dcmread(res["files"][0])
    assert str(ds.PatientName) == "Reddy (SYNTHETIC)^Anitha"
    assert ds.PatientID == "VXH/26/004201" and ds.IssuerOfPatientID == INSTITUTION
    assert ds.PatientBirthDate == "19800315" and ds.PatientSex == "F" and ds.PatientAge == "046Y"
    assert ds.AccessionNumber == ACC and ds.StudyID == "2600981"
    assert ds.StudyDescription == "Bilateral mammogram"
    assert ds.InstitutionName == INSTITUTION and ds.InstitutionAddress == ""
    assert str(ds.ReferringPhysicianName) == "Menon^Arvind^^Dr"
    for kw in ("PerformingPhysicianName", "OperatorsName", "StationName", "DeviceSerialNumber"):
        assert str(ds.get(kw, "")) == ""
    assert ds.ImageComments == R.IMAGE_COMMENTS
    assert ds.SeriesDescription == "AXIAL 5.0"       # kept
    assert ds.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
    assert R.DEID_NOTE in list(ds.DeidentificationMethod)


def test_relabel_uids_deterministic(ct, tmp_path):
    src, out, uids, res = ct
    ds = pydicom.dcmread(res["files"][1])
    assert ds.StudyInstanceUID == R.study_uid(ACC)
    assert ds.SeriesInstanceUID == res["series_uid"] == R.series_uid(ACC, 1)
    assert ds.SOPInstanceUID == R.instance_uid(ACC, 1, 2) == ds.file_meta.MediaStorageSOPInstanceUID
    assert ds.FrameOfReferenceUID == R.frame_of_reference_uid(ACC)
    again = relabel(src, tmp_path / "again")
    assert again["sop_uids"] == res["sop_uids"] and again["series_uid"] == res["series_uid"]
    # the reference to an instance of this series follows it; the outside one gets a deterministic new UID
    refs = [str(i.ReferencedSOPInstanceUID) for i in ds.ReferencedImageSequence]
    assert refs[0] == R.instance_uid(ACC, 1, 1)
    assert refs[1].startswith("2.25.") and refs[1] != f"{ROOT}.99.1"
    assert ds.ReferencedImageSequence[0].ReferencedSOPClassUID == "1.2.840.10008.5.1.4.1.1.2"


def test_relabel_series_number_option(tmp_path):
    src = tmp_path / "src"
    make_series(src)
    res = relabel(src, tmp_path / "out", series_number=2)
    ds = pydicom.dcmread(res["files"][0])
    assert ds.SeriesNumber == 2 and ds.SeriesInstanceUID == R.series_uid(ACC, 2)
    assert Path(res["files"][0]).name.startswith("2-")


def test_relabel_dates_move_together(ct):
    src, out, uids, res = ct
    ds = pydicom.dcmread(res["files"][2])
    assert (ds.StudyDate, ds.StudyTime) == ("20260902", "093000")
    assert ds.SeriesDate == ds.AcquisitionDate == ds.ContentDate == "20260902"
    assert ds.SeriesTime == "093500"                   # 10:20:00 was 5 minutes after 10:15:00
    assert ds.AcquisitionTime == "093603"
    assert ds.ContentTime == "093703.500000"           # precision kept


def test_relabel_removes_identifying_elements(ct):
    src, out, uids, res = ct
    ds = pydicom.dcmread(res["files"][0])
    for kw in ("OtherPatientIDs", "PatientAddress", "PatientTelephoneNumbers", "EthnicGroup", "PatientComments",
               "PatientMotherBirthName", "ClinicalTrialSponsorName", "ClinicalTrialProtocolID",
               "ClinicalTrialSubjectID", "RequestAttributesSequence"):
        assert kw not in ds, kw
    assert not any(el.tag.is_private for el in ds.iterall())
    assert not any(0x6000 <= el.tag.group <= 0x60FF for el in ds)
    assert "PatientWeight" not in ds                   # kept only for PET
    assert "ImplementationVersionName" not in ds.file_meta or ds.file_meta.ImplementationVersionName != "SRC_TOOL"
    assert any("PatientAddress" in t for t in res["removed_tags"])
    assert any("private" in t for t in res["removed_tags"])
    assert ds.PatientIdentityRemoved == "YES"


def test_relabel_keeps_pixels_and_geometry(ct):
    src, out, uids, res = ct
    for k, f in enumerate(sorted(res["files"]), start=1):
        new = pydicom.dcmread(f)
        old = pydicom.dcmread(next(Path(src).glob(f"{k:08d}.dcm")))
        assert np.array_equal(new.pixel_array, old.pixel_array)
        assert list(new.ImagePositionPatient) == list(old.ImagePositionPatient)
        assert list(new.PixelSpacing) == list(old.PixelSpacing)
        assert new.InstanceNumber == old.InstanceNumber


def test_verify_clean(ct):
    src, out, uids, res = ct
    assert R.verify_relabelled(out, expected_for(res, uids)) == []


def test_verify_finds_leaks(ct):
    src, out, uids, res = ct
    f = sorted(out.glob("*.dcm"))[0]
    ds = pydicom.dcmread(f)
    ds.StudyDescription = f"from {SRC_PID}"
    ds.SeriesDescription = COLLECTION.lower()
    ds.add_new(0x00091001, "LO", "vendor")
    ds.ReferencedImageSequence[0].ReferencedSOPInstanceUID = uids["sops"][0]
    ds.AcquisitionDate = "19991231"
    ds.save_as(f, enforce_file_format=True)
    problems = " | ".join(R.verify_relabelled(out, expected_for(res, uids)))
    for word in ("source PatientID", "collection name", "private tag", "original UID", "before 2020"):
        assert word in problems, word


def test_verify_counts_and_pixels(ct):
    src, out, uids, res = ct
    f = sorted(out.glob("*.dcm"))[0]
    ds = pydicom.dcmread(f)
    arr = ds.pixel_array.copy()
    arr[0, 0] += 1
    ds.PixelData = arr.tobytes()
    ds.save_as(f, enforce_file_format=True)
    problems = R.verify_relabelled(out, expected_for(res, uids, instances=4))
    assert any("pixel data changed" in p for p in problems)
    assert any("4" in p and "files" in p for p in problems)


def test_relabel_pet_keeps_decay_interval_and_weight(tmp_path):
    src = tmp_path / "pt"
    make_series(src, modality="PT", n=2)
    res = relabel(src, tmp_path / "out")
    ds = pydicom.dcmread(res["files"][0])
    assert ds.PatientWeight == 70                     # rounded, kept for SUV display
    # injection 09:15:00 and series 10:20:00 in the source: 65 minutes apart before and after
    assert ds.RadiopharmaceuticalInformationSequence[0].RadiopharmaceuticalStartTime == "083000"
    assert ds.SeriesTime == "093500"


def test_relabel_age_only_identity(tmp_path):
    src = tmp_path / "src"
    make_series(src, n=1)
    res = relabel(src, tmp_path / "out", identity={"name": "Ramesh Yadav (SYNTHETIC)", "uhid": "VXH/26/004205",
                                                    "sex": "M", "age": 49})
    ds = pydicom.dcmread(res["files"][0])
    assert ds.PatientAge == "049Y" and ds.PatientBirthDate == "19760903"


def test_relabel_decompresses_rle(tmp_path):
    src = tmp_path / "rle"
    make_series(src, n=2, rle=True)
    assert pydicom.dcmread(next(src.glob("*.dcm"))).file_meta.TransferSyntaxUID == RLELossless
    res = relabel(src, tmp_path / "out")
    ds = pydicom.dcmread(res["files"][1])
    assert ds.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
    assert np.array_equal(ds.pixel_array, np.arange(256, dtype=np.uint16).reshape(16, 16) * 2)


def test_relabel_undecodable_is_an_error(tmp_path, monkeypatch):
    src = tmp_path / "rle"
    make_series(src, n=1, rle=True)

    def broken(self, *a, **k):
        raise RuntimeError("no decoder")
    monkeypatch.setattr(pydicom.dataset.Dataset, "decompress", broken)
    with pytest.raises(R.RelabelError):
        relabel(src, tmp_path / "out")


def test_relabel_empty_folder(tmp_path):
    with pytest.raises(R.RelabelError):
        relabel(tmp_path, tmp_path / "out")


def test_relabel_renumbers_repeated_instance_numbers(tmp_path):
    src = tmp_path / "src"
    make_series(src, n=3)
    for f in src.glob("*.dcm"):
        ds = pydicom.dcmread(f)
        ds.InstanceNumber = 1
        ds.save_as(f, enforce_file_format=True)
    res = relabel(src, tmp_path / "out")
    assert res["renumbered"] and sorted(res["instance_numbers"]) == [1, 2, 3]
    assert len(set(res["sop_uids"])) == 3


def test_shift_dt_string():
    from datetime import timedelta
    assert R._shift_dt_string("19600105101500.25+0100", timedelta(days=1, minutes=30)) == "19600106104500.25+0100"
    assert R._shift_dt_string("1960", timedelta(days=400)) == "1961"
    assert R._shift_dt_string("garbage", timedelta(days=1)) is None


# ------------------------------------------------------------------------ assignment planner
def mrow(slot, group, collection, pid, study, series, modality, role, sex="F", age="050Y", desc=None, **kw):
    r = {"slot": slot, "group": group, "collection": collection, "source_patient_id": pid, "source_study_uid": study,
         "source_series_uid": series, "modality": modality, "role": role, "source_sex": sex, "source_age": age,
         "series_description": desc or role, "status": "downloaded", "instances": 10, "deface_check": "clear",
         "text_check": "pass", "burned_in": "no", "stand_in": group.startswith("E ")}
    r.update(kw)
    return r


def fake_manifest(path):
    rows = [
        mrow("BR-01", "A Breast", "CMMD", "MG1", "s-mg1", "x-mg1", "MG", "mg"),
        mrow("BR-02", "A Breast", "CMMD", "MG2", "s-mg2", "x-mg2", "MG", "mg"),
        mrow("BR-04", "A Breast", "CMB-BRCA", "BR4", "s-br4", "x-br4-mg", "MG", "mg", sex="O", age="000Y"),
        mrow("BR-04", "A Breast", "CMB-BRCA", "BR4", "s-br4", "x-br4-ct", "CT", "ct_chest", sex="O", age="000Y"),
        mrow("LU-05", "B Lung", "TCGA-LUAD", "LU5", "s-lu5a", "x-lu5-chest", "CT", "ct_chest", sex="M", age="070Y"),
        mrow("LU-05", "B Lung", "TCGA-LUAD", "LU5", "s-lu5b", "x-lu5-ctac", "CT", "ct_cap_petct", sex="M"),
        mrow("LU-05", "B Lung", "TCGA-LUAD", "LU5", "s-lu5b", "x-lu5-pt", "PT", "pt_wb", sex="M"),
        mrow("CX-01", "C Cervix", "TCGA-CESC", "CX1", "s-cx1", "x-cx1-t2", "MR", "mr_pelvis", sex=""),
        mrow("CX-01", "C Cervix", "TCGA-CESC", "CX1", "s-cx1", "x-cx1-t1", "MR", "mr_pelvis", sex=""),
        mrow("CR-02", "D Colorectal", "TCGA-READ", "CR2", "s-cr2", "x-cr2-ax", "CT", "ct_ap"),
        mrow("CR-02", "D Colorectal", "TCGA-READ", "CR2", "s-cr2", "x-cr2-cor", "CT", "ct_ap_coronal"),
        mrow("HN-01", "E Head and neck", "CPTAC-LUAD", "HN1", "s-hn1", "x-hn1", "CT", "ct_neck", sex="M",
             deface_check="cropped:56"),
        mrow("HN-09", "E Head and neck", "X", "HN9", "s-hn9", "x-hn9", "CT", "ct_neck", sex="M", deface_check="pending"),
        mrow("CUP-04", "F CUP", "CPTAC-PDA", "CUP4", "s-cup4", "x-cup4-ch", "CT", "ct_chest", sex="M"),
        mrow("CUP-04", "F CUP", "CPTAC-PDA", "CUP4", "s-cup4", "x-cup4-ab", "CT", "ct_ap", sex="M"),
        mrow("CUP-01", "F CUP", "FDG", "CUP1", "s-cup1", "x-cup1-ct", "CT", "ct_cap_contrast", sex="F"),
        mrow("CXR-01", "G Chest X-ray", "LIDC-IDRI", "CXRM", "s-cxrm", "x-cxrm", "DX", "cr_chest", sex="M"),
        mrow("CXR-04", "G Chest X-ray", "LIDC-IDRI", "CXRF", "s-cxrf", "x-cxrf", "DX", "cr_chest", sex="F"),
    ]
    Path(path).write_text(json.dumps({"series": rows}))
    return rows


def fake_store(path):
    pats = {
        "p1": dict(uhid="VXH/26/000001", name="Asha One (SYNTHETIC)", sex="F", age=46, dob_iso="1980-01-01"),
        "p2": dict(uhid="VXH/26/000002", name="Bina Two (SYNTHETIC)", sex="F", age=54, dob_iso="1972-01-01"),
        "p3": dict(uhid="VXH/26/000003", name="Chand Three (SYNTHETIC)", sex="M", age=66, dob_iso="1960-01-01"),
        "p4": dict(uhid="VXH/26/000004", name="Devi Four (SYNTHETIC)", sex="F", age=40, dob_iso="1986-01-01"),
        "p4t": dict(uhid="VXH/T/26/00001", name="Devi Four (SYNTHETIC)", sex="F", age=40, dob_iso="1986-01-01"),
        "p5": dict(uhid="VXH/26/000005", name="Esh Five (SYNTHETIC)", sex="M", age=50, dob_iso="1976-01-01"),
        "p6": dict(uhid="VXH/26/000006", name="Farid Six (SYNTHETIC)", sex="M", age=60, dob_iso="1966-01-01"),
        "p7": dict(uhid="VXH/26/000007", name="Gita Seven (SYNTHETIC)", sex="F", age=58, dob_iso="1968-01-01"),
    }
    plan = [  # (patient, accession, test, modality, department, status)
        ("p1", "RAD/26/00001", "mammogram", "MG", "Breast Surgery", "available"),
        ("p1", "RAD/26/00002", "usg_breast_axilla", "US", "Breast Surgery", "available"),
        ("p2", "RAD/26/00003", "mammogram", "MG", "Breast Surgery", "available"),
        ("p2", "RAD/26/00004", "cect_chest_abdomen_pelvis", "CT", "Breast Surgery", "available"),
        ("p2", "NM/26/00001", "bone_scan", "NM", "Breast Surgery", "available"),
        ("p3", "RAD/26/00005", "cect_tap", "CT", "Medical Oncology", "available"),
        ("p3", "NM/26/00002", "pet_ct", "PT", "Medical Oncology", "available"),
        ("p3", "RAD/26/00006", "mammogram", "MG", "Medical Oncology", "available"),
        ("p4", "RAD/26/00007", "mri_pelvis", "MR", "Gynaecologic Oncology", "available"),
        ("p4", "RAD/26/00008", "chest_xray", "CR", "Gynaecologic Oncology", "available"),
        ("p4t", "RAD/26/00009", "cect_abdomen_pelvis", "CT", "Gynaecologic Oncology", "available"),
        ("p5", "RAD/26/00010", "cect_face_neck", "CT", "ENT / Head and Neck Surgery", "available"),
        ("p5", "RAD/26/00011", "mri_oral_cavity_neck", "MR", "ENT / Head and Neck Surgery", "available"),
        ("p5", "RAD/26/00012", "chest_xray", "CR", "ENT / Head and Neck Surgery", "available"),
        ("p6", "RAD/26/00013", "cect_tap", "CT", "Medical Oncology", "available"),
        ("p7", "RAD/26/00014", "cect_tap", "CT", "Medical Oncology", "cancelled"),
        ("p7", "RAD/26/00015", "cect_tap", "CT", "Medical Oncology", "available"),
    ]
    store = {"patients": {k: dict(v, id=k) for k, v in pats.items()}, "orders": {}, "imaging_studies": {}}
    for i, (pid, acc, test, mod, dept, status) in enumerate(plan):
        oid = R.slug(acc)
        store["orders"][oid] = {"id": oid, "accession": acc, "test": test, "label": test.replace("_", " "),
                                "ordering_department": dept, "status": "completed"}
        store["imaging_studies"]["img-" + oid] = {"id": "img-" + oid, "order_id": oid, "accession": acc,
                                                  "patient_id": pid, "modality": mod, "status": status,
                                                  "started": f"2026-09-{i + 1:02d}"}
    Path(path).write_text(json.dumps(store))
    return store


@pytest.fixture
def plan(tmp_path):
    fake_manifest(tmp_path / "MANIFEST.json")
    fake_store(tmp_path / "store.json")
    out = tmp_path / "assignment.json"
    groups = {"VXH/26/000006": "cup"}
    rows = R.plan_assignment(tmp_path / "store.json", tmp_path / "MANIFEST.json", out_path=out, groups=groups)
    return rows, json.loads(out.read_text())


def by_acc(rows):
    return {r["accession"]: r for r in rows}


def test_plan_rules(plan):
    rows, out = plan
    assert R.check_assignment(rows) == []
    a = by_acc(rows)
    assert "RAD/26/00014" not in a                                    # cancelled study skipped
    assert a["RAD/26/00006"]["status"] == "synthetic"                 # no mammogram for a man
    assert "women only" in a["RAD/26/00006"]["reason"]
    for acc in ("RAD/26/00001", "RAD/26/00003"):
        assert a[acc]["status"] == "public" and a[acc]["series"][0]["role"] == "mg"
    assert a["RAD/26/00002"]["status"] == "synthetic" and "ultrasound" in a["RAD/26/00002"]["reason"]
    assert a["NM/26/00001"]["status"] == "synthetic" and "nuclear medicine" in a["NM/26/00001"]["reason"]
    assert a["RAD/26/00011"]["status"] == "synthetic" and "head and neck MRI" in a["RAD/26/00011"]["reason"]


def test_plan_modalities_and_sex(plan):
    rows, out = plan
    a = by_acc(rows)
    assert {s["role"] for s in a["RAD/26/00007"]["series"]} == {"mr_pelvis"}
    assert len(a["RAD/26/00007"]["series"]) == 2                      # every sequence of the MR exam
    assert a["RAD/26/00008"]["source_patient_id"] == "CXRF"           # the female radiograph for the woman
    assert a["RAD/26/00012"]["source_patient_id"] == "CXRM"
    assert a["RAD/26/00010"]["source_patient_id"] == "HN1"            # HN-09 is not face-checked: never used
    pet = {s["role"] for s in a["NM/26/00002"]["series"]}
    assert "pt_wb" in pet and a["NM/26/00002"]["source_patient_id"] == "LU5"
    assert a["RAD/26/00005"]["source_patient_id"] == "LU5"            # same body for the CT and the PET-CT
    assert {s["role"] for s in a["RAD/26/00004"]["series"]} <= {"ct_chest", "ct_cap_contrast", "ct_cap",
                                                               "ct_ap", "ct_cap_petct"}
    for r in rows:   # a known source sex always matches
        if r["status"] == "public" and r["source_patient_id"] in ("LU5", "HN1", "CXRM", "CUP4"):
            assert r["patient_sex"] == "M"


def test_plan_groups_and_duplicates(plan):
    rows, out = plan
    a = by_acc(rows)
    assert a["RAD/26/00013"]["source_patient_id"] == "CUP4"           # CUP patient: chest and abdomen CT
    assert {s["role"] for s in a["RAD/26/00013"]["series"]} == {"ct_chest", "ct_ap"}
    # the temporary registration of p4 is the same person: its CT may come from the same body or another one,
    # but no other person shares a source patient
    persons = {}
    for r in rows:
        if r["status"] == "public":
            persons.setdefault(r["source_patient_id"], set()).add(r["person"])
    assert all(len(v) == 1 for v in persons.values())
    assert a["RAD/26/00009"]["person"] == a["RAD/26/00007"]["person"]
    assert a["RAD/26/00009"]["status"] == "public" and a["RAD/26/00009"]["series"][0]["role"] == "ct_ap"
    assert {s["role"] for s in a["RAD/26/00009"]["series"]} == {"ct_ap", "ct_ap_coronal"}


def test_plan_file_shape(plan):
    rows, out = plan
    assert set(out) == {r["accession"] for r in rows}
    for acc, e in out.items():
        assert {"collection", "source_series_uid", "source_patient_id", "reason"} <= set(e)
        if e["source_series_uid"]:
            assert e["series"][0]["source_series_uid"] == e["source_series_uid"]
        else:
            assert e["reason"].startswith("stays synthetic")
    used = [s["source_series_uid"] for e in out.values() for s in e.get("series", [])]
    assert len(used) == len(set(used))


def test_plan_is_deterministic(tmp_path, plan):
    rows, out = plan
    again = R.plan_assignment(tmp_path / "store.json", tmp_path / "MANIFEST.json", out_path=None,
                              groups={"VXH/26/000006": "cup"})
    assert [(r["accession"], r.get("source_series_uid")) for r in again] == \
           [(r["accession"], r.get("source_series_uid")) for r in rows]


def test_check_assignment_catches_sharing():
    rows = [{"status": "public", "source_patient_id": "S1", "person": "a", "uhid": "A", "accession": "X1",
             "test": "mammogram", "patient_sex": "M", "series": [{"source_series_uid": "u1"}]},
            {"status": "public", "source_patient_id": "S1", "person": "b", "uhid": "B", "accession": "X2",
             "test": "cect_tap", "patient_sex": "F", "series": [{"source_series_uid": "u1"}]}]
    problems = " | ".join(R.check_assignment(rows))
    assert "serves" in problems and "used by" in problems and "mammogram for a M" in problems


# ------------------------------------------------------------------------ QA crop and manifest helpers
def test_qa_crop_and_results(tmp_path, monkeypatch):
    pick = {"slot": "LU-99", "group": "B Lung", "collection": "CMMD", "patient": SRC_PID, "study": "s", "n": 5,
            "series": f"{ROOT}.20", "modality": "CT", "bp": "CHEST", "desc": "test"}
    monkeypatch.setattr(M, "load_picks", lambda include_extra=True: [pick])
    folder = M.series_dir(tmp_path, pick)
    make_series(folder, n=5)                                          # z = 0, -5, -10, -15, -20
    (folder / ".complete").write_text("")
    decisions = {pick["series"]: {"face": "crop", "crop_from_z": -10.0, "text": "pass", "burned_in": "no",
                                  "note": "test"}}
    res = Q.apply_decisions(tmp_path, decisions)
    r = res[pick["series"]]
    assert r["deface_check"] == "cropped:3" and r["instances_removed"] == [1, 2, 3]
    assert len(list(folder.glob("*.dcm"))) == 2
    res2 = Q.apply_decisions(tmp_path, decisions)                     # idempotent
    assert res2[pick["series"]]["instances_removed"] == [1, 2, 3]
    rows = M.build_rows(tmp_path)
    assert rows[0]["deface_check"] == "cropped:3" and rows[0]["instances"] == 2 and rows[0]["burned_in"] == "no"
    assert "differs" not in rows[0]["notes"]                          # 2 kept + 3 removed = 5


def test_qa_render_writes_pngs(tmp_path, monkeypatch):
    pick = {"slot": "HN-99", "group": "E Head and neck", "collection": "FAKE", "patient": SRC_PID, "study": "s",
            "n": 25, "series": f"{ROOT}.20", "modality": "CT", "bp": "NECK", "desc": "test"}
    monkeypatch.setattr(M, "load_picks", lambda include_extra=True: [pick])
    folder = M.series_dir(tmp_path, pick)
    make_series(folder, n=25)
    (folder / ".complete").write_text("")
    idx = Q.render_all(tmp_path)
    r = idx[pick["series"]]
    assert len(r["face_pngs"]) == 6 and r["mid_png"] and r["reformat"] and Path(r["sheet"]).exists()
    names = sorted(Path(p).name for p in r["face_pngs"])
    assert names[0].startswith("bottom") and any(n.startswith("top1_i0001") for n in names)


def test_burned_in_value():
    assert M.burned_in_value("NO", "pass") == "no"
    assert M.burned_in_value("absent", "pass") == "no"
    assert M.burned_in_value("YES", "pass") == "yes"
    assert M.burned_in_value("NO", "fail") == "yes"
    assert M.burned_in_value("NO", "pending") == "unknown"


def test_licence_texts():
    md, att = M.licences_markdown({}), M.attribution_text()
    for text in (md, att):
        assert EM_DASH not in text and EN_DASH not in text
    for part in (M.SECTION5_ABOUT, M.SECTION5_SOURCES, M.SECTION5_LICENCES, M.SECTION5_CITATIONS, M.SECTION5_WHY):
        assert part in md
    assert M.CREDIT_LINE in att and M.TCIA_CITATION in att
    for name, v in M.COLLECTIONS.items():
        assert v["doi"] in md and v["doi"] in att and name in att


def test_section5_is_verbatim_from_the_plan():
    plan = Path(__file__).resolve().parents[2] / "docs" / "ui" / "build" / "pacs" / "tcia_plan.md"
    if not plan.exists():
        pytest.skip("plan document not present")
    text = plan.read_text()
    for part in (M.SECTION5_ABOUT, M.SECTION5_SOURCES, M.SECTION5_LICENCES, M.SECTION5_CITATIONS, M.SECTION5_WHY):
        assert part in text


def test_no_dashes_in_code_and_data():
    here = Path(__file__).resolve().parents[1]
    for f in list(here.glob("*.py")) + list(here.glob("*.json")) + list(here.glob("*.md")) + \
            list(here.glob("*.sh")) + list(here.glob("tests/*.py")):
        text = f.read_text(encoding="utf-8")
        assert EM_DASH not in text and EN_DASH not in text, f.name


def test_face_check_required():
    assert M.face_check_required({"slot": "HN-01", "bp": "NECK", "modality": "CT"})
    assert M.face_check_required({"slot": "X", "bp": "", "modality": "PT"})
    assert M.face_check_required({"slot": "X", "bp": "CHEST", "modality": "CT"})
    assert M.face_check_required({"slot": "X", "bp": "CHEST", "modality": "DX"})
    assert not M.face_check_required({"slot": "X", "bp": "BREAST", "modality": "MG"})
    assert not M.face_check_required({"slot": "X", "bp": "PELVIS", "modality": "MR"})
