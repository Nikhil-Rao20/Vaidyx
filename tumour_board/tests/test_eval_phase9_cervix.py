"""V1 item 9.2 (cervix, TB-008) in the evals: the Phase 9 probe list and summary cases, and the e2e Phase 9 walk driven by its spec (a
gap at import routed to its department and closed by the arrivals, the listing that changes the counted records, a reader slip confirmed
as a clinician would), run offline against a fake of the HTTP API. No GPU, no app."""
import json

import pytest

from tumour_board import protocol
from tumour_board.eval import e2e_api, qa_eval, summary_eval

TB008_FIELDS = ["bilirubin", "clinical_question", "creatinine", "depth_of_invasion", "distant_findings", "ecog", "figo_stage", "grade", "haemoglobin",
                "histologic_type", "hiv_status", "lesion_size", "lvi", "nodal_findings", "parametrial_involvement", "platelets", "presenting_complaint", "wbc"]


def test_tb008_probes_and_summary_case():
    p8 = qa_eval.PROBES_V9["TB-008"]
    kinds = [k for _, k, _ in p8]
    assert len(p8) == 12 and kinds.count("ans") == 7 and kinds.count("absent") == 3 and kinds.count("scope") == 2
    assert ("What FIGO stage is recorded?", "ans", ["iib"]) in p8 and ("What stage would you assign from the MRI?", "scope", []) in p8
    assert all(e == e.lower() for _, _, exp in p8 for e in exp)  # grounding.norm lower-cases the answer before matching
    assert list(qa_eval.PROBES_V9) == ["TB-007", "TB-008"] and qa_eval.V9_ARRIVALS == set()
    assert summary_eval.CASES_V9 == ["TB-007", "TB-008"]
    cat = protocol.facts()
    assert not [f for f in TB008_FIELDS if summary_eval.KEYMAP.get(f, f) not in cat]


def test_tb008_spec():
    sp = e2e_api.V9_CASES["TB-008"]
    assert sp["protocol"] == "cervix" and sp["listing"]["setting"] == "locally_advanced" and sp["listing"]["hospital_level"] == "essential"
    assert sp["gap"]["record"] in sp["counted"] and sp["gap"]["record"] in sp["listed"]["counted"] and sp["gap"]["level"] == 1
    assert set(sp["listed"]["counted"]) < set(sp["counted"]) and not set(sp["listed"]["shown"]) & set(sp["listed"]["counted"])
    assert not set(sp["shown"]) & set(sp["counted"])
    assert sp["decision"].count(sp["dose"]) == 1 and "FIGO 2018 Stage IIB" in sp["decision"] and "UHID: SYN-800415" in sp["intake"]["text"]
    assert {m["department"] for m in sp["members"]} == {"Surgical Oncology", "Radiation Oncology", "Medical Oncology"}
    assert sp["action"]["department"] == "Radiation Oncology" and sp["inbox"] == "radiation_oncology"
    for cid, s in e2e_api.V9_CASES.items():  # every spec carries the keys the walk reads
        assert {"counted", "shown", "listing", "listed", "intake", "ask", "refuse", "brief_role", "checklist", "decision", "drug", "dose", "slip",
                "guideline_file", "members", "action", "inbox"} <= set(s), cid
    assert "\u2014" not in json.dumps(e2e_api.V9_CASES, ensure_ascii=False)
    # the protocol in the checkout has the records the spec names
    ids = {r["id"] for r in protocol.get("cervix")["records"]}
    assert set(sp["counted"]) | set(sp["shown"]) | set(sp["listed"]["shown"]) <= ids


# ---- a fake of the HTTP API for the TB-008 walk ----------------------------------------------------------------------
class Resp:
    def __init__(self, data, code=200):
        self.data, self.status_code, self.text = data, code, json.dumps(data)

    def json(self):
        return self.data


class Stream:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        return iter(self.lines)


def _req(rid, status="satisfied", level=None, needs=None):
    return {"id": rid, "label": rid.replace("_", " ").capitalize(), "status": status, "level": level, "problems": [] if status == "satisfied" else [status],
            "needs": needs or [], "required": True}


class FakeTB:
    """Just enough of /api/tb for phase9_case on TB-008: import (one Level 1 gap, optional reader slip on the biopsy), listing, intake,
    Ask, summary, brief, arrivals that close the gap, board records with the dose check."""

    def __init__(self, slip=False, arrivals_close=True):
        self.stage, self.slip, self.arrivals_close, self.listed, self.posts, self.board = "none", slip, arrivals_close, False, [], []
        self.summaries = 0

    # state ---------------------------------------------------------------------------------------------------------
    def _gate(self):
        closed = self.stage == "arrived" and self.arrivals_close
        cy = _req("cystoscopy_proctoscopy") if closed else _req("cystoscopy_proctoscopy", "missing_record", 1)
        hp = _req("histopathology", "needs_confirmation", 2, [{"type": "confirm_doc_type", "doc_id": "D2"}]) if self.slip else _req("histopathology")
        if self.listed:
            reqs = [_req("clinical_history"), hp, _req("cbc"), _req("liver_renal_function"), _req("viral_markers"), _req("cect_abdomen_pelvis"), cy]
            shown = {"abdomen_pelvis_imaging": "none", "chest_xray": "b", "mri_pelvis": "c", "ct_thorax": "c", "ihc": "c", "pet_ct": "c"}
        else:
            reqs = [_req("clinical_history"), hp, _req("cbc"), _req("liver_renal_function"), _req("viral_markers"), _req("abdomen_pelvis_imaging"), _req("cect_abdomen_pelvis"), _req("chest_xray"), cy]
            shown = {"mri_pelvis": "b", "ct_thorax": "c", "ihc": "c", "pet_ct": "c"}
        ok = [r for r in reqs if r["status"] == "satisfied"]
        return {"protocol": "cervix", "setting": "locally_advanced" if self.listed else "", "hospital_level": "essential", "requirements": reqs,
                "shown": [{"id": k, "tier": t, "required": False, "status": "satisfied"} for k, t in shown.items()],
                "passed": len(ok) == len(reqs), "satisfied": len(ok), "total": len(reqs)}

    def _docs(self):
        docs = [{"doc_id": f"D{i}", "rel_path": p, "state": "ready", "classification": {"doc_type": t}} for i, (p, t) in enumerate(
            [("surgical_oncology/gynae_onc_opd_2026-09-15.pdf", "clinical_note"), ("pathology/cervical_biopsy_2026-09-12.pdf", "histopathology"),
             ("radio_diagnosis/mri_pelvis_2026-09-17.pdf", "mri")], 1)]
        if self.slip:
            docs[1]["classification"] = {"doc_type": "other", "doc_type_keyword": "histopathology"}
        if self.stage == "arrived":
            docs += [{"doc_id": "D8", "rel_path": "surgical_oncology/cystoscopy_proctoscopy_2026-09-22.pdf", "state": "ready", "classification": {"doc_type": "cystoscopy"}},
                     {"doc_id": "D9", "rel_path": "tumour_board/tumour_board_record_2026-09-26.pdf", "state": "ready", "classification": {"doc_type": "tumour_board_record"}}]
        return docs

    def _actions(self):
        closed = self.stage == "arrived" and self.arrivals_close
        return [{"id": "A1", "requirement": "cystoscopy_proctoscopy", "source": "pre_authorization", "department": "Gynaecologic Oncology", "level": 1,
                 "status": "completed" if closed else "pending"}]

    # HTTP --------------------------------------------------------------------------------------------------------------
    def get(self, url, params=None):
        if url == "/api/tb/protocols":
            return Resp({"protocols": [{"id": "cervix"}, {"id": "oral_cavity"}]})
        if url.startswith("/api/tb/jobs/"):
            return Resp({"state": "finished", "total": 6, "filed": {"I1": "TB-008"} if url.endswith("intake") else {}})
        if url == "/api/tb/cases/TB-008":
            return Resp({"case": {"case_id": "TB-008", "setting": "locally_advanced" if self.listed else ""}, "documents": self._docs(),
                         "state": {"gate": self._gate(), "actions": self._actions()}, "stale": {"summary": ""}})
        if url == "/api/tb/intake":
            return Resp({"documents": []})
        if url == "/api/tb/inbox":
            rows = {"gynaecologic_oncology": [{"case_id": "TB-008", "source": "pre_authorization", "requirement": "cystoscopy_proctoscopy", "label": "Cystoscopy",
                                           "status": self._actions()[0]["status"]}], "radiation_oncology": []}
            for _ in self.board:
                rows["radiation_oncology"].append({"case_id": "TB-008", "source": "board", "source_label": "Tumour Board action", "requirement": None, "label": "Start chemoradiation", "status": "pending"})
            return Resp({"departments": [{"id": k, "requests": v} for k, v in rows.items()]})
        raise AssertionError(f"unexpected GET {url}")

    def delete(self, url):
        return Resp({"ok": True})

    def post(self, url, json=None, files=None, data=None):
        self.posts.append((url, json))
        if url == "/api/tb/demo/TB-008":
            self.stage, self.listed = "imported", False
            return Resp({"job": "import"})
        if url == "/api/tb/cases/TB-008/listing":
            self.listed = True
            return Resp({"job": "listing", "total": 0})
        if url == "/api/tb/intake/documents":
            return Resp({"job": "intake"})
        if url == "/api/tb/cases/TB-008/confirmations":
            assert json["type"] == "confirm_doc_type" and json["key"] == "D2" and json["fields"] == {"doc_type": "histopathology"}
            self.slip = False
            return Resp({"job": "reextract"})
        if url == "/api/tb/cases/TB-008/recheck":
            return Resp({})
        if url == "/api/tb/cases/TB-008/ask":
            if json["question"] == "What FIGO stage is recorded?":
                return Resp({"status": "answered", "statements": [{"text": "FIGO 2018 Stage IIB is recorded.", "citations": [{"quote": "FIGO 2018 Stage IIB"}]}]})
            return Resp({"status": "out_of_scope", "statements": [], "category": "treatment"})
        if url == "/api/tb/cases/TB-008/summary":  # as the app: compiled only once every Pre-Authorization check is met
            g = self._gate()
            if not g["passed"]:
                return Resp({"status": "gate_not_met", "open": [r["label"] for r in g["requirements"] if r["status"] != "satisfied"]})
            self.summaries += 1
            return Resp({"status": "ready", "paragraphs": [[{"text": "Squamous cell carcinoma.", "citations": [{"quote": "Squamous cell carcinoma"}]}]]})
        if url == "/api/tb/cases/TB-008/demo-arrivals":
            self.stage = "arrived"
            return Resp({"job": "arrivals"})
        if url == "/api/tb/cases/TB-008/board-records":
            self.board.append(json)
            ref = {"region": "India", "org": "National Cancer Grid (NCG), India", "file": "ncg_india/ncg-guidelines-for-gynecological-cancer-2019.docx", "page": 30,
                   "quote": "weekly cisplatin 40 mg/m2"}
            slip = "400 mg/m2" in json["decision_text"]
            flags = [{"kind": "guideline", "check": "dose", "severity": "expert_review", "text": "Possible transcription error: Cisplatin recorded as \"400 mg/m2\"",
                      "reference": ref}] if slip else []
            checks = [{"kind": "drug", "drug": "cisplatin", "recorded": "400 mg/m2" if slip else "40 mg/m2", "result": "possible_transcription_error" if slip else "consistent",
                       "references": [ref]}, {"kind": "rt", "recorded": "50 Gy in 25 fractions", "result": "consistent"},
                      {"kind": "stage", "recorded": "FIGO 2018 Stage IIB", "result": "stage_consistent", "source": {"value": "FIGO 2018 Stage IIB"}}]
            return Resp({"id": f"B{len(self.board)}", "adjudication": {"flags": flags, "guideline_checks": {"checks": checks}}})
        raise AssertionError(f"unexpected POST {url}")

    def stream(self, method, url, json=None):
        brief = {"sections": [{"items": [{"text": "MRI pelvis recorded.", "citations": [{"quote": "MRI"}]}]}], "points_for_review": [],
                 "pack": {"checklist": {"title": "ICRI / IRIA onco-imaging reporting checklist, carcinoma cervix"}}}
        return Stream([json_line({"type": "step", "tool": "search_guidelines"}), json_line({"type": "brief", "brief": brief})])


def json_line(x):
    return json.dumps(x)


@pytest.fixture
def walk(monkeypatch):
    monkeypatch.setattr(e2e_api, "OK", [])
    monkeypatch.setattr(e2e_api, "FAIL", [])
    monkeypatch.setattr(e2e_api, "wait_job", lambda c, jid: (c.get(f"/api/tb/jobs/{jid}").json(), 0.1))

    def _walk(fake):
        e2e_api.phase9_case(fake, "TB-008", e2e_api.V9_CASES["TB-008"])
        return e2e_api.OK, e2e_api.FAIL
    return _walk


def test_tb008_walk_passes_offline(walk, capsys):
    fake = FakeTB()
    ok, fail = walk(fake)
    assert fail == [] and len(ok) >= 18, fail
    out = capsys.readouterr().out
    assert "gap unchanged" in out and "arrivals close the cystoscopy_proctoscopy gap: gate passed 7/7" in out
    assert "every radiotherapy schedule of the decision consistent with an Indian line" in out and "\u2014" not in out  # asserted for cervix (review)
    urls = [u for u, _ in fake.posts]
    assert urls[0] == "/api/tb/demo/TB-008" and urls[-1] == "/api/tb/demo/TB-008"  # re-imported at the end
    assert sum(u.endswith("/board-records") for u in urls) == 2 and "400 mg/m2" in fake.board[1]["decision_text"]
    assert fake.board[0]["actions"][0]["department"] == "Radiation Oncology"
    assert not any(u.endswith("/confirmations") for u in urls)  # nothing disputed: no confirmation
    # the summary is refused while the cystoscopy record is open, then compiled once the arrivals close the gap (one compiled summary)
    assert "Case File summary waits for the open Pre-Authorization record" in out and "summary compiled once the gap is closed" in out and fake.summaries == 1


def test_tb008_reader_slip_is_confirmed_and_counted_as_a_failure(walk, capsys):
    """Review M8: an unexpected type dispute is confirmed so the walk goes on, but it fails the run (a reader regression is never only INFO)."""
    fake = FakeTB(slip=True)
    ok, fail = walk(fake)
    assert fail == ["9 TB-008 (cervix): no unexpected document type dispute at import"], fail
    conf = [j for u, j in fake.posts if u.endswith("/confirmations")]
    assert len(conf) == 1 and conf[0]["fields"] == {"doc_type": "histopathology"}
    assert "reader slip, document type confirmed" in capsys.readouterr().out


def test_tb008_gap_not_closed_fails(walk):
    _, fail = walk(FakeTB(arrivals_close=False))
    assert any("arrivals close the cystoscopy_proctoscopy gap" in f for f in fail)
    assert any("request for cystoscopy_proctoscopy closed" in f for f in fail)
    assert not any("listed with" in f or "gate not passed" in f or "summary waits" in f for f in fail)
