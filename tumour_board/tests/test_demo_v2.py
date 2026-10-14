"""V2 item 8.1: the pure parts of the end-to-end demo script (tumour_board/eval/demo_v2.py). No network, no model, no logins file
of the real demo: the helpers are fed hand-made data (SYNTHETIC)."""
import datetime

import pytest

from tumour_board.eval import demo_v2 as dv


def test_read_logins_skips_comments_and_never_needs_more_than_two_columns(tmp_path):
    f = tmp_path / "logins"
    f.write_text("# username<TAB>password<TAB>display name<TAB>roles\n\n"
                 "tb-breast-doc\tpw-one\tDr Breast Surgery (demo)\tBreast Surgery doctor\n"
                 "tb-mdt\tpw-two\n"
                 "   \n", encoding="utf-8")
    got = dv.read_logins(f)
    assert got == {"tb-breast-doc": ("pw-one", "Dr Breast Surgery (demo)"), "tb-mdt": ("pw-two", "tb-mdt")}
    assert dv.read_logins(tmp_path / "missing") == {}


def test_parse_steps_ranges_lists_and_errors():
    assert dv.parse_steps("1-6") == [1, 2, 3, 4, 5, 6]
    assert dv.parse_steps("1,2,5") == [1, 2, 5]
    assert dv.parse_steps("4-") == [4, 5, 6]
    assert dv.parse_steps("-2") == [1, 2]
    assert dv.parse_steps("3") == [3]
    assert dv.parse_steps("") == list(dv.STEPS)
    assert dv.parse_steps("2,2,1") == [1, 2]
    for bad in ("0-3", "7", "5-2", "x", "1-9"):
        with pytest.raises(ValueError):
            dv.parse_steps(bad)


def _detail(reqs, actions=()):
    return {"state": {"gate": {"requirements": reqs, "passed": not any(r["status"] not in ("satisfied", "not_applicable", "waived") for r in reqs)}, "actions": list(actions)}}


def test_gaps_and_row_and_action_for():
    d = _detail([{"id": "clinical_history", "status": "satisfied", "level": None},
                 {"id": "breast_imaging", "status": "not_final", "level": 1, "accession": "RAD/26/01019", "problems": ["Bilateral mammogram is PRELIMINARY: a final, signed version is required"]},
                 {"id": "usg_axilla", "status": "not_final", "level": 1},
                 {"id": "pet_ct", "status": "waived", "level": None}],
                [{"id": "A1", "requirement": "breast_imaging", "status": "suggested"}, {"id": "A2", "requirement": "breast_imaging", "status": "pending"},
                 {"id": "A3", "requirement": None, "status": "pending"}])
    assert dv.gaps(d) == [("breast_imaging", 1), ("usg_axilla", 1)]
    assert dv.row(d, "breast_imaging")["accession"] == "RAD/26/01019"
    assert dv.row(d, "nope") == {}
    assert dv.action_for(d, "breast_imaging")["id"] == "A2"  # the newest request of the requirement
    assert dv.action_for(d, "usg_axilla") == {}
    assert dv.gaps({}) == [] and dv.row({}, "x") == {}


def test_names_preliminary_mammogram_reads_the_problem_text():
    assert dv.names_preliminary_mammogram({"problems": ["Bilateral mammogram is PRELIMINARY: a final, signed version is required (HIS: preliminary)"]})
    assert dv.names_preliminary_mammogram({"problems": ["Mammography report is preliminary and unsigned"]})
    assert not dv.names_preliminary_mammogram({"problems": ["USG both breasts and axillae is PRELIMINARY"]})
    assert not dv.names_preliminary_mammogram({"problems": ["No breast imaging report in the Case File"]})
    assert not dv.names_preliminary_mammogram({})


def test_every_sentence_cited():
    assert dv.every_sentence_cited({"paragraphs": [[{"text": "a", "citations": [{"doc_id": "d1"}]}], [{"text": "b", "citations": [{"doc_id": "d2"}]}]]})
    assert not dv.every_sentence_cited({"paragraphs": [[{"text": "a", "citations": []}]]})
    assert not dv.every_sentence_cited({"paragraphs": []}) and not dv.every_sentence_cited({})


def test_default_board_date_is_the_next_friday_at_least_two_days_ahead():
    assert dv.default_board_date(datetime.date(2026, 10, 14)) == "2026-10-16"   # Wednesday -> Friday
    assert dv.default_board_date(datetime.date(2026, 10, 15)) == "2026-10-23"   # Thursday -> not tomorrow, next Friday
    assert dv.default_board_date(datetime.date(2026, 10, 16)) == "2026-10-23"   # Friday -> next Friday
    assert dv.default_board_date(datetime.date(2026, 10, 17)) == "2026-10-23"   # Saturday
    for d in range(30):
        got = datetime.date.fromisoformat(dv.default_board_date(datetime.date(2026, 10, 1) + datetime.timedelta(days=d)))
        assert got.weekday() == 4 and (got - (datetime.date(2026, 10, 1) + datetime.timedelta(days=d))).days >= 2


def test_order_id_is_the_mock_slug():
    assert dv.order_id("RAD/26/01019") == "rad-26-01019"
    assert dv.order_id("PATH/26/00461") == "path-26-00461"


def test_check_counts_and_prints(capsys):
    dv.OK.clear(); dv.FAIL.clear()
    assert dv.check("one", True) is True
    assert dv.check("two", False, "why") is False
    out = capsys.readouterr().out
    assert "PASS one" in out and "FAIL two" in out and "[why]" in out
    assert dv.OK == ["one"] and dv.FAIL == ["two"]
    dv.OK.clear(); dv.FAIL.clear()


def test_constants_are_synthetic_and_consistent():
    assert set(dv.ROLES) == {"breast", "rad", "mdt", "pulmo", "crs"}
    assert all(u.startswith("tb-") for u in dv.ROLES.values())
    assert all(c.startswith("TB-DEMO-") for c in dv.CASES.values()) and len(set(dv.CASES.values())) == 4
    assert dv.UHID_P19 == "VXH/26/004219" and dv.MG_ACCESSION == "RAD/26/01019" and dv.US_ACCESSION == "RAD/26/01020"
    assert "SYNTHETIC" in dv.SESSION_TITLE and "TB-2026-bharath" not in dv.CASES.values()
