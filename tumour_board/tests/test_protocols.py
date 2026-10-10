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
        assert protocol.get(pid)["version"] == "0.4"


def test_every_protocol_parses():
    for p in config.PROTOCOL_DIR.glob("*.json"):
        json.loads(p.read_text())
