"""A synthetic hospital information system as an MCP server, for the demo of the connectors (12 Oct).

It serves the "later arrivals" of the synthetic demo corpus (/data/vaidyx/tb_demo_corpus/arrivals/<case>/...) as the records a
hospital system would hold for a patient, keyed by the hospital number (MRN) in the corpus truth files. Vaidyx-TB's connector
asks it which records exist for a Case File's patient and fetches the ones the coordinator picks; the files then go through the
normal intake pipeline (reading, classification, patient matching, verification). No real patient data: SYNTHETIC only.

The records protocol a hospital-system connector must offer (every tool read-only, readOnlyHint=True):
  find_patient(query)                -> {"patients": [{"patient_id", "name", "age_sex"}]}          query = hospital number, ABHA, name
  list_records(patient_id)           -> {"records": [{"record_id", "filename", "record_type", "record_date", "department", "size"}]}
  fetch_record(patient_id, record_id)-> {"filename", "mime", "content_base64", "sha256", "record_type", "record_date", "department"}

Run: /data/vaidyx/venv/app/bin/python -m tumour_board.demo_data.demo_his_mcp [--port 7111]   (token: data/tumour_board/demo_his_token)
"""
import argparse, base64, hashlib, json, mimetypes, os, re, secrets
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .. import config

RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
DEFAULT_PORT = int(os.getenv("TB_DEMO_HIS_PORT", "7111"))
DEPT = {"01_clinical": "Medical Oncology", "02_radiology": "Radio-diagnosis", "03_nuclear_medicine": "Nuclear Medicine", "04_pathology": "Pathology",
        "05_lab": "Laboratory Medicine", "06_discharge": "Medical Oncology", "07_molecular": "Molecular Pathology", "08_endoscopy": "Gastroenterology",
        "09_surgery": "Surgical Oncology", "10_dental": "Surgical Oncology", "11_gynaecology": "Surgical Oncology", "12_radiotherapy": "Radiation Oncology"}


def token_path() -> Path:
    return Path(config.DATA_ROOT) / "demo_his_token"


def token() -> str:
    p = token_path()
    if p.exists():
        return p.read_text().strip()
    t = secrets.token_urlsafe(24)
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(t + "\n"); os.chmod(p, 0o600)
    return t


def _index(corpus: Path = None) -> dict:
    """{patient_id: {"patient": {...}, "case_id", "records": [...]}} from the corpus truth files and the arrivals folders."""
    corpus = corpus or config.DEMO_CORPUS
    out = {}
    truth = corpus / "truth"
    for tf in sorted(truth.glob("TB-*.json")) if truth.exists() else []:
        t = json.loads(tf.read_text())
        pat = t.get("patient") or {}
        pid = pat.get("mrn")
        if not pid:
            continue
        recs = []
        src = corpus / "arrivals" / t["case_id"]
        for p in sorted(src.rglob("*")) if src.exists() else []:
            if not p.is_file():
                continue
            rel = str(p.relative_to(src))
            m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
            recs.append({"record_id": hashlib.sha1(rel.encode()).hexdigest()[:10], "filename": rel, "record_type": p.parent.name.split("_", 1)[-1] if "_" in p.parent.name else p.parent.name,
                         "record_date": m.group(1) if m else "", "department": DEPT.get(p.parent.name, "Medical Records"), "size": p.stat().st_size, "_path": str(p)})
        out[pid] = {"patient": {"patient_id": pid, "name": pat.get("name", ""), "age_sex": pat.get("agesex", "")}, "case_id": t["case_id"], "records": recs}
    return out


def build(**kw) -> FastMCP:
    m = FastMCP("demo-his", instructions="SYNTHETIC hospital information system for the Vaidyx-TB demo: read-only records of synthetic patients.",
                host="127.0.0.1", port=kw.pop("port", DEFAULT_PORT), **kw)
    for fn, desc in TOOLS:
        m.tool(annotations=RO, description=desc)(fn)
    return m



def find_patient(query: str) -> dict:
    q = (query or "").strip().lower()
    idx = _index()
    hits = [v["patient"] for pid, v in idx.items() if q and (q == pid.lower() or q in v["patient"]["name"].lower())]
    return {"patients": hits}


def list_records(patient_id: str) -> dict:
    v = _index().get((patient_id or "").strip())
    return {"patient_id": patient_id, "records": [{k: r[k] for k in ("record_id", "filename", "record_type", "record_date", "department", "size")} for r in (v or {}).get("records", [])]}


def fetch_record(patient_id: str, record_id: str) -> dict:
    v = _index().get((patient_id or "").strip()) or {}
    r = next((x for x in v.get("records", []) if x["record_id"] == record_id), None)
    if not r:
        raise ValueError("No such record")
    data = Path(r["_path"]).read_bytes()
    return {"filename": r["filename"], "mime": mimetypes.guess_type(r["filename"])[0] or "application/octet-stream", "content_base64": base64.b64encode(data).decode(),
            "sha256": hashlib.sha256(data).hexdigest(), "record_type": r["record_type"], "record_date": r["record_date"], "department": r["department"]}


TOOLS = [
    (find_patient, "Find a patient by hospital number (MRN / UHID), ABHA or name. SYNTHETIC patients only."),
    (list_records, "The records the hospital system holds for a patient: id, file name, type, date, department, size."),
    (fetch_record, "Fetch one record as a file (base64), with its SHA-256, type, date and department."),
]

mcp = build()


def http_app(m: FastMCP = None, expected: str = None):
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    inner = (m or mcp).streamable_http_app()
    expected = expected if expected is not None else token()

    class Bearer(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            h = request.headers.get("authorization", "")
            if not h.startswith("Bearer ") or not secrets.compare_digest(h[7:].strip(), expected):
                return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
            return await call_next(request)
    inner.add_middleware(Bearer)
    return inner


def main(argv=None):
    ap = argparse.ArgumentParser(description="Synthetic hospital system (MCP, read-only) for the Vaidyx-TB demo")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    a = ap.parse_args(argv)
    import uvicorn
    print(f"demo-his (SYNTHETIC) on http://127.0.0.1:{a.port}/mcp; token in {token_path()}; {len(_index())} patients", flush=True)
    uvicorn.run(http_app(), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
