"""Re-capture the HIS fixtures of test_his_client.py from the live mock hospital (SYNTHETIC, read only).

    /data/vaidyx/venv/app/bin/python -m tumour_board.tests.fixtures.his._capture

Runs the HIS client against http://127.0.0.1:7130 through a recording transport, trims every answer (no base64 PDFs, no DICOM
instance lists, no meta tags or profiles, no Practitioner / Media entries) and writes one JSON file per request plus index.json
({"<path>?<query>": file}). The one PDF the tests fetch by url is kept as a .pdf file. Nothing is written to the mock.
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tumour_board import his_client  # noqa: E402

URL = "http://127.0.0.1:7130"
DROP_TYPES = {"Practitioner", "Media", "Composition"}
# registrations whose $everything only feeds open_orders() / referrals() in the tests: reports are dropped from their fixture
ORDERS_ONLY = {"vxh-26-004204", "vxh-26-004208", "vxh-26-004210", "vxh-26-004214", "vxh-26-004215"}
REPORT_TYPES = {"Observation", "Provenance", "DocumentReference"}


def key_of(url: httpx.URL) -> str:
    q = url.query.decode() if isinstance(url.query, bytes) else str(url.query)
    return unquote(url.raw_path.decode().split("?")[0]) + (("?" + unquote(q)) if q else "")


def slug(key: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", key.replace("/fhir/", "", 1)).strip("_").lower()
    return s[:120]


def trim(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("tag", "profile", "search"):
                continue
            if k == "data" and isinstance(v, str) and len(v) > 200 and "contentType" in obj:
                continue                     # attachment / presentedForm base64
            if k == "instance" and isinstance(v, list):
                continue                     # DICOM instance lists
            out[k] = trim(v)
        if out.get("resourceType") == "Bundle":
            out["entry"] = [e for e in out.get("entry") or [] if (e.get("resource") or {}).get("resourceType") not in DROP_TYPES]
            out["link"] = [link for link in out.get("link") or [] if link.get("relation") != "self"]
        return out
    if isinstance(obj, list):
        return [trim(x) for x in obj]
    return obj


class Recorder(httpx.AsyncBaseTransport):
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport()
        self.seen = {}

    async def handle_async_request(self, request):
        resp = await self.inner.handle_async_request(request)
        body = await resp.aread()
        self.seen[key_of(request.url)] = (resp.status_code, resp.headers.get("content-type", ""), body)
        return httpx.Response(resp.status_code, headers=resp.headers, content=body, request=request)


async def run(c):
    await c.ping()
    for q in ["VXH/26/004201", "VXH/T/26/00412", "VXH/26/004209", "IP/26/01875", "OP/26/118701", "99-2600-0000-0101",
              "anitha.reddy@sbx", "VXH/26/999999"]:
        await c.find_patient(q)
    await c.similar("vxh-26-004209")
    for p in ["vxh-26-004201", "vxh-26-004203"]:
        await c.encounters(p)
    for p in ["vxh-26-004201", "vxh-26-004202", "vxh-26-004203", "vxh-26-004212"]:
        await c.reports(p)
    await c.reports("vxh-26-004202", since="2026-09-10T00:00:00+05:30")
    for p in ["vxh-26-004215", "vxh-26-004204", "vxh-26-004210", "vxh-26-004208", "vxh-26-004214"]:
        await c.open_orders(p)
    await c.referrals("vxh-26-004214")
    await c.document("DocumentReference/doc-p02-r05-v2")
    async with c._client() as h:          # the PDF by url (the trimmed DocumentReference has no base64 data)
        await c._send(h, c._url("/documents/documents/p02-r05-v2.pdf"))
    await c.imaging_study("ImagingStudy/img-rad-26-01004")
    await c.hospital()


def main():
    rec = Recorder()
    tok = (REPO / "data" / "his_mock" / "token").read_text().strip()
    c = his_client.FHIRClient(URL, tok, transport=rec)
    asyncio.run(run(c))
    for f in HERE.glob("*.json"):
        f.unlink()
    for f in HERE.glob("*.pdf"):
        f.unlink()
    index = {}
    for key, (status, ctype, body) in sorted(rec.seen.items()):
        if status != 200:
            raise SystemExit(f"{key}: HTTP {status}")
        if "pdf" in ctype:
            name = slug(key) + ".pdf"
            (HERE / name).write_bytes(body)
        else:
            name = slug(key) + ".json"
            data = trim(json.loads(body))
            if key.endswith("/$everything") and key.split("/")[-2] in ORDERS_ONLY:
                data["entry"] = [e for e in data["entry"] if e["resource"]["resourceType"] not in REPORT_TYPES]
            (HERE / name).write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
        index[key] = name
    (HERE / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    print(f"{len(index)} fixtures written to {HERE}")


if __name__ == "__main__":
    main()
