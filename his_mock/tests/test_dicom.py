"""Unit tests for the mock PACS images (plan item V2-1.7): one synthetic DICOM study per imaging study, linked to its order
by Study UID and accession number. SYNTHETIC data only; builds into a temporary directory. The Orthanc tests run only when
Orthanc answers on 127.0.0.1:8042, and delete every study they uploaded (studies already there before are left alone)."""
import copy
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta

import pytest

pydicom = pytest.importorskip("pydicom")

from his_mock import dicom_studies, generator, ids, scenarios  # noqa: E402
from his_mock.ids import IST, parse_time  # noqa: E402
from his_mock.model import Store  # noqa: E402

ORTHANC = dicom_studies.ORTHANC_URL
EXPECTED_INSTANCES = {"CT": 8, "MR": 8, "CR": 1, "MG": 2, "US": 4, "PT": 6, "NM": 2}
SOP = {"CT": "1.2.840.10008.5.1.4.1.1.2", "MR": "1.2.840.10008.5.1.4.1.1.4", "CR": "1.2.840.10008.5.1.4.1.1.1",
       "MG": "1.2.840.10008.5.1.4.1.1.1.2", "US": "1.2.840.10008.5.1.4.1.1.6.1", "PT": "1.2.840.10008.5.1.4.1.1.128",
       "NM": "1.2.840.10008.5.1.4.1.1.20"}
UID_RE = re.compile(r"^2\.25\.[1-9]\d*$")


def _uid(text):
    return "2.25." + str(uuid.uuid5(ids.STUDY_UID_NAMESPACE, text).int)


@pytest.fixture(scope="module")
def fx():
    return scenarios.load()


@pytest.fixture(scope="module")
def built(tmp_path_factory, fx):
    out = tmp_path_factory.mktemp("his_mock_dicom")
    store = generator.build(out, fixtures=fx, documents=False, hl7=False, dicom=True)
    return out, store


@pytest.fixture(scope="module")
def store(built):
    return built[1]


@pytest.fixture(scope="module")
def dicom_dir(built):
    return built[0] / "dicom"


def live(store):
    return sorted((s for s in store.imaging_studies.values() if dicom_studies.performed(store, s)), key=lambda s: s["id"])


def read(path):
    return pydicom.dcmread(path)


# ------------------------------------------------------------------ files
def test_one_directory_per_study_with_designed_counts(store, dicom_dir):
    studies = live(store)
    assert len(studies) >= 30
    assert {p.name for p in dicom_dir.iterdir() if p.is_dir()} == {ids.slug(s["accession"]) for s in studies}
    for s in studies:
        files = sorted(p.name for p in (dicom_dir / ids.slug(s["accession"])).iterdir())
        n = EXPECTED_INSTANCES[s["modality"]]
        assert files == sorted(f"1-{k}.dcm" for k in range(1, n + 1)), s["id"]
    assert {s["modality"] for s in studies} == set(EXPECTED_INSTANCES)


def test_every_file_reads_back_linked_to_its_order(store, dicom_dir):
    for s in live(store):
        patient = store.patients[s["patient_id"]]
        order = store.orders[s["order_id"]]
        for f in sorted((dicom_dir / ids.slug(s["accession"])).glob("*.dcm")):
            ds = read(f)
            assert ds.file_meta.TransferSyntaxUID == "1.2.840.10008.1.2.1"
            assert ds.StudyInstanceUID == s["study_uid"] == ids.study_uid(order["accession"])
            assert ds.AccessionNumber == s["accession"] == order["accession"]
            assert ds.PatientID == patient["uhid"]          # a study under a temporary UHID keeps that UHID
            assert ids.PATTERNS["uhid"].match(ds.PatientID) or ids.PATTERNS["temporary_uhid"].match(ds.PatientID)
            assert "SYNTHETIC" in str(ds.PatientName) and "^" in str(ds.PatientName)
            assert ds.ImageComments == "SYNTHETIC image, no clinical content"
            assert ds.InstitutionName == "Vaidyx Demo Hospital (SYNTHETIC)" and ds.Manufacturer == "Vaidyx Synthetic"
            assert ds.PatientBirthDate == patient["dob_iso"].replace("-", "") and ds.PatientSex == patient["sex"]
            assert ds.StudyDescription == s["description"] and ds.Modality == s["modality"]
            assert ds.SOPClassUID == SOP[s["modality"]] == ds.file_meta.MediaStorageSOPClassUID
            assert ds.StudyID == "".join(c for c in s["accession"] if c.isdigit())
            assert ds.StudyDate == s["started"][:10].replace("-", "")
            arr = ds.pixel_array
            assert arr.shape == (ds.Rows, ds.Columns) and arr.std() > 0
            assert int(arr.max()) < (1 << ds.BitsStored)
            assert ds.PhotometricInterpretation == "MONOCHROME2"


def test_referring_physician_is_the_ordering_consultant(store, dicom_dir):
    for s in live(store):
        enc = store.encounters[store.orders[s["order_id"]]["encounter_id"]]
        ds = read(dicom_dir / ids.slug(s["accession"]) / "1-1.dcm")
        if enc.get("consultant_id"):
            surname = store.practitioners[enc["consultant_id"]]["name"].split()[-1]
            assert str(ds.ReferringPhysicianName).startswith(surname + "^"), s["id"]
            assert str(ds.ReferringPhysicianName).endswith("^^Dr")


def test_images_acquired_after_order_and_before_report(store, dicom_dir):
    for s in live(store):
        order = store.orders[s["order_id"]]
        ds = read(dicom_dir / ids.slug(s["accession"]) / "1-1.dcm")
        t = datetime.strptime(ds.StudyDate + ds.StudyTime, "%Y%m%d%H%M%S").replace(tzinfo=IST)
        assert t > parse_time(order["ordered_on"]), s["id"]
        rep = store.reports.get(order["report_id"]) if order["report_id"] else None
        if rep:
            assert t + timedelta(minutes=20) < parse_time(rep["versions"][0]["reported_on"]), s["id"]


def test_modality_specific_pixel_modules(store, dicom_dir):
    seen = set()
    for s in live(store):
        m = s["modality"]
        if m in seen:
            continue
        seen.add(m)
        ds = read(dicom_dir / ids.slug(s["accession"]) / "1-1.dcm")
        if m in ("CT", "MR", "PT", "NM"):
            assert ds.BitsAllocated == 16
        if m == "CT":
            assert ds.BitsStored == 12 and ds.RescaleIntercept == -1024 and ds.RescaleSlope == 1
        if m in ("CT", "MR"):
            assert (ds.Rows, ds.Columns) == (256, 256) and len(ds.ImagePositionPatient) == 3
            assert list(ds.ImageOrientationPatient) == [1, 0, 0, 0, 1, 0]
            assert ds.PixelSpacing and ds.SliceThickness and UID_RE.match(ds.FrameOfReferenceUID)
            assert ds.FrameOfReferenceUID == _uid(f"{s['accession']}|frame-of-reference")
        if m in ("CR", "MG"):
            assert (ds.Rows, ds.Columns) == (512, 512)
        if m == "US":
            assert (ds.Rows, ds.Columns) == (256, 256) and ds.BitsAllocated == 8
        assert "WindowCenter" in ds and "WindowWidth" in ds
    assert seen == set(EXPECTED_INSTANCES)


def test_slices_of_a_stack_differ_and_move(store, dicom_dir):
    ct = next(s for s in live(store) if s["modality"] == "CT")
    a = read(dicom_dir / ids.slug(ct["accession"]) / "1-1.dcm")
    b = read(dicom_dir / ids.slug(ct["accession"]) / "1-8.dcm")
    assert (a.pixel_array != b.pixel_array).any()
    assert a.ImagePositionPatient[2] != b.ImagePositionPatient[2]


# ------------------------------------------------------------------ UIDs
def test_uids_deterministic_and_unique(store, dicom_dir):
    all_uids = []
    for s in live(store):
        acc = s["accession"]
        for f in sorted((dicom_dir / ids.slug(acc)).glob("*.dcm")):
            series_no, inst_no = (int(x) for x in f.stem.split("-"))
            ds = read(f)
            assert ds.SeriesInstanceUID == _uid(f"{acc}|series|{series_no}")
            assert ds.SOPInstanceUID == _uid(f"{acc}|series|{series_no}|instance|{inst_no}")
            assert ds.SOPInstanceUID == ds.file_meta.MediaStorageSOPInstanceUID
            assert ds.SeriesNumber == series_no and ds.InstanceNumber == inst_no
            for u in (ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.SOPInstanceUID):
                assert UID_RE.match(u) and len(u) <= 64
            all_uids.append(ds.SOPInstanceUID)
        all_uids.append(_uid(f"{acc}|series|1"))
    study_uids = [s["study_uid"] for s in live(store)]
    assert len(set(study_uids)) == len(study_uids)
    assert len(set(all_uids)) == len(all_uids)
    assert not set(all_uids) & set(study_uids)


def test_rebuild_gives_byte_identical_files(tmp_path, fx, store, dicom_dir):
    generator.build(tmp_path, fixtures=fx, documents=False, hl7=False, dicom=True)
    other = tmp_path / "dicom"
    mine = sorted(p.relative_to(dicom_dir) for p in dicom_dir.rglob("*.dcm"))
    assert mine == sorted(p.relative_to(other) for p in other.rglob("*.dcm"))
    ct = next(s for s in live(store) if s["modality"] == "CT")
    mg = next(s for s in live(store) if s["modality"] == "MG")
    for rel in (f"{ids.slug(ct['accession'])}/1-5.dcm", f"{ids.slug(mg['accession'])}/1-2.dcm"):
        assert (dicom_dir / rel).read_bytes() == (other / rel).read_bytes(), rel
    digest = lambda d: hashlib.sha256(b"".join((d / r).read_bytes() for r in mine)).hexdigest()  # noqa: E731
    assert digest(dicom_dir) == digest(other)


def test_cancelled_study_has_no_directory(tmp_path, store):
    s2 = Store(copy.deepcopy(store.data))
    victim = live(s2)[0]
    stale = tmp_path / ids.slug(victim["accession"])
    stale.mkdir()
    (stale / "1-1.dcm").write_bytes(b"old")
    (tmp_path / "keep.txt").write_text("x")
    victim["status"] = "cancelled"
    n = dicom_studies.build_all(s2, tmp_path)
    assert n == len(live(s2)) == len(live(store)) - 1
    assert not stale.exists() and (tmp_path / "keep.txt").exists()
    assert victim["status"] == "cancelled"


def test_store_study_carries_series_counts_and_orthanc_id(built, store, fx):
    out, _ = built
    plain = generator.build_store(fx)[0]
    saved = Store.load(out / "store.json")
    for s in live(store):
        n = EXPECTED_INSTANCES[s["modality"]]
        assert s["status"] == "registered" and s["uploaded"] is False   # built; available once uploaded
        assert s["number_of_series"] == 1 and s["number_of_instances"] == n
        assert s["path"] == f"dicom/{ids.slug(s['accession'])}" and (out / s["path"]).is_dir()
        [series] = s["series"]
        assert series["uid"] == _uid(f"{s['accession']}|series|1") and series["number"] == 1
        assert series["modality"] == s["modality"]
        assert [i["number"] for i in series["instances"]] == list(range(1, n + 1))
        assert all(i["sop_class"] == SOP[s["modality"]] and UID_RE.match(i["uid"]) for i in series["instances"])
        uhid = store.patients[s["patient_id"]]["uhid"]
        h = hashlib.sha1(f"{uhid}|{s['study_uid']}".encode()).hexdigest()
        assert s["orthanc_id"] == "-".join(h[i:i + 8] for i in range(0, 40, 8))
        assert re.match(r"^[0-9a-f]{8}(-[0-9a-f]{8}){4}$", s["orthanc_id"])
        assert s["meta"] == plain.imaging_studies[s["id"]]["meta"]      # building images bumps nothing
        assert saved.imaging_studies[s["id"]] == s


def test_viewer_url_and_orthanc_id_helpers():
    uid = ids.study_uid("RAD/26/00981")
    assert dicom_studies.viewer_url(uid) == f"/ohif/viewer?StudyInstanceUIDs={uid}"
    assert dicom_studies.viewer_url(uid, base="/tb/pacs/ohif/") == f"/tb/pacs/ohif/viewer?StudyInstanceUIDs={uid}"
    oid = dicom_studies.orthanc_study_id("VXH/26/004201", uid)
    assert oid.replace("-", "") == hashlib.sha1(f"VXH/26/004201|{uid}".encode()).hexdigest()


def test_person_names():
    assert dicom_studies._person_name("Venkatesh Rao (SYNTHETIC)") == "Rao (SYNTHETIC)^Venkatesh"
    assert dicom_studies._person_name("Meena Kumari Joshi (SYNTHETIC)") == "Joshi (SYNTHETIC)^Meena Kumari"
    assert dicom_studies._person_name("Dr Arvind Menon", prefix="Dr") == "Menon^Arvind^^Dr"


def test_cli_build_on_a_data_dir(tmp_path, fx, capsys):
    generator.build(tmp_path, fixtures=fx, documents=False, hl7=False, dicom=False)
    assert all(s["status"] == "registered" for s in Store.load(tmp_path / "store.json").imaging_studies.values())
    assert dicom_studies.main(["--build", "--data", str(tmp_path)]) == 0
    assert "synthetic studies" in capsys.readouterr().out
    after = Store.load(tmp_path / "store.json")
    assert all(s["status"] == "registered" and s["series"] and s["orthanc_id"] for s in after.imaging_studies.values()
               if dicom_studies.performed(after, s))
    assert any(s["status"] == "registered" for s in after.imaging_studies.values())  # the scheduled, unperformed study
    with pytest.raises(SystemExit):
        dicom_studies.main(["--build", "--data", str(tmp_path / "data" / "tumour_board")])


# ------------------------------------------------------------------ Orthanc (only when it answers)
@pytest.fixture(scope="module")
def orthanc(store, dicom_dir):
    if not dicom_studies.orthanc_alive(ORTHANC):
        pytest.skip(f"Orthanc not answering at {ORTHANC}/system (start it with his_mock/orthanc.sh start)")
    before = set(json.loads(_get(f"{ORTHANC}/studies")))
    counts = dicom_studies.upload_all(store, dicom_dir, ORTHANC)
    yield counts, before
    for oid in counts["studies"]:
        if oid not in before:          # never delete a study that was there before this test (the real build)
            dicom_studies.delete_study(oid, ORTHANC)
    assert set(json.loads(_get(f"{ORTHANC}/studies"))) == before


def _get(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read()


def test_upload_all_counts_and_orthanc_ids(orthanc, store):
    counts, _ = orthanc
    studies = live(store)
    assert counts["failed"] == 0
    assert counts["files"] == counts["stored"] + counts["already_stored"] == sum(s["number_of_instances"] for s in studies)
    assert set(counts["studies"]) == {s["orthanc_id"] for s in studies}


def test_upload_is_idempotent(orthanc, store, dicom_dir):
    again = dicom_studies.upload_all(store, dicom_dir, ORTHANC)
    assert again["stored"] == 0 and again["failed"] == 0 and again["already_stored"] == again["files"]


def test_every_study_found_by_uid_and_accession(orthanc, store):
    for s in live(store):
        e = dicom_studies.find_study(s["study_uid"], ORTHANC)
        assert e, s["id"]
        assert e["00080050"]["Value"][0] == s["accession"]
        assert int(e["00201208"]["Value"][0]) == s["number_of_instances"]
        a = dicom_studies.find_by_accession(s["accession"], ORTHANC)
        assert a and a["0020000D"]["Value"][0] == s["study_uid"]
    assert dicom_studies.find_study(ids.study_uid("RAD/26/99999"), ORTHANC) is None
    assert dicom_studies.find_by_accession("RAD/26/99999", ORTHANC) is None


def test_verify_passes_and_catches_a_mismatch(orthanc, store):
    assert dicom_studies.verify(store, ORTHANC) == []
    s2 = Store(copy.deepcopy(store.data))
    victim = live(s2)[0]
    victim["number_of_instances"] += 1
    s2.imaging_studies[live(s2)[1]["id"]]["study_uid"] = ids.study_uid("RAD/26/99998")
    problems = dicom_studies.verify(s2, ORTHANC)
    assert len(problems) == 2 and any("instances" in p for p in problems) and any("not found" in p for p in problems)


def test_ohif_viewer_answers(orthanc, store):
    s = live(store)[0]
    body = _get(ORTHANC + dicom_studies.viewer_url(s["study_uid"])).decode("utf-8", "replace")
    assert "<html" in body.lower()
