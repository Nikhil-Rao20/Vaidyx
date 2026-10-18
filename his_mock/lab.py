"""The Laboratory module (LIS) of the demo HIMS, mounted at /his by app.py. SYNTHETIC data only.

    GET  /his/lab?tab=ordered|collected|entered|verified&dept=   the work list of the laboratory orders (CBC under
                                                                  Pathology, LFT / RFT / CEA under Biochemistry, viral
                                                                  markers under Microbiology)
    GET  /his/lab/orders/{order id}                               one order: collect sample (barcode VXS...), result
                                                                  entry per test template (Indian units, reference
                                                                  intervals), verify and sign (lab.doctor), amendment,
                                                                  cancel, the signed PDF
    GET  /his/lab/orders/{order id}/label                         the printable sample label
    POST /his/lab/orders/{order id}/collect | /result | /verify | /cancel, /his/lab/reports/{report id}/amend

Every action runs through the reporting engine (common.run -> desk.run_action): the Store transition under the lock,
the PDF of the new version, the HL7 message, the save and the audit lines. The technician collects and enters; only the
laboratory consultant verifies and signs (auth.PERMISSIONS). No em dashes.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from . import common, model, templates, ui
from .app import Hospital, get_hospital
from .common import FieldError, FormState, dt

router = APIRouter()

TABS = [("ordered", "Ordered"), ("collected", "Sample collected"), ("entered", "Results entered"), ("verified", "Verified")]
RECENT_VERIFIED = 25


# The next step for each worklist tab, as a button straight to its form (18 Oct: the Lab No. link alone did not say what to do).
NEXT_STEP = {'ordered': ('Collect sample', '#collect'), 'collected': ('Enter results', '#result'), 'entered': ('Verify and sign', '#verify'), 'verified': ('View', '#current')}


def action_cell(o, tab):
    label, anchor = NEXT_STEP.get(tab, ("Open", ""))
    return f'<a class="btn primary" href="/his/lab/orders/{ui.esc(o["id"])}{anchor}">{ui.esc(label)}</a>'


# -------------------------------------------------------------------- the work list
def lab_orders(store, dept=None):
    out = [o for o in store.orders.values() if common.is_lab(o)]
    if dept:
        dd = store.department(dept)
        out = [o for o in out if dd and o["performing_department"] == dd["name"]]
    return out


def bucket(store, o):
    """ordered | collected | entered | verified | cancelled."""
    if o["status"] == "cancelled":
        return "cancelled"
    r = store.report_for_order(o["id"])
    if r:
        v = store.current_version(r)
        if r["status"] == "cancelled":
            return "cancelled"
        if r["status"] == "preliminary" or (r["status"] == "final" and not v.get("signature_id")):
            return "entered"
        return "verified"
    return "collected" if o["status"] == "sample_collected" else "ordered"


def worklist(store, tab, dept=None):
    rows = [o for o in lab_orders(store, dept) if bucket(store, o) == tab]
    if tab == "verified":
        rows.sort(key=lambda o: (store.current_version(store.report_for_order(o["id"]))["reported_on"], o["id"]), reverse=True)
        return rows[:RECENT_VERIFIED]
    return sorted(rows, key=lambda o: (o["ordered_on"], o["id"]))


def counts(store, dept=None):
    out = {k: 0 for k, _ in TABS}
    for o in lab_orders(store, dept):
        b = bucket(store, o)
        if b in out:
            out[b] += 1
    return out


def _sample_cell(store, o):
    if o.get("specimen_id"):
        s = store.specimens.get(o["specimen_id"]) or {}
        return f'<span class=mono>{ui.esc(s.get("barcode"))}</span><br><span class=small>{ui.esc(dt(s.get("collected_on")))}</span>'
    return '<span class=muted>not collected</span>'


def _report_cell(store, o):
    r = store.report_for_order(o["id"])
    if not r:
        return '<span class=muted>none</span>'
    v = store.current_version(r)
    sig = store.signatures.get(v.get("signature_id") or "") or {}
    who = common.prac_name(store, sig.get("signer_id")) if sig else common.prac_name(store, v.get("reported_by"))
    return ui.pill(r["status"]) + f'<br><span class=small>{ui.esc(who)}, {ui.esc(dt(v["reported_on"]))}</span>'


@router.get("/lab", response_class=HTMLResponse)
def lab_home(request: Request, tab: str = "ordered", dept: str = "", hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    tab = tab if tab in dict(TABS) else "ordered"
    labs = sorted({o["performing_department"] for o in lab_orders(store)})
    codes = [(store.department(n) or {}).get("code") for n in labs]
    n = counts(store, dept or None)
    base = "/his/lab" + (f"?dept={ui.esc(dept)}" if dept else "")
    filt = ('<div class=panel><form method=get action="/his/lab">'
            f'{ui.hidden("tab", tab)}<label class=lbl>Laboratory <select name=dept class=short>'
            + ui.options([("", "All laboratories")] + [(c, f"{nm} ({c})") for nm, c in zip(labs, codes)], dept)
            + '</select></label> <button type=submit>Show</button></form></div>')
    rows = []
    for o in worklist(store, tab, dept or None):
        rows.append([f'<a href="/his/lab/orders/{ui.esc(o["id"])}" class=mono>{ui.esc(o["accession"] or o["id"])}</a>',
                     common.patient_cell(store, o), common.encounter_cell(store, o), ui.esc(o["label"]),
                     ui.esc(o["performing_department"]), ui.esc(dt(o["ordered_on"])), common.unit_cell(store, o),
                     _sample_cell(store, o), _report_cell(store, o), common.documents_cell(store.report_for_order(o["id"])),
                     action_cell(o, tab)])
    body = (filt + ui.tabs([(k, l, n[k]) for k, l in TABS], tab, base)
            + '<div class=panel id=worklist>'
            + ui.table(["Lab No.", "Patient / UHID", "IP / OP No.", "Test", "Laboratory", "Ordered on", "Ordering unit",
                        "Sample", "Report", "PDF", "Action"], rows, f"No order under '{dict(TABS)[tab]}'.") + '</div>')
    return common.page(request, "Laboratory (LIS)", body, active="Laboratory")


# -------------------------------------------------------------------- one order
def _dept(store, o):
    return store.department(o["performing_department"])


def _result_fields(request, template, sex, state, presets=None):
    st = state or common.EMPTY
    out = []
    for f in template["fields"]:
        name = "v_" + f["key"]
        preset = (presets or {}).get(f["key"], "")
        if f["kind"] == "numeric":
            val = st.v(name, preset.rsplit(" " + f["unit"], 1)[0] if preset and f["unit"] and preset.endswith(f["unit"]) else preset)
            ctl = (ui.text_input(name, val, short=True, placeholder=f["example"], extra=" inputmode=decimal")
                   + f' <span class=small>{ui.esc(f["unit"])}</span>'
                   f' <span class="small muted">Reference interval: {ui.esc(templates.reference_text(f, sex))}</span>')
        else:
            val = st.v(name, preset)
            ctl = ui.select(name, [("", "Choose")] + [(x, x) for x in f["options"]], val, short=True)
        out.append(ui.field(name, f["label"], ctl, st.err(name)))
    return "".join(out)


def _label_block(store, o, spec):
    p = store.patients[o["patient_id"]]
    e = store.encounters.get(o["encounter_id"]) or {}
    return (f'<div class=label-print>{ui.esc(spec["barcode"])} | {ui.esc(p["name"])} | {ui.esc(p["uhid"])} | '
            f'{ui.esc(common.age_sex(p))} | {ui.esc(e.get("number"))} | {ui.esc(o["label"])} | '
            f'{ui.esc(dt(spec["collected_on"]))}</div>')


def render_order(request, hospital, o, state=None, status=200):
    store = hospital.store
    p = store.patients[o["patient_id"]]
    e = store.encounters.get(o["encounter_id"])
    r = store.report_for_order(o["id"])
    spec = store.specimens.get(o.get("specimen_id")) if o.get("specimen_id") else None
    template = templates.lab_template(o["test"])
    csrf = common.csrf_field(request)
    base = f"/his/lab/orders/{ui.esc(o['id'])}"
    body = common.order_panel(store, o)
    if spec:
        body += (f'<div class=panel id=label><h2>Sample label</h2>{_label_block(store, o, spec)} '
                 f'<a href="{base}/label" target=_blank>Print label</a></div>')
    if r:
        v = store.current_version(r)
        body += (f'<div class=panel id=current><h2>{ui.esc(r["title"])} {ui.pill(r["status"])}</h2>'
                 + common.values_table(v["values"]) + '<h3>Versions</h3>' + common.versions_table(store, r) + '</div>')
    b = bucket(store, o)
    forms = ""
    if b == "ordered":
        if common.can(request, "lab.collect"):
            forms += (f'<div class=panel id=collect><h2>Collect sample</h2><form method=post action="{base}/collect">{csrf}'
                      '<p class=muted>The barcode (VXS and 8 digits) is allocated by the LIS; the label prints after collection.</p>'
                      '<p><button type=submit class=primary>Collect sample</button></p></form></div>')
        else:
            forms += '<div class=panel id=collect><h2>Collect sample</h2>' + common.refused_line(request, "lab.collect") + '</div>'
    if b in ("ordered", "collected"):
        if common.can(request, "lab.result"):
            st = state if state is not None and state.form == "result" else None
            if template and template["fields"]:
                fields = _result_fields(request, template, p["sex"], st)
            else:
                fields = ui.field("values", "Values (key: value per line)", ui.textarea("values", (st or common.EMPTY).v("values"), rows=5),
                                  (st or common.EMPTY).err("values"))
            forms += (f'<div class=panel id=result><h2>Result entry: {ui.esc(o["label"])}</h2>'
                      f'<form method=post action="{base}/result">{csrf}{fields}'
                      '<p class=small>Results are saved as entered, status preliminary (verification awaited) until the '
                      'laboratory consultant verifies and signs.</p>'
                      '<p><button type=submit class=primary>Save results</button></p></form></div>')
        else:
            forms += '<div class=panel id=result><h2>Result entry</h2>' + common.refused_line(request, "lab.result") + '</div>'
    if b in ("ordered", "collected", "entered"):
        if common.can(request, "lab.sign"):
            st = state if state is not None and state.form == "verify" else None
            presets = dict(store.current_version(r)["values"]) if r else {}
            if template and template["fields"]:
                fields = _result_fields(request, template, p["sex"], st, presets=presets)
            else:
                fields = ui.field("values", "Values (key: value per line)",
                                  ui.textarea("values", (st or common.EMPTY).v("values", "\n".join(f"{k}: {v}" for k, v in presets.items())), rows=5),
                                  (st or common.EMPTY).err("values"))
            me = common.practitioner(request, store)
            forms += (f'<div class=panel id=verify><h2>Verify and sign</h2><form method=post action="{base}/verify">{csrf}{fields}'
                      f'<p class=muted>Signed by {ui.esc(me["name"] if me else "")}, Reg. No. {ui.esc(me["reg_no"] if me else "")} '
                      '(Vaidyx Demo CA); the report becomes final and the NABL-style PDF is rendered.</p>'
                      '<p><button type=submit class=primary>Verify and sign</button></p></form></div>')
        else:
            forms += '<div class=panel id=verify><h2>Verify and sign</h2>' + common.refused_line(request, "lab.sign") + '</div>'
        if common.can(request, "lab.cancel"):
            forms += (f'<div class=panel id=cancel><h2>Cancel</h2><form method=post action="{base}/cancel">{csrf}'
                      + ui.field("reason", "Reason", ui.text_input("reason", required=True))
                      + '<p><button type=submit class=danger>Cancel order</button></p></form></div>')
    elif b == "verified":
        if common.can(request, "lab.sign"):
            st = state if state is not None and state.form == "amend" else None
            presets = dict(store.current_version(r)["values"])
            if template and template["fields"]:
                fields = _result_fields(request, template, p["sex"], st, presets=presets)
            else:
                fields = ui.field("values", "Values (key: value per line)",
                                  ui.textarea("values", (st or common.EMPTY).v("values", "\n".join(f"{k}: {v}" for k, v in presets.items())), rows=5),
                                  (st or common.EMPTY).err("values"))
            forms += (f'<div class=panel id=amend><h2>Amendment</h2><form method=post action="/his/lab/reports/{ui.esc(r["id"])}/amend">{csrf}{fields}'
                      + ui.field("note", "Amendment note *", ui.text_input("note", (st or common.EMPTY).v("note"), required=True),
                                 (st or common.EMPTY).err("note"))
                      + '<p><button type=submit class=primary>Sign amendment</button></p></form></div>')
        else:
            forms += '<div class=panel id=amend><h2>Amendment</h2>' + common.refused_line(request, "lab.sign") + '</div>'
    else:
        forms += f'<p class=muted>This order is {ui.esc(o["status"])}; no action is open.</p>'
    body += forms + '<p><a href="/his/lab">Back to the work list</a></p>'
    return common.page(request, f"{o['label']}: {o['accession'] or o['id']}", body, active="Laboratory",
                       banner=common.banner(store, p, e), status=status)


@router.get("/lab/orders/{oid}", response_class=HTMLResponse)
def order_page(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    if not common.is_lab(o):
        return common.redirect(common.order_url(o))
    return render_order(request, hospital, o)


@router.get("/lab/orders/{oid}/label", response_class=HTMLResponse)
def label_page(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    o = common.order_or_404(store, oid)
    spec = store.specimens.get(o.get("specimen_id")) if o.get("specimen_id") else None
    if not spec:
        return common.redirect(f"/his/lab/orders/{oid}", "No sample collected yet; no label to print.", bad=True)
    body = (f'<div class=panel>{_label_block(store, o, spec)}<p class=small>Sample ID {ui.esc(spec["barcode"])}, '
            f'{ui.esc(spec["type"])}; collected {ui.esc(dt(spec["collected_on"]))}. Print this page for the tube.</p>'
            f'<p><a href="/his/lab/orders/{ui.esc(oid)}">Back to the order</a></p></div>')
    return common.page(request, "Sample label", body, active="Laboratory")


# -------------------------------------------------------------------- actions
def _values_from(form, template, sex, state_name):
    if template and template["fields"]:
        values, errors = templates.parse_lab_form(template, form, sex)
        if errors:
            field, msg = next(iter(errors.items()))
            raise FieldError(field, msg)
        return values
    try:
        values = common.parse_values(form.get("values"))
    except ValueError as e:
        raise FieldError("values", str(e)) from None
    if not values:
        raise FieldError("values", "Enter at least one value.")
    return values


@router.post("/lab/orders/{oid}/collect")
async def collect_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.module_order_or_404(hospital.store, oid, "lab")
    form = await common.form(request)
    common.require(request, "lab.collect")

    def change(s):
        s.collect_sample(o["id"])
        return s.orders[o["id"]]

    try:
        rec, notes = common.run(hospital, request, _dept(hospital.store, o), "collect", change, order_id=o["id"])
    except ValueError as ex:
        return common.redirect(f"/his/lab/orders/{oid}", str(ex), bad=True)
    spec = hospital.store.specimens[rec["specimen_id"]]
    return common.redirect(f"/his/lab/orders/{oid}", f"Sample {spec['barcode']} collected; print the label.")


@router.post("/lab/orders/{oid}/result")
async def result_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    o = common.module_order_or_404(store, oid, "lab")
    form = await common.form(request)
    common.require(request, "lab.result")
    p = store.patients[o["patient_id"]]
    template = templates.lab_template(o["test"])
    try:
        values = _values_from(form, template, p["sex"], "result")
        me = common.practitioner(request, store)
        dept = _dept(store, o)
        reporter = me["id"] if me else _first_staff(store, dept)
        rec, notes = common.run(hospital, request, dept, "preliminary",
                                lambda s: s.report_preliminary(o["id"], reporter, values), order_id=o["id"])
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "result"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/lab/orders/{oid}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"Results saved for {o['accession'] or o['id']} (verification awaited)", notes)
    return common.redirect(f"/his/lab/orders/{oid}", msg, warn=warn)


def _first_staff(store, dept):
    """The department's first practitioner, as the reporter of results a technician entered (the LIS records the
    technician in the audit; the printed report names the verifying consultant once signed)."""
    people = [store.practitioners[x] for x in dept.get("consultants", []) if x in store.practitioners]
    if not people:
        raise model.LifecycleError(f"{dept['name']} has no practitioner to report under")
    return sorted(people, key=lambda x: (x["role"] != "consultant", x["reg_no"]))[0]["id"]


@router.post("/lab/orders/{oid}/verify")
async def verify_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    o = common.module_order_or_404(store, oid, "lab")
    form = await common.form(request)
    common.require(request, "lab.sign")
    p = store.patients[o["patient_id"]]
    template = templates.lab_template(o["test"])
    try:
        prac = common.module_signer(request, store, "lab", o)
        values = _values_from(form, template, p["sex"], "verify")
        rec, notes = common.run(hospital, request, _dept(store, o), "sign",
                                lambda s: s.sign_final(o["id"], prac["id"], values=values), order_id=o["id"],
                                report_id=(store.report_for_order(o["id"]) or {}).get("id"))
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "verify"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/lab/orders/{oid}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"{o['accession'] or o['id']} verified and signed", notes)
    return common.redirect(f"/his/lab/orders/{oid}", msg, warn=warn)


@router.post("/lab/reports/{rid}/amend")
async def amend_post(rid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    r = common.module_report_or_404(store, rid, "lab")
    o = store.orders[r["order_id"]]
    form = await common.form(request)
    common.require(request, "lab.sign")
    p = store.patients[o["patient_id"]]
    template = templates.lab_template(o["test"])
    try:
        prac = common.module_signer(request, store, "lab", o)
        values = _values_from(form, template, p["sex"], "amend")
        note = common.text(form, "note")
        if not note:
            raise FieldError("note", "An amendment needs a note saying what changed.")
        rec, notes = common.run(hospital, request, _dept(store, o), "addendum",
                                lambda s: s.amend(r["id"], prac["id"], values, note), order_id=o["id"], report_id=r["id"])
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "amend"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/lab/orders/{o['id']}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"Amendment signed: {o['accession'] or o['id']} v{rec['current_version']}", notes)
    return common.redirect(f"/his/lab/orders/{o['id']}", msg, warn=warn)


@router.post("/lab/orders/{oid}/cancel")
async def cancel_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.module_order_or_404(hospital.store, oid, "lab")
    form = await common.form(request)
    common.require(request, "lab.cancel")
    reason = common.text(form, "reason")
    if not reason:
        return common.redirect(f"/his/lab/orders/{oid}", "Enter the reason for cancelling.", bad=True)
    try:
        common.run(hospital, request, _dept(hospital.store, o), "cancel", lambda s: s.cancel_order(o["id"], reason), order_id=o["id"])
    except ValueError as ex:
        return common.redirect(f"/his/lab/orders/{oid}", str(ex), bad=True)
    return common.redirect(f"/his/lab/orders/{oid}", f"{o['accession'] or o['id']} cancelled.")
