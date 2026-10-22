"""The Registration module and the shared patient / encounter pages of the demo HIMS, mounted at /his by app.py.
SYNTHETIC data only.

    GET  /his                               registration search (UHID, temporary UHID, IP / OP No., ABHA number or
                                            address, accession / Lab No., or a name), recent registrations, new registration
    GET  /his/open?accession=..&uhid=..     a deep link (a Vaidyx-TB request card): the order page of the accession / Lab No.,
                                            else the patient page of the UHID; signed out, the login comes first, then here
    POST /his/registrations                 new registration (duplicate warning first; the desk confirms "register anyway")
    GET  /his/patients/{patient id}         patient banner, demographics, similar registrations, the encounter timeline
                                            (newest first) with each encounter's orders and reports; New OP visit, Admit
    GET  /his/encounters/{encounter id}     one OP visit or IP admission: ward history, referrals, orders and reports, and
                                            the forms of the OPD / IPD modules (OPD note, order entry, referral, transfer,
                                            discharge summary, discharge)
    POST /his/patients/{id}/visits | /admissions, /his/encounters/{id}/refer | /accept | /transfer | /discharge |
         /orders | /notes | /discharge-summary
    /his/api/...                            the same as JSON for tests and the e2e (login-free, localhost only)

Every change goes through a Store transition under hospital.lock, then one HL7 message per new event is appended to
events.hl7 and the store is saved (common.apply); report-producing forms go through the reporting engine (common.run).
Every HTML form carries the session's CSRF token and is role-checked (auth.PERMISSIONS). A temporary or duplicate
registration is shown next to its look-alikes for a person to link in Vaidyx-TB; the mock never merges registrations.
No Aadhaar is ever shown or asked for. No em dashes in any UI string.
"""
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import common, ids, ipd, model, opd, ui
from .app import Hospital, get_hospital
from .common import FieldError, FormState, d

router = APIRouter()

UNITS = ("Unit I", "Unit II", "Unit III", "Casualty")
VISIT_TYPES = (("new", "New"), ("follow_up", "Follow-up"), ("casualty", "Casualty"))
PREAUTH_STATUSES = ("pending", "approved", "rejected")
KINDS = ("permanent", "temporary")
ABHA_NUMBER = re.compile(r"^\d{2}-\d{4}-\d{4}-\d{4}$")
PMJAY_ID = re.compile(r"^PMJAY-VX-\d{8}$")
PIN = re.compile(r"^[1-9]\d{5}$")
PHONE = re.compile(r"^(\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}$")
SIMILAR_NOTE = "Possible duplicate or temporary registration; link in Vaidyx-TB, not merged here"
RECENT = 10
STATES = ("Andhra Pradesh", "Karnataka", "Kerala", "Maharashtra", "Tamil Nadu", "Telangana", "Other")


class DuplicateWarning(Exception):
    """Similar registrations exist; the desk must confirm "register anyway"."""

    def __init__(self, similar):
        super().__init__(f"{len(similar)} similar registration(s) exist; confirm that this is a new person.")
        self.similar = similar


# -------------------------------------------------------------------- small helpers
def _d(value):
    return d(value)


def _plain(name):
    s = re.sub(r"\(\s*synthetic\s*\)", " ", str(name or ""), flags=re.I)
    return " ".join(s.lower().split())


def _prac(store, pid):
    return common.prac_name(store, pid)


def _kind_pill(kind):
    return ui.pill(kind)


def _enc_pill(e):
    return '<span class="pill ok">IP</span>' if e["kind"] == "IP" else '<span class="pill info">OP</span>'


def _visit_type(v):
    return dict(VISIT_TYPES).get(v, v or "").lower()


def _age_sex(p):
    return common.age_sex(p)


def _address(p):
    a = p.get("address") or {}
    parts = []
    for k in ("line", "town", "district", "state"):
        if a.get(k) and (not parts or parts[-1] != a[k]):
            parts.append(a[k])
    return ", ".join(parts) + (f", PIN {a['pin']}" if a.get("pin") else "")


def _treating(store):
    return sorted((d_ for d_ in store.departments.values() if d_["group"] == "treating"), key=lambda x: x["name"])


def _consultants(store, departments):
    names = {x["name"] for x in departments}
    return sorted((p for p in store.practitioners.values() if p["department"] in names and p["role"] == "consultant"),
                  key=lambda p: (p["department"], p["name"]))


def _wards(store):
    return sorted({h["ward"] for e in store.encounters.values() for h in e.get("ward_history") or [] if h.get("ward")})


def _apply(hospital, change, request=None, action="change"):
    return common.apply(hospital, request, action, change)


# -------------------------------------------------------------------- search
def search(store, q):
    """('identifier' | 'name' | 'none', [patients]). An identifier hit is exact: UHID (permanent or temporary), IP / OP
    No., ABHA number or address, accession / Lab No.; otherwise every word of the query must be in the name."""
    q = (q or "").strip()
    if not q:
        return "none", []
    p = store.patient_by_identifier(q)
    if not p:
        key = q.lower()
        p = next((x for x in store.patients.values() if ((x.get("abha") or {}).get("address") or "").lower() == key), None)
    if not p:
        o = next((o for o in store.orders.values() if (o.get("accession") or "").upper() == q.upper()), None)
        p = store.patients.get(o["patient_id"]) if o else None
    if p:
        return "identifier", [p]
    words = _plain(q).split()
    if not words or not re.search(r"[a-z]", " ".join(words)):
        return "none", []
    hits = [x for x in store.patients.values() if all(w in _plain(x["name"]) for w in words)]
    hits.sort(key=lambda x: (_plain(x["name"]), x["registered_on"], x["uhid"]))
    return ("name" if hits else "none"), hits


def recent(store, n=RECENT):
    return sorted(store.patients.values(), key=lambda p: (p["registered_on"], p["meta"]["lastUpdated"], p["uhid"]),
                  reverse=True)[:n]


def summary(store, p):
    """One registration as a search result row (JSON)."""
    return {"id": p["id"], "uhid": p["uhid"], "registration_kind": p["registration_kind"], "name": p["name"],
            "sex": p["sex"], "age": p["age"], "registered_on": p["registered_on"], "abha": bool(p.get("abha")),
            "similar": [q["id"] for q in store.similar_registrations(p["id"])]}


def _registrations_table(store, patients, empty):
    rows = []
    for p in patients:
        sim = store.similar_registrations(p["id"])
        note = (f'<br><a class=muted href="/his/patients/{ui.esc(p["id"])}">{len(sim)} similar registration(s)</a>'
                if sim else "")
        rows.append([f'<a href="/his/patients/{ui.esc(p["id"])}">{ui.esc(p["name"])}</a>{note}',
                     f'<span class=mono>{ui.esc(p["uhid"])}</span>', _kind_pill(p["registration_kind"]),
                     ui.esc(_age_sex(p)), ui.esc(_d(p["registered_on"])), "yes" if p.get("abha") else "no"])
    return ui.table(["Name", "UHID", "Registration", "Age / Sex", "Registered on", "ABHA"], rows, empty=empty)


# -------------------------------------------------------------------- orders and reports (JSON views)
def _version_label(v):
    return common.version_label(v)


def report_view(store, r):
    """A report with its versions (JSON): status, signed, reported on, PDF link when rendered."""
    if not r:
        return None
    out = []
    for v in r["versions"]:
        path = (v.get("document") or {}).get("path")
        out.append({"version": v["version"], "status": v["status"], "reported_on": v["reported_on"],
                    "reported_by": _prac(store, v.get("reported_by")), "signed": bool(v.get("signature_id")),
                    "amendment_note": v.get("amendment_note"),
                    "pdf": f"/view/reports/{r['id']}/{v['version']}" if path else None})
    return {"id": r["id"], "status": r["status"], "current_version": r["current_version"], "title": r["title"],
            "versions": out}


def order_view(store, o):
    spec = store.specimens.get(o.get("specimen_id")) if o.get("specimen_id") else None
    return {"id": o["id"], "accession": o["accession"], "test": o["test"], "label": o["label"], "doc_type": o["doc_type"],
            "ordering_department": o["ordering_department"], "performing_department": o["performing_department"],
            "status": o["status"], "ordered_on": o["ordered_on"], "scheduled_for": o["scheduled_for"],
            "sample_collected_on": o["sample_collected_on"], "barcode": spec["barcode"] if spec else None,
            "cancelled_on": o["cancelled_on"], "cancel_reason": o["cancel_reason"],
            "report": report_view(store, store.report_for_order(o["id"]))}


def _orders(store, encounter_id):
    return sorted(store.orders_for(encounter_id=encounter_id), key=lambda o: (o["ordered_on"], o["id"]))


# -------------------------------------------------------------------- encounters
def _preauth_text(e):
    pre = e.get("pmjay_preauth")
    if not pre:
        return "not requested"
    return (pre.get("status") or "") + (f" ({_d(pre['date'])})" if pre.get("date") else "")


def encounter_heading(store, e):
    who = _prac(store, e.get("consultant_id"))
    if e["kind"] == "OP":
        parts = [f"OP visit {e['number']}", f"{e['department']} {e['unit'] or ''}".strip(), who, _d(e["date"]),
                 _visit_type(e.get("visit_type"))]
    else:
        parts = [f"Admission {e['number']}", f"{e['department']} {e['unit'] or ''}".strip(), who,
                 f"admitted {_d(e['admitted'])}",
                 f"discharged {_d(e['discharged'])}" if e.get("discharged") else "in ward"]
    return ", ".join(x for x in parts if x)


def _encounter_lines(e):
    """The admission's ward / bed and Pre-Authorization line, and the referrals in one line each."""
    out = []
    if e["kind"] == "IP":
        where = "at discharge" if e.get("discharged") else "now"
        out.append(f"Ward / bed {where}: {e.get('ward') or ''}, {e.get('bed') or ''}. "
                   f"PM-JAY Pre-Authorization: {_preauth_text(e)}.")
        if len(e.get("ward_history") or []) > 1:
            out.append(f"{len(e['ward_history']) - 1} ward transfer(s).")
    for r in e.get("referrals") or []:
        acc = f", accepted {_d(r['accepted_on'])}" if r.get("accepted_on") else ""
        out.append(f"Referral from {r['from']} to {r['to']} on {_d(r['on'])}: {r['status']}{acc}.")
    return out


def encounter_view(store, e):
    """An encounter with consultant name, its orders (and reports), newest data included (JSON)."""
    out = {k: v for k, v in e.items()}
    out["consultant"] = _prac(store, e.get("consultant_id"))
    out["heading"] = encounter_heading(store, e)
    out["orders"] = [order_view(store, o) for o in _orders(store, e["id"])]
    return out


def _timeline(store, p):
    encs = list(reversed(store.encounters_for(p["id"])))
    if not encs:
        return '<p class=muted>No OP visit or admission on this registration yet.</p>'
    panels = []
    for e in encs:
        lines = "".join(f'<p class=muted>{ui.esc(x)}</p>' for x in _encounter_lines(e))
        st = ui.pill(e["status"]) if e["kind"] == "IP" else ""
        panels.append(f'<div class=panel data-encounter="{ui.esc(e["id"])}" data-kind="{ui.esc(e["kind"])}">'
                      f'<h3>{_enc_pill(e)} <a href="/his/encounters/{ui.esc(e["id"])}">{ui.esc(encounter_heading(store, e))}</a> {st}</h3>'
                      f'{lines}{common.orders_table(store, _orders(store, e["id"]))}</div>')
    return "".join(panels)


# -------------------------------------------------------------------- transitions shared by the forms and the API
def _field(f, key, default=""):
    v = f.get(key) if f is not None else None
    return default if v is None else " ".join(str(v).split())


def _dob(text_):
    """A date of birth typed as DD/MM/YYYY or YYYY-MM-DD -> ISO date."""
    s = text_.strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    try:
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        return date.fromisoformat(s).isoformat()
    except ValueError:
        raise FieldError("dob", "Date of birth must be DD/MM/YYYY.") from None


def _age_on(dob_iso, today_iso):
    b, t = date.fromisoformat(dob_iso), date.fromisoformat(today_iso)
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def do_register(store, f):
    """Validate the registration form (FieldError names the field) and register. Similar registrations raise
    DuplicateWarning unless `confirm_duplicate` is set."""
    name = _field(f, "name")
    if not name.endswith("(SYNTHETIC)"):
        raise FieldError("name", 'The name must end with "(SYNTHETIC)": the demo hospital holds synthetic patients only.')
    if not _plain(name):
        raise FieldError("name", "A name is required before (SYNTHETIC).")
    sex = _field(f, "sex").upper()
    if sex not in ("F", "M"):
        raise FieldError("sex", "Sex must be F or M.")
    dob_text = _field(f, "dob")
    dob = _dob(dob_text) if dob_text else None
    age_text = _field(f, "age")
    if dob and dob > common.today(store):
        raise FieldError("dob", "The date of birth is in the future.")
    if age_text:
        try:
            age = int(age_text)
        except ValueError:
            raise FieldError("age", "Age must be a whole number of years.") from None
    elif dob:
        age = _age_on(dob, common.today(store))
    else:
        raise FieldError("age", "Enter the age in years or the date of birth.")
    if not 0 <= age <= 120:
        raise FieldError("age", "Age must be between 0 and 120 years.")
    kind = _field(f, "kind", "permanent") or "permanent"
    if kind not in KINDS:
        raise FieldError("kind", "Registration kind must be permanent or temporary.")
    phone = _field(f, "phone")
    if phone and not PHONE.match(phone):
        raise FieldError("phone", "Phone must be a 10-digit Indian mobile number, optionally with +91.")
    pin = _field(f, "pin")
    if pin and not PIN.match(pin):
        raise FieldError("pin", "PIN must be 6 digits.")
    address = {k: _field(f, k) for k in ("line", "town", "district", "state")}
    address["pin"] = pin
    address = address if any(address.values()) else None
    abha = _field(f, "abha_number")
    if abha:
        if not ABHA_NUMBER.match(abha):
            raise FieldError("abha_number", "ABHA number must be 14 digits written 2-4-4-4, for example 99-2600-0000-0001.")
        if kind != "permanent":
            raise FieldError("abha_number", "An ABHA number is linked to a permanent registration only.")
        if store.patient_by_identifier(abha):
            raise FieldError("abha_number", f"ABHA number {abha} is already linked to another registration.")
    pmjay = _field(f, "pmjay_id").upper()
    if pmjay and not PMJAY_ID.match(pmjay):
        raise FieldError("pmjay_id", "PM-JAY ID must look like PMJAY-VX-26000101 (synthetic pattern).")
    similar = store.patients_by_name(name, sex=sex, age=age, tolerance=2)
    if similar and not _field(f, "confirm_duplicate"):
        raise DuplicateWarning(similar)
    return store.register_patient(name, sex, age, kind=kind, dob=dob, phone=phone or None, address=address,
                                  abha={"number": abha, "address": None} if abha else None, pmjay_id=pmjay or None)


def _check_consultant(store, consultant_id, dept):
    if not consultant_id:
        return None
    prac = store.practitioner(consultant_id)
    if not prac:
        raise model.LifecycleError(f"unknown consultant {consultant_id!r}")
    if prac["department"] != dept["name"] or prac["role"] != "consultant":
        raise model.LifecycleError(f"{prac['name']} is not a consultant of {dept['name']}.")
    return prac["id"]


def _treating_department(store, name):
    dept = store.department(name)
    if not dept or dept["group"] != "treating":
        raise model.LifecycleError(f"{name or 'no department'} is not a treating department.")
    return dept


def do_visit(store, pid, f):
    dept = _treating_department(store, _field(f, "department"))
    consultant = _check_consultant(store, _field(f, "consultant_id"), dept)
    unit = _field(f, "unit", "Unit I") or "Unit I"
    if unit not in UNITS:
        raise ValueError(f"Unit must be one of {', '.join(UNITS)}.")
    vt = _field(f, "visit_type", "new") or "new"
    if vt not in dict(VISIT_TYPES):
        raise ValueError("Visit type must be new, follow_up or casualty.")
    return store.open_visit(pid, dept["name"], unit=unit, consultant_id=consultant, visit_type=vt)


def do_admit(store, pid, f):
    p = store.patients[pid]
    current = common.current_admission(store, pid)
    if current:
        raise model.LifecycleError(f"{p['uhid']} is already admitted under {current['number']}; discharge first.")
    dept = _treating_department(store, _field(f, "department"))
    consultant = _check_consultant(store, _field(f, "consultant_id"), dept)
    unit = _field(f, "unit", "Unit I") or "Unit I"
    if unit not in UNITS:
        raise ValueError(f"Unit must be one of {', '.join(UNITS)}.")
    ward, bed = _field(f, "ward"), _field(f, "bed")
    if not ward or not bed:
        raise ValueError("An admission needs a ward and a bed.")
    status = _field(f, "pmjay_preauth")
    pre = None
    if status:
        if status not in PREAUTH_STATUSES:
            raise ValueError(f"PM-JAY Pre-Authorization status must be one of {', '.join(PREAUTH_STATUSES)}.")
        if not p.get("pmjay_id"):
            raise model.LifecycleError(f"{p['uhid']} has no PM-JAY ID; no Pre-Authorization can be recorded.")
        pre = {"status": status, "date": store.now() if status != "pending" else None}
    return store.admit(pid, dept["name"], ward, bed, unit=unit, consultant_id=consultant, pmjay_preauth=pre)


def do_refer(store, e, f):
    to = store.department(_field(f, "to"))
    if not to:
        raise model.LifecycleError(f"unknown department {_field(f, 'to')!r}")
    reason = " ".join(_field(f, "reason").split())
    if not reason:
        raise ValueError("A referral needs a reason.")
    frm = _field(f, "from") or e["department"]
    return store.refer(e["id"], frm, to["name"], reason)


def do_accept(store, e, f):
    return store.accept_referral(e["id"], _field(f, "to"))


def do_transfer(store, e, f):
    ward, bed = _field(f, "ward"), _field(f, "bed")
    if not ward or not bed:
        raise ValueError("A transfer needs a ward and a bed.")
    return store.transfer_ward(e["id"], ward, bed, reason=_field(f, "reason") or None)


def do_discharge(store, e, f=None):
    return store.discharge(e["id"])


# -------------------------------------------------------------------- HTML: registration search
def _register_form(request, store, state=None, similar=None):
    st = state or common.EMPTY
    warn = ""
    if similar:
        warn = ('<div class="flash warn">Possible duplicate: a registration with the same name, sex and age (within 2 '
                'years) exists. Open it below, or tick "Register anyway" when this is a new person.</div>'
                + _registrations_table(store, similar, "")
                + '<p><label><input type=checkbox name=confirm_duplicate value=1> Register anyway (new person)</label></p>')
    body = (f'<div class=panel id=register><h2>New registration</h2>'
            '<form method=post action="/his/registrations">' + common.csrf_field(request) + warn
            + ui.field("name", 'Name (ends with "(SYNTHETIC)")', ui.text_input("name", st.v("name"), required=True,
                                                                              placeholder="Firstname Surname (SYNTHETIC)"), st.err("name"))
            + ui.field("sex", "Sex", ui.select("sex", [("F", "F"), ("M", "M")], st.v("sex") or "F", short=True), st.err("sex"))
            + ui.field("age", "Age (years)", ui.text_input("age", st.v("age"), short=True, extra=" inputmode=numeric"), st.err("age"),
                       help="Leave blank when the date of birth is given.")
            + ui.field("dob", "Date of birth (DD/MM/YYYY)", ui.text_input("dob", st.v("dob"), short=True, placeholder="DD/MM/YYYY"),
                       st.err("dob"))
            + ui.field("phone", "Mobile phone", ui.text_input("phone", st.v("phone"), short=True, placeholder="+91 98765 43210"),
                       st.err("phone"))
            + ui.field("line", "Address", ui.text_input("line", st.v("line"), placeholder="H. No., street, locality"), st.err("line"))
            + ui.field("town", "Town / village", ui.text_input("town", st.v("town"), short=True), st.err("town"))
            + ui.field("district", "District", ui.text_input("district", st.v("district"), short=True), st.err("district"))
            + ui.field("state", "State", ui.select("state", [("", "Choose")] + [(s, s) for s in STATES], st.v("state"), short=True),
                       st.err("state"))
            + ui.field("pin", "PIN code", ui.text_input("pin", st.v("pin"), short=True, extra=" inputmode=numeric"), st.err("pin"))
            + ui.field("kind", "Registration", ui.select("kind", [("permanent", "Permanent UHID"),
                                                                  ("temporary", "Temporary UHID (casualty)")], st.v("kind") or "permanent"),
                       st.err("kind"))
            + ui.field("abha_number", "ABHA number (optional, permanent only)",
                       ui.text_input("abha_number", st.v("abha_number"), short=True, placeholder="99-2600-0000-0001"), st.err("abha_number"),
                       help="ABDM sandbox format, 14 digits written 2-4-4-4.")
            + ui.field("pmjay_id", "PM-JAY ID (optional)", ui.text_input("pmjay_id", st.v("pmjay_id"), short=True,
                                                                        placeholder="PMJAY-VX-26000101"), st.err("pmjay_id"))
            + '<p><button type=submit class=primary>Register</button></p></form></div>')
    return body


def _search_box(q):
    return ('<div class=panel><form method=get action="/his">'
            '<label class=lbl for=q>UHID (permanent or temporary), IP No., OP No., ABHA number or address, Lab No., or name</label>'
            f'<input type=text id=q name=q value="{ui.esc(q)}" placeholder="VXH/26/004201, IP/26/01872, OP/26/118701 or a name">'
            ' <button type=submit>Search</button></form></div>')


def home_page(request, hospital, q="", state=None, similar=None, status=200):
    store = hospital.store
    results = ""
    if q.strip():
        match, hits = search(store, q)
        results = (f'<div class=panel id=results><h2>Registrations matching "{ui.esc(q.strip())}"</h2>'
                   + _registrations_table(store, hits, "No registration matches this identifier or name.")
                   + '<p class=muted>A person links similar registrations in Vaidyx-TB; the HIS never merges them.</p></div>')
    rec = ('<div class=panel id=recent><h2>Recent registrations</h2>'
           + _registrations_table(store, recent(store), "No registrations yet.") + '</div>')
    form = _register_form(request, store, state, similar) if common.can(request, "register") else \
        '<div class=panel id=register><h2>New registration</h2>' + common.refused_line(request, "register") + '</div>'
    return common.page(request, "Registration search", _search_box(q) + results + rec + form, active="Registration",
                       status=status)


@router.get("", response_class=HTMLResponse)
def home(request: Request, q: str = "", hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    match, hits = search(store, q)
    if match == "identifier":
        return RedirectResponse(f"/his/patients/{hits[0]['id']}", status_code=303)
    return home_page(request, hospital, q)


@router.get("/open", response_class=HTMLResponse)
def open_record(accession: str = "", uhid: str = "", hospital: Hospital = Depends(get_hospital)):
    """The order of an accession / Lab No. on its own department page (Pathology, Radiology, Lab, OPD), else the patient
    of a UHID (or any identifier the registration search knows). A signed-out user is sent to the login with this link as
    "next" (app._login_redirect) and lands here again; the order page itself checks the role."""
    store = hospital.store
    acc = accession.strip().upper()
    o = next((o for o in store.orders.values() if acc and (o.get("accession") or "").upper() == acc), None)
    if o:
        return RedirectResponse(common.order_url(o), status_code=303)
    q = uhid.strip() or accession.strip()
    match, hits = search(store, q)
    if match == "identifier":
        return RedirectResponse(f"/his/patients/{hits[0]['id']}", status_code=303)
    return common.redirect("/his", f"Nothing found for {q}: search by UHID, IP / OP No. or name." if q else None, warn=True)


@router.post("/registrations")
async def register(request: Request, hospital: Hospital = Depends(get_hospital)):
    form = await common.form(request)
    common.require(request, "register")
    try:
        p = _apply(hospital, lambda s: do_register(s, form), request, "register")
    except FieldError as e:
        return home_page(request, hospital, state=FormState(common.values_of(form), {e.field: e.message}), status=422)
    except DuplicateWarning as e:
        return home_page(request, hospital, state=FormState(common.values_of(form)), similar=e.similar, status=409)
    except ValueError as e:
        return common.redirect("/his", str(e), bad=True)
    sim = hospital.store.similar_registrations(p["id"])
    msg = f"Registered {p['name']} as {p['uhid']} ({p['registration_kind']})."
    if sim:
        return common.redirect(f"/his/patients/{p['id']}", msg + f" Note: {len(sim)} similar registration(s) exist.", warn=True)
    return common.redirect(f"/his/patients/{p['id']}", msg)


# -------------------------------------------------------------------- HTML: patient
def _dept_options(departments, selected=None):
    return ui.options([(x["name"], x["name"]) for x in departments], selected)


def _consultant_options(store, departments, selected=None):
    return ui.options([("", "Not assigned")] + [(c["id"], f"{c['name']} ({c['department']})")
                                                 for c in _consultants(store, departments)], selected)


def _patient_forms(request, store, p):
    tre = _treating(store)
    last = (store.encounters_for(p["id"]) or [None])[-1]
    me = common.practitioner(request, store)
    dsel = me["department"] if me else (last["department"] if last else None)
    csel = me["id"] if me else None
    units = ui.options([(u, u) for u in UNITS])
    csrf = common.csrf_field(request)
    parts = []
    if common.can(request, "visit.open"):
        parts.append('<div class=panel id=visit><h2>New OP visit</h2>'
                     f'<form method=post action="/his/patients/{ui.esc(p["id"])}/visits">{csrf}'
                     + ui.field("department", "Department", f'<select id="f-department" name=department>{_dept_options(tre, dsel)}</select>')
                     + ui.field("unit", "Unit", f'<select id="f-unit" name=unit class=short>{units}</select>')
                     + ui.field("consultant_id", "Consultant", f'<select id="f-consultant_id" name=consultant_id>{_consultant_options(store, tre, csel)}</select>')
                     + ui.field("visit_type", "Visit type", f'<select id="f-visit_type" name=visit_type class=short>{ui.options(VISIT_TYPES)}</select>')
                     + '<p><button type=submit class=primary>Open OP visit</button></p></form></div>')
    else:
        parts.append('<div class=panel id=visit><h2>New OP visit</h2>' + common.refused_line(request, "visit.open") + '</div>')
    if common.can(request, "admit"):
        wards = "".join(f'<option value="{ui.esc(w)}">' for w in _wards(store))
        pre = ui.options([("", "Not requested")] + [(s, s) for s in PREAUTH_STATUSES])
        parts.append('<div class=panel id=admit><h2>Admit</h2>'
                     f'<form method=post action="/his/patients/{ui.esc(p["id"])}/admissions">{csrf}'
                     + ui.field("a-department", "Department", f'<select id="f-a-department" name=department>{_dept_options(tre, dsel)}</select>')
                     + ui.field("a-unit", "Unit", f'<select id="f-a-unit" name=unit class=short>{units}</select>')
                     + ui.field("a-consultant", "Consultant", f'<select id="f-a-consultant" name=consultant_id>{_consultant_options(store, tre, csel)}</select>')
                     + ui.field("ward", "Ward", f'<input type=text id="f-ward" name=ward list=wards required class=short><datalist id=wards>{wards}</datalist>')
                     + ui.field("bed", "Bed", ui.text_input("bed", required=True, short=True))
                     + ui.field("pmjay_preauth", "PM-JAY Pre-Authorization", f'<select id="f-pmjay_preauth" name=pmjay_preauth class=short>{pre}</select>',
                                help="Only a patient with a PM-JAY ID can carry a Pre-Authorization.")
                     + '<p><button type=submit class=primary>Admit</button></p></form></div>')
    else:
        parts.append('<div class=panel id=admit><h2>Admit</h2>' + common.refused_line(request, "admit") + '</div>')
    return f'<div class=grid>{"".join(parts)}</div>'


@router.get("/patients/{pid}", response_class=HTMLResponse)
def patient_page(pid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    p = common.patient_or_404(store, pid)
    abha = p.get("abha") or {}
    demo = ui.dl([
        ("UHID", f'<span class=mono>{ui.esc(p["uhid"])}</span> {_kind_pill(p["registration_kind"])}'),
        ("Name", ui.esc(p["name"])),
        ("Age / Sex", ui.esc(_age_sex(p))),
        ("Date of birth", ui.esc(p.get("dob") or "")),
        ("ABHA number", f'<span class=mono>{ui.esc(abha.get("number"))}</span>' if abha.get("number") else '<span class=muted>not linked</span>'),
        ("ABHA address", ui.esc(abha.get("address")) if abha.get("address") else '<span class=muted>not linked</span>'),
        ("PM-JAY ID", f'<span class=mono>{ui.esc(p["pmjay_id"])}</span>' if p.get("pmjay_id") else '<span class=muted>none</span>'),
        ("Phone", ui.esc(p.get("phone") or "")),
        ("Address", ui.esc(_address(p))),
        ("Registered on", ui.esc(_d(p["registered_on"]))),
    ] + ([("Note", ui.esc(p["note"]))] if p.get("note") else []))
    body = f'<div class=panel id=demographics><h2>Demographics</h2>{demo}</div>'
    sim = store.similar_registrations(p["id"])
    if sim:
        body += ('<div class=panel id=similar><h2>Similar registrations</h2>'
                 f'<p><span class="pill warn">Check</span> {ui.esc(SIMILAR_NOTE)}</p>'
                 + _registrations_table(store, sim, "") + '</div>')
    body += '<h2>Timeline (OP visits and IP admissions, newest first)</h2>' + _timeline(store, p)
    body += _patient_forms(request, store, p)
    return common.page(request, f"{p['name']}, {p['uhid']}", body, active="Registration", banner=common.banner(store, p))


@router.post("/patients/{pid}/visits")
async def visit_form(pid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    common.patient_or_404(hospital.store, pid)
    form = await common.form(request)
    common.require(request, "visit.open")
    try:
        e = _apply(hospital, lambda s: do_visit(s, pid, form), request, "visit.open")
    except ValueError as ex:
        return common.redirect(f"/his/patients/{pid}", str(ex), bad=True)
    return common.redirect(f"/his/encounters/{e['id']}", f"OP visit {e['number']} opened in {e['department']} {e['unit']}.")


@router.post("/patients/{pid}/admissions")
async def admit_form(pid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    common.patient_or_404(hospital.store, pid)
    form = await common.form(request)
    common.require(request, "admit")
    try:
        e = _apply(hospital, lambda s: do_admit(s, pid, form), request, "admit")
    except ValueError as ex:
        return common.redirect(f"/his/patients/{pid}", str(ex), bad=True)
    return common.redirect(f"/his/encounters/{e['id']}", f"Admitted under {e['number']}, {e['ward']} bed {e['bed']}.")


# -------------------------------------------------------------------- HTML: encounter
def _encounter_forms(request, store, e, state=None):
    eid = ui.esc(e["id"])
    csrf = common.csrf_field(request)
    parts = []
    open_ip = e["kind"] == "IP" and e["status"] == "in-progress"
    # OPD note and order entry (OPD module), discharge summary (IPD module)
    if e["kind"] == "OP":
        parts.append(opd.note_form(request, store, e, state))
    parts.append(opd.order_form(request, store, e))
    if e["kind"] == "IP":
        parts.append(ipd.discharge_summary_form(request, store, e, state))
    # referral
    others = sorted((x for x in store.departments.values() if x["name"] != e["department"]),
                    key=lambda x: (x["group"] != "treating", x["name"]))
    froms = [e["department"]] + [r["to"] for r in e.get("referrals") or [] if r["status"] == "accepted"]
    froms = list(dict.fromkeys(froms))
    from_field = ""
    if len(froms) > 1:
        from_field = ui.field("from", "From", f'<select id="f-from" name=from>{ui.options([(x, x) for x in froms])}</select>')
    if common.can(request, "refer"):
        parts.append('<div class=panel id=refer><h2>Refer to department</h2>'
                     f'<form method=post action="/his/encounters/{eid}/refer">{csrf}{from_field}'
                     + ui.field("to", "To", f'<select id="f-to" name=to>{_dept_options(others)}</select>')
                     + ui.field("reason", "Reason", ui.textarea("reason", required=True, rows=2))
                     + '<p><button type=submit>Refer</button></p></form></div>')
    else:
        parts.append('<div class=panel id=refer><h2>Refer to department</h2>' + common.refused_line(request, "refer") + '</div>')
    open_refs = [r for r in e.get("referrals") or [] if r["status"] == "requested"]
    if open_refs and common.can(request, "accept_referral"):
        btns = "".join(f'<form class=inline method=post action="/his/encounters/{eid}/accept">{csrf}'
                       f'<input type=hidden name=to value="{ui.esc(r["to"])}">'
                       f'<button type=submit>Accepted by {ui.esc(r["to"])}</button></form> '
                       for r in open_refs)
        parts.append(f'<div class=panel id=accept><h2>Accept referral</h2><p>{btns}</p></div>')
    if open_ip:
        if common.can(request, "transfer"):
            wards = "".join(f'<option value="{ui.esc(w)}">' for w in _wards(store))
            parts.append('<div class=panel id=transfer><h2>Transfer ward</h2>'
                         f'<form method=post action="/his/encounters/{eid}/transfer">{csrf}'
                         + ui.field("t-ward", "Ward", f'<input type=text id=t-ward name=ward list=wards required class=short value="{ui.esc(e.get("ward"))}"><datalist id=wards>{wards}</datalist>')
                         + ui.field("t-bed", "Bed", '<input type=text id=t-bed name=bed required class=short>')
                         + ui.field("t-reason", "Reason (optional)", '<input type=text id=t-reason name=reason>')
                         + '<p><button type=submit>Transfer</button></p></form></div>')
        if common.can(request, "discharge"):
            parts.append('<div class=panel id=discharge><h2>Discharge</h2>'
                         f'<form method=post action="/his/encounters/{eid}/discharge">{csrf}'
                         f'<p class=muted>Discharge {ui.esc(e["number"])} from {ui.esc(e.get("ward"))}, bed {ui.esc(e.get("bed"))}. '
                         'Write the discharge summary first.</p>'
                         '<p><button type=submit class=danger>Discharge</button></p></form></div>')
        else:
            parts.append('<div class=panel id=discharge><h2>Discharge</h2>' + common.refused_line(request, "discharge") + '</div>')
    return f'<div class=grid>{"".join(parts)}</div>'


def render_encounter(request, hospital, e, state=None, status=200):
    store = hospital.store
    p = store.patients[e["patient_id"]]
    pairs = [("Patient", f'<a href="/his/patients/{ui.esc(p["id"])}">{ui.esc(p["name"])}</a>, '
                         f'<span class=mono>{ui.esc(p["uhid"])}</span> {_kind_pill(p["registration_kind"])}, {ui.esc(_age_sex(p))}'),
             ("Encounter", f'{_enc_pill(e)} <span class=mono>{ui.esc(e["number"])}</span> '
                           + ("OP visit" if e["kind"] == "OP" else "IP admission")),
             ("Department", ui.esc(e["department"])), ("Unit", ui.esc(e.get("unit") or "")),
             ("Consultant", ui.esc(_prac(store, e.get("consultant_id"))) or '<span class=muted>not assigned</span>'),
             ("Status", ui.pill(e["status"]))]
    if e["kind"] == "OP":
        pairs += [("Visit date", ui.esc(_d(e["date"]))), ("Visit type", ui.esc(_visit_type(e.get("visit_type"))))]
    else:
        pairs += [("Admitted", ui.esc(_d(e["admitted"]))),
                  ("Discharged", ui.esc(_d(e["discharged"])) if e.get("discharged") else '<span class=muted>in ward</span>'),
                  ("Ward / bed", ui.esc(f"{e.get('ward') or ''}, {e.get('bed') or ''}")),
                  ("PM-JAY Pre-Authorization", ui.esc(_preauth_text(e)))]
    if e.get("note"):
        pairs.append(("Note", ui.esc(e["note"])))
    body = f'<div class=panel id=details>{ui.dl(pairs)}</div>'
    if e["kind"] == "IP":
        rows = [[ui.esc(h["ward"]), ui.esc(h["bed"]), ui.esc(ids.display_time(h["from"])), ui.esc(h.get("reason") or "")]
                for h in e.get("ward_history") or []]
        body += ('<div class=panel id=wards><h2>Ward history</h2>'
                 + ui.table(["Ward", "Bed", "From", "Reason"], rows, empty="No ward recorded.") + '</div>')
    rows = [[ui.esc(r["from"]), ui.esc(r["to"]), ui.esc(_d(r["on"])), ui.esc(r.get("reason") or ""), ui.pill(r["status"]),
             ui.esc(_d(r.get("accepted_on")))] for r in e.get("referrals") or []]
    body += ('<div class=panel id=referrals><h2>Referrals</h2>'
             + ui.table(["From", "To", "On", "Reason", "Status", "Accepted on"], rows, empty="No referral on this encounter.")
             + '</div>')
    body += ('<div class=panel id=orders><h2>Orders and reports</h2>' + common.orders_table(store, _orders(store, e["id"])) + '</div>')
    body += _encounter_forms(request, store, e, state)
    return common.page(request, encounter_heading(store, e), body, active="OPD" if e["kind"] == "OP" else "IPD",
                       banner=common.banner(store, p, e), status=status)


@router.get("/encounters/{eid}", response_class=HTMLResponse)
def encounter_page(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    e = common.encounter_or_404(hospital.store, eid)
    return render_encounter(request, hospital, e)


def _encounter_post(action, label, permission):
    async def handler(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
        common.encounter_or_404(hospital.store, eid)
        form = await common.form(request)
        common.require(request, permission)
        try:
            res = _apply(hospital, lambda s: action(s, s.encounters[eid], form), request, permission)
        except ValueError as ex:
            return common.redirect(f"/his/encounters/{eid}", str(ex), bad=True)
        return common.redirect(f"/his/encounters/{eid}", label(hospital.store.encounters[eid], res))
    return handler


router.add_api_route("/encounters/{eid}/refer", _encounter_post(
    do_refer, lambda e, r: f"Referral from {r['from']} to {r['to']} requested.", "refer"), methods=["POST"])
router.add_api_route("/encounters/{eid}/accept", _encounter_post(
    do_accept, lambda e, r: f"Referral accepted by {r['to']}.", "accept_referral"), methods=["POST"])
router.add_api_route("/encounters/{eid}/transfer", _encounter_post(
    do_transfer, lambda e, r: f"{e['number']} transferred to {e['ward']}, bed {e['bed']}.", "transfer"), methods=["POST"])
router.add_api_route("/encounters/{eid}/discharge", _encounter_post(
    do_discharge, lambda e, r: f"{e['number']} discharged.", "discharge"), methods=["POST"])


@router.post("/encounters/{eid}/orders")
async def orders_form(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    """Order entry: the ticked tests, grouped by performing department on the form, placed one by one."""
    e = common.encounter_or_404(hospital.store, eid)
    form = await common.form(request)
    common.require(request, "order")
    tests = [t for t in form.getlist("tests") if t]
    try:
        placed = _apply(hospital, lambda s: opd.do_orders(s, e, tests), request, "order",)
    except ValueError as ex:
        return common.redirect(f"/his/encounters/{eid}", str(ex), bad=True)
    what = "; ".join(f"{o['accession'] or o['id']} {o['label']}" for o in placed)
    return common.redirect(f"/his/encounters/{eid}", f"Ordered: {what}.")


@router.post("/encounters/{eid}/notes")
async def note_form_post(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    """The OPD consultation note: an opd_note order signed at once by the consultant (PDF, HL7, FHIR DocumentReference)."""
    e = common.encounter_or_404(hospital.store, eid)
    form = await common.form(request)
    common.require(request, "note")
    try:
        rec, notes = opd.do_note(hospital, request, e, form)
    except FieldError as ex:
        return render_encounter(request, hospital, e, state=FormState(common.values_of(form), {ex.field: ex.message}, "note"),
                                status=422)
    except ValueError as ex:
        return common.redirect(f"/his/encounters/{eid}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"OPD note signed on {e['number']}", notes)
    return common.redirect(f"/his/encounters/{eid}", msg, warn=warn)


@router.post("/encounters/{eid}/discharge-summary")
async def discharge_summary_post(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    e = common.encounter_or_404(hospital.store, eid)
    form = await common.form(request)
    common.require(request, "note")
    try:
        rec, notes = ipd.do_discharge_summary(hospital, request, e, form)
    except FieldError as ex:
        return render_encounter(request, hospital, e, state=FormState(common.values_of(form), {ex.field: ex.message}, "summary"),
                                status=422)
    except ValueError as ex:
        return common.redirect(f"/his/encounters/{eid}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"Discharge summary signed for {e['number']}", notes)
    return common.redirect(f"/his/encounters/{eid}", msg, warn=warn)


# -------------------------------------------------------------------- JSON API (login-free, for tests and the e2e)
def _error(ex):
    if isinstance(ex, DuplicateWarning):
        return JSONResponse({"error": "duplicate", "detail": str(ex), "similar": [x["id"] for x in ex.similar]},
                            status_code=409)
    if isinstance(ex, model.LifecycleError):
        return JSONResponse({"error": "lifecycle", "detail": str(ex)}, status_code=409)
    out = {"error": "invalid", "detail": str(ex)}
    if isinstance(ex, FieldError):
        out["field"] = ex.field
    return JSONResponse(out, status_code=422)


async def _body(request):
    try:
        data = await request.json()
    except Exception:
        data = None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HTTPException(422, "a JSON object is expected")
    return data


def patient_view(store, p):
    return {"patient": {k: v for k, v in p.items()},
            "similar": [summary(store, q) for q in store.similar_registrations(p["id"])],
            "encounters": [encounter_view(store, e) for e in reversed(store.encounters_for(p["id"]))]}


@router.get("/api/search")
def api_search(q: str = "", hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    match, hits = search(store, q)
    return {"q": q, "match": match, "patients": [summary(store, p) for p in hits]}


@router.get("/api/patients/{pid}")
def api_patient(pid: str, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    return patient_view(store, common.patient_or_404(store, pid))


@router.get("/api/encounters")
def api_encounters(kind: str = "", status: str = "", hospital: Hospital = Depends(get_hospital)):
    """Encounters filtered by kind (OP / IP) and status (in-progress, finished), newest first; no orders."""
    store = hospital.store
    out = [e for e in store.encounters.values() if (not kind or e["kind"] == kind.upper()) and (not status or e["status"] == status)]
    out.sort(key=lambda e: (e.get("admitted") or e.get("date") or "", e["number"]), reverse=True)
    return {"encounters": [{**{k: v for k, v in e.items()}, "consultant": _prac(store, e.get("consultant_id")),
                            "heading": encounter_heading(store, e)} for e in out]}


@router.get("/api/encounters/{eid}")
def api_encounter(eid: str, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    return encounter_view(store, common.encounter_or_404(store, eid))


@router.post("/api/registrations")
async def api_register(request: Request, hospital: Hospital = Depends(get_hospital)):
    data = await _body(request)
    try:
        p = _apply(hospital, lambda s: do_register(s, data), request, "register")
    except (ValueError, DuplicateWarning) as ex:
        return _error(ex)
    return {"ok": True, "patient": p, "event": hospital.store.events[-1]["id"]}


def _patient_api(action, key):
    async def handler(pid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
        common.patient_or_404(hospital.store, pid)
        data = await _body(request)
        try:
            e = _apply(hospital, lambda s: action(s, pid, data), request, key)
        except ValueError as ex:
            return _error(ex)
        return {"ok": True, key: encounter_view(hospital.store, e), "event": hospital.store.events[-1]["id"]}
    return handler


router.add_api_route("/api/patients/{pid}/visits", _patient_api(do_visit, "encounter"), methods=["POST"])
router.add_api_route("/api/patients/{pid}/admissions", _patient_api(do_admit, "encounter"), methods=["POST"])


def _encounter_api(action, key):
    async def handler(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
        common.encounter_or_404(hospital.store, eid)
        data = await _body(request)
        try:
            res = _apply(hospital, lambda s: action(s, s.encounters[eid], data), request, key or "change")
        except ValueError as ex:
            return _error(ex)
        out = {"ok": True, "encounter": encounter_view(hospital.store, hospital.store.encounters[eid]), "event": hospital.store.events[-1]["id"]}
        if key:
            out[key] = res
        return out
    return handler


router.add_api_route("/api/encounters/{eid}/refer", _encounter_api(do_refer, "referral"), methods=["POST"])
router.add_api_route("/api/encounters/{eid}/accept", _encounter_api(do_accept, "referral"), methods=["POST"])
router.add_api_route("/api/encounters/{eid}/transfer", _encounter_api(do_transfer, None), methods=["POST"])
router.add_api_route("/api/encounters/{eid}/discharge", _encounter_api(do_discharge, None), methods=["POST"])


@router.post("/api/encounters/{eid}/orders")
async def api_orders(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    """JSON order entry: {"tests": ["cbc", "lft"]} -> the placed orders."""
    e = common.encounter_or_404(hospital.store, eid)
    data = await _body(request)
    tests = data.get("tests") or []
    if not isinstance(tests, list):
        return JSONResponse({"error": "invalid", "detail": "tests must be a list of test keys"}, status_code=422)
    try:
        placed = _apply(hospital, lambda s: opd.do_orders(s, e, [str(t) for t in tests]), request, "order")
    except ValueError as ex:
        return _error(ex)
    return {"ok": True, "orders": [order_view(hospital.store, o) for o in placed]}
