"""docstatus: report status, signature and date rules (characterisation of today's behaviour)."""
import json

import pytest

from tumour_board import docstatus as ds
from tumour_board.tests.conftest import FIXTURES


@pytest.mark.parametrize("text,status", [
    ("Report status: FINAL", "FINAL"),
    ("Report Status - Amended", "AMENDED"),
    ("Report status: Final (Amended)", "AMENDED"),
    ("Report status: Corrected", "CORRECTED"),
    ("Report status: Preliminary", "PRELIMINARY"),
    ("Report status: provisional", "PRELIMINARY"),
    ("Report status: Draft", "DRAFT"),
    ("Report status: Cancelled", "CANCELLED"),
    ("Result status: canceled", "CANCELLED"),
    ("Record status: FINAL", "FINAL"),
    ("FINAL DIAGNOSIS: Adenocarcinoma", "FINAL"),
    ("FINAL PATHOLOGIC DIAGNOSIS", "FINAL"),
    ("*** End of report ***", "FINAL"),
    ("ADDENDUM: HER2 FISH", "AMENDED"),
    ("Revised report issued", "AMENDED"),
    ("Supplementary report", "AMENDED"),
    ("Corrected report", "CORRECTED"),
    ("DRAFT REPORT", "DRAFT"),
    ("DRAFT / UNSIGNED", "DRAFT"),
    ("Preliminary report: pending IHC", "PRELIMINARY"),
    ("Interim result", "PRELIMINARY"),
    ("Biopsy (provisional) see addendum", "PRELIMINARY"),
    ("Report cancelled", "CANCELLED"),
    ("Report withdrawn", "CANCELLED"),
    ("Impression: mass in right upper lobe", "UNSTATED"),
    ("Entered in error", "UNSTATED"),  # needs "report entered in error"
])
def test_detect_status(text, status):
    assert ds.detect_status(text)[0] == status


def test_status_line_beats_other_markers():
    st, quote, _ = ds.detect_status("FINAL DIAGNOSIS: adenocarcinoma\nReport status: PRELIMINARY (pending HER2 FISH)")
    assert st == "PRELIMINARY" and quote.startswith("Report status: PRELIMINARY")


def test_negative_markers_beat_positive_ones():
    assert ds.detect_status("Preliminary report.\nFINAL DIAGNOSIS: adenocarcinoma")[0] == "PRELIMINARY"
    assert ds.detect_status("DRAFT REPORT\n*** End of report ***")[0] == "DRAFT"


def test_amended_beats_final_without_status_line():
    assert ds.detect_status("FINAL DIAGNOSIS: carcinoma\nADDENDUM: HER2 FISH not amplified")[0] == "AMENDED"


def test_unstated_with_draft_word_adds_note():
    st, quote, notes = ds.detect_status("This is a draft copy of the summary")
    assert (st, quote) == ("UNSTATED", "")
    assert notes == ["the word 'draft' appears in the text; confirm this is the final version"]


def test_unstated_without_draft_word_has_no_note():
    assert ds.detect_status("Impression: normal study") == ("UNSTATED", "", [])


# ---- V1 3.2: a "final diagnosis" header whose content is still pending is explicit negative evidence ------------------
@pytest.mark.parametrize("text", [
    "FINAL DIAGNOSIS: pending IHC",
    "Final diagnosis: Awaited",
    "FINAL DIAGNOSIS:\nDeferred until immunohistochemistry",
    "Final diagnosis is pending",
    "Final diagnosis to follow after IHC",
    "Final diagnosis: report to follow",
    "FINAL PATHOLOGICAL DIAGNOSIS - will follow",
])
def test_final_diagnosis_pending_is_preliminary(text):
    st, quote, notes = ds.detect_status(text)
    assert st == "PRELIMINARY" and quote.lower().startswith("final") and notes == []


def test_final_diagnosis_pending_quote_is_the_snippet():
    st, quote, _ = ds.detect_status("Specimen: core biopsy, right lung\nFINAL DIAGNOSIS: pending IHC\nSd/- Dr. S. Rao")
    assert st == "PRELIMINARY" and "FINAL DIAGNOSIS: pending IHC" in quote


@pytest.mark.parametrize("text", [
    "FINAL DIAGNOSIS: Adenocarcinoma",
    "FINAL DIAGNOSIS: Adenocarcinoma, HER2 pending",       # a diagnosis is given; one test still pending
    "Final diagnosis: invasive ductal carcinoma. IHC awaited for receptor status",
])
def test_real_final_diagnosis_stays_final(text):
    assert ds.detect_status(text)[0] == "FINAL"


@pytest.mark.parametrize("text,signed", [
    ("Electronically signed by Dr. Meera Nair", "yes"),
    ("Digitally signed", "yes"),
    ("e-signed", "yes"),
    ("Sd/-", "yes"),
    ("Sd/- Dr. Rao", "yes"),
    ("(Sd.) Dr Rao", "yes"),
    ("Reg No: TN/12345", "yes"),
    ("Reg. No. 45678", "yes"),
    ("KMC Reg. No. 54321", "yes"),
    ("Dr. P. Menon, NMC 123456", "yes"),
    ("Verified by Dr. A. Menon", "yes"),
    ("Reported by: Dr. Meera Nair, Consultant", "yes"),
    ("Signed out by Dr X", "yes"),
    ("Authorised signatory", "yes"),
    ("unsigned", "no"),
    ("Signature pending", "no"),
    ("Not yet signed", "no"),
    ("Awaiting verification", "no"),
    ("Pending sign-out", "no"),
    ("Impression: normal", "unknown"),
    ("Dr. Meera Nair, MD Pathology", "unknown"),  # a name with a degree is a signer line, not a signature
])
def test_detect_signature(text, signed):
    assert ds.detect_signature(text)[0] == signed


def test_unsigned_anywhere_wins():
    assert ds.detect_signature("Signed by Dr X.\nAddendum unsigned")[0] == "no"


def test_signer_line_returned():
    signed, line = ds.detect_signature("Diagnosis: carcinoma\nReported by: Dr. A. Menon, Consultant Pathologist\nReg. No. 45678")
    assert signed == "yes" and line == "Reported by: Dr. A. Menon, Consultant Pathologist"


def test_signer_line_without_signature_is_unknown():
    assert ds.detect_signature("Dr. Meera Nair, MD Pathology") == ("unknown", "Dr. Meera Nair, MD Pathology")


def test_reg_no_with_council_prefix_is_signed():
    """Found in 0.3, fixed in V1 item 3.5 (was a strict xfail in test_known_issues)."""
    assert ds.detect_signature("Dr. S. Rao, MD (Pathology)\nReg. No. KMC 45678") == ("yes", "Dr. S. Rao, MD (Pathology)")


@pytest.mark.parametrize("text", [
    "Reg. No. KMC 45678", "Reg No: TNMC/12345", "KMC Reg. No. 45678", "Regn. No. 12345 (MMC)", "Dr. S. Rao, MCI 12345", "NMC Reg 123456",
    "Reg. No. KMC-45678", "Registration No. DMC/R/04512", "APMC Regn No 67890", "Dr. P. Sen, MBBS, MD, WBMC 55123", "Dr. A. Iyer, MD, TCMC 22345", "Dr. K. Shetty (KMC/45678)",
])
def test_council_registration_is_a_signature(text):
    """V1 item 3.5: State Medical Council / NMC / MCI registration in the usual Indian layouts."""
    assert ds.detect_signature(text)[0] == "yes"


@pytest.mark.parametrize("text", [
    "UHID: KMC 123456", "UHID KMC123456", "Patient ID KMC 778899", "MRN KMC 445566", "Sample No. KMC 12345", "Lab No: KMC/2026/4411",
    "Sample No. 2026/4411", "UHID: SYN-900001", "CR No. 2026/0042", "pmc 2026",
])
def test_identifiers_and_sample_numbers_are_not_signatures(text):
    """A hospital identifier or a lab sample number, even one that starts with a council-like code, is not a signature."""
    assert ds.detect_signature(text)[0] == "unknown"


def test_reg_no_without_council_unchanged():
    """'Reg. No.' with a number and no council code reads as today (a registration number is a signature cue); V1 item 3.5 only adds councils."""
    assert ds.detect_signature("Reg. No. 2026/4411")[0] == "yes"


@pytest.mark.parametrize("text", ["Registration No. with State Code", "Reg. No.: ________", "Name of the treating doctor:\nRegistration No. with State Code:\nSignature:"])
def test_blank_registration_label_is_not_a_signature(text):
    """A form's empty 'Registration No.' label (claim forms, Pre-Authorization requests) carries no number, so it is not a signature (12 Oct)."""
    assert ds.detect_signature(text)[0] == "unknown"


@pytest.mark.parametrize("s,iso", [
    ("02-Sep-2026", "2026-09-02"),
    ("02/09/2026", "2026-09-02"),  # day first (India)
    ("02.09.2026", "2026-09-02"),
    ("02-09-26", "2026-09-02"),
    ("2 September 2026", "2026-09-02"),
    ("2nd Sept 2026", "2026-09-02"),
    ("29-Sept-26", "2026-09-29"),
    ("5 Sep. 2026", "2026-09-05"),
    ("Sep 2, 2026", "2026-09-02"),
    ("Sept 29 2026", "2026-09-29"),
    ("2026-09-02", "2026-09-02"),
    ("13/02/2026", "2026-02-13"),
    ("02/13/2026", "2026-02-13"),  # month > 12 in the second slot: read as month first
    ("Reported on: 05/09/2026", "2026-09-05"),
    ("31/02/2026", ""),  # impossible date
    ("12/12/1985", ""),  # years before 1990 are ignored
    ("04-Jun-89", ""),
    ("", ""),
    (None, ""),
    ("no date here", ""),
])
def test_parse_date(s, iso):
    assert ds.parse_date(s) == iso


def test_parse_date_takes_first_valid_date():
    assert ds.parse_date("DOB: 12/03/1964 Reported: 05/09/2026") == "2026-09-05"  # 1964 is outside the year window
    assert ds.parse_date("Collected 01/09/2026 Reported 05/09/2026") == "2026-09-01"


@pytest.mark.parametrize("text,isos", [
    ("Age 62 Years 02/09/2026", ["2026-09-02"]),  # found in 0.3: "62 Years 02" was read as a date and swallowed the real one
    ("Ward 4 dated 04/09/2026", ["2026-09-04"]),
    ("Bed 12 Sept 2026 notes 05/09/2026", ["2026-09-12", "2026-09-05"]),
    ("Hb 11 gm% 03/09/2026", ["2026-09-03"]),
    ("LAB/26/118011 and HP/2026/7731", []),  # sample numbers are not dates
    ("ABHA No. 91-4021-7788-3105", []),
])
def test_find_dates_after_number_and_word(text, isos):
    assert ds.find_dates(text) == isos


@pytest.mark.parametrize("s,iso", [
    ("01-Jan-2026", "2026-01-01"), ("2026-09-29", "2026-09-29"), ("29/09/2026", "2026-09-29"), ("29-09-26", "2026-09-29"),
    ("Sep 29, 2026", "2026-09-29"), ("29 SEP 2026", "2026-09-29"), ("Sept. 29, 2026", "2026-09-29"), ("4th June 2026", "2026-06-04"),
    ("29/09/2026 10:15 AM", "2026-09-29"), ("120/09/2026", ""), ("29/09/20261", ""),
])
def test_parse_date_formats_used_by_confirm_service_identity(s, iso):
    assert ds.parse_date(s) == iso


def test_match_iso_year_window():
    m = ds._DATE_RX.search("DOB 14/03/1968")
    assert ds.match_iso(m) == "" and ds.match_iso(m, (1900, 2100)) == "1968-03-14"


def test_find_dates_unique_in_order_with_limit():
    assert ds.find_dates("seen 01/09/2026; reported 05/09/2026; again 05-Sep-2026") == ["2026-09-01", "2026-09-05"]
    many = " ".join(f"{d:02d}/09/2026" for d in range(1, 12))
    assert len(ds.find_dates(many)) == 6 and len(ds.find_dates(many, limit=3)) == 3


def _fixture_docs():
    return sorted((FIXTURES / "cases").glob("*/docs/*/doc.json"))


@pytest.mark.parametrize("path", _fixture_docs(), ids=lambda p: f"{p.parts[-4]}-{p.parts[-2]}")
def test_rules_reproduce_fixture_classification(path):
    """The stored status / signed of every demo document is what the rules give on its text today."""
    d = json.loads(path.read_text())
    full = "\n\n".join(f"[page {i + 1}]\n{p['text']}" for i, p in enumerate(d["pages"]))
    assert ds.detect_status(full)[0] == d["classification"]["status"]
    assert ds.detect_signature(full)[0] == d["classification"]["signed"]


@pytest.mark.parametrize("text", ["Lab Ref KMC/2026/12345", "IP KMC 45678", "Accession KMC-2026-0042", "Barcode TNMC12345", "PMC 2026 annual",
                                  "MCI 12345", "WBMC 55123", "KMC/45678", "GMC 2026/4411", "Sample ABMC 123456"])
def test_bare_council_code_without_a_doctor_line_is_not_a_signature(text):
    """Hospital abbreviations (KMC, GMC, MMC) prefix IP, lab and accession numbers: a bare code is a signature only on a doctor's line (review of Phase 3)."""
    assert ds.detect_signature("Patient X\n" + text + "\nFindings: as above")[0] == "unknown"
