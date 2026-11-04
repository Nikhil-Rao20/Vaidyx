"""File-based case storage. One directory per Tumour Board Case File:

cases/<case_id>/case.json        identity, protocol, patient, created
cases/<case_id>/state.json       gate result, actions, board records, expert reviews, AI artefacts
cases/<case_id>/docs/<doc_id>/   original file + doc.json (pages, classification, facts, verification)
cases/<case_id>/audit.jsonl      append-only log of every AI call and user action

intake/<doc_id>/                 department uploads before they are matched to a patient (V1 item 2.3): original file + doc.json
intake/audit.jsonl               append-only log of intake events (uploads, matching, filing)
"""
import asyncio, hashlib, json, os, re, shutil, time, uuid
import threading
from datetime import datetime
from pathlib import Path

from . import config

_locks: dict[str, asyncio.Lock] = {}
_deleted: set = set()  # Case File directories deleted by this process (until a Case File is created there again): see gone()
log = __import__("logging").getLogger("tumour_board")


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def lock(case_id: str) -> asyncio.Lock:
    return _locks.setdefault(case_id, asyncio.Lock())


def safe_id(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "-", s.strip())[:64]
    if not s or s.startswith("."):
        raise ValueError("invalid id")
    return s


def case_dir(case_id: str) -> Path:
    return config.CASES_DIR / safe_id(case_id)


def _write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, p)


def _read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        return default


def list_cases():
    out = []
    if not config.CASES_DIR.exists():
        return out
    for d in sorted(config.CASES_DIR.iterdir()):
        c = _read_json(d / "case.json")
        if c:
            st = _read_json(d / "state.json", {})
            g = st.get("gate") or {}
            out.append({**c, "documents": len(list((d / "docs").glob("*/doc.json"))) if (d / "docs").exists() else 0,
                        "gate_passed": g.get("passed"), "open_actions": sum(1 for a in st.get("actions", []) if a["status"] != "completed"),
                        "suggested_actions": sum(1 for a in st.get("actions", []) if a.get("status") == "suggested"),  # requests nobody sent yet (V2 items 4.2, 7.1)
                        "readiness": g.get("readiness")})
    return out


def gone(case_id) -> bool:
    """True when this Case File was deleted while something was still working on it (the ready hook, an agent, a reading job): its writes
    are dropped, so no directory comes back with an orphan state.json or audit.jsonl that a later Case File of the same id would inherit
    (18 Oct, e2e: the ready hook of a deleted Case File re-created its directory). A Case File created there again (case.json) clears it."""
    d = str(case_dir(case_id))
    if d not in _deleted:
        return False
    if (Path(d) / "case.json").exists():
        _deleted.discard(d)
        return False
    return True


def _dropped(case_id, what) -> bool:
    if gone(case_id):
        log.warning("Case File %s was deleted: %s not written", case_id, what)
        return True
    return False


def create_case(case_id, patient: dict, protocol: str, board_date: str = "", created_by: str = "", setting: str = "", hospital_level: str = ""):
    d = case_dir(case_id)
    if (d / "case.json").exists():
        raise FileExistsError(case_id)
    _deleted.discard(str(d))
    c = {"case_id": case_id, "patient": patient, "protocol": protocol, "setting": setting, "hospital_level": hospital_level, "board_date": board_date,
         "created": now_iso(), "created_by": created_by,
         # a Case File without a protocol waits for the coordinator to list it (V1 item 2.5)
         "listing": {"status": "listed", "listed_by": created_by, "listed_at": now_iso()} if protocol else {"status": "awaiting_listing"}}
    _write_json(d / "case.json", c)
    _write_json(d / "state.json", {"actions": [], "board_records": [], "reviews": [], "artefacts": {}, "gate": None})
    return c


def save_case(case):
    if _dropped(case["case_id"], "case.json"):
        return
    _write_json(case_dir(case["case_id"]) / "case.json", case)


def delete_case(case_id):
    _last_hash.pop(str(case_dir(case_id) / "audit.jsonl"), None)  # a re-created Case File starts a fresh audit chain
    shutil.rmtree(case_dir(case_id), ignore_errors=True)
    _deleted.add(str(case_dir(case_id)))
    _docs_cache.pop(case_id, None)


def private_receipt(ev: dict) -> None:
    """One line in <DATA_ROOT>/private_deletions.jsonl for a deleted private Case File (its own audit is deleted with it): ids, who,
    when, never patient details."""
    p = config.DATA_ROOT / "private_deletions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now_iso(), **{k: v for k, v in ev.items() if k in ("kind", "case_id", "by", "how", "age_days", "records")}}) + "\n")


def get_case(case_id):
    return _read_json(case_dir(case_id) / "case.json")


def get_state(case_id):
    return _read_json(case_dir(case_id) / "state.json", {"actions": [], "board_records": [], "reviews": [], "artefacts": {}, "gate": None})


def save_state(case_id, st):
    if _dropped(case_id, "state.json"):
        return
    _write_json(case_dir(case_id) / "state.json", st)


def find_duplicate(case_id, data: bytes):
    """An identical file already in the Case File (same SHA-256), or None."""
    h = hashlib.sha256(data).hexdigest()
    for d in list_docs(case_id):
        if d.get("sha256") == h:
            return d
    return None


def delete_document(case_id, doc_id):
    shutil.rmtree(case_dir(case_id) / "docs" / safe_id(doc_id), ignore_errors=True)


def add_document_file(case_id, src_name: str, data: bytes, rel_path: str = ""):
    if gone(case_id):
        raise FileNotFoundError(f"Case File {case_id} was deleted")
    doc_id = "D" + uuid.uuid4().hex[:8]
    ext = Path(src_name).suffix.lower()
    dd = case_dir(case_id) / "docs" / doc_id
    dd.mkdir(parents=True, exist_ok=True)
    (dd / f"original{ext}").write_bytes(data)
    doc = {"doc_id": doc_id, "filename": Path(src_name).name, "rel_path": rel_path or Path(src_name).name, "ext": ext,
           "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "added": now_iso(), "state": "queued"}
    _write_json(dd / "doc.json", doc)
    return doc


def original_path(case_id, doc_id) -> Path:
    dd = case_dir(case_id) / "docs" / safe_id(doc_id)
    return next(dd.glob("original.*"))


def get_doc(case_id, doc_id):
    return _read_json(case_dir(case_id) / "docs" / safe_id(doc_id) / "doc.json")


def save_doc(case_id, doc):
    if _dropped(case_id, f"document {doc.get('doc_id')}"):
        return
    _write_json(case_dir(case_id) / "docs" / doc["doc_id"] / "doc.json", doc)


_docs_cache: dict[str, tuple] = {}


def list_docs(case_id):
    base = case_dir(case_id) / "docs"
    if not base.exists():
        return []
    sig = tuple(sorted((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in base.glob("*/doc.json")))
    hit = _docs_cache.get(case_id)
    if hit and hit[0] == sig:
        return [dict(d) for d in hit[1]]
    docs = sorted([d for d in (_read_json(p) for p in base.glob("*/doc.json")) if d], key=lambda d: (d.get("rel_path") or ""))
    _docs_cache[case_id] = (sig, docs)
    return [dict(d) for d in docs]


# ---- tamper-evident audit log (12 Oct): every event carries the hash of the previous one and its own hash ------------------
_chain_lock = threading.Lock()
_last_hash: dict = {}  # case_id -> hash of the last event written (read from the file's last line on first use)


def _canon(ev: dict) -> str:
    return json.dumps(ev, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def _event_hash(prev: str, body: dict) -> str:
    return hashlib.sha256((prev + "\n" + _canon(body)).encode("utf-8")).hexdigest()


def _tail_hash(p: Path) -> str:
    """The hash of the last line of an audit file ('' when the file is empty or its last line predates the chain)."""
    if not p.exists():
        return ""
    with open(p, "rb") as f:
        f.seek(0, 2); size = f.tell()
        f.seek(max(0, size - 65536)); tail = f.read().decode("utf-8", "replace")
    lines = [l for l in tail.splitlines() if l.strip()]
    if not lines:
        return ""
    try:
        return json.loads(lines[-1]).get("hash") or ""
    except Exception:
        return ""


def audit(case_id, event: dict):
    if _dropped(case_id, f"audit event {event.get('kind')}"):
        return
    event = {"ts": now_iso(), **{k: v for k, v in event.items() if k not in ("prev", "hash")}}
    p = case_dir(case_id) / "audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with _chain_lock:
        key = str(p)  # by file, not by case id: the same id in another data root (tests, a restored backup) must not inherit a hash
        cached = _last_hash.get(key)
        size = p.stat().st_size if p.exists() else 0
        prev = cached[0] if cached and cached[1] == size else _tail_hash(p)  # a file re-created or written elsewhere: read its tail again
        h = _event_hash(prev, event)
        with open(p, "a") as f:
            f.write(json.dumps({**event, "prev": prev, "hash": h}, ensure_ascii=False, default=str) + "\n")
        _last_hash[key] = (h, p.stat().st_size)


def verify_audit(case_id) -> dict:
    """Walk the chain: every hashed event must carry the hash of the event before it and its own recomputed hash. Events written
    before the chain existed count as unchained (the chain starts at the first hashed event)."""
    p = case_dir(case_id) / "audit.jsonl"
    if not p.exists():
        return {"ok": True, "events": 0, "chained": 0, "unchained": 0, "first_broken": None, "last_hash": ""}
    prev, chained, unchained, broken = "", 0, 0, None
    lines = [l for l in p.read_text().splitlines() if l.strip()]
    for i, l in enumerate(lines):
        try:
            ev = json.loads(l)
        except Exception:
            broken = broken if broken is not None else i; continue
        h = ev.get("hash")
        if not h:
            unchained += 1; continue
        body = {k: v for k, v in ev.items() if k not in ("prev", "hash")}
        if ev.get("prev", "") != prev or _event_hash(prev, body) != h:
            broken = broken if broken is not None else i
        prev = h; chained += 1
    return {"ok": broken is None, "events": len(lines), "chained": chained, "unchained": unchained, "first_broken": broken, "last_hash": prev}


def read_audit(case_id, limit=500):
    p = case_dir(case_id) / "audit.jsonl"
    if not p.exists():
        return []
    lines = p.read_text().splitlines()[-limit:]
    return [json.loads(l) for l in lines]


def auditor(case_id):
    return lambda ev: audit(case_id, ev)


# ---- intake area: department uploads before patient matching (V1 item 2.3) ----------------------------------------

def intake_dir() -> Path:
    return config.DATA_ROOT / "intake"


def intake_doc_dir(doc_id: str) -> Path:
    return intake_dir() / safe_id(doc_id)


def add_intake_file(src_name: str, data: bytes, rel_path: str, department: str, user: str):
    """Store an uploaded file in the intake area, tagged with the uploading department, user and time."""
    doc_id = "D" + uuid.uuid4().hex[:8]
    ext = Path(src_name).suffix.lower()
    dd = intake_doc_dir(doc_id)
    dd.mkdir(parents=True, exist_ok=True)
    (dd / f"original{ext}").write_bytes(data)
    doc = {"doc_id": doc_id, "filename": Path(src_name).name, "rel_path": rel_path or Path(src_name).name, "ext": ext,
           "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "added": now_iso(), "state": "queued",
           "department": department, "uploaded_by": user, "intake": True}
    _write_json(dd / "doc.json", doc)
    return doc


def get_intake(doc_id: str):
    return _read_json(intake_doc_dir(doc_id) / "doc.json")


def save_intake(doc):
    _write_json(intake_doc_dir(doc["doc_id"]) / "doc.json", doc)


def intake_original_path(doc_id: str) -> Path:
    return next(intake_doc_dir(doc_id).glob("original.*"))


def list_intake():
    base = intake_dir()
    if not base.exists():
        return []
    docs = [d for d in (_read_json(p) for p in base.glob("*/doc.json")) if d]
    return sorted(docs, key=lambda d: d.get("added") or "")


def delete_intake(doc_id: str):
    shutil.rmtree(intake_doc_dir(doc_id), ignore_errors=True)


def move_intake_to_case(doc_id: str, case_id: str):
    """Move an intake document (original + record) into cases/<case_id>/docs/<doc_id>/ keeping its id. Returns the record."""
    src = intake_doc_dir(doc_id)
    doc = _read_json(src / "doc.json")
    if not doc:
        raise KeyError(doc_id)
    dst = case_dir(case_id) / "docs" / safe_id(doc_id)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    _docs_cache.pop(case_id, None)
    return doc


def move_case_doc_to_intake(case_id: str, doc_id: str):
    """Move a document (original + record) out of a Case File back into the intake area, keeping its id. Returns the record."""
    src = case_dir(case_id) / "docs" / safe_id(doc_id)
    doc = _read_json(src / "doc.json")
    if not doc:
        raise KeyError(doc_id)
    dst = intake_doc_dir(doc_id)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    _docs_cache.pop(case_id, None)
    return doc


def audit_intake(event: dict):
    event = {"ts": now_iso(), **event}
    p = intake_dir() / "audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def read_intake_audit(limit=500):
    p = intake_dir() / "audit.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines()[-limit:]]


def intake_auditor(doc_id):
    return lambda ev: audit_intake({"doc_id": doc_id, **ev})
