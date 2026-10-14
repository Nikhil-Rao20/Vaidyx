"""V2 item 6.3: a hospital-system record whose PDF is missing on disk is fetched live from the HIS when opened, checked against the sha256
recorded at the first fetch, and audited; different bytes are refused. A fake HIS client, no network."""
import asyncio, copy, json

import pytest

from tumour_board import access, agents, board, config, dept_requests, his_case, metrics, notify, org, postboard, rules, service, store
from tumour_board.tests import util
from tumour_board.tests.test_board_v2 import DATE, COORD, BREAST, MEDONC, RAD, GYN, ADMIN, UNPLACED, _case, _hospital, _decide, cases  # noqa: F401


class _FakeHIS:
    def __init__(self, content, filename="report.pdf"):
        self.content, self.filename, self.calls = content, filename, []

    async def document(self, ref):
        self.calls.append(ref)
        return {"content": self.content, "filename": self.filename, "sha256": ""}


def test_fetch_file_restores_a_missing_his_pdf_and_refuses_different_bytes(data_root, monkeypatch):
    import hashlib
    _case("TB-H", owner="breast_surgery")
    data = b"%PDF-1.4 synthetic report"
    doc = store.add_document_file("TB-H", "report.pdf", data, "his/op/report.pdf")
    doc["his"] = {"document_ref": "DocumentReference/doc-1", "document_sha256": hashlib.sha256(data).hexdigest()}
    store.save_doc("TB-H", doc)
    p = store.original_path("TB-H", doc["doc_id"]); p.unlink()
    with pytest.raises(StopIteration):
        store.original_path("TB-H", doc["doc_id"])
    fake = _FakeHIS(data)
    monkeypatch.setattr(his_case, "_client", lambda: fake)
    out = asyncio.run(his_case.fetch_file("TB-H", doc, "meera"))
    assert out.read_bytes() == data and fake.calls == ["DocumentReference/doc-1"] and store.original_path("TB-H", doc["doc_id"]) == out
    assert any(e["kind"] == "document_fetched_live" and e["by"] == "meera" for e in store.read_audit("TB-H"))
    out.unlink()
    monkeypatch.setattr(his_case, "_client", lambda: _FakeHIS(b"%PDF-1.4 another file"))
    with pytest.raises(his_case.HISCaseError, match="differs") as ei:
        asyncio.run(his_case.fetch_file("TB-H", doc, "meera"))
    assert ei.value.status == 409 and not list(p.parent.glob("original.*"))
    assert any(e["kind"] == "document_fetch_live_failed" for e in store.read_audit("TB-H"))
    with pytest.raises(his_case.HISCaseError, match="did not come from the hospital system"):
        asyncio.run(his_case.fetch_file("TB-H", {"doc_id": "D0", "his": {}}, "meera"))
    # the bytes read at the first fetch win over the hash the HIS declared; a record without any hash is refused; the real case never written
    doc3 = store.add_document_file("TB-H", "report3.pdf", data, "his/op/report3.pdf")
    doc3["his"] = {"document_ref": "DocumentReference/doc-3", "document_sha256": "0" * 64}
    store.save_doc("TB-H", doc3); store.original_path("TB-H", doc3["doc_id"]).unlink()
    monkeypatch.setattr(his_case, "_client", lambda: _FakeHIS(data))
    assert asyncio.run(his_case.fetch_file("TB-H", doc3, "meera")).read_bytes() == data
    doc4 = {"doc_id": "D4", "sha256": "", "his": {"document_ref": "DocumentReference/doc-4", "document_sha256": ""}}
    with pytest.raises(his_case.HISCaseError, match="no recorded hash") as ei:
        asyncio.run(his_case.fetch_file("TB-H", doc4, "meera"))
    assert ei.value.status == 409 and any(e["kind"] == "document_fetch_live_failed" and e["reason"].startswith("no sha256") for e in store.read_audit("TB-H"))
    with pytest.raises(his_case.HISCaseError) as ei:
        asyncio.run(his_case.fetch_file(next(iter(config.PROTECTED_CASES)), doc3, "meera"))
    assert ei.value.status == 403
