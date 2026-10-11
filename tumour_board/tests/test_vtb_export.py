"""NCG Virtual Tumour Board / RCC export (V1 item 4.6): the NCG VTB case template filled from a synthetic, verified Case File summary.
Reads the NCG template from the guideline library (read-only); no model calls."""
from io import BytesIO
from pathlib import Path

import pytest
from pptx import Presentation

from tumour_board import config, rules, store, vtb_export
from tumour_board.tests.util import add, fact, make_doc

FOOT = "Vaidyx footer"
TH = "Vaidyx treatment history"
HPE_TITLE = "HISTOPATHOLOGY REPORT (SYNTHETIC)"
CT_TITLE = "CECT THORAX REPORT (SYNTHETIC)"


def _cite(doc_id, quote):
    return {"doc_id": doc_id, "page": 0, "start": 0, "end": len(quote), "quote": quote}


def _summary(case_id, sections=None, points=True, stage=True, review=None, status="ready"):
    sec = {"presentation": [{"text": "The clinic note records cough for 3 months and weight loss.", "citations": [_cite("D1", "cough for 3 months")]}],
           "treatment_history": [],
           "investigations": [{"text": "The histopathology report records adenocarcinoma.", "citations": [_cite("D1", "Adenocarcinoma"), _cite("D1", "Adenocarcinoma")]}],
           "imaging": [{"text": "The CT report records a 3.2 cm mass in the right upper lobe.", "citations": [_cite("D2", "3.2 cm mass")]}],
           "fitness": [],
           "questions": [{"text": "The treating team asks whether the patient is suitable for surgery.", "citations": [_cite("D2", "suitable for surgery")]}]}
    sec.update(sections or {})
    titles = dict(presentation="Presenting complaints and examination", treatment_history="Treatment history", investigations="Investigations",
                  imaging="Imaging", fitness="Fitness for treatment", questions="Questions for the Tumour Board")
    summ = {"status": status, "sections": [{"id": k, "title": titles[k], "sentences": sec[k]} for k in titles],
            "points_for_review": [{"text": "The PD-L1 result is awaited.", "citations": [_cite("D1", "PD-L1 awaited")]}] if points else [],
            "stage_as_recorded": {"value": "cT2a N0 M0", "quote": "cT2a N0 M0", "doc_id": "D2", "doc_title": CT_TITLE, "date": "2026-09-03"} if stage else None,
            "review": review or {"status": "ai_draft"}, "generated": "2026-10-11T09:30:00", "model": "reasoner",
            "signature": rules.case_signature(case_id)}
    st = store.get_state(case_id)
    st.setdefault("artefacts", {})["summary"] = summ
    store.save_state(case_id, st)
    return summ


@pytest.fixture
def case(unit_case):
    c = store.get_case(unit_case)
    c["board_date"] = "2026-10-20"
    store.save_case(c)
    add(unit_case,
        make_doc("D1", "histopathology", date="2026-09-01", title=HPE_TITLE, facts={"histologic_type": fact("Adenocarcinoma")}),
        make_doc("D2", "ct", date="2026-09-03", title=CT_TITLE, region="thorax", facts={"lesion_size": fact("3.2 cm")}))
    return unit_case


def _deck(case_id):
    return Presentation(BytesIO(vtb_export.build(case_id)))


def _texts(slide):
    """The slide's main text: the content placeholder (slides 2 to 6) or, on slide 1 whose placeholder holds the NCG logo, the identity box."""
    ph = slide.placeholders[1]
    tf = ph.text_frame if ph.has_text_frame else _shape(slide, "Vaidyx case identity").text_frame
    return [p.text for p in tf.paragraphs]


def _shape(slide, name):
    return next((s for s in slide.shapes if s.name == name), None)


def _all_text(prs):
    return "\n".join(s.text_frame.text for sl in prs.slides for s in sl.shapes if s.has_text_frame)


def test_build_fills_all_six_slides(case):
    _summary(case)
    prs = _deck(case)
    assert len(prs.slides) == 6
    for sl in prs.slides:
        assert [t for t in _texts(sl) if t.strip()], "every slide has its section text"
        assert any(hasattr(s, "image") and s.image.blob for s in sl.shapes), "the NCG logo stays"
    for sl in list(prs.slides)[1:]:
        assert sl.placeholders[1].text_frame.text.strip()
    assert prs.slides[0].placeholders[1].image.blob  # slide 1's placeholder is the NCG logo picture, untouched
    assert "Presenting complaints" in _all_text(prs) and "Questions for the" in _all_text(prs)  # template titles kept
    assert vtb_export.filename(case) == "TB-UNIT_ncg_vtb_case.pptx"


def test_slide1_identity_and_intro_lines(case):
    _summary(case)
    s1 = _deck(case).slides[0]
    assert _texts(s1) == ["Tumour Board Case File TB-UNIT", "SYNTHETIC, Test Patient; Age / sex: 60 Y / M; UHID / MRN SYN-900001"]
    ident = _shape(s1, "Vaidyx case identity")
    assert ident.top + ident.height <= s1.placeholders[1].top  # above the logo
    box = next(s for s in s1.shapes if not s.is_placeholder and s.has_text_frame and "presenter" in s.text_frame.text)
    lines = [p.text for p in box.text_frame.paragraphs]
    assert lines == ["Name of the presenter: Tumour Board coordinator (test)", "Name of the centre: (hospital name not set)",
                     f"Diagnosis: Adenocarcinoma [{HPE_TITLE}, 01/09/2026]", "Date of presentation: 20/10/2026"]


def test_identity_only_what_is_present(case):
    c = store.get_case(case); c["patient"] = {"name": "SYNTHETIC, Only Name"}; store.save_case(c)
    _summary(case)
    assert vtb_export.content(case)["slides"][0]["items"] == ["Tumour Board Case File TB-UNIT", "SYNTHETIC, Only Name"]


def test_incomplete_gate_line_and_unverified_diagnosis(case):
    add(case, make_doc("D1", "histopathology", date="2026-09-01", title=HPE_TITLE, facts={"histologic_type": fact("Adenocarcinoma", verification="needs_review")}))
    c = store.get_case(case); c["board_date"] = ""; store.save_case(c)
    _summary(case, status="incomplete_gate")
    s1 = _deck(case).slides[0]
    box = next(s for s in s1.shapes if not s.is_placeholder and s.has_text_frame and "presenter" in s.text_frame.text)
    lines = [p.text for p in box.text_frame.paragraphs]
    assert lines[2] == "Diagnosis: as recorded in the attached records"
    assert lines[3] == "INCOMPLETE: Pre-Authorization not met"
    assert lines[4] == "Date of presentation: to be fixed"


def test_citations_and_treatment_history_box(case):
    _summary(case)
    prs = _deck(case)
    s2 = prs.slides[1]
    assert _texts(s2) == [f"The clinic note records cough for 3 months and weight loss. [{HPE_TITLE}, 01/09/2026]"]
    ph = s2.placeholders[1]
    assert ph.top + ph.height <= 3429000  # ends above the template's "Treatment history" title
    th = _shape(s2, TH)
    assert th is not None and th.top >= ph.top + ph.height
    assert th.text_frame.text == vtb_export.NOT_DOCUMENTED
    # the same citation twice is shown once
    assert _texts(prs.slides[2]) == [f"The histopathology report records adenocarcinoma. [{HPE_TITLE}, 01/09/2026]"]
    assert _texts(prs.slides[4]) == [vtb_export.NOT_DOCUMENTED]


def test_treatment_history_sentences(case):
    _summary(case, sections={"treatment_history": [{"text": "The discharge summary records 4 cycles of chemotherapy.", "citations": [_cite("D2", "4 cycles")]}]})
    th = _shape(_deck(case).slides[1], TH)
    assert th.text_frame.text == f"The discharge summary records 4 cycles of chemotherapy. [{CT_TITLE}, 03/09/2026]"


def test_stage_line_only_on_slide4_and_only_when_present(case):
    _summary(case)
    prs = _deck(case)
    line = f"Stage as recorded in {CT_TITLE} (03/09/2026): cT2a N0 M0"
    assert _texts(prs.slides[3])[-1] == line
    for i, sl in enumerate(prs.slides):
        if i != 3:
            assert "Stage as recorded" not in "\n".join(s.text_frame.text for s in sl.shapes if s.has_text_frame)
    _summary(case, stage=False)
    assert "Stage as recorded" not in _all_text(_deck(case))


def test_questions_then_points_for_review(case):
    _summary(case)
    t = _texts(_deck(case).slides[5])
    assert t[0].startswith("The treating team asks")
    assert t[1] == vtb_export.POINTS_HEADING
    assert t[2] == f"The PD-L1 result is awaited. [{HPE_TITLE}, 01/09/2026]"
    _summary(case, points=False, sections={"questions": []})
    assert _texts(_deck(case).slides[5]) == [vtb_export.NOT_DOCUMENTED]


def test_footer_on_every_slide_ai_draft_and_reviewed(case):
    _summary(case)
    for sl in _deck(case).slides:
        f = _shape(sl, FOOT)
        assert f is not None and "Human oversight: AI draft, awaiting expert review." in f.text_frame.text
        assert "Generated 11/10/2026 09:30." in f.text_frame.text
        assert f.text_frame.paragraphs[0].runs[0].font.size.pt == 9
    _summary(case, review={"status": "reviewed", "by": "dr_rao"})
    assert all("Human oversight: reviewed by dr_rao." in _shape(sl, FOOT).text_frame.text for sl in _deck(case).slides)
    _summary(case, review={"status": "flagged", "by": "dr_rao", "comment": "x"})
    assert "flagged for correction" in vtb_export.content(case)["footer"]


def test_no_summary_raises(case):
    with pytest.raises(vtb_export.ExportNotReady, match="Compile the Case File summary first"):
        vtb_export.build(case)


def test_stale_after_new_document(case):
    _summary(case)
    add(case, make_doc("D3", "xray", date="2026-09-05"))
    assert vtb_export.content(case)["stale"].startswith("The Case File changed since this was generated")
    with pytest.raises(vtb_export.ExportNotReady) as e:
        vtb_export.build(case)
    assert str(e.value).startswith("The Case File changed since this was generated")
    assert str(e.value).endswith("; regenerate the summary before exporting")


def test_missing_template_names_the_path(case, monkeypatch, tmp_path):
    _summary(case)
    monkeypatch.setattr(config, "GUIDELINE_DIR", tmp_path / "nowhere")
    monkeypatch.delenv("TB_VTB_TEMPLATE", raising=False)
    with pytest.raises(vtb_export.ExportNotReady, match="nowhere"):
        vtb_export.build(case)
    monkeypatch.setenv("TB_VTB_TEMPLATE", str(tmp_path / "other.pptx"))
    with pytest.raises(vtb_export.ExportNotReady, match="other.pptx"):
        vtb_export.build(case)


def test_content_mirrors_the_slides(case):
    _summary(case, sections={"treatment_history": [{"text": "Surgery recorded.", "citations": [_cite("D1", "Surgery")]}]})
    data = vtb_export.content(case)
    prs = _deck(case)
    assert data["stale"] == "" and data["review"] == {"status": "ai_draft"}
    assert [s["n"] for s in data["slides"]] == [1, 2, 3, 4, 5, 6]
    for spec, sl in zip(data["slides"], prs.slides):
        assert _texts(sl) == spec["items"]
    assert _shape(prs.slides[1], TH).text_frame.text == "\n".join(data["slides"][1]["extra"]["treatment_history"])
    assert data["slides"][3]["extra"]["stage"].startswith("Stage as recorded in")


def test_long_section_is_capped_with_continuation(case):
    many = [{"text": f"Finding number {i} is recorded.", "citations": [_cite("D1", "x")]} for i in range(30)]
    _summary(case, sections={"investigations": many, "imaging": many[:12]})
    prs = _deck(case)
    t = _texts(prs.slides[2])
    assert len(t) == vtb_export.MAX_LINES and t[-1] == vtb_export.CONTINUED
    runs = [r for p in prs.slides[2].placeholders[1].text_frame.paragraphs for r in p.runs]
    assert all(r.font.size.pt == 12 for r in runs)
    # slide 4: more than 10 lines -> 12 pt, stage line kept, not cut
    t4 = _texts(prs.slides[3])
    assert len(t4) == 13 and t4[-1].startswith("Stage as recorded") and vtb_export.CONTINUED not in t4
    assert prs.slides[3].placeholders[1].text_frame.paragraphs[0].runs[0].font.size.pt == 12
    # a short slide stays at 14 pt
    assert prs.slides[1].placeholders[1].text_frame.paragraphs[0].runs[0].font.size.pt == 14


def test_stage_line_survives_a_cut(case):
    many = [{"text": f"Imaging finding {i}.", "citations": []} for i in range(25)]
    _summary(case, sections={"imaging": many})
    t = _texts(_deck(case).slides[3])
    assert len(t) == vtb_export.MAX_LINES and t[-2].startswith("Stage as recorded") and t[-1] == vtb_export.CONTINUED


def test_no_em_dash_anywhere(case):
    _summary(case, sections={"fitness": [{"text": "ECOG 1 \u2014 as recorded \u2013 in the note.", "citations": [_cite("D2", "ECOG 1")]}]})
    prs = _deck(case)
    text = _all_text(prs)
    assert "\u2014" not in text and "\u2013" not in text
    assert "ECOG 1, as recorded - in the note." in text


def test_template_is_not_modified(case):
    _summary(case)
    p = vtb_export.template_path()
    before = Path(p).read_bytes()
    vtb_export.build(case)
    assert Path(p).read_bytes() == before
