"""ocr_boxes: transcription tokens mapped to OCR engine word boxes (V1 item 8.4). Synthetic word lists only, no images."""
import random
import re
import time

from tumour_board import ocr_boxes as ob

LINE_H = 0.02
GAP = 0.03


def layout(lines, x0=0.05, gap=GAP, line_h=LINE_H):
    """Engine words for lines of tokens: [text, x0, y0, x1, y1, conf, line_no], one text line per list."""
    words = []
    for ln, toks in enumerate(lines):
        x, y = x0, round(0.05 + ln * gap, 4)
        for t in toks:
            w = 0.01 * max(1, len(t))
            words.append([t, round(x, 4), y, round(x + w, 4), round(y + line_h, 4), 95, ln])
            x += w + 0.01
    return words


def word_box(words, text):
    hits = [w for w in words if w[0] == text]
    assert len(hits) == 1, (text, hits)
    return hits[0][1:5]


def span(text, quote, nth=0):
    s = -1
    for _ in range(nth + 1):
        s = text.index(quote, s + 1)
    return s, s + len(quote)


def boxes(text, words, quote, nth=0):
    return ob.boxes_for_span(ob.token_map(text, words), *span(text, quote, nth))


def inside(outer, inner):
    return outer[0] <= inner[0] + 1e-9 and outer[1] <= inner[1] + 1e-9 and outer[2] >= inner[2] - 1e-9 and outer[3] >= inner[3] - 1e-9


def digits_safe(text, words, tmap):
    """Every boxed token shows the same numbers as the engine words inside its box (a highlight never points at another number)."""
    for s, e, *r in tmap:
        tok = re.findall(r"\d+(?:\.\d+)?", text[s:e].replace(",", ""))
        under = [w[0] for w in words if inside(r, w[1:5])]
        got = [n for w in under for n in re.findall(r"\d+(?:\.\d+)?", w.replace(",", ""))]
        if tok:
            assert got == tok, (text[s:e], under)


def test_exact_match_every_token_boxed():
    lines = [["Haemoglobin", "11.2", "g/dL"], ["Platelets", "2,45,000", "/cumm"]]
    text = "Haemoglobin 11.2 g/dL\nPlatelets 2,45,000 /cumm"
    words = layout(lines)
    tmap = ob.token_map(text, words)
    assert len(tmap) == 6
    assert [t[0] for t in tmap] == sorted(t[0] for t in tmap)
    assert all(isinstance(v, int) for t in tmap for v in t[:2])
    s, e = span(text, "11.2")
    assert [t[:2] for t in tmap if t[2:] == word_box(words, "11.2")] == [[s, e]]
    b = ob.boxes_for_span(tmap, s, e)
    x0, y0, x1, y1 = word_box(words, "11.2")
    assert b == [[round(x0 - 0.003, 4), round(y0 - 0.003, 4), round(x1 + 0.003, 4), round(y1 + 0.003, 4)]]
    assert ob.span_coverage(tmap, text, 0, len(text)) == 1.0


def test_case_and_punctuation_differences():
    text = "ER: POSITIVE (Allred score 8/8)."
    words = layout([["er", "positive", "allred", "Score:", "8/8"]])
    tmap = ob.token_map(text, words)
    assert ob.span_coverage(tmap, text, 0, len(text)) == 1.0
    assert boxes(text, words, "8/8)")[0][0] < word_box(words, "8/8")[0]


def test_table_pipes_in_transcription_and_engine():
    text = "| Test | Result | Unit |\n|---|---|---|\n| Hb | 11.2 | g/dL |\n| TLC | 7,200 | /cumm |"
    words = layout([["Test", "|", "Result", "Unit"], ["Hb", "11.2", "|", "g/dL"], ["TLC", "7200", "/cumm"]])
    tmap = ob.token_map(text, words)
    assert ob.span_coverage(tmap, text, 0, len(text)) == 1.0
    assert inside(boxes(text, words, "11.2")[0], word_box(words, "11.2"))
    assert inside(boxes(text, words, "7,200")[0], word_box(words, "7200"))  # thousands comma ignored, same digits
    digits_safe(text, words, tmap)


def test_split_and_merged_tokens():
    # "60 %" vs "60%", "IHC:" vs "IHC :", "Ki-67" vs "Ki- 67", "ER positive" vs "ERpositive"
    text = "IHC: PD-L1 TPS 60 % Ki-67 index ER positive"
    words = layout([["IHC", ":", "PD-L1", "TPS", "60%", "Ki-", "67", "index", "ERpositive"]])
    tmap = ob.token_map(text, words)
    assert ob.span_coverage(tmap, text, 0, len(text)) == 1.0
    assert inside(boxes(text, words, "60 %")[0], word_box(words, "60%"))
    k = boxes(text, words, "Ki-67")
    assert len(k) == 1 and inside(k[0], word_box(words, "Ki-")) and inside(k[0], word_box(words, "67"))
    assert inside(boxes(text, words, "ER")[0], word_box(words, "ERpositive"))
    # and the other way round: the transcription joins what the engine split
    text2 = "TPS 60% IHC : done"
    words2 = layout([["TPS", "60", "%", "IHC:", "done"]])
    tmap2 = ob.token_map(text2, words2)
    assert ob.span_coverage(tmap2, text2, 0, len(text2)) == 1.0
    assert inside(boxes(text2, words2, "60%")[0], word_box(words2, "60"))


def test_split_digits_never_join_into_another_number():
    for text, engine in (("value 7.2 mg", ["value", "7.", "2", "mg"]), ("ratio 1/2 seen", ["ratio", "12", "seen"]),
                         ("count 12 cells", ["count", "1", "2", "cells"])):
        words = layout([engine])
        tmap = ob.token_map(text, words)
        assert boxes(text, words, text.split()[1]) == [], text
        digits_safe(text, words, tmap)


def test_fuzzy_word_paired_short_words_not():
    text = "Adenocarcinoma ER PR"
    words = layout([["Adenocarcinorna", "PR", "ER"]])
    tmap = ob.token_map(text, words)
    assert inside(boxes(text, words, "Adenocarcinoma")[0], word_box(words, "Adenocarcinorna"))
    for t in ("ER", "PR"):  # order swapped: each short word is mapped to its own box or to none, never the other's
        b = boxes(text, words, t)
        assert b == [] or inside(b[0], word_box(words, t))


def test_repeated_tokens_map_to_the_right_occurrence():
    lines = [["Cycle", str(i), "dose", "1", "unit", "day", "1"] for i in range(1, 9)]
    text = "\n".join(" ".join(l) for l in lines)
    words = layout(lines)
    words = [w for w in words if not (w[6] == 4 and w[0] == "dose")]  # the engine missed a word on line 5
    words = [["d0se", *w[1:]] if (w[6] == 6 and w[0] == "dose") else w for w in words]  # and garbled one on line 7
    tmap = ob.token_map(text, words)
    for ln in range(8):
        for nth_on_line, q in ((0, "1"), (1, "1")):
            line_start = sum(len(" ".join(l)) + 1 for l in lines[:ln])
            row = text[line_start:line_start + len(" ".join(lines[ln]))]
            idx = [m.start() for m in re.finditer(r"(?<!\S)1(?!\S)", row)]
            # positions of "dose 1" and "day 1" ones (skip the cycle number on line 1)
            s = line_start + idx[-2 + nth_on_line]
            b = ob.boxes_for_span(tmap, s, s + 1)
            assert len(b) == 1, (ln, b)
            y = 0.05 + ln * GAP
            assert abs(b[0][1] - (y - 0.003)) < 1e-6, (ln, b)  # on its own line, not the first "1" on the page
    digits_safe(text, words, tmap)


def test_extra_line_in_transcription_does_not_shift_boxes():
    lines = [["Sodium", "138", "mmol/L"], ["Potassium", "4.1", "mmol/L"], ["Chloride", "101", "mmol/L"]]
    text = "SYNTHETIC LAB REPORT page 1\n" + "\n".join(" ".join(l) for l in lines)
    words = layout(lines)
    tmap = ob.token_map(text, words)
    for ln in range(3):
        b = boxes(text, words, "mmol/L", nth=ln)
        assert len(b) == 1 and abs(b[0][1] - (0.05 + ln * GAP - 0.003)) < 1e-6
    assert boxes(text, words, "SYNTHETIC LAB REPORT page 1") == []


def test_different_number_gets_no_box():
    text = "PD-L1 TPS 60% (22C3)"
    words = layout([["PD-L1", "TPS", "80%", "(22C3)"]])
    tmap = ob.token_map(text, words)
    s, e = span(text, "60%")
    assert ob.boxes_for_span(tmap, s, e) == []
    assert ob.span_coverage(tmap, text, s, e) == 0.0
    assert ob.boxes_for_span(tmap, *span(text, "TPS")) != []
    digits_safe(text, words, tmap)
    # a long word that differs only in its digits is not paired either
    text2 = "Specimen SP-2026-0461 received"
    words2 = layout([["Specimen", "SP-2026-0481", "received"]])
    assert boxes(text2, words2, "SP-2026-0461") == []


def test_illegible_marker_gets_no_box_neighbours_do():
    text = "Margin [illegible] mm from tumour"
    words = layout([["Margin", "3", "mm", "from", "tumour"]])
    tmap = ob.token_map(text, words)
    assert boxes(text, words, "[illegible]") == []
    assert boxes(text, words, "mm from tumour") != []
    digits_safe(text, words, tmap)


def test_span_across_two_lines_gives_two_rectangles():
    lines = [["Final", "diagnosis:", "invasive", "ductal"], ["carcinoma", "grade", "2"]]
    text = "Final diagnosis: invasive ductal\ncarcinoma grade 2"
    words = layout(lines)
    b = boxes(text, words, "invasive ductal\ncarcinoma grade")
    assert len(b) == 2
    assert b[0][1] < b[1][1]
    assert inside(b[0], word_box(words, "invasive")) and inside(b[0], word_box(words, "ductal"))
    assert inside(b[1], word_box(words, "carcinoma")) and inside(b[1], word_box(words, "grade"))
    assert not inside(b[1], word_box(words, "2"))
    assert all(0 <= v <= 1 for r in b for v in r)


def test_boxes_clipped_to_page():
    words = [["Edge", 0.0, 0.0, 0.1, 0.02, 90, 0], ["word", 0.9, 0.98, 1.0, 1.0, 90, 1]]
    tmap = ob.token_map("Edge word", words)
    assert ob.boxes_for_span(tmap, 0, 9) == [[0.0, 0.0, 0.103, 0.023], [0.897, 0.977, 1.0, 1.0]]


def test_span_with_no_matched_token():
    text = "Remarks: kindly correlate clinically"
    words = layout([["Remarks", "something", "else"]])
    tmap = ob.token_map(text, words)
    s, e = span(text, "kindly correlate clinically")
    assert ob.boxes_for_span(tmap, s, e) == []
    assert ob.span_coverage(tmap, text, s, e) == 0.0
    assert ob.span_coverage(tmap, text, 0, len(text)) == 0.25


def test_reordered_table_never_points_at_another_number():
    # vision model reads row by row, engine reads column by column: any box given must show the same number
    rows = [["1", "2", "3"], ["2", "1", "1"], ["1", "1", "2"], ["3", "2", "1"]]
    text = "Counts\n" + "\n".join(" | ".join(r) for r in rows) + "\nEnd of table"
    cells = layout([["Counts"]] + rows + [["End", "of", "table"]], gap=0.04)
    head, grid, tail = cells[:1], cells[1:13], cells[13:]
    words = head + [grid[r * 3 + c] for c in range(3) for r in range(4)] + tail
    tmap = ob.token_map(text, words)
    digits_safe(text, words, tmap)
    assert boxes(text, words, "Counts") and boxes(text, words, "End of table")


def test_small_differing_stretch_pairs_repeated_tokens_in_order():
    text = "Margin 1 cm free 1 cm deep"
    words = layout([["Margin", "1", "crn", "frec", "1", "cm", "deep"]])
    tmap = ob.token_map(text, words)
    ones = [w for w in words if w[0] == "1"]
    assert inside(boxes(text, words, "1", nth=0)[0], ones[0][1:5])
    assert inside(boxes(text, words, "1", nth=1)[0], ones[1][1:5])
    digits_safe(text, words, tmap)


def test_aadhaar_masked_words():
    words = layout([["Aadhaar", "XXXX", "XXXX", "4821", "UHID", "XXL"]])
    m = ob.masked_boxes(words)
    assert len(m) == 2
    for r, w in zip(m, [w for w in words if w[0] == "XXXX"]):
        assert inside(r, w[1:5])
    assert ob.masked_boxes([]) == [] and ob.masked_boxes(None) == []
    # the masked groups never match transcribed digits
    text = "Aadhaar 1234 5678 4821 UHID 445566"
    tmap = ob.token_map(text, words)
    assert boxes(text, words, "1234 5678") == []
    digits_safe(text, words, tmap)


def test_empty_and_malformed_inputs():
    assert ob.token_map("some text", []) == []
    assert ob.token_map("some text", None) == []
    assert ob.token_map("", layout([["a"]])) == []
    assert ob.token_map("| --- |", layout([["|"]])) == []
    assert ob.boxes_for_span([], 0, 10) == []
    assert ob.span_coverage([], "text here", 0, 9) == 0.0
    assert ob.span_coverage([], "", 0, 0) == 0.0
    words = [["Hb", 0.1, 0.1, 0.2, 0.12, 90, 0], ["bad"], [None, "x", 0, 0, 0], ["", 0.3, 0.1, 0.4, 0.12, -1, 0]]
    assert len(ob.token_map("Hb", words)) == 1


def test_devanagari_word_keeps_vowel_signs():
    text = "निदान कैंसर"
    words = layout([["निदान", "कैंसर"]])
    tmap = ob.token_map(text, words)
    assert ob.span_coverage(tmap, text, 0, len(text)) == 1.0
    assert tmap[0][:2] == [0, len("निदान")]


def _noisy_page(seed, n_tokens=600):
    rng = random.Random(seed)
    vocab = ["Haemoglobin", "g/dL", "Platelets", "lakhs/cumm", "TLC", "Neutrophils", "Lymphocytes", "creatinine", "mg/dL",
             "carcinoma", "grade", "margin", "positive", "negative", "ER", "PR", "HER2", "Ki-67", "IHC:", "TPS", "|", "SYNTHETIC"]
    lines, cur = [], []
    for _ in range(n_tokens):
        cur.append(rng.choice(vocab) if rng.random() < 0.6 else str(rng.choice([1, 2, 3, 60, 7.2, 11.4, 245000, 1, 1])))
        if len(cur) >= 10:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    text = "\n".join(" ".join(l) for l in lines)
    eng = []
    for l in lines:
        e = []
        for t in l:
            r = rng.random()
            if t == "|" and r < 0.5:
                continue
            if r < 0.03:
                continue  # missed word
            if r < 0.06:
                e.append(t[:-1] + ("x" if not t[-1].isdigit() else str((int(t[-1]) + 1) % 10)))  # garbled letter / digit
            elif r < 0.08 and len(t) > 3:
                e += [t[:2], t[2:]]  # split
            else:
                e.append(t)
        eng.append(e)
    return text, layout(eng, gap=0.014, line_h=0.01)


def test_speed_600_token_page_and_safety_under_noise():
    text, words = _noisy_page(7)
    assert len(re.findall(r"[^\s|]+", text)) >= 550
    best = min(_timed(ob.token_map, text, words) for _ in range(3))
    assert best < 0.05, best
    tmap = ob.token_map(text, words)
    digits_safe(text, words, tmap)
    assert ob.span_coverage(tmap, text, 0, len(text)) > 0.85
    t0 = time.perf_counter()
    for seed in range(100):  # a 100-page scanned document
        ob.token_map(*_noisy_page(seed))
    assert time.perf_counter() - t0 < 10


def _timed(f, *a):
    t0 = time.perf_counter()
    f(*a)
    return time.perf_counter() - t0


def test_quote_coverage_against_suggested_threshold():
    # a typical quote with one OCR-garbled number still clears the suggested threshold; a quote the engine did not read does not
    text = "Tumour size 3.2 x 2.1 cm, margins free (closest 4 mm)."
    words = layout([["Tumour", "size", "3.2", "x", "2.7", "cm,", "margins", "free", "(closest", "4", "mm)."]])
    tmap = ob.token_map(text, words)
    q = span(text, "Tumour size 3.2 x 2.1 cm")
    assert ob.span_coverage(tmap, text, *q) >= ob.SUGGESTED_COVERAGE
    assert ob.span_coverage(tmap, text, *span(text, "2.1")) == 0.0
    digits_safe(text, words, tmap)


def test_masked_boxes_cover_every_masked_form_and_follow_the_engine_indices():
    """Review S2: hyphenated, run-together and punctuation-attached groups are blacked out too; the engine's masked word indices win."""
    words = layout([["Aadhaar:XXXX", "XXXX", "2200"], ["(XXXX", "XXXX-XXXX-2200", "XXXXXXXX2200", "UHID", "SYN-1"]])
    assert len(ob.masked_boxes(words)) == 5  # every word containing XXXX (pages read before the engine kept indices)
    assert len(ob.masked_boxes(words, indices=[0, 1, 6, 99, "x"])) == 3  # exactly the listed words; out-of-range and malformed indices ignored
    assert ob.masked_boxes(words, indices=[]) == []
