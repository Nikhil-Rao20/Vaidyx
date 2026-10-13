"""The mock hospital's HIS screens (plan item V2-1.6), mounted at /his by his_mock/app.py. SYNTHETIC data only.

    GET  /his                               registration search (UHID, temporary UHID, IP / OP No., ABHA number or
                                            address, accession / Lab No., or a name), recent registrations, new registration
    GET  /his/patients/{patient id}         demographics, similar registrations, the timeline grouped by OP visit and IP
                                            admission (newest first) with each encounter's orders and reports
    GET  /his/encounters/{encounter id}     one encounter: ward history, referrals, orders and reports; refer, accept,
                                            transfer ward, discharge
    POST /his/registrations, /his/patients/{id}/visits | /admissions, /his/encounters/{id}/refer | /accept | /transfer |
         /discharge                         the forms (303 back with ?flash=; a refused transition is a red flash)
    /his/api/...                            the same as JSON for tests and the e2e

Every change goes through a Store transition under hospital.lock, then one HL7 message per new event is appended to
events.hl7 (hl7.append) and the store is saved. A temporary or duplicate registration is shown next to its look-alikes
for a person to link in Vaidyx-TB; the mock never merges registrations. No Aadhaar is ever shown or asked for. No em
dashes in any UI string.
"""
import re
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import hl7, ids, model, ui
from .app import Hospital, get_hospital

router = APIRouter()

NAV = [("HIS", "/his"), ("Reporting desk", "/desk")]
UNITS = ("Unit I", "Unit II", "Unit III", "Casualty")
VISIT_TYPES = (("new", "New"), ("follow_up", "Follow-up"), ("casualty", "Casualty"))
PREAUTH_STATUSES = ("pending", "approved", "rejected")
KINDS = ("permanent", "temporary")
KIND_CLASS = {"permanent": "ok", "temporary": "warn", "duplicate": "bad"}
ABHA_NUMBER = re.compile(r"^\d{2}-\d{4}-\d{4}-\d{4}$")
SIMILAR_NOTE = "Possible duplicate or temporary registration; link in Vaidyx-TB, not merged here"
RECENT = 10


# -------------------------------------------------------------------- small helpers
def _d(value):
    """DD/MM/YYYY of an ISO date or date-time ('' when empty)."""
    return ids.display_date(value) if value else ""


def _plain(name):
    s = re.sub(r"\(\s*synthetic\s*\)", " ", str(name or ""), flags=re.I)
    return " ".join(s.lower().split())


def _prac(store, pid):
    p = store.practitioner(pid) if pid else None
    return p["name"] if p else ""


def _kind_pill(kind):
    return f'<span class="pill {KIND_CLASS.get(kind, "info")}">{ui.esc(kind)}</span>'


def _enc_pill(e):
    return '<span class="pill ok">IP</span>' if e["kind"] == "IP" else '<span class="pill info">OP</span>'


def _visit_type(v):
    return dict(VISIT_TYPES).get(v, v or "").lower()


def _age_sex(p):
    return f"{p['age']} Y / {p['sex']}"


def _address(p):
    a = p.get("address") or {}
    parts = []
    for k in ("line", "town", "district", "state"):
        if a.get(k) and (not parts or parts[-1] != a[k]):
            parts.append(a[k])
    return ", ".join(parts) + (f", PIN {a['pin']}" if a.get("pin") else "")


def _table(headers, rows, empty):
    """ui.table in a horizontally scrolling box, so a wide table never widens the page on a phone."""
    return f'<div style="overflow-x:auto">{ui.table(headers, rows, empty=empty)}</div>'


def _flash(request):
    msg = request.query_params.get("flash")
    if not msg:
        return None
    return ("bad" if request.query_params.get("level") == "bad" else "ok", msg)


def _redirect(url, msg, bad=False):
    q = {"flash": msg}
    if bad:
        q["level"] = "bad"
    return RedirectResponse(f"{url}?{urlencode(q)}", status_code=303)


def _html(title, body, request=None, flash=None):
    return HTMLResponse(ui.page(title, body, nav=NAV, active="HIS", flash=flash or (_flash(request) if request else None)))


def _patient_or_404(store, pid):
    p = store.patients.get(pid)
    if not p:
        raise HTTPException(404, f"no registration {pid!r}")
    return p


def _encounter_or_404(store, eid):
    e = store.encounters.get(eid)
    if not e:
        raise HTTPException(404, f"no encounter {eid!r}")
    return e


def _treating(store):
    return sorted((d for d in store.departments.values() if d["group"] == "treating"), key=lambda d: d["name"])


def _consultants(store, departments):
    names = {d["name"] for d in departments}
    return sorted((p for p in store.practitioners.values() if p["department"] in names and p["role"] == "consultant"),
                  key=lambda p: (p["department"], p["name"]))


def _wards(store):
    return sorted({h["ward"] for e in store.encounters.values() for h in e.get("ward_history") or [] if h.get("ward")})


def _apply(hospital, change):
    """Run one change under the lock; append one HL7 message per new event; save. Errors leave nothing appended."""
    with hospital.lock:
        store = hospital.store
        n = len(store.events)
        result = change(store)
        for ev in store.events[n:]:
            hl7.append(store, ev, hospital.files["hl7"])
        if len(store.events) > n:
            hospital.save()
    return result


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
    return _table(["Name", "UHID", "Registration", "Age / Sex", "Registered on", "ABHA"], rows, empty=empty)


# -------------------------------------------------------------------- orders and reports
def _version_label(v):
    return f"v{v['version']} ({v['status']})"


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


def _order_state(store, o):
    if o["status"] == "scheduled" and o.get("scheduled_for"):
        return f"scheduled for {_d(o['scheduled_for'])}"
    if o["status"] == "sample_collected":
        spec = store.specimens.get(o.get("specimen_id")) or {}
        return f"sample collected {spec.get('barcode') or ''}".strip()
    if o["status"] == "cancelled":
        return f"cancelled {_d(o.get('cancelled_on'))}" + (f": {o['cancel_reason']}" if o.get("cancel_reason") else "")
    return ""


def _documents_cell(r):
    if not r:
        return '<span class=muted>no report yet</span>'
    vs = r["versions"]
    parts = []
    for v in vs:
        path = (v.get("document") or {}).get("path")
        label = "PDF" if len(vs) == 1 else _version_label(v)
        if path:
            parts.append(f'<a href="/view/reports/{ui.esc(r["id"])}/{v["version"]}" target=_blank>{ui.esc(label)}</a>')
        else:
            parts.append(f'<span class=muted>{ui.esc(label if len(vs) > 1 else "PDF")} not rendered</span>')
    return "<br>".join(parts)


def _orders_table(store, orders):
    rows = []
    for o in orders:
        r = store.report_for_order(o["id"])
        cur = store.current_version(r) if r and r["versions"] else None
        status = ui.pill(o["status"]) + (" " + ui.pill(r["status"]) if r else "")
        state = _order_state(store, o)
        if state:
            status += f'<br><span class=muted>{ui.esc(state)}</span>'
        acc = f'<span class=mono>{ui.esc(o["accession"])}</span>' if o["accession"] else '<span class=muted>none</span>'
        rows.append([acc, ui.esc(o["label"]), ui.esc(o["performing_department"]), ui.esc(_d(o["ordered_on"])), status,
                     ui.esc(_d(cur["reported_on"])) if cur else "", ("yes" if cur.get("signature_id") else "no") if cur else "",
                     _documents_cell(r)])
    return _table(["Accession / Lab No.", "Test", "Department", "Ordered on", "Status", "Reported on", "Signed",
                     "Document"], rows, empty="No orders on this encounter.")


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
                      f'{lines}{_orders_table(store, _orders(store, e["id"]))}</div>')
    return "".join(panels)


# -------------------------------------------------------------------- transitions shared by the forms and the API
def _field(f, key, default=""):
    v = f.get(key) if f is not None else None
    return default if v is None else str(v).strip()


def do_register(store, f):
    name = " ".join(_field(f, "name").split())
    if not name.endswith("(SYNTHETIC)"):
        raise ValueError('The name must end with "(SYNTHETIC)": the mock hospital holds synthetic patients only.')
    if not _plain(name):
        raise ValueError("A name is required before (SYNTHETIC).")
    sex = _field(f, "sex").upper()
    if sex not in ("F", "M"):
        raise ValueError("Sex must be F or M.")
    try:
        age = int(_field(f, "age"))
    except ValueError:
        raise ValueError("Age must be a whole number of years.") from None
    if not 0 <= age <= 120:
        raise ValueError("Age must be between 0 and 120 years.")
    kind = _field(f, "kind", "permanent") or "permanent"
    if kind not in KINDS:
        raise ValueError("Registration kind must be permanent or temporary.")
    abha = _field(f, "abha_number")
    if abha:
        if not ABHA_NUMBER.match(abha):
            raise ValueError("ABHA number must be 14 digits written 2-4-4-4, for example 99-2600-0000-0001.")
        if kind != "permanent":
            raise ValueError("An ABHA number is linked to a permanent registration only.")
        if store.patient_by_identifier(abha):
            raise model.LifecycleError(f"ABHA number {abha} is already linked to another registration.")
    return store.register_patient(name, sex, age, kind=kind, abha={"number": abha, "address": None} if abha else None)


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
    current = next((e for e in store.encounters_for(pid) if e["kind"] == "IP" and e["status"] == "in-progress"), None)
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
def _register_form():
    return ('<div class=panel><h2>New registration</h2>'
            '<form method=post action="/his/registrations">'
            '<label for=r-name>Name (must end with "(SYNTHETIC)")</label>'
            '<input type=text id=r-name name=name required placeholder="Firstname Surname (SYNTHETIC)">'
            '<label for=r-sex>Sex</label><select id=r-sex name=sex>' + ui.options([("F", "F"), ("M", "M")]) + '</select>'
            '<label for=r-age>Age (years)</label><input type=text id=r-age name=age required inputmode=numeric>'
            '<label for=r-kind>Registration</label><select id=r-kind name=kind>'
            + ui.options([("permanent", "Permanent UHID"), ("temporary", "Temporary UHID (casualty)")]) + '</select>'
            '<label for=r-abha>ABHA number (optional, permanent registration only)</label>'
            '<input type=text id=r-abha name=abha_number placeholder="99-2600-0000-0001">'
            '<p><button type=submit>Register</button></p></form></div>')


@router.get("", response_class=HTMLResponse)
def home(request: Request, q: str = "", hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    match, hits = search(store, q)
    if match == "identifier":
        return RedirectResponse(f"/his/patients/{hits[0]['id']}", status_code=303)
    box = ('<div class=panel><form method=get action="/his">'
           '<label for=q>UHID (permanent or temporary), IP No., OP No., ABHA number or address, Lab No., or name</label>'
           f'<input type=text id=q name=q value="{ui.esc(q)}" placeholder="VXH/26/004201, IP/26/01872, OP/26/118701 or a name">'
           '<p><button type=submit>Search</button></p></form></div>')
    results = ""
    if q.strip():
        results = (f'<div class=panel id=results><h2>Registrations matching "{ui.esc(q.strip())}"</h2>'
                   + _registrations_table(store, hits, "No registration matches this identifier or name.")
                   + '<p class=muted>A person links similar registrations in Vaidyx-TB; the HIS never merges them.</p></div>')
    rec = ('<div class=panel id=recent><h2>Recent registrations</h2>'
           + _registrations_table(store, recent(store), "No registrations yet.") + '</div>')
    return _html("Registration search", box + results + rec + _register_form(), request)


@router.post("/registrations")
async def register(request: Request, hospital: Hospital = Depends(get_hospital)):
    form = await request.form()
    try:
        p = _apply(hospital, lambda s: do_register(s, form))
    except ValueError as e:
        return _redirect("/his", str(e), bad=True)
    return _redirect(f"/his/patients/{p['id']}", f"Registered {p['name']} as {p['uhid']} ({p['registration_kind']}).")


# -------------------------------------------------------------------- HTML: patient
def _dept_options(departments, selected=None):
    return ui.options([(d["name"], d["name"]) for d in departments], selected)


def _consultant_options(store, departments):
    return ui.options([("", "Not assigned")] + [(c["id"], f"{c['name']} ({c['department']})")
                                                 for c in _consultants(store, departments)])


def _patient_forms(store, p):
    tre = _treating(store)
    last = (store.encounters_for(p["id"]) or [None])[-1]
    dsel = last["department"] if last else None
    units = ui.options([(u, u) for u in UNITS])
    visit = ('<div class=panel><h2>New OP visit</h2>'
             f'<form method=post action="/his/patients/{ui.esc(p["id"])}/visits">'
             '<label for=v-dept>Department</label><select id=v-dept name=department>' + _dept_options(tre, dsel) + '</select>'
             '<label for=v-unit>Unit</label><select id=v-unit name=unit>' + units + '</select>'
             '<label for=v-cons>Consultant (of that department)</label><select id=v-cons name=consultant_id>'
             + _consultant_options(store, tre) + '</select>'
             '<label for=v-type>Visit type</label><select id=v-type name=visit_type>' + ui.options(VISIT_TYPES) + '</select>'
             '<p><button type=submit>Open OP visit</button></p></form></div>')
    wards = "".join(f'<option value="{ui.esc(w)}">' for w in _wards(store))
    pre = ui.options([("", "Not requested")] + [(s, s) for s in PREAUTH_STATUSES])
    admit = ('<div class=panel><h2>Admit</h2>'
             f'<form method=post action="/his/patients/{ui.esc(p["id"])}/admissions">'
             '<label for=a-dept>Department</label><select id=a-dept name=department>' + _dept_options(tre, dsel) + '</select>'
             '<label for=a-unit>Unit</label><select id=a-unit name=unit>' + units + '</select>'
             '<label for=a-cons>Consultant (of that department)</label><select id=a-cons name=consultant_id>'
             + _consultant_options(store, tre) + '</select>'
             f'<label for=a-ward>Ward</label><input type=text id=a-ward name=ward list=wards required><datalist id=wards>{wards}</datalist>'
             '<label for=a-bed>Bed</label><input type=text id=a-bed name=bed required>'
             '<label for=a-pre>PM-JAY Pre-Authorization status (optional)</label><select id=a-pre name=pmjay_preauth>'
             + pre + '</select>'
             '<p><button type=submit>Admit</button></p></form></div>')
    return f'<div class=grid>{visit}{admit}</div>'


@router.get("/patients/{pid}", response_class=HTMLResponse)
def patient_page(pid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    p = _patient_or_404(store, pid)
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
    body = f'<div class=panel id=demographics>{demo}</div>'
    sim = store.similar_registrations(p["id"])
    if sim:
        body += ('<div class=panel id=similar><h2>Similar registrations</h2>'
                 f'<p><span class="pill warn">Check</span> {ui.esc(SIMILAR_NOTE)}</p>'
                 + _registrations_table(store, sim, "") + '</div>')
    body += '<h2>Timeline (OP visits and IP admissions, newest first)</h2>' + _timeline(store, p)
    body += _patient_forms(store, p)
    return _html(f"{p['name']}, {p['uhid']}", body, request)


@router.post("/patients/{pid}/visits")
async def visit_form(pid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    _patient_or_404(hospital.store, pid)
    form = await request.form()
    try:
        e = _apply(hospital, lambda s: do_visit(s, pid, form))
    except ValueError as ex:
        return _redirect(f"/his/patients/{pid}", str(ex), bad=True)
    return _redirect(f"/his/patients/{pid}", f"OP visit {e['number']} opened in {e['department']} {e['unit']}.")


@router.post("/patients/{pid}/admissions")
async def admit_form(pid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    _patient_or_404(hospital.store, pid)
    form = await request.form()
    try:
        e = _apply(hospital, lambda s: do_admit(s, pid, form))
    except ValueError as ex:
        return _redirect(f"/his/patients/{pid}", str(ex), bad=True)
    return _redirect(f"/his/encounters/{e['id']}", f"Admitted under {e['number']}, {e['ward']} bed {e['bed']}.")


# -------------------------------------------------------------------- HTML: encounter
def _encounter_forms(store, e):
    eid = ui.esc(e["id"])
    others = sorted((d for d in store.departments.values() if d["name"] != e["department"]),
                    key=lambda d: (d["group"] != "treating", d["name"]))
    froms = [e["department"]] + [r["to"] for r in e.get("referrals") or [] if r["status"] == "accepted"]
    froms = list(dict.fromkeys(froms))
    from_field = ""
    if len(froms) > 1:
        from_field = ('<label for=f-from>From</label><select id=f-from name=from>'
                      + ui.options([(x, x) for x in froms]) + '</select>')
    parts = [('<div class=panel id=refer><h2>Refer to department</h2>'
              f'<form method=post action="/his/encounters/{eid}/refer">{from_field}'
              '<label for=f-to>To</label><select id=f-to name=to>' + _dept_options(others) + '</select>'
              '<label for=f-reason>Reason</label><textarea id=f-reason name=reason required></textarea>'
              '<p><button type=submit>Refer</button></p></form></div>')]
    open_refs = [r for r in e.get("referrals") or [] if r["status"] == "requested"]
    if open_refs:
        btns = "".join(f'<form class=inline method=post action="/his/encounters/{eid}/accept">'
                       f'<input type=hidden name=to value="{ui.esc(r["to"])}">'
                       f'<button type=submit class=secondary>Accepted by {ui.esc(r["to"])}</button></form> '
                       for r in open_refs)
        parts.append(f'<div class=panel id=accept><h2>Accept referral</h2><p>{btns}</p></div>')
    if e["kind"] == "IP" and e["status"] == "in-progress":
        wards = "".join(f'<option value="{ui.esc(w)}">' for w in _wards(store))
        parts.append('<div class=panel id=transfer><h2>Transfer ward</h2>'
                     f'<form method=post action="/his/encounters/{eid}/transfer">'
                     f'<label for=t-ward>Ward</label><input type=text id=t-ward name=ward list=wards required value="{ui.esc(e.get("ward"))}">'
                     f'<datalist id=wards>{wards}</datalist>'
                     '<label for=t-bed>Bed</label><input type=text id=t-bed name=bed required>'
                     '<label for=t-reason>Reason (optional)</label><input type=text id=t-reason name=reason>'
                     '<p><button type=submit>Transfer</button></p></form></div>')
        parts.append('<div class=panel id=discharge><h2>Discharge</h2>'
                     f'<form method=post action="/his/encounters/{eid}/discharge">'
                     f'<p class=muted>Discharge {ui.esc(e["number"])} from {ui.esc(e.get("ward"))}, bed {ui.esc(e.get("bed"))}.</p>'
                     '<p><button type=submit class=danger>Discharge</button></p></form></div>')
    return f'<div class=grid>{"".join(parts)}</div>'


@router.get("/encounters/{eid}", response_class=HTMLResponse)
def encounter_page(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    e = _encounter_or_404(store, eid)
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
                 + _table(["Ward", "Bed", "From", "Reason"], rows, empty="No ward recorded.") + '</div>')
    rows = [[ui.esc(r["from"]), ui.esc(r["to"]), ui.esc(_d(r["on"])), ui.esc(r.get("reason") or ""), ui.pill(r["status"]),
             ui.esc(_d(r.get("accepted_on")))] for r in e.get("referrals") or []]
    body += ('<div class=panel id=referrals><h2>Referrals</h2>'
             + _table(["From", "To", "On", "Reason", "Status", "Accepted on"], rows, empty="No referral on this encounter.")
             + '</div>')
    body += ('<div class=panel id=orders><h2>Orders and reports</h2>' + _orders_table(store, _orders(store, e["id"])) + '</div>')
    body += _encounter_forms(store, e)
    return _html(encounter_heading(store, e), body, request)


def _encounter_post(action, label):
    async def handler(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
        _encounter_or_404(hospital.store, eid)
        form = await request.form()
        try:
            res = _apply(hospital, lambda s: action(s, s.encounters[eid], form))
        except ValueError as ex:
            return _redirect(f"/his/encounters/{eid}", str(ex), bad=True)
        return _redirect(f"/his/encounters/{eid}", label(hospital.store.encounters[eid], res))
    return handler


router.add_api_route("/encounters/{eid}/refer", _encounter_post(
    do_refer, lambda e, r: f"Referral from {r['from']} to {r['to']} requested."), methods=["POST"])
router.add_api_route("/encounters/{eid}/accept", _encounter_post(
    do_accept, lambda e, r: f"Referral accepted by {r['to']}."), methods=["POST"])
router.add_api_route("/encounters/{eid}/transfer", _encounter_post(
    do_transfer, lambda e, r: f"{e['number']} transferred to {e['ward']}, bed {e['bed']}."), methods=["POST"])
router.add_api_route("/encounters/{eid}/discharge", _encounter_post(
    do_discharge, lambda e, r: f"{e['number']} discharged."), methods=["POST"])


# -------------------------------------------------------------------- JSON API
def _error(ex):
    if isinstance(ex, model.LifecycleError):
        return JSONResponse({"error": "lifecycle", "detail": str(ex)}, status_code=409)
    return JSONResponse({"error": "invalid", "detail": str(ex)}, status_code=422)


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
    return patient_view(store, _patient_or_404(store, pid))


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
    return encounter_view(store, _encounter_or_404(store, eid))


@router.post("/api/registrations")
async def api_register(request: Request, hospital: Hospital = Depends(get_hospital)):
    data = await _body(request)
    try:
        p = _apply(hospital, lambda s: do_register(s, data))
    except ValueError as ex:
        return _error(ex)
    return {"ok": True, "patient": p, "event": hospital.store.events[-1]["id"]}


def _patient_api(action, key):
    async def handler(pid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
        _patient_or_404(hospital.store, pid)
        data = await _body(request)
        try:
            e = _apply(hospital, lambda s: action(s, pid, data))
        except ValueError as ex:
            return _error(ex)
        return {"ok": True, key: encounter_view(hospital.store, e), "event": hospital.store.events[-1]["id"]}
    return handler


router.add_api_route("/api/patients/{pid}/visits", _patient_api(do_visit, "encounter"), methods=["POST"])
router.add_api_route("/api/patients/{pid}/admissions", _patient_api(do_admit, "encounter"), methods=["POST"])


def _encounter_api(action, key):
    async def handler(eid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
        _encounter_or_404(hospital.store, eid)
        data = await _body(request)
        try:
            res = _apply(hospital, lambda s: action(s, s.encounters[eid], data))
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
