"""V2 scenario fixtures (plan item 0.3): the synthetic patients the mock hospital builds (1.1) and the outcome Vaidyx-TB must
show for each scenario (e2e in Phases 3 to 6). The data lives in scenarios.json next to this file; this module loads it and
checks it. Pure Python, no third-party imports, no import of tumour_board.

    from his_mock import scenarios
    data = scenarios.load()
    problems = scenarios.validate(data)   # [] when the fixtures are consistent
"""
import json
import re
from datetime import datetime
from pathlib import Path

PATH = Path(__file__).with_name("scenarios.json")

TOP_KEYS = ("version", "note", "identifier_patterns", "departments", "patients", "scenarios", "checklist")

# The eleven scenarios of the plan 1.1 table, in the plan's order.
PLAN_SCENARIOS = (
    "complete_workup",
    "opd_staging_ct_before_admission",
    "radiology_preliminary_only",
    "required_report_never_ordered",
    "value_missing_in_signed_report",
    "report_amended_after_signing",
    "molecular_sample_collected_result_awaited",
    "temporary_and_permanent_uhid",
    "lung_workup_referred_colorectal",
    "two_primaries",
    "outside_report_private_lab",
)
# The extra scenarios that cover the orchestration.md checklist.
CHECKLIST_SCENARIOS = (
    "entry_by_ip_or_op_no",
    "same_common_name",
    "abha_present_and_absent",
    "duplicate_permanent_uhid",
    "scanned_outside_report_aadhaar_masked",
    "ip_admission_ward_transfer",
    "report_ordered_never_reported",
    "report_cancelled",
    "unsigned_final_report",
    "observation_disagrees_with_pdf",
    "treating_department_procedure_request",
    "every_supporting_department_request",
    "board_radiology_head_absent",
    "board_medical_oncology_head_absent",
    "board_surgical_oncology_head_absent",
    "board_pathology_head_absent",
    "board_surgeon_outside_surgical_oncology_list",
    "board_pmjay_not_empanelled",
)
REQUIRED_SCENARIOS = PLAN_SCENARIOS + CHECKLIST_SCENARIOS

PROTOCOLS = ("breast", "oral_cavity", "cervix", "lung_nsclc", "colorectal_rectum")  # ids in tumour_board/protocols/
BOARD_HEADS = ("Radiology", "Medical Oncology", "Surgical Oncology", "Pathology")
PHASES = (3, 4, 5, 6)
N_TREATING, N_SUPPORTING = 22, 8
MIN_PATIENTS, MAX_PATIENTS = 15, 20

# order_status -> the report statuses it allows (lifecycle in research/indian_his.md)
LIFECYCLE = {
    "never_ordered": {"none"},
    "ordered": {"none"},
    "scheduled": {"none"},
    "sample_collected": {"none"},
    "completed": {"preliminary", "final", "amended"},
    "cancelled": {"cancelled"},
}
REQUEST_ORIGINS = {"suggested_from_gap", "doctor_initiated"}
GAP_LEVELS = {1, 2}

MASKED_AADHAAR = "XXXX XXXX 1234"
# 12 digits in a row, or 4-4-4 with spaces or hyphens, not part of a longer number (so ABHA 2-4-4-4 does not match)
AADHAAR_LIKE = re.compile(r"(?<![\w-])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\w-])")  # word-bounded: a sha256 digest is not one
DISPLAY_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})( (\d{2}):(\d{2}))?$")


def load(path=None):
    """The fixtures as a dict (scenarios.json next to this module unless a path is given)."""
    return json.loads(Path(path or PATH).read_text(encoding="utf-8"))


def by_id(data=None):
    """Scenario id -> scenario."""
    data = data or load()
    return {s["id"]: s for s in data["scenarios"]}


def patients_by_slot(data=None):
    data = data or load()
    return {p["slot"]: p for p in data["patients"]}


def patients_for(scenario, data=None):
    """The patient records a scenario (dict or id) uses, in the scenario's order."""
    data = data or load()
    if isinstance(scenario, str):
        scenario = by_id(data)[scenario]
    slots = patients_by_slot(data)
    return [slots[s] for s in scenario["patients"] if s in slots]


def checklist_tags(data=None):
    """Checklist tag -> (group, text)."""
    data = data or load()
    return {row["tag"]: (group, row["text"]) for group, rows in data["checklist"].items() for row in rows}


def coverage(data=None):
    """Checklist tag -> ids of the scenarios that cover it (empty list when uncovered)."""
    data = data or load()
    out = {t: [] for t in checklist_tags(data)}
    for s in data["scenarios"]:
        for t in s.get("checklist", []):
            out.setdefault(t, []).append(s["id"])
    return out


def requests_by_department(data=None):
    """Department -> ids of the scenarios whose expected outcome sends it a request."""
    data = data or load()
    out = {}
    for s in data["scenarios"]:
        for r in s.get("expected", {}).get("requests", []):
            ids = out.setdefault(r["department"], [])
            if s["id"] not in ids:
                ids.append(s["id"])
    return out


def absent_heads(data=None):
    """Board head -> ids of the board scenarios where that head is marked absent."""
    data = data or load()
    out = {h: [] for h in BOARD_HEADS}
    for s in data["scenarios"]:
        setup = s.get("setup")
        if not isinstance(setup, dict):
            continue
        for dept, mark in (setup.get("attendance") or {}).items():
            if mark == "absent" and dept in out:
                out[dept].append(s["id"])
    return out


def first_fetch(patient, protocol):
    """The case file of `patient` under `protocol`, or None."""
    return next((c for c in patient.get("case_files", []) if c.get("protocol") == protocol), None)


def strings(obj, path="$"):
    """Every string in a JSON value with its path (keys included)."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}#key", str(k)
            yield from strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from strings(v, f"{path}[{i}]")


def date_values(obj, path="$"):
    """Every {display, value} date object in a JSON value with its path."""
    if isinstance(obj, dict):
        if set(obj) == {"display", "value"}:
            yield path, obj
            return
        for k, v in obj.items():
            yield from date_values(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from date_values(v, f"{path}[{i}]")


def _date_problem(d):
    m = DISPLAY_DATE.match(str(d.get("display", "")))
    if not m:
        return f"display {d.get('display')!r} is not DD/MM/YYYY"
    dd, mm, yyyy, _, hh, mi = m.groups()
    try:
        shown = datetime(int(yyyy), int(mm), int(dd), int(hh or 0), int(mi or 0))
    except ValueError:
        return f"display {d['display']!r} is not a real date"
    value = str(d.get("value", ""))
    want = shown.strftime("%Y-%m-%d") if not hh else shown.strftime("%Y-%m-%dT%H:%M:00+05:30")
    if value != want:
        return f"value {value!r} does not match display {d['display']!r} (want {want!r})"
    return None


def _dupes(items):
    seen, out = set(), []
    for x in items:
        if x in seen and x not in out:
            out.append(x)
        seen.add(x)
    return out


def validate(data):
    """A list of problems (plain sentences); empty when the fixtures are consistent."""
    problems = []
    add = problems.append
    for k in TOP_KEYS:
        if k not in data:
            add(f"top-level key missing: {k}")
    if problems:
        return problems
    if "SYNTHETIC" not in data["note"]:
        add("note does not say SYNTHETIC")

    pats = {}
    for name, spec in data["identifier_patterns"].items():
        try:
            pats[name] = re.compile(spec["regex"])
        except (KeyError, TypeError, re.error) as e:
            add(f"identifier pattern {name}: bad regex ({e})")
    for need in ("uhid", "ip_no", "op_no", "accession", "abha_number", "abha_address", "reg_no", "ca"):
        if need not in pats:
            add(f"identifier pattern missing: {need}")
    if problems:
        return problems

    def check(kind, value, where):
        if kind in pats and not pats[kind].match(str(value or "")):
            add(f"{where}: {kind} {value!r} does not match {pats[kind].pattern}")

    # departments
    depts = {d["name"]: d for d in data["departments"]}
    for x in _dupes([d["name"] for d in data["departments"]]):
        add(f"department listed twice: {x}")
    for x in _dupes([d.get("code") for d in data["departments"]]):
        add(f"department code used twice: {x}")
    groups = [d.get("group") for d in data["departments"]]
    if groups.count("treating") != N_TREATING:
        add(f"{groups.count('treating')} treating departments, plan section 4 lists {N_TREATING}")
    if groups.count("supporting") != N_SUPPORTING:
        add(f"{groups.count('supporting')} supporting departments, plan section 4 lists {N_SUPPORTING}")
    codes = {d.get("code") for d in data["departments"]}
    treating = {n for n, d in depts.items() if d.get("group") == "treating"}
    supporting = {n for n, d in depts.items() if d.get("group") == "supporting"}
    staff = {}
    for d in data["departments"]:
        if d.get("group") not in ("treating", "supporting"):
            add(f"department {d['name']}: group must be treating or supporting")
        if d.get("group") == "supporting" and not d.get("produces"):
            add(f"supporting department {d['name']} lists no record types it produces")
        for c in d.get("consultants", []):
            check("reg_no", c.get("reg_no"), f"department {d['name']} consultant {c.get('name')}")
            staff.setdefault(c.get("reg_no"), (c.get("name"), d["name"]))
    for x in _dupes([c.get("reg_no") for d in data["departments"] for c in d.get("consultants", [])]):
        add(f"Reg. No. given to two consultants: {x}")
    for h in BOARD_HEADS:
        if h not in depts:
            add(f"board head department missing: {h}")
    hospital = data.get("hospital") or {}
    for d in hospital.get("surgical_oncology_list", []):
        if d not in treating:
            add(f"surgical oncology list names {d!r}, not a treating department")

    tests = data.get("tests") or {}
    doc_types = set(data.get("document_types") or [])
    for t, spec in tests.items():
        if doc_types and spec.get("doc_type") not in doc_types:
            add(f"test {t}: doc_type {spec.get('doc_type')!r} is not a known document type")
        dep = spec.get("department")
        if dep != "any_treating" and dep not in depts:
            add(f"test {t}: department {dep!r} is not in the department list")
        if dep in depts and t not in depts[dep].get("produces", []):
            add(f"test {t}: department {dep} does not list it under produces")

    def person(p, where):
        """A consultant / signer object: Reg. No. pattern and the same name as in the department list."""
        if not isinstance(p, dict):
            add(f"{where}: missing")
            return
        check("reg_no", p.get("reg_no"), where)
        known = staff.get(p.get("reg_no"))
        if known and known[0] != p.get("name"):
            add(f"{where}: Reg. No. {p.get('reg_no')} belongs to {known[0]}, not {p.get('name')}")

    # patients
    pts = data["patients"]
    if not MIN_PATIENTS <= len(pts) <= MAX_PATIENTS:
        add(f"{len(pts)} patients; the plan asks for {MIN_PATIENTS} to {MAX_PATIENTS}")
    for x in _dupes([p.get("slot") for p in pts]):
        add(f"patient slot used twice: {x}")
    uhids = [p.get("uhid") for p in pts] + [(p.get(k) or {}).get("uhid") for p in pts for k in ("temporary_uhid", "duplicate_uhid") if p.get(k)]
    for x in _dupes(uhids):
        add(f"UHID used twice: {x}")
    encs_all = [e.get("number") for p in pts for e in p.get("encounters", [])]
    for x in _dupes(encs_all):
        add(f"encounter number used twice: {x}")
    rec_ids = [r.get("id") for p in pts for r in p.get("records", [])]
    for x in _dupes(rec_ids):
        add(f"record id used twice: {x}")
    accs = [r.get("accession") for p in pts for r in p.get("records", []) if r.get("accession")]
    for x in _dupes(accs):
        add(f"accession No. used twice: {x}")
    scen_ids = [s.get("id") for s in data["scenarios"]]
    scen_set = set(scen_ids)

    for p in pts:
        slot = p.get("slot", "?")
        where = f"patient {slot}"
        if p.get("marker") != "SYNTHETIC" or "SYNTHETIC" not in str(p.get("name", "")):
            add(f"{where}: not marked SYNTHETIC (marker and name)")
        if p.get("sex") not in ("F", "M"):
            add(f"{where}: sex must be F or M")
        if not isinstance(p.get("age"), int) or not 0 < p["age"] < 110:
            add(f"{where}: age must be a whole number of years")
        check("uhid", p.get("uhid"), where)
        if p.get("temporary_uhid"):
            check("temporary_uhid", p["temporary_uhid"].get("uhid"), where)
        if p.get("duplicate_uhid"):
            check("uhid", p["duplicate_uhid"].get("uhid"), where)
        for k in ("temporary_uhid", "duplicate_uhid"):
            other = p.get(k)
            if other and (other.get("name"), other.get("sex"), other.get("age")) != (p.get("name"), p.get("sex"), p.get("age")):
                add(f"{where}: {k} must carry the same name, age and sex (that is how a person spots it)")
        if p.get("abha"):
            check("abha_number", p["abha"].get("number"), where)
            check("abha_address", p["abha"].get("address"), where)
        if p.get("pmjay_id"):
            check("pmjay_id", p["pmjay_id"], where)
        if p.get("treating_department") not in treating:
            add(f"{where}: treating department {p.get('treating_department')!r} is not a treating department")
        cfs = p.get("case_files") or []
        if not cfs:
            add(f"{where}: no case file")
        elif p.get("protocol") != cfs[0].get("protocol"):
            add(f"{where}: protocol must be the first case file's protocol")
        for cf in cfs:
            if cf.get("protocol") not in PROTOCOLS:
                add(f"{where}: unknown protocol {cf.get('protocol')!r}")
            if cf.get("owner") not in treating:
                add(f"{where}: case file owner {cf.get('owner')!r} is not a treating department")
            ff = cf.get("first_fetch") or {}
            gaps = ff.get("gaps", [])
            if ff.get("result") != ("gaps" if gaps else "pass"):
                add(f"{where} {cf.get('protocol')}: first_fetch result disagrees with its gaps")
            for g in gaps:
                if g.get("level") not in GAP_LEVELS:
                    add(f"{where}: gap {g.get('requirement')} level must be 1 or 2")
                if g.get("department") not in depts:
                    add(f"{where}: gap {g.get('requirement')} routes to unknown department {g.get('department')!r}")
                if g.get("accession"):
                    check("accession", g["accession"], f"{where} gap {g.get('requirement')}")
                    if g["accession"] not in accs:
                        add(f"{where}: gap {g.get('requirement')} names accession {g['accession']} that no record carries")
        regs = {p.get("uhid")} | {(p.get(k) or {}).get("uhid") for k in ("temporary_uhid", "duplicate_uhid") if p.get(k)}
        encs = {}
        for e in p.get("encounters", []):
            ew = f"{where} encounter {e.get('number')}"
            if e.get("kind") == "OP":
                check("op_no", e.get("number"), ew)
                if not e.get("date"):
                    add(f"{ew}: OP visit without a date")
            elif e.get("kind") == "IP":
                check("ip_no", e.get("number"), ew)
                if not e.get("admitted") or not e.get("ward"):
                    add(f"{ew}: IP admission without admission date or ward")
            else:
                add(f"{ew}: kind must be OP or IP")
            if e.get("department") not in depts:
                add(f"{ew}: unknown department {e.get('department')!r}")
            if e.get("registration") not in regs:
                add(f"{ew}: registration {e.get('registration')!r} is not one of the patient's UHIDs")
            person(e.get("consultant"), f"{ew} consultant")
            for ref in e.get("referrals", []):
                for k in ("from", "to"):
                    if ref.get(k) not in treating:
                        add(f"{ew}: referral {k} {ref.get(k)!r} is not a treating department")
            encs[e.get("number")] = e
        for r in p.get("records", []):
            rw = f"{where} record {r.get('id')}"
            if not str(r.get("id", "")).startswith(slot + "-"):
                add(f"{rw}: id must start with the slot")
            test = tests.get(r.get("test"))
            if tests and not test:
                add(f"{rw}: unknown test {r.get('test')!r}")
            if doc_types and r.get("type") not in doc_types:
                add(f"{rw}: unknown document type {r.get('type')!r}")
            if test and r.get("type") != test["doc_type"]:
                add(f"{rw}: type {r.get('type')!r} differs from the test's document type {test['doc_type']!r}")
            for s in r.get("scenarios", []):
                if s not in scen_set:
                    add(f"{rw}: unknown scenario {s!r}")
            for proto in (r.get("serves") or {}):
                if proto not in {c.get("protocol") for c in cfs}:
                    add(f"{rw}: serves {proto!r}, which is not one of the patient's case files")
            if r.get("source") == "outside_upload":
                if r.get("producing_department") is not None or r.get("encounter") is not None:
                    add(f"{rw}: an outside report has no producing department or encounter in the HIS")
                if not (r.get("outside_source") or {}).get("name"):
                    add(f"{rw}: outside report without its source")
                continue
            if r.get("source") != "his":
                add(f"{rw}: source must be his or outside_upload")
            dep = r.get("producing_department")
            if dep not in depts:
                add(f"{rw}: producing department {dep!r} is not in the department list")
            elif test and test["department"] == "any_treating":
                if dep not in treating:
                    add(f"{rw}: clinical record from {dep}, not a treating department")
            elif test and dep != test["department"]:
                add(f"{rw}: produced by {dep}, but {r.get('test')} comes from {test['department']}")
            os_, rs = r.get("order_status"), r.get("report_status")
            if os_ not in LIFECYCLE:
                add(f"{rw}: unknown order status {os_!r}")
            elif rs not in LIFECYCLE[os_]:
                add(f"{rw}: report status {rs!r} cannot follow order status {os_!r}")
            if os_ == "never_ordered":
                if r.get("accession") or r.get("ordered_on"):
                    add(f"{rw}: a record never ordered has no accession No. or order date")
            elif r.get("encounter") not in encs:
                add(f"{rw}: encounter {r.get('encounter')!r} is not one of the patient's encounters")
            elif r.get("registration", p.get("uhid")) != encs[r["encounter"]].get("registration"):
                add(f"{rw}: filed under a different registration from its encounter")
            if r.get("accession"):
                check("accession", r["accession"], rw)
                if r["accession"].split("/")[0] not in codes:
                    add(f"{rw}: accession prefix is not a department code")
                elif dep in depts and r["accession"].split("/")[0] != depts[dep].get("code"):
                    add(f"{rw}: accession prefix differs from the producing department's code")
            if r.get("sample_barcode"):
                check("sample_barcode", r["sample_barcode"], rw)
            if r.get("block_no"):
                check("block_no", r["block_no"], rw)
            signed = bool(r.get("signed"))
            if rs in ("none", "cancelled", "preliminary") and signed:
                add(f"{rw}: a {rs} report cannot be signed")
            if rs in ("preliminary", "final", "amended"):
                if not r.get("reported_on"):
                    add(f"{rw}: a reported record needs reported_on")
                person(r.get("reported_by"), f"{rw} reported_by")
            elif r.get("values"):
                add(f"{rw}: values on a record with no report")
            if signed:
                sig = r.get("signature") or {}
                person(sig.get("signer"), f"{rw} signer")
                check("ca", sig.get("ca"), rw)
                check("certificate_serial", sig.get("certificate_serial"), rw)
                block = sig.get("block", "")
                for part in ("Digitally signed by", (sig.get("signer") or {}).get("reg_no", "?"), "Vaidyx Demo CA"):
                    if part not in block:
                        add(f"{rw}: signature block lacks {part!r}")
            elif r.get("signature"):
                add(f"{rw}: unsigned record carries a signature")
            if rs == "amended":
                vs = r.get("versions") or []
                if len(vs) < 2 or vs[-1].get("values") != r.get("values"):
                    add(f"{rw}: an amended record keeps its earlier versions and its latest values match the record")
                elif vs[0].get("values") == vs[-1].get("values"):
                    add(f"{rw}: the amendment changes no value")

    # scenarios
    for x in _dupes(scen_ids):
        add(f"scenario id used twice: {x}")
    for sid in REQUIRED_SCENARIOS:
        if sid not in scen_set:
            add(f"scenario missing: {sid}")
    slots = {p.get("slot"): p for p in pts}
    tags = checklist_tags(data)
    for x in _dupes([row["tag"] for rows in data["checklist"].values() for row in rows]):
        add(f"checklist tag used twice: {x}")
    for s in data["scenarios"]:
        sw = f"scenario {s.get('id')}"
        if not re.match(r"^[a-z][a-z0-9_]*$", str(s.get("id", ""))):
            add(f"{sw}: id must be snake_case")
        for k in ("title", "patients", "setup", "expected", "phase", "checklist"):
            if k not in s:
                add(f"{sw}: missing {k}")
        if s.get("phase") not in PHASES:
            add(f"{sw}: phase must be one of {PHASES}")
        for ph in s.get("also_phases", []):
            if ph not in PHASES:
                add(f"{sw}: also_phases has {ph!r}")
        if s.get("plan_1_1") != (s.get("id") in PLAN_SCENARIOS):
            add(f"{sw}: plan_1_1 flag disagrees with the plan 1.1 list")
        if not s.get("patients"):
            add(f"{sw}: no patients")
        for slot in s.get("patients", []):
            if slot not in slots:
                add(f"{sw}: unknown patient {slot!r}")
        for t in s.get("checklist", []):
            if t not in tags:
                add(f"{sw}: unknown checklist tag {t!r}")
        exp = s.get("expected") or {}
        if not exp.get("text"):
            add(f"{sw}: expected outcome has no text")
        for g in exp.get("gate", []):
            p = slots.get(g.get("patient"))
            cf = first_fetch(p, g.get("protocol")) if p else None
            if not cf:
                add(f"{sw}: gate for {g.get('patient')} {g.get('protocol')}, which has no such case file")
                continue
            if g.get("when") == "first_fetch":
                gaps = cf["first_fetch"]["gaps"]
                want = (cf["first_fetch"]["result"], [x["requirement"] for x in gaps if x["level"] == 1],
                        [x["requirement"] for x in gaps if x["level"] == 2])
                if (g.get("result"), g.get("level1"), g.get("level2")) != want:
                    add(f"{sw}: first-fetch gate for {g['patient']} {g['protocol']} disagrees with the patient's case file")
        for r in exp.get("requests", []):
            if r.get("department") not in depts:
                add(f"{sw}: request to unknown department {r.get('department')!r}")
            if r.get("origin") not in REQUEST_ORIGINS:
                add(f"{sw}: request origin must be one of {sorted(REQUEST_ORIGINS)}")
            if r.get("patient") not in slots:
                add(f"{sw}: request for unknown patient {r.get('patient')!r}")
            if r.get("accession") and r["accession"] not in accs:
                add(f"{sw}: request names accession {r['accession']} that no record carries")
        setup = s.get("setup")
        if isinstance(setup, dict):
            for dept, mark in (setup.get("attendance") or {}).items():
                if dept not in depts or mark not in ("present", "absent"):
                    add(f"{sw}: attendance {dept!r}: {mark!r}")
            sp = setup.get("surgeon_present")
            if sp and sp.get("department") not in treating:
                add(f"{sw}: surgeon from {sp.get('department')!r}, not a treating department")
        for a in (exp.get("board") or {}).get("agents_active", []):
            if a not in depts:
                add(f"{sw}: agent for unknown department {a!r}")
    for t, ids in coverage(data).items():
        if not ids:
            add(f"checklist tag not covered by any scenario: {t}")
    seen_req = requests_by_department(data)
    for d in sorted(supporting):
        if d not in seen_req:
            add(f"supporting department receives no request in any scenario: {d}")
    for h, ids in absent_heads(data).items():
        if not ids:
            add(f"board head never absent: {h}")

    # whole-file checks: dates, Aadhaar, em dashes
    for where, d in date_values(data):
        why = _date_problem(d)
        if why:
            add(f"{where}: {why}")
    masked_at = []
    for where, s in strings(data):
        if "\u2014" in s:
            add(f"{where}: em dash (not allowed in UI or reports)")
        if MASKED_AADHAAR in s:
            masked_at.append(where)
        for m in AADHAAR_LIKE.finditer(s):
            add(f"{where}: Aadhaar-like 12-digit number {m.group(0)!r}")
    # the placeholder may be printed on exactly one outside report, named in its pattern, and described by the scenario
    # that tests masking; nowhere else
    masking = {f"$.scenarios[{i}]" for i, s in enumerate(data["scenarios"]) if "aadhaar_masked_outside_report" in s.get("checklist", [])}
    on_records = [w for w in masked_at if w.startswith("$.patients[") and w.endswith(".printed_identifiers.aadhaar")]
    stray = [w for w in masked_at if w not in on_records and not w.startswith("$.identifier_patterns.")
             and not any(w.startswith(m + ".") for m in masking)]
    if masked_at and len(on_records) != 1:
        add(f"the masked Aadhaar placeholder must be printed on exactly one outside report: found at {on_records}")
    for w in stray:
        add(f"{w}: masked Aadhaar placeholder outside the masking scenario")
    for p in pts:
        for r in p.get("records", []):
            ids = r.get("printed_identifiers") or {}
            if "aadhaar" in ids and (r.get("source") != "outside_upload" or ids["aadhaar"] != MASKED_AADHAAR):
                add(f"patient {p.get('slot')} record {r.get('id')}: Aadhaar only as the masked placeholder on an outside report")
        if any("aadhaar" in str(k).lower() for k in p):
            add(f"patient {p.get('slot')}: no Aadhaar field on a patient")
    return problems
