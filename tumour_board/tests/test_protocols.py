"""Protocol files: provenance notes name only sources whose text was used (V1 item 1.6), and every file parses."""
import json

from tumour_board import config, protocol


def test_protocol_notes_do_not_cite_nccn():
    for p in config.PROTOCOL_DIR.glob("*.json"):
        assert "NCCN" not in p.read_text(), p.name


def test_lung_and_breast_notes_name_indian_sources_first():
    for pid in ("lung_nsclc", "breast"):
        note = protocol.get(pid)["note"]
        assert note.index("NCG") < note.index("ESMO") and "ICMR" in note
        assert "to be rebuilt" not in note and "clinical review" in note
    assert {pid: protocol.get(pid)["version"] for pid in ("lung_nsclc", "breast", "colorectal_rectum")} == {
        "lung_nsclc": "0.6", "breast": "0.6", "colorectal_rectum": "0.5"}


def test_every_protocol_parses():
    for p in config.PROTOCOL_DIR.glob("*.json"):
        json.loads(p.read_text())


def test_lexicons_in_the_protocol_folder_are_not_protocols(tmp_path, monkeypatch):
    """facts.json and the lexicons (dates, units, document type keywords) share the folder: never listed or accepted as a protocol."""
    import json
    from tumour_board import config, protocol
    d = tmp_path / "protocols"; d.mkdir()
    (d / "facts.json").write_text(json.dumps({"doc_types": ["lab"], "facts": {}}))
    (d / "dates.json").write_text(json.dumps({"_note": "lexicon", "labels": {}}))
    (d / "units.json").write_text(json.dumps({"_note": "lexicon", "families": []}))
    (d / "real.json").write_text(json.dumps({"id": "real", "label": "Real", "version": "0.1", "mandatory": [], "optional": []}))
    monkeypatch.setattr(config, "PROTOCOL_DIR", d)
    assert [p["id"] for p in protocol.list_protocols()] == ["real"]
    assert protocol.exists("real") and not protocol.exists("dates") and not protocol.exists("units") and not protocol.exists("facts") and not protocol.exists("")
