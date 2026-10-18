"""The Admin module of the demo HIMS (hospital IT admin only), mounted at /his by app.py. SYNTHETIC data only.

    GET  /his/admin                             departments, practitioners (with the add form), accounts, the audit trails
                                                (his_audit.jsonl of logins and screen actions, desk_audit.jsonl of the
                                                reporting engine)
    POST /his/admin/practitioners               add a practitioner (name, qualification, Reg. No., department, role)
    POST /his/admin/accounts/{email}/reset      a new password for an account, shown ONCE on the page, never logged
"""
import json
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from . import auth, common, ui
from .app import Hospital, get_hospital
from .common import FieldError, FormState

router = APIRouter()

REG_NO = re.compile(r"^VXREG-\d{5}$")
AUDIT_LINES = 60


def next_reg_no(store):
    used = {p["reg_no"] for p in store.practitioners.values()}
    n = 30001
    while f"VXREG-{n}" in used:
        n += 1
    return f"VXREG-{n}"


def do_add_practitioner(store, f):
    name = common.text(f, "name")
    if not name.startswith("Dr "):
        raise FieldError("name", 'The name starts with "Dr ".')
    qualification = common.text(f, "qualification")
    if not qualification:
        raise FieldError("qualification", "Enter the qualification (for example MD (Pathology)).")
    reg_no = common.text(f, "reg_no").upper() or next_reg_no(store)
    if not REG_NO.match(reg_no):
        raise FieldError("reg_no", "Reg. No. must be VXREG- and 5 digits (synthetic council number).")
    if store.practitioner(reg_no):
        raise FieldError("reg_no", f"{reg_no} is already in use.")
    dept = store.department(common.text(f, "department"))
    if not dept:
        raise FieldError("department", "Choose a department.")
    role = common.text(f, "role") or "consultant"
    if role not in ("consultant", "junior_resident"):
        raise FieldError("role", "Role must be consultant or junior_resident.")
    serial = f"VXDCA-{secrets.token_hex(4).upper()}"
    return store.add_practitioner(name, qualification, reg_no, dept["name"], serial, role=role)


def _desk_audit(files, n=AUDIT_LINES):
    p = Path(files["data_dir"]) / "desk_audit.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def render(request, hospital, state=None, flash=None, status=200):
    store, files = hospital.store, hospital.files
    st = state or common.EMPTY
    csrf = common.csrf_field(request)
    rows = [[f'<span class=mono>{ui.esc(d_["code"])}</span>', ui.esc(d_["name"]), ui.esc(d_["group"]),
             str(len([x for x in d_.get("consultants", []) if x in store.practitioners])), ui.esc(d_.get("email"))]
            for d_ in sorted(store.departments.values(), key=lambda x: (x["group"] != "treating", x["name"]))]
    body = ('<div class=panel id=departments><h2>Departments</h2>'
            + ui.table(["Code", "Department", "Group", "Practitioners", "Email"], rows, "No department.") + '</div>')
    rows = [[ui.esc(p["name"]), ui.esc(p["qualification"]), f'<span class=mono>{ui.esc(p["reg_no"])}</span>',
             ui.esc(p["department"]), ui.esc(p["role"].replace("_", " ")), f'<span class=mono>{ui.esc(p["certificate_serial"])}</span>']
            for p in sorted(store.practitioners.values(), key=lambda x: (x["department"], x["name"]))]
    depts = [(d_["name"], d_["name"]) for d_ in sorted(store.departments.values(), key=lambda x: x["name"])]
    body += ('<div class=panel id=practitioners><h2>Practitioners</h2>'
             + ui.table(["Name", "Qualification", "Reg. No.", "Department", "Role", "Demo CA serial"], rows, "No practitioner.")
             + '<h3>Add practitioner</h3><form method=post action="/his/admin/practitioners">' + csrf
             + ui.field("name", "Name", ui.text_input("name", st.v("name"), required=True, placeholder="Dr Firstname Surname"), st.err("name"))
             + ui.field("qualification", "Qualification", ui.text_input("qualification", st.v("qualification"), required=True,
                                                                        placeholder="MD (Pathology)"), st.err("qualification"))
             + ui.field("reg_no", "Reg. No.", ui.text_input("reg_no", st.v("reg_no", next_reg_no(store)), short=True), st.err("reg_no"),
                        help="Synthetic council number VXREG-nnnnn; left blank, the next free one is used.")
             + ui.field("department", "Department", ui.select("department", depts, st.v("department")), st.err("department"))
             + ui.field("role", "Role", ui.select("role", [("consultant", "Consultant"), ("junior_resident", "Junior resident")],
                                                  st.v("role"), short=True), st.err("role"))
             + '<p><button type=submit class=primary>Add practitioner</button></p></form></div>')
    rows = []
    for spec in auth.ACCOUNT_SPECS:
        acc = hospital.accounts.account(spec["email"])
        if not acc:
            continue
        rows.append([f'<span class=mono>{ui.esc(acc["email"])}</span>', ui.esc(", ".join(acc["roles"])), ui.esc(acc["label"]),
                     ui.esc(acc.get("practitioner_name") or "none (cannot sign)"), ui.esc(common.dt(acc.get("password_changed"))),
                     f'<form class=inline method=post action="/his/admin/accounts/{ui.esc(acc["email"])}/reset">{csrf}'
                     '<button type=submit>Reset password</button></form>'])
    body += ('<div class=panel id=accounts><h2>Accounts</h2>'
             + ui.table(["Email", "Roles", "Label", "Signs as", "Password changed", "Action"], rows, "No account.")
             + f'<p class=small>Passwords are bcrypt-hashed in accounts.json; the build wrote the initial ones to '
             f'<span class=mono>{ui.esc(str(hospital.accounts.logins_path))}</span> (mode 600). A reset shows the new password '
             'once, here, and ends that account\'s sessions.</p></div>')
    rows = [[ui.esc(common.dt(x.get("time"))), ui.esc(x.get("user")), ui.esc(", ".join(x.get("roles") or [])), ui.esc(x.get("action")),
             ui.pill("ok" if x.get("outcome") in ("ok", "done") else "bad") if x.get("outcome") else "", ui.esc(x.get("detail") or "")]
            for x in reversed(auth.read_audit(files["data_dir"], AUDIT_LINES))]
    body += (f'<div class=panel id=audit><h2>Audit: logins and screen actions (his_audit.jsonl, last {AUDIT_LINES})</h2>'
             + ui.table(["Time", "User", "Roles", "Action", "Outcome", "Detail"], rows, "No audit line yet.") + '</div>')
    rows = [[ui.esc(common.dt(x.get("time"))), ui.esc(x.get("department")), ui.esc(x.get("action")), ui.esc(x.get("order_id")),
             ui.esc(x.get("report_id") or ""), ui.esc(x.get("by")), ui.pill("ok" if x.get("outcome") == "done" else "bad"),
             ui.esc(x.get("detail") or "")] for x in reversed(_desk_audit(files))]
    body += (f'<div class=panel id=desk-audit><h2>Audit: reporting engine (desk_audit.jsonl, last {AUDIT_LINES})</h2>'
             + ui.table(["Time", "Dept", "Action", "Order", "Report", "By", "Outcome", "Detail"], rows, "No audit line yet.")
             + '</div>')
    return common.page(request, "Admin", body, active="Admin", flash=flash, status=status)


@router.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, hospital: Hospital = Depends(get_hospital)):
    common.require(request, "admin")
    return render(request, hospital)


@router.post("/admin/practitioners")
async def add_practitioner(request: Request, hospital: Hospital = Depends(get_hospital)):
    form = await common.form(request)
    common.require(request, "admin")
    s = common.user(request) or {}
    try:
        with hospital.lock:
            p = do_add_practitioner(hospital.store, form)
            hospital.save()
    except FieldError as ex:
        return render(request, hospital, state=FormState(common.values_of(form), {ex.field: ex.message}), status=422)
    except ValueError as ex:
        return common.redirect("/his/admin", str(ex), bad=True)
    auth.audit(hospital.files["data_dir"], "admin.add_practitioner", "done", user=s.get("email"), roles=s.get("roles"),
               detail=f"{p['name']} {p['reg_no']} {p['department']}")
    return common.redirect("/his/admin", f"Added {p['name']}, Reg. No. {p['reg_no']}, {p['department']} ({p['role']}).")


@router.post("/admin/accounts/{email}/reset")
async def reset_password(email: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    await common.form(request)
    common.require(request, "admin")
    s = common.user(request) or {}
    try:
        password = hospital.accounts.reset_password(email)
    except KeyError:
        return common.redirect("/his/admin", "No such account.", bad=True)
    auth.audit(hospital.files["data_dir"], "admin.reset_password", "done", user=s.get("email"), roles=s.get("roles"), detail=email)
    # shown once, on this page only: never in a URL, a log or the audit
    return render(request, hospital, flash=("warn", f"New password for {email}: {password} (shown once; copy it now)."))
