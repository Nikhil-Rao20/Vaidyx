"""Specialty helpers (18 Oct, SPEC 3.5): six cards, one per agent role (Radiology, Pathology, Medical Oncology, Surgical Oncology,
Radiation Oncology, Nuclear Medicine), each "<Specialty> records check": a brief prepared from the records and the specialty's guideline
pack (the five heads at the ready mark through ready_hook, Nuclear Medicine and any refresh on click), then a chat thread with that helper
(agents.ask). All from records and guideline points, never an opinion: the hard rules live in agents.py. Brief status comes from
state.artefacts.brief_<role> (none / preparing / ready / stale by the Case File signature); the helper chats are saved per role in
cases/<id>/helper_chats.json and shared with the team."""
import asyncio
import logging
import re
import threading
import time
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


def title(role) -> str:
    """The agent's title on the Case File (night-v3 item 6.5, owner decision D2): "<Department>, AI agent", support only, never a member."""
    return f"{agents.ROLES[role]['department']}, AI agent"


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
           # "Reviewed" (the name goes beside it), "Flagged for correction by Dr <name>" or "AI draft, not reviewed" (Phase 9 review E, I2)
           "label": "Reviewed" if rv.get("status") == "reviewed" else review_label(rv)}
    if rv.get("status") == "reviewed":
        out["reviewed_by"] = rv.get("by")
        out["reviewed_by_name"] = _name(rv.get("by"))  # the reviewer's display name beside the login (review 9 C, M11)
    elif rv.get("status") == "flagged":
        out["flagged_by"] = rv.get("by")
        out["flagged_by_name"] = _name(rv.get("by"))
    return out


_TITLED = re.compile(r"^(dr|prof)\.?\s", re.I)  # a word, so "Drishti Rao" is not read as titled (Phase 9 review E, M8)


def dr_name(name) -> str:
    """"Dr <name>" unless the name already starts with the word Dr or Prof ("Dr Rao", "Dr. Rao", "Prof Iyer"); "" for none."""
    n = str(name or "").strip()
    if not n:
        return ""
    return n if _TITLED.match(n) else f"Dr {n}"


def reviewer(user, name_of=None) -> str:
    """The reviewer as a line names it: "Dr <display name>", or the login as it is when no display name is known."""
    if not user:
        return ""
    name = str((name_of or _name)(user) or "").strip()
    return dr_name(name) if name and name != str(user) else str(user)


def review_label(rv, name_of=None) -> str:
    """The review status of an AI artefact in words: "Reviewed by Dr <name>", "Flagged for correction by Dr <name>" (a doctor flagged
    it), else "AI draft, not reviewed". Shown on the Case File, the meeting tiles and spoken with "Present your points"."""
    rv = rv if isinstance(rv, dict) else {}
    who = reviewer(rv.get("by"), name_of)
    if rv.get("status") == "reviewed":
        return f"Reviewed by {who}" if who else "Reviewed"
    if rv.get("status") == "flagged":
        return f"Flagged for correction by {who}" if who else "Flagged for correction"
    return "AI draft, not reviewed"


def _name(user) -> str:
    """The display name of a login (the profile store, else org.json, else the login itself)."""
    if not user:
        return ""
    try:
        from .slots import display_name
        return display_name(user) or str(user)
    except Exception:
        return str(user)


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
    hook = _ready_hook_queue(case_id)
    out = []
    for role in ROLES:
        art = _artefact(st, role)
        queued = role in hook and not agents.fresh(art, sig)  # the ready mark's run will write it (18 Oct, e2e: these showed "none" meanwhile)
        b = brief_view(art, sig, (case_id, role) in PREPARING or queued)
        if queued:
            b["message"] = "Being prepared from the records" if hook[role] == "running" else "Queued at the ready mark: prepared after the summary, one head at a time"
            b["queued"] = hook[role] != "running"
        thread = [m for m in chats.get(role) or [] if isinstance(m, dict)]
        out.append({"role": role, "label": label(role), "department": agents.ROLES[role]["department"], "head": role in HEADS,
                    "brief": b, "job": PREPARING.get((case_id, role)),
                    "thread_count": len(chats.get(role) or []), "prepare_allowed": allowed, "prepared_at_ready": role in HEADS,
                    # night-v3 item 6.5: the Case File's "Specialty agents" (the title, the counts on the Overview card's chips)
                    "title": title(role), "points_count": len(b.get("points_for_review") or []), "not_documented_count": len(b.get("not_documented") or []),
                    "meeting_exchanges": sum(1 for m in thread if str(m.get("source") or "").startswith("meeting:")),
                    "prepared_at": b.get("at") if b.get("status") in ("ready", "stale") else None})
    return out


def _ready_hook_queue(case_id) -> dict:
    """{role: "running" | "queued"} for the heads the ready hook still has to prepare for this Case File ({} when it is not running)."""
    try:
        from . import ready_hook
        run = ready_hook.RUNNING.get(case_id)
    except Exception:
        return {}
    if not run:
        return {}
    step = run.get("step") or ""
    heads = list(ready_hook.HEADS)
    start = heads.index(step) if step in heads else 0  # waiting or the summary: every head is still to come
    return {r: ("running" if r == step else "queued") for r in heads[start:]}


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


def prepare_all(case_id, user) -> dict:
    """"Prepare all" on the Case File (night-v3 item 6.5): one brief job per role that has no brief standing for the Case File, run one
    after the other in the background (one reasoner, as the ready hook does), each job pollable at GET /jobs/{id} and each role shown as
    preparing meanwhile. A brief that still stands, a preparation already running and a head the ready hook is still to prepare are left
    as they are. Returns {helpers: [{role, status: preparing|ready|queued, job}], started}."""
    from . import service
    st = store.get_state(case_id)
    sig = rules.case_signature(case_id, st)
    hook = _ready_hook_queue(case_id)
    out, todo = [], []
    with _lock:
        for role in ROLES:
            jid = PREPARING.get((case_id, role))
            if jid:
                out.append({"role": role, "status": "preparing", "job": jid})
            elif role in hook:
                out.append({"role": role, "status": "queued", "job": None})
            elif agents.fresh(_artefact(st, role), sig):
                out.append({"role": role, "status": "ready", "job": None})
            else:
                job = _job(case_id, role, user, False)
                PREPARING[(case_id, role)] = job["id"]
                todo.append((role, job))
                out.append({"role": role, "status": "preparing", "job": job["id"]})
    for role, job in todo:
        store.audit(case_id, {"kind": "helper_prepare", "role": role, "by": user, "job": job["id"], "refresh": False, "all": True})

    async def run():
        for i, (role, job) in enumerate(todo):
            try:
                job["started"] = time.time()
                await _prepare(case_id, role, job, user)
            except BaseException:  # cancelled: the roles still waiting must not stay "preparing"
                for r, j in todo[i + 1:]:
                    PREPARING.pop((case_id, r), None)
                    j.update(state="failed", error="Stopped before it started")
                    service._save_job(j)
                raise
    if todo:
        task = asyncio.get_running_loop().create_task(run())
        TASKS.add(task)
        task.add_done_callback(TASKS.discard)
    return {"helpers": out, "started": len(todo)}


def _public(m, sig_hash) -> dict:
    stale = bool(m.get("signature") and sig_hash and m["signature"] != sig_hash)
    return {**{k: m.get(k) for k in ("id", "role", "by", "by_name", "at", "question", "status", "statements", "references", "message", "seconds", "dropped_unverified", "category",
                                     "meeting_date", "model")},
            "source": m.get("source") or "case", "stale": stale, "kind": agents.LIVE_LABEL}


def messages(case_id, role) -> list:
    if role not in ROLES:
        raise KeyError(role)
    sig = rules.case_signature(case_id)["hash"]
    return [_public(m, sig) for m in load_chats(case_id).get(role) or []]


def record_exchange(case_id, role, m, source="case") -> dict:
    """Write one exchange onto the role's thread, the one thread per Case File and role that the Case File page and every meeting share
    (night-v3 item 6.3): `source` is "case" or "meeting:<meeting id>" (`m["meeting_date"]` optional); the id, time, asker's name and the
    Case File signature are filled in when missing (the signature is best taken before the model call, as ask() does). Kept to the last
    MAX_MESSAGES of the role. Returns the stored message."""
    if role not in ROLES:
        raise KeyError(role)
    source = str(source or "case")
    if source != "case" and not (source.startswith("meeting:") and len(source) > len("meeting:")):
        raise ValueError("source is case or meeting:<id>")
    m = {**m, "role": role, "source": source}
    m.setdefault("id", "H" + uuid.uuid4().hex[:8])
    m.setdefault("at", store.now_iso())
    if m.get("by") and not m.get("by_name"):
        from .slots import display_name
        m["by_name"] = display_name(m["by"])
    if not m.get("signature"):
        m["signature"] = rules.case_signature(case_id)["hash"]
    with _lock:
        data = load_chats(case_id)
        rows = data.setdefault(role, [])
        rows.append(m)
        if len(rows) > MAX_MESSAGES:
            del rows[:-MAX_MESSAGES]
        save_chats(case_id, data)
    return m


RECORDS_CHANGED = "(The records changed after this answer, so it is left out. Answer again from the documents.)"


def history_for(case_id, role, n=3) -> list:
    """The last n exchanges of the role's shared thread as model history: [{"role": "user", "content": question}, {"role": "assistant",
    "content": the joined statements or the message}]. An exchange written from an earlier Case File signature keeps only its question; its
    answer text is replaced by a fixed line (research 05_board_agents.md section 6.5). History serves follow-ups and is never a fact: every
    new statement still needs its own quote."""
    if role not in ROLES:
        raise KeyError(role)
    if n <= 0:
        return []
    sig = rules.case_signature(case_id)["hash"]
    out = []
    for m in (load_chats(case_id).get(role) or [])[-n:]:
        if not isinstance(m, dict):
            continue
        out.append({"role": "user", "content": m.get("question") or ""})
        if m.get("signature") and m["signature"] != sig:
            out.append({"role": "assistant", "content": RECORDS_CHANGED})
        else:
            out.append({"role": "assistant", "content": " ".join(s.get("text") or "" for s in m.get("statements") or []) or (m.get("message") or "")})
    return out


async def ask(case_id, role, question, user) -> dict:
    """One question to a helper (agents.ask: records and the specialty pack, every statement verified, references only beside a verified
    answer); saved on the role's thread, shared with the team and the meetings. The last three exchanges of the thread go along as history."""
    if role not in ROLES:
        raise KeyError(role)
    q = " ".join(str(question or "").split())[:MAX_QUESTION]
    if not q:
        raise ValueError("Ask a question")
    history = history_for(case_id, role, 3)
    sig = rules.case_signature(case_id)["hash"]
    res = await agents.ask(case_id, role, q, history, user)
    m = {"by": user, "question": q, "status": res.get("status"), "statements": res.get("statements") or [], "references": res.get("references") or [],
         "message": res.get("message") or "", "seconds": res.get("seconds"), "dropped_unverified": res.get("dropped_unverified", 0),
         "category": res.get("category"), "signature": sig, "model": res.get("model") or ""}
    m = record_exchange(case_id, role, m, "case")
    store.audit(case_id, {"kind": "helper_asked", "role": role, "by": user, "message": m["id"], "question": q[:300], "status": m["status"],
                          "statements": len(m["statements"]), "references": len(m["references"])})
    return _public(m, sig)
