"""Phase 9 review E (28 Oct 2026), part B: a brief a doctor flagged for correction is shown and spoken as flagged, never as an AI draft
(I2): the label "Flagged for correction by Dr <name>" in the brief view, the meeting tile and the brief_label of "Present your points",
and "Present your points" on a flagged brief is refused (409 brief_flagged) with a plain sentence; the "Dr" title is added unless the
name starts with the word Dr or Prof, so "Drishti" is titled (M8). Hermetic: the fixtures of test_nik_meetings (a fake login system,
synthetic Case Files, no model)."""
import pytest

from tumour_board import agents, helpers, live, meetings, rules, store
from tumour_board.tests.test_nik_meetings import As, app, join_and_admit, started, tc  # noqa: F401

CT_LINE = "Spiculated mass in the right upper lobe measuring 5.2 x 4.1 cm"  # TB-001's CECT thorax report (D41f9d46c), synthetic
POINT = "The CECT thorax reports a spiculated right upper lobe mass of 5.2 x 4.1 cm."
FLAG_NOTE = "This brief is flagged for correction by Dr Anil Kumar; its points are not read out until it is corrected."


@pytest.fixture(autouse=True)
def _fresh_agent_limits():
    from tumour_board.api import meetings as api_meetings
    for lim in (api_meetings.AGENT_ASK_LIMIT, api_meetings.AGENT_LIMIT):
        lim._hits.clear()
    yield


def _brief(case_id, role, review):
    """A brief of one point that cites a line in the Case File's records, with this review."""
    st = store.get_state(case_id)
    st.setdefault("artefacts", {})[f"brief_{role}"] = {
        "role": role, "label": agents.ROLES[role]["label"], "generated": "2026-10-28T10:00:00", "model": "fake", "seconds": 0.1,
        "version": agents.BRIEF_VERSION, "focus": "", "near_match": False, "sections": [], "not_documented": [], "review": review,
        "signature": rules.case_signature(case_id),
        "points_for_review": [{"text": POINT, "citations": [{"doc_id": "D41f9d46c", "doc_title": "", "date": None, "page": 0, "quote": CT_LINE}], "references": []}]}
    store.save_state(case_id, st)


NAMES = {"anil": "Anil Kumar", "priya": "Dr Priya Nair", "drishti": "Drishti Rao", "dr2": "Dr. Shah", "prof": "Prof Iyer"}


@pytest.mark.parametrize("rv,label", [
    ({"status": "reviewed", "by": "priya"}, "Reviewed by Dr Priya Nair"),
    ({"status": "reviewed", "by": "anil"}, "Reviewed by Dr Anil Kumar"),
    ({"status": "flagged", "by": "anil"}, "Flagged for correction by Dr Anil Kumar"),
    ({"status": "flagged", "by": "drishti"}, "Flagged for correction by Dr Drishti Rao"),
    ({"status": "reviewed", "by": "drishti"}, "Reviewed by Dr Drishti Rao"),
    ({"status": "reviewed", "by": "dr2"}, "Reviewed by Dr. Shah"),
    ({"status": "reviewed", "by": "prof"}, "Reviewed by Prof Iyer"),
    ({"status": "flagged", "by": "nobody@hospital.example"}, "Flagged for correction by nobody@hospital.example"),  # no name: the login as it is
    ({"status": "flagged"}, "Flagged for correction"),
    ({"status": "ai_draft"}, "AI draft, not reviewed"),
    ({}, "AI draft, not reviewed"),
    (None, "AI draft, not reviewed"),
])
def test_the_review_label_for_reviewed_flagged_and_draft(rv, label):
    assert helpers.review_label(rv, lambda u: NAMES.get(u, u)) == label


@pytest.mark.parametrize("name,titled", [("Drishti Rao", "Dr Drishti Rao"), ("Dr Rao", "Dr Rao"), ("dr. rao", "dr. rao"), ("DR RAO", "DR RAO"),
                                         ("Drew", "Dr Drew"), ("Prof. Iyer", "Prof. Iyer"), ("Professor Iyer", "Dr Professor Iyer"), ("", "")])
def test_the_dr_title_is_a_word_never_a_prefix_of_the_name(name, titled):
    assert helpers.dr_name(name) == titled


def test_the_brief_view_and_the_meeting_label_carry_the_flag(tc):
    _brief("TB-001", "pathology", {"status": "flagged", "by": "anil", "comment": "The size is from the older CT"})
    st = store.get_state("TB-001")
    art = st["artefacts"]["brief_pathology"]
    bv = helpers.brief_view(art, rules.case_signature("TB-001", st))
    assert bv["label"] == "Flagged for correction by Dr Anil Kumar" and bv["review"] == "flagged" and bv["flagged_by"] == "anil"
    assert bv["flagged_by_name"] == "Anil Kumar" and "reviewed_by" not in bv
    assert meetings._brief_label(art) == "Flagged for correction by Dr Anil Kumar"
    assert meetings.flagged_brief_note(art) == FLAG_NOTE
    # a reviewed brief keeps its "Reviewed" word in the view (the name beside it) and the full line in the meeting
    _brief("TB-001", "pathology", {"status": "reviewed", "by": "priya"})
    art = store.get_state("TB-001")["artefacts"]["brief_pathology"]
    assert helpers.brief_view(art, rules.case_signature("TB-001"))["label"] == "Reviewed" and meetings._brief_label(art) == "Reviewed by Dr Priya Nair"
    assert meetings.flagged_brief_note(art) == ""
    _brief("TB-001", "pathology", {"status": "ai_draft"})
    art = store.get_state("TB-001")["artefacts"]["brief_pathology"]
    assert helpers.brief_view(art, rules.case_signature("TB-001"))["label"] == "AI draft, not reviewed" and meetings._brief_label(art) == "AI draft, not reviewed"


def test_present_your_points_on_a_flagged_brief_is_refused_and_the_tile_says_flagged(tc, monkeypatch):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    monkeypatch.setattr(live, "broadcast", lambda m, ev, **kw: True)
    _brief("TB-001", "pathology", {"status": "flagged", "by": "anil", "comment": "synthetic"})
    tile = {a["role"]: a for a in As(tc, "priya").get(f"/meetings/{mid}").json()["agents"]}["pathology"]
    assert tile["brief"]["label"] == "Flagged for correction by Dr Anil Kumar" and tile["brief"]["review"] == "flagged"
    assert tile["points"] and tile["points"][0]["text"] == POINT  # the brief stays readable on the screen
    before = len(meetings.get(mid).get("questions") or [])
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {"message": FLAG_NOTE, "code": "brief_flagged"}
    assert len(meetings.get(mid).get("questions") or []) == before  # nothing saved, nothing spoken
    # once a doctor reviews it, the points are read out with the reviewer's name
    _brief("TB-001", "pathology", {"status": "reviewed", "by": "priya"})
    r = As(tc, "priya").post(f"/meetings/{mid}/agents/pathology/present")
    assert r.status_code == 200, r.text
    a = r.json()["question"]["answer"]
    assert a["status"] == "answered" and a["brief_label"] == "Reviewed by Dr Priya Nair" and [x["text"] for x in a["statements"]] == [POINT]
    tile = {a["role"]: a for a in As(tc, "priya").get(f"/meetings/{mid}").json()["agents"]}["pathology"]
    assert tile["brief"]["review"] == "reviewed" and tile["brief"]["reviewed_by_name"] == "Dr Priya Nair"
