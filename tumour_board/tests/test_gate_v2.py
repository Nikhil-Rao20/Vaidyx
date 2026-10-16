"""V2 item 0.2: the regression gate takes a version root (eval/v2/<label>) and the mock-hospital checks once they exist; V1 stays the default."""
import json
from pathlib import Path

import pytest

from tumour_board import config
from tumour_board.eval import gate_summary

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "tumour_board" / "eval" / "gate.sh"


def _run(root, label, mock_unit=None, conformance=None):
    """A run folder as gate.sh writes it: mock_unit = (passed, failed, rc) or None; conformance = (text, rc) or None."""
    d = root / label
    d.mkdir(parents=True)
    steps = [("ocr_engine", 0), ("unit", 0)] + ([("unit_his_mock", mock_unit[2])] if mock_unit else []) + ([("conformance", conformance[1])] if conformance else []) + [("e2e_api", 0)]
    (d / "run_timings.txt").write_text("".join(f"=== {s} started x\n=== {s} finished rc={rc} in 10 s\n" for s, rc in steps))
    (d / "ocr_engine.log").write_text("tesseract 5.3\n")
    (d / "unit.log").write_text("700 passed in 12.30s\n")
    (d / "e2e_api.log").write_text("PASS TB-001 ingest + gate  [12 docs in 40.0s, gate 2/5]\nPASS ask answered with citation  [6.1 s]\n\n150 passed, 0 failed: []\n")
    if mock_unit:
        (d / "unit_his_mock.log").write_text(f"{mock_unit[0]} passed" + (f", {mock_unit[1]} failed" if mock_unit[1] else "") + " in 1.20s\n")
    if conformance:
        (d / "conformance.log").write_text(conformance[0])
    return d


@pytest.fixture
def v2(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DEMO_CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(gate_summary, "V9_QA_MIN", None); monkeypatch.setattr(gate_summary, "V9_SUM_MIN", None)
    root = gate_summary.runs_dir("v2")
    _run(root, "baseline")
    return root


def _rows(root, label):
    md = (root / label / "gate_summary.md").read_text()
    return md, {ln.split("|")[1].strip(): [x.strip() for x in ln.split("|")[2:-1]] for ln in md.splitlines() if ln.startswith("| ") and "---" not in ln}


def test_version_root_is_separate_and_v1_stays_the_default(v2, tmp_path):
    assert v2 == tmp_path / "eval" / "v2" and gate_summary.runs_dir("v1") == tmp_path / "eval" / "v1"
    assert gate_summary.RUNS.name == "v1"  # main() without a root keeps the V1 behaviour


def test_mock_rows_are_skipped_until_the_mock_exists(v2):
    _run(v2, "r1")
    assert gate_summary.main("r1", "baseline", runs=v2) == 0
    md, rows = _rows(v2, "r1")
    assert rows["Mock hospital unit tests (V2)"][0] == "skipped" and rows["Mock hospital unit tests (V2)"][-1] == "skipped"
    assert rows["Mock HIS conformance (NRCeS v6.5.0 basics)"][0] == "skipped" and "GREEN" in md
    assert (v2 / "r1" / "gate_summary.md").exists() and not (gate_summary.RUNS / "r1").exists()


def test_mock_rows_count_when_run(v2):
    d = _run(v2, "r2", mock_unit=(42, 0, 0), conformance=("checked 11 resources\nCONFORMANCE OK: 11 resources checked\n", 0))
    n = gate_summary.numbers(d)
    assert (n["mock_unit_passed"], n["mock_unit_failed"], n["conformance_ok"], n["conformance_resources"]) == (42, 0, True, 11)
    assert gate_summary.main("r2", "baseline", runs=v2) == 0
    md, rows = _rows(v2, "r2")
    assert rows["Mock hospital unit tests (V2)"][0] == "42 passed, 0 failed" and rows["Mock hospital unit tests (V2)"][-1] == "yes"
    assert rows["Mock HIS conformance (NRCeS v6.5.0 basics)"][0] == "OK, 11 resources" and rows["Mock HIS conformance (NRCeS v6.5.0 basics)"][-1] == "yes"


@pytest.mark.parametrize("mock_unit,conformance", [((40, 2, 1), None), ((42, 0, 0), ("CONFORMANCE FAILED: Patient missing identifier\n", 1)),
                                                    ((42, 0, 0), ("crashed before the tally\n", 0)), ((0, 0, 0), None),
                                                    ((42, 0, 0), ("CONFORMANCE OK: 0 resources checked\n", 0)), ((42, 0, 0), ("CONFORMANCE OK\n", 0))])
def test_a_failing_or_crashed_mock_check_makes_the_run_red(v2, mock_unit, conformance):
    _run(v2, "r3", mock_unit=mock_unit, conformance=conformance)
    assert gate_summary.main("r3", "baseline", runs=v2) == 1
    assert "RED" in _rows(v2, "r3")[0]


def test_gate_script_keeps_v1_by_default_and_adds_the_mock_steps_under_v2():
    s = GATE.read_text()
    assert "VER=v1" in s and "--v2) VER=v2" in s and 'eval/$VER/$LABEL' in s
    assert 'if [ $VER = v2 ]' in s and "his_mock/tests" in s and "his_mock.eval.conformance" in s
    assert '--label "$VER-$LABEL"' in s and 'gate_summary "$LABEL" --version "$VER"' in s
