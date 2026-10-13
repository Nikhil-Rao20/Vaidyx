"""The mock RIS / LIS reporting desk (plan item V2-1.5), mounted by app.py at /desk on 127.0.0.1:7130. SYNTHETIC data only.

It stands in for a supporting department's own reporting system (Radiology RIS, the laboratory LIS, Pathology), which a
real hospital already has and Vaidyx-TB never replaces: the department's pending orders and preliminary reports, and the
actions Schedule, Collect sample, Enter preliminary, Complete and sign (the report becomes final with a demo DSC signature),
Addendum and Cancel. Every action goes through the Store transitions of model.py, then, under Hospital.lock:

    render the new report version's PDF (documents.render_versions; on failure the change is kept and saved, "PDF not
    rendered") -> for an imaging order that is now reported and whose study has no images yet, build its synthetic DICOM
    (dicom_studies.build_study) and upload it when Orthanc answers (never fails the action, "images not uploaded") ->
    append the HL7 message of the new event to events.hl7 -> Hospital.save() -> one audit line in desk_audit.jsonl.

Pages (human, through ui.page):  GET /desk, /desk/{dept}, /desk/{dept}/orders/{order id}, /desk/{dept}/reports/{report id};
forms POST to /desk/{dept}/orders/{order id}/schedule | collect | preliminary | sign | cancel and
/desk/{dept}/reports/{report id}/addendum, then redirect 303 to /desk/{dept}?flash=...
JSON (tests, e2e):  GET /desk/api/{dept}/pending; POST /desk/api/{dept}/orders/{order id}/schedule | collect | preliminary |
sign | cancel and /desk/api/{dept}/reports/{report id}/addendum. A LifecycleError is 409 (app.py), bad input 400, an order
or report of another department 404.

No login of its own (localhost only; the demo reaches it through the Vaidyx-TB app's logged-in routes). Never shows or asks
for an Aadhaar number. No em dashes in any UI string.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import documents, hl7, model, ui
from .app import Hospital, get_hospital
from .ids import display_date, display_time, iso_date, parse_time

router = APIRouter()

AUDIT_NAME = "desk_audit.jsonl"
ORTHANC_URL = os.environ.get("TB_HIS_MOCK_ORTHANC") or "http://127.0.0.1:8042"   # tests point it elsewhere
SUPPORTING = "supporting"
DESK_BY = "reporting desk"          # the audit's "by" for actions without a practitioner (schedule, sample, cancel)
RECENT = 10
KEY = re.compile(r"^[a-z][a-z0-9_]*$")


class DeskError(ValueError):
    """Bad input on a desk form or JSON call (400 / a flash message); the store is not touched."""


# ------------------------------------------------------------------------ lookups
def _department(store, code):
    """A supporting department by code, name or id, else 404."""
    d = store.department(code)
    if not d or d.get("group") != SUPPORTING:
        raise HTTPException(404, f"no supporting department {code!r}")
    return d


def _order(store, dept, order_id):
    o = store.orders.get(order_id)
    if not o or o["performing_department"] != dept["name"]:
        raise HTTPException(404, f"no order {order_id!r} in {dept['name']}")
    return o


def _report(store, dept, report_id):
    r = store.reports.get(report_id)
    if not r or store.orders[r["order_id"]]["performing_department"] != dept["name"]:
        raise HTTPException(404, f"no report {report_id!r} in {dept['name']}")
    return r


def staff(store, dept):
    """The department's practitioners (consultants first, then junior residents), by name."""
    people = [store.practitioners[p] for p in dept.get("consultants", []) if p in store.practitioners]
    return sorted(people, key=lambda p: (p["role"] != "consultant", p["name"]))


def is_imaging(order):
    return order["doc_type"] in model.IMAGING_MODALITY


def _version_time(report):
    return model.Store.current_version(report)["reported_on"] if report.get("versions") else ""


def worklist(store, dept):
    """Pending orders (oldest first) and preliminary reports (oldest first) of a department."""
    p = store.pending_for_department(dept["code"])
    return {"orders": sorted(p["orders"], key=lambda o: (o["ordered_on"], o["id"])),
            "reports": sorted(p["reports"], key=lambda r: (_version_time(r), r["id"]))}


def recently_signed(store, dept, n=RECENT):
    """The department's last n final or amended reports, newest first."""
    out = [r for r in store.reports.values() if r["status"] in ("final", "amended")
           and store.orders[r["order_id"]]["performing_department"] == dept["name"]]
    return sorted(out, key=lambda r: (_version_time(r), r["id"]), reverse=True)[:n]


def _patient_brief(store, rec):
    p = store.patients.get(rec["patient_id"]) or {}
    e = store.encounters.get(rec["encounter_id"]) or {}
    return {"name": p.get("name"), "uhid": p.get("uhid")}, e.get("number")


def with_context(store, rec):
    """A copy of an order or report record with the patient's name and UHID and the encounter No. (the identifiers a
    radiologist or pathologist uses to find the patient in their own PACS / LIS)."""
    patient, number = _patient_brief(store, rec)
    out = json.loads(json.dumps(rec))
    out["patient"], out["encounter"] = patient, number
    return out


# ------------------------------------------------------------------------ input
def parse_values(text):
    """Values textarea: one `key: value` per line, split on the first colon; keys snake_case (spaces and hyphens become
    underscores); values exactly as typed (they are the printed values). Blank lines are ignored."""
    values = {}
    for n, line in enumerate(str(text or "").splitlines(), 1):
        if not line.strip():
            continue
        if ":" not in line:
            raise DeskError(f"line {n} has no colon: write one value per line as key: value")
        key, value = line.split(":", 1)
        values[_key(key, n)] = value.strip()
    return values


def _key(key, where):
    k = re.sub(r"[\s\-]+", "_", str(key).strip().lower())
    if not KEY.match(k):
        raise DeskError(f"value name {key!r} (line {where}) must be snake_case letters, digits and underscores")
    return k


def values_text(values):
    return "\n".join(f"{k}: {v}" for k, v in (values or {}).items())


def _json_values(values):
    if values is None:
        return None
    if not isinstance(values, dict):
        raise DeskError("values must be an object of key: printed value")
    out = {}
    for k, v in values.items():
        if not isinstance(v, (str, int, float)) or isinstance(v, bool):
            raise DeskError(f"value {k!r} must be printed text")
        out[_key(k, k)] = str(v).strip()
    return out


def _date(value):
    s = str(value or "").strip()
    if not s:
        raise DeskError("choose a date")
    try:
        parse_time(s)
    except (TypeError, ValueError):
        raise DeskError(f"{s!r} is not a date (YYYY-MM-DD)") from None
    return iso_date(s) if len(s) == 10 else s


def _text(value, what):
    s = str(value or "").strip()
    if not s:
        raise DeskError(f"enter the {what}")
    return s


def _person(store, dept, pid, what):
    p = store.practitioner(str(pid or "").strip())
    if not p:
        raise DeskError(f"choose the {what}")
    if p["department"] != dept["name"]:
        raise DeskError(f"{p['name']} is not on the staff of {dept['name']}")
    return p


# ------------------------------------------------------------------------ actions (shared by the pages and the JSON API)
def _audit(hospital, dept, action, order_id, report_id, by, outcome, detail=None):
    line = {"time": hospital.store.now(), "department": dept["code"], "action": action, "order_id": order_id,
            "report_id": report_id, "by": by, "outcome": outcome}
    if detail:
        line["detail"] = detail
    path = Path(hospital.files["data_dir"]) / AUDIT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _render(hospital, report, notes):
    v = model.Store.current_version(report)
    if v["status"] not in ("preliminary", "final", "amended"):
        return
    try:
        documents.render_versions(hospital.store, hospital.files, [(report, v)])
        notes.append(("ok", f"PDF rendered (version {v['version']})"))
    except Exception as exc:  # the transition already happened: keep it, save it, say so
        first = (str(exc).strip().splitlines() or [type(exc).__name__])[0][:200]
        notes.append(("bad", f"PDF not rendered: {first}"))


def _images(hospital, order, notes):
    """An imaging order that is now reported and whose study has no images yet: build the synthetic DICOM and upload it
    when Orthanc answers. Never fails the action."""
    store = hospital.store
    study = store.imaging_study_for(order["id"])
    if not study or study.get("uploaded") or study.get("status") == "cancelled":
        return
    now = store.now()
    try:
        from . import dicom_studies  # pydicom / numpy, loaded only when an imaging study is built
        if not dicom_studies.performed(store, study):
            return
        if not study.get("series"):
            dicom_studies.build_study(store, study, hospital.files["dicom"], when=now)
    except Exception as exc:
        notes.append(("bad", f"images not built: {str(exc)[:200]}"))
        return
    if not dicom_studies.orthanc_alive(ORTHANC_URL):
        notes.append(("bad", "images built; images not uploaded (PACS not reachable); the next action retries"))
        return
    try:
        counts = dicom_studies.upload_study(store, hospital.files["dicom"], study, orthanc_url=ORTHANC_URL, when=now)
    except Exception as exc:
        notes.append(("bad", f"images built; images not uploaded: {str(exc)[:200]}"))
        return
    if counts.get("failed"):
        notes.append(("bad", f"images not uploaded: {counts['failed']} of {counts['files']} files failed"))
    else:
        notes.append(("ok", f"images uploaded to PACS ({counts['files']} files)"))


def run_action(hospital, dept, action, change, *, order_id=None, report_id=None, by=None):
    """Run one transition under the lock, then render, build images, write HL7, save and audit. `change(store)` returns
    the changed order or report. Returns (record, notes). A refused action (LifecycleError, bad input) changes nothing
    and is audited as refused, then re-raised."""
    with hospital.lock:
        store = hospital.store
        n_events = len(store.events)
        try:
            rec = change(store)
        except Exception as exc:
            if len(hospital.store.events) != n_events:  # never keep a half-done change in memory
                hospital.reload()
            _audit(hospital, dept, action, order_id, report_id, by, "refused", str(exc)[:300])
            raise
        store = hospital.store
        notes = []
        report = rec if "versions" in rec else store.report_for_order(rec["id"])
        order = store.orders[report["order_id"]] if report else rec
        if report and action in ("preliminary", "sign", "addendum"):
            _render(hospital, report, notes)
        if report and is_imaging(order):
            _images(hospital, order, notes)
        for ev in store.events[n_events:]:
            try:
                hl7.append(store, ev, hospital.files["hl7"])
            except Exception as exc:
                notes.append(("bad", f"HL7 message not written: {str(exc)[:200]}"))
        hospital.save()
        _audit(hospital, dept, action, order["id"], report["id"] if report else report_id, by, "done")
    return rec, notes


def do_schedule(hospital, dept, order_id, date, by=None):
    store = hospital.store
    o = _order(store, dept, order_id)
    if not is_imaging(o):
        raise DeskError("only an imaging order is scheduled at the desk; collect the sample for a laboratory test")
    day = _date(date)
    return run_action(hospital, dept, "schedule", lambda s: s.schedule(o["id"], day), order_id=o["id"], by=by or DESK_BY)


def do_collect(hospital, dept, order_id, barcode=None, block_no=None, by=None):
    store = hospital.store
    o = _order(store, dept, order_id)
    if is_imaging(o):
        raise DeskError("an imaging order has no sample; schedule it instead")
    barcode = str(barcode or "").strip().upper() or None
    block_no = str(block_no or "").strip() or None

    def change(s):
        s.collect_sample(o["id"], barcode=barcode, block_no=block_no)
        return s.orders[o["id"]]

    return run_action(hospital, dept, "collect", change, order_id=o["id"], by=by or DESK_BY)


def do_preliminary(hospital, dept, order_id, reporter, values):
    store = hospital.store
    o = _order(store, dept, order_id)
    p = _person(store, dept, reporter, "reporting doctor")
    if not values:
        raise DeskError("enter at least one value")
    return run_action(hospital, dept, "preliminary", lambda s: s.report_preliminary(o["id"], p["id"], values),
                      order_id=o["id"], by=p["reg_no"])


def do_sign(hospital, dept, order_id, signer, values=None):
    """Complete and sign: the report becomes final with the signer's demo DSC. `values` None keeps the preliminary's."""
    store = hospital.store
    o = _order(store, dept, order_id)
    p = _person(store, dept, signer, "signing consultant")
    existing = store.report_for_order(o["id"])
    if not values and not existing:
        raise DeskError("enter at least one value")
    return run_action(hospital, dept, "sign",
                      lambda s: s.sign_final(o["id"], p["id"], values=values or None, apply_signature=True),
                      order_id=o["id"], report_id=existing["id"] if existing else None, by=p["reg_no"])


def do_addendum(hospital, dept, report_id, signer, values, note):
    store = hospital.store
    r = _report(store, dept, report_id)
    p = _person(store, dept, signer, "signing consultant")
    note = _text(note, "amendment note")
    return run_action(hospital, dept, "addendum", lambda s: s.amend(r["id"], p["id"], values or None, note),
                      order_id=r["order_id"], report_id=r["id"], by=p["reg_no"])


def do_cancel(hospital, dept, order_id, reason, by=None):
    store = hospital.store
    o = _order(store, dept, order_id)
    reason = _text(reason, "reason for cancelling")
    return run_action(hospital, dept, "cancel", lambda s: s.cancel_order(o["id"], reason), order_id=o["id"],
                      by=by or DESK_BY)


# ------------------------------------------------------------------------ JSON API
def _api(hospital, fn, *args):
    try:
        rec, notes = fn(hospital, *args)
    except DeskError as exc:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=400)
    with hospital.lock:
        out = with_context(hospital.store, rec)
        if "versions" in rec:
            v = model.Store.current_version(rec)
            out["signature_id"], out["document"] = v.get("signature_id"), v.get("document")
            out["signature"] = hospital.store.signatures.get(v.get("signature_id")) if v.get("signature_id") else None
        else:
            r = hospital.store.report_for_order(rec["id"])
            out["report"] = with_context(hospital.store, r) if r else None
        out["desk_messages"] = [{"kind": k, "text": t} for k, t in notes]
    return out


def _payload(payload):
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise HTTPException(400, "the body is a JSON object")
    return payload


@router.get("/api/{dept}/pending")
def api_pending(dept: str, hospital: Hospital = Depends(get_hospital)):
    with hospital.lock:
        store = hospital.store
        d = _department(store, dept)
        w = worklist(store, d)
        return {"department": {"name": d["name"], "code": d["code"]},
                "orders": [with_context(store, o) for o in w["orders"]],
                "reports": [with_context(store, r) for r in w["reports"]]}


@router.post("/api/{dept}/orders/{order_id}/schedule")
def api_schedule(dept: str, order_id: str, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    return _api(hospital, do_schedule, _department(hospital.store, dept), order_id, b.get("date"), b.get("by"))


@router.post("/api/{dept}/orders/{order_id}/collect")
def api_collect(dept: str, order_id: str, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    return _api(hospital, do_collect, _department(hospital.store, dept), order_id, b.get("barcode"), b.get("block_no"),
                b.get("by"))


@router.post("/api/{dept}/orders/{order_id}/preliminary")
def api_preliminary(dept: str, order_id: str, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    try:
        values = _json_values(b.get("values"))
    except DeskError as exc:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=400)
    return _api(hospital, do_preliminary, _department(hospital.store, dept), order_id,
                b.get("reporter") or b.get("by"), values)


@router.post("/api/{dept}/orders/{order_id}/sign")
def api_sign(dept: str, order_id: str, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    try:
        values = _json_values(b.get("values"))
    except DeskError as exc:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=400)
    return _api(hospital, do_sign, _department(hospital.store, dept), order_id, b.get("signer"), values)


@router.post("/api/{dept}/reports/{report_id}/addendum")
def api_addendum(dept: str, report_id: str, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    try:
        values = _json_values(b.get("values"))
    except DeskError as exc:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=400)
    return _api(hospital, do_addendum, _department(hospital.store, dept), report_id, b.get("signer"), values,
                b.get("note"))


@router.post("/api/{dept}/orders/{order_id}/cancel")
def api_cancel(dept: str, order_id: str, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    return _api(hospital, do_cancel, _department(hospital.store, dept), order_id, b.get("reason"), b.get("by"))


# ------------------------------------------------------------------------ HTML pages
def _base(request):
    return request.scope.get("root_path", "") + "/desk"


def _nav(request):
    root = request.scope.get("root_path", "")
    return [("Reporting desk", root + "/desk"), ("HIS", root + "/his")]


def _page(request, title, body, flash=None):
    return HTMLResponse(ui.page(title, body, nav=_nav(request), active="Reporting desk", flash=flash))


def _a(href, label):
    return f'<a href="{ui.esc(href)}">{ui.esc(label)}</a>'


def _patient_cell(store, rec):
    p = store.patients.get(rec["patient_id"]) or {}
    return (f"<strong>{ui.esc(p.get('name'))}</strong><br><span class=mono>{ui.esc(p.get('uhid'))}</span>"
            f" <span class=muted>{ui.esc(p.get('age'))} Y / {ui.esc(p.get('sex'))}</span>")


def _encounter_cell(store, rec):
    e = store.encounters.get(rec["encounter_id"]) or {}
    return f"<span class=mono>{ui.esc(e.get('number'))}</span>"


def _unit(store, order):
    e = store.encounters.get(order["encounter_id"]) or {}
    return ui.esc(order["ordering_department"] + (f", {e['unit']}" if e.get("unit") else ""))


def _when(value, with_time=False):
    if not value:
        return ""
    return display_time(value) if with_time and len(str(value)) > 10 else display_date(value)


def _who(store, pid):
    p = store.practitioner(pid)
    return p["name"] if p else ""


def _sample_or_slot(store, o):
    if o.get("specimen_id"):
        s = store.specimens.get(o["specimen_id"]) or {}
        out = f"<span class=mono>{ui.esc(s.get('barcode'))}</span>"
        if s.get("block_no"):
            out += f"<br>Block No. <span class=mono>{ui.esc(s['block_no'])}</span>"
        return out
    if o.get("scheduled_for"):
        return f"Scheduled {ui.esc(_when(o['scheduled_for']))}"
    return '<span class=muted>Not yet</span>'


def _order_actions(base, o):
    href = f"{base}/orders/{quote(o['id'])}"
    links = [_a(href + ("#schedule" if is_imaging(o) else "#collect"), "Schedule" if is_imaging(o) else "Collect sample"),
             _a(href + "#preliminary", "Enter preliminary"), _a(href + "#sign", "Complete and sign"),
             _a(href + "#cancel", "Cancel")]
    return " | ".join(links)


def _pdf_link(request, report, v):
    if (v.get("document") or {}).get("path"):
        root = request.scope.get("root_path", "")
        return _a(f"{root}/view/reports/{quote(report['id'])}/{v['version']}", "PDF")
    return '<span class=muted>not rendered</span>'


def _flash(request):
    text = request.query_params.get("flash")
    if not text:
        return None
    return ("bad" if request.query_params.get("kind") == "bad" else "ok", text)


@router.get("", response_class=HTMLResponse)
def desk_home(request: Request, hospital: Hospital = Depends(get_hospital)):
    with hospital.lock:
        store = hospital.store
        rows = []
        for d in sorted((d for d in store.departments.values() if d.get("group") == SUPPORTING), key=lambda d: d["name"]):
            w = store.pending_for_department(d["code"])
            rows.append([_a(f"{_base(request)}/{quote(d['code'])}", d["name"]), f"<span class=mono>{ui.esc(d['code'])}</span>",
                         str(len(w["orders"])), str(len(w["reports"]))])
    body = ('<div class=panel><p class=muted>The reporting systems of the supporting departments (RIS, LIS, Pathology). '
            'Pending orders and preliminary reports per department; Complete and sign makes a report final with the '
            "consultant's digital signature (Vaidyx Demo CA) and sends it to the HIS.</p>"
            + ui.table(["Department", "Code", "Pending orders", "Preliminary reports"], rows) + "</div>")
    return _page(request, "Reporting desk", body, flash=_flash(request))


@router.get("/{dept}", response_class=HTMLResponse)
def desk_department(dept: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    with hospital.lock:
        store = hospital.store
        d = _department(store, dept)
        base = f"{_base(request)}/{quote(d['code'])}"
        w = worklist(store, d)
        orders = [[f"<span class=mono>{ui.esc(o['accession'] or o['id'])}</span>", _patient_cell(store, o),
                   _encounter_cell(store, o), ui.esc(o["label"]), ui.esc(_when(o["ordered_on"])), _unit(store, o),
                   ui.pill(o["status"]), _sample_or_slot(store, o), _order_actions(base, o)] for o in w["orders"]]
        prelim = []
        for r in w["reports"]:
            o, v = store.orders[r["order_id"]], model.Store.current_version(r)
            href = f"{base}/reports/{quote(r['id'])}"
            prelim.append([f"<span class=mono>{ui.esc(o['accession'] or o['id'])}</span>", _patient_cell(store, r),
                           ui.esc(r["title"]), ui.esc(_when(v["reported_on"], True)), ui.esc(_who(store, v["reported_by"])),
                           " | ".join([_a(href + "#sign", "Complete and sign"), _a(href + "#cancel", "Cancel"),
                                       _pdf_link(request, r, v)])])
        recent = []
        for r in recently_signed(store, d):
            o, v = store.orders[r["order_id"]], model.Store.current_version(r)
            sig = store.signatures.get(v.get("signature_id") or "") or {}
            recent.append([f"<span class=mono>{ui.esc(o['accession'] or o['id'])}</span>", _patient_cell(store, r),
                           _a(f"{base}/reports/{quote(r['id'])}", r["title"]), ui.pill(r["status"]),
                           ui.esc(_who(store, sig.get("signer_id")) or "Signature pending"),
                           ui.esc(_when(sig.get("signed_at") or v["reported_on"], True)), _pdf_link(request, r, v)])
    body = (f'<p class=muted>{ui.esc(d["name"])} ({ui.esc(d["code"])}). Find the patient in your own PACS / LIS by '
            "name and UHID or by the accession No.</p>"
            '<div class=panel><h2>Pending orders</h2>'
            + ui.table(["Accession No.", "Patient / UHID", "IP / OP No.", "Test", "Ordered on", "Ordering unit", "Status",
                        "Sample / schedule", "Actions"], orders, "No pending orders.")
            + '</div><div class=panel><h2>Preliminary reports</h2>'
            + ui.table(["Accession No.", "Patient / UHID", "Test", "Reported on", "Reported by", "Actions"], prelim,
                       "No preliminary reports.")
            + '</div><div class=panel><h2>Signed recently</h2>'
            + ui.table(["Accession No.", "Patient / UHID", "Report", "Status", "Signed by", "Signed on", "PDF"], recent,
                       "Nothing signed yet.")
            + "</div>")
    return _page(request, f"Reporting desk: {d['name']}", body, flash=_flash(request))


def _signer_select(store, dept, name="signer"):
    opts = []
    for p in staff(store, dept):
        if p["role"] == "consultant":
            opts.append(f'<option value="{ui.esc(p["reg_no"])}">{ui.esc(p["name"])}, {ui.esc(p["qualification"])}, '
                        f'Reg. No. {ui.esc(p["reg_no"])}</option>')
        else:
            opts.append(f'<option value="{ui.esc(p["reg_no"])}" disabled>{ui.esc(p["name"])}, junior resident '
                        f"(cannot sign)</option>")
    return f'<select name="{ui.esc(name)}" required>{"".join(opts)}</select>'


def _reporter_select(store, dept):
    items = [(p["reg_no"], f"{p['name']}, {p['qualification']}" + (" (junior resident)" if p["role"] != "consultant" else ""))
             for p in staff(store, dept)]
    return f'<select name="reporter" required>{ui.options(items)}</select>'


def _textarea(name, text, rows=6):
    return f'<textarea name="{ui.esc(name)}" rows={rows} placeholder="key: value (one per line)">{ui.esc(text)}</textarea>'


def _form(action, anchor, title, fields, button, cls=""):
    return (f'<div class=panel id="{ui.esc(anchor)}"><h2>{ui.esc(title)}</h2>'
            f'<form method=post action="{ui.esc(action)}">{fields}'
            f'<p><button type=submit{f" class={cls}" if cls else ""}>{ui.esc(button)}</button></p></form></div>')


def _order_panel(store, o):
    p = store.patients.get(o["patient_id"]) or {}
    e = store.encounters.get(o["encounter_id"]) or {}
    consultant = _who(store, e.get("consultant_id"))
    pairs = [("Patient", f"<strong>{ui.esc(p.get('name'))}</strong>"),
             ("UHID", f"<span class=mono>{ui.esc(p.get('uhid'))}</span>"),
             ("Age / Sex", f"{ui.esc(p.get('age'))} Y / {ui.esc(p.get('sex'))}"),
             ("IP / OP No.", f"<span class=mono>{ui.esc(e.get('number'))}</span>"),
             ("Ordering unit", _unit(store, o) + (f", {ui.esc(consultant)}" if consultant else "")),
             ("Test", ui.esc(o["label"])),
             ("Accession No.", f"<span class=mono>{ui.esc(o['accession'] or 'none')}</span>"),
             ("Ordered on", ui.esc(_when(o["ordered_on"], True))),
             ("Status", ui.pill(o["status"])),
             ("Sample / schedule", _sample_or_slot(store, o))]
    if o.get("cancel_reason"):
        pairs.append(("Cancelled", ui.esc(f"{_when(o['cancelled_on'], True)}: {o['cancel_reason']}")))
    return '<div class=panel>' + ui.dl(pairs) + "</div>"


@router.get("/{dept}/orders/{order_id}", response_class=HTMLResponse)
def desk_order(dept: str, order_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    with hospital.lock:
        store = hospital.store
        d = _department(store, dept)
        o = _order(store, d, order_id)
        r = store.report_for_order(o["id"])
        base = f"{_base(request)}/{quote(d['code'])}"
        if r:
            return RedirectResponse(f"{base}/reports/{quote(r['id'])}", status_code=303)
        act = f"{base}/orders/{quote(o['id'])}"
        forms = ""
        if o["status"] in model.OPEN_ORDER:
            if is_imaging(o):
                forms += _form(act + "/schedule", "schedule", "Schedule",
                               f'<label>Date</label><input type=date name=date required '
                               f'value="{ui.esc(o["scheduled_for"] or store.now()[:10])}">', "Schedule", "secondary")
            elif o["status"] in ("ordered", "scheduled"):
                forms += _form(act + "/collect", "collect", "Collect sample",
                               '<label>Sample barcode (optional; allocated when empty, VXS and 8 digits)</label>'
                               '<input type=text name=barcode pattern="VXS[0-9]{8}">'
                               '<label>Block No. (optional, tissue)</label><input type=text name=block_no>',
                               "Collect sample", "secondary")
            forms += _form(act + "/preliminary", "preliminary", "Enter preliminary",
                           "<label>Values (one per line, key: value, printed exactly as typed)</label>"
                           + _textarea("values", "") + "<label>Reported by</label>" + _reporter_select(store, d),
                           "Save preliminary", "secondary")
            forms += _form(act + "/sign", "sign", "Complete and sign",
                           "<label>Values (one per line, key: value, printed exactly as typed)</label>"
                           + _textarea("values", "") + "<label>Signing consultant</label>" + _signer_select(store, d),
                           "Complete and sign")
            forms += _form(act + "/cancel", "cancel", "Cancel order",
                           "<label>Reason</label><input type=text name=reason required>", "Cancel order", "danger")
        else:
            forms = f'<p class=muted>This order is {ui.esc(o["status"])}; no action is open.</p>'
        body = _order_panel(store, o) + forms + f'<p>{_a(base, "Back to the work list")}</p>'
    return _page(request, f"Order {o['accession'] or o['id']}", body, flash=_flash(request))


@router.get("/{dept}/reports/{report_id}", response_class=HTMLResponse)
def desk_report(dept: str, report_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    with hospital.lock:
        store = hospital.store
        d = _department(store, dept)
        r = _report(store, d, report_id)
        o = store.orders[r["order_id"]]
        base = f"{_base(request)}/{quote(d['code'])}"
        v = model.Store.current_version(r)
        rows = []
        for x in r["versions"]:
            sig = store.signatures.get(x.get("signature_id") or "") or {}
            rows.append([str(x["version"]), ui.pill(x["status"]), ui.esc(_when(x["reported_on"], True)),
                         ui.esc(_who(store, x["reported_by"])),
                         ui.esc(sig.get("block") or ("Signature pending" if x["status"] != "preliminary" else "Not signed")),
                         ui.esc(x.get("amendment_note") or ""), _pdf_link(request, r, x)])
        values = ui.table(["Value", "As printed"], [[f"<span class=mono>{ui.esc(k)}</span>", ui.esc(val)]
                                                    for k, val in v["values"].items()], "No values.")
        forms = ""
        if r["status"] == "preliminary":
            forms += _form(f"{base}/orders/{quote(o['id'])}/sign", "sign", "Complete and sign",
                           "<label>Values (prefilled from the preliminary; one per line, key: value)</label>"
                           + _textarea("values", values_text(v["values"])) + "<label>Signing consultant</label>"
                           + _signer_select(store, d), "Complete and sign")
            forms += _form(f"{base}/orders/{quote(o['id'])}/cancel", "cancel", "Cancel order and report",
                           "<label>Reason</label><input type=text name=reason required>", "Cancel", "danger")
        elif r["status"] in ("final", "amended"):
            forms += _form(f"{base}/reports/{quote(r['id'])}/addendum", "addendum", "Addendum",
                           "<label>Values of the amended report (one per line, key: value)</label>"
                           + _textarea("values", values_text(v["values"]))
                           + "<label>Amendment note</label><input type=text name=note required>"
                           + "<label>Signing consultant</label>" + _signer_select(store, d), "Sign addendum")
        body = (_order_panel(store, o) + f'<div class=panel><h2>{ui.esc(r["title"])} {ui.pill(r["status"])}</h2>'
                + values + "<h3>Versions</h3>"
                + ui.table(["Version", "Status", "Reported on", "Reported by", "Signature", "Amendment note", "PDF"], rows)
                + "</div>" + forms + f'<p>{_a(base, "Back to the work list")}</p>')
    return _page(request, f"Report {o['accession'] or r['id']}", body, flash=_flash(request))


# ------------------------------------------------------------------------ HTML form posts
async def _form_fields(request):
    raw = (await request.body()).decode("utf-8", errors="replace")
    return {k: v[-1] for k, v in parse_qs(raw, keep_blank_values=True).items()}


async def _post(request, hospital, dept, fn, *args_from_form):
    """Run a desk action from a form and redirect 303 to the department page with a flash message."""
    f = await _form_fields(request)
    d = _department(hospital.store, dept)
    target = f"{_base(request)}/{quote(d['code'])}"

    def go():
        args = [a(f) if callable(a) else a for a in args_from_form]
        return fn(hospital, d, *args)

    try:
        rec, notes = await run_in_threadpool(go)
    except (model.LifecycleError, ValueError) as exc:  # DeskError is a ValueError
        return RedirectResponse(f"{target}?kind=bad&flash={quote(str(exc))}", status_code=303)
    ident = rec.get("accession") or (hospital.store.orders.get(rec.get("order_id")) or {}).get("accession") or rec["id"]
    status = rec.get("status")
    msg = f"{ident}: {status}." + "".join(f" {t}." for _, t in notes)
    kind = "bad" if any(k == "bad" for k, _ in notes) else "ok"
    return RedirectResponse(f"{target}?kind={kind}&flash={quote(msg)}", status_code=303)


def _vals(name="values", empty_none=False):
    def get(f):
        v = parse_values(f.get(name, ""))
        return (v or None) if empty_none else v
    return get


@router.post("/{dept}/orders/{order_id}/schedule")
async def post_schedule(dept: str, order_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    return await _post(request, hospital, dept, do_schedule, order_id, lambda f: f.get("date"))


@router.post("/{dept}/orders/{order_id}/collect")
async def post_collect(dept: str, order_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    return await _post(request, hospital, dept, do_collect, order_id, lambda f: f.get("barcode"),
                       lambda f: f.get("block_no"))


@router.post("/{dept}/orders/{order_id}/preliminary")
async def post_preliminary(dept: str, order_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    return await _post(request, hospital, dept, do_preliminary, order_id, lambda f: f.get("reporter"), _vals())


@router.post("/{dept}/orders/{order_id}/sign")
async def post_sign(dept: str, order_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    return await _post(request, hospital, dept, do_sign, order_id, lambda f: f.get("signer"), _vals(empty_none=True))


@router.post("/{dept}/reports/{report_id}/addendum")
async def post_addendum(dept: str, report_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    return await _post(request, hospital, dept, do_addendum, report_id, lambda f: f.get("signer"),
                       _vals(empty_none=True), lambda f: f.get("note"))


@router.post("/{dept}/orders/{order_id}/cancel")
async def post_cancel(dept: str, order_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    return await _post(request, hospital, dept, do_cancel, order_id, lambda f: f.get("reason"))
