"""Specialty helpers (18 Oct, SPEC 3.5): six cards, one per agent role (Radiology, Pathology, Medical Oncology, Surgical Oncology,
Radiation Oncology, Nuclear Medicine), each "<Specialty> records check": a brief prepared from the records and the specialty's guideline
pack (the five heads at the ready mark through ready_hook, Nuclear Medicine and any refresh on click), then a chat thread with that helper
(agents.ask). All from records and guideline points, never an opinion: the hard rules live in agents.py. Brief status comes from
state.artefacts.brief_<role> (none / preparing / ready / stale by the Case File signature); the helper chats are saved per role in
cases/<id>/helper_chats.json and shared with the team."""
import asyncio
import logging
import threading
import uuid

from . import agents, config, rules, store

log = logging.getLogger("tumour_board")

ROLES = ("radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology", "nuclear_medicine")
HEADS = ("radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology")  # prepared at the ready mark; Nuclear Medicine on click
FILE = "helper_chats.json"
MAX_QUESTION = 1000
MAX_MESSAGES = 200
PREPARING: dict = {}  # (case_id, role) -> job id while a preparation runs
TASKS: set = set()
_lock = threading.Lock()


def label(role) -> str:
    return f"{agents.ROLES[role]['department']} records check"


def _artefact(st, role):
    a = (st.get("artefacts") or {}).get(f"brief_{role}")
    return a if isinstance(a, dict) else None


def brief_view(art, sig, preparing=False) -> dict:
    """{status: none|preparing|ready|stale, at, sections, points_for_review, not_documented, reviewed_by?, ...} for one role."""
    if preparing:
        return {"status": "preparing", "at": None, "sections": [], "points_for_review": [], "not_documented": [], "message": "Being prepared from the records"}
    if not art:
        return {"status": "none", "at": None, "sections": [], "points_for_review": [], "not_documented": [], "message": ""}
    why = rules.stale_reason(art.get("signature"), sig) if art.get("signature") else "Prepared before the Case File signature was kept"
    rv = art.get("review") or {}
    out = {"status": "stale" if why else "ready", "at": art.get("generated"), "sections": art.get("sections") or [], "points_for_review": art.get("points_for_review") or [],
           "not_documented": art.get("not_documented") or [], "no_documents": bool(art.get("no_documents")), "message": art.get("message") or "",
           "open_items": art.get("open_items") or [], "model": art.get("model") or "", "removed": len(art.get("removed") or []), "dropped_unverified": art.get("dropped_unverified", 0),
           "references_dropped": art.get("references_dropped", 0), "stale_reason": why, "review": rv.get("status") or "", "pack": art.get("pack"),
           "label": "AI draft, not reviewed" if rv.get("status") in ("ai_draft", None, "") else ("Reviewed" if rv.get("status") == "reviewed" else rv.get("status"))}
    if rv.get("status") == "reviewed":
        out["reviewed_by"] = rv.get("by")
    return out


def load_chats(case_id) -> dict:
    data = store._read_json(store.case_dir(case_id) / FILE, {}) or {}
    return data if isinstance(data, dict) else {}


def save_chats(case_id, data) -> None:
    store._write_json(store.case_dir(case_id) / FILE, data)


def list_helpers(case_id, roles=None) -> list:
    from . import access, org
    st = store.get_state(case_id)
    case = store.get_case(case_id) or {}
    sig = rules.case_signature(case_id, st)
    chats = load_chats(case_id)
    allowed = bool(isinstance(roles, dict) and (roles.get("admin") or org.can(roles, "list_case") or access.may(roles, "upload_to_case", case)
                                                 or (roles.get("resident_treating") and access.owner(case) in roles["resident_treating"])))
    out = []
    for role in ROLES:
        out.append({"role": role, "label": label(role), "department": agents.ROLES[role]["department"], "head": role in HEADS,
                    "brief": brief_view(_artefact(st, role), sig, (case_id, role) in PREPARING), "job": PREPARING.get((case_id, role)),
                    "thread_count": len(chats.get(role) or []), "prepare_allowed": allowed, "prepared_at_ready": role in HEADS})
    return out


def _job(case_id, role, user, refresh):
    from . import service
    job = service._job(case_id, 1, [])
    job.update(kind="helper_brief", role=role, label=label(role), by=user, refresh=bool(refresh))
    service._save_job(job)
    return job


async def _prepare(case_id, role, job, user):
    from . import service
    try:
        res = await agents.prepare(case_id, role)
        b = res.get("brief")
        if b:
            job.update(state="finished", done=1, brief={"generated": b.get("generated"), "no_documents": bool(b.get("no_documents")), "sections": len(b.get("sections") or []),
                                                        "points_for_review": len(b.get("points_for_review") or []), "seconds": b.get("seconds")})
        else:
            job.update(state="failed", error=res.get("error") or "The agent wrote no brief")
    except Exception as e:  # the client polls this job: it must reach a terminal state
        log.exception("helper %s for %s failed", role, case_id)
        job.update(state="failed", error=f"{e.__class__.__name__}: {str(e)[:200]}")
        try:
            store.audit(case_id, {"kind": "error", "where": f"helper {role}", "error": job["error"], "by": user})
        except Exception:
            pass
    finally:
        job["seconds"] = job.get("seconds") or round(__import__("time").time() - job["started"], 1)
        service._save_job(job)
        PREPARING.pop((case_id, role), None)


def prepare(case_id, role, user, refresh=False) -> dict:
    """Start the brief in the background (agents.run_agent through agents.prepare); returns the job to poll at GET /jobs/{id}. A brief that
    still stands for the Case File is reused unless refresh; a preparation already running is returned as it is."""
    if role not in ROLES:
        raise KeyError(role)
    with _lock:
        jid = PREPARING.get((case_id, role))
        if jid:
            return {"job": jid, "status": "preparing", "reused": False, "role": role}
        st = store.get_state(case_id)
        art = _artefact(st, role)
        if art and not refresh and agents.fresh(art, rules.case_signature(case_id, st)):
            job = _job(case_id, role, user, refresh)
            job.update(state="finished", done=1, reused=True, brief={"generated": art.get("generated"), "no_documents": bool(art.get("no_documents")),
                                                                     "sections": len(art.get("sections") or []), "points_for_review": len(art.get("points_for_review") or [])})
            from . import service
            service._save_job(job)
            return {"job": job["id"], "status": "ready", "reused": True, "role": role}
        job = _job(case_id, role, user, refresh)
        PREPARING[(case_id, role)] = job["id"]
    store.audit(case_id, {"kind": "helper_prepare", "role": role, "by": user, "job": job["id"], "refresh": bool(refresh)})
    task = asyncio.get_running_loop().create_task(_prepare(case_id, role, job, user))
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    return {"job": job["id"], "status": "preparing", "reused": False, "role": role}


def _public(m, sig_hash) -> dict:
    stale = bool(m.get("signature") and sig_hash and m["signature"] != sig_hash)
    return {**{k: m.get(k) for k in ("id", "role", "by", "by_name", "at", "question", "status", "statements", "references", "message", "seconds", "dropped_unverified", "category")},
            "stale": stale, "kind": agents.LIVE_LABEL}


def messages(case_id, role) -> list:
    if role not in ROLES:
        raise KeyError(role)
    sig = rules.case_signature(case_id)["hash"]
    return [_public(m, sig) for m in load_chats(case_id).get(role) or []]


async def ask(case_id, role, question, user) -> dict:
    """One question to a helper (agents.ask: records and the specialty pack, every statement verified, references only beside a verified
    answer); saved on the role's thread, shared with the team. The last two exchanges of the thread go along as history."""
    if role not in ROLES:
        raise KeyError(role)
    q = " ".join(str(question or "").split())[:MAX_QUESTION]
    if not q:
        raise ValueError("Ask a question")
    prior = (load_chats(case_id).get(role) or [])[-2:]
    history = []
    for m in prior:
        history.append({"role": "user", "content": m.get("question") or ""})
        history.append({"role": "assistant", "content": " ".join(s.get("text") or "" for s in m.get("statements") or []) or (m.get("message") or "")})
    sig = rules.case_signature(case_id)["hash"]
    res = await agents.ask(case_id, role, q, history, user)
    from .slots import display_name
    m = {"id": "H" + uuid.uuid4().hex[:8], "role": role, "by": user, "by_name": display_name(user), "at": store.now_iso(), "question": q, "status": res.get("status"),
         "statements": res.get("statements") or [], "references": res.get("references") or [], "message": res.get("message") or "", "seconds": res.get("seconds"),
         "dropped_unverified": res.get("dropped_unverified", 0), "category": res.get("category"), "signature": sig, "model": res.get("model") or ""}
    with _lock:
        data = load_chats(case_id)
        rows = data.setdefault(role, [])
        rows.append(m)
        if len(rows) > MAX_MESSAGES:
            del rows[:-MAX_MESSAGES]
        save_chats(case_id, data)
    store.audit(case_id, {"kind": "helper_asked", "role": role, "by": user, "message": m["id"], "question": q[:300], "status": m["status"],
                          "statements": len(m["statements"]), "references": len(m["references"])})
    return _public(m, sig)
