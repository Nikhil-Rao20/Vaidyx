"""The OPD module of the demo HIMS, mounted at /his by app.py. SYNTHETIC data only.

    GET  /his/opd?date=&department=&unit=   today's OPD list by department / unit (and the recent OP visits), the
                                            clinical and procedure reports the units still have to write
    GET  /his/opd/orders/{order id}         a clinical note or procedure report the treating unit (or a consulting
                                            department) writes itself: enter, save preliminary, sign, addendum, cancel
    POST /his/opd/orders/{order id}/report | /addendum | /cancel

The OPD note form, the order entry form (tests grouped by performing department) and their actions (`note_form`,
`order_form`, `do_note`, `do_orders`) live here and are used by the encounter page of screens.py (which owns the
/his/encounters/{id}/notes and /orders routes). An OPD note is an `opd_note` order signed at once by the consultant, so
it renders as a PDF, goes out as ORU on the HL7 feed and shows in FHIR as a DocumentReference. No em dashes.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from . import common, model, templates, ui
from .app import Hospital, get_hospital
from .common import FieldError, FormState, d

router = APIRouter()

NOTE_TEST = "opd_note"


# -------------------------------------------------------------------- forms on the encounter page
def _fields_form(request, fields, state, prefix="v_", presets=None):
    st = state or common.EMPTY
    out = []
    for f in fields:
        name = prefix + f["key"]
        val = st.v(name, (presets or {}).get(f["key"], ""))
        if f["rows"]:
            ctl = ui.textarea(name, val, rows=f["rows"], required=f["required"], placeholder=f["example"])
        else:
            ctl = ui.text_input(name, val, required=f["required"], placeholder=f["example"])
        out.append(ui.field(name, f["label"] + (" *" if f["required"] else ""), ctl, st.err(name), f.get("help")))
    return "".join(out)


def note_form(request, store, e, state=None):
    """The OPD consultation note form (presenting complaint, examination, clinical question, plan)."""
    if not common.can(request, "note"):
        return '<div class=panel id=note><h2>OPD consultation note</h2>' + common.refused_line(request, "note") + '</div>'
    not_ours = common.not_own_department(request, store, e["department"])
    if not_ours:
        return f'<div class=panel id=note><h2>OPD consultation note</h2><p class=muted>{ui.esc(not_ours)}</p></div>'
    me = common.practitioner(request, store)
    st = state if state is not None and state.form == "note" else None
    who = (f'<p class=muted>Signed by {ui.esc(me["name"])}, Reg. No. {ui.esc(me["reg_no"])} (Vaidyx Demo CA).</p>' if me
           else '<p class=muted>This account is not a consultant: the note cannot be signed.</p>')
    return ('<div class=panel id=note><h2>OPD consultation note</h2>'
            f'<form method=post action="/his/encounters/{ui.esc(e["id"])}/notes">{common.csrf_field(request)}'
            + _fields_form(request, templates.OPD_NOTE, st) + who
            + '<p><button type=submit class=primary>Sign the note</button></p></form></div>')


def orderable(test):
    """Investigations, procedures and consultations of a department are ordered; the unit's own records (OPD note,
    referral note, discharge summary: any_treating) are written on the visit page instead."""
    return test["department"] != "any_treating"


def orderable_tests(store):
    """The tests of the service master grouped by performing department: [(department, [(key, label)])], supporting
    departments first, the unit's own records (any_treating) left out."""
    groups = {}
    for key, t in sorted(store.tests.items(), key=lambda kv: (kv[1]["department"], kv[1]["label"])):
        if not orderable(t):
            continue
        groups.setdefault(t["department"], []).append((key, t["label"]))
    order = sorted(groups, key=lambda name: ((store.department(name) or {}).get("group") != "supporting", name))
    return [(name, groups[name]) for name in order]


def order_form(request, store, e):
    """Order entry: tick tests grouped by performing department."""
    if not common.can(request, "order"):
        return '<div class=panel id=order-entry><h2>Order entry</h2>' + common.refused_line(request, "order") + '</div>'
    parts = []
    for dept, tests in orderable_tests(store):
        boxes = "".join(f'<label><input type=checkbox name=tests value="{ui.esc(k)}"> {ui.esc(l)}</label>' for k, l in tests)
        parts.append(f'<h3>{ui.esc(dept)}</h3>{boxes}')
    return ('<div class=panel id=order-entry><h2>Order entry</h2>'
            f'<form method=post action="/his/encounters/{ui.esc(e["id"])}/orders">{common.csrf_field(request)}'
            f'<div class=checks>{"".join(parts)}</div>'
            '<p class=small>Each ticked test becomes one order of the performing department (Lab No. / accession No. '
            'allocated by it); clinical notes are written on this page, not ordered.</p>'
            '<p><button type=submit class=primary>Place orders</button></p></form></div>')


# -------------------------------------------------------------------- actions
def do_orders(store, e, tests):
    """Place one order per test key on the encounter (ORM O01 each). ValueError when nothing or an unknown test."""
    if not tests:
        raise ValueError("Tick at least one test to order.")
    placed = []
    for key in tests:
        if key not in store.tests:
            raise ValueError(f"Unknown test {key!r}.")
        if not orderable(store.tests[key]):
            raise ValueError(f"{store.tests[key]['label']} is written on the visit page, not ordered.")
        placed.append(store.place_order(e["patient_id"], e["id"], key, e["department"]))
    return placed


def do_note(hospital, request, e, form):
    """An OPD note: place the opd_note order and sign it at once (PDF, HL7 ORU F). Returns (report, notes)."""
    store = hospital.store
    prac = common.signer(request, store)
    common.require_own_department(request, store, e["department"])
    values, errors = templates.parse_fields(templates.OPD_NOTE, form)
    if errors:
        field, msg = next(iter(errors.items()))
        raise FieldError(field, msg)
    dept = store.department(e["department"])

    def change(s):
        o = s.place_order(e["patient_id"], e["id"], NOTE_TEST, e["department"])
        return s.sign_final(o["id"], prac["id"], values=values)

    return common.run(hospital, request, dept, "sign", change, detail=f"opd_note on {e['number']}")


def _clinical_dept(store, o):
    return store.department(o["performing_department"]) or store.department(o["ordering_department"])


def own_department(request, store, o):
    """None when the signed-in consultant belongs to the department that performs this clinical or procedure report,
    else the plain reason."""
    dept = _clinical_dept(store, o)
    return common.not_own_department(request, store, dept["name"] if dept else o["performing_department"])


def _require_own(request, store, o):
    dept = _clinical_dept(store, o)
    common.require_own_department(request, store, dept["name"] if dept else o["performing_department"])


def do_report(hospital, request, o, form, action):
    """Enter a clinical / procedure report: `preliminary` (saved, verification awaited) or `sign` (final, signed)."""
    store = hospital.store
    _require_own(request, store, o)
    fields = templates.clinical_fields(o["doc_type"])
    values, errors = templates.parse_fields(fields, form)
    if errors:
        field, msg = next(iter(errors.items()))
        raise FieldError(field, msg)
    dept = _clinical_dept(store, o)
    if action == "sign":
        prac = common.signer(request, store)
        return common.run(hospital, request, dept, "sign", lambda s: s.sign_final(o["id"], prac["id"], values=values),
                          order_id=o["id"], detail=o["test"])
    prac = common.practitioner(request, store)
    if not prac:
        raise ValueError("This account is not a practitioner; a preliminary report needs one.")
    existing = store.report_for_order(o["id"])
    if existing:
        raise model.LifecycleError("A preliminary report exists; sign it (the values typed replace it).")
    return common.run(hospital, request, dept, "preliminary", lambda s: s.report_preliminary(o["id"], prac["id"], values),
                      order_id=o["id"], detail=o["test"])


def do_addendum(hospital, request, r, form):
    store = hospital.store
    prac = common.signer(request, store)
    o = store.orders[r["order_id"]]
    _require_own(request, store, o)
    fields = templates.clinical_fields(o["doc_type"])
    values, errors = templates.parse_fields(fields, form)
    note = common.text(form, "note")
    if not note:
        errors["note"] = "An addendum needs a note saying what changed."
    if errors:
        field, msg = next(iter(errors.items()))
        raise FieldError(field, msg)
    return common.run(hospital, request, _clinical_dept(store, o), "addendum",
                      lambda s: s.amend(r["id"], prac["id"], values, note), order_id=o["id"], report_id=r["id"])


def do_cancel(hospital, request, o, form):
    _require_own(request, hospital.store, o)
    reason = common.text(form, "reason")
    if not reason:
        raise ValueError("Enter the reason for cancelling.")
    return common.run(hospital, request, _clinical_dept(hospital.store, o), "cancel",
                      lambda s: s.cancel_order(o["id"], reason), order_id=o["id"])


# -------------------------------------------------------------------- pages
def _op_visits(store, day=None):
    out = [e for e in store.encounters.values() if e["kind"] == "OP" and (not day or e.get("date") == day)]
    return sorted(out, key=lambda e: (e.get("date") or "", e["number"]), reverse=True)


def _visit_rows(store, visits):
    rows = []
    for e in visits:
        p = store.patients.get(e["patient_id"]) or {}
        n = len(store.orders_for(encounter_id=e["id"]))
        rows.append([f'<a href="/his/encounters/{ui.esc(e["id"])}" class=mono>{ui.esc(e["number"])}</a>',
                     common.patient_cell(store, e), ui.esc(f"{e['department']}, {e.get('unit') or ''}"),
                     ui.esc(common.prac_name(store, e.get("consultant_id")) or "not assigned"),
                     ui.esc((e.get("visit_type") or "").replace("_", " ")), ui.esc(d(e.get("date"))), str(n)])
    return ui.table(["OP No.", "Patient / UHID", "Department, unit", "Consultant", "Visit type", "Date", "Orders"], rows,
                    "No OP visit on this day.")


def pending_clinical(store):
    """Open orders the treating units (and the consulting departments) report themselves, oldest first."""
    out = [o for o in store.orders.values() if common.module_of(o) == "opd" and o["status"] in model.OPEN_ORDER]
    out += [store.orders[r["order_id"]] for r in store.reports.values() if r["status"] == "preliminary"
            and common.module_of(store.orders[r["order_id"]]) == "opd"]
    seen, uniq = set(), []
    for o in out:
        if o["id"] not in seen:
            seen.add(o["id"])
            uniq.append(o)
    return sorted(uniq, key=lambda o: (o["ordered_on"], o["id"]))


@router.get("/opd", response_class=HTMLResponse)
def opd_home(request: Request, date: str = "", department: str = "", unit: str = "",
             hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    day = date.strip() or common.today(store)
    visits = _op_visits(store, day)
    if department:
        visits = [e for e in visits if e["department"] == department]
    if unit:
        visits = [e for e in visits if (e.get("unit") or "") == unit]
    depts = sorted({e["department"] for e in store.encounters.values() if e["kind"] == "OP"})
    units = sorted({e.get("unit") or "" for e in store.encounters.values() if e["kind"] == "OP" and e.get("unit")})
    filters = ('<div class=panel><form method=get action="/his/opd">'
               f'<label class=lbl>Date <input type=date name=date value="{ui.esc(day)}" class=short></label> '
               f'<label class=lbl>Department <select name=department class=short>{ui.options([("", "All")] + [(x, x) for x in depts], department)}</select></label> '
               f'<label class=lbl>Unit <select name=unit class=short>{ui.options([("", "All")] + [(x, x) for x in units], unit)}</select></label> '
               '<button type=submit>Show</button></form></div>')
    body = filters + f'<div class=panel id=today><h2>OPD list of {ui.esc(d(day))}</h2>{_visit_rows(store, visits)}</div>'
    body += ('<div class=panel id=recent-visits><h2>Recent OP visits</h2>' + _visit_rows(store, _op_visits(store)[:15])
             + '</div>')
    rows = []
    for o in pending_clinical(store):
        r = store.report_for_order(o["id"])
        rows.append([f'<a href="{common.order_url(o)}">{ui.esc(o["label"])}</a>', common.patient_cell(store, o),
                     common.encounter_cell(store, o), ui.esc(o["performing_department"]), ui.esc(d(o["ordered_on"])),
                     ui.pill(o["status"]) + (" " + ui.pill(r["status"]) if r else "")])
    body += ('<div class=panel id=clinical><h2>Clinical and procedure reports to write</h2>'
             + ui.table(["Report", "Patient / UHID", "IP / OP No.", "Department", "Ordered on", "Status"], rows,
                        "Nothing pending.") + '</div>')
    body += ('<p class=muted>New OP visit: search the patient in Registration and use "New OP visit" on the patient page. '
             'The OPD note and the order entry are on the visit page.</p>')
    return common.page(request, "OPD", body, active="OPD")


def _report_panel(request, store, o, r, state):
    """Entry / sign / addendum forms of a clinical or procedure report."""
    fields = templates.clinical_fields(o["doc_type"])
    me = common.practitioner(request, store)
    csrf = common.csrf_field(request)
    base = f"/his/opd/orders/{ui.esc(o['id'])}"
    out = ""
    not_ours = own_department(request, store, o) if common.can(request, "note") else None
    if not_ours and (o["status"] in model.OPEN_ORDER or r):
        out += f'<div class=panel id=report><h2>Report</h2><p class=muted>{ui.esc(not_ours)}</p></div>'
    elif o["status"] in model.OPEN_ORDER or (r and r["status"] == "preliminary"):
        if common.can(request, "note"):
            st = state if state is not None and state.form == "report" else None
            presets = dict(store.current_version(r)["values"]) if r else {}
            btn_prelim = '<button type=submit name=action value=preliminary>Save preliminary</button> ' if not r and me else ""
            out += (f'<div class=panel id=report><h2>{"Verify and sign" if r else "Enter"} the report</h2>'
                    f'<form method=post action="{base}/report">{csrf}' + _fields_form(request, fields, st, presets=presets)
                    + f'<p>{btn_prelim}<button type=submit name=action value=sign class=primary>Sign final</button></p></form></div>')
            out += (f'<div class=panel id=cancel><h2>Cancel</h2><form method=post action="{base}/cancel">{csrf}'
                    + ui.field("reason", "Reason", ui.text_input("reason", required=True))
                    + '<p><button type=submit class=danger>Cancel order</button></p></form></div>')
        else:
            out += '<div class=panel id=report><h2>Enter the report</h2>' + common.refused_line(request, "note") + '</div>'
    elif r and r["status"] in ("final", "amended"):
        if common.can(request, "note"):
            st = state if state is not None and state.form == "addendum" else None
            out += (f'<div class=panel id=addendum><h2>Addendum</h2><form method=post action="{base}/addendum">{csrf}'
                    + _fields_form(request, fields, st, presets=store.current_version(r)["values"])
                    + ui.field("note", "Amendment note *", ui.text_input("note", st.v("note") if st else "", required=True),
                               st.err("note") if st else None)
                    + '<p><button type=submit class=primary>Sign addendum</button></p></form></div>')
    else:
        out += f'<p class=muted>This order is {ui.esc(o["status"])}; no action is open.</p>'
    return out


def render_order(request, hospital, o, state=None, status=200):
    store = hospital.store
    p = store.patients[o["patient_id"]]
    e = store.encounters.get(o["encounter_id"])
    r = store.report_for_order(o["id"])
    body = common.order_panel(store, o)
    if r:
        v = store.current_version(r)
        body += (f'<div class=panel id=current><h2>{ui.esc(r["title"])} {ui.pill(r["status"])}</h2>'
                 + common.values_table(v["values"]) + '<h3>Versions</h3>' + common.versions_table(store, r) + '</div>')
    body += _report_panel(request, store, o, r, state)
    body += f'<p><a href="/his/encounters/{ui.esc(o["encounter_id"])}">Back to the visit</a> | <a href="/his/opd">OPD</a></p>'
    return common.page(request, f"{o['label']}: {o['accession'] or o['id']}", body, active="OPD",
                       banner=common.banner(store, p, e), status=status)


@router.get("/opd/orders/{oid}", response_class=HTMLResponse)
def order_page(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    if common.module_of(o) != "opd":
        return common.redirect(common.order_url(o))
    return render_order(request, hospital, o)


@router.post("/opd/orders/{oid}/report")
async def report_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    form = await common.form(request)
    common.require(request, "note")
    action = "sign" if common.text(form, "action", "sign") == "sign" else "preliminary"
    try:
        rec, notes = do_report(hospital, request, o, form, action)
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "report"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/opd/orders/{oid}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"{o['label']}: {rec['status']}", notes)
    return common.redirect(f"/his/opd/orders/{oid}", msg, warn=warn)


@router.post("/opd/orders/{oid}/addendum")
async def addendum_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    r = hospital.store.report_for_order(o["id"])
    if not r:
        return common.redirect(f"/his/opd/orders/{oid}", "No report to amend yet.", bad=True)
    form = await common.form(request)
    common.require(request, "note")
    try:
        rec, notes = do_addendum(hospital, request, r, form)
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "addendum"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/opd/orders/{oid}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"Addendum signed: {o['label']} v{rec['current_version']}", notes)
    return common.redirect(f"/his/opd/orders/{oid}", msg, warn=warn)


@router.post("/opd/orders/{oid}/cancel")
async def cancel_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    form = await common.form(request)
    common.require(request, "note")
    try:
        rec, notes = do_cancel(hospital, request, o, form)
    except ValueError as ex:
        return common.redirect(f"/his/opd/orders/{oid}", str(ex), bad=True)
    return common.redirect(f"/his/opd/orders/{oid}", f"{o['label']} cancelled.")
