"""dates.document_dates: labelled report and event dates (V1 item 3.1 b, c, d). Synthetic text only."""
import json
from pathlib import Path

import pytest

from tumour_board import config, dates, grounding
from tumour_board.tests.conftest import FIXTURES

TODAY = "2026-10-11"
TRUTH = config.DEMO_CORPUS / "truth"


def dd(text, doc_type="lab", **kw):
    kw.setdefault("today", TODAY)
    return dates.document_dates([text], kw.pop("filename", "report.pdf"), doc_type, **kw)


def kinds(r):
    return [(c["iso"], c["kind"]) for c in r["dates"]]


def grounded(r, texts):
    for k in ("report_date_quote", "event_date_quote"):
        if r[k]:
            assert grounding.locate(r[k], texts), r[k]
    for c in r["dates"]:
        assert grounding.locate(c["quote"], texts), c


# ---- Indian lab layouts --------------------------------------------------------------------------------------
def test_boxed_header_grid_from_a_scan():
    text = ("HAEMATOLOGY REPORT\nName | Mr. RAMESH KUMAR | UHID | SYN-1\nReg. Date | Collected on | Reported on\n"
            "04/09/2026 09:10 | 04/09/2026 | 05/09/2026\nHaemoglobin | 12.6 | gm%")
    r = dd(text)
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-09-04", "Collected on")
    assert (r["report_date_iso"], r["report_date_label"]) == ("2026-09-05", "Reported on")
    assert not r["report_date_assumed"] and not r["event_date_assumed"] and not r["date_unconfirmed"]
    assert "Reg. Date" in r["event_date_quote"] and "04/09/2026 09:10" in r["event_date_quote"]  # header + value cells
    grounded(r, [text])


def test_label_and_value_cells_in_one_row():
    text = ("Aadhaar No. | XXXX XXXX 2200 | Reg. date | 05/09/2026 08:02 | Collected on | 06/09/2026 08:10\n"
            "Reported on | 07/09/2026 12:40 | Ref. by | Dr. Anand Kulkarni")
    r = dd(text)
    assert kinds(r) == [("2026-09-05", "event_low"), ("2026-09-06", "event"), ("2026-09-07", "report")]
    assert (r["event_date_iso"], r["report_date_iso"]) == ("2026-09-06", "2026-09-07")


def test_space_separated_header_above_values_with_dob():
    text = ("LABORATORY INVESTIGATION REPORT\nName UHID Age / Sex\nSmt. Sunita Devi SYN-500263 52 Y / F\n"
            "DOB Reg. date Collected on\n02/01/1974 03/09/2026 09:12 04/09/2026 09:20\n"
            "Reported on Ref. by Sample ID\n05/09/2026 15:45 Dr. Pooja Hegde LAB/26/118011")
    r = dd(text)
    assert kinds(r) == [("1974-01-02", "ignore"), ("2026-09-03", "event_low"), ("2026-09-04", "event"), ("2026-09-05", "report")]
    assert (r["event_date_iso"], r["report_date_iso"]) == ("2026-09-04", "2026-09-05")
    grounded(r, [text])


def test_collected_on_and_reported_on_lines():
    r = dd("Sample collected on: 04/09/2026\nReported on: 05/09/2026\nHb 11.2 g/dL")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-09-04", "Sample collected on")
    assert (r["report_date_iso"], r["report_date_label"]) == ("2026-09-05", "Reported on")


def test_two_labels_on_one_line_nearest_wins():
    r = dd("Collected on 04/09/2026 Reported on 05/09/2026")
    assert (r["event_date_iso"], r["report_date_iso"]) == ("2026-09-04", "2026-09-05")


def test_reg_date_is_a_low_priority_event_for_labs_only():
    r = dd("Reg. Date: 04/09/2026\nSigned: 05/09/2026")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-09-04", "Reg. Date")
    r = dd("Reg. Date: 04/09/2026\nSigned: 05/09/2026", doc_type="ct")
    assert r["event_date_iso"] == "2026-09-05" and r["event_date_assumed"]


def test_received_on_used_only_when_no_collection_date():
    r = dd("Received on 29/08/2026\nSigned: 31/08/2026", doc_type="histopathology")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-08-29", "Received on")
    r = dd("Received on 29/08/2026\nDate of biopsy: 28/08/2026\nSigned: 31/08/2026", doc_type="histopathology")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-08-28", "Date of biopsy")


def test_sd_signature_line_with_date():
    r = dd("Impression: as above\nSd/- Dr. Neha Joshi, MD (Pathology) 16/09/2026", doc_type="molecular")
    assert (r["report_date_iso"], r["report_date_label"]) == ("2026-09-16", "signature line")
    assert r["event_date_assumed"]


def test_sd_block_with_date_below():
    r = dd("*** End of report ***\nSd/-\nDr. Neha Joshi, MD (Pathology), KMC Reg. No. 73305\nDate: 16/09/2026", doc_type="molecular")
    assert (r["report_date_iso"], r["report_date_label"]) == ("2026-09-16", "signature line")


def test_reported_on_with_time():
    r = dd("Reported on: 04/09/2026 10:15 AM")
    assert r["report_date_iso"] == "2026-09-04" and r["report_date_quote"] == "Reported on: 04/09/2026 10:15 AM"


def test_label_on_the_line_above():
    r = dd("Study date\n02/09/2026\nFindings\nnormal\nReported on\n03/09/2026", doc_type="ct")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-09-02", "Study date")
    assert (r["report_date_iso"], r["report_date_label"]) == ("2026-09-03", "Reported on")


def test_prose_line_above_is_not_a_header():
    r = dd("He was seen at the clinic and referred here. A CT was done in this hospital on\n02/09/2026 at the request of the doctor.",
           doc_type="clinical_note")
    assert kinds(r) == [("2026-09-02", "unlabelled")] and r["date_unconfirmed"]


# ---- never guess --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Patient name Test Patient\nDOB 14/03/1998\nAge / Sex 28 Y / M",
    "Date of birth: 14-Mar-1998",
    "Next review 19/09/2026",
    "Pt counselled. Review on\n17/09/2026",
    "Follow-up: review in OPD on 22/09/2026 with reports",
    "Comparison CT thorax 10-Nov-2025",
    "Mass now 5.2 cm, previously 2.1 cm on CT\ndated 10-Nov-2025.",
    "Compared with CT dated 10/11/2025 the mass is larger.",
    "Relates to IHC report of 19-Aug-2026",
    "Printed on: 06/09/2026 10:00",
    "Bill date 06/09/2026",
    "Valid till 31/12/2026",
    "LMP: 01/08/2026",
    "ABHA card issue date 01/01/2025",
])
def test_ignored_dates_are_never_used_even_when_alone(text):
    r = dd(text, doc_type="clinical_note", model_date=text)
    assert r["date_unconfirmed"] and r["report_date_iso"] == "" and r["event_date_iso"] == ""
    assert r["model_date_iso"] == ""
    assert r["dates"] and all(c["kind"] == "ignore" for c in r["dates"])


def test_dob_only_document_is_unconfirmed_but_seen():
    r = dd("Name Ramesh Kumar\nDOB 12/03/1995\nHaemoglobin 11.8 g/dL")
    assert r["date_unconfirmed"] and r["report_date_iso"] == ""
    assert r["dates"] == [{"iso": "1995-03-12", "kind": "ignore", "label": "DOB", "quote": "DOB 12/03/1995", "page": 0}]


def test_unlabelled_dates_are_kept_but_never_used():
    r = dd("CECT thorax (28-Aug-2026), PET/CT (06-Sep-2026) arranged.", doc_type="clinical_note")
    assert r["date_unconfirmed"] and [c["kind"] for c in r["dates"]] == ["unlabelled", "unlabelled"]


def test_filename_date_is_a_suggestion_only():
    r = dd("CT THORAX\nFindings: normal", doc_type="ct", filename="cect_thorax_2026-09-02.pdf")
    assert r["date_unconfirmed"] and r["report_date_iso"] == "" and r["date_suggestion"] == "2026-09-02"


def test_impossible_or_out_of_window_dates_are_rejected():
    assert dd("Reported on 31/02/2026")["date_unconfirmed"]
    assert dd("Reported on 12/12/1985")["date_unconfirmed"]


# ---- one date stands in for the other ---------------------------------------------------------------------
def test_event_only_report_assumed():
    r = dd("Patient name UHID Age / Sex Study date\nSUNITA DEVI SYN-500263 52 Y / F 06/09/2026\nImpression: normal", doc_type="ct")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-09-06", "Study date") and not r["event_date_assumed"]
    assert r["report_date_iso"] == "2026-09-06" and r["report_date_assumed"]


def test_report_only_event_assumed():
    r = dd("Diagnosis: positive for carcinoma\nSigned: 16-Aug-2026 12:45", doc_type="cytology")
    assert r["report_date_iso"] == "2026-08-16" and not r["report_date_assumed"]
    assert r["event_date_iso"] == "2026-08-16" and r["event_date_assumed"] and r["event_date_label"] == "Signed"


def test_latest_labelled_report_date_wins():
    r = dd("Reported on 19/08/2026\nVerified on 25/08/2026", doc_type="ihc")
    assert r["report_date_iso"] == "2026-08-25"


def test_bare_date_is_a_last_resort_report_date():
    r = dd("REFERRAL LETTER\nDate: 30/08/2026\nKindly see this patient.", doc_type="referral")
    assert (r["report_date_iso"], r["report_date_label"]) == ("2026-08-30", "Date (unspecified)")
    r = dd("Date: 30/08/2026\nReported on 01/09/2026")
    assert r["report_date_iso"] == "2026-09-01"


def test_many_different_bare_dates_are_not_a_report_date():
    r = dd("PROGRESS NOTE\nDate: 11/05/2026, time 13:15\nPROGRESS NOTE\nDate: 12/05/2026, time 16:15", doc_type="other")
    assert r["date_unconfirmed"]


# ---- the model's date ---------------------------------------------------------------------------------------
def test_model_date_used_only_when_found_in_text():
    text = "HAEMATOLOGY\nHb 11.8 g/dL\n04/09/2026"
    r = dd(text, model_date="01-Jan-2026")
    assert r["model_date_iso"] == "" and r["date_unconfirmed"]
    r = dd(text, model_date="04/09/2026")
    assert r["model_date_iso"] == "2026-09-04"
    assert (r["report_date_iso"], r["report_date_label"]) == ("2026-09-04", "model (found in text)")
    assert r["event_date_assumed"]


def test_model_date_on_an_event_line_is_the_event_not_the_report():
    r = dd("Visit date 03/09/2026\nExamination: lump", doc_type="clinical_note", model_date="03/09/2026")
    assert r["model_date_iso"] == "2026-09-03"
    assert r["event_date_label"] == "Visit date" and r["report_date_assumed"]


# ---- per doc type -------------------------------------------------------------------------------------------
def test_clinical_note_with_dob_and_next_review():
    text = ("MEDICAL ONCOLOGY OPD NOTE\nDOB 14/03/1968\nVisit date 05/09/2026\nNext review 19/09/2026\n"
            "Reported by: Dr. Anand Kulkarni, MD, DM\nSigned: 05/09/2026 15:20")
    r = dd(text, doc_type="clinical_note")
    assert (r["event_date_iso"], r["report_date_iso"]) == ("2026-09-05", "2026-09-05")
    assert ("2026-09-19", "ignore") in kinds(r) and ("1968-03-14", "ignore") in kinds(r)
    assert r["date_flags"] == []


def test_imaging_header_study_date_and_reported_on():
    text = "Patient name CR No. Age / Sex\nR. Kumar CR/2026/04118 58Y/M\nStudy date Reported on Ref. by\n02/09/2026 03/09/2026 Dr. Harish Gowda"
    r = dd(text, doc_type="ct")
    assert (r["event_date_iso"], r["report_date_iso"]) == ("2026-09-02", "2026-09-03")


def test_discharge_summary_uses_the_discharge_date_and_keeps_admission():
    r = dd("Date of admission 06/09/2026\nDate of discharge 14/09/2026\nSigned: 14/09/2026", doc_type="discharge_summary")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-09-14", "Date of discharge")
    assert ("2026-09-06", "event") in kinds(r)


def test_compound_admitted_discharged_label():
    r = dd("Admitted / Discharged 01-Sep-2026 / 05-Sep-2026", doc_type="discharge_summary")
    assert [(c["iso"], c["label"]) for c in r["dates"]] == [("2026-09-01", "Admitted"), ("2026-09-05", "Discharged")]
    assert r["event_date_iso"] == "2026-09-05"


def test_treatment_summary_range_uses_completion():
    r = dd("Treatment dates 30-Jun-2026 to 10-Aug-2026\nSigned: 12-Aug-2026", doc_type="treatment_summary")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-08-10", "Treatment dates (end)")
    assert dd("Date of completion: 10/08/2026", doc_type="treatment_summary")["event_date_iso"] == "2026-08-10"


def test_tumour_board_record_board_date():
    r = dd("TUMOUR BOARD RECORD\nBoard date 12-Jun-2026\nRecorded by: Dr. F. Siddiqui\nSigned: 12-Jun-2026 18:00", doc_type="tumour_board_record")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-06-12", "Board date")


def test_endoscopy_procedure_date():
    r = dd("COLONOSCOPY REPORT\nProcedure date 30-May-2026\nSigned: 30-May-2026 13:45", doc_type="endoscopy")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-05-30", "Procedure date")


def test_other_doc_type_takes_the_earliest_labelled_event():
    text = ("Hosp. No.: DGH-26-071134. Admission: 11/05/2026. Discharge: 18/05/2026.\n"
            "COLONOSCOPY REPORT\nDate of procedure: 12/05/2026. Growth seen.")
    r = dd(text, doc_type="other")
    assert (r["event_date_iso"], r["event_date_label"]) == ("2026-05-11", "Admission")


def test_clinical_note_does_not_take_a_procedure_date_from_history():
    r = dd("History: Date of surgery 12/03/2025\nSigned: 05/09/2026", doc_type="clinical_note")
    assert r["event_date_iso"] == "2026-09-05" and r["event_date_assumed"]


# ---- formats ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("s,iso", [
    ("02/09/2026", "2026-09-02"), ("02-09-2026", "2026-09-02"), ("02.09.2026", "2026-09-02"), ("02-Sep-2026", "2026-09-02"),
    ("2 September 2026", "2026-09-02"), ("02/09/26", "2026-09-02"), ("2026-09-02", "2026-09-02"), ("Sep 02, 2026", "2026-09-02"),
    ("29/09/2026", "2026-09-29"), ("04/09/2026 10:15 AM", "2026-09-04"),
])
def test_formats(s, iso):
    assert dd(f"Reported on: {s}")["report_date_iso"] == iso


# ---- sanity flags -------------------------------------------------------------------------------------------
def test_after_today_flag():
    r = dd("Collected on 04/09/2026\nReported on 05/11/2026")
    assert r["date_flags"] == ["report date is after today"]
    r = dd("Collected on 04/11/2026\nReported on 05/11/2026")
    assert r["date_flags"] == ["report date is after today", "event date is after today"]
    r = dd("Reported on 05/11/2028")  # far in the future: kept and flagged, not dropped
    assert r["report_date_iso"] == "2028-11-05" and r["date_flags"] == ["report date is after today"]


def test_before_dob_flag():
    assert dd("Reported on 05/09/2026", dob_iso="2026-10-01")["date_flags"] == ["date is before the date of birth"]
    assert dd("DOB 01/10/2026\nReported on 05/09/2026", today="2026-12-01")["date_flags"] == ["date is before the date of birth"]
    assert dd("Reported on 05/09/2026", dob_iso="1968-03-14")["date_flags"] == []


def test_month_first_flag():
    r = dd("Study date 03/04/2026\nSigned: 09/29/2026", doc_type="ct")
    assert "day and month may be swapped: the document also has a month-first date" in r["date_flags"]
    assert r["event_date_iso"] == "2026-04-03"  # still read day first
    assert dd("Study date 03/04/2026\nSigned: 29/09/2026", doc_type="ct")["date_flags"] == []
    assert dd("Study date 13/04/2026\nSigned: 09/29/2026", doc_type="ct")["date_flags"] == []  # 13/04 is not ambiguous


# ---- lexicon and shape --------------------------------------------------------------------------------------
def test_lexicon_loaded_once_and_plain_english():
    assert dates.lexicon() is dates.lexicon()
    raw = (config.PROTOCOL_DIR / "dates.json").read_text()
    assert "—" not in raw  # no em dashes
    kinds_ = {x["kind"] for x in json.loads(raw)["labels"]}
    assert kinds_ == {"report", "event", "event_low", "ignore", "unspecified"}


def test_result_shape_and_pages():
    r = dates.document_dates(["Page one, no date", "Collected on 04/09/2026\nSigned: 05/09/2026"], "x.pdf", "lab", today=TODAY)
    assert set(r) >= {"report_date_iso", "event_date_iso", "report_date_assumed", "event_date_assumed", "report_date_quote",
                      "event_date_quote", "report_date_label", "event_date_label", "date_unconfirmed", "date_suggestion",
                      "date_flags", "dates", "model_date_iso"}
    assert [c["page"] for c in r["dates"]] == [1, 1]
    assert dates.document_dates([], "", "")["date_unconfirmed"]


# ---- answer key on the unit fixtures ------------------------------------------------------------------------
def test_fixture_cases_against_answer_key():
    """Same comparison as eval/dates_eval.py on the trimmed demo cases TB-001..003 (>= 95 % exact, 0 from ignored dates)."""
    from tumour_board.eval import dates_eval
    rows = []
    for cid in ("TB-001", "TB-002", "TB-003"):
        tf = TRUTH / f"{cid}.json"
        if not tf.exists():
            pytest.skip("answer key not available")
        rows += dates_eval.compare_case(FIXTURES / "cases" / cid, json.loads(tf.read_text()))
    assert len(rows) == 27
    ok = sum(r[4] + r[5] for r in rows)
    assert 100.0 * ok / (2 * len(rows)) >= 95.0, [(r[0], r[4], r[5]) for r in rows if not (r[4] and r[5])]
    assert sum(r[6] for r in rows) == 0


@pytest.mark.parametrize("path", sorted((FIXTURES / "cases").glob("*/docs/*/doc.json")), ids=lambda p: f"{p.parts[-4]}-{p.parts[-2]}")
def test_every_fixture_date_quote_is_grounded(path):
    d = json.loads(path.read_text())
    texts = [p["text"] for p in d["pages"]]
    r = dates.document_dates(texts, d["filename"], d["classification"]["doc_type"], model_date=d["classification"].get("report_date", ""))
    assert not r["date_unconfirmed"] and r["date_flags"] == []
    grounded(r, texts)
