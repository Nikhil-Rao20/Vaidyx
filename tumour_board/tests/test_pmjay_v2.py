"""V2 item 6.4: the PM-JAY HBP 2.2 board composition is checked only for an empanelled hospital; a surgeon from a department outside the
hospital's surgical oncology list fills the surgical seat with a "check PM-JAY requirement" flag (review, never a block); the dashboard
quorum and the minutes follow. Synthetic data, no model calls."""
import asyncio, copy, json

import pytest

from tumour_board import access, agents, board, dept_requests, his_case, metrics, notify, org, postboard, rules, service, store
from tumour_board.tests import util
from tumour_board.tests.test_board_v2 import DATE, COORD, BREAST, MEDONC, RAD, GYN, ADMIN, UNPLACED, _case, _hospital, _decide, cases  # noqa: F401


def test_composition_not_applicable_when_the_hospital_is_not_empanelled(data_root):
    att = {"present": ["Medical Oncology"], "members": []}
    c = postboard.composition({"attendance": att})
    assert c["checked"] and c["missing"] == ["surgical_oncology", "radiation_oncology"] and postboard._composition_flag(c)["severity"] == "review"
    _hospital(pmjay_empanelled=False)
    c = postboard.composition({"attendance": att})
    assert c == {"checked": False, "not_applicable": True, "how": None, "present": [], "missing": [], "reference": postboard.PMJAY_REFERENCE, "reason": postboard.NOT_EMPANELLED,
                 "seat": {"filled": False, "filled_by": [], "check": False, "note": ""}, "seat_note": ""}
    assert postboard._composition_flag(c) is None
    assert postboard._composition_flag(postboard.composition({"participants": "Dr A, Dr B"})) is None  # nothing to check either


def test_surgeon_outside_the_pmjay_list_fills_the_seat_with_a_check_flag(data_root):
    att = {"present": ["Medical Oncology", "Radiation Oncology", "Breast Surgery"], "members": [{"name": "Dr Meera Nair", "department": "breast_surgery"}]}
    c = postboard.composition({"attendance": att})
    assert c["missing"] == [] and c["present"] == ["surgical_oncology", "radiation_oncology", "medical_oncology"]
    assert c["seat"] == {"filled": True, "filled_by": ["breast_surgery"], "check": True, "note": "Surgical seat filled by Breast Surgery: check the PM-JAY requirement, which names a Surgical Oncologist"}
    f = postboard._composition_flag(c)
    assert f["severity"] == "review" and f["check"] == "surgical_seat" and f["missing"] == [] and "check the PM-JAY requirement" in f["text"] and "not a block" in f["text"]
    c = postboard.composition({"attendance": {"present": ["Medical Oncology", "Radiation Oncology", "Gynaecologic Oncology"], "members": []}})
    assert c["missing"] == [] and c["seat"]["check"] is False and postboard._composition_flag(c) is None  # on the hospital's PM-JAY surgical oncology list
    c = postboard.composition({"attendance": {"present": ["Medical Oncology", "Breast Surgery"], "members": []}})
    assert c["missing"] == ["radiation_oncology"] and "check the PM-JAY requirement" in postboard._composition_flag(c)["text"]
    assert postboard.pmjay_present({"medical_oncology", "urology"}) == {"medical_oncology", "surgical_oncology"}
    assert postboard.pmjay_present({"medical_oncology", "dermatology"}) == {"medical_oncology"}


def test_dashboard_quorum_follows_empanelment(cases):
    s = board.create(DATE, "anil", case_ids=["TB-BR"])
    for d in ("medical_oncology", "radiation_oncology", "breast_surgery"):
        board.set_attendance(s["id"], d, "present", "anil")
    board.start(s["id"], "anil"); board.close(s["id"], "anil")
    d = metrics.dashboard()["kpis"]["during"]
    assert d["pmjay_empanelled"] is True and d["quorate_n"] == 1 and d["quorate_pct"] == 100  # the breast surgeon fills the seat
    _hospital(pmjay_empanelled=False)
    d = metrics.dashboard()["kpis"]["during"]
    assert d["pmjay_empanelled"] is False and d["quorate_n"] is None and d["quorate_pct"] is None


def test_minutes_say_pmjay_not_applicable_for_a_hospital_that_is_not_empanelled(cases):
    _hospital(pmjay_empanelled=False)
    s = board.create(DATE, "anil", case_ids=["TB-BR"])
    board.add_member(s["id"], "Dr Meera Nair", "breast_surgery", "anil")
    board.start(s["id"], "anil")
    _decide(s["id"], "TB-BR")
    m = board.minutes(s["id"])
    assert m["pmjay_empanelled"] is False and m["cases"][0]["decision"]["composition"]["not_applicable"] is True
    h = board.minutes_html(s["id"])
    assert "PM-JAY board composition: not applicable" in h and "check PM-JAY requirement" not in h
