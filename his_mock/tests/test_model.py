"""Unit tests for the mock hospital's data model (plan item V2-1.1): transitions, lifecycle, lookups, persistence.
SYNTHETIC data only; a small hand-made hospital, no fixtures, no network."""
import json
import re

import pytest

from his_mock import ids
from his_mock.model import LifecycleError, Store

HOSPITAL = {"name": "Vaidyx Demo Hospital (SYNTHETIC)", "ncg_level": "optimal", "pmjay_empanelled": True,
            "fetch_window_months": 12, "surgical_oncology_list": ["Surgical Oncology"], "board_heads": ["Radiology"],
            "today": "2026-10-13"}
BLOCK = re.compile(r"^Digitally signed by (.+), (.+), Reg\. No\. (VXREG-\d{5}), (\d{2}/\d{2}/\d{4} \d{2}:\d{2}), "
                   r"Vaidyx Demo CA, certificate serial (VXDCA-[0-9A-F]{8})$")


class Clock:
    def __init__(self, t="2026-10-13T10:00:00+05:30"):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def h(clock):
    """A tiny hospital: four departments, five doctors, five tests, one patient with an OP visit."""
    s = Store.empty(HOSPITAL, seed=7, fixture_version="test", built_at="2026-10-13T00:00:00+05:30", clock=clock)
    for name, code, group in (("Radiology", "RAD", "supporting"), ("Pathology", "PATH", "supporting"),
                              ("Breast Surgery", "BS", "treating"), ("Medical Oncology", "MO", "treating")):
        s.add_department(name, code, group)
    s.add_practitioner("Dr Test Radiologist", "MD (Radiodiagnosis)", "VXREG-29001", "Radiology", "VXDCA-0000A001")
    s.add_practitioner("Dr Test Resident", "MBBS, Junior Resident (Radiodiagnosis)", "VXREG-29002", "Radiology",
                       "VXDCA-0000A002")
    s.add_practitioner("Dr Test Pathologist", "MD (Pathology)", "VXREG-29003", "Pathology", "VXDCA-0000A003")
    s.add_practitioner("Dr Test Surgeon", "MS (General Surgery), MCh (Breast Surgery)", "VXREG-29004", "Breast Surgery",
                       "VXDCA-0000A004")
    s.add_test("mammogram", "Bilateral mammogram", "mammogram", "Radiology")
    s.add_test("cect_tap", "CECT thorax, abdomen and pelvis", "ct", "Radiology")
    s.add_test("hpe_biopsy", "Histopathology report (biopsy)", "histopathology", "Pathology")
    s.add_test("cbc", "Complete blood count", "lab", "Pathology")
    s.add_test("opd_note", "OPD consultation note", "clinical_note", "any_treating")
    s.register_patient("Test Patient (SYNTHETIC)", "F", 50, uhid="VXH/26/009001", dob="1976-01-01",
                       abha={"number": "99-2600-0000-9001", "address": "test.patient@sbx"}, when="2026-09-01T08:30:00+05:30")
    s.open_visit("vxh-26-009001", "Breast Surgery", op_no="OP/26/190001", consultant_id="prac-vxreg-29004",
                 when="2026-09-01T09:00:00+05:30")
    return s


def _order(h, test="cect_tap", when="2026-09-01T09:30:00+05:30", **kw):
    return h.place_order("vxh-26-009001", "op-26-190001", test, "Breast Surgery", ordered_on=when, **kw)


# ------------------------------------------------------------------ registration and identifiers
def test_empty_store_has_every_table_and_marker(h):
    for t in ("departments", "practitioners", "tests", "patients", "encounters", "orders", "specimens", "reports",
              "signatures", "imaging_studies", "events"):
        assert t in h.data
    assert h.meta["marker"] == h.hospital["marker"] == "SYNTHETIC"
    assert h.meta["schema_version"] == 1 and h.hospital["timezone"] == "+05:30"


def test_register_allocates_uhid_and_requires_synthetic_name(h, clock):
    clock.t = "2026-10-01T09:00:00+05:30"
    p = h.register_patient("New Person (SYNTHETIC)", "M", 40)
    assert ids.PATTERNS["uhid"].match(p["uhid"]) and p["id"] == ids.slug(p["uhid"])
    t = h.register_patient("New Person (SYNTHETIC)", "M", 40, kind="temporary")
    assert t["uhid"].startswith("VXH/T/26/") and ids.PATTERNS["temporary_uhid"].match(t["uhid"])
    assert p["registered_on"] == "2026-10-01" and p["meta"] == {"versionId": "1", "lastUpdated": "2026-10-01T09:00:00+05:30"}
    with pytest.raises(ValueError):
        h.register_patient("Real Looking Name", "M", 40)
    with pytest.raises(ValueError):
        h.register_patient("Other (SYNTHETIC)", "M", 40, kind="temporary", abha={"number": "99-2600-0000-9999"})
    with pytest.raises(LifecycleError):
        h.register_patient("Test Patient (SYNTHETIC)", "F", 50, uhid="VXH/26/009001")


def test_patient_dob_display_and_iso(h):
    p = h.patients["vxh-26-009001"]
    assert p["dob"] == "01/01/1976" and p["dob_iso"] == "1976-01-01"


def test_patient_by_identifier_resolves_uhid_op_and_abha(h):
    assert h.patient_by_identifier("VXH/26/009001")["id"] == "vxh-26-009001"
    assert h.patient_by_identifier(" vxh/26/009001 ")["id"] == "vxh-26-009001"
    assert h.patient_by_identifier("OP/26/190001")["id"] == "vxh-26-009001"
    assert h.patient_by_identifier("99-2600-0000-9001")["id"] == "vxh-26-009001"
    assert h.patient_by_identifier("test.patient@sbx")["id"] == "vxh-26-009001"
    assert h.patient_by_identifier("VXH/26/999999") is None and h.patient_by_identifier("") is None


def test_patients_by_name_ignores_case_and_marker(h):
    h.register_patient("Test Patient (SYNTHETIC)", "F", 52, uhid="VXH/26/009002", when="2026-09-02T08:00:00+05:30")
    assert len(h.patients_by_name("test patient")) == 2
    assert [p["uhid"] for p in h.patients_by_name("TEST PATIENT (SYNTHETIC)", sex="F", age=50)] == ["VXH/26/009001"]
    assert len(h.patients_by_name("Test Patient", sex="F", age=50, tolerance=2)) == 2
    assert h.patients_by_name("Test Patient", sex="M") == []
    assert h.similar_registrations("vxh-26-009001") == []


def test_similar_registrations_same_name_sex_age(h):
    h.register_patient("Test Patient (SYNTHETIC)", "F", 50, uhid="VXH/T/26/09001", kind="temporary",
                       when="2026-08-01T08:00:00+05:30")
    assert [p["id"] for p in h.similar_registrations("vxh-26-009001")] == ["vxh-t-26-09001"]
    assert [p["id"] for p in h.similar_registrations("vxh-t-26-09001")] == ["vxh-26-009001"]


# ------------------------------------------------------------------ encounters
def test_open_visit_allocates_op_no(h):
    e = h.open_visit("vxh-26-009001", "Medical Oncology", when="2026-09-05T09:00:00+05:30")
    assert ids.PATTERNS["op_no"].match(e["number"]) and e["class"] == "AMB" and e["date"] == "2026-09-05"
    assert e["number"] == "OP/26/190002"  # after the given OP/26/190001


def test_admit_transfer_discharge(h):
    e = h.admit("vxh-26-009001", "Breast Surgery", "Surgical Ward 1", "1-01", ip_no="IP/26/09001",
                when="2026-09-10T10:00:00+05:30", pmjay_preauth={"status": "approved", "date": "2026-09-08"})
    assert e["status"] == "in-progress" and e["class"] == "IMP" and e["pmjay_preauth"] == {"status": "approved",
                                                                                          "date": "2026-09-08"}
    h.transfer_ward("ip-26-09001", "High Dependency Unit", "HDU-01", "Observation", when="2026-09-11T22:00:00+05:30")
    assert (e["ward"], e["bed"]) == ("High Dependency Unit", "HDU-01") and len(e["ward_history"]) == 2
    assert e["ward_history"][0]["bed"] == "1-01" and e["ward_history"][1]["reason"] == "Observation"
    h.discharge("ip-26-09001", when="2026-09-14T18:00:00+05:30")
    assert e["status"] == "finished" and e["discharged"] == "2026-09-14" and e["meta"]["versionId"] == "3"
    assert [ev["trigger"] for ev in h.events[-3:]] == ["A01", "A02", "A03"]
    with pytest.raises(LifecycleError):
        h.transfer_ward("ip-26-09001", "Ward", "1", when="2026-09-15T10:00:00+05:30")
    with pytest.raises(LifecycleError):
        h.discharge("op-26-190001")


def test_referral_requested_then_accepted(h):
    h.admit("vxh-26-009001", "Medical Oncology", "MO Ward", "MO-1", when="2026-09-10T10:00:00+05:30")
    eid = ids.encounter_id(next(e["number"] for e in h.encounters.values() if e["kind"] == "IP"))
    ref = h.refer(eid, "Medical Oncology", "Breast Surgery", "Breast lump", when="2026-09-11T10:00:00+05:30")
    assert ref["status"] == "requested" and ref["on"] == "2026-09-11"
    assert h.events[-1]["kind"] == "REF" and h.events[-1]["trigger"] == "I12"
    h.accept_referral(eid, "Breast Surgery", when="2026-09-11T15:00:00+05:30")
    assert ref["status"] == "accepted" and h.events[-1]["trigger"] == "I13"
    with pytest.raises(LifecycleError):
        h.accept_referral(eid, "Breast Surgery")
    with pytest.raises(LifecycleError):
        h.refer(eid, "Medical Oncology", "Medical Oncology", "same")


# ------------------------------------------------------------------ orders
def test_place_order_allocates_accession_per_department(h):
    a = _order(h)
    b = _order(h, "cbc")
    assert a["accession"] == "RAD/26/00001" and b["accession"] == "PATH/26/00001"
    assert a["id"] == "rad-26-00001" and a["status"] == "ordered" and a["performing_department"] == "Radiology"
    assert h.events[-1]["kind"] == "ORM" and h.events[-1]["status"] == "O" and h.events[-1]["order_status"] == "IP"


def test_allocation_never_collides_with_existing_accessions(h):
    _order(h, accession="RAD/26/00981")
    c = _order(h)
    assert c["accession"] == "RAD/26/00982"
    with pytest.raises(LifecycleError):
        _order(h, accession="RAD/26/00981")
    with pytest.raises(ValueError):
        _order(h, accession="RAD-26-1")


def test_clinical_note_order_has_no_accession(h):
    o = h.place_order("vxh-26-009001", "op-26-190001", "opd_note", "Breast Surgery")
    assert o["accession"] is None and o["id"].startswith("ord-") and o["performing_department"] == "Breast Surgery"
    o2 = h.place_order("vxh-26-009001", "op-26-190001", "opd_note", "Breast Surgery", order_id="ord-x-1")
    assert o2["id"] == "ord-x-1"


def test_order_on_another_patients_encounter_is_refused(h):
    h.register_patient("Other (SYNTHETIC)", "M", 30, uhid="VXH/26/009009", when="2026-09-01T08:00:00+05:30")
    with pytest.raises(LifecycleError):
        h.place_order("vxh-26-009009", "op-26-190001", "cbc", "Breast Surgery")
    with pytest.raises(LifecycleError):
        _order(h, "no_such_test")


def test_schedule_creates_imaging_study_with_valid_uid(h):
    o = _order(h)
    h.schedule(o["id"], "2026-09-02", when="2026-09-01T09:45:00+05:30")
    st = h.imaging_study_for(o["id"])
    assert o["status"] == "scheduled" and o["scheduled_for"] == "2026-09-02"
    assert st["study_uid"] == ids.study_uid("RAD/26/00001") and re.match(r"^2\.25\.\d+$", st["study_uid"])
    assert len(st["study_uid"]) <= 64 and st["modality"] == "CT" and st["status"] == "registered"
    assert st["accession"] == o["accession"] and st["started"] == "2026-09-02"
    assert h.events[-1]["status"] == "S" and h.events[-1]["order_status"] == "SC"


def test_collect_sample_creates_specimen(h):
    o = _order(h, "hpe_biopsy")
    sp = h.collect_sample(o["id"], block_no="PATH/26/00001-A1", when="2026-09-01T10:00:00+05:30")
    assert ids.PATTERNS["sample_barcode"].match(sp["barcode"]) and sp["barcode"] == "VXS26000001"
    assert sp["type"] == "tissue" and o["status"] == "sample_collected" and o["specimen_id"] == sp["id"]
    assert h.events[-1]["status"] == "I"
    with pytest.raises(LifecycleError):
        h.collect_sample(o["id"])
    blood = h.collect_sample(_order(h, "cbc")["id"], when="2026-09-01T10:05:00+05:30")
    assert blood["type"] == "blood" and blood["barcode"] == "VXS26000002"


# ------------------------------------------------------------------ reports, signatures, lifecycle
def test_preliminary_then_sign_final(h, clock):
    o = _order(h)
    h.schedule(o["id"], "2026-09-02", when="2026-09-01T10:00:00+05:30")
    r = h.report_preliminary(o["id"], "prac-vxreg-29002", {"lesion_size": "4.8 x 3.6 cm"}, report_id="rep-x",
                             when="2026-09-02T20:15:00+05:30")
    assert r["status"] == "preliminary" and r["current_version"] == 1 and r["versions"][0]["signature_id"] is None
    assert o["status"] == "completed" and h.events[-1]["status"] == "P"
    assert not [s for s in h.signatures.values() if s["report_id"] == "rep-x"]
    assert h.pending_for_department("Radiology")["reports"] == [r]
    before = r["meta"]["lastUpdated"]
    clock.t = "2026-10-13T11:05:00+05:30"
    h.sign_final("rep-x", "VXREG-29001")
    assert r["status"] == "final" and r["current_version"] == 2
    assert [v["status"] for v in r["versions"]] == ["preliminary", "final"]
    assert r["versions"][1]["values"] == {"lesion_size": "4.8 x 3.6 cm"}
    sig = h.signatures["sig-rep-x-v2"]
    assert sig["block"] == ("Digitally signed by Dr Test Radiologist, MD (Radiodiagnosis), Reg. No. VXREG-29001, "
                            "13/10/2026 11:05, Vaidyx Demo CA, certificate serial VXDCA-0000A001")
    assert BLOCK.match(sig["block"]) and sig["ca"] == "Vaidyx Demo CA" and sig["verification_status"] == "verified"
    assert h.events[-1]["kind"] == "ORU" and h.events[-1]["status"] == "F" and h.events[-1]["refs"]["version"] == 2
    assert r["meta"]["lastUpdated"] == "2026-10-13T11:05:00+05:30" and int(r["meta"]["versionId"]) == 2
    assert h.reports_for(since=before) == [r]
    assert h.reports_for(since=r["meta"]["lastUpdated"]) == []
    assert h.pending_for_department("Radiology")["reports"] == []


def test_junior_resident_cannot_sign(h):
    o = _order(h)
    h.report_preliminary(o["id"], "prac-vxreg-29002", {"a": "1"}, when="2026-09-02T20:15:00+05:30")
    with pytest.raises(LifecycleError):
        h.sign_final(o["id"], "prac-vxreg-29002", when="2026-09-03T10:00:00+05:30")


def test_sign_final_directly_creates_version_one(h):
    o = _order(h, "cbc")
    r = h.sign_final(o["id"], "prac-vxreg-29003", values={"haemoglobin": "12.1 gm%"}, when="2026-09-01T11:20:00+05:30")
    assert r["id"] == "rep-path-26-00001" and r["current_version"] == 1 and r["status"] == "final"
    assert r["versions"][0]["signature_id"] == "sig-rep-path-26-00001-v1" and r["meta"]["versionId"] == "1"
    with pytest.raises(LifecycleError):
        h.sign_final(r["id"], "prac-vxreg-29003")
    with pytest.raises(LifecycleError):
        h.report_preliminary(o["id"], "prac-vxreg-29003", {})


def test_unsigned_final_has_no_signature(h):
    o = _order(h, "hpe_biopsy")
    r = h.sign_final(o["id"], "prac-vxreg-29003", values={"grade": "G2"}, apply_signature=False,
                     when="2026-09-03T17:30:00+05:30")
    assert r["status"] == "final" and r["versions"][0]["signature_id"] is None and not h.signatures


def test_amend_keeps_earlier_versions(h):
    o = _order(h, "hpe_biopsy")
    h.sign_final(o["id"], "prac-vxreg-29003", values={"her2": "2+ (Equivocal)"}, report_id="r1",
                 when="2026-09-03T14:10:00+05:30")
    r = h.amend("r1", "prac-vxreg-29003", {"her2": "3+ (Positive)"}, "Addendum: re-scored",
                when="2026-09-16T11:30:00+05:30")
    assert r["status"] == "amended" and r["current_version"] == 2
    assert r["versions"][0]["values"] == {"her2": "2+ (Equivocal)"} and r["versions"][1]["amendment_note"] == "Addendum: re-scored"
    assert h.current_version(r)["values"] == {"her2": "3+ (Positive)"}
    assert set(h.signatures) == {"sig-r1-v1", "sig-r1-v2"} and h.events[-1]["status"] == "C"
    h.amend("r1", "prac-vxreg-29003", {"her2": "3+ (Positive)", "ki67": "40 %"}, "Second addendum",
            when="2026-09-17T10:00:00+05:30")
    assert r["current_version"] == 3 and len(r["versions"]) == 3


def test_amend_requires_a_final_report(h):
    o = _order(h)
    h.report_preliminary(o["id"], "prac-vxreg-29002", {"a": "1"}, report_id="p1", when="2026-09-02T20:15:00+05:30")
    with pytest.raises(LifecycleError):
        h.amend("p1", "prac-vxreg-29001", {"a": "2"}, "x")
    with pytest.raises(LifecycleError):
        h.amend("nope", "prac-vxreg-29001", {}, "x")


def test_cancel_open_order(h):
    o = _order(h)
    h.schedule(o["id"], "2026-09-05", when="2026-09-01T09:40:00+05:30")
    h.cancel_order(o["id"], "Patient did not report on the scheduled date", when="2026-09-06T11:00:00+05:30")
    assert o["status"] == "cancelled" and o["cancel_reason"] == "Patient did not report on the scheduled date"
    assert o["cancelled_on"] == "2026-09-06T11:00:00+05:30" and h.imaging_study_for(o["id"])["status"] == "cancelled"
    assert h.events[-1]["status"] == "X" and h.events[-1]["order_status"] == "CA" and o["report_id"] is None
    for step in (lambda: h.schedule(o["id"], "2026-09-07"), lambda: h.collect_sample(o["id"]),
                 lambda: h.sign_final(o["id"], "prac-vxreg-29001"), lambda: h.cancel_order(o["id"], "again")):
        with pytest.raises(LifecycleError):
            step()


def test_cancel_from_completed_raises(h):
    o = _order(h, "cbc")
    h.sign_final(o["id"], "prac-vxreg-29003", values={"wbc": "6,900 /cumm"}, when="2026-09-01T11:20:00+05:30")
    with pytest.raises(LifecycleError):
        h.cancel_order(o["id"], "too late")


def test_cancel_preliminary_cancels_the_report(h):
    o = _order(h)
    r = h.report_preliminary(o["id"], "prac-vxreg-29002", {"a": "1"}, when="2026-09-02T20:15:00+05:30")
    h.cancel_order(o["id"], "Wrong patient", when="2026-09-03T09:00:00+05:30")
    assert r["status"] == "cancelled" and h.events[-1]["kind"] == "ORU" and h.events[-1]["status"] == "X"


def test_render_hook_fills_document_and_hash(h):
    calls = []

    def hook(report, version):
        calls.append((report["id"], version["version"]))
        return {"path": f"documents/{report['id']}-v{version['version']}.pdf", "sha256": "ab" * 32}

    h.render_hook = hook
    o = _order(h, "cbc")
    r = h.sign_final(o["id"], "prac-vxreg-29003", values={"wbc": "1"}, when="2026-09-01T11:20:00+05:30")
    assert calls == [(r["id"], 1)]
    assert r["versions"][0]["document"]["sha256"] == "ab" * 32
    assert h.signatures[r["versions"][0]["signature_id"]]["document_hash"] == "ab" * 32


def test_transitions_bump_meta_and_use_the_clock(h, clock):
    clock.t = "2026-10-13T12:00:00+05:30"
    o = _order(h, "cbc", when=None)
    assert o["ordered_on"] == "2026-10-13T12:00:00+05:30" and o["meta"]["versionId"] == "1"
    clock.t = "2026-10-13T12:30:00+05:30"
    h.collect_sample(o["id"])
    assert o["meta"] == {"versionId": "2", "lastUpdated": "2026-10-13T12:30:00+05:30"}
    assert [e["id"] for e in h.events] == [f"ev-{i:06d}" for i in range(1, len(h.events) + 1)]


def test_lookups_filter(h):
    a = _order(h)
    b = _order(h, "cbc")
    assert h.orders_for(patient_id="vxh-26-009001") == [a, b]
    assert h.orders_for(department="Radiology") == [a]
    assert h.orders_for(department="RAD", status="ordered") == [a]
    assert h.orders_for(department="Nowhere") == []
    assert h.pending_for_department("Pathology")["orders"] == [b]
    assert [e["id"] for e in h.encounters_for("vxh-26-009001")] == ["op-26-190001"]
    assert h.practitioner("VXREG-29001")["id"] == "prac-vxreg-29001" and h.department("rad")["name"] == "Radiology"
    assert h.practitioners["prac-vxreg-29002"]["role"] == "junior_resident"


def test_save_and_load_round_trip(h, tmp_path):
    _order(h)
    path = h.save(tmp_path / "store.json")
    assert not [p for p in tmp_path.iterdir() if ".tmp" in p.name]
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(h.events) and json.loads(lines[-1]) == h.events[-1]
    back = Store.load(path)
    assert back.data == h.data and back.orders["rad-26-00001"]["accession"] == "RAD/26/00001"
