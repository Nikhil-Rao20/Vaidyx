"""The mock hospital's data model (plan item V2-1.1): one JSON store for an Indian HIS with LIS, RIS and pathology modules.
SYNTHETIC data only. Pure stdlib; no FastAPI, no import of tumour_board.

Tables (dicts keyed by deterministic id): departments, practitioners, tests (the service master), patients (one entry per
registration, so a temporary or duplicate UHID is a separate patient with no link), encounters (OP visits and IP admissions),
orders (ServiceRequest), specimens, reports (DiagnosticReport, every version kept), signatures, imaging_studies, and an
append-only events list (HL7 v2-style ORM / ORU / ADT records that 1.4 renders).

Clinical state changes only through the transition methods of Store (register_patient, open_visit, admit, transfer_ward,
refer, accept_referral, discharge, place_order, schedule, collect_sample, report_preliminary, sign_final, amend,
cancel_order). Each one checks the lifecycle (research/indian_his.md: ordered -> scheduled / sample_collected ->
preliminary -> final -> amended; cancel from any state before final), sets meta.lastUpdated to its time (`when=`, else
Store.now()), increments meta.versionId and appends exactly one event.
"""
import copy
import json
import os
import re
from datetime import datetime
from pathlib import Path

from . import ids
from .ids import IST, display_date, display_time, iso, iso_date, parse_time, slug
from .paths import STORE_PATH, EVENTS_NAME

SCHEMA_VERSION = 1
MARKER = "SYNTHETIC"
CA_NAME = "Vaidyx Demo CA"
TIMEZONE = "+05:30"

TABLES = ("departments", "practitioners", "tests", "patients", "encounters", "orders", "specimens", "reports",
          "signatures", "imaging_studies")

ORDER_STATUSES = ("ordered", "scheduled", "sample_collected", "completed", "cancelled")
REPORT_STATUSES = ("preliminary", "final", "amended", "cancelled")
OPEN_ORDER = ("ordered", "scheduled", "sample_collected")  # before any report: can be scheduled, sampled, reported, cancelled
REGISTRATION_KINDS = ("permanent", "temporary", "duplicate")

# document type -> DICOM modality, for the orders that get an ImagingStudy
IMAGING_MODALITY = {"ct": "CT", "mri": "MR", "xray": "CR", "ultrasound": "US", "mammogram": "MG", "pet_ct": "PT",
                    "bone_scan": "NM"}
TISSUE_DOC_TYPES = {"histopathology", "ihc", "molecular", "cytology"}
# document types that never get an accession No. by default (clinical records written by the treating unit)
NO_ACCESSION_DOC_TYPES = {"clinical_note", "referral", "discharge_summary"}

# HL7 v2 status letters. OBR-25 (result status) on every order / result event; ORC-5 (order status) on order events.
OBR25 = {"placed": "O", "scheduled": "S", "sample_collected": "I", "preliminary": "P", "final": "F", "amended": "C",
         "cancelled": "X"}
ORC5 = {"placed": "IP", "scheduled": "SC", "sample_collected": "IP", "cancelled": "CA"}


class LifecycleError(ValueError):
    """A transition the HIS would not allow (wrong state, unknown id, a junior resident signing)."""


class Store:
    """The hospital's data: one JSON document. Load, change through the transitions, save."""

    def __init__(self, data, path=None, clock=None):
        self.data = data
        self.path = Path(path) if path else None
        self.clock = clock          # callable returning a datetime / ISO string; tests inject a fixed clock
        self.render_hook = None     # callable(report, version) -> {path, sha256}; 1.2 / 1.5 plug the PDF renderer in

    # ---------------------------------------------------------------- persistence
    @classmethod
    def load(cls, path=STORE_PATH, clock=None):
        path = Path(path)
        return cls(json.loads(path.read_text(encoding="utf-8")), path=path, clock=clock)

    @classmethod
    def empty(cls, hospital, seed=2026, fixture_version=None, built_at=None, clock=None):
        """A store with the hospital settings and nothing else (fixtures' `hospital` block)."""
        h = {
            "id": "org-vaidyx-demo-hospital",
            "name": hospital.get("name") or "Vaidyx Demo Hospital (SYNTHETIC)",
            "ncg_level": hospital.get("ncg_level"),
            "pmjay_empanelled": hospital.get("pmjay_empanelled"),
            "fetch_window_months": hospital.get("fetch_window_months"),
            "surgical_oncology_list": list(hospital.get("surgical_oncology_list") or []),
            "board_heads": list(hospital.get("board_heads") or []),
            "today": hospital.get("today"),
            "timezone": TIMEZONE,
            "marker": MARKER,
        }
        if MARKER not in h["name"]:
            raise ValueError("the mock hospital's name must say SYNTHETIC")
        data = {
            "meta": {"seed": seed, "fixture_version": fixture_version, "built_at": built_at, "schema_version": SCHEMA_VERSION,
                     "marker": MARKER, "counters": {}},
            "hospital": h,
        }
        for t in TABLES:
            data[t] = {}
        data["events"] = []
        store = cls(data, clock=clock)
        if built_at is None:
            data["meta"]["built_at"] = store.now()
        return store

    def save(self, path=None, events_path=None):
        """Write store.json atomically (temporary file, then rename) and events.jsonl next to it."""
        path = Path(path or self.path or STORE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(self.data, indent=1, ensure_ascii=False) + "\n")
        events_path = Path(events_path) if events_path else path.parent / EVENTS_NAME
        _atomic_write(events_path, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self.data["events"]))
        self.path = path
        return path

    def now(self):
        """The current time as ISO with +05:30 (the injected clock when set)."""
        return iso(self.clock() if self.clock else datetime.now(IST))

    # ---------------------------------------------------------------- tables (properties, defined below the class)

    # ---------------------------------------------------------------- master data (setup, no events)
    def add_department(self, name, code, group, email=None):
        did = ids.department_id(code)
        self.departments[did] = {"id": did, "name": name, "code": code, "group": group, "consultants": [],
                                 "email": email or f"{code.lower()}@vaidyx-demo.invalid"}
        return self.departments[did]

    def add_practitioner(self, name, qualification, reg_no, department, certificate_serial, role=None):
        if not ids.PATTERNS["reg_no"].match(reg_no):
            raise ValueError(f"Reg. No. {reg_no!r} is not a VXREG- number")
        if not ids.PATTERNS["certificate_serial"].match(certificate_serial):
            raise ValueError(f"certificate serial {certificate_serial!r} is not a VXDCA- serial")
        dept = self.department(department)
        if not dept:
            raise ValueError(f"unknown department {department!r}")
        pid = ids.practitioner_id(reg_no)
        role = role or ("junior_resident" if "junior resident" in qualification.lower() else "consultant")
        self.practitioners[pid] = {"id": pid, "name": name, "qualification": qualification, "reg_no": reg_no,
                                   "department": dept["name"], "role": role, "certificate_serial": certificate_serial}
        if pid not in dept["consultants"]:
            dept["consultants"].append(pid)
        return self.practitioners[pid]

    def add_test(self, key, label, doc_type, department):
        self.tests[key] = {"id": key, "label": label, "doc_type": doc_type, "department": department}
        return self.tests[key]

    # ---------------------------------------------------------------- lookups
    def department(self, name):
        """Department by name, code or id (None when unknown)."""
        if not name:
            return None
        key = str(name).strip().lower()
        for d in self.departments.values():
            if key in (d["name"].lower(), d["code"].lower(), d["id"]):
                return d
        return None

    def practitioner(self, pid):
        """Practitioner by id (prac-vxreg-20104) or Reg. No. (VXREG-20104)."""
        if not pid:
            return None
        return self.practitioners.get(pid) or self.practitioners.get(ids.practitioner_id(pid))

    def report(self, rid):
        return self.reports.get(rid)

    @staticmethod
    def current_version(report):
        """The report's current version (the latest; earlier ones stay in report['versions'])."""
        return next(v for v in report["versions"] if v["version"] == report["current_version"])

    def patient_by_identifier(self, value):
        """UHID (permanent or temporary), IP No., OP No., ABHA number or address, or a patient id -> patient or None."""
        if not value:
            return None
        v = str(value).strip()
        key = v.upper()
        if v in self.patients:
            return self.patients[v]
        for p in self.patients.values():
            if p["uhid"].upper() == key:
                return p
        enc = self.encounters.get(ids.encounter_id(v))
        if enc and enc["number"].upper() == key:
            return self.patients.get(enc["patient_id"])
        for p in self.patients.values():
            abha = p.get("abha") or {}
            if v in (abha.get("number"), abha.get("address")):
                return p
        return None

    def patients_by_name(self, name, sex=None, age=None, tolerance=0):
        """Registrations whose name matches (case-insensitive, "(SYNTHETIC)" ignored), optionally the same sex and an age
        within `tolerance` years."""
        want = _plain_name(name)
        out = []
        for p in self.patients.values():
            if _plain_name(p["name"]) != want:
                continue
            if sex and p["sex"] != sex:
                continue
            if age is not None and abs(int(p["age"]) - int(age)) > tolerance:
                continue
            out.append(p)
        return out

    def similar_registrations(self, patient_id):
        """Other registrations with the same name, sex and age: how a person spots a temporary or duplicate UHID. Never
        linked or merged automatically."""
        p = self.patients[patient_id]
        return [q for q in self.patients_by_name(p["name"], sex=p["sex"], age=p["age"]) if q["id"] != patient_id]

    def encounters_for(self, patient_id):
        """The registration's encounters, oldest first."""
        return sorted((e for e in self.encounters.values() if e["patient_id"] == patient_id), key=_encounter_start)

    def orders_for(self, patient_id=None, encounter_id=None, department=None, status=None):
        """Orders filtered by patient, encounter, department (performing or ordering) and status."""
        dept = self.department(department) if department else None
        if department and not dept:
            return []
        out = []
        for o in self.orders.values():
            if patient_id and o["patient_id"] != patient_id:
                continue
            if encounter_id and o["encounter_id"] != encounter_id:
                continue
            if dept and dept["name"] not in (o["performing_department"], o["ordering_department"]):
                continue
            if status and o["status"] != status:
                continue
            out.append(o)
        return out

    def reports_for(self, patient_id=None, since=None, encounter_id=None):
        """Reports of a patient / encounter; with `since`, only those whose meta.lastUpdated is strictly later."""
        cut = parse_time(since) if since else None
        out = []
        for r in self.reports.values():
            if patient_id and r["patient_id"] != patient_id:
                continue
            if encounter_id and r["encounter_id"] != encounter_id:
                continue
            if cut and not parse_time(r["meta"]["lastUpdated"]) > cut:
                continue
            out.append(r)
        return out

    def pending_for_department(self, dept):
        """The reporting desk's work list: open orders the department performs and its preliminary reports."""
        d = self.department(dept)
        if not d:
            return {"orders": [], "reports": []}
        orders = [o for o in self.orders.values() if o["performing_department"] == d["name"] and o["status"] in OPEN_ORDER]
        reports = [r for r in self.reports.values() if self.orders[r["order_id"]]["performing_department"] == d["name"]
                   and (r["status"] == "preliminary" or (r["status"] == "final" and not self.current_version(r).get("signature_id")))]  # awaiting signature too
        return {"orders": orders, "reports": reports}

    def imaging_study_for(self, order_id):
        o = self.orders.get(order_id)
        return self.imaging_studies.get(o["imaging_study_id"]) if o and o.get("imaging_study_id") else None

    def report_for_order(self, order_id):
        o = self.orders.get(order_id)
        return self.reports.get(o["report_id"]) if o and o.get("report_id") else None

    # ---------------------------------------------------------------- registration and encounters
    def register_patient(self, name, sex, age, *, uhid=None, kind="permanent", dob=None, abha=None, pmjay_id=None,
                         address=None, phone=None, note=None, when=None):
        """A new registration (ADT A28). `uhid` is allocated when not given; `dob` is an ISO date."""
        if MARKER not in str(name):
            raise ValueError("every mock patient's name carries (SYNTHETIC)")
        if sex not in ("F", "M"):
            raise ValueError("sex must be F or M")
        if kind not in REGISTRATION_KINDS:
            raise ValueError(f"registration kind must be one of {REGISTRATION_KINDS}")
        t = self._when(when)
        yy = t[2:4]
        if uhid:
            pattern = "temporary_uhid" if kind == "temporary" else "uhid"
            if not ids.PATTERNS[pattern].match(uhid):
                raise ValueError(f"UHID {uhid!r} does not match the {pattern} pattern")
            self._note_counter(uhid.rsplit("/", 1)[0], uhid.rsplit("/", 1)[1])
        else:
            uhid = self._allocate(f"VXH/T/{yy}" if kind == "temporary" else f"VXH/{yy}", 5 if kind == "temporary" else 6, "/")
        pid = ids.patient_id(uhid)
        if pid in self.patients:
            raise LifecycleError(f"UHID {uhid} is already registered")
        if kind != "permanent" and abha:
            raise ValueError("ABHA is linked to the permanent registration only")
        self.patients[pid] = {
            "id": pid, "uhid": uhid, "registration_kind": kind, "name": name, "sex": sex, "age": int(age),
            "dob": display_date(dob) if dob else None, "dob_iso": iso_date(dob) if dob else None,
            "abha": dict(abha) if abha else None, "pmjay_id": pmjay_id, "address": dict(address) if address else None,
            "phone": phone, "registered_on": iso_date(t), "marker": MARKER, "note": note, "meta": _meta(t),
        }
        self._event("ADT", "A28", t, refs={"patient_id": pid},
                    text=f"Registration {uhid} ({kind}) {name}, {age} Y / {sex}")
        return self.patients[pid]

    def open_visit(self, patient_id, department, *, op_no=None, unit="Unit I", consultant_id=None, visit_type="new",
                   when=None, note=None):
        """An OP visit (ADT A04): OP No. allocated when not given."""
        p = self._patient(patient_id)
        dept = self._department(department)
        t = self._when(when)
        if op_no:
            if not ids.PATTERNS["op_no"].match(op_no):
                raise ValueError(f"OP No. {op_no!r} does not match OP/<yy>/<6 digits>")
            self._note_counter(*op_no.rsplit("/", 1))
        else:
            op_no = self._allocate(f"OP/{t[2:4]}", 6, "/")
        eid = self._new_encounter_id(op_no)
        self.encounters[eid] = {
            "id": eid, "kind": "OP", "number": op_no, "patient_id": p["id"], "department": dept["name"], "unit": unit,
            "consultant_id": self._practitioner_id(consultant_id), "visit_type": visit_type, "date": iso_date(t),
            "admitted": None, "discharged": None, "ward": None, "bed": None, "ward_history": [], "referrals": [],
            "pmjay_preauth": None, "status": "finished", "class": "AMB", "note": note, "meta": _meta(t),
        }
        self._event("ADT", "A04", t, refs={"patient_id": p["id"], "encounter_id": eid},
                    text=f"OP visit {op_no}, {dept['name']} {unit}, {visit_type}")
        return self.encounters[eid]

    def admit(self, patient_id, department, ward, bed, *, ip_no=None, unit="Unit I", consultant_id=None, when=None,
              pmjay_preauth=None, note=None):
        """An IP admission (ADT A01): IP No. allocated when not given; `pmjay_preauth` = {status, date}."""
        p = self._patient(patient_id)
        dept = self._department(department)
        t = self._when(when)
        if ip_no:
            if not ids.PATTERNS["ip_no"].match(ip_no):
                raise ValueError(f"IP No. {ip_no!r} does not match IP/<yy>/<5 digits>")
            self._note_counter(*ip_no.rsplit("/", 1))
        else:
            ip_no = self._allocate(f"IP/{t[2:4]}", 5, "/")
        eid = self._new_encounter_id(ip_no)
        pre = None
        if pmjay_preauth:
            pre = {"status": pmjay_preauth.get("status"),
                   "date": iso_date(pmjay_preauth["date"]) if pmjay_preauth.get("date") else None}
        self.encounters[eid] = {
            "id": eid, "kind": "IP", "number": ip_no, "patient_id": p["id"], "department": dept["name"], "unit": unit,
            "consultant_id": self._practitioner_id(consultant_id), "visit_type": None, "date": None,
            "admitted": iso_date(t), "discharged": None, "ward": ward, "bed": bed,
            "ward_history": [{"ward": ward, "bed": bed, "from": t, "reason": None}], "referrals": [],
            "pmjay_preauth": pre, "status": "in-progress", "class": "IMP", "note": note, "meta": _meta(t),
        }
        self._event("ADT", "A01", t, refs={"patient_id": p["id"], "encounter_id": eid},
                    text=f"Admission {ip_no}, {dept['name']} {unit}, {ward} bed {bed}")
        return self.encounters[eid]

    def transfer_ward(self, encounter_id, ward, bed, reason=None, when=None):
        """Move an admitted patient to another ward / bed (ADT A02); the earlier locations stay in ward_history."""
        e = self._admission(encounter_id)
        t = self._when(when)
        e["ward_history"].append({"ward": ward, "bed": bed, "from": t, "reason": reason})
        e["ward"], e["bed"] = ward, bed
        _bump(e, t)
        self._event("ADT", "A02", t, refs={"patient_id": e["patient_id"], "encounter_id": e["id"]},
                    text=f"Transfer {e['number']} to {ward} bed {bed}" + (f": {reason}" if reason else ""))
        return e

    def refer(self, encounter_id, from_dept, to_dept, reason, when=None):
        """Inter-department referral on an encounter (event REF I12), status requested."""
        e = self._encounter(encounter_id)
        a, b = self._department(from_dept), self._department(to_dept)
        if a["name"] == b["name"]:
            raise LifecycleError("a referral goes to another department")
        t = self._when(when)
        e["referrals"].append({"from": a["name"], "to": b["name"], "on": iso_date(t), "reason": reason,
                               "status": "requested", "accepted_on": None})
        _bump(e, t)
        self._event("REF", "I12", t, refs={"patient_id": e["patient_id"], "encounter_id": e["id"]},
                    text=f"Referral {e['number']} from {a['name']} to {b['name']}")
        return e["referrals"][-1]

    def accept_referral(self, encounter_id, to_dept, when=None):
        """The receiving department accepts the open referral addressed to it (event REF I13)."""
        e = self._encounter(encounter_id)
        b = self._department(to_dept)
        ref = next((r for r in e["referrals"] if r["to"] == b["name"] and r["status"] == "requested"), None)
        if not ref:
            raise LifecycleError(f"no open referral to {b['name']} on {e['number']}")
        t = self._when(when)
        ref["status"], ref["accepted_on"] = "accepted", iso_date(t)
        _bump(e, t)
        self._event("REF", "I13", t, refs={"patient_id": e["patient_id"], "encounter_id": e["id"]},
                    text=f"Referral {e['number']} accepted by {b['name']}")
        return ref

    def discharge(self, encounter_id, when=None):
        """Discharge an admitted patient (ADT A03)."""
        e = self._admission(encounter_id)
        t = self._when(when)
        e["discharged"], e["status"] = iso_date(t), "finished"
        _bump(e, t)
        self._event("ADT", "A03", t, refs={"patient_id": e["patient_id"], "encounter_id": e["id"]},
                    text=f"Discharge {e['number']}")
        return e

    # ---------------------------------------------------------------- orders, samples, reports
    def place_order(self, patient_id, encounter_id, test, ordering_department, ordered_on=None, accession=None, *,
                    order_id=None, performing_department=None, allocate_accession=None):
        """A new order (ORM O01, OBR-25 O). The accession No. <dept code>/<yy>/<5 digits> is allocated from a per-department
        counter when not given (for clinical records, by default, none is allocated)."""
        p = self._patient(patient_id)
        e = self._encounter(encounter_id)
        if e["patient_id"] != p["id"]:
            raise LifecycleError(f"encounter {e['number']} belongs to another registration")
        spec = self.tests.get(test)
        if not spec:
            raise LifecycleError(f"unknown test {test!r}")
        ordering = self._department(ordering_department)["name"]
        if performing_department:
            performing = self._department(performing_department)["name"]
        elif spec["department"] == "any_treating":
            performing = ordering
        else:
            performing = spec["department"]
        perf = self.department(performing)
        t = self._when(ordered_on)
        if allocate_accession is None:
            allocate_accession = spec["department"] != "any_treating" and spec["doc_type"] not in NO_ACCESSION_DOC_TYPES
        if accession:
            if not ids.PATTERNS["accession"].match(accession):
                raise ValueError(f"accession {accession!r} does not match <code>/<yy>/<5 digits>")
            if any(o["accession"] == accession for o in self.orders.values()):
                raise LifecycleError(f"accession {accession} is already in use")
            self._note_counter(*accession.rsplit("/", 1))
        elif allocate_accession:
            accession = self._allocate(f"{perf['code']}/{t[2:4]}", 5, "/")
        oid = order_id or (ids.order_id(accession) if accession else self._allocate("ord", 6, "-"))
        if oid in self.orders:
            raise LifecycleError(f"order {oid} exists")
        self.orders[oid] = {
            "id": oid, "accession": accession, "patient_id": p["id"], "encounter_id": e["id"], "test": test,
            "label": spec["label"], "doc_type": spec["doc_type"], "ordering_department": ordering,
            "performing_department": performing, "status": "ordered", "ordered_on": t, "scheduled_for": None,
            "sample_collected_on": None, "cancelled_on": None, "cancel_reason": None, "report_id": None,
            "specimen_id": None, "imaging_study_id": None, "meta": _meta(t),
        }
        self._order_event("placed", self.orders[oid], t, f"Order {accession or oid} {spec['label']} by {ordering}")
        return self.orders[oid]

    def schedule(self, order_id, date, when=None):
        """RIS / department booking (ORM O01, ORC-5 SC). Imaging orders get their ImagingStudy here."""
        o = self._order(order_id)
        if o["status"] not in ("ordered", "scheduled"):
            raise LifecycleError(f"order {o['id']} is {o['status']}; only an ordered or scheduled order can be scheduled")
        t = self._when(when)
        o["status"], o["scheduled_for"] = "scheduled", iso_date(date) if len(str(date)) == 10 else iso(date)
        self._ensure_imaging_study(o, o["scheduled_for"], t)
        study = self.imaging_study_for(o["id"])
        if study and study["status"] == "registered" and not study.get("series") and study["started"] != o["scheduled_for"]:
            study["started"] = o["scheduled_for"]          # rescheduled before acquisition: the study moves with it
            _bump(study, t)
        _bump(o, t)
        self._order_event("scheduled", o, t, f"Order {o['accession'] or o['id']} scheduled for {o['scheduled_for']}")
        return o

    def collect_sample(self, order_id, barcode=None, block_no=None, when=None, received_on=None):
        """LIS sample collection with a barcode (ORM O01, OBR-25 I); creates the Specimen."""
        o = self._order(order_id)
        if o["status"] not in ("ordered", "scheduled"):
            raise LifecycleError(f"order {o['id']} is {o['status']}; a sample is collected on an open order")
        t = self._when(when)
        if barcode:
            if not ids.PATTERNS["sample_barcode"].match(barcode):
                raise ValueError(f"barcode {barcode!r} does not match VXS<8 digits>")
            self._note_counter(barcode[:5], barcode[5:])
        else:
            barcode = self._allocate(f"VXS{t[2:4]}", 6, "")
        sid = ids.specimen_id(barcode)
        if sid in self.specimens:
            raise LifecycleError(f"barcode {barcode} is already in use")
        tissue = block_no or o["doc_type"] in TISSUE_DOC_TYPES
        self.specimens[sid] = {
            "id": sid, "order_id": o["id"], "patient_id": o["patient_id"], "barcode": barcode, "block_no": block_no,
            "type": "tissue" if tissue else "blood", "collected_on": t, "received_on": iso(received_on) if received_on else t,
            "status": "available", "meta": _meta(t),
        }
        o["status"], o["sample_collected_on"], o["specimen_id"] = "sample_collected", t, sid
        _bump(o, t)
        self._order_event("sample_collected", o, t, f"Sample {barcode} collected for {o['accession'] or o['id']}")
        return self.specimens[sid]

    def report_preliminary(self, order_id, by, values, sections=None, when=None, *, report_id=None, title=None,
                           omitted_values=None, observation_values=None):
        """Result entry before verification (ORU R01, OBR-25 P): the report's first version, status preliminary."""
        o = self._order(order_id)
        if o["status"] not in OPEN_ORDER or o.get("report_id"):
            raise LifecycleError(f"order {o['id']} is {o['status']}; a preliminary report needs an open order")
        prac = self._practitioner(by)
        t = self._when(when)
        r = self._new_report(o, report_id, title, t, omitted_values, observation_values)
        r["versions"].append(_version(1, "preliminary", t, prac["id"], values, sections))
        r["current_version"], r["status"] = 1, "preliminary"
        self._complete_order(o, r, t)
        self._result_event("preliminary", r, t, f"Preliminary report {r['id']} by {prac['name']}")
        return r

    def sign_final(self, order_id_or_report_id, by, values=None, sections=None, when=None, document=None, *, report_id=None,
                   title=None, apply_signature=True, omitted_values=None, observation_values=None,
                   verification_status="verified"):
        """Verification and digital signature (ORU R01, OBR-25 F). On a preliminary report this adds a new final version
        (the preliminary stays in history); on an open order it creates the report with a final first version; on a report
        marked final whose signature was never applied, signing adds a new signed final version (the unsigned one stays in
        history). `apply_signature=False` records a report marked final whose signature was never applied."""
        r = self.reports.get(order_id_or_report_id)
        o = self.orders[r["order_id"]] if r else self._order(order_id_or_report_id)
        r = r or self.report_for_order(o["id"])
        prac = self._practitioner(by)
        if apply_signature and prac["role"] != "consultant":
            raise LifecycleError(f"{prac['name']} is a junior resident; a consultant signs the final report")
        t = self._when(when)
        if r:
            prev = self.current_version(r)
            unsigned_final = r["status"] == "final" and not prev.get("signature_id")  # marked final, never signed: can still be signed
            if r["status"] != "preliminary" and not (unsigned_final and apply_signature):
                raise LifecycleError(f"report {r['id']} is {r['status']}; use amend for a signed report")
            _bump(r, t)
            n = prev["version"] + 1
            vals = values if values is not None else prev["values"]
            secs = sections if sections is not None else prev["sections"]
            if omitted_values is not None:
                r["omitted_values"] = list(omitted_values)
            if observation_values is not None:
                r["observation_values"] = dict(observation_values)
        else:
            if o["status"] not in OPEN_ORDER:
                raise LifecycleError(f"order {o['id']} is {o['status']}; it cannot be reported")
            r = self._new_report(o, report_id, title, t, omitted_values, observation_values)
            n, vals, secs = 1, values or {}, sections
        v = _version(n, "final", t, prac["id"], vals, secs)
        r["versions"].append(v)
        r["current_version"], r["status"] = n, "final"
        if apply_signature:
            self._sign(r, v, prac, t, verification_status)
        self._attach_document(r, v, document)
        self._complete_order(o, r, t)
        self._result_event("final", r, t, f"Final report {r['id']} " + (f"signed by {prac['name']}" if apply_signature
                                                                           else "marked final, not signed"))
        return r

    def amend(self, report_id, by, values, note, when=None, sections=None, document=None, verification_status="verified"):
        """Addendum / correction after signing (ORU R01, OBR-25 C): a new signed version, status amended; earlier versions
        are kept."""
        r = self.reports.get(report_id)
        if not r:
            raise LifecycleError(f"unknown report {report_id!r}")
        if r["status"] not in ("final", "amended"):
            raise LifecycleError(f"report {r['id']} is {r['status']}; only a final report can be amended")
        prac = self._practitioner(by)
        if prac["role"] != "consultant":
            raise LifecycleError(f"{prac['name']} is a junior resident; a consultant signs the amendment")
        t = self._when(when)
        prev = self.current_version(r)
        v = _version(prev["version"] + 1, "amended", t, prac["id"], values if values is not None else prev["values"],
                     sections if sections is not None else prev["sections"])
        v["amendment_note"] = note
        r["versions"].append(v)
        r["current_version"], r["status"] = v["version"], "amended"
        self._sign(r, v, prac, t, verification_status)
        self._attach_document(r, v, document)
        _bump(r, t)
        self._result_event("amended", r, t, f"Amended report {r['id']} v{v['version']} signed by {prac['name']}")
        return r

    def cancel_order(self, order_id, reason, when=None):
        """Cancel an order before a final report (OBR-25 X, ORC-5 CA). A preliminary report is cancelled with it."""
        o = self._order(order_id)
        r = self.report_for_order(o["id"])
        if o["status"] == "cancelled":
            raise LifecycleError(f"order {o['id']} is already cancelled")
        if o["status"] == "completed" and not (r and r["status"] == "preliminary"):
            raise LifecycleError(f"order {o['id']} is completed with a {r['status'] if r else 'missing'} report; "
                                 "a signed report is amended, not cancelled")
        t = self._when(when)
        o["status"], o["cancelled_on"], o["cancel_reason"] = "cancelled", t, reason
        _bump(o, t)
        study = self.imaging_study_for(o["id"])
        if study:
            study["status"] = "cancelled"
            _bump(study, t)
        if r:
            prev = self.current_version(r)
            v = _version(prev["version"] + 1, "cancelled", t, None, prev["values"], prev["sections"])
            v["amendment_note"] = reason
            r["versions"].append(v)                      # the preliminary stays in history
            r["current_version"], r["status"] = v["version"], "cancelled"
            _bump(r, t)
            self._result_event("cancelled", r, t, f"Report {r['id']} cancelled: {reason}")
        else:
            self._order_event("cancelled", o, t, f"Order {o['accession'] or o['id']} cancelled: {reason}")
        return o

    # ---------------------------------------------------------------- internals
    def _when(self, when):
        return iso(when) if when else self.now()

    def _patient(self, pid):
        p = self.patients.get(pid)
        if not p:
            raise LifecycleError(f"unknown patient {pid!r}")
        return p

    def _department(self, name):
        d = self.department(name)
        if not d:
            raise LifecycleError(f"unknown department {name!r}")
        return d

    def _practitioner(self, pid):
        p = self.practitioner(pid)
        if not p:
            raise LifecycleError(f"unknown practitioner {pid!r}")
        return p

    def _practitioner_id(self, pid):
        return self._practitioner(pid)["id"] if pid else None

    def _encounter(self, eid):
        e = self.encounters.get(eid) or self.encounters.get(ids.encounter_id(eid))
        if not e:
            raise LifecycleError(f"unknown encounter {eid!r}")
        return e

    def _admission(self, eid):
        e = self._encounter(eid)
        if e["kind"] != "IP" or e["status"] != "in-progress":
            raise LifecycleError(f"{e['number']} is not a current admission")
        return e

    def _order(self, oid):
        o = self.orders.get(oid)
        if not o:
            raise LifecycleError(f"unknown order {oid!r}")
        return o

    def _new_encounter_id(self, number):
        eid = ids.encounter_id(number)
        if eid in self.encounters:
            raise LifecycleError(f"encounter {number} exists")
        return eid

    def _new_report(self, o, report_id, title, t, omitted_values, observation_values):
        rid = report_id or "rep-" + o["id"]
        if rid in self.reports:
            raise LifecycleError(f"report {rid} exists")
        r = {
            "id": rid, "order_id": o["id"], "patient_id": o["patient_id"], "encounter_id": o["encounter_id"],
            "test": o["test"], "doc_type": o["doc_type"], "title": title or o["label"], "status": None,
            "current_version": 0, "versions": [], "omitted_values": list(omitted_values or []),
            "observation_values": dict(observation_values or {}), "meta": _meta(t),
        }
        self.reports[rid] = r
        o["report_id"] = rid
        return r

    def _complete_order(self, o, r, t):
        if o["doc_type"] in IMAGING_MODALITY:
            self._ensure_imaging_study(o, o["scheduled_for"] or t, t)
        if o["status"] != "completed":
            o["status"] = "completed"
            _bump(o, t)

    def _ensure_imaging_study(self, o, started, t):
        modality = IMAGING_MODALITY.get(o["doc_type"])
        if not modality or o.get("imaging_study_id"):
            return
        key = o["accession"] or o["id"]
        sid = ids.imaging_study_id(key)
        self.imaging_studies[sid] = {
            "id": sid, "order_id": o["id"], "accession": o["accession"], "patient_id": o["patient_id"],
            "study_uid": ids.study_uid(key), "modality": modality, "description": o["label"], "started": started,
            "status": "registered", "number_of_series": 0, "number_of_instances": 0, "meta": _meta(t),
        }
        o["imaging_study_id"] = sid

    def _sign(self, r, v, prac, t, verification_status):
        sid = ids.signature_id(r["id"], v["version"])
        block = (f"Digitally signed by {prac['name']}, {prac['qualification']}, Reg. No. {prac['reg_no']}, "
                 f"{display_time(t)}, {CA_NAME}, certificate serial {prac['certificate_serial']}")
        self.signatures[sid] = {
            "id": sid, "report_id": r["id"], "version": v["version"], "signer_id": prac["id"], "signed_at": t, "ca": CA_NAME,
            "certificate_serial": prac["certificate_serial"], "document_hash": None,
            "verification_status": verification_status, "block": block,
        }
        v["signature_id"] = sid

    def _attach_document(self, r, v, document):
        if document is None and self.render_hook:
            document = self.render_hook(r, v)
        if document:
            v["document"] = {"path": document.get("path"), "sha256": document.get("sha256")}
            if v.get("signature_id"):
                self.signatures[v["signature_id"]]["document_hash"] = document.get("sha256")

    def _note_counter(self, key, number):
        """Raise the counter of a prefix (RAD/26, OP/26, VXS26) to an existing number so allocation never collides."""
        c = self.meta.setdefault("counters", {})
        c[key] = max(c.get(key, 0), int(number))

    def _allocate(self, key, width, sep):
        c = self.meta.setdefault("counters", {})
        c[key] = c.get(key, 0) + 1
        return f"{key}{sep}{c[key]:0{width}d}"

    def _event(self, kind, trigger, t, refs, text, status=None, order_status=None):
        ev = {"id": f"ev-{len(self.events) + 1:06d}", "time": t, "kind": kind, "trigger": trigger, "status": status}
        if order_status:
            ev["order_status"] = order_status
        ev["refs"] = {k: v for k, v in refs.items() if v is not None}
        ev["text"] = text
        self.events.append(ev)
        return ev

    def _order_event(self, step, o, t, text):
        return self._event("ORM", "O01", t, status=OBR25[step], order_status=ORC5[step], text=text,
                           refs={"patient_id": o["patient_id"], "encounter_id": o["encounter_id"], "order_id": o["id"]})

    def _result_event(self, step, r, t, text):
        return self._event("ORU", "R01", t, status=OBR25[step], text=text,
                           refs={"patient_id": r["patient_id"], "encounter_id": r["encounter_id"], "order_id": r["order_id"],
                                 "report_id": r["id"], "version": r["current_version"]})


for _name in TABLES + ("events", "meta", "hospital"):
    setattr(Store, _name, property(lambda self, _n=_name: self.data[_n], doc=f"The store's {_name}."))
del _name


# -------------------------------------------------------------------- module helpers
def _meta(t):
    return {"versionId": "1", "lastUpdated": t}


def _bump(rec, t):
    m = rec.setdefault("meta", _meta(t))
    m["versionId"] = str(int(m.get("versionId", "0")) + 1)
    m["lastUpdated"] = t


def _version(n, status, t, by, values, sections):
    return {"version": n, "status": status, "reported_on": t, "reported_by": by, "values": copy.deepcopy(values or {}),
            "amendment_note": None, "signature_id": None, "document": {"path": None, "sha256": None},
            "sections": copy.deepcopy(sections or {})}


def _plain_name(name):
    s = re.sub(r"\(\s*synthetic\s*\)", " ", str(name or ""), flags=re.I)
    return " ".join(s.lower().split())


def _encounter_start(e):
    if e["kind"] == "IP" and e["ward_history"]:
        return e["ward_history"][0]["from"]
    return e.get("date") or e.get("admitted") or ""


def _atomic_write(path, text):
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
