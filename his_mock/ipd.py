"""The IPD module of the demo HIMS, mounted at /his by app.py. SYNTHETIC data only.

    GET /his/ipd        the ward census (current admissions by ward and bed, with the PM-JAY Pre-Authorization line)
                        and the recent discharges

Admit lives on the patient page, transfer and discharge on the admission page (screens.py); the discharge summary form
and its action (`discharge_summary_form`, `do_discharge_summary`) live here and are used by that page: a
`discharge_summary` order signed at once by the consultant (diagnosis, course, advice), rendered as a PDF, sent as ORU on
the HL7 feed and shown in FHIR as a DocumentReference. No em dashes.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from . import common, model, templates, ui
from .app import Hospital, get_hospital
from .common import FieldError, d, dt

router = APIRouter()

SUMMARY_TEST = "discharge_summary"


def _fields_form(request, fields, state, prefix="v_"):
    st = state or common.EMPTY
    out = []
    for f in fields:
        name = prefix + f["key"]
        ctl = ui.textarea(name, st.v(name), rows=f["rows"] or 3, required=f["required"], placeholder=f["example"])
        out.append(ui.field(name, f["label"] + (" *" if f["required"] else ""), ctl, st.err(name)))
    return "".join(out)


def existing_summary(store, e):
    return next((r for r in store.reports_for(encounter_id=e["id"]) if r["test"] == SUMMARY_TEST
                 and r["status"] in ("final", "amended", "preliminary")), None)


def discharge_summary_form(request, store, e, state=None):
    if not common.can(request, "note"):
        return '<div class=panel id=summary><h2>Discharge summary</h2>' + common.refused_line(request, "note") + '</div>'
    done = existing_summary(store, e)
    if done:
        v = store.current_version(done)
        link = (f' <a href="/view/reports/{ui.esc(done["id"])}/{v["version"]}" target=_blank>PDF</a>'
                if (v.get("document") or {}).get("path") else "")
        return (f'<div class=panel id=summary><h2>Discharge summary</h2><p>Written on {ui.esc(dt(v["reported_on"]))} '
                f'({ui.pill(done["status"])}){link}. A correction goes through an addendum on '
                f'<a href="{common.order_url(store.orders[done["order_id"]])}">its report page</a>.</p></div>')
    not_ours = common.not_own_department(request, store, e["department"])
    if not_ours:
        return f'<div class=panel id=summary><h2>Discharge summary</h2><p class=muted>{ui.esc(not_ours)}</p></div>'
    me = common.practitioner(request, store)
    st = state if state is not None and state.form == "summary" else None
    who = (f'<p class=muted>Signed by {ui.esc(me["name"])}, Reg. No. {ui.esc(me["reg_no"])} (Vaidyx Demo CA). '
           'Ward movements, referrals and the PM-JAY line are filled in from the admission.</p>' if me
           else '<p class=muted>This account is not a consultant: the summary cannot be signed.</p>')
    return ('<div class=panel id=summary><h2>Discharge summary</h2>'
            f'<form method=post action="/his/encounters/{ui.esc(e["id"])}/discharge-summary">{common.csrf_field(request)}'
            + _fields_form(request, templates.DISCHARGE_SUMMARY, st) + who
            + '<p><button type=submit class=primary>Sign the discharge summary</button></p></form></div>')


def do_discharge_summary(hospital, request, e, form):
    store = hospital.store
    if e["kind"] != "IP":
        raise model.LifecycleError("A discharge summary is written on an IP admission.")
    if existing_summary(store, e):
        raise model.LifecycleError("This admission already has a discharge summary; amend it on its report page.")
    prac = common.signer(request, store)
    common.require_own_department(request, store, e["department"])
    values, errors = templates.parse_fields(templates.DISCHARGE_SUMMARY, form)
    if errors:
        field, msg = next(iter(errors.items()))
        raise FieldError(field, msg)
    dept = store.department(e["department"])

    def change(s):
        o = s.place_order(e["patient_id"], e["id"], SUMMARY_TEST, e["department"])
        return s.sign_final(o["id"], prac["id"], values=values)

    return common.run(hospital, request, dept, "sign", change, detail=f"discharge_summary on {e['number']}")


# -------------------------------------------------------------------- the ward census
def _preauth(e):
    pre = e.get("pmjay_preauth")
    if not pre:
        return "not requested"
    return (pre.get("status") or "") + (f" ({d(pre['date'])})" if pre.get("date") else "")


def census(store):
    """Current admissions sorted by ward and bed."""
    out = [e for e in store.encounters.values() if e["kind"] == "IP" and e["status"] == "in-progress"]
    return sorted(out, key=lambda e: (e.get("ward") or "", e.get("bed") or "", e["number"]))


def recent_discharges(store, n=10):
    out = [e for e in store.encounters.values() if e["kind"] == "IP" and e.get("discharged")]
    return sorted(out, key=lambda e: (e["discharged"], e["number"]), reverse=True)[:n]


@router.get("/ipd", response_class=HTMLResponse)
def ipd_home(request: Request, hospital: Hospital = Depends(get_hospital)):
    store = hospital.store
    rows = []
    for e in census(store):
        p = store.patients.get(e["patient_id"]) or {}
        pmjay = p.get("pmjay_id") or ""
        rows.append([ui.esc(e.get("ward")), ui.esc(e.get("bed")),
                     f'<a href="/his/encounters/{ui.esc(e["id"])}" class=mono>{ui.esc(e["number"])}</a>',
                     common.patient_cell(store, e), ui.esc(f"{e['department']}, {e.get('unit') or ''}"),
                     ui.esc(common.prac_name(store, e.get("consultant_id")) or "not assigned"), ui.esc(d(e.get("admitted"))),
                     ui.esc((f"{pmjay}: " if pmjay else "") + _preauth(e))])
    body = ('<div class=panel id=census><h2>Ward census (current admissions)</h2>'
            + ui.table(["Ward", "Bed", "IP No.", "Patient / UHID", "Department, unit", "Consultant", "Admitted on",
                        "PM-JAY Pre-Authorization"], rows, "No patient admitted at the moment.") + '</div>')
    rows = []
    for e in recent_discharges(store):
        rows.append([f'<a href="/his/encounters/{ui.esc(e["id"])}" class=mono>{ui.esc(e["number"])}</a>',
                     common.patient_cell(store, e), ui.esc(f"{e['department']}, {e.get('unit') or ''}"),
                     ui.esc(d(e.get("admitted"))), ui.esc(d(e.get("discharged"))),
                     "yes" if existing_summary(store, e) else '<span class=muted>no</span>'])
    body += ('<div class=panel id=discharges><h2>Recent discharges</h2>'
             + ui.table(["IP No.", "Patient / UHID", "Department, unit", "Admitted", "Discharged", "Summary"], rows,
                        "No discharge yet.") + '</div>')
    body += ('<p class=muted>Admit: search the patient in Registration and use "Admit" on the patient page. Transfer, '
             'discharge summary and discharge are on the admission page.</p>')
    return common.page(request, "IPD", body, active="IPD")
