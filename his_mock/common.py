"""Helpers shared by the human screens of the demo HIMS (registration, OPD, IPD, laboratory, radiology, pathology,
exchange, admin): the page wrapper with the signed-in user, CSRF-checked forms, role checks, flash redirects, the patient
banner, the order / report tables and the change runners (ADT / order changes through `apply`, report-producing actions
through the reporting engine of desk.py). SYNTHETIC data only; no em dashes in any UI string.
"""
import re
import secrets
from urllib.parse import quote, urlencode

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from . import auth, hl7, ids, model, ui

TODAY_FALLBACK = "2026-10-13"


class FieldError(ValueError):
    """A validation error of one form field; the page is shown again with the message next to the field."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field
        self.message = message


class FormState:
    """What a re-rendered form needs: the values typed and the errors per field."""

    def __init__(self, values=None, errors=None, form=None):
        self.values = dict(values or {})
        self.errors = dict(errors or {})
        self.form = form

    def v(self, name, default=""):
        return self.values.get(name, default)

    def err(self, name):
        return self.errors.get(name)


EMPTY = FormState()


# -------------------------------------------------------------------- the signed-in user
def user(request):
    return getattr(request.state, "session", None) if request is not None else None


def roles(request):
    return (user(request) or {}).get("roles") or []


def can(request, permission):
    return auth.allowed(roles(request), permission)


def require(request, permission):
    auth.require(user(request), permission)


def practitioner(request, store):
    """The store practitioner the signed-in account signs as (None for a technician, the desk or the admin)."""
    s = user(request) or {}
    return store.practitioner(s.get("practitioner_id")) if s.get("practitioner_id") else None


def signer(request, store):
    """The signing consultant of the account, else Forbidden with a plain message."""
    p = practitioner(request, store)
    if not p:
        raise auth.Forbidden(f"{auth.REFUSED}: this account is not a consultant and cannot sign.")
    if p["role"] != "consultant":
        raise auth.Forbidden(f"{auth.REFUSED}: {p['name']} is a junior resident and cannot sign.")
    return p


def not_own_department(request, store, department):
    """None when the signed-in consultant belongs to `department` (who writes and signs that unit's notes and reports),
    else the plain reason: a Breast Surgery consultant does not sign an ENT discharge summary or a Pulmonology
    bronchoscopy report."""
    me = practitioner(request, store)
    if me and me["department"] == department:
        return None
    who = f"this account signs for {me['department']}" if me else "this account is not a consultant"
    return f"Only a consultant of {department} writes and signs this; {who}."


def require_own_department(request, store, department):
    reason = not_own_department(request, store, department)
    if reason:
        raise auth.Forbidden(f"{auth.REFUSED}: {reason}")


def by_label(request, store):
    """Who did it, for the desk audit: Reg. No. of the account's practitioner, else the account email."""
    p = practitioner(request, store)
    return p["reg_no"] if p else (user(request) or {}).get("email") or "api"


# -------------------------------------------------------------------- forms
async def form(request):
    """The posted form fields (a FormData: .get and .getlist) after the CSRF check against the session's token."""
    data = await request.form()
    s = user(request)
    if s:
        token = str(data.get("csrf") or "")
        if not token or not secrets.compare_digest(token, str(s.get("csrf") or "")):
            raise auth.Forbidden("The form token is missing or stale: open the page again and resubmit.")
    return data


def csrf_field(request):
    s = user(request) or {}
    return ui.hidden("csrf", s.get("csrf") or "")


def text(f, key, default=""):
    v = f.get(key) if f is not None else None
    return default if v is None else " ".join(str(v).split())


def multiline(f, key):
    v = f.get(key) if f is not None else None
    if v is None:
        return ""
    lines = [" ".join(line.split()) for line in str(v).replace("\r", "").split("\n")]
    return "\n".join(x for x in lines if x).strip()


def values_of(f):
    """A plain dict of the posted fields (for re-rendering a form)."""
    try:
        return {k: str(f.get(k)) for k in f.keys()}
    except AttributeError:
        return dict(f or {})


# -------------------------------------------------------------------- pages, flashes, redirects
def flash_of(request):
    msg = request.query_params.get("flash") if request is not None else None
    if not msg:
        return None
    level = request.query_params.get("level") or request.query_params.get("kind") or "ok"
    return (level if level in ("ok", "bad", "warn") else "ok", msg)


def page(request, title, body, *, active=None, flash=None, banner=None, status=200):
    return HTMLResponse(ui.page(title, body, active=active, user=user(request), banner=banner,
                                flash=flash or flash_of(request)), status_code=status)


def redirect(url, msg=None, bad=False, warn=False):
    if msg is None:
        return RedirectResponse(url, status_code=303)
    q = {"flash": msg}
    if bad:
        q["level"] = "bad"
    elif warn:
        q["level"] = "warn"
    sep = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{sep}{urlencode(q)}", status_code=303)


def not_found(what):
    raise HTTPException(404, f"No such {what}.")


# -------------------------------------------------------------------- lookups
def patient_or_404(store, pid):
    p = store.patients.get(pid)
    if not p:
        raise HTTPException(404, "No such registration.")
    return p


def encounter_or_404(store, eid):
    e = store.encounters.get(eid)
    if not e:
        raise HTTPException(404, "No such OP visit or admission.")
    return e


def order_or_404(store, oid):
    o = store.orders.get(oid)
    if not o:
        raise HTTPException(404, "No such order.")
    return o


def report_or_404(store, rid):
    r = store.reports.get(rid)
    if not r:
        raise HTTPException(404, "No such report.")
    return r


def module_order_or_404(store, oid, module):
    """An order this module works (lab, radiology, pathology, opd), else 404: a laboratory form never acts on an imaging order
    (security review #12)."""
    o = order_or_404(store, oid)
    if module_of(o) != module:
        raise HTTPException(404, "No such order in this module.")
    return o


def module_report_or_404(store, rid, module):
    r = report_or_404(store, rid)
    o = store.orders.get(r.get("order_id"))
    if not o or module_of(o) != module:
        raise HTTPException(404, "No such report in this module.")
    return r


SIGNING_DEPARTMENTS = {"radiology": ("Radiology", "Nuclear Medicine"), "pathology": ("Pathology",)}


def module_signer(request, store, module, order):
    """The signing consultant of the account for an order of this module (security review #12): a consultant of the order's performing
    department; for the laboratory, a consultant of any laboratory department (the demo's laboratory consultant verifies the whole
    laboratory); for radiology, Radiology or Nuclear Medicine. Else Forbidden with a plain message."""
    p = signer(request, store)
    if module == "lab":
        allowed = {t.get("department") for t in store.tests.values() if t.get("doc_type") == "lab"}
    else:
        allowed = set(SIGNING_DEPARTMENTS.get(module, ()))
    allowed.add(order.get("performing_department"))
    if p.get("department") not in allowed:
        raise auth.Forbidden(f"{auth.REFUSED}: {p['name']} signs for {p.get('department')}, not for {order.get('performing_department')}.")
    return p


def d(value):
    """DD/MM/YYYY of an ISO date or date-time ('' when empty)."""
    return ids.display_date(value) if value else ""


def dt(value):
    """DD/MM/YYYY HH:MM when the value carries a time, else DD/MM/YYYY."""
    if not value:
        return ""
    return ids.display_time(value) if len(str(value).strip()) > 10 else ids.display_date(value)


def prac_name(store, pid):
    p = store.practitioner(pid) if pid else None
    return p["name"] if p else ""


def age_sex(p):
    return f"{p['age']} Y / {p['sex']}"


def today(store):
    return store.now()[:10]


def current_admission(store, pid):
    return next((e for e in store.encounters_for(pid) if e["kind"] == "IP" and e["status"] == "in-progress"), None)


def is_imaging(order):
    return order["doc_type"] in model.IMAGING_MODALITY


def is_tissue(order):
    return order["doc_type"] in model.TISSUE_DOC_TYPES


def is_lab(order):
    return order["doc_type"] == "lab"


def module_of(order):
    """The module that works an order: lab, radiology, pathology, or opd (clinical notes and procedures of the units)."""
    if is_lab(order):
        return "lab"
    if is_imaging(order):
        return "radiology"
    if is_tissue(order):
        return "pathology"
    return "opd"


def order_url(order):
    return f"/his/{module_of(order)}/orders/{quote(order['id'])}"


def report_url(store, report):
    o = store.orders.get(report["order_id"])
    return order_url(o) if o else "/his"


def viewer_url(study_uid):
    """The PACS viewer link of a study on this HIMS (see pacs_proxy.py for why the path looks like the Vaidyx one)."""
    return "/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=" + quote(str(study_uid), safe=".")


# -------------------------------------------------------------------- the patient banner
def banner(store, p, e=None):
    """Name, UHID, Age / Sex, IP / OP No., Ward / Bed, Consultant on every patient page."""
    if e is None:
        e = current_admission(store, p["id"]) or (store.encounters_for(p["id"]) or [None])[-1]
    parts = [f'<span><b>Name:</b> <a href="/his/patients/{ui.esc(p["id"])}">{ui.esc(p["name"])}</a></span>',
             f'<span><b>UHID:</b> <span class=mono>{ui.esc(p["uhid"])}</span> {ui.pill(p["registration_kind"])}</span>',
             f'<span><b>Age / Sex:</b> {ui.esc(age_sex(p))}</span>']
    if e:
        label = "IP No." if e["kind"] == "IP" else "OP No."
        parts.append(f'<span><b>{label}:</b> <a href="/his/encounters/{ui.esc(e["id"])}" class=mono>{ui.esc(e["number"])}</a>'
                     f' ({ui.esc(e["department"])}, {ui.esc(e.get("unit") or "")})</span>')
        if e["kind"] == "IP":
            where = f"{e.get('ward') or ''}, {e.get('bed') or ''}" + ("" if e["status"] == "in-progress" else " (discharged)")
            parts.append(f'<span><b>Ward / Bed:</b> {ui.esc(where)}</span>')
        parts.append(f'<span><b>Consultant:</b> {ui.esc(prac_name(store, e.get("consultant_id")) or "not assigned")}</span>')
    else:
        parts.append('<span><b>IP / OP No.:</b> <span class=muted>no visit yet</span></span>')
    return f'<div class=banner>{"".join(parts)}</div>'


# -------------------------------------------------------------------- change runners
def apply(hospital, request, action, change, *, detail=None):
    """Run one ADT / order change under the lock; append one HL7 message per new event; save; one his_audit line.
    A refused change leaves nothing appended (and is audited as refused)."""
    s = user(request) or {}
    files = hospital.files
    with hospital.lock:
        store = hospital.store
        n = len(store.events)
        try:
            result = change(store)
        except Exception as exc:
            if len(hospital.store.events) != n:
                hospital.reload()
            auth.audit(files["data_dir"], action, "refused", user=s.get("email"), roles=s.get("roles"), detail=str(exc)[:300])
            raise
        for ev in store.events[n:]:
            hl7.append(store, ev, files["hl7"])
        if len(store.events) > n:
            hospital.save()
    auth.audit(files["data_dir"], action, "done", user=s.get("email"), roles=s.get("roles"), detail=detail)
    return result


def run(hospital, request, dept, action, change, *, order_id=None, report_id=None, detail=None):
    """An order / report action through the reporting engine (render the PDF, build and upload DICOM, HL7, save, desk
    audit), plus one his_audit line. Returns (record, notes)."""
    from . import desk

    s = user(request) or {}
    by = by_label(request, hospital.store)
    try:
        rec, notes = desk.run_action(hospital, dept, action, change, order_id=order_id, report_id=report_id, by=by)
    except Exception as exc:
        auth.audit(hospital.files["data_dir"], action, "refused", user=s.get("email"), roles=s.get("roles"),
                   detail=str(exc)[:300])
        raise
    auth.audit(hospital.files["data_dir"], action, "done", user=s.get("email"), roles=s.get("roles"), detail=detail)
    return rec, notes


def notes_flash(msg, notes):
    """(text, warn) of the redirect flash of a done action: its message, then what the engine said (PDF, images, HL7) as
    sentences. `warn` is True when a side effect did not work (the action itself is saved), shown in amber."""
    sentences = [msg.rstrip(". ")] + [t[:1].upper() + t[1:] for _, t in notes]
    return ". ".join(x.rstrip(". ") for x in sentences) + ".", any(k == "bad" for k, _ in notes)


# -------------------------------------------------------------------- orders and reports as table rows
def version_label(v):
    return f"v{v['version']} ({v['status']})"


def documents_cell(r):
    """The report's PDF: one button for the current version; earlier versions (a preliminary entry, an amended report) stay
    kept and reachable under a folded "Earlier versions" line (every version is part of the medico-legal record)."""
    if not r:
        return '<span class=muted>no report yet</span>'
    vs = sorted(r["versions"], key=lambda v: v["version"])
    cur = next((v for v in vs if v["version"] == r.get("current_version")), vs[-1])
    path = (cur.get("document") or {}).get("path")
    word = {"final": "final", "amended": "amended", "preliminary": "preliminary", "cancelled": "cancelled"}.get(cur.get("status"), "")
    if path:
        out = (f'<a class="btn" href="/view/reports/{ui.esc(r["id"])}/{cur["version"]}" target=_blank '
               f'title="Version {cur["version"]}{", " + word if word else ""}">PDF{" (" + ui.esc(word) + ")" if word and word != "final" else ""}</a>')
    else:
        out = '<span class=muted>PDF not rendered</span>'
    older = [v for v in vs if v is not cur]
    if older:
        links = "".join(
            f'<li><a href="/view/reports/{ui.esc(r["id"])}/{v["version"]}" target=_blank>{ui.esc(version_label(v))}</a></li>'
            if (v.get("document") or {}).get("path") else f'<li class=muted>{ui.esc(version_label(v))} not rendered</li>'
            for v in older)
        out += (f'<details class="small versions"><summary>Earlier versions ({len(older)})</summary><ul>{links}</ul></details>')
    return out


def order_state(store, o):
    if o["status"] == "scheduled" and o.get("scheduled_for"):
        return f"scheduled for {dt(o['scheduled_for'])}"
    if o["status"] == "sample_collected":
        spec = store.specimens.get(o.get("specimen_id")) or {}
        return f"sample collected {spec.get('barcode') or ''}".strip()
    if o["status"] == "cancelled":
        return f"cancelled {d(o.get('cancelled_on'))}" + (f": {o['cancel_reason']}" if o.get("cancel_reason") else "")
    return ""


def orders_table(store, orders, empty="No orders on this encounter."):
    rows = []
    for o in orders:
        r = store.report_for_order(o["id"])
        cur = store.current_version(r) if r and r["versions"] else None
        status = ui.pill(o["status"]) + (" " + ui.pill(r["status"]) if r else "")
        state = order_state(store, o)
        if state:
            status += f'<br><span class=muted>{ui.esc(state)}</span>'
        acc = (f'<a href="{order_url(o)}" class=mono>{ui.esc(o["accession"])}</a>' if o["accession"]
               else f'<a href="{order_url(o)}" class=muted>none</a>')
        rows.append([acc, ui.esc(o["label"]), ui.esc(o["performing_department"]), ui.esc(d(o["ordered_on"])), status,
                     ui.esc(dt(cur["reported_on"])) if cur else "", ("yes" if cur.get("signature_id") else "no") if cur else "",
                     documents_cell(r)])
    return ui.table(["Accession / Lab No.", "Test", "Department", "Ordered on", "Status", "Reported on", "Signed",
                     "Document"], rows, empty=empty)


def patient_cell(store, rec):
    p = store.patients.get(rec["patient_id"]) or {}
    return (f'<a href="/his/patients/{ui.esc(p.get("id"))}"><b>{ui.esc(p.get("name"))}</b></a><br>'
            f'<span class=mono>{ui.esc(p.get("uhid"))}</span> <span class=muted>{ui.esc(p.get("age"))} Y / {ui.esc(p.get("sex"))}</span>')


def encounter_cell(store, rec):
    e = store.encounters.get(rec["encounter_id"]) or {}
    return f'<a href="/his/encounters/{ui.esc(e.get("id"))}" class=mono>{ui.esc(e.get("number"))}</a>'


def unit_cell(store, order):
    e = store.encounters.get(order["encounter_id"]) or {}
    who = prac_name(store, e.get("consultant_id"))
    return ui.esc(order["ordering_department"] + (f", {e['unit']}" if e.get("unit") else "") + (f", {who}" if who else ""))


def order_panel(store, o):
    """The order's details (patient identifiers, test, accession, status, sample or schedule) as a definition list."""
    p = store.patients.get(o["patient_id"]) or {}
    e = store.encounters.get(o["encounter_id"]) or {}
    spec = store.specimens.get(o.get("specimen_id")) if o.get("specimen_id") else None
    pairs = [("Test", f"<b>{ui.esc(o['label'])}</b>"),
             ("Accession / Lab No.", f"<span class=mono>{ui.esc(o['accession'] or 'none')}</span>"),
             ("Ordered on", ui.esc(dt(o["ordered_on"]))),
             ("Ordering unit", unit_cell(store, o)),
             ("Performing department", ui.esc(o["performing_department"])),
             ("Status", ui.pill(o["status"]))]
    if o.get("scheduled_for"):
        pairs.append(("Scheduled", ui.esc(dt(o["scheduled_for"])) + (f", {ui.esc(o['room'])}" if o.get("room") else "")))
    if spec:
        pairs.append(("Sample", f"<span class=mono>{ui.esc(spec['barcode'])}</span> ({ui.esc(spec['type'])}), collected "
                                f"{ui.esc(dt(spec['collected_on']))}"))
        if spec.get("block_no"):
            pairs.append(("Block No.", f"<span class=mono>{ui.esc(spec['block_no'])}</span>"))
    if o.get("cancel_reason"):
        pairs.append(("Cancelled", ui.esc(f"{dt(o['cancelled_on'])}: {o['cancel_reason']}")))
    return f'<div class=panel id=order>{ui.dl(pairs)}</div>'


def versions_table(store, r):
    rows = []
    for x in r["versions"]:
        sig = store.signatures.get(x.get("signature_id") or "") or {}
        rows.append([str(x["version"]), ui.pill(x["status"]), ui.esc(dt(x["reported_on"])),
                     ui.esc(prac_name(store, x.get("reported_by"))),
                     ui.esc(sig.get("block") or ("Signature pending" if x["status"] not in ("preliminary", "cancelled") else "Not signed")),
                     ui.esc(x.get("amendment_note") or ""),
                     (f'<a href="/view/reports/{ui.esc(r["id"])}/{x["version"]}" target=_blank>PDF</a>'
                      if (x.get("document") or {}).get("path") else '<span class=muted>not rendered</span>')])
    return ui.table(["Version", "Status", "Reported on", "Reported by", "Signature", "Amendment note", "PDF"], rows,
                    "No version yet.")


def values_table(values, labels=None):
    from . import documents

    rows = [[ui.esc((labels or {}).get(k) or documents.label(k)), ui.esc(v)] for k, v in (values or {}).items()]
    return ui.table(["Item", "As printed"], rows, "No values entered.")


def refused_line(request, permission):
    """A muted line in place of a form the role cannot use."""
    return f'<p class=muted>{ui.esc(auth.refusal(permission))}</p>'


KEY = re.compile(r"^[a-z][a-z0-9_]*$")


def parse_values(text_):
    """Free values: one `key: value` per line (the pathology IHC panel and the generic reports)."""
    from . import desk

    return desk.parse_values(text_)
