"""MCP (12 Oct): the read-only Vaidyx-TB server and the connectors client, in process (httpx ASGI transport, stateless servers).

Covers: every server tool is annotated read-only and the protected Case File stays hidden; the bearer check refuses a wrong
token; connector validation; a connector is usable only when all its tools are read-only and the records protocol is complete;
records listed for a Case File are marked when already present; a fetch hands the files to the intake pipeline as the
connector's department (the pipeline itself is replaced by a fake here) and is audited."""
import asyncio, base64, hashlib, json

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from tumour_board import config, connectors, mcp_server, service, store
from tumour_board.demo_data import demo_his_mcp
from tumour_board.tests.util import add, fact, make_doc

TOKEN = "unit-token"
# in-process servers: one JSON answer per request, no session, and no DNS-rebinding guard (the ASGI transport sends no port in Host)
INPROC = dict(stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


class _InProcess:
    """An httpx client bound to an in-process MCP app whose startup (the SDK's session manager) is run for the test."""

    def __init__(self, app, token=TOKEN):
        self.app, self.token = app, token

    async def __aenter__(self):
        self._life = self.app.router.lifespan_context(self.app)
        await self._life.__aenter__()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1", headers={"Authorization": f"Bearer {self.token}"})
        return self.client

    async def __aexit__(self, *a):
        await self.client.aclose()
        await self._life.__aexit__(*a)


def _client_for(app, token=TOKEN):
    return _InProcess(app, token)


def _demo_app(index):
    """The demo HIS as a stateless JSON MCP app over a fake records index."""
    demo_his_mcp._index = lambda corpus=None: index
    return demo_his_mcp.http_app(demo_his_mcp.build(**INPROC), expected=TOKEN)


def _index(tmp_path):
    f = tmp_path / "mri_brain_2026-09-14.txt"; f.write_text("SYNTHETIC\nMRI BRAIN REPORT\nNo intracranial metastasis.\nReport status: FINAL\n")
    g = tmp_path / "cbc_2026-09-14.txt"; g.write_text("SYNTHETIC\nHAEMATOLOGY REPORT\nHaemoglobin 12.4 g/dL\n")
    recs = [{"record_id": "r1", "filename": "02_radiology/mri_brain_2026-09-14.txt", "record_type": "radiology", "record_date": "2026-09-14", "department": "Radio-diagnosis", "size": f.stat().st_size, "_path": str(f)},
            {"record_id": "r2", "filename": "05_lab/cbc_2026-09-14.txt", "record_type": "lab", "record_date": "2026-09-14", "department": "Laboratory Medicine", "size": g.stat().st_size, "_path": str(g)}]
    return {"SYN-900001": {"patient": {"patient_id": "SYN-900001", "name": "SYNTHETIC, Test Patient", "age_sex": "60 Y / M"}, "case_id": "TB-UNIT", "records": recs}}


CONN = {"id": "demo_his", "label": "Demo HIS", "url": "http://127.0.0.1/mcp", "token": TOKEN, "department": "Radio-diagnosis", "enabled": True}


def test_connector_validation_and_save_hide_the_token():
    with pytest.raises(ValueError):
        connectors.validate({**CONN, "url": "ftp://x"})
    with pytest.raises(ValueError):
        connectors.validate({**CONN, "department": "Astrology"})
    with pytest.raises(ValueError):
        connectors.validate({**CONN, "id": "Demo HIS"})
    saved = connectors.save([CONN], by="admin")
    assert saved[0]["department"] == "radiology" and saved[0]["token"] == TOKEN
    assert connectors.public(saved[0])["has_token"] is True and "token" not in connectors.public(saved[0])
    kept = connectors.save([{**CONN, "token": "", "keep_token": True}], by="admin")  # an edit without retyping the token keeps it
    assert kept[0]["token"] == TOKEN
    with pytest.raises(ValueError):
        connectors.save([CONN, CONN], by="admin")
    assert json.loads((config.DATA_ROOT / "org_audit.jsonl").read_text().splitlines()[-1])["kind"] == "connectors_saved"


def test_probe_usable_only_when_read_only_and_protocol_complete(tmp_path):
    app = _demo_app(_index(tmp_path))
    pr = asyncio.run(connectors.probe(CONN, _client_for(app)))
    assert pr["ok"] and pr["usable"] and {t["name"] for t in pr["tools"]} == set(connectors.REQUIRED_TOOLS) and all(t["read_only"] for t in pr["tools"])
    bad = asyncio.run(connectors.probe({**CONN, "token": "wrong"}, _client_for(app, "wrong")))
    assert bad["ok"] is False and bad["usable"] is False
    # a server with a writing tool, or without the records protocol, is refused
    m = FastMCP("writer", **INPROC)
    m.tool(name="find_patient", annotations=ToolAnnotations(readOnlyHint=True))(lambda query: {"patients": []})
    m.tool(name="delete_record", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))(lambda record_id: {"ok": True})
    pr2 = asyncio.run(connectors.probe(CONN, _client_for(demo_his_mcp.http_app(m, expected=TOKEN))))
    assert pr2["ok"] and not pr2["usable"] and "read-only" in pr2["reason"] and "delete_record" in pr2["reason"]
    m2 = FastMCP("partial", **INPROC)
    m2.tool(name="find_patient", annotations=ToolAnnotations(readOnlyHint=True))(lambda query: {"patients": []})
    pr3 = asyncio.run(connectors.probe(CONN, _client_for(demo_his_mcp.http_app(m2, expected=TOKEN))))
    assert pr3["ok"] and not pr3["usable"] and "missing" in pr3["reason"] and "fetch_record" in pr3["reason"]


def test_available_records_marks_files_already_in_the_case_file(unit_case, tmp_path):
    add(unit_case, make_doc("Dmri00001", "mri", filename="02_radiology/mri_brain_2026-09-14.txt"))
    app = _demo_app(_index(tmp_path))
    av = asyncio.run(connectors.available_records(unit_case, CONN, _client_for(app)))
    assert av["patient"]["patient_id"] == "SYN-900001" and av["matched_on"] == "SYN-900001"
    assert {r["record_id"]: r["in_case_file"] for r in av["records"]} == {"r1": True, "r2": False}
    assert store.read_audit(unit_case)[-1]["kind"] == "connector_records_listed"
    none = asyncio.run(connectors.available_records(unit_case, CONN, _client_for(_demo_app({}))))
    assert none["patient"] is None and none["records"] == []


def test_fetch_hands_files_to_intake_as_the_connector_department(unit_case, tmp_path, monkeypatch):
    app = _demo_app(_index(tmp_path))
    seen = {}

    def fake_add_intake(files, department, user="", warn=True):
        seen.update(files=files, department=department, user=user)
        return {"id": "Jfake", "state": "queued"}
    monkeypatch.setattr(service, "add_intake_files", fake_add_intake)
    out = asyncio.run(connectors.fetch(unit_case, connectors.validate(CONN), ["r2", "nope"], user="coord", client=_client_for(app)))
    assert out["job"] == "Jfake" and [f["record_id"] for f in out["fetched"]] == ["r2"] and out["errors"][0]["record_id"] == "nope"
    rel, data = seen["files"][0]
    assert rel == "demo_his/05_lab/cbc_2026-09-14.txt" and b"Haemoglobin 12.4" in data and seen["department"] == "radiology" and "via connector demo_his" in seen["user"]
    assert hashlib.sha256(data).hexdigest() == out["fetched"][0]["sha256"]
    ev = store.read_audit(unit_case)[-1]
    assert ev["kind"] == "connector_fetch" and ev["by"] == "coord" and ev["job"] == "Jfake"


def test_server_tools_are_read_only_and_hide_protected_cases(unit_case, monkeypatch):
    add(unit_case, make_doc("Dhist0001", "histopathology", facts={"histologic_type": fact("Adenocarcinoma")}, text="SYNTHETIC\nHISTOPATHOLOGY REPORT\nAdenocarcinoma\nReport status: FINAL"))
    from tumour_board import rules
    rules.evaluate(unit_case)
    m = mcp_server.build(**INPROC)
    assert all(t.annotations.readOnlyHint and t.annotations.destructiveHint is False for t in m._tool_manager.list_tools())
    app = mcp_server.http_app(m, expected=TOKEN)

    async def go(tok):
        async with connectors.session({"url": "http://127.0.0.1/mcp"}, _client_for(app, tok)) as s:
                names = [t.name for t in (await s.list_tools()).tools]
                cases = connectors._structured(await s.call_tool("list_cases", {}))
                case = connectors._structured(await s.call_tool("get_case", {"case_id": unit_case}))
                docs = connectors._structured(await s.call_tool("list_documents", {"case_id": unit_case}))
                txt = connectors._structured(await s.call_tool("read_document", {"case_id": unit_case, "doc_id": "Dhist0001"}))
                gaps = connectors._structured(await s.call_tool("get_gaps", {"case_id": unit_case}))
                return names, cases, case, docs, txt, gaps
    names, cases, case, docs, txt, gaps = asyncio.run(go(TOKEN))
    assert "get_case" in names and "list_requests" in names and len(names) == 13
    assert [c["case_id"] for c in cases["cases"]] == [unit_case]
    assert case["verified_fields"][0]["value"] == "Adenocarcinoma" and case["gate"]["total"] >= 1
    assert docs["documents"][0]["doc_id"] == "Dhist0001" and "Adenocarcinoma" in txt["text"]
    assert gaps["listed"] and any(g["status"] != "satisfied" for g in gaps["gaps"])
    assert any(e["kind"] == "mcp_call" and e["tool"] == "get_case" for e in store.read_audit(unit_case))
    monkeypatch.setattr(config, "PROTECTED_CASES", {unit_case})
    hidden = mcp_server.list_cases()
    assert hidden["cases"] == []  # the real case never appears unless TB_MCP_INCLUDE_PROTECTED is set
    with pytest.raises(ValueError):
        mcp_server.get_case(unit_case)
    with pytest.raises(Exception):
        asyncio.run(go("wrong-token"))
