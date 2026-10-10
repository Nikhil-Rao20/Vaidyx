"""Clinician confirmations: one audited, undoable record per human decision about the Case File (V1 item 2.2).

Policy (human oversight, expert-in-the-loop):
  - A confirmation records what a clinician decided, from the source record, with the user, the time and an audit event.
    It never adds interpretation: values are copied as the clinician read them in the source document.
  - Confirmations live in state.json, never in doc.json. Re-processing a document rewrites doc.json only, so every
    confirmation survives it, and because they are overlaid at read time (apply_to_doc) after the model, they win.
  - One active record per type + key: a new one supersedes the old (the old is marked undone, never deleted).
  - Undo marks the record undone (who, when); nothing is erased from state.json or the audit log.
  - attest_final and waive are mirrored into the legacy state["overrides"] shape that rules.evaluate, agents and summary
    read today; the mirror entry carries the confirmation id so undo only removes its own entry.
"""
import copy
import uuid

from . import docstatus, protocol, store

TYPES = {
    "attest_final":     {"target": "document",    "fields": [],                            "reason_required": False, "action": "confirm"},
    "waive":            {"target": "requirement", "fields": [],                            "reason_required": True,  "action": "waive"},
    "confirm_dates":    {"target": "document",    "fields": ["report_date", "event_date"], "reason_required": False, "action": "confirm"},
    "confirm_doc_type": {"target": "document",    "fields": ["doc_type"],                  "reason_required": False, "action": "confirm"},
    "confirm_match":    {"target": "document",    "fields": ["case_id"],                   "reason_required": False, "action": "match"},
    "dismiss_failed":   {"target": "document",    "fields": [],                            "reason_required": True,  "action": "dismiss_failed"},
    "confirm_value":    {"target": "fact",        "fields": ["value"],                     "reason_required": False, "action": "confirm"},
    "resolve_flag":     {"target": "flag",        "fields": ["resolution", "value"],       "reason_required": False, "action": "resolve_flag"},
}
RESOLUTIONS = ("corrected", "intentional_deviation", "false_alarm")
LEGACY = {"documents": ("attest_final", "attested_final"), "requirements": ("waive", "waived")}
_LEGACY_KIND = {t: k for k, (t, _) in LEGACY.items()}


def _id_ok(s):
    try:
        return store.safe_id(s) == s
    except ValueError:
        return False


def _key(target, key):
    key = (key if isinstance(key, str) else "").strip()
    if not key:
        raise ValueError("Choose what this confirmation is about")
    if target in ("document", "requirement") and not _id_ok(key):
        raise ValueError(f"Not a valid {target} id: {key}")
    if target == "fact":
        doc_id, _, fid = key.partition(":")
        if not (_id_ok(doc_id) and _id_ok(fid)):
            raise ValueError("A value confirmation needs the document and the field (document id:field id)")
    if target == "flag" and len(key) > 128:
        raise ValueError("Flag id is too long")
    return key


def validate(ctype, key, fields=None, reason=""):
    """Clean and check one confirmation. Returns {"type", "key", "fields", "reason"}; raises ValueError with a plain
    message. Unknown fields are dropped; text is trimmed at the ends only (values stay as written in the source)."""
    spec = TYPES.get(ctype)
    if not spec:
        raise ValueError(f"Unknown confirmation type: {ctype}")
    key = _key(spec["target"], key)
    if fields is None:
        fields = {}
    if not isinstance(fields, dict):
        raise ValueError("Fields must be given as name: value")
    reason = (reason if isinstance(reason, str) else "").strip()
    raw = {k: ("" if fields[k] is None else str(fields[k])).strip() for k in spec["fields"] if k in fields}
    out = {}
    if ctype == "confirm_dates":
        if not raw:
            raise ValueError("Give the report date, the event date or both")
        for k, v in raw.items():
            iso = docstatus.parse_date(v) if v else ""
            if v and not iso:
                raise ValueError(f"Not a valid date: {v} (use DD/MM/YYYY or YYYY-MM-DD)")
            out[k] = iso  # "" means the document does not state this date
    elif ctype == "confirm_doc_type":
        if raw.get("doc_type", "") not in protocol.doc_types():
            raise ValueError(f"Unknown document type: {raw.get('doc_type', '')}")
        out["doc_type"] = raw["doc_type"]
    elif ctype == "confirm_match":
        if "case_id" not in raw:
            raise ValueError("Choose the Case File, or mark the document as not this patient")
        if raw["case_id"] and not _id_ok(raw["case_id"]):
            raise ValueError(f"Not a valid Case File id: {raw['case_id']}")
        out["case_id"] = raw["case_id"]  # "" means not this patient
    elif ctype == "confirm_value":
        if not raw.get("value"):
            raise ValueError("Type the value as written in the source document")
        out["value"] = raw["value"]
    elif ctype == "resolve_flag":
        res = raw.get("resolution", "")
        if res not in RESOLUTIONS:
            raise ValueError("Choose how the flag was resolved: corrected, intentional deviation or false alarm")
        if res == "intentional_deviation" and not reason:
            raise ValueError("A reason is required for an intentional deviation")
        if res == "corrected" and not raw.get("value"):
            raise ValueError("Type the corrected value as written in the source document")
        out = {"resolution": res, "value": raw.get("value", "")}
    if spec["reason_required"] and not reason:
        raise ValueError("A reason is required for this decision")
    return {"type": ctype, "key": key, "fields": out, "reason": reason}


def _records(state_or_case_id):
    st = store.get_state(state_or_case_id) if isinstance(state_or_case_id, str) else (state_or_case_id or {})
    return st.get("confirmations") or []


def active(state_or_case_id, ctype=None, key=None):
    """Records not undone, oldest first (newest last), optionally filtered by type and key."""
    return [c for c in _records(state_or_case_id) if not c.get("undone")
            and (ctype is None or c["type"] == ctype) and (key is None or c["key"] == key)]


def latest(state_or_case_id, ctype, key):
    a = active(state_or_case_id, ctype, key)
    return a[-1] if a else None


def _mirror_set(st, rec):
    kind = _LEGACY_KIND.get(rec["type"])
    if not kind:
        return
    flag = LEGACY[kind][1]
    entry = {flag: True, **({"reason": rec["reason"]} if rec["reason"] or kind == "requirements" else {}),
             "by": rec["by"], "at": rec["at"], "confirmation": rec["id"]}
    st.setdefault("overrides", {}).setdefault(kind, {})[rec["key"]] = entry


def _mirror_drop(st, rec):
    kind = _LEGACY_KIND.get(rec["type"])
    ov = ((st.get("overrides") or {}).get(kind) or {}) if kind else {}
    if (ov.get(rec["key"]) or {}).get("confirmation") == rec["id"]:
        ov.pop(rec["key"])


def record(case_id, ctype, key, fields=None, reason="", by=""):
    """Validate and store one confirmation; an active one of the same type and key is superseded. Audited."""
    clean = validate(ctype, key, fields, reason)
    st = store.get_state(case_id)
    confs = st.setdefault("confirmations", [])
    at = store.now_iso()
    rec = {"id": "C" + uuid.uuid4().hex[:8], **clean, "by": by, "at": at, "undone": None}
    old = active(st, ctype, clean["key"])
    for c in old:
        c["undone"] = {"by": by, "at": at, "superseded_by": rec["id"]}
        _mirror_drop(st, c)
    confs.append(rec)
    _mirror_set(st, rec)
    store.save_state(case_id, st)
    ev = {"kind": "confirmation", "type": ctype, "key": clean["key"], "fields": clean["fields"], "reason": clean["reason"], "by": by, "id": rec["id"]}
    store.audit(case_id, {**ev, "supersedes": [c["id"] for c in old]} if old else ev)
    return rec


def undo(case_id, conf_id, by=""):
    """Mark a confirmation undone (kept for the record) and drop its legacy mirror entry. KeyError if unknown or already undone."""
    st = store.get_state(case_id)
    rec = next((c for c in st.get("confirmations") or [] if c["id"] == conf_id), None)
    if not rec or rec.get("undone"):
        raise KeyError(conf_id)
    rec["undone"] = {"by": by, "at": store.now_iso()}
    _mirror_drop(st, rec)
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "confirmation_undone", "type": rec["type"], "key": rec["key"], "by": by, "id": conf_id})
    return rec


def legacy_override(case_id, kind, key, value, by=""):
    """The old /overrides contract on top of confirmations. kind "documents" = attest final, "requirements" = waive.
    A value with attested_final / waived true records one; None or false undoes it (and clears any entry written by the
    old rules.set_override). Keeps the legacy "override" audit event as well. Returns the new record or None."""
    if kind not in LEGACY:
        raise ValueError(f"Unknown override kind: {kind}")
    ctype, flag = LEGACY[kind]
    rec = None
    if value and value.get(flag):
        rec = record(case_id, ctype, key, {}, value.get("reason", ""), by)
    else:
        for c in active(case_id, ctype, key):
            undo(case_id, c["id"], by)
        st = store.get_state(case_id)
        if key in ((st.get("overrides") or {}).get(kind) or {}):
            st["overrides"][kind].pop(key)
            store.save_state(case_id, st)
    store.audit(case_id, {"kind": "override", "target": kind, "key": key, "value": value, "by": by})
    return rec


def apply_to_doc(doc, state):
    """The document as the clinicians confirmed it: confirmations overlaid on the model's reading (they win), with the
    model's values kept under model_*. Never mutates the input; a document with no confirmations comes back equal."""
    did = doc.get("doc_id")
    mine = [c for c in active(state) if c["key"] == did or (TYPES[c["type"]]["target"] == "fact" and c["key"].partition(":")[0] == did)]
    mine = [c for c in mine if c["type"] in ("confirm_doc_type", "confirm_dates", "confirm_value", "dismiss_failed")]
    if not mine:
        return dict(doc)
    d = copy.deepcopy(doc)
    cls = d.setdefault("classification", {}) if any(c["type"] in ("confirm_doc_type", "confirm_dates") for c in mine) else d.get("classification")
    for c in mine:
        f = c["fields"]
        if c["type"] == "confirm_doc_type":
            cls["model_doc_type"] = cls.get("doc_type")
            cls["doc_type"] = f["doc_type"]
            cls["doc_type_confirmed_by"] = c["by"]
        elif c["type"] == "confirm_dates":
            for k in ("report_date", "event_date"):
                if k in f:
                    cls["model_" + k + "_iso"] = cls.get(k + "_iso")
                    cls[k + "_iso"] = f[k]
                    cls[k + "_assumed"] = False  # the clinician read it (or said the document does not state it)
                    cls[k + "_label"] = "confirmed by " + c["by"]
                    cls[k + "_quote"] = ""
            cls["dates_confirmed_by"] = c["by"]
            cls["date_unconfirmed"] = False  # a confirmation settles the date question (V1 item 3.1), even "not stated"
            cls["date_flags"] = []
        elif c["type"] == "confirm_value":
            from . import extract  # the same pending wording as extraction ("awaited", "not reported"): a confirmed "Awaited" stays pending
            fid = c["key"].partition(":")[2]
            prev = (d.get("facts") or {}).get(fid)
            fact = dict(prev) if prev else {"reason": None, "polarity": "affirmed"}
            # the clinician's reading is the evidence: no model quote is shown as if it supported the confirmed value
            fact.update({"model_value": (prev or {}).get("value"), "model_verification": (prev or {}).get("verification"),
                         "model_state": (prev or {}).get("state"), "model_quote": (prev or {}).get("quote"), "model_location": (prev or {}).get("location"),
                         "value": f["value"], "quote": "", "location": None, "verification": "confirmed",
                         "state": "pending" if extract.PENDING_RE.search(f["value"]) else "present", "confirmed_by": c["by"], "confirmation": c["id"]})
            d.setdefault("facts", {})[fid] = fact
        elif c["type"] == "dismiss_failed":
            d["dismissed"] = {"by": c["by"], "at": c["at"], "reason": c["reason"]}
    d["confirmations"] = [c["id"] for c in mine]
    return d


def apply_to_docs(docs, state):
    return [apply_to_doc(d, state) for d in docs]


def summary(state):
    """Active confirmations per type (every type listed, zero when none) and the total, for the Case File header."""
    a = active(state)
    out = {t: sum(1 for c in a if c["type"] == t) for t in TYPES}
    out["total"] = len(a)
    return out
