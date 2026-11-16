"""Shared pieces of the folder adapters: the allowed folder roots, path safety, capped reads, a per-folder parse cache, the
status vocabulary, dates, and the report / patient / encounter dicts in the shapes of his_client."""
import hashlib
import os
import re
from datetime import date, datetime
from pathlib import Path

from .. import config, his_client
from ..his_client import HISError, IST

MAX_MESSAGE_BYTES = 5 * 1024 * 1024       # one HL7 message file, one ABDM bundle, the index file
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024     # one report file named by index.csv
MAX_FILES = 5000                          # files read from one folder
MAX_ROWS = 50000                          # rows read from one index.csv
STATUSES = ("final", "preliminary", "corrected", "amended", "cancelled", "registered", "partial", "unknown")
_STATUS_WORDS = {
    "final": "final", "f": "final", "finalised": "final", "finalized": "final", "verified": "final", "authorised": "final", "authorized": "final",
    "approved": "final", "completed": "final", "complete": "final", "signed": "final", "reported": "final",
    "preliminary": "preliminary", "p": "preliminary", "provisional": "preliminary", "draft": "preliminary", "unverified": "preliminary",
    "pending": "preliminary", "interim": "preliminary",
    "corrected": "corrected", "c": "corrected", "revised": "corrected", "correction": "corrected",
    "amended": "amended", "addendum": "amended", "amendment": "amended",
    "cancelled": "cancelled", "canceled": "cancelled", "x": "cancelled", "withdrawn": "cancelled", "entered in error": "cancelled",
    "entered-in-error": "cancelled", "rejected": "cancelled",
    "partial": "partial", "registered": "registered"}
_AADHAAR = ("AADHAAR", "AADHAR", "UIDAI")


def status_word(s) -> str:
    """A status as the hospital wrote it (index.csv) in the vocabulary of his_client ("unknown" for anything else)."""
    return _STATUS_WORDS.get(re.sub(r"\s+", " ", str(s or "").strip().lower()), "unknown")


def is_aadhaar(kind: str, authority: str = "") -> bool:
    """An identifier type or assigning authority that names Aadhaar: never stored, never searched (project rule)."""
    k, a = str(kind or "").upper(), str(authority or "").upper()
    return k in _AADHAAR or k in ("UID", "NI", "NNIND") or any(w in a for w in _AADHAAR)


# ---------------------------------------------------------------------------------------------------- folders
def folder_roots() -> list:
    """The folders a hospital-system folder may live in: TB_HIS_FOLDER_ROOTS (comma separated), default <DATA_ROOT>/his_inbox. The
    environment names the default hospital's folders only: any other hospital reads only its own <DATA_ROOT>/his_inbox (16 Nov 2026)."""
    if config.hospital_id() != config.DEFAULT_HOSPITAL:
        return [Path(config.DATA_ROOT) / "his_inbox"]
    raw = [x.strip() for x in os.getenv("TB_HIS_FOLDER_ROOTS", "").split(",") if x.strip()]
    return [Path(x) for x in raw if Path(x).is_absolute()] or [Path(config.DATA_ROOT) / "his_inbox"]


def _inside(real: Path, root: Path) -> bool:
    return real == root or root in real.parents


def check_folder(folder) -> Path:
    """The folder as a resolved path inside an allowed root, or ValueError with a plain message. Checked when the settings are
    saved and again every time the folder is read (a link placed later is caught too)."""
    s = str(folder or "").strip()
    if not s:
        raise ValueError("give the folder the hospital system drops its files into")
    if "\x00" in s or len(s) > 500:
        raise ValueError("the folder path is not valid")
    p = Path(s)
    if not p.is_absolute():
        raise ValueError("the folder must be a full path (starting with /)")
    if ".." in p.parts:
        raise ValueError("the folder path must not contain '..'")
    real = Path(os.path.realpath(p))
    for root in folder_roots():
        if _inside(real, Path(os.path.realpath(root))):
            return real
    raise ValueError("the folder must be inside an allowed folder root (TB_HIS_FOLDER_ROOTS, default <data root>/his_inbox); ask the Vaidyx admin")


def runtime_folder(folder) -> Path:
    """check_folder for a read: HISError instead of ValueError, and the folder must exist and be readable."""
    try:
        real = check_folder(folder)
    except ValueError as e:
        raise HISError(str(e)) from None
    if not real.is_dir():
        raise HISError("the hospital-system folder does not exist on this server")
    if not os.access(real, os.R_OK | os.X_OK):
        raise HISError("the hospital-system folder cannot be read by Vaidyx-TB")
    return real


def _skip(skipped: dict, reason: str, n: int = 1):
    skipped[reason] = skipped.get(reason, 0) + n


def list_files(folder: Path, suffixes, max_bytes: int = MAX_MESSAGE_BYTES, max_files: int = MAX_FILES) -> tuple:
    """([(path, size, mtime_ns)], skipped): the regular files directly in `folder` with one of `suffixes`, by name. A link that
    leaves the folder, a file over `max_bytes` and files past `max_files` are skipped and counted, never read."""
    out, skipped = [], {}
    try:
        entries = sorted(os.scandir(folder), key=lambda e: e.name)
    except OSError as e:
        raise HISError(f"the hospital-system folder cannot be listed: {type(e).__name__}") from None
    for e in entries:
        if e.name.startswith(".") or Path(e.name).suffix.lower() not in suffixes:
            continue
        try:
            real = Path(os.path.realpath(e.path))
            if e.is_symlink() and not _inside(real, folder):
                _skip(skipped, "a link that leaves the folder"); continue
            if not real.is_file():
                continue
            st = real.stat()
        except OSError:
            _skip(skipped, "unreadable file"); continue
        if st.st_size > max_bytes:
            _skip(skipped, f"larger than {max_bytes // (1024 * 1024)} MiB"); continue
        if len(out) >= max_files:
            _skip(skipped, f"past the limit of {max_files} files"); continue
        out.append((real, st.st_size, st.st_mtime_ns))
    return out, skipped


def inside_file(folder: Path, rel, max_bytes: int = MAX_DOCUMENT_BYTES) -> Path:
    """A file named relative to `folder` (index.csv's `file` column) as a resolved path, or ValueError (plain reason): never an
    absolute path, never '..', never a link that leaves the folder, never over `max_bytes`."""
    s = str(rel or "").strip()
    if not s:
        raise ValueError("no file named")
    if "\x00" in s or "\\" in s or Path(s).is_absolute():
        raise ValueError("the file must be named relative to the folder")
    if ".." in Path(s).parts:
        raise ValueError("the file path contains '..'")
    real = Path(os.path.realpath(folder / s))
    if not _inside(real, folder) or real == folder:
        raise ValueError("the file is outside the folder")
    if not real.is_file():
        raise ValueError("the file is missing")
    if real.stat().st_size > max_bytes:
        raise ValueError(f"the file is larger than {max_bytes // (1024 * 1024)} MiB")
    return real


_CACHE: dict = {}


def cached(kind: str, folder: Path, signature, build):
    """`build()` once per folder state: the parsed folder is reused until a file is added, removed or changed."""
    key = (kind, str(folder))
    hit = _CACHE.get(key)
    if hit and hit[0] == signature:
        return hit[1]
    val = build()
    _CACHE[key] = (signature, val)
    if len(_CACHE) > 16:
        _CACHE.pop(next(iter(_CACHE)))
    return val


# ---------------------------------------------------------------------------------------------------- dates
_DMY = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def iso_day(s) -> str:
    """DD/MM/YYYY (also with - or . and an optional time) or an ISO date / date-time as ISO text; "" when unreadable."""
    v = str(s or "").strip()
    if not v:
        return ""
    m = _DMY.match(v)
    try:
        if m:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if m.group(4) is None:
                return d.isoformat()
            return datetime(d.year, d.month, d.day, int(m.group(4)), int(m.group(5)), int(m.group(6) or 0), tzinfo=IST).isoformat(timespec="seconds")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            return date.fromisoformat(v).isoformat()
        t = his_client._parse_time(v)
        return t.isoformat(timespec="seconds") if t else ""
    except ValueError:
        return ""


def stamp(s) -> str:
    """A comparable instant for `last_updated`: a date becomes its IST midnight."""
    v = str(s or "")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        return v + "T00:00:00+05:30"
    return v


def after(value: str, since) -> bool:
    """Whether `value` (ISO) is at or after `since` (ISO; None = always). HISError on a bad `since`."""
    if since is None:
        return True
    cut = his_client._parse_time(since)
    if cut is None:
        raise HISError(f"bad 'since' value {since!r}")
    t = his_client._parse_time(value)
    return t is not None and t >= cut


# ---------------------------------------------------------------------------------------------------- shapes
def patient_shape(pid: str, uhid: str, name: str = "", sex: str = "", dob: str = "", age=None, abha: str = "", abha_address: str = "",
                  pmjay_id: str = "", phone: str = "", last_updated: str = "") -> dict:
    """The Patient dict of his_client.patient_dict (no matched_on / similar)."""
    idents = [{"kind": k, "value": v} for k, v in (("uhid", uhid), ("abha", abha), ("abha_address", abha_address), ("pmjay", pmjay_id)) if v]
    if dob and age is None:
        age = his_client._age(dob)
    return {"id": pid, "ref": None, "uhid": uhid, "registration_kind": "permanent", "name": name, "sex": sex if sex in ("M", "F") else "",
            "dob": dob, "age": age, "abha": abha, "abha_address": abha_address, "pmjay_id": pmjay_id, "phone": phone, "identifiers": idents,
            "registered_on": "", "last_updated": last_updated}


def encounter_shape(number: str, kind: str, start: str = "", end: str = "", department: str = "", unit: str = "", consultant=None,
                    ward_history=(), last_updated: str = "", status: str = "") -> dict:
    """The encounter dict of his_client.encounter_dict."""
    return {"id": number, "ref": "", "kind": kind if kind in ("IP", "OP") else "", "number": number, "status": status or ("finished" if end else ""),
            "department": department, "unit": unit, "consultant": consultant, "start": start, "end": end, "ward_history": list(ward_history),
            "pmjay_preauth": None, "last_updated": last_updated}


def report_shape(rid: str, version: int, document_ref: str, *, title: str = "", status: str = "unknown", issued: str = "", effective: str = "",
                 kind: str = "diagnostic", code=None, category=(), doc_type: str = "", doc_type_basis: str = "", encounter_number: str = "",
                 encounter_kind: str = "", accession: str = "", order_ref=None, performer_department: str = "", reported_by=None, observations=(),
                 conclusion: str = "", amendment_note: str = "", sha256: str = "", size=None, content_type: str = "", last_updated: str = "",
                 current: bool = True, text_only: bool = False) -> dict:
    """The report dict of his_client.build_report. `signature` is always None here: these transports carry no signature that
    Vaidyx-TB can verify, so the signature is unknown (never "yes")."""
    return {"id": rid, "version": version, "kind": kind, "ref": None, "document_ref": document_ref, "current": current, "title": title,
            "code": code, "category": list(category), "doc_type": doc_type, "doc_type_basis": doc_type_basis,
            "status": status if status in STATUSES else "unknown", "issued": issued, "effective": effective, "encounter_ref": "",
            "encounter_number": encounter_number, "encounter_kind": encounter_kind, "accession": accession, "order_ref": order_ref,
            "performer_department": performer_department, "reported_by": reported_by, "signature": None, "observations": list(observations),
            "imaging_study_ref": None, "conclusion": conclusion, "amendment_note": amendment_note,
            "document": {"url": "", "sha256": sha256, "sha1_b64": "", "size": size, "content_type": content_type, "title": title,
                         "creation": issued, "text_only": text_only},
            "last_updated": last_updated or stamp(issued)}


def number_versions(reports: list) -> list:
    """Reports of one patient, several per report id in arrival order: numbered 1..n per id, the last one current, sorted as the
    FHIR client sorts (first issue of the report, id, version)."""
    by_id = {}
    for r in reports:
        by_id.setdefault(r["id"], []).append(r)
    out = []
    for rid, rs in by_id.items():
        for n, r in enumerate(rs, start=1):
            r["version"], r["current"] = n, n == len(rs)
            out.append(r)
    first = {}
    far = datetime.max.replace(tzinfo=IST)
    for r in out:
        t = his_client._parse_time(r["issued"]) or far
        first[r["id"]] = min(first.get(r["id"], t), t)
    return sorted(out, key=lambda r: (first[r["id"]], r["id"], r["version"]))


def sniff(data: bytes, hint: str = "") -> tuple:
    """(extension, content type) of report bytes: PDF, JPEG, PNG by their first bytes, else text."""
    if data[:5] == b"%PDF-":
        return ".pdf", "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg", "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png", "image/png"
    return ".txt", "text/plain"


def document_shape(ref: str, data: bytes, title: str, stem: str, creation: str = "", status: str = "current", doc_status: str = "",
                   text_only: bool = False) -> dict:
    """The document dict of FHIRClient.document."""
    ext, ctype = sniff(data)
    return {"ref": ref, "content": data, "sha256": hashlib.sha256(data).hexdigest(), "content_type": ctype, "title": title,
            "filename": f"{his_client._slug(stem, 80)}{ext}", "size": len(data), "creation": creation, "status": status,
            "doc_status": doc_status, "text_only": text_only}


def one_match(matches: dict, value: str):
    """The single patient key among `matches` ({key: ...}); None for none; HISError for more than one."""
    if not matches:
        return None
    if len(matches) > 1:
        raise HISError(f"more than one registration matches {value}; a person must choose")
    return next(iter(matches))
