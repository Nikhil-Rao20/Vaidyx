"""The patient's Case Files (night-v3 item 1.1: one Case File per patient and cancer).

GET /patient-case-files?identifier=<UHID or IP / OP No.> answers the New Case File page: once the patient is found, it lists the live
Case Files of that patient (the same UHID or a registration linked to one; his_case.same_patient_cases), so the doctor sees that a
Case File for this cancer exists ("Open it" when allowed, else "Ask to join") and that another cancer gets its own Case File, linked
to these. GET /patient-case-files?case_id=<id> lists the other Case Files of that Case File's patient for its Overview ("Other Case
Files of this patient"), for a person who may open that Case File.

Each row says only the cancer, the owning department and consultant, the creation date, a status word and whether this person may
open it: no clinical content and no name but the owner's. Archived and protected Case Files are never listed. For any placed login or
the MDT Coordinator (never an outside expert or a Vaidyx admin); the identifier look-up is rate-limited (30 per 10 minutes per login;
the case_id form is not, as it only answers for a Case File the person may open already, so opening Overviews never uses up the
New Case File page's look-ups); both are audited in the organisation log (kind patient_case_files_checked) without the identifier."""
from fastapi import Request

from tumour_board import access, his_case, his_client, org, store
from tumour_board.api.common import RateLimit, fail, make_router, roles

router = make_router()
CHECK_LIMIT = RateLimit(30, 10 * 60)


def _may_check(r: dict) -> bool:
    if not isinstance(r, dict) or r.get("disabled") or r.get("expired") or not r.get("known"):
        return False
    if r.get("vaidyx_admin") or (r.get("outside_expert") and not r.get("departments") and not r.get("coordinator")):
        return False
    return bool(r.get("coordinator") or r.get("departments"))


def _status_label(c: dict) -> str:
    """A plain status word without clinical content: archived files are never listed here."""
    if isinstance(c.get("board_ready"), dict) and c["board_ready"].get("at"):
        return "Ready for the board"
    st = store.get_state(c["case_id"]) or {}
    if any(isinstance(x, dict) for x in st.get("board_records") or []):
        return "Discussed at the board"
    if not c.get("protocol"):
        return "Cancer not chosen yet"
    return "Being prepared"


def rows(cases, r: dict) -> list:
    out = []
    for c in sorted(cases, key=lambda x: str(x.get("created") or "")):
        brief = his_case.file_brief(c, r)
        out.append({**brief, "owner_words": his_case.owner_words(brief), "created_at": c.get("created") or "", "status_label": _status_label(c)})
    return out


async def _uhids_of(identifier: str) -> set:
    """The UHIDs the identifier stands for, resolved like the HIS lookup (a UHID, an IP / OP No. or an ABHA); the identifier itself when
    no hospital system answers (a Case File made by hand carries the UHID it was given)."""
    out = {identifier}
    client = his_client.client()
    if client is None:
        return out
    try:
        p = await client.find_patient(identifier)
    except his_client.HISError:
        return out
    if p and p.get("uhid"):
        out = {p["uhid"]} | ({identifier} if isinstance(p.get("matched_on"), dict) and p["matched_on"].get("kind") == "uhid" else set())
    return out


@router.get("/patient-case-files")
async def patient_case_files(request: Request, identifier: str = "", case_id: str = ""):
    r = roles(request)
    if not _may_check(r):
        fail(403, "Only a doctor placed in a department or the MDT Coordinator sees a patient's Case Files.", "forbidden")
    identifier = str(identifier or "").strip()[:80]
    if case_id:
        try:
            c = store.get_case(store.safe_id(case_id))
        except ValueError:
            c = None
        if not c or access.scope(r, c) != access.FULL:  # a Case File this person cannot open is not named (nor its patient's other files)
            fail(404, "Case not found", "not_found")
        system = (c["his"].get("kind"), c["his"].get("label")) if isinstance(c.get("his"), dict) else None
        found = his_case.same_patient_cases(his_case.case_uhids(c), exclude=c["case_id"], his=system)
        org.audit("patient_case_files_checked", r["user"], how="case_id", case_id=c["case_id"], count=len(found))
        return {"cases": rows(found, r)}
    if not identifier:
        fail(400, "Give the UHID, IP No. or OP No.", "bad_identifier")
    CHECK_LIMIT.check(r["user"], "Too many look-ups. Wait a few minutes and try again.")
    client = his_client.client()
    system = (client.kind, client.label) if client is not None else None
    found = his_case.same_patient_cases(await _uhids_of(identifier), his=system)
    org.audit("patient_case_files_checked", r["user"], how="identifier", count=len(found))  # never the identifier (night-v3 item 1.1)
    return {"cases": rows(found, r)}
