"""Test set-up: repo root on sys.path, and every test runs against a temporary data root, never data/tumour_board.

Fixtures are trimmed copies of the synthetic demo cases TB-001..003 (watermarked SYNTHETIC). No real patient data."""
import asyncio, atexit, os, shutil, sys, tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
_SAFE_ROOT = tempfile.mkdtemp(prefix="tb-unit-")
os.environ["TB_DATA_ROOT"] = _SAFE_ROOT  # before tumour_board.config is imported
atexit.register(shutil.rmtree, _SAFE_ROOT, True)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

from tumour_board import config, protocol, store  # noqa: E402
from tumour_board.tests import util  # noqa: E402


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    """Point storage at an empty temporary data root for every test."""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "CASES_DIR", tmp_path / "cases")
    store._docs_cache.clear()
    yield tmp_path
    store._docs_cache.clear()


class _NoGuidelines:
    chunks = []

    def search(self, q, k=8, cancer=None, sources=None):
        return []


@pytest.fixture(autouse=True)
def no_guideline_index(monkeypatch):
    """The shared guideline index (the whole library, embedded on CPU) is never built in the unit suite: guidelines.index() is an empty
    stub. Tests of the index build their own GuidelineIndex on a temporary folder; agent tests patch packs.search."""
    from tumour_board import guidelines
    monkeypatch.setattr(guidelines, "index", lambda: _NoGuidelines())


class _NoCaseIndex:
    def search(self, q, k=60):
        return []


@pytest.fixture(autouse=True)
def no_case_index(monkeypatch):
    """The Case File search index (chunk embeddings on CPU, about 14 s to load the model) is never built in the unit suite: every
    ingestion job ends by warming it (service.process_docs), which made whichever test first awaited a job take 14 to 17 s.
    search.index() is an empty stub; no unit test reaches the embedding search (context_for fits the whole Case File)."""
    from tumour_board import search
    monkeypatch.setattr(search, "index", lambda case_id: _NoCaseIndex())


@pytest.fixture
def demo_cases(data_root):
    """TB-001 (lung), TB-002 (breast), TB-003 (rectum) copied into the temporary data root."""
    shutil.copytree(FIXTURES / "cases", data_root / "cases")
    return data_root / "cases"


@pytest.fixture
def unit_case(monkeypatch):
    """An empty Case File under the small test protocol `unit` (see util.UNIT_PROTOCOL)."""
    real_get = protocol.get
    monkeypatch.setattr(protocol, "get", lambda pid: util.unit_protocol() if pid == "unit" else real_get(pid))
    store.create_case("TB-UNIT", util.PATIENT, "unit", created_by="test")
    return "TB-UNIT"


@pytest.fixture
def run(unit_case, monkeypatch):
    """Run extract.process_document on a synthetic text with ingest / classify / extract_facts replaced by fakes."""
    from tumour_board import extract, ingest

    def _run(text=util.TEXT, cls=None, raw=None, filename="cbc_report.txt", page_extra=None, patient=None, protocol_id="lung_nsclc"):
        doc = store.add_document_file(unit_case, filename, b"synthetic")
        pages = [{"text": text, "method": "text-layer", **(page_extra or {})}]

        async def fake_pages(path, audit=None):
            return pages

        async def fake_classify(t, audit=None):
            return {**util.CLS, **(cls or {})}

        async def fake_facts(t, fids, audit=None):
            return {k: v for k, v in (util.RAW if raw is None else raw).items() if k in fids}
        monkeypatch.setattr(ingest, "extract_pages", fake_pages)
        monkeypatch.setattr(extract, "classify", fake_classify)
        monkeypatch.setattr(extract, "extract_facts", fake_facts)
        return asyncio.run(extract.process_document(unit_case, doc["doc_id"], protocol_id, patient or {"mrn": "SYN-900001", "name": "SYNTHETIC, Test Patient"}))
    return _run
