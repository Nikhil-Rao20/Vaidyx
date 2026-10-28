"""Ask this Case File: the shared team chat (18 Oct, SPEC 3.5 right column). Every question is a thread saved in cases/<id>/chats.json with
the answer of qa.ask (statements, each with its verified quotes: document, title, page), who asked, when, the Case File signature the answer
was computed from (a later change marks the thread stale: "records changed since"), and a pin. Visible to the owner's team and the
participating departments with FULL scope, never to a supporting-only doctor and never in REQUESTS scope; "View as" stays general.
Audited "chat_asked" / "chat_pinned". The model is called only through qa.ask."""
import threading
import uuid

from . import config, qa, rules, store

FILE = "chats.json"
MAX_QUESTION = 1000
MAX_THREADS = 500
_lock = threading.Lock()


def _path(case_id):
    return store.case_dir(case_id) / FILE


def load(case_id) -> dict:
    data = store._read_json(_path(case_id), {"threads": []}) or {"threads": []}
    if not isinstance(data.get("threads"), list):
        data["threads"] = []
    return data


def save(case_id, data) -> None:
    store._write_json(_path(case_id), data)


def may_read(roles, scope) -> bool:
    """FULL scope, and a clinical member of the team: a treating consultant or resident, the coordinator or the Vaidyx admin. A
    supporting-only doctor (even a participant) never reads the team chat (plan section 4)."""
    from . import access
    if not isinstance(roles, dict) or roles.get("disabled") or scope != access.FULL:
        return False
    if roles.get("admin") or roles.get("coordinator"):
        return True
    return bool(roles.get("treating") or roles.get("resident_treating"))


def refusal(roles) -> str:
    if isinstance(roles, dict) and (roles.get("supporting") or roles.get("resident")) and not (roles.get("treating") or roles.get("resident_treating")):
        return "The team chat of a Case File is for its treating team and the MDT Coordinator; a supporting department sees the requests it was asked."
    return "The team chat of a Case File is for its treating team and the MDT Coordinator."


def _citations(statements) -> list:
    out = []
    for s in statements or []:
        cites = []
        for c in s.get("citations") or []:
            cites.append({k: c.get(k) for k in ("doc_id", "doc_title", "page", "quote", "start", "end", "date", "status", "source_method", "approximate") if c.get(k) is not None})
        out.append({"text": s.get("text") or "", "citations": cites, **({"flags": s["flags"]} if s.get("flags") else {})})
    return out


def display_name(user) -> str:
    from .slots import display_name as dn
    return dn(user)


def _model(res) -> str:
    """The model that wrote the answer, named beside it on the thread (review 9 C, S3): the answer's own, else the reasoner's label;
    "" when no model was called (a request refused by the scope check before the answer)."""
    if res.get("model"):
        return str(res["model"])
    if res.get("status") == "out_of_scope":
        return ""
    try:
        return str(config.models()["reasoner"].get("label") or "reasoner")
    except Exception:
        return "reasoner"


def public(t, sig_hash) -> dict:
    stale = bool(t.get("signature") and sig_hash and t["signature"].get("hash") != sig_hash)
    return {**{k: t.get(k) for k in ("id", "by", "by_name", "at", "question", "status", "statements", "message", "pinned", "seconds", "dropped_unverified", "category",
                                     "model")},
            "stale": stale, "stale_reason": "The records changed since this answer was computed" if stale else "", "signature": (t.get("signature") or {}).get("hash")}


def threads(case_id, state=None) -> list:
    sig = rules.case_signature(case_id, state)
    rows = [(i, public(t, sig["hash"])) for i, t in enumerate(load(case_id)["threads"])]  # the file order breaks ties within one second
    rows.sort(key=lambda x: (bool(x[1].get("pinned")), x[1].get("at") or "", x[0]), reverse=True)
    return [t for _, t in rows]


def _history(h):
    return [x for x in h if isinstance(x, dict) and x.get("role") in ("user", "assistant") and isinstance(x.get("content"), str)][-4:] if isinstance(h, list) else None


async def ask(case_id, question, user, history=None) -> dict:
    """Run qa.ask and save the thread. The signature is taken before the model call: a change during it marks the thread stale."""
    q = " ".join(str(question or "").split())[:MAX_QUESTION]
    if not q:
        raise ValueError("Ask a question")
    st = store.get_state(case_id)
    sig = rules.case_signature(case_id, st)
    res = await qa.ask(case_id, q, _history(history))
    t = {"id": "T" + uuid.uuid4().hex[:8], "by": user, "by_name": display_name(user), "at": store.now_iso(), "question": q, "status": res.get("status") or "not_documented",
         "statements": _citations(res.get("statements")), "message": res.get("message") or "", "pinned": False, "seconds": res.get("seconds"),
         "dropped_unverified": res.get("dropped_unverified", 0), "category": res.get("category"), "model": _model(res), "signature": {k: sig.get(k) for k in ("hash", "documents", "ready", "confirmations")},
         "shared": True}
    with _lock:
        data = load(case_id)
        data["threads"].append(t)
        if len(data["threads"]) > MAX_THREADS:  # the oldest unpinned threads go
            keep = [x for x in data["threads"] if x.get("pinned")]
            rest = [x for x in data["threads"] if not x.get("pinned")]
            data["threads"] = sorted(keep + rest[-(MAX_THREADS - len(keep)):], key=lambda x: x.get("at") or "")
        save(case_id, data)
    store.audit(case_id, {"kind": "chat_asked", "by": user, "thread": t["id"], "question": q[:300], "status": t["status"], "statements": len(t["statements"]),
                          "dropped_unverified": t["dropped_unverified"]})
    return public(t, sig["hash"])


def pin(case_id, thread_id, pinned, user) -> dict:
    with _lock:
        data = load(case_id)
        t = next((x for x in data["threads"] if x.get("id") == thread_id), None)
        if not t:
            raise KeyError(thread_id)
        t["pinned"] = bool(pinned)
        t["pinned_by"] = user if pinned else None
        save(case_id, data)
    store.audit(case_id, {"kind": "chat_pinned" if pinned else "chat_unpinned", "by": user, "thread": thread_id})
    return public(t, rules.case_signature(case_id)["hash"])
