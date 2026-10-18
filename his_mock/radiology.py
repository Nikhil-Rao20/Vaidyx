"""The Radiology module (RIS) of the demo HIMS, mounted at /his by app.py. SYNTHETIC data only.

    GET  /his/radiology?tab=ordered|scheduled|reported|signed   the work list of the imaging orders (Radiology and
                                                                Nuclear Medicine)
    GET  /his/radiology/orders/{order id}                       one order: schedule (date, time, modality room; creates
                                                                the ImagingStudy and its Study UID), "Open images" in
                                                                the PACS viewer, report entry (technique, comparison,
                                                                findings, impression), preliminary save, sign
                                                                (radiologist), addendum, cancel, the signed PDF
    POST /his/radiology/orders/{order id}/schedule | /report | /sign | /cancel, /his/radiology/reports/{report id}/addendum

The technician schedules and may save a preliminary report; only the radiologist signs. Signing an imaging report builds
the synthetic DICOM study and uploads it to the PACS when Orthanc answers (the reporting engine of desk.py), after which
"Open images" opens OHIF through this HIMS (/api/tb/pacs/..., see pacs_proxy.py). No em dashes.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from . import common, documents, model, templates, ui
from .app import Hospital, get_hospital
from .common import FieldError, FormState, dt

router = APIRouter()

TABS = [("ordered", "Ordered"), ("scheduled", "Scheduled"), ("reported", "Reported (preliminary)"), ("signed", "Signed")]
ROOMS = {"ct": ("CT room 1", "CT room 2"), "mri": ("MRI 1",), "xray": ("X-ray room 1", "X-ray room 2"),
         "ultrasound": ("USG room 1", "USG room 2"), "mammogram": ("Mammography unit",), "pet_ct": ("PET-CT suite",),
         "bone_scan": ("Gamma camera 1",)}
RECENT_SIGNED = 25


# -------------------------------------------------------------------- the work list
def imaging_orders(store):
    return [o for o in store.orders.values() if common.is_imaging(o)]


def bucket(store, o):
    if o["status"] == "cancelled":
        return "cancelled"
    r = store.report_for_order(o["id"])
    if r:
        v = store.current_version(r)
        if r["status"] == "cancelled":
            return "cancelled"
        if r["status"] == "preliminary" or (r["status"] == "final" and not v.get("signature_id")):
            return "reported"
        return "signed"
    return "scheduled" if o["status"] == "scheduled" else "ordered"


def worklist(store, tab):
    rows = [o for o in imaging_orders(store) if bucket(store, o) == tab]
    if tab == "signed":
        rows.sort(key=lambda o: (store.current_version(store.report_for_order(o["id"]))["reported_on"], o["id"]), reverse=True)
        return rows[:RECENT_SIGNED]
    if tab == "scheduled":
        return sorted(rows, key=lambda o: (o.get("scheduled_for") or "", o["id"]))
    return sorted(rows, key=lambda o: (o["ordered_on"], o["id"]))


def counts(store):
    out = {k: 0 for k, _ in TABS}
    for o in imaging_orders(store):
        b = bucket(store, o)
        if b in out:
            out[b] += 1
    return out


def study_cell(store, o):
    s = store.imaging_study_for(o["id"])
    if not s:
        return '<span class=muted>not scheduled</span>'
    out = f'{ui.esc(s["modality"])} {ui.pill(s["status"])}'
    if o.get("scheduled_for"):
        out += f'<br><span class=small>{ui.esc(dt(o["scheduled_for"]))}{", " + ui.esc(o["room"]) if o.get("room") else ""}</span>'
    if s.get("series") or s.get("uploaded"):
        out += f'<br><a href="{common.viewer_url(s["study_uid"])}" target=_blank>Open images</a>'
    return out


@router.get("/radiology", response_class=HTMLResponse)
def radiology_home(request: Request, tab: str = "ordered", hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    tab = tab if tab in dict(TABS) else "ordered"
    n = counts(store)
    rows = []
    for o in worklist(store, tab):
        r = store.report_for_order(o["id"])
        rows.append([f'<a href="/his/radiology/orders/{ui.esc(o["id"])}" class=mono>{ui.esc(o["accession"] or o["id"])}</a>',
                     common.patient_cell(store, o), common.encounter_cell(store, o), ui.esc(o["label"]),
                     ui.esc(o["performing_department"]), ui.esc(dt(o["ordered_on"])), common.unit_cell(store, o),
                     study_cell(store, o), (ui.pill(r["status"]) if r else '<span class=muted>none</span>'),
                     common.documents_cell(r)])
    body = (ui.tabs([(k, l, n[k]) for k, l in TABS], tab, "/his/radiology") + '<div class=panel id=worklist>'
            + ui.table(["Accession No.", "Patient / UHID", "IP / OP No.", "Study", "Department", "Ordered on",
                        "Ordering unit", "Study / images", "Report", "PDF"], rows, f"No order under '{dict(TABS)[tab]}'.")
            + '</div><p class=small>Images: synthetic DICOM test patterns built when a report is entered and uploaded to '
            'the demo PACS (Orthanc + OHIF); public-dataset images, when loaded, are credited on the PACS about page.</p>')
    return common.page(request, "Radiology (RIS)", body, active="Radiology")


# -------------------------------------------------------------------- one order
def _dept(store, o):
    return store.department(o["performing_department"])


def _fields_form(request, state, presets, doc_type):
    st = state or common.EMPTY
    out = []
    for f in templates.RADIOLOGY:
        name = "v_" + f["key"]
        default = presets.get(f["key"], documents.TECHNIQUE.get(doc_type, "") if f["key"] == "technique" else "")
        ctl = ui.textarea(name, st.v(name, default), rows=f["rows"] or 3, required=f["required"], placeholder=f["example"])
        out.append(ui.field(name, f["label"] + (" *" if f["required"] else ""), ctl, st.err(name)))
    return "".join(out)


def _study_panel(store, o):
    s = store.imaging_study_for(o["id"])
    if not s:
        return ""
    pairs = [("Modality", ui.esc(s["modality"])), ("Study UID", f'<span class=mono>{ui.esc(s["study_uid"])}</span>'),
             ("Accession No.", f'<span class=mono>{ui.esc(s.get("accession") or "none")}</span>'),
             ("Study date", ui.esc(dt(s.get("started")))), ("PACS status", ui.pill(s["status"])),
             ("Series / images", f'{s.get("number_of_series") or 0} / {s.get("number_of_instances") or 0}')]
    if s.get("series") or s.get("uploaded"):
        pairs.append(("Images", f'<a href="{common.viewer_url(s["study_uid"])}" target=_blank>Open images in the PACS viewer</a>'))
    else:
        pairs.append(("Images", '<span class=muted>none yet: the study images arrive when the report is entered</span>'))
    return f'<div class=panel id=study><h2>Imaging study</h2>{ui.dl(pairs)}</div>'


def render_order(request, hospital, o, state=None, status=200):
    store = hospital.store
    p = store.patients[o["patient_id"]]
    e = store.encounters.get(o["encounter_id"])
    r = store.report_for_order(o["id"])
    csrf = common.csrf_field(request)
    base = f"/his/radiology/orders/{ui.esc(o['id'])}"
    body = common.order_panel(store, o) + _study_panel(store, o)
    if r:
        v = store.current_version(r)
        body += (f'<div class=panel id=current><h2>{ui.esc(r["title"])} {ui.pill(r["status"])}</h2>'
                 + common.values_table(v["values"]) + '<h3>Versions</h3>' + common.versions_table(store, r) + '</div>')
    b = bucket(store, o)
    forms = ""
    if b in ("ordered", "scheduled"):
        if common.can(request, "rad.schedule"):
            st = state if state is not None and state.form == "schedule" else None
            rooms = ROOMS.get(o["doc_type"], ("Room 1",))
            when = o.get("scheduled_for") or ""
            forms += (f'<div class=panel id=schedule><h2>{"Reschedule" if b == "scheduled" else "Schedule"}</h2>'
                      f'<form method=post action="{base}/schedule">{csrf}'
                      + ui.field("date", "Date *", ui.text_input("date", (st or common.EMPTY).v("date", when[:10] or common.today(store)),
                                                                   kind="date", short=True, required=True), (st or common.EMPTY).err("date"))
                      + ui.field("time", "Time", ui.text_input("time", (st or common.EMPTY).v("time", when[11:16] if len(when) > 10 else "09:00"),
                                                               kind="time", short=True), (st or common.EMPTY).err("time"))
                      + ui.field("room", "Modality room", ui.select("room", [(x, x) for x in rooms], (st or common.EMPTY).v("room", o.get("room")), short=True))
                      + '<p class=small>Scheduling registers the ImagingStudy with its Study UID and the accession No. in the PACS work list.</p>'
                      '<p><button type=submit class=primary>Schedule</button></p></form></div>')
        else:
            forms += '<div class=panel id=schedule><h2>Schedule</h2>' + common.refused_line(request, "rad.schedule") + '</div>'
    if b in ("ordered", "scheduled", "reported"):
        presets = dict(store.current_version(r)["values"]) if r else {}
        if common.can(request, "rad.report") and not r:
            st = state if state is not None and state.form == "report" else None
            forms += (f'<div class=panel id=report><h2>Report entry</h2><form method=post action="{base}/report">{csrf}'
                      + _fields_form(request, st, presets, o["doc_type"])
                      + '<p class=small>Saved as preliminary (verification awaited) until the radiologist signs.</p>'
                      '<p><button type=submit>Save preliminary</button></p></form></div>')
        elif not r:
            forms += '<div class=panel id=report><h2>Report entry</h2>' + common.refused_line(request, "rad.report") + '</div>'
        if common.can(request, "rad.sign"):
            st = state if state is not None and state.form == "sign" else None
            me = common.practitioner(request, store)
            forms += (f'<div class=panel id=sign><h2>Sign the report</h2><form method=post action="{base}/sign">{csrf}'
                      + _fields_form(request, st, presets, o["doc_type"])
                      + f'<p class=muted>Signed by {ui.esc(me["name"] if me else "")}, Reg. No. {ui.esc(me["reg_no"] if me else "")} '
                      '(Vaidyx Demo CA); the report becomes final, the PDF is rendered and the images go to the PACS.</p>'
                      '<p><button type=submit class=primary>Sign final</button></p></form></div>')
        else:
            forms += '<div class=panel id=sign><h2>Sign the report</h2>' + common.refused_line(request, "rad.sign") + '</div>'
        if common.can(request, "rad.cancel"):
            forms += (f'<div class=panel id=cancel><h2>Cancel</h2><form method=post action="{base}/cancel">{csrf}'
                      + ui.field("reason", "Reason", ui.text_input("reason", required=True))
                      + '<p><button type=submit class=danger>Cancel order</button></p></form></div>')
    elif b == "signed":
        if common.can(request, "rad.sign"):
            st = state if state is not None and state.form == "addendum" else None
            forms += (f'<div class=panel id=addendum><h2>Addendum</h2><form method=post action="/his/radiology/reports/{ui.esc(r["id"])}/addendum">{csrf}'
                      + _fields_form(request, st, dict(store.current_version(r)["values"]), o["doc_type"])
                      + ui.field("note", "Amendment note *", ui.text_input("note", (st or common.EMPTY).v("note"), required=True),
                                 (st or common.EMPTY).err("note"))
                      + '<p><button type=submit class=primary>Sign addendum</button></p></form></div>')
        else:
            forms += '<div class=panel id=addendum><h2>Addendum</h2>' + common.refused_line(request, "rad.sign") + '</div>'
    else:
        forms += f'<p class=muted>This order is {ui.esc(o["status"])}; no action is open.</p>'
    body += forms + '<p><a href="/his/radiology">Back to the work list</a></p>'
    return common.page(request, f"{o['label']}: {o['accession'] or o['id']}", body, active="Radiology",
                       banner=common.banner(store, p, e), status=status)


@router.get("/radiology/orders/{oid}", response_class=HTMLResponse)
def order_page(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    if not common.is_imaging(o):
        return common.redirect(common.order_url(o))
    return render_order(request, hospital, o)


# -------------------------------------------------------------------- actions
def _report_values(form):
    values, errors = templates.parse_fields(templates.RADIOLOGY, form)
    if errors:
        field, msg = next(iter(errors.items()))
        raise FieldError(field, msg)
    return values


def _study_done(store, o):
    """A study booked for a later day is not done yet, so it has no report (the dates on the PDF and in the PACS stay in
    order). ValueError with the cause and the one action."""
    when = o.get("scheduled_for") or ""
    if o["status"] == "scheduled" and when[:10] > common.today(store):
        raise ValueError(f"This study is booked for {dt(when)}; a report is entered once the study is done. "
                         "Reschedule it to today to report now.")


@router.post("/radiology/orders/{oid}/schedule")
async def schedule_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    form = await common.form(request)
    common.require(request, "rad.schedule")
    day, time_, room = common.text(form, "date"), common.text(form, "time"), common.text(form, "room")
    try:
        if not day:
            raise FieldError("date", "Choose a date.")
        when = f"{day}T{time_}" if time_ else day
        try:
            model.parse_time(when)
        except (TypeError, ValueError):
            raise FieldError("date", "The date or time is not valid (YYYY-MM-DD and HH:MM).") from None

        def change(s):
            s.schedule(o["id"], when)
            if room:
                s.orders[o["id"]]["room"] = room
            return s.orders[o["id"]]

        rec, notes = common.run(hospital, request, _dept(hospital.store, o), "schedule", change, order_id=o["id"])
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "schedule"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/radiology/orders/{oid}", str(ex), bad=True)
    s = hospital.store.imaging_study_for(o["id"]) or {}
    return common.redirect(f"/his/radiology/orders/{oid}",
                           f"{o['accession'] or o['id']} scheduled for {dt(rec['scheduled_for'])}" + (f", {room}" if room else "")
                           + (f"; Study UID {s['study_uid']}." if s else "."))


@router.post("/radiology/orders/{oid}/report")
async def report_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    o = common.order_or_404(store, oid)
    form = await common.form(request)
    common.require(request, "rad.report")
    try:
        values = _report_values(form)
        _study_done(store, o)
        me = common.practitioner(request, store)
        dept = _dept(store, o)
        reporter = me["id"] if me else _first_staff(store, dept)
        rec, notes = common.run(hospital, request, dept, "preliminary",
                                lambda s: s.report_preliminary(o["id"], reporter, values), order_id=o["id"])
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "report"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/radiology/orders/{oid}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"Preliminary report saved for {o['accession'] or o['id']}", notes)
    return common.redirect(f"/his/radiology/orders/{oid}", msg, warn=warn)


def _first_staff(store, dept):
    people = [store.practitioners[x] for x in dept.get("consultants", []) if x in store.practitioners]
    if not people:
        raise model.LifecycleError(f"{dept['name']} has no practitioner to report under")
    return sorted(people, key=lambda x: (x["role"] != "consultant", x["reg_no"]))[0]["id"]


@router.post("/radiology/orders/{oid}/sign")
async def sign_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    o = common.order_or_404(store, oid)
    form = await common.form(request)
    common.require(request, "rad.sign")
    try:
        prac = common.signer(request, store)
        values = _report_values(form)
        _study_done(store, o)
        rec, notes = common.run(hospital, request, _dept(store, o), "sign",
                                lambda s: s.sign_final(o["id"], prac["id"], values=values), order_id=o["id"],
                                report_id=(store.report_for_order(o["id"]) or {}).get("id"))
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "sign"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/radiology/orders/{oid}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"{o['accession'] or o['id']} signed", notes)
    return common.redirect(f"/his/radiology/orders/{oid}", msg, warn=warn)


@router.post("/radiology/reports/{rid}/addendum")
async def addendum_post(rid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    r = common.report_or_404(store, rid)
    o = store.orders[r["order_id"]]
    form = await common.form(request)
    common.require(request, "rad.sign")
    try:
        prac = common.signer(request, store)
        values = _report_values(form)
        note = common.text(form, "note")
        if not note:
            raise FieldError("note", "An addendum needs a note saying what changed.")
        rec, notes = common.run(hospital, request, _dept(store, o), "addendum",
                                lambda s: s.amend(r["id"], prac["id"], values, note), order_id=o["id"], report_id=r["id"])
    except FieldError as ex:
        return render_order(request, hospital, o, state=FormState(common.values_of(form), {ex.field: ex.message}, "addendum"), status=422)
    except ValueError as ex:
        return common.redirect(f"/his/radiology/orders/{o['id']}", str(ex), bad=True)
    msg, warn = common.notes_flash(f"Addendum signed: {o['accession'] or o['id']} v{rec['current_version']}", notes)
    return common.redirect(f"/his/radiology/orders/{o['id']}", msg, warn=warn)


@router.post("/radiology/orders/{oid}/cancel")
async def cancel_post(oid: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    o = common.order_or_404(hospital.store, oid)
    form = await common.form(request)
    common.require(request, "rad.cancel")
    reason = common.text(form, "reason")
    if not reason:
        return common.redirect(f"/his/radiology/orders/{oid}", "Enter the reason for cancelling.", bad=True)
    try:
        common.run(hospital, request, _dept(hospital.store, o), "cancel", lambda s: s.cancel_order(o["id"], reason), order_id=o["id"])
    except ValueError as ex:
        return common.redirect(f"/his/radiology/orders/{oid}", str(ex), bad=True)
    return common.redirect(f"/his/radiology/orders/{oid}", f"{o['accession'] or o['id']} cancelled.")
