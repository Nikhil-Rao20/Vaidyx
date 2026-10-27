"""HIS-connected Case Files (plan items V2-3.2 create from a UHID, 3.5 re-fetch, 3.6 outside reports).

A treating doctor enters a UHID (or an IP / OP No. that resolves to its UHID). The adapter (his_client) finds the registration,
lists the registrations that may be the same person (temporary or duplicate UHIDs: shown for a person to link, never merged) and
fetches every report version of every OP visit and IP admission inside the fetch window (default 12 months, adjustable; "Fetch
older records" widens it later). Each report arrives as a document in the Case File with its HIS metadata (`doc["his"]`: report
id and version, status, signature, encounter, accession, order, the HIS Observations as candidates) and runs the V1 pipeline:
the PDF text is read, classified and extracted, his_overlay fills status / signed from the HIS and checks every candidate value
against the text. Nothing is written to the hospital system.

Re-fetch (3.5): a delta pull since the Case File's watermark (the newest `meta.lastUpdated` seen); only new or changed versions
are processed, the earlier version of an amended report is kept as history (`superseded`), the gate re-checks, requests whose
record now arrives final and signed close themselves (rules.sync_actions) and the owning department is told.

Outside reports (3.6) are uploaded by the treating doctor into the Case File (service.add_files(outside=True)); they run the V1
pipeline including patient matching and OCR and carry `doc["outside"]`.
"""
import hashlib
import logging
import asyncio
import re
from datetime import date, datetime

from . import config, his_client, identity, intake, notify, org, store

log = logging.getLogger("tumour_board")

FIRST, REFETCH, OLDER, LINK = "first_fetch", "refetch", "older", "link"
WINDOW_MONTHS = (6, 12, 24)
HIS_FOLDER = "HIS"


class HISCaseError(ValueError):
    """A plain message for the caller (400 / 404 / 409 chosen by the route through `status`)."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---- fetch window ----------------------------------------------------------------------------------------------------

def default_window() -> dict:
    months = (org.load().get("hospital") or {}).get("fetch_window_months") or 12
    return {"months": int(months)}


def window_from(body) -> dict:
    """{"months": 6 | 12 | 24 | n}, {"all": true} or {"from": "YYYY-MM-DD" | "DD/MM/YYYY"}; the hospital default when empty."""
    if not body:
        return default_window()
    if not isinstance(body, dict):
        raise HISCaseError("The fetch window must be given as months, all or a from-date")
    if body.get("all"):
        return {"all": True}
    if body.get("from"):
        from .docstatus import parse_date
        iso = parse_date(str(body["from"]))
        if not iso:
            raise HISCaseError(f"Not a valid from-date: {body['from']}")
        return {"from": iso}
    if body.get("months") is not None:
        try:
            m = int(body["months"])
        except (TypeError, ValueError):
            raise HISCaseError("The fetch window must be a number of months")
        if not org.FETCH_WINDOW_RANGE[0] <= m <= org.FETCH_WINDOW_RANGE[1]:
            raise HISCaseError(f"The fetch window must be between {org.FETCH_WINDOW_RANGE[0]} and {org.FETCH_WINDOW_RANGE[1]} months")
        return {"months": m}
    return default_window()


def _months_ago(d: date, n: int) -> date:
    y, m = d.year, d.month - n
    while m <= 0:
        y -= 1; m += 12
    last = [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def window_start(window: dict, today=None) -> str:
    """The ISO date records must be dated on or after; "" for every record."""
    today = today or date.today()
    if window.get("all"):
        return ""
    if window.get("from"):
        return window["from"]
    return _months_ago(today, int(window.get("months") or 12)).isoformat()


def dmy(s) -> str:
    """DD/MM/YYYY of an ISO date or date-time (Indian convention); other strings as given."""
    s = str(s or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[0:4]}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else s


def window_label(window: dict) -> str:
    if window.get("all"):
        return "all records"
    if window.get("from"):
        return f"records from {dmy(window['from'])}"
    return f"last {window.get('months', 12)} months"


# ---- the cancer's name (owner decision R05-Q04) -------------------------------------------------------------------------

CANCER_NAME_MIN, CANCER_NAME_MAX = 2, 80


def clean_cancer_name(value, protocol_id: str = "") -> str:
    """The cancer's name as the doctor picked or typed it (case.json "cancer_name"): trimmed, inner spaces collapsed, 2 to 80
    characters. Required under the generic rule (a cancer with no built checklist: protocol "generic", four core records), optional
    under a built checklist. Returns "" when none is given and none is needed; HISCaseError (400) with a plain message otherwise."""
    from .protocol import GENERIC_IDS
    if value is not None and not isinstance(value, str):
        raise HISCaseError("The cancer's name must be text")
    name = " ".join(str(value or "").split())
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise HISCaseError("The cancer's name has characters that cannot be shown: type it again")
    if not name:
        if protocol_id in GENERIC_IDS:
            raise HISCaseError(f"Type the cancer's name: a cancer with no checklist yet needs it ({CANCER_NAME_MIN} to {CANCER_NAME_MAX} characters)")
        return ""
    if not CANCER_NAME_MIN <= len(name) <= CANCER_NAME_MAX:
        raise HISCaseError(f"The cancer's name must be {CANCER_NAME_MIN} to {CANCER_NAME_MAX} characters (it has {len(name)})")
    return name


def _same_cancer(c: dict, protocol_id: str, cancer_name: str) -> bool:
    """Another Case File of the same UHID is for the same cancer: the same protocol and, under the generic rule, the same typed name."""
    if c.get("protocol") != protocol_id:
        return False
    from .protocol import GENERIC_IDS
    return protocol_id not in GENERIC_IDS or " ".join(str(c.get("cancer_name") or "").split()).lower() == cancer_name.lower()


# ---- the same patient and the same cancer (night-v3 item 1.1: one Case File per patient and cancer) ----------------------------

DUPLICATE_CODE = "duplicate_case_file"


class DuplicateCaseFile(HISCaseError):
    """A non-archived Case File for this patient and this cancer exists: the creation is refused (409) and the caller is shown who owns
    it, with "Open it" when the caller may already open it, else "Ask to join". `body()` is the JSON the routes answer."""

    def __init__(self, existing: dict, message: str):
        super().__init__(message, 409)
        self.existing = existing

    def body(self) -> dict:
        return {"detail": str(self), "code": DUPLICATE_CODE, "existing": dict(self.existing)}


def case_uhids(c: dict) -> set:
    """Every UHID a Case File answers for, normalised (identity.normalise_id): the HIS registration it was made from, the patient's UHID
    (patient.mrn) and every patient identifier of kind uhid, the registrations a person linked to it included."""
    c = c if isinstance(c, dict) else {}
    p = c.get("patient") if isinstance(c.get("patient"), dict) else {}
    raw = [(c.get("his") or {}).get("uhid") if isinstance(c.get("his"), dict) else "", p.get("mrn")]
    raw += [x.get("value") for x in p.get("ids") or [] if isinstance(x, dict) and x.get("kind") == "uhid"]
    return {n for n in (identity.normalise_id(x) for x in raw if x) if n}


def same_patient_cases(uhids, exclude: str = "", his=None) -> list:
    """The live Case Files of the same patient: their UHID set overlaps `uhids` (linked registrations count). Archived and protected
    Case Files (config.PROTECTED_CASES, real patient data) never count. `his` = (kind, label) of the hospital system in use: a Case File
    made from another hospital system answers for another numbering and is left out; a Case File made by hand (no HIS) counts."""
    from . import access
    want = {n for n in (identity.normalise_id(u) for u in uhids or () if u) if n}
    if not want:
        return []
    out = []
    for c in store.list_cases():
        cid = c.get("case_id")
        if not cid or cid == exclude or cid in config.PROTECTED_CASES or access.is_archived(c):
            continue
        h = c.get("his") if isinstance(c.get("his"), dict) else None
        if his and h and (h.get("kind"), str(h.get("label") or "")) != (his[0], str(his[1] or "")):
            continue
        if case_uhids(c) & want:
            out.append(c)
    return out


def owner_doctor(c: dict) -> str:
    """The consultant shown as the Case File's owner, as the Case Files list names it: its creator when a consultant of the owning
    department, else the first one (the creator when none is placed)."""
    from . import team
    cons = team.owner_consultants(c)
    by = str((c or {}).get("created_by") or "")
    return by if by in cons else (cons[0] if cons else by)


def dr_name(name: str) -> str:
    """"Dr Rao" when the name has no title yet (as the interface writes it)."""
    name = str(name or "").strip()
    return name if not name or re.match(r"^(dr|prof)\.?\s", name, re.I) else f"Dr {name}"


def file_brief(c: dict, roles: dict | None) -> dict:
    """A Case File as another Case File's creator may see it: the cancer, the owning department and consultant, and whether this person
    may open it. No clinical content and no patient detail."""
    from . import access, profiles, protocol
    own = access.owner(c)
    doc = owner_doctor(c)
    return {"case_id": c["case_id"], "protocol": c.get("protocol") or "", "cancer_name": c.get("cancer_name") or "",
            "cancer_label": protocol.case_label(c) or "Cancer not chosen yet",
            "department": own or "", "department_name": org.department_name(own) if own else "",
            "owner": doc, "owner_name": profiles.display_name(doc) if doc else "",
            "can_open": bool(roles) and access.scope(roles, c) == access.FULL}


def owner_words(brief: dict) -> str:
    """"Breast Surgery, Dr X" (the department alone when no consultant is placed yet)."""
    return ", ".join(x for x in (brief.get("department_name") or "", dr_name(brief.get("owner_name") or "")) if x) or "owner not set"


def duplicate_of(uhids, protocol_id: str, cancer_name: str = "", his=None, exclude: str = ""):
    """The live Case File of the same patient and the same cancer (_same_cancer), or None. No cancer chosen yet: never a duplicate."""
    if not protocol_id:
        return None
    return next((c for c in same_patient_cases(uhids, exclude, his) if _same_cancer(c, protocol_id, cancer_name or "")), None)


def refuse_duplicate(uhids, protocol_id: str, cancer_name: str, user: str, roles: dict, his=None, via: str = "", exclude: str = "") -> None:
    """DuplicateCaseFile (409) when a live Case File of this patient and this cancer exists; the refusal is audited in that Case File
    (kind duplicate_refused: who and the cancer tried; nothing more of the patient). `exclude`: the Case File being listed itself."""
    dup = duplicate_of(uhids, protocol_id, cancer_name, his, exclude)
    if not dup:
        return
    brief = file_brief(dup, roles)
    store.audit(dup["case_id"], {"kind": "duplicate_refused", "by": user, "protocol": protocol_id, **({"cancer_name": cancer_name} if cancer_name else {}),
                                 **({"via": via} if via else {})})
    raise DuplicateCaseFile(brief, f"A Case File for this patient and this cancer exists ({owner_words(brief)})")


# ---- helpers ---------------------------------------------------------------------------------------------------------

def _day(s) -> str:
    return str(s or "")[:10]


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", str(s or "")).strip("_")
    return s[:60] or "record"


def rel_path(r: dict, ext: str = ".pdf") -> str:
    enc = r.get("encounter_number") or "no_encounter"
    return f"{HIS_FOLDER}/{_slug(enc)}/{_slug(r.get('title') or r.get('id'))}_v{r.get('version') or 1}{ext or '.pdf'}"


def patient_record(p: dict, encounters=()) -> dict:
    """A Case File patient record from the HIS registration: UHID as the MRN, ABHA / PM-JAY, and every OP / IP number of the
    patient's encounters as learned identifiers (so each record's IP / OP No. matches on arrival). Never an Aadhaar."""
    ids = [{"kind": "uhid", "value": p["uhid"], "from": "his"}]
    if p.get("abha"):
        ids.append({"kind": "abha", "value": p["abha"], "from": "his"})
    if p.get("pmjay_id"):
        ids.append({"kind": "pmjay", "value": p["pmjay_id"], "from": "his"})
    for e in encounters or []:
        if e.get("number"):
            ids.append({"kind": "ip_no" if e.get("kind") == "IP" else "op_no", "value": e["number"], "from": "his"})
    agesex = f"{p['age']} Y / {p['sex']}" if p.get("age") is not None and p.get("sex") else ""
    return {"name": p.get("name") or "", "mrn": p["uhid"], "agesex": agesex, "age": p.get("age"), "sex": p.get("sex") or "", "dob": p.get("dob") or "",
            "abha": p.get("abha") or None, "ids": ids, "source": "his", "registration_kind": p.get("registration_kind") or "permanent"}


def learn_encounters(case: dict, encounters, source: str = "his", registration: str = "") -> list:
    """The Case File learns the OP / IP numbers of encounters it does not know yet (a new visit since the first fetch, a linked
    registration's visits), so each record's printed number matches on arrival. Returns the identifiers added."""
    pat = case.setdefault("patient", {})
    ids = pat.setdefault("ids", [])
    have = {(x.get("kind"), identity.normalise_id(x.get("value"))) for x in ids if isinstance(x, dict)}
    new = []
    for e in encounters or []:
        num = e.get("number")
        kind = "ip_no" if e.get("kind") == "IP" else "op_no"
        if num and (kind, identity.normalise_id(num)) not in have:
            new.append({"kind": kind, "value": num, "from": source, **({"registration": registration} if registration else {})})
            have.add((kind, identity.normalise_id(num)))
    ids.extend(new)
    return new


def _public_patient(p: dict) -> dict:
    keep = ("id", "ref", "uhid", "registration_kind", "name", "sex", "age", "dob", "abha", "abha_address", "pmjay_id", "registered_on", "last_updated", "matched_on")
    return {k: p.get(k) for k in keep if k in p}


def _client():
    c = his_client.client()
    if c is None:
        raise HISCaseError("No hospital information system is configured (Organisation: HIS connection)", 409)
    return c


def _owner_department(roles: dict, department) -> str:
    """The treating department that owns the new Case File: the doctor's own (the one given when placed in several); a Vaidyx
    admin or the coordinator must name one."""
    treating = (roles or {}).get("treating") or {}
    did = org.department_id(department) if department else None
    if department and not did:
        raise HISCaseError(f"Unknown department: {department}")
    if did and org.department_group(did) != "treating":
        raise HISCaseError(f"{org.department_name(did)} is a supporting department; a Case File is owned by a treating department")
    if did and (did in treating or roles.get("admin") or roles.get("coordinator")):
        return did
    if did:
        raise HISCaseError(f"You are not placed in {org.department_name(did)}", 403)
    if len(treating) == 1:
        return next(iter(treating))
    if treating:
        raise HISCaseError("You are placed in more than one treating department: choose the one that owns this Case File")
    raise HISCaseError("Choose the treating department that owns this Case File", 400 if roles.get("admin") or roles.get("coordinator") else 403)


def _max_updated(*lists) -> str:
    best = ""
    for xs in lists:
        for x in xs or []:
            lu = str((x or {}).get("last_updated") or "")
            if lu > best:
                best = lu
    return best


def _in_window(r: dict, start: str, end: str = "") -> bool:
    day = _day(r.get("issued") or r.get("effective") or r.get("last_updated"))
    if start and day and day < start:
        return False
    if end and day and day >= end:
        return False
    return True


# ---- lookup and creation (3.2) ------------------------------------------------------------------------------------------

async def lookup(identifier: str, window=None) -> dict:
    """What the doctor sees before creating: the registration, its encounters, how many reports fall inside the window and how
    many are older, and the registrations that may be the same person."""
    identifier = str(identifier or "").strip()
    if not identifier:
        raise HISCaseError("Enter a UHID, IP No. or OP No.")
    client = _client()
    try:
        p = await client.find_patient(identifier)
        if not p:
            return {"found": False, "identifier": identifier, "his": client.label}
        encs = await client.encounters(p["id"])
        reports = await client.reports(p["id"])
    except his_client.HISError as e:
        raise HISCaseError(f"The hospital system did not answer: {e}", 502)
    window = window_from(window)
    start = window_start(window)
    current = [r for r in reports if r.get("current", True)]
    inside = [r for r in current if _in_window(r, start)]
    return {"found": True, "identifier": identifier, "his": client.label, "patient": _public_patient(p),
            "similar": [_public_patient(s) for s in p.get("similar") or []],
            "encounters": [{k: e.get(k) for k in ("kind", "number", "department", "unit", "start", "end", "status")} for e in encs],
            "window": window, "window_start": start, "reports": len(inside), "older": len(current) - len(inside),
            "note": "Possible duplicate or temporary registration: link?" if p.get("similar") else ""}


async def create(identifier: str, protocol_id: str, setting: str, hospital_level: str, board_date: str, window, user: str, roles: dict,
                 department=None, case_id: str = "", cancer_name=None) -> dict:
    """Create the Case File from the HIS registration and start the first fetch. Returns {"case", "job"}. `cancer_name`: the cancer as
    the doctor picked or typed it, required under the generic rule (protocol "generic", owner decision R05-Q04), stored and audited."""
    from . import protocol, service
    identifier = str(identifier or "").strip()
    if not identifier:
        raise HISCaseError("Enter a UHID, IP No. or OP No.")
    if not protocol.exists(protocol_id):
        raise HISCaseError(f"Unknown protocol: {protocol_id}")
    if setting and setting not in {x["id"] for x in protocol.settings(protocol_id)}:
        raise HISCaseError(f"Unknown NCG setting for {protocol_id}: {setting}")
    cancer_name = clean_cancer_name(cancer_name, protocol_id)
    hospital_level = hospital_level or (org.load().get("hospital") or {}).get("level") or "essential"
    if hospital_level not in org.LEVELS:
        raise HISCaseError("Hospital level must be essential or optimal")
    if board_date:
        from .docstatus import parse_date
        iso = parse_date(board_date)
        if not iso:
            raise HISCaseError(f"Not a valid board date: {board_date}")
        board_date = iso
    owner = _owner_department(roles, department)
    window = window_from(window)
    client = _client()
    try:
        p = await client.find_patient(identifier)
    except his_client.HISError as e:
        raise HISCaseError(f"The hospital system did not answer: {e}", 502)
    if not p:
        raise HISCaseError(f"No registration in the hospital system matches {identifier}", 404)
    if case_id:
        case_id = store.safe_id(case_id)
        if case_id in config.PROTECTED_CASES:
            raise HISCaseError("That Case File id is protected", 409)
        if store.get_case(case_id):
            raise HISCaseError("Case already exists", 409)
    else:
        case_id = intake.next_case_id()
    # one Case File per patient and cancer (night-v3 item 1.1): the registration's UHID, and the identifier typed when it is a UHID
    uhids = {p["uhid"]} | ({(p.get("matched_on") or {}).get("value")} if isinstance(p.get("matched_on"), dict) and (p["matched_on"].get("kind") or "") == "uhid" else set())
    system = (client.kind, client.label)  # the same hospital system (review Phase 5 minor 3): another system numbers its patients apart
    refuse_duplicate(uhids, protocol_id, cancer_name, user, roles, his=system, via="from_his")  # under the generic rule, two different typed cancers are not the same one
    try:
        encs = await client.encounters(p["id"])
    except his_client.HISError as e:
        raise HISCaseError(f"The hospital system did not answer: {e}", 502)
    others = same_patient_cases(uhids, exclude=case_id, his=system)  # the same patient's other cancers (linked registrations count)
    case = store.create_case(case_id, patient_record(p, encs), protocol_id, board_date, user, setting, hospital_level)
    case["department"] = owner
    if cancer_name:
        case["cancer_name"] = cancer_name
    if others:  # the same patient's other cancer episodes (two primaries, V2 item 5.3): linked both ways, each with its own owner and protocol
        case["linked_cases"] = [{"case_id": o["case_id"], "protocol": o.get("protocol") or "", "department": o.get("department") or "", "linked_at": store.now_iso(),
                                 "reason": "same UHID"} for o in others]
    case["his"] = {"kind": client.kind, "label": client.label, "patient_id": p["id"], "patient_ref": p.get("ref"), "uhid": p["uhid"],
                   "registration_kind": p.get("registration_kind") or "permanent", "matched_on": p.get("matched_on"),
                   "window": window, "window_start": window_start(window), "fetched_at": None, "watermark": "",
                   "similar": [{**_public_patient(s), "linked": False} for s in p.get("similar") or []], "linked": [],
                   "encounters": encs, "orders": [], "referrals": [], "older_available": 0, "fetches": []}
    store.save_case(case)
    store.audit(case_id, {"kind": "case_created", "by": user, "listing": case["listing"]["status"], "protocol": protocol_id, "setting": setting,
                          **({"cancer_name": cancer_name} if cancer_name else {}),
                          "from_his": {"label": client.label, "identifier": identifier, "matched_on": p.get("matched_on"), "uhid": p["uhid"],
                                       "registration_kind": p.get("registration_kind"), "similar": [s.get("uhid") for s in p.get("similar") or []]},
                          "owner": owner, "window": window, "linked_cases": [o["case_id"] for o in others]})
    for o in others:  # the link is recorded on both sides and audited in both Case Files
        full = store.get_case(o["case_id"]) or {}
        if full and not any((l or {}).get("case_id") == case_id for l in full.get("linked_cases") or []):
            full.setdefault("linked_cases", []).append({"case_id": case_id, "protocol": protocol_id, "department": owner, "linked_at": store.now_iso(), "reason": "same UHID"})
            store.save_case(full)
            store.audit(o["case_id"], {"kind": "case_linked", "by": user, "case_id": case_id, "protocol": protocol_id, "department": owner, "reason": "same UHID"})
    if others:
        store.audit(case_id, {"kind": "case_linked", "by": user, "linked": [o["case_id"] for o in others], "reason": "same UHID"})
        from . import service
        for o in others:  # the linked Case File re-checks its gate: with a second cancer, the other site's reports step aside (V2 item 5.3)
            try:
                service.recheck(o["case_id"], user)
            except Exception as e:  # a re-check problem never blocks the new Case File
                log.warning("re-check of the linked Case File %s failed: %s", o["case_id"], e)
    try:
        job = await fetch(case_id, client, start=case["his"]["window_start"], user=user, reason=FIRST)
    except HISCaseError:  # the first fetch failed: no half-made Case File stays behind (a retry would make a second one)
        notify.purge_case(case_id)
        unlink_cases(case_id, user)  # the same patient's other Case Files forget the link too (V2 item 5.3)
        store.delete_case(case_id)
        raise
    return {"case": store.get_case(case_id), "job": job}


def unlink_cases(case_id: str, user: str = "") -> list:
    """A deleted Case File leaves the linked Case Files of the same patient (V2 item 5.3); returns the ids it was linked to."""
    out = []
    for c in store.list_cases():
        links = c.get("linked_cases") or []
        if any((l or {}).get("case_id") == case_id for l in links):
            full = store.get_case(c["case_id"])
            full["linked_cases"] = [l for l in full.get("linked_cases") or [] if (l or {}).get("case_id") != case_id]
            store.save_case(full)
            store.audit(c["case_id"], {"kind": "case_unlinked", "by": user, "case_id": case_id, "reason": "the linked Case File was deleted"})
            out.append(c["case_id"])
    return out


# ---- fetching ----------------------------------------------------------------------------------------------------------

def _existing_refs(case_id) -> dict:
    out = {}
    for d in store.list_docs(case_id):
        h = d.get("his") or {}
        if h.get("document_ref"):
            out[h["document_ref"]] = d["doc_id"]
    return out


def _mark_versions(case_id):
    """Within each HIS report, the newest version is current and the others are history (`superseded`)."""
    by_report = {}
    for d in store.list_docs(case_id):
        h = d.get("his") or {}
        if h.get("id"):
            by_report.setdefault((h.get("registration") or "", h["id"]), []).append(d)
    for key, ds in by_report.items():
        ds.sort(key=lambda d: int((d.get("his") or {}).get("version") or 1))
        newest = ds[-1]
        for d in ds:
            was = d.get("superseded")
            if d is newest:
                if was:
                    d.pop("superseded", None); store.save_doc(case_id, d)
            else:
                mark = {"by_doc": newest["doc_id"], "version": (newest.get("his") or {}).get("version"), "at": store.now_iso()}
                if not was or was.get("by_doc") != mark["by_doc"]:
                    d["superseded"] = mark; store.save_doc(case_id, d)


async def fetch(case_id: str, client, *, since: str = "", start: str = "", end: str = "", patient_id: str = "", registration: str = "",
                user: str = "", reason: str = FIRST) -> dict:
    """Download the report versions of one registration (the Case File's own unless `patient_id` / `registration` name a linked
    one) that fall inside [start, end) and are not in the Case File yet, file them with their HIS metadata and start the
    processing job. Also refreshes encounters, open orders, referrals and the watermark. Returns the job."""
    from . import service
    case = store.get_case(case_id)
    his = case.get("his") or {}
    pid = patient_id or his.get("patient_id")
    linked = bool(patient_id) and patient_id != his.get("patient_id")
    try:
        reports = await client.reports(pid, since or None)
        encs = await client.encounters(pid)
        orders = await client.open_orders(pid)
        refs = await client.referrals(pid)
    except his_client.HISError as e:
        store.audit(case_id, {"kind": "his_fetch_failed", "reason": reason, "by": user, "error": str(e)[:300]})
        raise HISCaseError(f"The hospital system did not answer: {e}", 502)
    async with store.lock(case_id):  # edits made while the HIS answered (listing, board date, another fetch) are not overwritten (review M10)
        case = store.get_case(case_id)
        learned = learn_encounters(case, encs, "his_link" if linked else "his", registration)  # before any record is read: its OP / IP No. must be known
        if learned:
            store.save_case(case)
            store.audit(case_id, {"kind": "patient_ids_learned", "ids": learned, "by": user, "source": "his", "registration": registration or None})
    have = _existing_refs(case_id)
    added, updated, skipped, outside_window, errors = [], [], [], [], []
    for r in sorted(reports, key=lambda x: (str(x.get("id")), int(x.get("version") or 1))):
        if not _in_window(r, start, end):
            outside_window.append((r.get("document_ref"), _day(r.get("issued") or r.get("effective") or r.get("last_updated")))); continue
        if r.get("document_ref") in have:
            # the same version came back: changed in the HIS since it was fetched (a signature added, a status change, a re-rendered
            # PDF) its metadata and, when the bytes changed, its file are refreshed and it is read again; otherwise nothing to do
            try:
                changed = await _refresh_doc(case_id, have[r["document_ref"]], r, client)
            except his_client.HISError as e:
                errors.append({"document_ref": r.get("document_ref"), "error": str(e)[:200], "last_updated": r.get("last_updated")}); continue
            (updated if changed else skipped).append(r["document_ref"]); continue
        try:
            d = await client.document(r["document_ref"])
        except his_client.HISError as e:
            errors.append({"document_ref": r.get("document_ref"), "error": str(e)[:200], "last_updated": r.get("last_updated")}); continue
        dup = store.find_duplicate(case_id, d["content"])
        if dup:
            skipped.append(r["document_ref"]); continue
        from pathlib import Path
        rp = rel_path(r, Path(d.get("filename") or "x.pdf").suffix.lower() or ".pdf")
        if registration:
            rp = f"{HIS_FOLDER}/{_slug(registration)}/" + rp[len(HIS_FOLDER) + 1:]
        doc = store.add_document_file(case_id, d.get("filename") or rp.rsplit("/", 1)[-1], d["content"], rp)
        doc["source"] = "his"
        doc["his"] = {k: r.get(k) for k in ("id", "version", "kind", "ref", "document_ref", "current", "title", "code", "category", "doc_type", "doc_type_basis",
                                             "status", "issued", "effective", "encounter_ref", "encounter_number", "encounter_kind", "accession", "order_ref",
                                             "performer_department", "reported_by", "signature", "observations", "imaging_study_ref", "conclusion",
                                             "amendment_note", "last_updated")}
        doc["his"]["label"] = client.label
        doc["his"]["fetched_at"] = store.now_iso()
        doc["his"]["fetch_reason"] = reason
        doc["his"]["document_sha256"] = (r.get("document") or {}).get("sha256") or d.get("sha256")
        if registration:
            doc["his"]["registration"] = registration
        dept = org.department_id(r.get("performer_department") or "")
        if dept:
            doc["department"] = dept  # the department that produced the record: a Level 2 gap goes back to its desk (Phase 2 review note)
        store.save_doc(case_id, doc)
        have[r["document_ref"]] = doc["doc_id"]
        added.append(doc["doc_id"])
        store.audit(case_id, {"kind": "document_added", "doc_id": doc["doc_id"], "file": rp, "by": user, "source": "his", "his": {
            "id": r.get("id"), "version": r.get("version"), "status": r.get("status"), "accession": r.get("accession"), "encounter": r.get("encounter_number"),
            "signed": bool(r.get("signature")), "document_ref": r.get("document_ref"), "sha256": doc["his"]["document_sha256"]}})
    for did in updated:
        store.audit(case_id, {"kind": "document_updated_from_his", "doc_id": have.get(did) or did, "document_ref": did, "by": user, "reason": reason})
    _mark_versions(case_id)
    # the watermark of this registration: the newest report version seen, never past a version that failed to download (it is asked for again; review M1 / M2)
    wm = _max_updated(reports)
    failed_at = [str(e.get("last_updated") or "") for e in errors if e.get("last_updated")]
    if failed_at:
        wm = min([wm] + failed_at)
    async with store.lock(case_id):
        case = store.get_case(case_id)
        his = case.setdefault("his", {})
        if not linked:
            his["encounters"] = encs
            his["orders"] = orders
            his["referrals"] = refs
            if reason == FIRST:
                his["older_available"] = len([x for x in outside_window if x[0]])
            elif reason == OLDER:
                his["older_available"] = len([x for x in outside_window if x[0] and x[1] and start and x[1] < start]) if start else 0
            if wm and (wm > (his.get("watermark") or "") or failed_at):
                his["watermark"] = wm
        else:  # a linked registration: its encounters, open orders and watermark are kept beside the main registration's, labelled with it
            his.setdefault("linked_encounters", {})[patient_id] = [{**e, "registration": registration} for e in encs]
            his.setdefault("linked_orders", {})[patient_id] = orders
            wms = his.setdefault("linked_watermarks", {})
            if wm and (wm > (wms.get(patient_id) or "") or failed_at):
                wms[patient_id] = wm
        his["fetched_at"] = store.now_iso()
        his.setdefault("fetches", []).append({"at": his["fetched_at"], "reason": reason, "by": user, "since": since or None, "start": start or None, "end": end or None,
                                              "reports": len(reports), "added": len(added), "updated": len(updated), "skipped": len(skipped), "outside_window": len(outside_window),
                                              "errors": len(errors), "registration": registration or None})
        his["fetches"] = his["fetches"][-50:]
        store.save_case(case)
    store.audit(case_id, {"kind": "his_fetch", "reason": reason, "by": user, "since": since or None, "start": start or None, "end": end or None, "registration": registration or None,
                          "reports": len(reports), "added": added, "updated": [have.get(x) for x in updated], "skipped": len(skipped), "outside_window": len(outside_window), "errors": errors,
                          "watermark": wm or None, "open_orders": [o.get("accession") or o.get("id") for o in orders]})
    open_before = [a["id"] for a in store.get_state(case_id).get("actions", []) if a.get("source") == "pre_authorization" and a.get("status") != "completed"]
    todo = added + [have[x] for x in updated]
    job = service._job(case_id, len(todo), todo)
    job["his"] = {"reason": reason, "reports": len(reports), "added": len(added), "updated": len(updated), "skipped": len(skipped), "outside_window": len(outside_window), "errors": errors}
    job["open_before"] = open_before
    if reason != FIRST:
        job["refetch"] = True
    service._save_job(job)
    # new documents are read in full; a refreshed one whose bytes did not change keeps its pages (from_stored) and gets the overlay and the extraction again
    job["task"] = asyncio.get_event_loop().create_task(service.process_docs(case_id, todo, job, from_stored=True))
    return job


_HIS_KEYS = ("id", "version", "kind", "ref", "document_ref", "current", "title", "code", "category", "doc_type", "doc_type_basis", "status", "issued", "effective",
             "encounter_ref", "encounter_number", "encounter_kind", "accession", "order_ref", "performer_department", "reported_by", "signature", "observations",
             "imaging_study_ref", "conclusion", "amendment_note", "last_updated")


async def _refresh_doc(case_id: str, doc_id: str, r: dict, client) -> bool:
    """A report version already in the Case File came back from the HIS: when its `last_updated`, status or signature changed, its HIS
    metadata is replaced (and its file re-downloaded when the HIS sha256 differs, with the stored pages dropped so it is read again).
    Returns True when something changed."""
    doc = store.get_doc(case_id, doc_id)
    if not doc:
        return False
    h = doc.get("his") or {}
    new_sha = (r.get("document") or {}).get("sha256") or ""
    material = (r.get("status") != h.get("status") or bool(r.get("signature")) != bool(h.get("signature"))
                or (bool(r.get("signature")) and (r.get("signature") or {}).get("verification_status") != (h.get("signature") or {}).get("verification_status"))
                or (new_sha and new_sha != (h.get("document_sha256") or "")))
    if not material:
        if str(r.get("last_updated") or "") > str(h.get("last_updated") or "") or r.get("current") != h.get("current"):
            # bookkeeping only (the version was superseded, its timestamp moved): the metadata follows, nothing is read again
            doc["his"] = {**h, "current": r.get("current"), "last_updated": r.get("last_updated") or h.get("last_updated")}
            store.save_doc(case_id, doc)
        return False
    if new_sha and new_sha != (h.get("document_sha256") or doc.get("sha256")):
        d = await client.document(r["document_ref"])
        path = store.original_path(case_id, doc_id)
        path.write_bytes(d["content"])
        import hashlib
        doc["sha256"] = hashlib.sha256(d["content"]).hexdigest(); doc["size"] = len(d["content"])
        doc.pop("pages", None); doc.pop("classification", None); doc.pop("identity_read", None)  # the text changed: read it again
        doc["his_document_sha256_before"] = h.get("document_sha256")
    doc["his"] = {**h, **{k: r.get(k) for k in _HIS_KEYS}, "document_sha256": new_sha or h.get("document_sha256"), "refreshed_at": store.now_iso()}
    doc["state"] = "queued"; doc.pop("error", None)
    store.save_doc(case_id, doc)
    return True


async def fetch_file(case_id: str, doc: dict, user: str = "") -> "Path":
    """The PDF of a hospital-system record fetched live when its file is missing on disk (V2 item 6.3: "any HIS record opens in the
    document viewer, fetched live if needed"): the same DocumentReference, the bytes checked against the sha256 recorded at the first
    fetch (HISCaseError when they differ: never a different file under a verified record). Audited."""
    from pathlib import Path
    if case_id in config.PROTECTED_CASES:  # never written to (project rules)
        raise HISCaseError("This Case File is never written to", 403)
    h = doc.get("his") or {}
    ref = h.get("document_ref")
    if not ref:
        raise HISCaseError("This record did not come from the hospital system; its file cannot be fetched", 404)
    d = await _client().document(ref)
    want = str(doc.get("sha256") or h.get("document_sha256") or "").lower()  # the bytes read and quoted at the first fetch win over the hash the HIS declared
    got = hashlib.sha256(d["content"]).hexdigest()
    if not want or got != want:  # no recorded hash: nothing can vouch for the file (Phase 6 review)
        store.audit(case_id, {"kind": "document_fetch_live_failed", "doc_id": doc["doc_id"], "by": user,
                              "reason": "sha256 differs from the record fetched first" if want else "no sha256 recorded for this record", "expected": want, "got": got})
        raise HISCaseError("The hospital system returned a file that differs from the record this Case File holds; ask the department" if want
                           else "This record has no recorded hash, so a file fetched now cannot be matched to it; ask the department", 409)
    dd = Path(config.CASES_DIR) / store.safe_id(case_id) / "docs" / store.safe_id(doc["doc_id"])
    dd.mkdir(parents=True, exist_ok=True)
    p = dd / f"original{doc.get('ext') or Path(d.get('filename') or 'x.pdf').suffix.lower() or '.pdf'}"
    p.write_bytes(d["content"])
    store.audit(case_id, {"kind": "document_fetched_live", "doc_id": doc["doc_id"], "by": user, "document_ref": ref, "sha256": got, "bytes": len(d["content"])})
    return p


def _his_case(case_id) -> tuple:
    case = store.get_case(case_id)
    if not case:
        raise HISCaseError("Case not found", 404)
    if not case.get("his"):
        raise HISCaseError("This Case File was not created from the hospital system", 409)
    return case, case["his"]


async def refetch(case_id: str, user: str) -> dict:
    """Re-fetch from the HIS (3.5): only versions changed since the watermark; the gate re-checks when the job finishes."""
    case, his = _his_case(case_id)
    client = _client()
    job = await fetch(case_id, client, since=his.get("watermark") or "", start=his.get("window_start") or "", user=user, reason=REFETCH)
    for reg in his.get("linked") or []:  # linked registrations move too, each from its own watermark
        try:
            await fetch(case_id, client, since=(his.get("linked_watermarks") or {}).get(reg["id"]) or "", start=his.get("window_start") or "",
                        patient_id=reg["id"], registration=reg["uhid"], user=user, reason=REFETCH)
        except HISCaseError:
            pass
    return job


AUTOMATIC = "Vaidyx (automatic)"  # the scheduler's half-hourly re-fetch (18 Oct)


def _archived(case: dict) -> bool:
    return bool(case.get("archived")) or (case.get("listing") or {}).get("status") == "archived" or case.get("status") == "archived"


def _decided(case: dict, st: dict, today: str) -> bool:
    """A Case File whose board decision is recorded and whose board date is not ahead any more: nothing to re-fetch for."""
    recs = [b for b in (st or {}).get("board_records") or [] if isinstance(b, dict) and (b.get("outcome_type") or "decision") == "decision"]
    if not recs:
        return False
    bd = str(case.get("board_date") or "")[:10]
    return not bd or bd <= today


def active_his_cases(today: str = "") -> list[str]:
    """The HIS-connected Case Files the scheduler keeps fresh: not archived, not protected, not decided (18 Oct)."""
    today = today or store.now_iso()[:10]
    out = []
    for c in store.list_cases():
        cid = c.get("case_id")
        if not cid or cid in config.PROTECTED_CASES or not c.get("his") or _archived(c):
            continue
        if _decided(c, store.get_state(cid), today):
            continue
        out.append(cid)
    return out


async def refetch_all_active(user: str = AUTOMATIC, skip=(), wait: bool = True) -> dict:
    """Re-fetch every active HIS-connected Case File (the scheduler's job): each one from its watermark, by `user`; `skip` names Case
    Files with a job already running. With wait=True the processing job of each fetch is awaited, so the caller's loop finishes the
    work. Returns {case_id: {"job", "added", "updated"} | {"error"}}; a missing HIS connection stops the run after the first Case File."""
    out = {}
    for cid in active_his_cases():
        if cid in skip:
            out[cid] = {"skipped": "job running"}
            continue
        try:
            job = await refetch(cid, user)
        except HISCaseError as e:
            out[cid] = {"error": str(e)}
            if e.status == 409 and "No hospital information system" in str(e):
                break
            continue
        except Exception as e:  # one Case File's failure never stops the others
            out[cid] = {"error": f"{e.__class__.__name__}: {str(e)[:200]}"}
            continue
        task = job.get("task")
        if wait and task is not None:
            try:
                await task
            except Exception as e:
                out[cid] = {"job": job.get("id"), "error": f"{e.__class__.__name__}: {str(e)[:200]}"}
                continue
        h = job.get("his") or {}
        out[cid] = {"job": job.get("id"), "added": h.get("added", 0), "updated": h.get("updated", 0)}
    return out


async def fetch_older(case_id: str, window, user: str) -> dict:
    """Widen the fetch window without starting over: records dated before the current start and on or after the new one."""
    case, his = _his_case(case_id)
    window = window_from(window)
    new_start = window_start(window)
    old_start = his.get("window_start") or ""
    if old_start and new_start and new_start >= old_start:
        raise HISCaseError(f"The window already starts at {dmy(old_start)}; choose an earlier start or all records")
    if not old_start:
        raise HISCaseError("Every record is already fetched (the window has no start)")
    client = _client()
    his["window"], his["window_start"] = window, new_start
    store.save_case(case)
    store.audit(case_id, {"kind": "his_window_widened", "by": user, "from": old_start, "to": new_start or "all", "window": window})
    job = await fetch(case_id, client, start=new_start, end=old_start, user=user, reason=OLDER)
    for reg in his.get("linked") or []:  # linked registrations widen too
        try:
            await fetch(case_id, client, start=new_start, end=old_start, patient_id=reg["id"], registration=reg["uhid"], user=user, reason=OLDER)
        except HISCaseError:
            pass
    return job


async def link_registration(case_id: str, uhid: str, user: str, reason: str = "") -> dict:
    """A person links a possible duplicate or temporary registration (never automatic): the Case File learns its UHID, its records
    are fetched labelled with that registration, and the link is audited."""
    case, his = _his_case(case_id)
    uhid = str(uhid or "").strip()
    sim = next((s for s in his.get("similar") or [] if s.get("uhid", "").upper() == uhid.upper()), None)
    if not sim:
        raise HISCaseError(f"{uhid} is not among the registrations listed for this Case File", 404)
    if sim.get("linked"):
        raise HISCaseError(f"{uhid} is already linked", 409)
    client = _client()
    sim["linked"] = True; sim["linked_by"] = user; sim["linked_at"] = store.now_iso(); sim["reason"] = reason
    his.setdefault("linked", []).append({"id": sim["id"], "uhid": sim["uhid"], "registration_kind": sim.get("registration_kind"), "by": user, "at": sim["linked_at"]})
    pat = case.setdefault("patient", {})
    ids = pat.setdefault("ids", [])
    if not any(identity.normalise_id(x.get("value")) == identity.normalise_id(uhid) for x in ids if isinstance(x, dict)):
        ids.append({"kind": "uhid", "value": sim["uhid"], "from": "his_link", "registration_kind": sim.get("registration_kind")})
    store.save_case(case)
    store.audit(case_id, {"kind": "registration_linked", "by": user, "uhid": sim["uhid"], "registration_kind": sim.get("registration_kind"), "reason": reason})
    return await fetch(case_id, client, start=his.get("window_start") or "", patient_id=sim["id"], registration=sim["uhid"], user=user, reason=LINK)


def unlink_registration(case_id: str, uhid: str, user: str, reason: str = "") -> dict:
    """Undo a link (review M8): the registration's records leave the Case File, the identifiers learned from it are forgotten, its
    encounters, orders and watermark are dropped; audited. The caller re-checks the gate."""
    case, his = _his_case(case_id)
    uhid = str(uhid or "").strip()
    sim = next((s for s in his.get("similar") or [] if s.get("uhid", "").upper() == uhid.upper()), None)
    if not sim or not sim.get("linked"):
        raise HISCaseError(f"{uhid} is not linked to this Case File", 404)
    removed = []
    for d in store.list_docs(case_id):
        if (d.get("his") or {}).get("registration", "").upper() == uhid.upper():
            intake.unlearn_ids(case_id, d["doc_id"], user)
            store.delete_document(case_id, d["doc_id"])
            removed.append(d["doc_id"])
            store.audit(case_id, {"kind": "document_deleted", "doc_id": d["doc_id"], "file": d.get("rel_path"), "by": user, "reason": f"registration {uhid} unlinked"})
    pat = case.setdefault("patient", {})
    before = pat.get("ids") or []
    keep = [x for x in before if not (isinstance(x, dict) and (x.get("registration", "").upper() == uhid.upper()
                                                             or (x.get("kind") == "uhid" and identity.normalise_id(x.get("value")) == identity.normalise_id(uhid))))]
    forgotten = [x for x in before if x not in keep]
    pat["ids"] = keep
    sim["linked"] = False; sim["unlinked_by"] = user; sim["unlinked_at"] = store.now_iso(); sim["unlink_reason"] = reason
    pid = sim.get("id")
    his["linked"] = [x for x in his.get("linked") or [] if x.get("uhid", "").upper() != uhid.upper()]
    for key in ("linked_encounters", "linked_orders", "linked_watermarks"):
        (his.get(key) or {}).pop(pid, None)
    store.save_case(case)
    store.audit(case_id, {"kind": "registration_unlinked", "by": user, "uhid": uhid, "reason": reason, "removed_documents": removed, "forgotten_ids": forgotten})
    return {"removed_documents": len(removed), "forgotten_ids": forgotten, "uhid": uhid}


def after_refetch(case_id: str, job: dict):
    """After a re-fetch job ran the gate: requests that closed are reported to the owning department (and the audit), once; the notice
    also says when the Case File summary compiled earlier went stale (V2 item 4.4)."""
    from . import rules  # local: rules is the gate, his_case the fetch; neither needs the other at import time
    try:
        case = store.get_case(case_id) or {}
        st = store.get_state(case_id)
        before = set(job.get("open_before") or [])
        closed = [a for a in st.get("actions", []) if a["id"] in before and a.get("status") == "completed"]
        opened = [a for a in st.get("actions", []) if a.get("source") == "pre_authorization" and a.get("status") != "completed" and a["id"] not in before]
        summ = (st.get("artefacts") or {}).get("summary")  # the Case File summary compiled earlier goes stale when the re-fetch changed the Case File (V2 item 4.4)
        stale = rules.stale_reason(summ["signature"], rules.case_signature(case_id, st)) if isinstance(summ, dict) and summ.get("signature") else ""
        job["refetch_result"] = {"closed": [a["id"] for a in closed], "opened": [a["id"] for a in opened], "summary_stale": stale}
        store.audit(case_id, {"kind": "his_refetch_checked", "job": job.get("id"), "closed": [{"id": a["id"], "label": a.get("label")} for a in closed],
                              "opened": [{"id": a["id"], "label": a.get("label")} for a in opened], "added": (job.get("his") or {}).get("added", 0)})
        owner = case.get("department")
        patient = (case.get("patient") or {}).get("name") or case_id
        if owner and (closed or (job.get("his") or {}).get("added") or stale):
            what = (f"{len(closed)} request(s) closed: " + "; ".join(a.get("label") or a["id"] for a in closed)) if closed else "no request closed"
            g = st.get("gate") or {}
            notify.notify({"department": owner}, "request_closed", case_id, f"Re-fetch from the HIS for {patient} ({case_id}): {what}",
                          f"{(job.get('his') or {}).get('added', 0)} new or changed record(s) processed; Pre-Authorization {g.get('satisfied')}/{g.get('total')} met"
                          + ("; the Case File is ready." if g.get("passed") else ".")
                          + (" The Case File summary compiled earlier is stale: regenerate it before the board." if stale else ""),
                          refetch=True, closed=[a["id"] for a in closed], summary_stale=stale)
    except Exception as e:  # never fail the job for the notice
        store.audit(case_id, {"kind": "error", "where": "after_refetch", "error": f"{e.__class__.__name__}: {str(e)[:200]}"})


# ---- views ------------------------------------------------------------------------------------------------------------------

def doc_view(d: dict) -> dict:
    """The HIS and outside-report fields of a document for the Case File view (no PDF, no observations)."""
    out = {}
    h = d.get("his")
    if h:
        out["his"] = {k: h.get(k) for k in ("id", "version", "current", "status", "issued", "encounter_number", "encounter_kind", "accession", "performer_department",
                                              "reported_by", "registration", "imaging_study_ref", "label", "fetch_reason", "amendment_note", "doc_type", "title")}
        out["his"]["signed"] = bool(h.get("signature")) and str((h.get("signature") or {}).get("verification_status", "")).lower() == "verified"
        out["his"]["signature"] = {k: (h.get("signature") or {}).get(k) for k in ("signer", "signed_at", "ca", "serial", "verification_status")} if h.get("signature") else None
    if d.get("superseded"):
        out["superseded"] = d["superseded"]
    if d.get("outside"):
        out["outside"] = d["outside"]
    if d.get("his_flags"):
        out["his_flags"] = d["his_flags"]
    if d.get("his_checks"):
        out["his_checks"] = len(d["his_checks"])
    if d.get("identity_confirmed_by"):
        out["identity_confirmed_by"] = d["identity_confirmed_by"]
    return out


def flags(case_id: str, docs=None) -> list:
    """Every HIS value the report text does not carry, across the Case File (points for review)."""
    out = []
    for d in docs if docs is not None else store.list_docs(case_id):
        for f in d.get("his_flags") or []:
            c = d.get("classification") or {}
            out.append({**f, "doc_id": d["doc_id"], "doc_title": c.get("title") or d.get("filename"), "accession": (d.get("his") or {}).get("accession")})
    return out


def points(case_id: str, state=None) -> list:
    """The HIS mismatches as points for review for the summary (cited to the report, never a fact)."""
    from . import rules
    out = []
    for d in rules.case_docs(case_id, state):
        for f in d.get("his_flags") or []:
            c = d.get("classification") or {}
            txt = f["text"] + f" (HIS Observation of {c.get('title') or d.get('filename')}, not shown as a fact)."
            out.append({"text": txt, "citations": [], "system": True, "kind": "his_mismatch", "doc_id": d["doc_id"]})
    return out


def encounter_groups(case: dict, docs: list) -> list:
    """The Case File's records grouped by OP visit and IP admission (3.4), newest encounter first; records with no encounter and
    outside reports in their own groups. An OP visit dated before an IP admission is labelled pre-admission OPD."""
    his = case.get("his") or {}
    encs = list(his.get("encounters") or []) + [e for es in (his.get("linked_encounters") or {}).values() for e in es]  # linked registrations too
    admissions = [e for e in encs if e.get("kind") == "IP" and e.get("start")]
    first_adm = min((_day(e["start"]) for e in admissions), default="")
    groups = {}
    for e in encs:
        g = {"key": e.get("number"), "kind": e.get("kind"), "number": e.get("number"), "department": e.get("department"), "unit": e.get("unit"), "start": _day(e.get("start")),
             "end": _day(e.get("end")), "status": e.get("status"), "ward_history": e.get("ward_history") or [], "consultant": (e.get("consultant") or {}).get("name"),
             "pmjay_preauth": e.get("pmjay_preauth"), "docs": []}
        g["label"] = ("IP admission " if e.get("kind") == "IP" else "OP visit ") + str(e.get("number") or "")
        if e.get("kind") == "OP" and first_adm and g["start"] and g["start"] < first_adm:
            g["pre_admission"] = True
        if e.get("registration"):
            g["registrations"] = [e["registration"]]
        groups[e.get("number")] = g
    other = {"key": "his_other", "kind": "HIS", "label": "Other hospital records", "docs": [], "start": ""}
    outside = {"key": "outside", "kind": "outside", "label": "Outside reports (uploaded)", "docs": [], "start": ""}
    uploads = {"key": "uploads", "kind": "upload", "label": "Uploaded documents", "docs": [], "start": ""}
    for d in docs:
        h = d.get("his") or {}
        if h:
            g = groups.get(h.get("encounter_number"))
            (g or other)["docs"].append(d["doc_id"])
            if g and h.get("registration"):
                g.setdefault("registrations", [])
                if h["registration"] not in g["registrations"]:
                    g["registrations"].append(h["registration"])
        elif d.get("outside"):
            outside["docs"].append(d["doc_id"])
        else:
            uploads["docs"].append(d["doc_id"])
    out = sorted(groups.values(), key=lambda g: g.get("start") or "", reverse=True)
    return out + [g for g in (other, outside, uploads) if g["docs"]]


def public(case: dict) -> dict:
    """The HIS block of a Case File for the UI (everything the doctor needs; no token, no PDFs)."""
    his = case.get("his")
    if not his:
        return None
    out = {k: his.get(k) for k in ("kind", "label", "uhid", "registration_kind", "matched_on", "window", "window_start", "fetched_at", "watermark", "similar", "linked",
                                   "older_available", "orders", "referrals", "same_uhid_case")}
    out["window_label"] = window_label(his.get("window") or {})
    out["encounters"] = [{k: e.get(k) for k in ("kind", "number", "department", "unit", "start", "end", "status", "ward_history", "pmjay_preauth", "registration")} | {"consultant": (e.get("consultant") or {}).get("name")}
                         for e in list(his.get("encounters") or []) + [x for es in (his.get("linked_encounters") or {}).values() for x in es]]
    out["fetches"] = (his.get("fetches") or [])[-5:]
    out["unlinked"] = [s for s in his.get("similar") or [] if not s.get("linked")]
    return out
