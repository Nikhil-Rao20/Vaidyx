"""Unit tests for the mock hospital's event feed (plan item V2-1.4): one HL7 v2.5-style message per store event, the feed file,
the light parser and the delta (changed_since / events_since). SYNTHETIC data only; stores built in memory or in tmp_path."""
import re
from datetime import timedelta

import pytest

from his_mock import generator, hl7, ids, scenarios
from his_mock.model import Store

from .test_model import HOSPITAL, Clock

# a 12-digit number standing alone, with or without 4-4-4 spaces / hyphens (what an Aadhaar number looks like)
TWELVE_DIGITS = re.compile(r"(?<![\d-])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\d-])")
TS = re.compile(r"^\d{14}\+0530$")


@pytest.fixture(scope="module")
def fx():
    return scenarios.load()


@pytest.fixture()
def fstore(fx):
    """The full fixture build in memory (fresh per test: some tests change it)."""
    return generator.build_store(fx)[0]


@pytest.fixture(scope="module")
def fixture_messages(fx):
    s = generator.build_store(fx)[0]
    return s, [hl7.message(s, e) for e in s.events]


@pytest.fixture
def h():
    """A tiny hospital with one admitted patient: covers ward transfer, referral, discharge and both cancellations."""
    clock = Clock()
    s = Store.empty(HOSPITAL, seed=7, fixture_version="test", built_at="2026-10-13T00:00:00+05:30", clock=clock)
    for name, code, group in (("Radiology", "RAD", "supporting"), ("Pathology", "PATH", "supporting"),
                              ("Breast Surgery", "BS", "treating"), ("Medical Oncology", "MO", "treating")):
        s.add_department(name, code, group)
    s.add_practitioner("Dr Test Radiologist", "MD (Radiodiagnosis)", "VXREG-29001", "Radiology", "VXDCA-0000A001")
    s.add_practitioner("Dr Test Pathologist", "MD (Pathology)", "VXREG-29003", "Pathology", "VXDCA-0000A003")
    s.add_practitioner("Dr Test Surgeon", "MS (General Surgery), MCh (Breast Surgery)", "VXREG-29004", "Breast Surgery",
                       "VXDCA-0000A004")
    s.add_test("cect_tap", "CECT thorax, abdomen and pelvis", "ct", "Radiology")
    s.add_test("cbc", "Complete blood count", "lab", "Pathology")
    s.add_test("hpe_biopsy", "Histopathology report (biopsy)", "histopathology", "Pathology")
    s.register_patient("Test Patient (SYNTHETIC)", "F", 50, uhid="VXH/26/009001", dob="1976-01-01",
                       abha={"number": "99-2600-0000-9001", "address": "test.patient@sbx"}, when="2026-09-01T08:30:00+05:30")
    s.admit("vxh-26-009001", "Breast Surgery", "Female Surgical Ward", "FSW-12", ip_no="IP/26/09001",
            consultant_id="prac-vxreg-29004", when="2026-09-02T10:00:00+05:30")
    s.transfer_ward("ip-26-09001", "High Dependency Unit", "HDU-02", reason="Post-operative care",
                    when="2026-09-03T22:00:00+05:30")
    s.refer("ip-26-09001", "Breast Surgery", "Medical Oncology", "Opinion on systemic therapy | ER & PR",
            when="2026-09-04T10:00:00+05:30")
    s.accept_referral("ip-26-09001", "Medical Oncology", when="2026-09-04T15:00:00+05:30")
    s.place_order("vxh-26-009001", "ip-26-09001", "cect_tap", "Breast Surgery", ordered_on="2026-09-02T10:30:00+05:30")
    s.cancel_order("rad-26-00001", "Patient unfit for contrast", when="2026-09-02T12:00:00+05:30")
    s.place_order("vxh-26-009001", "ip-26-09001", "cbc", "Breast Surgery", ordered_on="2026-09-02T10:32:00+05:30")
    s.collect_sample("path-26-00001", when="2026-09-02T10:50:00+05:30")
    s.report_preliminary("path-26-00001", "prac-vxreg-29003", {"hb": "11.2 gm%", "tlc": "7,800 /cumm"},
                         when="2026-09-02T14:00:00+05:30")
    s.cancel_order("path-26-00001", "Sample haemolysed", when="2026-09-02T15:00:00+05:30")
    s.discharge("ip-26-09001", when="2026-09-08T18:00:00+05:30")
    return s


def _consultant(store, dept_name):
    d = store.department(dept_name)
    return next(store.practitioners[p]["id"] for p in d["consultants"] if store.practitioners[p]["role"] == "consultant")


def _later(t, **kw):
    return ids.iso(ids.parse_time(t) + timedelta(**kw))


# ------------------------------------------------------------------ messages
def test_one_message_per_event_and_every_message_parses(fixture_messages):
    s, msgs = fixture_messages
    assert len(msgs) == len(s.events) > 0
    for e, m in zip(s.events, msgs):
        p = hl7.parse(m)
        assert p["control_id"] == e["id"]
        assert p["type"] == f"{e['kind']}^{e['trigger']}"
        msh = p["segments"]["MSH"]
        assert msh[1:4] == ["|", "^~\\&", "VXHIS"] and msh[4] == "VXDEMO" and msh[12] == "2.5"
        assert TS.match(msh[7]) and msh[7] == hl7.ts(e["time"])
        assert "\n" not in m and "PID" in p["segments"] and "PV1" in p["segments"]


def test_message_types_match_event_kinds(fixture_messages, h):
    s, msgs = fixture_messages
    seen = set()
    for e, m in zip(s.events, msgs):
        p = hl7.parse(m)
        seg = p["segments"]
        seen.add(p["type"])
        if e["kind"] == "ADT":
            assert set(seg) == {"MSH", "EVN", "PID", "PV1"} and seg["EVN"][1] == e["trigger"]
        elif e["kind"] == "REF":
            assert seg["RF1"][1].split("^")[0] == {"I12": "P", "I13": "A"}[e["trigger"]]
            assert [prd[1] for prd in seg["PRD"]] == ["RP", "RT"]
        elif e["kind"] == "ORM":
            assert seg["OBR"][25] == e["status"] in ("O", "S", "I", "X")
            assert seg["ORC"][5] == e["order_status"] in ("IP", "SC", "CA")
            assert seg["ORC"][1] == {"O": "NW", "S": "SC", "I": "SC", "X": "CA"}[e["status"]]
            order = s.orders[e["refs"]["order_id"]]
            assert seg["ORC"][2].split("^")[0] == seg["OBR"][2].split("^")[0] == order["id"]
            assert seg["OBR"][4].split("^")[0] == order["test"]
            if order["accession"]:
                assert seg["ORC"][3].split("^")[0] == order["accession"]
        else:
            assert e["kind"] == "ORU" and seg["OBR"][25] == e["status"] in ("P", "F", "C", "X")
    assert {"ADT^A28", "ADT^A04", "ADT^A01", "ADT^A02", "ADT^A03", "REF^I12", "REF^I13", "ORM^O01",
            "ORU^R01"} <= seen
    statuses = {(e["kind"], e["status"]) for e in s.events}
    assert {("ORM", "O"), ("ORM", "S"), ("ORM", "I"), ("ORM", "X"), ("ORU", "P"), ("ORU", "F"), ("ORU", "C")} <= statuses
    # the hand-made store adds a cancelled preliminary report: ORU with OBR-25 X
    oru_x = [hl7.parse(hl7.message(h, e)) for e in h.events if e["kind"] == "ORU" and e["status"] == "X"]
    assert len(oru_x) == 1 and "OBX" not in oru_x[0]["segments"]
    assert oru_x[0]["segments"]["ORC"][5] == "CA" and hl7.unescape(oru_x[0]["segments"]["NTE"][0][3]) == "Sample haemolysed"


def test_cancelled_order_event_carries_x(h, fstore):
    for s in (h, fstore):
        cancelled = [o for o in s.orders.values() if o["status"] == "cancelled"]
        assert cancelled
        for o in cancelled:
            ev = [e for e in s.events if e["refs"].get("order_id") == o["id"] and e["status"] == "X"]
            assert len(ev) == 1
            seg = hl7.parse(hl7.message(s, ev[0]))["segments"]
            assert seg["OBR"][25] == "X" and seg["ORC"][1] == "CA" and seg["ORC"][5] == "CA"
            assert hl7.unescape(seg["ORC"][16]) == o["cancel_reason"]


def test_pid_and_pv1(h, fixture_messages):
    s, msgs = fixture_messages
    for e, m in zip(s.events, msgs):
        seg = hl7.parse(m)["segments"]
        patient = s.patients[e["refs"]["patient_id"]]
        reps = seg["PID"][3].split("~")
        assert reps[0] == f"{patient['uhid']}^^^VXH^MR"
        if patient.get("abha"):
            assert reps[1] == f"{patient['abha']['number']}^^^ABHA^NH"
        assert "(SYNTHETIC)" in seg["PID"][5] and len(seg["PID"][5].split("^")) == 2
        assert seg["PID"][7] == patient["dob_iso"].replace("-", "") and seg["PID"][8] == patient["sex"]
        enc = s.encounters.get(e["refs"].get("encounter_id"))
        if enc:
            assert seg["PV1"][2] == {"OP": "O", "IP": "I"}[enc["kind"]] and seg["PV1"][19] == enc["number"]
            assert seg["PV1"][10].split("^")[0] == enc["department"]
            if enc.get("consultant_id"):
                assert re.match(r"^VXREG-\d{5}\^Dr ", seg["PV1"][7])
        else:
            assert e["trigger"] == "A28" and seg["PV1"][2] == "N"
    # the name: SURNAME^GIVEN, the marker kept
    first = hl7.parse(hl7.message(h, h.events[0]))["segments"]["PID"]
    assert first[5] == "Patient (SYNTHETIC)^Test"
    # the bed at the time of each event (the transfer moves it), discharge time on A03 only
    pv1 = {e["trigger"]: hl7.parse(hl7.message(h, e))["segments"]["PV1"] for e in h.events if e["kind"] == "ADT"}
    assert pv1["A01"][3] == "Female Surgical Ward^^FSW-12" and pv1["A02"][3] == "High Dependency Unit^^HDU-02"
    assert pv1["A03"][45] == "20260908180000+0530" and len(pv1["A01"]) <= 45


def test_referral_rf1_and_escaping(h):
    refs = [hl7.parse(hl7.message(h, e))["segments"] for e in h.events if e["kind"] == "REF"]
    assert [r["RF1"][1] for r in refs] == ["P^Requested", "A^Accepted"]
    for r in refs:
        assert r["RF1"][3] == "Breast Surgery^Medical Oncology" and r["RF1"][6].startswith("IP/26/09001-R1")
        assert hl7.unescape(r["RF1"][10].split("^")[1]) == "Opinion on systemic therapy | ER & PR"
        assert "\\F\\" in r["RF1"][10] and "\\T\\" in r["RF1"][10]
    assert hl7.unescape(hl7.escape("a|b^c&d~e\\f\ng")) == "a|b^c&d~e\\f\ng"


def test_signed_report_obx_values_and_signature_nte(fixture_messages):
    s, msgs = fixture_messages
    checked = 0
    for e, m in zip(s.events, msgs):
        if e["kind"] != "ORU" or e["status"] not in ("F", "C"):
            continue
        r = s.reports[e["refs"]["report_id"]]
        v = next(v for v in r["versions"] if v["version"] == e["refs"]["version"])
        seg = hl7.parse(m)["segments"]
        obx = seg.get("OBX", [])
        assert [(o[3], hl7.unescape(o[5])) for o in obx] == list(v["values"].items())
        assert all(o[2] == "ST" and o[11] == e["status"] for o in obx)
        assert seg["OBR"][22] == hl7.ts(v["reported_on"])
        if v.get("signature_id"):
            sig = s.signatures[v["signature_id"]]
            signer = s.practitioners[sig["signer_id"]]
            assert seg["OBR"][32] == f"{signer['reg_no']}^{signer['name']}"
            note = hl7.unescape(seg["NTE"][0][3])
            assert note == sig["block"] and "Digitally signed by" in note and "Vaidyx Demo CA" in note
            assert seg["NTE"][0][4] == "SIG"
            checked += 1
        else:
            assert len(seg["OBR"]) <= 32 or seg["OBR"][32] == ""
    assert checked > 100
    # the amendment keeps its note and the preliminary one has P values and no signer
    amended = [hl7.parse(m)["segments"] for e, m in zip(s.events, msgs) if e["kind"] == "ORU" and e["status"] == "C"]
    assert amended and any(n[4] == "AMD" for n in amended[0]["NTE"])
    prelim = [hl7.parse(m)["segments"] for e, m in zip(s.events, msgs) if e["kind"] == "ORU" and e["status"] == "P"]
    assert prelim and all(o[11] == "P" for o in prelim[0]["OBX"]) and "NTE" not in prelim[0]
    assert len(prelim[0]["OBR"]) <= 32 or prelim[0]["OBR"][32] == ""


def test_no_aadhaar_anywhere(fixture_messages, h):
    _, msgs = fixture_messages
    assert TWELVE_DIGITS.search("x|1234 5678 9012|") and TWELVE_DIGITS.search("x|123456789012|")
    assert not TWELVE_DIGITS.search("99-2600-0000-9001") and not TWELVE_DIGITS.search("20260908180000+0530")
    for m in msgs + [hl7.message(h, e) for e in h.events]:
        assert "aadhaar" not in m.lower()
        assert not TWELVE_DIGITS.search(m), TWELVE_DIGITS.search(m).group(0)


# ------------------------------------------------------------------ the feed file
def test_write_read_append_round_trip(h, tmp_path):
    path = tmp_path / "events.hl7"
    n = hl7.write_feed(h, path)
    assert n == len(h.events)
    msgs = hl7.read_feed(path)
    assert len(msgs) == n and msgs == [hl7.message(h, e) for e in h.events]
    assert path.read_bytes().count(b"\r\n\r\n") == n
    h.place_order("vxh-26-009001", "ip-26-09001", "hpe_biopsy", "Breast Surgery", ordered_on="2026-09-09T09:00:00+05:30")
    hl7.append(h, h.events[-1], path)
    again = hl7.read_feed(path)
    assert len(again) == len(h.events) == n + 1 and hl7.parse(again[-1])["control_id"] == h.events[-1]["id"]
    assert hl7.read_feed(tmp_path / "missing.hl7") == []


def test_full_fixture_feed_has_one_message_per_event(fstore, tmp_path):
    path = tmp_path / "events.hl7"
    assert hl7.write_feed(fstore, path) == len(fstore.events)
    msgs = hl7.read_feed(path)
    assert len(msgs) == len(fstore.events)
    assert [hl7.parse(m)["control_id"] for m in msgs] == [e["id"] for e in fstore.events]


def test_generator_build_writes_events_hl7(tmp_path, fx):
    store = generator.build(tmp_path, fixtures=fx, documents=False, dicom=False, hl7=True)
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    msgs = hl7.read_feed(tmp_path / "events.hl7")
    assert len(msgs) == len(lines) == len(store.events)
    assert all(hl7.parse(m)["type"] for m in msgs)


# ------------------------------------------------------------------ deltas
def test_delta_returns_exactly_the_changed_reports(fstore):
    s = fstore
    mark = hl7.last_event_time(s)
    assert mark == max((e["time"] for e in s.events), key=ids.parse_time)
    assert hl7.changed_since(s, mark) == [] and hl7.events_since(s, mark) == []
    assert len(hl7.changed_since(s, None)) == len(s.reports)

    prelim = [r for r in s.reports.values() if r["status"] == "preliminary" and r["patient_id"] == "vxh-26-004212"]  # P12, the "preliminary only" scenario
    assert len(prelim) == 1
    rep = prelim[0]
    dept = s.orders[rep["order_id"]]["performing_department"]
    t1 = _later(mark, hours=1)
    s.sign_final(rep["id"], _consultant(s, dept), when=t1)
    assert [r["id"] for r in hl7.changed_since(s, mark)] == [rep["id"]]
    evs = hl7.events_since(s, mark)
    assert len(evs) == 1 and evs[0]["kind"] == "ORU" and evs[0]["status"] == "F"
    assert evs[0]["refs"]["report_id"] == rep["id"]
    seg = hl7.parse(hl7.message(s, evs[0]))["segments"]
    assert seg["OBR"][25] == "F" and "Digitally signed by" in hl7.unescape(seg["NTE"][0][3])
    assert hl7.last_event_time(s) == t1
    # per patient: the signed report's registration sees it, another registration sees nothing
    other = next(p for p in s.patients if p != rep["patient_id"])
    assert [r["id"] for r in hl7.changed_since(s, mark, patient_id=rep["patient_id"])] == [rep["id"]]
    assert hl7.changed_since(s, mark, patient_id=other) == [] and hl7.events_since(s, mark, patient_id=other) == []

    # a second change: an amendment of another signed report
    final = next(r for r in s.reports.values() if r["status"] == "final" and r["id"] != rep["id"]
                 and s.current_version(r).get("signature_id"))
    signer = s.signatures[s.current_version(final)["signature_id"]]["signer_id"]
    values = dict(s.current_version(final)["values"])
    t2 = _later(mark, hours=2)
    s.amend(final["id"], signer, values, "Addendum: typographical correction (SYNTHETIC test).", when=t2)
    assert [r["id"] for r in hl7.changed_since(s, mark)] == [rep["id"], final["id"]]
    assert [r["id"] for r in hl7.changed_since(s, t1)] == [final["id"]]
    evs = hl7.events_since(s, mark)
    assert [(e["refs"]["report_id"], e["status"]) for e in evs] == [(rep["id"], "F"), (final["id"], "C")]
    assert hl7.changed_since(s, t2) == [] and hl7.last_event_time(s) == t2


def test_events_and_reports_agree(fx):
    """Every event after a watermark concerns a changed report or an encounter / patient / order change, and every changed
    report has a result event after it."""
    s = generator.build_store(fx)[0]
    times = sorted({e["time"] for e in s.events}, key=ids.parse_time)
    for mark in times[:: max(1, len(times) // 25)]:
        changed = {r["id"] for r in hl7.changed_since(s, mark)}
        evs = hl7.events_since(s, mark)
        with_report = {e["refs"]["report_id"] for e in evs if e["refs"].get("report_id")}
        assert with_report == changed
        for e in evs:
            if not e["refs"].get("report_id"):
                assert e["kind"] in ("ADT", "REF", "ORM")
                assert e["refs"].get("encounter_id") or e["trigger"] == "A28"
