"""Unit tests for the mock hospital generator (plan item V2-1.1): every fixture patient is built into the store through the
transitions, and nothing that should be absent is there. SYNTHETIC data only; builds into a temporary directory."""
import json
import os
import re
import stat
from datetime import date

import pytest

from his_mock import build as build_cli
from his_mock import generator, ids, scenarios
from his_mock.model import IMAGING_MODALITY, LifecycleError, Store

IMAGING = set(IMAGING_MODALITY)


@pytest.fixture(scope="module")
def fx():
    return scenarios.load()


@pytest.fixture(scope="module")
def built(tmp_path_factory, fx):
    out = tmp_path_factory.mktemp("his_mock")
    # the store alone: the post-build steps (report PDFs, HL7 feed, DICOM) have their own test modules
    store = generator.build(out, seed=2026, fixtures=fx, documents=False, hl7=False, dicom=False)
    index = json.loads((out / "fixture_index.json").read_text(encoding="utf-8"))
    return out, store, index


@pytest.fixture(scope="module")
def store(built):
    return built[1]


@pytest.fixture(scope="module")
def index(built):
    return built[2]


def his_records(fx, ordered=True):
    for p in fx["patients"]:
        for r in p["records"]:
            if r["source"] != "his" or (ordered and r["order_status"] == "never_ordered"):
                continue
            yield p, r


def rec(fx, rid):
    return next(r for p in fx["patients"] for r in p["records"] if r["id"] == rid)


def slot(fx, s):
    return next(p for p in fx["patients"] if p["slot"] == s)


def report_of(store, rid):
    return store.reports[rid.lower()]


# ------------------------------------------------------------------ files and counts
def test_build_writes_every_file(built):
    out, store, _ = built
    for name in ("store.json", "fixture_index.json", "events.jsonl", "token"):
        assert (out / name).is_file(), name
    assert (out / "documents").is_dir() and (out / "dicom").is_dir() and not list((out / "documents").iterdir())
    assert not (out / "events.hl7").exists()  # hl7=False
    assert Store.load(out / "store.json").data == store.data
    lines = (out / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(store.events) > 0


def test_patient_count_is_one_per_registration(store, fx):
    regs = sum(1 + bool(p.get("temporary_uhid")) + bool(p.get("duplicate_uhid")) for p in fx["patients"])
    assert len(store.patients) == regs == 20
    kinds = sorted(p["registration_kind"] for p in store.patients.values())
    assert kinds.count("temporary") == 1 and kinds.count("duplicate") == 1


def test_encounter_order_report_counts(store, fx):
    assert len(store.encounters) == sum(len(p["encounters"]) for p in fx["patients"])
    assert len(store.orders) == len(list(his_records(fx)))
    with_report = [r for _, r in his_records(fx) if r["report_status"] in ("preliminary", "final", "amended")
                   or (r["report_status"] == "cancelled" and r.get("reported_on"))]
    assert len(store.reports) == len(with_report)
    assert len(store.specimens) == len([r for _, r in his_records(fx) if r.get("sample_barcode")])


def test_events_in_time_order_and_sequential(store):
    ev = store.events
    assert len(ev) > len(store.orders)
    times = [ids.parse_time(e["time"]) for e in ev]
    assert times == sorted(times)
    assert [e["id"] for e in ev] == [f"ev-{i:06d}" for i in range(1, len(ev) + 1)]
    assert {e["kind"] for e in ev} == {"ADT", "ORM", "ORU", "REF"}
    assert {e["status"] for e in ev if e["kind"] == "ORU"} == {"P", "F", "C"}
    assert any(e["kind"] == "ORM" and e["status"] == "X" for e in ev)


def test_one_result_event_per_report_version(store):
    for r in store.reports.values():
        n = len([e for e in store.events if e["kind"] == "ORU" and e["refs"].get("report_id") == r["id"]])
        assert n == len(r["versions"]), r["id"]


# ------------------------------------------------------------------ every HIS record survives
def test_every_his_record_survives(store, fx, index):
    for p, r in his_records(fx):
        m = index["slots"][p["slot"]]["records"][r["id"]]
        o = store.orders[m["order_id"]]
        assert o["status"] == r["order_status"], r["id"]
        assert o["accession"] == r.get("accession"), r["id"]
        assert o["test"] == r["test"] and o["doc_type"] == r["type"] and o["performing_department"] == r["producing_department"]
        assert o["encounter_id"] == ids.encounter_id(r["encounter"])
        assert o["ordered_on"][:10] == r["ordered_on"]["value"]
        assert o["patient_id"] == ids.patient_id(r.get("registration") or p["uhid"])
        if r.get("sample_barcode"):
            sp = store.specimens[o["specimen_id"]]
            assert sp["barcode"] == r["sample_barcode"] and sp["block_no"] == r.get("block_no")
        if not m["report_id"]:
            assert o["report_id"] is None and r["report_status"] in ("none", "cancelled")
            continue
        rep = store.reports[m["report_id"]]
        assert rep["id"] == r["id"].lower() and o["report_id"] == rep["id"] and rep["order_id"] == o["id"]
        assert rep["status"] == r["report_status"] and rep["title"] == r["title"]
        cur = store.current_version(rep)
        assert cur["values"] == r["values"], r["id"]
        assert cur["reported_on"] == (r["signature"]["signed_at"]["value"] if r.get("signature") else r["reported_on"]["value"])
        assert rep["omitted_values"] == r.get("omitted_values", [])
        assert rep["observation_values"] == r.get("observation_values", {})
        if r["signed"]:
            sig = store.signatures[cur["signature_id"]]
            s = r["signature"]
            assert sig["block"] == s["block"], r["id"]
            assert sig["signer_id"] == ids.practitioner_id(s["signer"]["reg_no"])
            assert sig["certificate_serial"] == s["certificate_serial"] and sig["ca"] == s["ca"]
            assert sig["signed_at"] == s["signed_at"]["value"] and sig["verification_status"] == s["verification_status"]
            assert sig["document_hash"] is None  # filled by documents.render_all (1.2), not run here
        else:
            assert cur["signature_id"] is None, r["id"]


def test_signature_blocks_use_the_fixture_format(store):
    pat = re.compile(r"^Digitally signed by Dr [^,]+, .+, Reg\. No\. VXREG-\d{5}, \d{2}/\d{2}/\d{4} \d{2}:\d{2}, "
                     r"Vaidyx Demo CA, certificate serial VXDCA-[0-9A-F]{8}$")
    assert store.signatures and all(pat.match(s["block"]) for s in store.signatures.values())


def test_never_ordered_and_outside_reports_absent_but_indexed(store, fx, index):
    absent = [r for p in fx["patients"] for r in p["records"]
              if r["source"] == "outside_upload" or r["order_status"] == "never_ordered"]
    assert len(absent) == 7
    text = json.dumps(store.data)
    for r in absent:
        assert f'"{r["id"].lower()}"' not in text and f'"ord-{r["id"].lower()}"' not in text
    assert sorted(x["record"]["id"] for x in index["outside_reports"]) == ["P06-R06", "P17-R10"]
    assert all(x["record"]["source"] == "outside_upload" and x["record"]["values"] for x in index["outside_reports"])
    assert sorted(x["record"]["id"] for x in index["never_ordered"]) == sorted(
        r["id"] for r in absent if r["order_status"] == "never_ordered")
    assert "P05-R04" in index["slots"]["P05"]["never_ordered"]


def test_fixture_index_covers_every_slot(store, fx, index):
    assert set(index["slots"]) == {p["slot"] for p in fx["patients"]}
    for p in fx["patients"]:
        e = index["slots"][p["slot"]]
        assert e["case_files"] == p["case_files"]
        assert all(pid in store.patients for pid in e["patient_ids"])
        assert all(eid in store.encounters for eid in e["encounter_ids"])
        assert all(oid in store.orders for oid in e["order_ids"]) and all(rid in store.reports for rid in e["report_ids"])
    assert index["fixture_version"] == fx["version"] == store.meta["fixture_version"]


def test_no_slot_fields_in_the_store(store):
    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    assert not {"slot", "scenarios", "serves", "case_files"} & set(keys(store.data))


# ------------------------------------------------------------------ report lifecycle scenarios
def test_amended_report_keeps_earlier_version(store, fx):
    r = report_of(store, "P02-R05")
    f = rec(fx, "P02-R05")
    assert r["status"] == "amended" and len(r["versions"]) == 2
    assert [v["values"] for v in r["versions"]] == [v["values"] for v in f["versions"]]
    assert r["versions"][0]["status"] == "final" and r["versions"][1]["status"] == "amended"
    assert r["versions"][1]["amendment_note"] == f["versions"][1]["amendment_note"]
    assert r["versions"][0]["signature_id"] and r["versions"][1]["signature_id"]
    assert r["meta"]["lastUpdated"] == f["versions"][1]["reported_on"]["value"]


def test_preliminary_report_has_no_signature(store):
    r = report_of(store, "P12-R02")
    assert r["status"] == "preliminary" and len(r["versions"]) == 1 and r["versions"][0]["signature_id"] is None
    assert store.practitioner(r["versions"][0]["reported_by"])["role"] == "junior_resident"
    assert not [s for s in store.signatures.values() if s["report_id"] == r["id"]]
    assert r in store.pending_for_department("Radiology")["reports"]


def test_unsigned_final_report_has_no_signature(store):
    r = report_of(store, "P11-R02")
    assert r["status"] == "final" and r["versions"][0]["signature_id"] is None
    assert not [s for s in store.signatures.values() if s["report_id"] == r["id"]]


def test_cancelled_order_carries_reason_and_no_report(store, fx):
    f = rec(fx, "P10-R09")
    o = store.orders[ids.order_id(f["accession"])]
    assert o["status"] == "cancelled" and o["cancel_reason"] == f["cancel_reason"]
    assert o["cancelled_on"][:10] == f["cancelled_on"]["value"] and o["report_id"] is None
    assert store.imaging_study_for(o["id"]) is None


def test_open_orders_keep_their_state(store, fx):
    assert store.orders["nm-26-00152"]["status"] == "scheduled"
    assert store.orders["nm-26-00152"]["scheduled_for"] == rec(fx, "P04-R09")["scheduled_for"]["value"]
    assert store.orders["mic-26-00611"]["status"] == "ordered"
    mol = store.orders["path-26-00451"]
    assert mol["status"] == "sample_collected" and mol["sample_collected_on"] == "2026-09-17T10:30:00+05:30"
    pend = store.pending_for_department("Pathology")["orders"]
    assert mol in pend and store.orders["mic-26-00611"] in store.pending_for_department("Microbiology")["orders"]


def test_observation_and_omitted_values(store):
    assert report_of(store, "P15-R03")["observation_values"] == {"haemoglobin": "11.2 gm%"}
    assert store.current_version(report_of(store, "P15-R03"))["values"]["haemoglobin"] == "12.1 gm%"
    assert report_of(store, "P03-R05")["omitted_values"] == ["her2"]
    assert "her2" not in store.current_version(report_of(store, "P03-R05"))["values"]


# ------------------------------------------------------------------ encounters
def test_encounters_carry_fixture_fields(store, fx):
    for p in fx["patients"]:
        for e in p["encounters"]:
            s = store.encounters[ids.encounter_id(e["number"])]
            assert (s["kind"], s["number"], s["department"], s["unit"]) == (e["kind"], e["number"], e["department"], e["unit"])
            assert s["patient_id"] == ids.patient_id(e["registration"]) and s["note"] == e.get("note")
            assert s["consultant_id"] == ids.practitioner_id(e["consultant"]["reg_no"])
            if e["kind"] == "OP":
                assert s["date"] == e["date"]["value"] and s["visit_type"] == e["visit_type"] and s["class"] == "AMB"
            else:
                assert s["admitted"] == e["admitted"]["value"] and s["class"] == "IMP"
                assert s["discharged"] == ((e.get("discharged") or {}).get("value"))
                assert s["status"] == ("finished" if e.get("discharged") else "in-progress")
                assert s["ward"] == (e["ward_history"][-1]["ward"] if e.get("ward_history") else e["ward"])
                pre = e.get("pmjay_preauth")
                assert s["pmjay_preauth"] == (pre and {"status": pre["status"], "date": (pre.get("date") or {}).get("value")})


def test_p03_ward_transfers_and_repeat_cbc_same_ip(store, fx):
    e = store.encounters["ip-26-01872"]
    f = next(x for x in slot(fx, "P03")["encounters"] if x["number"] == "IP/26/01872")
    assert len(e["ward_history"]) == 3
    assert [(w["ward"], w["bed"], w["from"]) for w in e["ward_history"]] == [
        (w["ward"], w["bed"], w["from"]["value"]) for w in f["ward_history"]]
    assert e["ward_history"][1]["reason"] == "Observation after a hypotensive episode"
    assert len([x for x in store.events if x["trigger"] == "A02" and x["refs"]["encounter_id"] == e["id"]]) == 2
    cbcs = [o for o in store.orders_for(patient_id="vxh-26-004203") if o["test"] == "cbc"]
    assert len(cbcs) >= 2 and {o["encounter_id"] for o in cbcs if o["accession"] == "PATH/26/00420"} == {e["id"]}


def test_p14_referral_pulmonology_to_colorectal(store):
    e = store.encounters["ip-26-01877"]
    assert e["department"] == "Pulmonology"
    assert [(r["from"], r["to"], r["on"], r["status"]) for r in e["referrals"]] == [
        ("Pulmonology", "Colorectal Surgery", "2026-09-04", "accepted")]
    assert e["referrals"][0]["reason"].startswith("Lung biopsy reported as metastatic adenocarcinoma")


# ------------------------------------------------------------------ registrations and identity
def test_p09_temporary_registration_is_separate_and_found_by_similarity(store):
    perm, temp = store.patients["vxh-26-004209"], store.patients["vxh-t-26-00412"]
    assert temp["registration_kind"] == "temporary" and temp["abha"] is None and temp["pmjay_id"] is None
    assert "vxh-26-004209" not in json.dumps(temp) and "VXH/26/004209" not in json.dumps(temp)
    assert [p["id"] for p in store.similar_registrations(perm["id"])] == [temp["id"]]
    assert [p["id"] for p in store.similar_registrations(temp["id"])] == [perm["id"]]
    assert store.orders["rad-26-00997"]["patient_id"] == temp["id"]
    assert temp["registered_on"] == "2026-08-22"


def test_p17_duplicate_uhid_is_separate(store):
    dup = store.patients["vxh-26-004317"]
    assert dup["registration_kind"] == "duplicate" and dup["registered_on"] == "2026-03-12"
    assert [p["id"] for p in store.similar_registrations("vxh-26-004217")] == ["vxh-26-004317"]
    assert [e["id"] for e in store.encounters_for(dup["id"])] == ["op-26-118721"]


def test_two_sunita_devis_are_not_similar(store):
    both = store.patients_by_name("Sunita Devi")
    assert sorted(p["uhid"] for p in both) == ["VXH/26/004204", "VXH/26/004210"]
    assert {p["age"] for p in both} == {52, 61}
    assert store.similar_registrations("vxh-26-004204") == [] and store.similar_registrations("vxh-26-004210") == []


def test_patient_by_identifier(store, fx):
    p12 = slot(fx, "P12")
    assert store.patient_by_identifier("VXH/26/004212")["id"] == "vxh-26-004212"
    assert store.patient_by_identifier("VXH/T/26/00412")["id"] == "vxh-t-26-00412"
    assert store.patient_by_identifier("IP/26/01875")["id"] == "vxh-26-004212"
    assert store.patient_by_identifier("OP/26/118716")["id"] == "vxh-26-004212"
    assert store.patient_by_identifier(p12["abha"]["number"])["id"] == "vxh-26-004212"
    assert store.patient_by_identifier("OP/26/118712")["id"] == "vxh-t-26-00412"


def test_patients_carry_demographics(store, fx):
    today = date.fromisoformat(fx["hospital"]["today"])
    for p in store.patients.values():
        assert p["marker"] == "SYNTHETIC" and "(SYNTHETIC)" in p["name"] and p["sex"] in ("F", "M")
        dob = date.fromisoformat(p["dob_iso"])
        assert p["dob"] == dob.strftime("%d/%m/%Y")
        assert today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)) == p["age"]
        assert re.match(r"^\+91 90000 0\d{4}$", p["phone"])
        assert set(p["address"]) == {"line", "town", "district", "state", "pin"} and re.match(r"^5\d{5}$", p["address"]["pin"])
        first = min((e.get("date") or e["admitted"]) for e in store.encounters_for(p["id"]))
        assert p["registered_on"] <= first
        assert p["meta"]["lastUpdated"][:10] == p["registered_on"]
    assert len({p["phone"] for p in store.patients.values()}) == len(store.patients)
    for f in fx["patients"]:
        s = store.patients[ids.patient_id(f["uhid"])]
        assert s["abha"] == f["abha"] and s["pmjay_id"] == f["pmjay_id"] and s["registration_kind"] == "permanent"


def test_p12_has_an_opd_note_older_than_the_fetch_window(store, fx):
    h = fx["hospital"]
    today = date.fromisoformat(h["today"])
    cutoff = today.replace(year=today.year - h["fetch_window_months"] // 12)
    e = store.encounters["op-25-104211"]
    assert e["patient_id"] == "vxh-26-004212" and e["department"] == "Pulmonology"
    assert date.fromisoformat(e["date"]) < cutoff
    r = report_of(store, "P12-R14")
    assert r["encounter_id"] == e["id"] and r["status"] == "final" and r["versions"][0]["signature_id"]
    assert store.current_version(r)["values"]["presenting_complaint"] == "Cough for 6 weeks"
    assert store.reports_for(patient_id="vxh-26-004212", since=f"{cutoff.isoformat()}T00:00:00+05:30").count(r) == 0


# ------------------------------------------------------------------ master data
def test_departments_and_practitioners(store, fx):
    assert len(store.departments) == len(fx["departments"]) == 30
    for d in fx["departments"]:
        s = store.department(d["name"])
        assert s["code"] == d["code"] and s["group"] == d["group"] and s["email"] == f"{d['code'].lower()}@vaidyx-demo.invalid"
        assert s["consultants"] == [ids.practitioner_id(c["reg_no"]) for c in d.get("consultants", [])]
    n = sum(len(d.get("consultants", [])) for d in fx["departments"])
    assert len(store.practitioners) == n
    serials = [p["certificate_serial"] for p in store.practitioners.values()]
    assert len(set(serials)) == n and all(ids.PATTERNS["certificate_serial"].match(s) for s in serials)
    assert store.practitioner("VXREG-20203")["role"] == "junior_resident"
    assert store.practitioner("VXREG-20108")["certificate_serial"] == "VXDCA-00A1B25F"
    assert {p["role"] for p in store.practitioners.values()} == {"consultant", "junior_resident"}


def test_hospital_and_meta(store, fx):
    h = store.hospital
    assert h["name"] == "Vaidyx Demo Hospital (SYNTHETIC)" and h["timezone"] == "+05:30" and h["marker"] == "SYNTHETIC"
    for k in ("ncg_level", "pmjay_empanelled", "fetch_window_months", "surgical_oncology_list", "board_heads"):
        assert h[k] == fx["hospital"][k]
    m = store.meta
    assert m["seed"] == 2026 and m["schema_version"] == 1 and m["marker"] == "SYNTHETIC" and m["built_at"]


# ------------------------------------------------------------------ imaging, times
def test_imaging_study_for_every_imaging_order(store):
    for o in store.orders.values():
        st = store.imaging_study_for(o["id"])
        if o["doc_type"] in IMAGING and o["status"] != "cancelled":
            assert st and st["accession"] == o["accession"] and st["order_id"] == o["id"], o["id"]
            assert st["study_uid"] == ids.study_uid(o["accession"]) and len(st["study_uid"]) <= 64
            assert re.match(r"^2\.25\.[1-9]\d*$", st["study_uid"])
            assert st["modality"] == IMAGING_MODALITY[o["doc_type"]] and st["status"] == "registered"  # dicom=False
        elif o["doc_type"] not in IMAGING:
            assert st is None
    uids = [s["study_uid"] for s in store.imaging_studies.values()]
    assert len(uids) == len(set(uids))


def test_last_updated_is_the_clinical_time(store):
    for r in store.reports.values():
        assert r["meta"]["lastUpdated"] == store.current_version(r)["reported_on"], r["id"]
    for o in store.orders.values():
        r = store.report_for_order(o["id"])
        steps = [o["ordered_on"], o["sample_collected_on"], o["cancelled_on"]] + ([r["versions"][0]["reported_on"]] if r else [])
        assert o["meta"]["lastUpdated"] == max(ids.iso(s) for s in steps if s) or o["status"] == "scheduled"
    built_at = store.meta["built_at"][:10]
    assert all(x["meta"]["lastUpdated"][:10] < built_at for x in store.encounters.values())


def test_orders_follow_encounter_and_precede_results(store):
    for o in store.orders.values():
        e = store.encounters[o["encounter_id"]]
        start = e["ward_history"][0]["from"] if e["kind"] == "IP" else e["date"] + "T00:00:00+05:30"
        assert ids.parse_time(o["ordered_on"]) >= ids.parse_time(start), o["id"]
        r = store.report_for_order(o["id"])
        if r:
            assert ids.parse_time(r["versions"][0]["reported_on"]) > ids.parse_time(o["ordered_on"]), o["id"]
        if o["sample_collected_on"] and r:
            assert ids.parse_time(o["sample_collected_on"]) < ids.parse_time(r["versions"][0]["reported_on"])


# ------------------------------------------------------------------ the desk flow on the built store
def test_sign_the_preliminary_and_delta_fetch(store):
    s = Store(json.loads(json.dumps(store.data)), clock=lambda: "2026-10-13T11:00:00+05:30")
    mark = max(r["meta"]["lastUpdated"] for r in s.reports.values())
    s.sign_final("p12-r02", "VXREG-20201")
    r = s.reports["p12-r02"]
    assert r["status"] == "final" and [v["status"] for v in r["versions"]] == ["preliminary", "final"]
    assert s.signatures["sig-p12-r02-v2"]["certificate_serial"] == "VXDCA-00A1B202"
    assert s.reports_for(since=mark) == [r]
    assert s.reports_for(patient_id="vxh-26-004212", since=mark) == [r]
    assert s.events[-1]["status"] == "F" and s.events[-1]["refs"]["report_id"] == "p12-r02"


def test_new_accession_does_not_collide_with_fixtures(store, fx):
    s = Store(json.loads(json.dumps(store.data)), clock=lambda: "2026-10-13T11:00:00+05:30")
    o = s.place_order("vxh-26-004212", "ip-26-01875", "chest_xray", "Medical Oncology")
    fixture_acc = {r.get("accession") for p in fx["patients"] for r in p["records"]}
    assert ids.PATTERNS["accession"].match(o["accession"]) and o["accession"].startswith("RAD/26/")
    assert o["accession"] not in fixture_acc
    with pytest.raises(LifecycleError):
        s.cancel_order("path-26-00411", "too late")


# ------------------------------------------------------------------ hygiene, determinism, token
def test_store_is_synthetic_and_clean(built):
    out, store, _ = built
    text = (out / "store.json").read_text(encoding="utf-8") + (out / "events.jsonl").read_text(encoding="utf-8")
    assert "Sahyadri" not in text and "SYN-" not in text and "—" not in text
    assert not scenarios.AADHAAR_LIKE.search(text)
    assert all("(SYNTHETIC)" in p["name"] for p in store.patients.values())
    for _, s in scenarios.strings(store.data):
        assert not scenarios.AADHAAR_LIKE.search(s), s


def test_deterministic_rebuild(tmp_path, built, fx):
    out, _, _ = built
    other = generator.build(tmp_path, seed=2026, fixtures=fx, documents=False, hl7=False, dicom=False)
    a = json.loads((out / "store.json").read_text(encoding="utf-8"))
    b = json.loads((tmp_path / "store.json").read_text(encoding="utf-8"))
    a["meta"].pop("built_at"), b["meta"].pop("built_at")
    assert a == b
    assert (out / "fixture_index.json").read_text() == (tmp_path / "fixture_index.json").read_text()
    assert (out / "events.jsonl").read_text() == (tmp_path / "events.jsonl").read_text()
    seeded = generator.build_store(fx, seed=99)[0]
    assert seeded.patients["vxh-26-004201"]["dob"] != other.patients["vxh-26-004201"]["dob"] or \
        seeded.patients["vxh-26-004201"]["address"] != other.patients["vxh-26-004201"]["address"]


def test_token_mode_600_and_kept_on_rebuild(tmp_path, fx):
    generator.build(tmp_path, fixtures=fx, documents=False, hl7=False, dicom=False)
    tok = tmp_path / "token"
    first = tok.read_text()
    assert re.match(r"^[0-9a-f]{32}\n$", first)
    assert stat.S_IMODE(os.stat(tok).st_mode) == 0o600
    (tmp_path / "documents" / "old.pdf").write_text("x")
    (tmp_path / "dicom" / "keep.dcm").write_text("x")
    generator.build(tmp_path, fixtures=fx, documents=False, hl7=False, dicom=False)
    assert tok.read_text() == first and not (tmp_path / "documents" / "old.pdf").exists()
    assert (tmp_path / "dicom" / "keep.dcm").exists()


def test_build_refuses_inconsistent_fixtures(tmp_path, fx):
    bad = json.loads(json.dumps(fx))
    bad["patients"][0]["uhid"] = "SAH/26/1"
    with pytest.raises(ValueError):
        generator.build(tmp_path, fixtures=bad, documents=False, hl7=False, dicom=False)
    assert not (tmp_path / "store.json").exists()


def test_cli_prints_summary(tmp_path, capsys):
    assert build_cli.main(["--out", str(tmp_path), "--seed", "2026", "--no-pdf", "--no-hl7", "--no-dicom"]) == 0
    line = capsys.readouterr().out.strip()
    assert "20 patients" in line and "165 orders" in line and "events" in line and "\n" not in line
    with pytest.raises(SystemExit):
        build_cli.main(["--out", str(tmp_path / "data" / "tumour_board" / "x")])
