"""Independent OCR engine for numbers (V1 item 8.3): the number check on strings, the word format, Aadhaar masking of the
engine's words, ocr_page with the engine absent / mocked, and (only when Tesseract is installed) the Done-when fixture: one
wrong digit that both model reads share is flagged by the engine. Synthetic text only."""
import asyncio, io, json

import pytest

from tumour_board import ingest, ocr_engine

ENGINE = "the independent OCR engine reads a different number"


def spans(full, eng):
    return [(s["line"], s["numbers"]) for s in ocr_engine.engine_spans(full, eng)]


# ---- engine_spans on strings ----------------------------------------------------------------------------------------
def test_one_wrong_digit_is_flagged():
    full = "IHC REPORT\nPD-L1 (22C3) Tumour Proportion Score: 80%\nKi-67 index: 35%"
    (s,) = ocr_engine.engine_spans(full, "IHC REPORT\nPD-L1 (22C3) Tumour Proportion Score: 60%\nKi-67 index: 35%")
    assert s["line"] == "PD-L1 (22C3) Tumour Proportion Score: 80%" and s["numbers"] == ["80"]  # the transcription's number only
    assert s["reason"] == ENGINE and s["source"] == "engine" and full[s["start"]:s["end"]] == s["line"]


def test_equal_numbers_are_not_flagged():
    t = "Hb 11.8 g/dL 13.0 - 17.0\nECOG 1\nPlatelets 2,45,000 /cumm"
    assert spans(t, t) == []
    assert spans(t, "Hb 11.8 g/dl. 13.0-17.0\nECOG 1\nPlatelets 245000 /cumm") == []


@pytest.mark.parametrize("full,eng", [
    ("Haemoglobin 11.8 g/dL 13.0 - 17.0", "Haemoglobin 118 g/dl. 13.0-17.0"),           # decimal point lost by the engine
    ("S. Creatinine 0.8 mg/dl 0.5 - 1.1", "S. Creatinine 08 mg/dl 05-11"),
    ("22:00 97.8 84 121/71 17 MK", "22:00 97.8 84 121/71 7 MK"),                       # leading digit cut
    ("Platelet count 198 x10^3/uL 150 - 410", "Platelet count 198 x103/uL 150 - 410"),  # merged
    ("cT2b N2 M0, Stage IIIA (AJCC 8th edition)", "€12b NZ MO, Stage IIIA (ACC 8th edition)"),  # letters, missed digits
    ("Mr. RAMESH KUMAR SYN-400118 58 Y / M", "Mr. RAMESH KUMAR SYN-400118 Es EERE"),     # number not read at all
    ("05/09/2026 12:40 Dr. Anand Kulkarni LAB/26/118392", "05/09/2026 12:40 _Dr. Anand Kulkarni _1AB/26/118392"),  # extra number
])
def test_engine_slips_that_are_not_evidence(full, eng):
    assert spans(full, eng) == []


def test_table_rows_with_pipes():
    full = "| Test | Result | Unit |\n| Hb | 11.8 | g/dL |\n| Platelets | 2,46,000 | /cumm |\n| Creatinine | 0.9 | mg/dL |"
    eng = "Test Result Unit\nHb 11.8 g/dL\nPlatelets 2,45,000 /cumm\nCreatinine 0.9 mg/dL"
    assert spans(full, eng) == [("| Platelets | 2,46,000 | /cumm |", ["246000"])]
    assert spans(full.replace("2,46,000", "2,45,000"), eng) == []


@pytest.mark.parametrize("eng", [
    "1, | have been explained the nature of the procedure, its risks",
    "8.1 have been explained the nature of the procedure, its risks",
    "(1) I have been explained the nature of the procedure, its risks",
])
def test_list_markers_are_not_compared(eng):
    assert spans("1. I have been explained the nature of the procedure, its risks", eng) == []


def test_page_markers_and_blank_form_fields():
    full = "Case record, scanned copy. Page 35 of 100\nItem 4: ______________________ Amount: ________"
    assert spans(full, "Case record, scanned copy. Page 36 of 100\nitem 4: Amount:") == []
    assert spans(full.replace("Item 4", "Item 7"), "Case record, scanned copy. Page 35 of 100\nitem 4: Amount:") == [
        ("Item 7: ______________________ Amount: ________", ["7"])]  # underscores dropped by the engine: still partners


def test_lines_without_partner_compared_with_the_engine_stretch():
    full = "Patient SYNTHETIC\nHb 11.8 | WBC 7200 | Platelets 245000\nReport status: FINAL"
    eng = "Patient SYNTHETIC\nPlatelets 245000\nWBC 7200\nHb 11.8\nReport status: FINAL"  # columns read in another order
    assert spans(full, eng) == []


def test_offsets_with_leading_spaces():
    full = "Patient: Test Patient\n  PD-L1 TPS 6%  \nECOG 1"
    (s,) = ocr_engine.engine_spans(full, "Patient: Test Patient\nPD-L1 TPS 8%\nECOG 1")
    assert full[s["start"]:s["end"]] == "PD-L1 TPS 6%"


def test_confirm_needs_the_same_number_in_doubt():
    full = "10:00 97.9 89 131/72 14 MK"
    first = ocr_engine.engine_spans(full, "10:00 97.9 89 134/72 14 MK")
    assert first and first[0]["numbers"] == ["131"]
    assert ocr_engine.confirm_spans(first, full, "10:00 37.9 89 131/72 14 MK") == []  # another slip on the same row
    assert ocr_engine.confirm_spans(first, full, "10:00 97.9 89 131/72 14 MK") == []  # the re-read agrees
    assert ocr_engine.confirm_spans(first, full, "10:00 97.9 89 134/72 14 MK") == first


# ---- word format, Aadhaar --------------------------------------------------------------------------------------------
TSV_HEAD = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def _tsv(rows):
    return TSV_HEAD + "".join(f"5\t1\t{b}\t1\t{ln}\t{k + 1}\t{x}\t{y}\t{w}\t{h}\t{c}\t{t}\n" for k, (b, ln, x, y, w, h, c, t) in enumerate(rows))


def test_parse_tsv_normalises_boxes_and_lines():
    tsv = _tsv([(1, 1, 100, 50, 200, 40, 96.4, "Ki-67"), (1, 1, 320, 50, 100, 40, 91.0, "35%"),
                (1, 2, 100, 120, 300, 40, 88.25, "FINAL"), (2, 1, 100, 300, 50, 40, -1, " ")])
    text, words = ocr_engine.parse_tsv(tsv, 1000, 2000)
    assert text == "Ki-67 35%\nFINAL"
    assert words[0] == ["Ki-67", 0.1, 0.025, 0.3, 0.045, 96.4, 0]
    assert words[2] == ["FINAL", 0.1, 0.06, 0.4, 0.08, 88.2, 1] and len(words) == 3


def test_aadhaar_masked_in_text_and_words():
    tsv = _tsv([(1, 1, 10, 10, 90, 20, 95, "Aadhaar"), (1, 1, 110, 10, 40, 20, 95, "No."), (1, 1, 160, 10, 60, 20, 95, "6043"),
                (1, 1, 230, 10, 60, 20, 95, "1187"), (1, 1, 300, 10, 60, 20, 95, "2200"), (1, 2, 10, 40, 40, 20, 95, "Hb"),
                (1, 2, 60, 40, 50, 20, 95, "11.8")])
    text, words = ocr_engine.parse_tsv(tsv, 1000, 1000)
    masked, mw, n, idx = ocr_engine.mask_words(text, words)
    assert n == 1 and masked == "Aadhaar No. XXXX XXXX 2200\nHb 11.8" and idx == [2, 3]
    assert [w[0] for w in mw] == ["Aadhaar", "No.", "XXXX", "XXXX", "2200", "Hb", "11.8"]
    assert [w[1:] for w in mw] == [w[1:] for w in words]  # boxes kept for masking the preview
    assert "6043" not in json.dumps([masked, mw]) and "1187" not in json.dumps([masked, mw])


def test_aadhaar_ungrouped_word_on_a_labelled_line():
    tsv = _tsv([(1, 1, 10, 10, 60, 20, 95, "UID:"), (1, 1, 80, 10, 150, 20, 95, "604311872200")])
    text, words = ocr_engine.parse_tsv(tsv, 1000, 1000)
    masked, mw, n, idx = ocr_engine.mask_words(text, words)
    assert n == 1 and "604311872200" not in json.dumps([masked, mw]) and mw[1][0] == "XXXXXXXX2200" and idx == [1]


def test_no_aadhaar_words_unchanged():
    text, words = "Hb 11.8", [["Hb", 0.1, 0.1, 0.2, 0.2, 95.0, 0], ["11.8", 0.3, 0.1, 0.4, 0.2, 95.0, 0]]
    assert ocr_engine.mask_words(text, words) == (text, words, 0, [])


# ---- settings -----------------------------------------------------------------------------------------------------
def test_turned_off_and_not_installed(monkeypatch):
    monkeypatch.setenv("TB_OCR_ENGINE", "off")
    assert not ocr_engine.available() and ocr_engine.unavailable_note() == "independent OCR engine turned off"
    assert asyncio.run(ocr_engine.read_page(b"png")) is None and ocr_engine.engine_info() is None
    monkeypatch.delenv("TB_OCR_ENGINE")
    monkeypatch.setenv("TB_TESSERACT", "/nonexistent/tesseract")
    assert ocr_engine.binary() is None and ocr_engine.unavailable_note() == "independent OCR engine not installed"
    events = []
    assert asyncio.run(ocr_engine.read_page(b"png", events.append)) is None and events == []


def test_recheck_scale():
    assert ocr_engine.recheck_scale([1198, 1693]) == 1.5
    assert ocr_engine.recheck_scale([3000, 2000]) == pytest.approx(1.333, abs=1e-3)
    assert ocr_engine.recheck_scale([4000, 3000]) == 0.75


# ---- ocr_page -----------------------------------------------------------------------------------------------------
def _reader(monkeypatch, full, second=None):
    async def fake(png, audit=None, max_side=None):
        return (second if second is not None else full) if max_side else full
    monkeypatch.setattr(ingest, "ocr_image", fake)


def test_ocr_page_without_the_engine_is_unchanged(monkeypatch):
    monkeypatch.setenv("TB_TESSERACT", "/nonexistent/tesseract")
    _reader(monkeypatch, "PD-L1 TPS 6%\nECOG 1", "PD-L1 TPS 8%\nECOG 1")
    events = []
    p = asyncio.run(ingest.ocr_page(b"png", audit=events.append))
    assert p["ocr_engine_note"] == "independent OCR engine not installed" and "ocr_engine" not in p
    assert [s["reason"] for s in p["ocr_uncertain_spans"]] == ["the two OCR reads disagree on a number"]
    assert events == [{"kind": "ocr_disagreement", "numbers": ["6", "8"], "lines": 1}]


def _fake_engine(monkeypatch, *texts):
    """read_page returns these texts in turn (first read, then the confirming re-read)."""
    calls, it = [], iter(texts)

    async def read(png, audit=None, scale=1.0):
        calls.append(scale)
        return {"engine": "tesseract", "version": "5.5.3", "lang": "eng", "size": [1000, 1400], "text": next(it), "words": []}
    monkeypatch.setattr(ocr_engine, "read_page", read)
    return calls


def test_ocr_page_merges_engine_spans(monkeypatch):
    t = "IHC REPORT\nPD-L1 TPS 80%\nKi-67 35%"
    _reader(monkeypatch, t)
    calls = _fake_engine(monkeypatch, t.replace("80%", "60%"), t.replace("80%", "60%"))
    events = []
    p = asyncio.run(ingest.ocr_page(b"png", audit=events.append))
    (s,) = p["ocr_uncertain_spans"]
    assert s["reason"] == ENGINE and s["source"] == "engine" and p["ocr_uncertain_numbers"] == ["80"]
    assert calls == [1.0, 1.5] and p["ocr_engine"]["recheck"]["confirmed"] == 1 and p["text"] == t  # transcription untouched
    assert events == [{"kind": "ocr_engine_disagreement", "numbers": ["80"], "lines": 1}]
    loc = p["text"].index("80%")
    assert ingest.uncertain_overlap(p, loc, loc + 3)["reason"] == ENGINE


def test_ocr_page_engine_agrees_no_reread(monkeypatch):
    t = "IHC REPORT\nPD-L1 TPS 80%"
    _reader(monkeypatch, t)
    calls = _fake_engine(monkeypatch, t)
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert "ocr_uncertain_spans" not in p and calls == [1.0] and p["ocr_engine"]["text"] == t and "ocr_engine_note" not in p


def test_ocr_page_unconfirmed_engine_slip_is_dropped(monkeypatch):
    t = "10:00 97.9 89 131/72 14 MK"
    _reader(monkeypatch, t)
    _fake_engine(monkeypatch, "10:00 97.9 89 134/72 14 MK", "10:00 97.9 89 131/72 14 MK")
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert "ocr_uncertain_spans" not in p and p["ocr_engine"]["recheck"] == {
        "scale": 1.5, "text": t, "candidates": 1, "confirmed": 0}


def test_ocr_page_keeps_both_reasons_on_one_line(monkeypatch):
    _reader(monkeypatch, "PD-L1 TPS 80%\nECOG 1", "PD-L1 TPS 30%\nECOG 1")
    _fake_engine(monkeypatch, "PD-L1 TPS 60%\nECOG 1", "PD-L1 TPS 60%\nECOG 1")
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert [s["reason"] for s in p["ocr_uncertain_spans"]] == ["the two OCR reads disagree on a number", ENGINE]
    assert p["ocr_uncertain_numbers"] == ["30", "80"]  # the engine's "60" is never shown


def test_ocr_page_engine_failure_is_a_note(monkeypatch):
    async def none(png, audit=None, scale=1.0):
        return None
    monkeypatch.setattr(ocr_engine, "read_page", none)
    monkeypatch.setattr(ocr_engine, "binary", lambda: "/usr/bin/tesseract")
    _reader(monkeypatch, "ECOG 1")
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert p["ocr_engine_note"] == "independent OCR engine could not read this page" and "ocr_uncertain_spans" not in p


# ---- review fixes: Aadhaar through the engine (S1), masked word indexes (S2) ------------------------------------------
AADHAAR = ("4821", "6093")  # the masked groups of the synthetic Aadhaar 4821 6093 2200 used below


def _words_of(text):
    """Engine words for a text, one per space-separated token, on its line (the shape parse_tsv gives)."""
    out = []
    for n, line in enumerate(text.split("\n")):
        for k, t in enumerate(line.split(" ")):
            out.append([t, round(0.05 + 0.1 * k, 4), round(0.05 * n, 4), round(0.1 + 0.1 * k, 4), round(0.05 * n + 0.03, 4), 90.0, n])
    return out


def _raw_engine(monkeypatch, *texts):
    """read_page returns these engine texts UNMASKED (first read, then the re-read), so that the masking ocr_page does on
    its own is what is tested."""
    calls, it = [], iter(texts)

    async def read(png, audit=None, scale=1.0):
        calls.append(scale)
        t = next(it)
        return {"engine": "tesseract", "version": "5.5.3", "lang": "eng", "size": [1000, 1400], "text": t, "words": _words_of(t),
                "masked_words": []}
    monkeypatch.setattr(ocr_engine, "read_page", read)
    return calls


def _no_leak(*objs):
    blob = json.dumps(objs)
    return all(g not in blob for g in AADHAAR)


@pytest.mark.parametrize("eng", [
    "Name RAMESH KUMAR\nAadhaar: 4821 6093 22O0\nHb 11.8 g/dL",           # reviewer: O for 0, identity's rule misses it
    "Name RAMESH KUMAR\nAadhaar 4821 6093\n2200\nHb 11.8 g/dL",          # reviewer: the engine splits the line
    "Name RAMESH KUMAR\nAadhaar: 4821-6O93-2200\nHb 11.8 g/dL",           # hyphenated, look-alike
    "Name RAMESH KUMAR 4821 6O93\nCollected 22OO\nHb 11.8 g/dL",          # no label, no 12 characters: only the cross-mask sees it
    "Name RAMESH KUMAR\nAadhaar:4821609322O0\nHb 11.8 g/dL",              # run together
])
def test_reader_aadhaar_never_leaks_through_the_engine(monkeypatch, eng):
    full = "Name RAMESH KUMAR\nAadhaar: 4821 6093 2200\nHb 11.8 g/dL"
    _reader(monkeypatch, full)
    _raw_engine(monkeypatch, eng, eng)
    events = []
    p = asyncio.run(ingest.ocr_page(b"png", audit=events.append))
    assert p["text"] == "Name RAMESH KUMAR\nAadhaar: XXXX XXXX 2200\nHb 11.8 g/dL"
    assert _no_leak(p, events), json.dumps(p["ocr_engine"])
    e = p["ocr_engine"]
    assert e["masked_words"] and all("X" in e["words"][i][0] for i in e["masked_words"])
    assert all(any(g in w[0] for g in AADHAAR) is False for w in e["words"])
    assert "Hb 11.8 g/dL" in e["text"]  # the rest of the reading untouched


def test_engine_spans_numbers_are_the_transcriptions_only():
    """Reviewer: unmasked engine digits on the Aadhaar line were shown as numbers in doubt."""
    (s,) = ocr_engine.engine_spans("Aadhaar: XXXX XXXX 2200", "Aadhaar: 4821 6093 22O0")
    assert s["numbers"] == ["2200"]
    (s,) = ocr_engine.engine_spans("PD-L1 TPS 80%\nKi-67 35%", "PD-L1 TPS 60%\nKi-67 35%")
    assert s["numbers"] == ["80"]


def test_recheck_text_and_audit_cross_masked(monkeypatch):
    """A flagged line elsewhere sends the page to the re-read; the re-read sees the Aadhaar in a form only the cross-mask
    catches (no label on its line, look-alikes): masked before it is stored or compared."""
    full = "Patient: Test Patient\nAadhaar No.\n4821 6093 2200\nPD-L1 TPS 80%"
    _reader(monkeypatch, full)
    _raw_engine(monkeypatch, "Patient: Test Patient\nAadhaar No.\n4821 6093 2200\nPD-L1 TPS 60%",
                "Patient: Test Patient\nRef 4821 6O93 22OO\nPD-L1 TPS 60%")
    events = []
    p = asyncio.run(ingest.ocr_page(b"png", audit=events.append))
    assert p["ocr_engine"]["recheck"]["confirmed"] == 1 and p["ocr_uncertain_numbers"] == ["80"]
    assert _no_leak(p, events) and "XXXX XXXX" in p["ocr_engine"]["recheck"]["text"]
    assert {"kind": "ocr_engine_disagreement", "numbers": ["80"], "lines": 1} in events


def test_second_model_read_cross_masked(monkeypatch):
    """The second model read writes the number in a form identity's rule misses: masked with the first read's number, so it
    is not in second_read, the uncertain numbers or the ocr_disagreement audit."""
    monkeypatch.setenv("TB_OCR_ENGINE", "off")
    _reader(monkeypatch, "Name RAMESH\nAadhaar: 4821 6093 2200\nECOG 1", "Name RAMESH\nNo. 4821 6O93 22OO\nECOG 1")
    events = []
    p = asyncio.run(ingest.ocr_page(b"png", audit=events.append))
    assert _no_leak(p, events) and "XXXX XXXX" in p["second_read"] and p["aadhaar_masked"] == 1


def test_aadhaar_numbers_of_a_raw_reading():
    assert ocr_engine.aadhaar_numbers("Aadhaar: 4821 6093 2200\nUHID SYN-400118") == ["482160932200"]
    assert ocr_engine.aadhaar_numbers("Aadhaar No.\n4821 6O93 22O0") == ["482160932200"]  # look-alikes read as digits
    assert ocr_engine.aadhaar_numbers("4821 6093 2200 12") == ["482160932200"]
    assert ocr_engine.aadhaar_numbers("Hb 11.8 g/dL\nLAB/26/118392\n05/09/2026 12:40") == []


@pytest.mark.parametrize("text", [
    "UID: 4B2I 6O93 22O0",                # labelled, look-alikes
    "Aadhar No 4821 6093 22O0",           # label read loosely, look-alike in the last group
    "Aadhaar No.\n4821-6093-22O0",        # label on the line above
    "4821 6093 22O0\nAadhaar",            # label on the line below
    "Aadhaar 4821 6093\n2200",            # split over two lines under the label
    "Ref 4821 6O93 2200 date",            # no label: groups with 6 or more real digits
])
def test_engine_loose_aadhaar_rules(text):
    masked, words, n, idx = ocr_engine.mask_words(text, _words_of(text))
    assert n >= 1 and idx and "4821" not in masked and "6093" not in masked and "6O93" not in masked and "4B2I" not in masked
    assert len(masked) == len(text)  # character for character: word boxes stay aligned
    assert all("X" in words[i][0] for i in idx)


@pytest.mark.parametrize("text", ["Hb 11.8 g/dL 13.0 - 17.0", "05/09/2026 08:02 05/09/2026 08:10", "LAB/26/118392 SYN-400118",
                                  "Platelets 2,45,000 /cumm", "BOSS lOIS SOIL"])
def test_engine_loose_rules_leave_ordinary_lines(text):
    assert ocr_engine.mask_words(text, _words_of(text)) == (text, _words_of(text), 0, [])


@pytest.mark.parametrize("text,masked_tokens", [
    ("Aadhaar: 4821-6093-2200", {"XXXX-XXXX-2200"}),                     # hyphenated: one word
    ("UID 482160932200", {"XXXXXXXX2200"}),                             # run together
    ("Aadhaar No. (4821 6093 2200)", {"(XXXX", "XXXX"}),               # punctuation attached
    ("Aadhaar:4821 6093 2200", {"Aadhaar:XXXX", "XXXX"}),              # label attached
])
def test_masked_words_records_every_word_with_a_masked_digit(text, masked_tokens):
    words = _words_of(text)
    masked, mw, n, idx = ocr_engine.mask_words(text, words)
    assert {mw[i][0] for i in idx} == masked_tokens and idx == sorted(set(idx))
    assert [w[1:] for w in mw] == [w[1:] for w in words]


def test_cross_mask_adds_masked_words_and_is_idempotent():
    t = "Name RAMESH 4821 6O93\nHb 11.8"
    read = {"text": t, "words": _words_of(t), "masked_words": [], "recheck": {"scale": 1.5, "text": "Ref 4821 6093"}}
    assert ocr_engine.cross_mask(read, ["482160932200"]) >= 1
    assert read["masked_words"] == [2, 3] and read["text"] == "Name RAMESH XXXX XXXX\nHb 11.8"
    assert read["recheck"]["text"] == "Ref XXXX XXXX" and read["aadhaar_masked"] >= 1
    before = json.dumps(read)
    assert ocr_engine.cross_mask(read, ["482160932200"]) == 0 and json.dumps(read) == before


def test_safety_net_masks_any_group_left(monkeypatch):
    """Whatever slipped past (a word that does not spell its line, an error text, a span's numbers): no group remains."""
    page = {"text": "Aadhaar: XXXX XXXX 2200\nRef 4821", "ocr_engine": {
                "text": "Aadhaar: XXXX XXXX 2200", "words": [["Aadhaar:", 0.1, 0.1, 0.2, 0.2, 90.0, 0], ["x4821y", 0.3, 0.1, 0.4, 0.2, 90.0, 0]],
                "masked_words": [], "note": "read 6093"},
            "ocr_uncertain_spans": [{"start": 24, "end": 32, "line": "Ref 4821", "numbers": ["4821"], "reason": "r"}],
            "ocr_uncertain_numbers": ["4821"]}
    ingest._aadhaar_safety_net(page, ["482160932200"])
    assert _no_leak(page["ocr_engine"], page["ocr_uncertain_spans"], page["ocr_uncertain_numbers"])
    assert 1 in page["ocr_engine"]["masked_words"] and page["ocr_uncertain_numbers"] == ["XXXX"]
    assert page["text"] == "Aadhaar: XXXX XXXX 2200\nRef 4821"  # the transcription itself is not the net's to change


# ---- review fixes: one digit added or removed (M2) ------------------------------------------------------------------
def test_insertion_and_deletion_need_the_reread_to_read_the_same_number():
    full, eng = "IHC REPORT\nPD-L1 TPS Score: 60%\nHb 1.2 g/dL", "IHC REPORT\nPD-L1 TPS Score: 6%\nHb 12 g/dL"
    assert ocr_engine.engine_spans(full, eng) == []  # one read: no substitution
    (s,) = ocr_engine.confirmed_spans(full, eng, eng)  # the re-read reads 6% again
    assert ocr_engine.confirmed_spans(full, eng, eng, indels=False) == []
    assert s["line"] == "PD-L1 TPS Score: 60%" and s["numbers"] == ["60"] and s["reason"] == ENGINE  # Hb: a point lost, no evidence
    assert ocr_engine.confirmed_spans(full, eng, full, indels=True) == []  # the re-read agrees with the transcription
    assert ocr_engine.confirmed_spans(full, eng, eng.replace("6%", "50%"), indels=True) == []  # another slip
    (s,) = ocr_engine.confirmed_spans("Ki-67 index: 5%", "Ki-67 index: 15%", "Ki-67 index: 15%", indels=True)  # reader dropped a digit
    assert s["numbers"] == ["5"]
    (s,) = ocr_engine.confirmed_spans("Ki-67 index: 15%", "Ki-67 index: 5%", "Ki-67 index: 5%", indels=True)
    assert s["numbers"] == ["15"]


@pytest.mark.parametrize("full,eng", [
    ("Haemoglobin 11.8 g/dL 13.0 - 17.0", "Haemoglobin 118 g/dl. 13.0-17.0"),            # same digits, decimal point lost
    ("Platelet count 198 x10^3/uL 150 - 410", "Platelet count 198 x103/uL 150 - 410"),   # two numbers run together
    ("cT2b N2 M0, Stage IIIA (AJCC 8th edition)", "c12b N2 M0, Stage IIIA (AJCC 8th edition)"),  # a letter read as a digit
    ("Hb 11.8 g/dL", "Hb 11.866 g/dL"),                                                   # two digits more: not one
])
def test_insertion_deletion_slips_that_are_not_evidence(full, eng):
    assert ocr_engine.confirmed_spans(full, eng, eng, indels=True) == []


def _fake_engine_words(monkeypatch, conf, *texts):
    """read_page with words of the given confidence (the insertion / deletion floor reads it)."""
    calls, it = [], iter(texts)

    async def read(png, audit=None, scale=1.0):
        calls.append(scale)
        t = next(it)
        return {"engine": "tesseract", "version": "5.5.3", "lang": "eng", "size": [1000, 1400], "text": t,
                "words": [w[:5] + [conf] + w[6:] for w in _words_of(t)], "masked_words": []}
    monkeypatch.setattr(ocr_engine, "read_page", read)
    return calls


def test_ocr_page_low_confidence_deletion_is_not_evidence(monkeypatch):
    """Tesseract cuts a leading digit ("17" read as "7") with a modest confidence, often again at 1.5x: not evidence."""
    t = "IHC REPORT\nKi-67 index: 15%\nReport status: FINAL"
    _reader(monkeypatch, t)
    calls = _fake_engine_words(monkeypatch, 60.0, t.replace("15%", "5%"))
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert "ocr_uncertain_spans" not in p and calls == [1.0]


def test_ocr_page_flags_a_confirmed_deletion(monkeypatch):
    t = "IHC REPORT\nKi-67 index: 15%\nReport status: FINAL"
    _reader(monkeypatch, t)
    calls = _fake_engine_words(monkeypatch, 95.0, t.replace("15%", "5%"), t.replace("15%", "5%"))
    events = []
    p = asyncio.run(ingest.ocr_page(b"png", audit=events.append))
    (s,) = p["ocr_uncertain_spans"]
    assert s["numbers"] == ["15"] and calls == [1.0, 1.5] and p["ocr_engine"]["recheck"]["confirmed"] == 1
    assert events == [{"kind": "ocr_engine_disagreement", "numbers": ["15"], "lines": 1}]


def test_reread_failure_keeps_substitutions_drops_insertions(monkeypatch):
    monkeypatch.setattr(ocr_engine, "CHECK_INDELS", True)
    full = "PD-L1 TPS 80%\nKi-67 index: 15%"
    eng = {"text": "PD-L1 TPS 60%\nKi-67 index: 5%", "size": [1000, 1000]}

    async def none(png, audit=None, scale=1.0):
        return None
    monkeypatch.setattr(ocr_engine, "read_page", none)
    kept = asyncio.run(ocr_engine.check_page(b"png", full, eng))
    assert [s["numbers"] for s in kept] == [["80"]] and eng["recheck"]["candidates"] == 2 and eng["recheck"]["confirmed"] is None


def test_reread_check_error_is_audited_first_spans_kept(monkeypatch):
    """m4: an exception while checking the re-read keeps the first read's spans and is audited."""
    full = "PD-L1 TPS 80%"
    eng = {"text": "PD-L1 TPS 60%", "size": [1000, 1000]}

    async def again(png, audit=None, scale=1.0):
        return {"text": "PD-L1 TPS 60%"}
    monkeypatch.setattr(ocr_engine, "read_page", again)

    def boom(*a, **k):
        raise ValueError("bad re-read")
    monkeypatch.setattr(ocr_engine, "confirmed_spans", boom)
    events = []
    kept = asyncio.run(ocr_engine.check_page(b"png", full, eng, events.append))
    assert [s["numbers"] for s in kept] == [["80"]] and "text" not in eng["recheck"]
    assert events[0]["kind"] == "ocr_engine_error" and "bad re-read" in events[0]["error"]


def test_engine_info_caches_a_failed_version_read(monkeypatch, tmp_path):
    """m8: a binary whose version cannot be read is asked once, not on every page."""
    b = tmp_path / "tesseract"
    b.write_text("#!/bin/sh\nexit 1\n"); b.chmod(0o755)
    monkeypatch.setenv("TB_TESSERACT", str(b))
    monkeypatch.delenv("TB_OCR_ENGINE", raising=False)
    monkeypatch.setattr(ocr_engine, "_version_cache", {})
    calls = []

    def run(*a, **k):
        calls.append(a)
        raise OSError("cannot run")
    monkeypatch.setattr(ocr_engine.subprocess, "run", run)
    assert ocr_engine.engine_info() is None and ocr_engine.engine_info() is None and len(calls) == 1


# ---- with the real binary -------------------------------------------------------------------------------------------
IHC_LINES = ["Sahyadri Cancer Institute (SYNTHETIC)", "IHC REPORT", "UHID SYN-400118",
             "PD-L1 (22C3) Tumour Proportion Score: 60%", "Ki-67 index: 35%", "Report status: FINAL"]


def _png(lines) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default(size=28)
    im = Image.new("L", (1100, 60 + 50 * len(lines)), 255)
    d = ImageDraw.Draw(im)
    for k, line in enumerate(lines):
        d.text((40, 30 + 50 * k), line, fill=0, font=font)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return buf.getvalue()


needs_binary = pytest.mark.skipif(not ocr_engine.available(), reason="Tesseract not installed")


@needs_binary
def test_done_when_one_wrong_digit_both_reads_share_is_flagged(monkeypatch):
    """V1 8.3 Done when: both model reads say 80% (the two-read check cannot see it); the engine reads 60% on the image."""
    wrong = "\n".join(IHC_LINES).replace("60%", "80%")
    _reader(monkeypatch, wrong, wrong)
    events = []
    p = asyncio.run(ingest.ocr_page(_png(IHC_LINES), audit=events.append))
    (s,) = p["ocr_uncertain_spans"]
    assert s["line"] == "PD-L1 (22C3) Tumour Proportion Score: 80%" and s["reason"] == ENGINE and s["numbers"] == ["80"]
    assert p["text"] == wrong and p["ocr_engine"]["engine"] == "tesseract" and p["ocr_engine"]["version"].startswith("5.")
    assert {"kind": "ocr_engine_disagreement", "numbers": ["80"], "lines": 1} in events
    loc = p["text"].index("80%")
    assert ingest.uncertain_overlap(p, loc, loc + 3) is s


@needs_binary
def test_real_read_word_format(monkeypatch):
    r = asyncio.run(ocr_engine.read_page(_png(IHC_LINES)))
    assert r["engine"] == "tesseract" and r["lang"] == "eng" and r["size"] == [1100, 360]
    assert "PD-L1 (22C3) Tumour Proportion Score: 60%" in r["text"]
    lines = r["text"].split("\n")
    for t, x0, y0, x1, y1, conf, n in r["words"]:
        assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1 and isinstance(conf, float) and t in lines[n].split(" ")
    w = next(w for w in r["words"] if w[0] == "60%")
    assert w[6] == lines.index("PD-L1 (22C3) Tumour Proportion Score: 60%")


@needs_binary
def test_real_read_masks_aadhaar():
    r = asyncio.run(ocr_engine.read_page(_png(["Aadhaar No. 6043 1187 2200", "Hb 11.8 g/dL"])))
    blob = json.dumps(r)
    assert "6043" not in blob and "1187" not in blob and "XXXX XXXX 2200" in r["text"] and r["aadhaar_masked"] == 1
    assert r["masked_words"] and {r["words"][i][0] for i in r["masked_words"]} == {"XXXX"}


@needs_binary
def test_real_read_cross_masks_the_readers_aadhaar(monkeypatch):
    """The engine sees the two groups without a label or the last group (no rule of its own can tell): the reader's
    number masks them."""
    _reader(monkeypatch, "Aadhaar: 6043 1187 2200\nHb 11.8 g/dL")
    events = []
    p = asyncio.run(ingest.ocr_page(_png(["Ref 6043 1187", "Hb 11.8 g/dL"]), audit=events.append))
    blob = json.dumps([p, events])
    assert "6043" not in blob and "1187" not in blob and "Ref XXXX XXXX" in p["ocr_engine"]["text"]
    assert len(p["ocr_engine"]["masked_words"]) == 2


@needs_binary
def test_real_read_error_is_audited_never_raised():
    events = []
    assert asyncio.run(ocr_engine.read_page(b"not an image", events.append)) is None
    assert events and events[0]["kind"] == "ocr_engine_error"
