"""Builds the mock hospital's store from the V2 fixtures (plan item V2-1.1). SYNTHETIC data only, stdlib only.

    from his_mock import generator
    store = generator.build(out_dir, seed=2026)

Every registration, encounter, order, sample, report, signature and ward / referral movement of his_mock/scenarios.json is
replayed through the Store transitions with `when=` set to the fixture times, in time order, so meta.lastUpdated and the
event log read like the hospital's real history. Records that were never ordered and outside reports are not created in
the store; fixture_index.json lists them, with the slot <-> id mapping that tests and the e2e use (the store itself carries
no fixture slots).

Deterministic for a given seed: two builds give the same store.json apart from meta.built_at.
"""
import json
import os
import random
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from . import ids, scenarios
from .ids import IST, iso, parse_time
from .model import IMAGING_MODALITY, Store
from .paths import DATA_DIR, layout

DEFAULT_SEED = 2026

# invented address parts (plain fiction; PIN codes 5xxxxx as in the southern states named)
_LOCALITIES = ("Kalpit Nagar", "Demo Colony", "Sample Layout", "Vaidyx Extension", "Model Housing Society", "Nirmit Vihar")
_TOWNS = (("Kalpitpur", "Kalpitpur", "Karnataka"), ("Demogiri", "Demogiri", "Telangana"),
          ("Samplepet", "Nirmit", "Andhra Pradesh"), ("Vaidyxpura", "Kalpitpur", "Karnataka"),
          ("Mockanagaram", "Demogiri", "Telangana"))

# fixed times of day (IST) for fixture values that carry only a date
_REGISTRATION_LEAD = timedelta(minutes=30)
_VISIT_TIME = (9, 0)
_ADMISSION_TIME = (10, 0)
_ORDER_TIME = (9, 30)
_REFERRAL_TIME = (10, 0)
_ACCEPT_TIME = (15, 0)
_CANCEL_TIME = (11, 0)
_DISCHARGE_TIME = (18, 0)

# tie-break for actions at the same minute: the step a hospital does first comes first
_PRIORITY = {"register": 0, "visit": 1, "admit": 1, "transfer": 2, "order": 3, "schedule": 4, "collect": 5,
             "preliminary": 6, "final": 7, "amend": 8, "cancel": 9, "refer": 10, "accept": 11, "discharge": 12}


def build(out_dir=None, seed=DEFAULT_SEED, fixtures=None, clock=None, documents=True, dicom=True, hl7=True):
    """Build every scenario patient into `out_dir` (default data/his_mock/) and return the Store.

    Writes store.json, fixture_index.json, events.jsonl, documents/ (1.2), events.hl7 (1.4), dicom/ (1.7) and a token
    file (32 hex chars, mode 600) only when none exists. A rebuild wipes store.json, fixture_index.json, events.jsonl,
    events.hl7 and documents/ and keeps the token (and dicom/, which 1.7 fills deterministically). The post-build steps
    (report PDFs, HL7 feed, DICOM) run only when their module exists; `documents=False` / `dicom=False` / `hl7=False`
    skip them (fast unit tests)."""
    fixtures = fixtures if fixtures is not None else scenarios.load()
    problems = scenarios.validate(fixtures)
    if problems:
        raise ValueError("fixtures do not validate: " + "; ".join(problems[:5]))
    store, index = build_store(fixtures, seed=seed, clock=clock)
    files = layout(out_dir or DATA_DIR)
    d = files["data_dir"]
    d.mkdir(parents=True, exist_ok=True)
    if files["store"].exists():
        try:
            marker = json.loads(files["store"].read_text(encoding="utf-8")).get("meta", {}).get("marker")
        except (ValueError, OSError):
            marker = None
        if marker != "SYNTHETIC":
            raise ValueError(f"{files['store']} is not a mock-hospital store (no SYNTHETIC marker): refusing to wipe {d}")
    for k in ("store", "fixture_index", "events", "hl7"):
        if files[k].exists():
            files[k].unlink()
    if files["documents"].exists():
        shutil.rmtree(files["documents"])
    files["documents"].mkdir()
    files["dicom"].mkdir(exist_ok=True)
    store.save(files["store"], files["events"])
    files["fixture_index"].write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    ensure_token(files["token"])
    ensure_token(files["write_token"])  # the JSON write APIs have their own token (security review #13)
    # post-build steps, each in its own module (plan items 1.2, 1.4, 1.7); they update the store and save it again
    if documents and _module("documents"):
        from . import documents as _documents
        _documents.render_all(store, files)          # fills versions[].document and signatures[].document_hash
    if hl7 and _module("hl7"):
        from . import hl7 as _hl7
        _hl7.write_feed(store, files["hl7"])         # events.hl7 from store.events
    if dicom and _module("dicom_studies"):
        from . import dicom_studies as _dicom
        _dicom.build_all(store, files["dicom"])      # synthetic DICOM per imaging study (upload is a separate step)
    store.save(files["store"], files["events"])
    return store


def _module(name):
    """True when his_mock/<name>.py exists (the post-build steps arrive with later items)."""
    return (Path(__file__).with_name(name + ".py")).exists()


def ensure_token(path):
    """The API token for 1.3: 32 random hex characters, mode 600, created only when missing."""
    import secrets

    path = Path(path)
    if path.exists():
        return path
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secrets.token_hex(16) + "\n")
    os.chmod(path, 0o600)
    return path


def build_store(fixtures, seed=DEFAULT_SEED, clock=None):
    """(Store, fixture index) in memory, nothing written."""
    built_at = iso(clock()) if clock else iso(datetime.now(IST))
    store = Store.empty(fixtures["hospital"], seed=seed, fixture_version=fixtures.get("version"), built_at=built_at,
                        clock=clock)
    _master_data(store, fixtures)
    actions = []
    index = {"fixture_version": fixtures.get("version"), "seed": seed, "slots": {}, "outside_reports": [],
             "never_ordered": []}
    for p in fixtures["patients"]:
        _plan_patient(store, p, seed, actions, index, today=fixtures["hospital"].get("today") or "2026-10-13")
    actions.sort(key=lambda a: (a[0], _PRIORITY[a[1]], a[2]))
    for _, _, _, fn in actions:
        fn()
    return store, index


# ------------------------------------------------------------------------ master data
def _master_data(store, fixtures):
    for key, spec in fixtures["tests"].items():
        store.add_test(key, spec["label"], spec["doc_type"], spec["department"])
    for d in fixtures["departments"]:
        store.add_department(d["name"], d["code"], d["group"])
    serials = {}
    for p in fixtures["patients"]:
        for r in p["records"]:
            sig = r.get("signature")
            if sig:
                serials.setdefault(sig["signer"]["reg_no"], sig["certificate_serial"])
    for d in fixtures["departments"]:
        for c in d.get("consultants", []):
            serial = serials.get(c["reg_no"]) or _generated_serial(c["reg_no"])
            store.add_practitioner(c["name"], c["qualification"], c["reg_no"], d["name"], serial)


def _generated_serial(reg_no):
    """A demo CA serial for a doctor who signs nothing in the fixtures (fixture serials use the 00A1B prefix)."""
    return f"VXDCA-00A1C{int(reg_no[-3:]):03X}"


# ------------------------------------------------------------------------ time helpers
def _at(day, hm):
    d = date.fromisoformat(str(day)[:10])
    return datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=IST)


def _t(dv):
    """A fixture {display, value} -> aware datetime (a bare date is 00:00 IST) or None."""
    return parse_time(dv["value"]) if dv else None


def _is_date_only(dv):
    return bool(dv) and len(dv["value"]) == 10


def _minute(dt):
    return dt.replace(second=0, microsecond=0)


# ------------------------------------------------------------------------ one patient
def _plan_patient(store, p, seed, actions, index, today):
    slot = p["slot"]
    rng = random.Random(f"{seed}:{slot}")
    seq = [0]

    def add(when, kind, fn):
        seq[0] += 1
        actions.append((when, kind, (slot, seq[0]), fn))

    entry = {"patient_ids": [], "encounter_ids": [], "order_ids": [], "report_ids": [], "case_files": p.get("case_files", []),
             "records": {}, "never_ordered": []}
    index["slots"][slot] = entry

    # encounters: start time of each (registration needs it)
    starts = {}
    for e in p["encounters"]:
        if e["kind"] == "OP":
            starts[e["number"]] = _at(e["date"]["value"], _VISIT_TIME)
        else:
            wh = e.get("ward_history") or []
            starts[e["number"]] = _t(wh[0]["from"]) if wh else _at(e["admitted"]["value"], _ADMISSION_TIME)

    # registrations: the permanent UHID, then a temporary or duplicate one (separate patients, no link)
    dob = _dob(p["age"], rng, today)
    address = _address(rng)
    regs = [(p["uhid"], "permanent", None)]
    for k in ("temporary_uhid", "duplicate_uhid"):
        if p.get(k):
            regs.append((p[k]["uhid"], p[k].get("kind") or k.split("_")[0], p[k]))
    slot_no = int(slot[1:])
    for i, (uhid, kind, extra) in enumerate(regs):
        first = min((starts[e["number"]] for e in p["encounters"] if e["registration"] == uhid), default=None)
        if extra and extra.get("registered_on"):
            day = extra["registered_on"]["value"]
            when = first - _REGISTRATION_LEAD if first and first.date().isoformat() == day else _at(day, (8, 0))
        else:
            when = first - _REGISTRATION_LEAD if first else _at("2026-01-01", (8, 0))
        pid = ids.patient_id(uhid)
        entry["patient_ids"].append(pid)
        kw = dict(uhid=uhid, kind=kind, dob=dob, address=address, phone=f"+91 55500 0{slot_no:02d}{i:02d}",
                  note=(extra or {}).get("note"), when=when,
                  abha=p.get("abha") if kind == "permanent" else None,
                  pmjay_id=p.get("pmjay_id") if kind == "permanent" else None)
        add(when, "register", lambda kw=kw: store.register_patient(p["name"], p["sex"], p["age"], **kw))

    # encounters
    for e in p["encounters"]:
        eid = ids.encounter_id(e["number"])
        entry["encounter_ids"].append(eid)
        pid = ids.patient_id(e["registration"])
        cons = ids.practitioner_id(e["consultant"]["reg_no"]) if e.get("consultant") else None
        start = starts[e["number"]]
        if e["kind"] == "OP":
            add(start, "visit", lambda e=e, pid=pid, cons=cons, start=start: store.open_visit(
                pid, e["department"], op_no=e["number"], unit=e.get("unit"), consultant_id=cons,
                visit_type=e.get("visit_type"), when=start, note=e.get("note")))
            continue
        wh = e.get("ward_history") or []
        ward, bed = (wh[0]["ward"], wh[0]["bed"]) if wh else (e["ward"], e["bed"])
        pre = e.get("pmjay_preauth")
        pre = {"status": pre.get("status"), "date": (pre.get("date") or {}).get("value")} if pre else None
        add(start, "admit", lambda e=e, pid=pid, cons=cons, start=start, ward=ward, bed=bed, pre=pre: store.admit(
            pid, e["department"], ward, bed, ip_no=e["number"], unit=e.get("unit"), consultant_id=cons, when=start,
            pmjay_preauth=pre, note=e.get("note")))
        for w in wh[1:]:
            wt = _t(w["from"])
            add(wt, "transfer", lambda e=e, w=w, wt=wt: store.transfer_ward(_eid(e), w["ward"], w["bed"],
                                                                             w.get("reason"), when=wt))
        for ref in e.get("referrals", []):
            rday = (ref.get("on") or ref.get("date"))["value"]
            rt = max(_at(rday, _REFERRAL_TIME), start + timedelta(hours=1))
            add(rt, "refer", lambda e=e, ref=ref, rt=rt: store.refer(_eid(e), ref["from"], ref["to"], ref.get("reason"),
                                                                     when=rt))
            if ref.get("status") == "accepted":
                at = max(_at(rday, _ACCEPT_TIME), rt + timedelta(hours=1))
                add(at, "accept", lambda e=e, ref=ref, at=at: store.accept_referral(_eid(e), ref["to"], when=at))
        if e.get("discharged"):
            dt = _at(e["discharged"]["value"], _DISCHARGE_TIME)
            add(dt, "discharge", lambda e=e, dt=dt: store.discharge(_eid(e), when=dt))

    # records
    per_encounter = {}
    for r in p["records"]:
        rid = r["id"]
        if r.get("source") == "outside_upload":
            index["outside_reports"].append({"slot": slot, "patient_id": ids.patient_id(p["uhid"]), "record": r})
            entry["records"][rid] = {"order_id": None, "report_id": None, "in_store": False, "why": "outside_upload"}
            continue
        if r.get("order_status") == "never_ordered":
            index["never_ordered"].append({"slot": slot, "patient_id": ids.patient_id(p["uhid"]), "record": r})
            entry["never_ordered"].append(rid)
            entry["records"][rid] = {"order_id": None, "report_id": None, "in_store": False, "why": "never_ordered"}
            continue
        n = per_encounter.get(r["encounter"], 0)
        per_encounter[r["encounter"]] = n + 1
        enc_dept = next(e["department"] for e in p["encounters"] if e["number"] == r["encounter"])
        oid, rep = _plan_record(store, p, r, starts[r["encounter"]], enc_dept, n, add)
        entry["order_ids"].append(oid)
        if rep:
            entry["report_ids"].append(rep)
        entry["records"][rid] = {"order_id": oid, "report_id": rep, "in_store": True}


def _eid(e):
    return ids.encounter_id(e["number"])


def _plan_record(store, p, r, enc_start, enc_dept, n, add):
    """Queue the order's steps; returns (order id, report id or None)."""
    oid = ids.order_id(r.get("accession"), r["id"])
    rep_id = r["id"].lower()
    pid = ids.patient_id(r.get("registration") or p["uhid"])
    eid = ids.encounter_id(r["encounter"])
    doc_type = r["type"]
    status, rstatus = r["order_status"], r["report_status"]
    versions = r.get("versions") or []
    first_report = _t(versions[0]["reported_on"]) if versions else _t(r.get("reported_on"))
    collected = _t(r.get("sample_collected_on"))
    cancelled = None
    if r.get("cancelled_on"):
        cancelled = _at(r["cancelled_on"]["value"], _CANCEL_TIME) if _is_date_only(r["cancelled_on"]) else _t(r["cancelled_on"])

    # when the order was placed
    day = r["ordered_on"]["value"]
    base = enc_start + timedelta(minutes=30) if enc_start.date().isoformat() == day else _at(day, _ORDER_TIME)
    base += timedelta(minutes=2 * n)
    nxt = min([t for t in (collected, first_report, cancelled) if t], default=None)
    if nxt and base >= nxt - timedelta(minutes=10):
        base = nxt - timedelta(minutes=30)
        if base <= enc_start < nxt:
            base = enc_start + (nxt - enc_start) / 3
    base = _minute(base)

    # intermediate steps between the order and its first result: booking (imaging) and sample collection
    imaging = doc_type in IMAGING_MODALITY
    do_schedule = imaging and status in ("completed", "scheduled") or status == "scheduled"
    do_collect = bool(r.get("sample_barcode")) and status in ("completed", "sample_collected")
    steps = [s for s, on in (("schedule", do_schedule), ("collect", do_collect)) if on]
    end = nxt or base + timedelta(minutes=15 * (len(steps) + 1))
    # each step 20 minutes after the previous one, squeezed evenly when the result came sooner
    times = {s: _minute(base + min((end - base) * (i + 1) / (len(steps) + 1), timedelta(minutes=20 * (i + 1))))
             for i, s in enumerate(steps)}
    if collected:
        times["collect"] = collected

    # a clinical record is written by its own department; an investigation is ordered by the unit of the visit / admission
    ordering = r["producing_department"] if store.tests[r["test"]]["department"] == "any_treating" else enc_dept
    add(base, "order", lambda: store.place_order(pid, eid, r["test"], ordering, ordered_on=base,
                                                 accession=r.get("accession"), order_id=oid,
                                                 performing_department=r["producing_department"], allocate_accession=False))
    if "schedule" in times:
        sched_for = (r.get("scheduled_for") or {}).get("value") or (first_report or times["schedule"]).date().isoformat()
        ts = times["schedule"]
        add(ts, "schedule", lambda: store.schedule(oid, sched_for, when=ts))
    if "collect" in times:
        tc = times["collect"]
        received = tc + min(timedelta(minutes=15), ((nxt - tc) / 2) if nxt and nxt > tc else timedelta(minutes=15))
        add(tc, "collect", lambda: store.collect_sample(oid, barcode=r["sample_barcode"], block_no=r.get("block_no"),
                                                        when=tc, received_on=_minute(received)))

    report_kw = dict(report_id=rep_id, title=r.get("title"), omitted_values=r.get("omitted_values"),
                     observation_values=r.get("observation_values"))
    by = ids.practitioner_id(r["reported_by"]["reg_no"]) if r.get("reported_by") else None
    sig = r.get("signature") or {}
    signer = ids.practitioner_id(sig["signer"]["reg_no"]) if sig else by
    vstatus = sig.get("verification_status") or "verified"
    made_report = None
    if rstatus == "preliminary":
        add(first_report, "preliminary", lambda: store.report_preliminary(oid, by, r["values"], when=first_report,
                                                                          **report_kw))
        made_report = rep_id
    elif rstatus == "final":
        when = _t(sig["signed_at"]) if sig else first_report
        add(when, "final", lambda: store.sign_final(oid, signer, values=r["values"], when=when,
                                                    apply_signature=bool(r.get("signed")), verification_status=vstatus,
                                                    **report_kw))
        made_report = rep_id
    elif rstatus == "amended":
        v0 = versions[0]
        t0 = _t(v0["reported_on"])
        add(t0, "final", lambda: store.sign_final(oid, signer, values=v0["values"], when=t0,
                                                  apply_signature=bool(v0.get("signed", True)), **report_kw))
        for v in versions[1:]:
            tv = _t(v["reported_on"])
            add(tv, "amend", lambda v=v, tv=tv: store.amend(rep_id, signer, v["values"], v.get("amendment_note"), when=tv,
                                                            verification_status=vstatus))
        made_report = rep_id
    elif rstatus == "cancelled" and r.get("reported_on"):
        add(first_report, "preliminary", lambda: store.report_preliminary(oid, by, r["values"], when=first_report,
                                                                          **report_kw))
        made_report = rep_id
    if status == "cancelled":
        add(cancelled, "cancel", lambda: store.cancel_order(oid, r.get("cancel_reason"), when=cancelled))
    return oid, made_report


# ------------------------------------------------------------------------ demographics
def _dob(age, rng, today):
    """A date of birth that gives exactly `age` completed years on the hospital's today."""
    t = date.fromisoformat(today)
    anniversary = t.replace(year=t.year - int(age))
    return (anniversary - timedelta(days=rng.randint(1, 364))).isoformat()


def _address(rng):
    town, district, state = rng.choice(_TOWNS)
    return {
        "line": f"H. No. {rng.randint(1, 48)}-{rng.randint(1, 30)}, {rng.choice(('1st', '2nd', '3rd', '4th'))} Cross, "
                f"{rng.choice(_LOCALITIES)}",
        "town": town,
        "district": district,
        "state": state,
        "pin": f"5{rng.randint(10, 99)}{rng.randint(100, 999)}",
    }
