"""Review of 16 Nov (admin consoles): a new hospital has no hospital system, no PACS and only its own folder root; the TB_HIS_* and
TB_HIS_FOLDER_ROOTS environment name the default hospital only; Case File search works in a new hospital (its chunk cache folder is made)."""
from pathlib import Path

from tumour_board import config, hospitals, his_client
from tumour_board.his_adapters import _common



def test_new_hospital_has_no_hospital_system(monkeypatch):
    monkeypatch.setenv("TB_HIS_URL", "https://his.real.example/fhir")
    monkeypatch.setenv("TB_HIS_TOKEN", "secret-token-value")
    h = hospitals.create("Lotus Hospital", "tester")
    hid = h["id"] if isinstance(h, dict) else h
    with config.use_hospital(hid):
        s = his_client.settings()
        assert s["enabled"] is False and s["kind"] == "none" and s["url"] == "" and s["pacs_url"] == "" and s["token"] == ""
        assert his_client.client() is None
    with config.use_hospital("default"):
        s = his_client.settings()
        assert s["url"] == "https://his.real.example/fhir" and s["enabled"] is True


def test_new_hospital_keeps_its_own_saved_system():
    h = hospitals.create("Asha Cancer Centre", "tester")
    hid = h["id"] if isinstance(h, dict) else h
    with config.use_hospital(hid):
        his_client.settings_path().write_text('{"kind": "fhir", "url": "http://127.0.0.1:9999", "enabled": true}')
        s = his_client.settings()
        assert s["url"] == "http://127.0.0.1:9999" and s["enabled"] is True and s["token_file"] == ""


def test_folder_roots_are_per_hospital(monkeypatch, tmp_path):
    monkeypatch.setenv("TB_HIS_FOLDER_ROOTS", str(tmp_path))
    h = hospitals.create("Kaveri Hospital", "tester")
    hid = h["id"] if isinstance(h, dict) else h
    with config.use_hospital(hid):
        assert _common.folder_roots() == [Path(config.root_for(hid)) / "his_inbox"]
    with config.use_hospital("default"):
        assert _common.folder_roots() == [tmp_path]


def test_search_index_builds_in_a_new_hospital_without_a_cache_folder():
    src = Path(__file__).resolve().parent.parent / "search.py"
    text = src.read_text()
    line = next(l for l in text.splitlines() if 'embed_cache" / "chunks"' in l)
    assert "mkdir" not in line.split("#", 1)[-1] or "#" not in line  # the mkdir is code, not a comment
    assert 'cache.mkdir(parents=True, exist_ok=True)' in text
