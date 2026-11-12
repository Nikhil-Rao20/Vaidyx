"""A folder of report files with an index (kind "folder_bridge"): the fallback for a hospital with no API at all. Someone at
the hospital (or a nightly export of its HIMS) puts the report PDFs in a folder and lists them in `index.csv`:

    uhid, patient_name, sex, dob (or age), visit_no, visit_type (OP / IP), report_id, report_type, report_date (DD/MM/YYYY or
    ISO), status, signed_by, file          optional: department, accession

UTF-8, one row per report version (rows with the same report_id are versions in date order; the last one is current). `file`
is relative to the folder. A bad row is skipped with a counted reason and never stops the rest. `status` is mapped to the
vocabulary of the FHIR path (final / preliminary / corrected / amended / cancelled; anything else: unknown). `signed_by` is
only the name the index gives: the signature stays unknown (None) and the report text decides, as for any upload.
No open orders, no referrals, no imaging links.
"""
import asyncio
import csv
import io
import re
from urllib.parse import quote, unquote

from .. import his_client
from ..his_client import HISClient, HISError
from . import _common as C

KIND = "folder_bridge"
INDEX = "index.csv"
REQUIRED = ("uhid", "patient_name", "report_id", "report_type", "report_date", "status", "file")
COLUMNS = ("uhid", "patient_name", "sex", "dob", "age", "visit_no", "visit_type", "report_id", "report_type", "report_date", "status",
           "signed_by", "file", "department", "accession")
FILE_TYPES = (".pdf", ".txt", ".jpg", ".jpeg", ".png")


def _norm(h) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(h or "").strip().lower()).strip("_")


def read_index(folder) -> dict:
    """The parsed index: patients, visits, reports (numbered versions), the file of each report, counts and skipped rows."""
    try:
        path = C.inside_file(folder, INDEX, C.MAX_MESSAGE_BYTES)
    except ValueError as e:
        raise HISError(f"index.csv: {e}") from None
    st = path.stat()

    def build():
        idx = {"patients": {}, "ids": {}, "visits": {}, "reports": {}, "files": {}, "skipped": {}, "rows": 0}
        try:
            text = path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HISError("index.csv is not UTF-8 text") from None
        except OSError as e:
            raise HISError(f"index.csv cannot be read: {type(e).__name__}") from None
        rows = csv.reader(io.StringIO(text, newline=""))
        try:
            head = [_norm(h) for h in next(rows, [])]
        except csv.Error:
            raise HISError("index.csv is not a readable CSV file") from None
        missing = [c for c in REQUIRED if c not in head]
        if missing:
            raise HISError("index.csv is missing the columns: " + ", ".join(missing))
        raw = {}
        try:
            for n, cells in enumerate(rows, start=2):
                if n > C.MAX_ROWS + 1:
                    C._skip(idx["skipped"], f"past the limit of {C.MAX_ROWS} rows"); continue
                if not any(str(c).strip() for c in cells):
                    continue
                idx["rows"] += 1
                row = {h: str(v).strip() for h, v in zip(head, cells) if h in COLUMNS}
                why = _add_row(folder, idx, raw, row)
                if why:
                    C._skip(idx["skipped"], why)
        except csv.Error:
            C._skip(idx["skipped"], "a line that is not readable CSV")
        for key, reps in raw.items():
            reps.sort(key=lambda r: C.stamp(r["issued"]))        # stable: equal dates keep their row order
            idx["reports"][key] = C.number_versions(reps)
        return idx
    return C.cached(KIND, folder, (st.st_size, st.st_mtime_ns), build)


def _add_row(folder, idx: dict, raw: dict, row: dict) -> str:
    """Add one index row; returns "" or the reason it was skipped."""
    uhid, rid = row.get("uhid") or "", row.get("report_id") or ""
    if not uhid:
        return "no uhid"
    if not rid:
        return "no report_id"
    if not row.get("patient_name"):
        return "no patient_name"
    issued = C.iso_day(row.get("report_date"))
    if not issued:
        return "report_date missing or not a date (DD/MM/YYYY or ISO)"
    try:
        f = C.inside_file(folder, row.get("file"))
    except ValueError as e:
        return f"file: {e}"
    if f.suffix.lower() not in FILE_TYPES:
        return "file: not a PDF, text or image file"
    vtype = (row.get("visit_type") or "").upper()
    vtype = {"IPD": "IP", "OPD": "OP", "I": "IP", "O": "OP"}.get(vtype, vtype)
    if vtype not in ("", "IP", "OP"):
        return "visit_type is not OP or IP"
    dob = C.iso_day(row.get("dob"))[:10] if row.get("dob") else ""
    if row.get("dob") and not dob:
        return "dob is not a date (DD/MM/YYYY or ISO)"
    age = None
    if row.get("age"):
        m = re.match(r"^(\d{1,3})\s*(y|yr|yrs|years)?$", row["age"].strip().lower())
        if not m or int(m.group(1)) > 130:
            return "age is not a number of years"
        age = int(m.group(1))
    sex = {"m": "M", "male": "M", "f": "F", "female": "F"}.get((row.get("sex") or "").lower(), "")
    key = uhid
    idx["patients"][key] = C.patient_shape(key, uhid, name=row["patient_name"], sex=sex, dob=dob, age=age, last_updated=C.stamp(issued))
    idx["ids"].setdefault(uhid.lower(), {})[key] = "uhid"
    visit = row.get("visit_no") or ""
    if visit:
        idx["ids"].setdefault(visit.lower(), {})[key] = "ip_no" if vtype == "IP" else "op_no"
        old = idx["visits"].setdefault(key, {}).get(visit)
        start = min(issued, old["start"]) if old else issued
        idx["visits"][key][visit] = C.encounter_shape(visit, vtype or (old or {}).get("kind") or "", start=start, department=row.get("department") or "",
                                                      last_updated=C.stamp(issued))
    title = row.get("report_type") or ""
    doc_type, basis = his_client.doc_type_for("", [], title, f.name)
    rel = str(f.relative_to(folder))
    ref = f"folder:{quote(key, safe='')}/{quote(rid, safe='')}/{quote(rel, safe='')}"
    if ref in idx["files"]:
        return "the same file listed twice for one report"
    rep = C.report_shape(rid, 1, ref, title=title, status=C.status_word(row.get("status")), issued=issued, effective=issued,
                         doc_type=doc_type, doc_type_basis=basis.replace("(no known code)", "(index.csv)"), encounter_number=visit,
                         encounter_kind=vtype, accession=row.get("accession") or "", performer_department=row.get("department") or "",
                         reported_by={"ref": "", "name": row["signed_by"]} if row.get("signed_by") else None, size=f.stat().st_size,
                         content_type={".pdf": "application/pdf", ".txt": "text/plain", ".png": "image/png"}.get(f.suffix.lower(), "image/jpeg"))
    idx["files"][ref] = rel
    raw.setdefault(key, []).append(rep)
    return ""


class FolderBridgeClient(HISClient):
    """A folder of report files with index.csv (see the module docstring)."""
    carries_signature = False  # no verifiable signature on this transport: the report text decides (his_overlay)
    kind = KIND

    def __init__(self, folder, label: str = ""):
        self.folder = str(folder or "")
        self.label = label or "Report folder with an index file"

    def __repr__(self):
        return f"FolderBridgeClient({self.folder!r})"

    async def _idx(self) -> dict:
        return await asyncio.to_thread(lambda: read_index(C.runtime_folder(self.folder)))

    async def ping(self) -> dict:
        out = {"ok": False, "name": self.label, "fhir_version": "", "token_ok": None, "error": ""}
        try:
            idx = await self._idx()
            out["counts"] = {"rows": idx["rows"], "patients": len(idx["patients"]), "reports": sum(len(v) for v in idx["reports"].values()),
                             "skipped": idx["skipped"]}
            out["ok"] = True
        except HISError as e:
            out["error"] = str(e)
        return out

    async def find_patient(self, identifier: str) -> dict | None:
        value = str(identifier or "").strip()
        if not value:
            return None
        idx = await self._idx()
        hits = idx["ids"].get(value.lower()) or {}
        key = C.one_match(hits, value)
        if key is None:
            return None
        return {**idx["patients"][key], "matched_on": {"kind": hits[key], "value": value}, "similar": []}

    async def encounters(self, patient_id: str) -> list:
        idx = await self._idx()
        return sorted((dict(v) for v in (idx["visits"].get(patient_id) or {}).values()), key=lambda e: (e["start"] or "9999", e["number"]))

    async def reports(self, patient_id: str, since: str | None = None) -> list:
        idx = await self._idx()
        return [dict(r, document=dict(r["document"])) for r in idx["reports"].get(patient_id) or [] if C.after(r["last_updated"], since)]

    async def document(self, ref: str) -> dict:
        """The file the index names for this report (only files listed in index.csv are ever served), with its sha256."""
        m = re.match(r"^folder:([^/]+)/([^/]+)/([^/]+)$", str(ref or ""))
        if not m:
            raise HISError(f"not a report-folder reference: {str(ref)[:80]}")
        idx = await self._idx()
        rel = idx["files"].get(ref)
        rep = next((r for r in idx["reports"].get(unquote(m.group(1))) or [] if r["document_ref"] == ref), None)
        if not rel or rep is None:
            raise HISError("index.csv no longer lists that report")

        def read():
            try:
                return C.inside_file(C.runtime_folder(self.folder), rel).read_bytes()
            except ValueError as e:
                raise HISError(f"the report file cannot be read: {e}") from None
            except OSError as e:
                raise HISError(f"the report file cannot be read: {type(e).__name__}") from None
        data = await asyncio.to_thread(read)
        out = C.document_shape(ref, data, rep["title"] or rep["id"], f"{rep['title'] or 'report'}_{rep['id']}_v{rep['version']}",
                               creation=rep["issued"], doc_status=rep["status"])
        ext = "." + rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
        if ext in FILE_TYPES and not out["filename"].endswith(ext) and C.sniff(data)[0] == ".txt":
            out["filename"] = out["filename"][:-4] + ext          # a scan or text file keeps the extension the hospital gave it
        return out
