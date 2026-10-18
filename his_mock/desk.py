"""The mock RIS / LIS reporting desk (plan item V2-1.5), mounted by app.py at /desk on 127.0.0.1:7130. SYNTHETIC data only.

It stands in for a supporting department's own reporting system (Radiology RIS, the laboratory LIS, Pathology), which a
real hospital already has and Vaidyx-TB never replaces: the department's pending orders and preliminary reports, and the
actions Schedule, Collect sample, Enter preliminary, Complete and sign (the report becomes final with a demo DSC signature),
Addendum and Cancel. Every action goes through the Store transitions of model.py, then, under Hospital.lock:

    render the new report version's PDF (documents.render_versions; on failure the change is kept and saved, "PDF not
    rendered") -> for an imaging order that is now reported and whose study has no images yet, build its synthetic DICOM
    (dicom_studies.build_study) and upload it when Orthanc answers (never fails the action, "images not uploaded") ->
    append the HL7 message of the new event to events.hl7 -> Hospital.save() -> one audit line in desk_audit.jsonl.

Pages (human): GET /desk lists the supporting departments with their counts and links into the HIMS modules; /desk/{dept},
/desk/{dept}/orders/{order id} and /desk/{dept}/reports/{report id} redirect to the module page (Laboratory, Radiology,
Pathology, OPD) of that department, order or report, so the old links keep working. The forms live in the modules.
JSON (tests, e2e):  GET /desk/api/{dept}/pending; POST /desk/api/{dept}/orders/{order id}/schedule | collect | preliminary |
sign | cancel and /desk/api/{dept}/reports/{report id}/addendum. A LifecycleError is 409 (app.py), bad input 400, an order
or report of another department 404. The JSON API carries no login (localhost only, same-origin writes; the demo script
and the tests call it); the pages need the HIMS session like every human screen. `run_action` is the reporting engine
every module action runs through. Never shows or asks for an Aadhaar number. No em dashes in any UI string.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import documents, hl7, model, ui
from .app import Hospital, get_hospital
from .ids import iso_date, parse_time

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
        if is_imaging(order) and (report or action == "exam_done"):  # the technician's exam done sends the images first (18 Oct)
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


def _session(request):
    """The staff session behind a JSON call (None for a write-token caller and for the open test app)."""
    return getattr(request.state, "session", None)


def _session_person(request, hospital, dept, what):
    """For a staff session the person is the account's own practitioner, never one named in the body (security review #3): a
    consultant of the department (signing), or for a technician entering results the department's first practitioner (as the
    screens record it). Raises Forbidden when the account has no practitioner of that department."""
    from . import auth

    s = _session(request) or {}
    p = hospital.store.practitioner(s.get("practitioner_id")) if s.get("practitioner_id") else None
    if what == "signing consultant":
        if not p or p.get("role") != "consultant":
            raise auth.Forbidden(f"{auth.REFUSED}: this account is not a consultant and cannot sign.")
        if p["department"] != dept["name"]:
            raise auth.Forbidden(f"{auth.REFUSED}: {p['name']} signs for {p['department']}, not for {dept['name']}.")
        return p["id"]
    if p and p["department"] == dept["name"]:
        return p["id"]
    people = staff(hospital.store, dept)
    if not people:
        raise DeskError(f"{dept['name']} has no practitioner to report under")
    return people[0]["id"]


def _by(request, hospital, given):
    """Who did it for the desk audit: the session's Reg. No. or email; a token caller's own words."""
    s = _session(request)
    if not s:
        return given
    p = hospital.store.practitioner(s.get("practitioner_id")) if s.get("practitioner_id") else None
    return p["reg_no"] if p else s.get("email")


@router.post("/api/{dept}/orders/{order_id}/schedule")
def api_schedule(dept: str, order_id: str, request: Request, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    return _api(hospital, do_schedule, _department(hospital.store, dept), order_id, b.get("date"), _by(request, hospital, b.get("by")))


@router.post("/api/{dept}/orders/{order_id}/collect")
def api_collect(dept: str, order_id: str, request: Request, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    return _api(hospital, do_collect, _department(hospital.store, dept), order_id, b.get("barcode"), b.get("block_no"),
                _by(request, hospital, b.get("by")))


@router.post("/api/{dept}/orders/{order_id}/preliminary")
def api_preliminary(dept: str, order_id: str, request: Request, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    try:
        values = _json_values(b.get("values"))
    except DeskError as exc:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=400)
    d = _department(hospital.store, dept)
    try:
        reporter = _session_person(request, hospital, d, "reporting doctor") if _session(request) else (b.get("reporter") or b.get("by"))
    except DeskError as exc:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=400)
    return _api(hospital, do_preliminary, d, order_id, reporter, values)


@router.post("/api/{dept}/orders/{order_id}/sign")
def api_sign(dept: str, order_id: str, request: Request, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    """The signer is the signed-in consultant for a staff session; a write-token caller names it (a consultant of that department)."""
    b = _payload(payload)
    try:
        values = _json_values(b.get("values"))
    except DeskError as exc:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=400)
    d = _department(hospital.store, dept)
    signer = _session_person(request, hospital, d, "signing consultant") if _session(request) else b.get("signer")
    return _api(hospital, do_sign, d, order_id, signer, values)


@router.post("/api/{dept}/reports/{report_id}/addendum")
def api_addendum(dept: str, report_id: str, request: Request, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    try:
        values = _json_values(b.get("values"))
    except DeskError as exc:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=400)
    d = _department(hospital.store, dept)
    signer = _session_person(request, hospital, d, "signing consultant") if _session(request) else b.get("signer")
    return _api(hospital, do_addendum, d, report_id, signer, values, b.get("note"))


@router.post("/api/{dept}/orders/{order_id}/cancel")
def api_cancel(dept: str, order_id: str, request: Request, payload: dict = Body(None), hospital: Hospital = Depends(get_hospital)):
    b = _payload(payload)
    return _api(hospital, do_cancel, _department(hospital.store, dept), order_id, b.get("reason"), _by(request, hospital, b.get("by")))


# ------------------------------------------------------------------------ HTML: a thin alias of the modules
# The reporting desk's own pages moved into the Laboratory, Radiology, Pathology and OPD modules of the HIMS. The old
# links keep working: /desk lists the departments with their counts and links into the modules, /desk/{dept} and the
# order / report pages redirect to the module page of that department, order or report.
MODULE_OF_DEPARTMENT = {"RAD": "/his/radiology", "NM": "/his/radiology", "PATH": "/his/pathology"}


def _module_for(store, d):
    if d["code"] in MODULE_OF_DEPARTMENT:
        return MODULE_OF_DEPARTMENT[d["code"]]
    if any(t["doc_type"] == "lab" and t["department"] == d["name"] for t in store.tests.values()):
        return f"/his/lab?dept={quote(d['code'])}"
    return "/his/opd"


@router.get("", response_class=HTMLResponse)
def desk_home(request: Request, hospital: Hospital = Depends(get_hospital)):
    from . import common

    with hospital.lock:
        store = hospital.store
        rows = []
        for d in sorted((d for d in store.departments.values() if d.get("group") == SUPPORTING), key=lambda d: d["name"]):
            w = store.pending_for_department(d["code"])
            rows.append([f'<a href="{ui.esc(_module_for(store, d))}">{ui.esc(d["name"])}</a>',
                         f"<span class=mono>{ui.esc(d['code'])}</span>", str(len(w["orders"])), str(len(w["reports"]))])
    body = ('<div class=panel><p class=muted>The reporting desk of the supporting departments now lives in the modules: '
            '<a href="/his/lab">Laboratory</a>, <a href="/his/radiology">Radiology</a>, <a href="/his/pathology">Pathology</a>; '
            'clinical notes of the consulting departments under <a href="/his/opd">OPD</a>.</p>'
            + ui.table(["Department", "Code", "Pending orders", "Preliminary reports"], rows, "No supporting department.")
            + "</div>")
    return common.page(request, "Reporting desk", body, active=None)


@router.get("/{dept}", response_class=HTMLResponse)
def desk_department(dept: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    d = _department(hospital.store, dept)
    return RedirectResponse(_module_for(hospital.store, d), status_code=303)


@router.get("/{dept}/orders/{order_id}", response_class=HTMLResponse)
def desk_order(dept: str, order_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    from . import common

    d = _department(hospital.store, dept)
    o = _order(hospital.store, d, order_id)
    return RedirectResponse(common.order_url(o), status_code=303)


@router.get("/{dept}/reports/{report_id}", response_class=HTMLResponse)
def desk_report(dept: str, report_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    from . import common

    d = _department(hospital.store, dept)
    r = _report(hospital.store, d, report_id)
    return RedirectResponse(common.report_url(hospital.store, r), status_code=303)
