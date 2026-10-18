"""The Pathology module of the demo HIMS, mounted at /his by app.py. SYNTHETIC data only.

    GET  /his/pathology?tab=ordered|received|entered|signed   the work list of the tissue orders (HPE, IHC, molecular,
                                                              cytology) of the Pathology department
    GET  /his/pathology/orders/{order id}                     one order: specimen receipt (barcode, block No.), report
                                                              entry per template (HPE: specimen, gross, microscopy,
                                                              diagnosis; IHC panel markers, e.g. ihc_breast ER / PR /
                                                              HER2 / Ki-67; molecular; cytology), sign, addendum,
                                                              add-on orders (IHC / molecular on the same encounter), cancel
    POST /his/pathology/orders/{order id}/receive | /report | /sign | /cancel | /addon,
         /his/pathology/reports/{report id}/addendum

Only the pathologist enters and signs; a laboratory technician may receive specimens (auth.PERMISSIONS). No em dashes.
"""
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from . import common, scenarios, templates, ui
from .app import Hospital, get_hospital
from .common import FieldError, FormState, dt

router = APIRouter()

TABS = [("ordered", "Ordered"), ("received", "Specimen received"), ("entered", "Entered"), ("signed", "Signed")]
BLOCK_NO = re.compile(scenarios.load()["identifier_patterns"]["block_no"]["regex"])   # PATH/26/00412-A1
ADDON_DOC_TYPES = ("ihc", "molecular")
RECENT_SIGNED = 25


# -------------------------------------------------------------------- the work list
def tissue_orders(store):
    return [o for o in store.orders.values() if common.is_tissue(o)]


def bucket(store, o):
    if o["status"] == "cancelled":
        return "cancelled"
    r = store.report_for_order(o["id"])
    if r:
        v = store.current_version(r)
        if r["status"] == "cancelled":
            return "cancelled"
        if r["status"] == "preliminary" or (r["status"] == "final" and not v.get("signature_id")):
            return "entered"
        return "signed"
    return "received" if o["status"] == "sample_collected" else "ordered"


def worklist(store, tab):
    rows = [o for o in tissue_orders(store) if bucket(store, o) == tab]
    if tab == "signed":
        rows.sort(key=lambda o: (store.current_version(store.report_for_order(o["id"]))["reported_on"], o["id"]), reverse=True)
        return rows[:RECENT_SIGNED]
    return sorted(rows, key=lambda o: (o["ordered_on"], o["id"]))


def counts(store):
    out = {k: 0 for k, _ in TABS}
    for o in tissue_orders(store):
        b = bucket(store, o)
        if b in out:
            out[b] += 1
    return out


def _specimen_cell(store, o):
    if o.get("specimen_id"):
        s = store.specimens.get(o["specimen_id"]) or {}
        out = f'<span class=mono>{ui.esc(s.get("barcode"))}</span>'
        if s.get("block_no"):
            out += f'<br>Block No. <span class=mono>{ui.esc(s["block_no"])}</span>'
        return out
    return '<span class=muted>not received</span>'


@router.get("/pathology", response_class=HTMLResponse)
def pathology_home(request: Request, tab: str = "ordered", hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    tab = tab if tab in dict(TABS) else "ordered"
    n = counts(store)
    rows = []
    for o in worklist(store, tab):
        r = store.report_for_order(o["id"])
        rows.append([f'<a href="/his/pathology/orders/{ui.esc(o["id"])}" class=mono>{ui.esc(o["accession"] or o["id"])}</a>',
                     common.patient_cell(store, o), common.encounter_cell(store, o), ui.esc(o["label"]),
                     ui.esc(dt(o["ordered_on"])), common.unit_cell(store, o), _specimen_cell(store, o),
                     (ui.pill(r["status"]) if r else '<span class=muted>none</span>'), common.documents_cell(r)])
    body = (ui.tabs([(k, l, n[k]) for k, l in TABS], tab, "/his/pathology") + '<div class=panel id=worklist>'
            + ui.table(["Lab No.", "Patient / UHID", "IP / OP No.", "Test", "Ordered on", "Ordering unit", "Specimen / block",
                        "Report", "PDF"], rows, f"No order under '{dict(TABS)[tab]}'.") + '</div>')
    return common.page(request, "Pathology", body, active="Pathology")


# -------------------------------------------------------------------- one order
def _dept(store, o):
    return store.department(o["performing_department"])


def _fields_form(request, fields, state, presets):
    st = state or common.EMPTY
    out = []
    if fields is None:
        text_ = st.v("values", "\n".join(f"{k}: {v}" for k, v in presets.items()))
        return ui.field("values", "Markers / results (one per line, marker: result)",
                        ui.textarea("values", text_, rows=6, placeholder="er: Positive (Allred score 7/8)"), st.err("values"))
    for f in fields:
        name = "v_" + f["key"]
        val = st.v(name, presets.get(f["key"], ""))
        if f["rows"]:
            ctl = ui.textarea(name, val, rows=f["rows"], required=f["required"], placeholder=f["example"])
        else:
            ctl = ui.text_input(name, val, required=f["required"], placeholder=f["example"])
        out.append(ui.field(name, f["label"] + (" *" if f["required"] else ""), ctl, st.err(name)))
    return "".join(out)


def suggested_block(store, o):
    """The block No. to offer on receipt: an add-on test is cut from the block already received on the same OP visit or
    admission (the newest one); a new specimen gets its accession plus A1."""
    blocks = sorted((sp for sp in store.specimens.values() if sp.get("block_no") and sp["order_id"] != o["id"]
                     and (store.orders.get(sp["order_id"]) or {}).get("encounter_id") == o["encounter_id"]),
                    key=lambda sp: (sp["received_on"] or "", sp["id"]), reverse=True)
    if blocks and o["doc_type"] in ADDON_DOC_TYPES:
        return blocks[0]["block_no"]
    return f"{o['accession']}-A1" if o.get("accession") else ""


def addon_tests(store):
    return [(k, t["label"]) for k, t in sorted(store.tests.items(), key=lambda kv: kv[1]["label"])
            if t["doc_type"] in ADDON_DOC_TYPES and t["department"] == "Pathology"]


def render_order(request, hospital, o, state=None, status=200):
    store = hospital.store
    p = store.patients[o["patient_id"]]
    e = store.encounters.get(o["encounter_id"])
    r = store.report_for_order(o["id"])
    spec = store.specimens.get(o.get("specimen_id")) if o.get("specimen_id") else None
    fields = templates.pathology_fields(o["test"], o["doc_type"])
    csrf = common.csrf_field(request)
    base = f"/his/pathology/orders/{ui.esc(o['id'])}"
    body = common.order_panel(store, o)
    if r:
        v = store.current_version(r)
        body += (f'<div class=panel id=current><h2>{ui.esc(r["title"])} {ui.pill(r["status"])}</h2>'
                 + common.values_table(v["values"]) + '<h3>Versions</h3>' + common.versions_table(store, r) + '</div>')
    b = bucket(store, o)
    forms = ""
    if b == "ordered":
        if common.can(request, "path.receive"):
            st = state if state is not None and state.form == "receive" else None
            suggested = suggested_block(store, o)
            forms += (f'<div class=panel id=receive><h2>Specimen receipt</h2><form method=post action="{base}/receive">{csrf}'
                      + ui.field("block_no", "Block No.", ui.text_input("block_no", (st or common.EMPTY).v("block_no", suggested), short=True),
                                 (st or common.EMPTY).err("block_no"),
                                 help="Accession plus block letter and number, e.g. PATH/26/00412-A1. The barcode (VXS and "
                                      "8 digits) is allocated on receipt.")
                      + '<p><button type=submit class=primary>Receive specimen</button></p></form></div>')
        else:
            forms += '<div class=panel id=receive><h2>Specimen receipt</h2>' + common.refused_line(request, "path.receive") + '</div>'
    if b in ("ordered", "received", "entered"):
        presets = dict(store.current_version(r)["values"]) if r else {}
        if common.can(request, "path.report"):
            st = state if state is not None and state.form == "report" else None
            me = common.practitioner(request, store)
            btn_prelim = '<button type=submit name=action value=preliminary>Save preliminary</button> ' if not r else ""
            forms += (f'<div class=panel id=report><h2>{"Sign" if r else "Report entry"}: {ui.esc(o["label"])}</h2>'
                      f'<form method=post action="{base}/report">{csrf}' + _fields_form(request, fields, st, presets)
                      + f'<p class=muted>Signed by {ui.esc(me["name"] if me else "")}, Reg. No. {ui.esc(me["reg_no"] if me else "")} (Vaidyx Demo CA).</p>'
                      + f'<p>{btn_prelim}<button type=submit name=action value=sign class=primary>Sign final</button></p></form></div>')
            forms += (f'<div class=panel id=cancel><h2>Cancel</h2><form method=post action="{base}/cancel">{csrf}'
                      + ui.field("reason", "Reason", ui.text_input("reason", required=True))
                      + '<p><button type=submit class=danger>Cancel order</button></p></form></div>')
        else:
            forms += '<div class=panel id=report><h2>Report entry</h2>' + common.refused_line(request, "path.report") + '</div>'
    elif b == "signed":
        if common.can(request, "path.sign"):
            st = state if state is not None and state.form == "addendum" else None
            forms += (f'<div class=panel id=addendum><h2>Addendum</h2><form method=post action="/his/pathology/reports/{ui.esc(r["id"])}/addendum">{csrf}'
                      + _fields_form(request, fields, st, dict(store.current_version(r)["values"]))
                      + ui.field("note", "Amendment note *", ui.text_input("note", (st or common.EMPTY).v("note"), required=True),
                                 (st or common.EMPTY).err("note"))
                      + '<p><button type=submit class=primary>Sign addendum</button></p></form></div>')
        else:
            forms += '<div class=panel id=addendum><h2>Addendum</h2>' + common.refused_line(request, "path.sign") + '</div>'
    else:
        forms += f'<p class=muted>This order is {ui.esc(o["status"])}; no action is open.</p>'
    if common.can(request, "path.addon") and o["status"] != "cancelled":
        forms += (f'<div class=panel id=addon><h2>Add-on order (same encounter)</h2><form method=post action="{base}/addon">{csrf}'
                  + ui.field("test", "Test", ui.select("test", addon_tests(store)))
                  + '<p class=small>An IHC panel or molecular test the pathologist adds on the block of this specimen; '
                  'the order is placed by Pathology on the same OP visit / admission.</p>'
                  '<p><button type=submit>Place add-on order</button></p></form></div>')
    body += forms + '<p><a href="/his/pathology">Back to the work list</a></p>'
    return common.page(request, f"{o['label']}: {o['accession'] or o['id']}", body, active="Pathology",
                       banner=common.banner(store, p, e), status=status)


@router.get("/pathology/orders/{oid}", response_class=HTMLResponse)
def order_page(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    if not common.is_tissue(o):
        return common.redirect(common.order_url(o))
    return render_order(request, hospital, o)


# -------------------------------------------------------------------- actions
def _values(o, form):
    fields = templates.pathology_fields(o["test"], o["doc_type"])
    if fields is None:
        try:
            values = common.parse_values(form.get("values"))
        except ValueError as e:
            raise FieldError("values", str(e)) from None
        if not values:
            raise FieldError("values", "Enter at least one marker or result.")
        return values
    values, errors = templates.parse_fields(fields, form)
    if errors:
        field, msg = next(iter(errors.items()))
        raise FieldError(field, msg)
    return values


@router.post("/pathology/orders/{oid}/receive")
async def receive_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    form = await common.form(request)
    common.require(request, "path.receive")
    block = common.text(form, "block_no").upper() or None
    if block and not BLOCK_NO.match(block):
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {
            "block_no": "Block No. is the accession plus block letter and number, for example PATH/26/00412-A1."},
            "receive"), status=422)

    def change(s):
        s.collect_sample(o["id"], block_no=block)
        return s.orders[o["id"]]

    try:
        rec, notes = common.run(hospital, request, _dept(hospital.store, o), "collect", change, order_id=o["id"])
    except ValueError as ex:
        return common.redirect(f"/his/pathology/orders/{oid}", str(ex), bad=True)
    spec = hospital.store.specimens[rec["specimen_id"]]
    return common.redirect(f"/his/pathology/orders/{oid}",
                           f"Specimen {spec['barcode']} received" + (f", block No. {spec['block_no']}" if spec.get("block_no") else "") + ".")


@router.post("/pathology/orders/{oid}/report")
async def report_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    o = common.order_or_404(store, oid)
    form = await common.form(request)
    common.require(request, "path.report")
    action = "sign" if common.text(form, "action", "sign") == "sign" else "preliminary"
    try:
        values = _values(o, form)
        dept = _dept(store, o)
        if action == "sign":
            common.require(request, "path.sign")
            prac = common.signer(request, store)
            rec, notes = common.run(hospital, request, dept, "sign", lambda s: s.sign_final(o["id"], prac["id"], values=values),
                                    order_id=o["id"], report_id=(store.report_for_order(o["id"]) or {}).get("id"))
        else:
            me = common.practitioner(request, store)
            if not me:
                raise ValueError("This account is not a practitioner; a preliminary report needs one.")
            rec, notes = common.run(hospital, request, dept, "preliminary",
                                    lambda s: s.report_preliminary(o["id"], me["id"], values), order_id=o["id"])
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "report"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/pathology/orders/{oid}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"{o['accession'] or o['id']}: {rec['status']}", notes)
    return common.redirect(f"/his/pathology/orders/{oid}", msg, warn=warn)


@router.post("/pathology/orders/{oid}/sign")
async def sign_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    """Sign with the values typed (the same form as /report with action=sign)."""
    return await report_post(oid, request, hospital)


@router.post("/pathology/reports/{rid}/addendum")
async def addendum_post(rid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    r = common.report_or_404(store, rid)
    o = store.orders[r["order_id"]]
    form = await common.form(request)
    common.require(request, "path.sign")
    try:
        prac = common.signer(request, store)
        values = _values(o, form)
        note = common.text(form, "note")
        if not note:
            raise FieldError("note", "An addendum needs a note saying what changed.")
        rec, notes = common.run(hospital, request, _dept(store, o), "addendum",
                                lambda s: s.amend(r["id"], prac["id"], values, note), order_id=o["id"], report_id=r["id"])
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "addendum"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/pathology/orders/{o['id']}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"Addendum signed: {o['accession'] or o['id']} v{rec['current_version']}", notes)
    return common.redirect(f"/his/pathology/orders/{o['id']}", msg, warn=warn)


@router.post("/pathology/orders/{oid}/addon")
async def addon_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    o = common.order_or_404(store, oid)
    form = await common.form(request)
    common.require(request, "path.addon")
    test = common.text(form, "test")
    if test not in dict(addon_tests(store)):
        return common.redirect(f"/his/pathology/orders/{oid}", "Choose an IHC or molecular test to add on.", bad=True)
    try:
        new = common.apply(hospital, request, "path.addon",
                           lambda s: s.place_order(o["patient_id"], o["encounter_id"], test, "Pathology"), detail=test)
    except ValueError as ex:
        return common.redirect(f"/his/pathology/orders/{oid}", str(ex), bad=True)
    return common.redirect(f"/his/pathology/orders/{new['id']}", f"Add-on order {new['accession']} {new['label']} placed.")


@router.post("/pathology/orders/{oid}/cancel")
async def cancel_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    form = await common.form(request)
    common.require(request, "path.cancel")
    reason = common.text(form, "reason")
    if not reason:
        return common.redirect(f"/his/pathology/orders/{oid}", "Enter the reason for cancelling.", bad=True)
    try:
        common.run(hospital, request, _dept(hospital.store, o), "cancel", lambda s: s.cancel_order(o["id"], reason), order_id=o["id"])
    except ValueError as ex:
        return common.redirect(f"/his/pathology/orders/{oid}", str(ex), bad=True)
    return common.redirect(f"/his/pathology/orders/{oid}", f"{o['accession'] or o['id']} cancelled.")
