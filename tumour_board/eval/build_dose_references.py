"""Build the guideline dose / radiotherapy reference table for the guideline checks (V1 item 7.2).

    python -m tumour_board.eval.build_dose_references [--index PATH] [--candidates OUT.json] [--write] [--unknown]

Reads the guideline index cache (data/tumour_board/embed_cache/guidelines_index.json, key "chunks": {text, file, title, org,
region, page, page_end}; built by tumour_board.guidelines from the files in TB_GUIDELINE_DIR). Never written from memory:
every entry is a line of a guideline file, quoted verbatim with its page.

Step 1, scan (code): for each protocol's cancer, the chunks of that cancer's files (multi-cancer files: only chunks naming the
cancer) are scanned for
  - a drug name (generic name or an alias the guideline text itself uses, e.g. NCG "Adriamycin") followed by a dose and a unit
    (mg/m2, mg/kg, mg, g/m2, AUC; ranges "1000-1250 mg/m2"); every dose before the next drug name is its own candidate
    ("Paclitaxel 175 mg/m2 q 3 weekly or 80 mg/m2 q weekly" gives 175 and 80);
  - radiotherapy schedules: total Gy with fractions ("50 Gy in 25 fractions", "25 Gy/5#", "45-50.4 Gy in 25-28 fractions",
    "40Gy/15fractions", "5 x 5 Gy", "8 Gy single fraction").
  The quote is the source line holding the dose (continued onto the next line when the dose runs over a line break), exactly as
  in the chunk text apart from whitespace. --candidates writes every candidate with its id for reading.
Step 2, curate (by reading the candidates, recorded below): PAGES limits a file to the pages of the right cancer (NCG thoracic
also covers SCLC, thymoma, mesothelioma and oesophagus); DROP_QUOTE drops lines that are not a dosing statement (dose
reductions, cumulative limits, HDR boosts); DROP lists candidate ids dropped by reading (dose comparisons, some trial arm details,
other cancers, a unit misprint). Every kept line gets a source_kind: "regimen" (a regimen or schedule line) or "trial_summary" (a
line describing what a trial gave its patients: trial names, arms, "(n = ...)", "randomly assigned", "patients received"); the code
reads the trial wording in the quote and the sentence before it (TRIAL_RX) and SOURCE_KIND records the corrections made by reading
every row. The same dose (or schedule) is kept once per file: its first regimen line, else its first trial summary line. The
parsers are the checker's own (dosecheck.parse_doses / parse_rt), so the table and the check read doses and units the same way.
--write writes tumour_board/protocols/dose_references.json, Indian sources first. --unknown prints words written just before a
dose that are not in the drug lexicon (to extend DRUGS when a new guideline file is added).

The table is a reference for the clinical team to review before real use; coverage is limited to the doses our guideline files
state. Rebuild after adding a guideline file: rebuild the guideline index, run with --candidates, read the new candidates, update
PAGES / DROP_QUOTE / DROP / SOURCE_KIND, then --write. A DROP or SOURCE_KIND id that is no longer produced is printed.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tumour_board import config, dosecheck  # noqa: E402

OUT = config.PROTOCOL_DIR / "dose_references.json"
REGION_ORDER = {"India": 0, "International": 1, "UK": 2, "US": 3}

# Generic oncology drug names (detection lexicon only; doses always come from the guideline text).
DRUGS = [
    "abemaciclib", "afatinib", "alectinib", "amivantamab", "anastrozole", "atezolizumab", "bevacizumab", "brigatinib",
    "capecitabine", "carboplatin", "ceritinib", "cetuximab", "cisplatin", "crizotinib", "cyclophosphamide", "dabrafenib",
    "docetaxel", "doxorubicin", "durvalumab", "encorafenib", "epirubicin", "eribulin", "erlotinib", "etoposide", "everolimus",
    "exemestane", "fluorouracil", "fulvestrant", "gefitinib", "gemcitabine", "goserelin", "ifosfamide", "ipilimumab",
    "irinotecan", "lapatinib", "leucovorin", "letrozole", "leuprolide", "lorlatinib", "methotrexate", "mitomycin", "neratinib",
    "nivolumab", "olaparib", "osimertinib", "oxaliplatin", "paclitaxel", "palbociclib", "panitumumab", "pembrolizumab",
    "pemetrexed", "pertuzumab", "raltitrexed", "regorafenib", "ribociclib", "tamoxifen", "trastuzumab", "trastuzumab deruxtecan",
    "trastuzumab emtansine", "trifluridine", "vinorelbine", "zoledronic acid", "denosumab", "selpercatinib", "pralsetinib",
    "capmatinib", "tepotinib", "sotorasib", "adagrasib", "entrectinib", "larotrectinib", "lenvatinib", "ramucirumab",
    "aflibercept", "tremelimumab", "cemiplimab", "dostarlimab", "nab-paclitaxel", "topotecan", "vincristine", "prednisone",
    "tucatinib", "alpelisib", "sacituzumab govitecan", "fruquintinib", "tegafur", "uracil", "trametinib", "binimetinib",
    "necitumumab", "datopotamab deruxtecan", "rituximab", "levamisole", "celecoxib",
]
# Aliases the guideline text itself uses (and the standard abbreviation 5-FU); brand names come only from the hospital formulary.
ALIASES = {"adriamycin": "doxorubicin", "5-fluorouracil": "fluorouracil", "5-fu": "fluorouracil", "5fu": "fluorouracil",
           "fluorouracil": "fluorouracil", "folinic acid": "leucovorin", "tdm1": "trastuzumab emtansine",
           "t-dm1": "trastuzumab emtansine", "nab paclitaxel": "nab-paclitaxel", "zoledronate": "zoledronic acid",
           "trifluridine/tipiracil": "trifluridine", "flurouracil": "fluorouracil", "lv": "leucovorin", "dato-dxd": "datopotamab deruxtecan"}

# Files per protocol cancer. "all": the whole file is about this cancer; a regex: a multi-cancer file, only chunks naming it.
SOURCES = {
    "breast": [
        ("ncg_india/ncg-guidelines-for-breast-cancer-2019.pdf", "all"),
        ("icmr/Breast_Cancer.pdf", "all"),
        ("tmc/tata-memorial-centre-evidence-based-management-of-breast.pdf", "all"),
        ("ncg_india/ncg-guidelines-manual-2021.pdf", r"\bbreast\b"),
        ("icmr/ICMR-STW-oncology-all-2020.pdf", r"\bbreast\b"),
        ("esmo/ESMO_PanAsian_2024_early_breast_cancer.pdf", "all"),
        ("esmo/ESMO_2024_early_breast_cancer_Loibl.pdf", "all"),
        ("nice/NG101-early-and-locally-advanced-breast-cancer.pdf", "all"),
        ("nci_pdq/breast-treatment-pdq.txt", "all"),
    ],
    "lung_nsclc": [
        ("ncg_india/ncg-guidelines-for-thoracic-cancer-2019.pdf", "all"),
        ("ncg_india/ncg-guidelines-manual-2021.pdf", r"\b(lung|nsclc)\b"),
        ("icmr/ICMR-STW-oncology-all-2020.pdf", r"\b(lung|nsclc)\b"),
        ("esmo/ESMO_2025_early_locally_advanced_NSCLC.pdf", "all"),
        ("esmo/ESMO_2023_non_oncogene_addicted_mNSCLC_Hendriks.pdf", "all"),
        ("esmo/ESMO_2023_oncogene_addicted_mNSCLC_Hendriks.pdf", "all"),
        ("esmo/ESMO_PanAsian_2024_oncogene_addicted_mNSCLC.pdf", "all"),
        ("nice/NG122-lung-cancer-diagnosis-and-management.pdf", "all"),
        ("nci_pdq/non-small-cell-lung-treatment-pdq.txt", "all"),
    ],
    "colorectal_rectum": [
        ("ncg_india/ncg-rectal-cancer.docx", "all"),
        ("icmr/Colorectal_Cancer_0.pdf", "all"),
        ("tmc/tata-memorial-centre-evidence-based-management-of-colorectal.pdf", "all"),
        ("ncg_india/ncg-guidelines-manual-2021.pdf", r"\b(rect\w*|colorectal|colon)\b"),
        ("icmr/ICMR-STW-oncology-all-2020.pdf", r"\b(rect\w*|colorectal|colon)\b"),
        ("esmo/ESMO_2025_localised_rectal_cancer.pdf", "all"),
        ("esmo/ESMO_2020_localised_colon_cancer_Argiles.pdf", "all"),
        ("esmo/ESMO_PanAsian_2023_metastatic_colorectal_cancer.pdf", "all"),
        ("nice/NG151-colorectal-cancer.pdf", "all"),
        ("nci_pdq/rectal-treatment-pdq.txt", "all"),
        ("nci_pdq/colon-treatment-pdq.txt", "all"),
    ],
    # V1 item 9.1: only Indian sources on disk for oral cavity (no ESMO, NICE or NCI PDQ head and neck file)
    "oral_cavity": [
        ("ncg_india/ncg-guidelines-for-head-neck-cancer-2019.pdf", "all"),
        ("ncg_india/ncg-guidelines-manual-2021.pdf", r"\b(oral (cavity|cancer)|buccal|head and neck)\b"),
        ("icmr/ICMR-STW-oncology-all-2020.pdf", r"\b(oral (cavity|cancer)|buccal|head and neck)\b"),
    ],
    # V1 item 9.2: Indian sources only on disk for cervix (no ESMO, NICE or NCI PDQ cervix file)
    "cervix": [
        ("ncg_india/ncg-guidelines-for-gynecological-cancer-2019.docx", "all"),
        ("ncg_india/ncg-guidelines-manual-2021.pdf", r"\b(cervix|carcinoma cervix|cervical (cancer|carcinoma))\b"),
        ("icmr/ICMR-STW-oncology-all-2020.pdf", r"\b(cervix|carcinoma cervix|cervical (cancer|carcinoma))\b"),
    ],
}

# Curation (step 2), recorded after reading the candidates. Pages of a file kept for a cancer (others are another cancer).
PAGES = {
    # NCG thoracic 2019: p8 lung RT (mesothelioma lines dropped below), p9-10 NSCLC chemotherapy and targeted therapy;
    # p11 SCLC, p14 thymoma, p17-20 oesophagus / GEJ are other cancers.
    ("lung_nsclc", "ncg_india/ncg-guidelines-for-thoracic-cancer-2019.pdf"): {8, 9, 10},
    # NCG head and neck 2019: p4-9 oral cancer (work-up, surgery, adjuvant therapy, NACT and palliative regimens); p10 onwards are other
    # head and neck sites (oropharynx, larynx ...), the recurrent / metastatic chart (p36) repeats the oral p8-9 regimens.
    ("oral_cavity", "ncg_india/ncg-guidelines-for-head-neck-cancer-2019.pdf"): {4, 5, 6, 7, 8, 9},
    # NCG gynaecological 2019 (Word file, 6,000-character parts): parts 1-5 hold the cervix chapter (part 1 opens with the front matter,
    # part 5 ends the cervix table and opens the ovarian chapter, which has no dose line in that part); 6 onwards ovary, endometrium, vulva.
    ("cervix", "ncg_india/ncg-guidelines-for-gynecological-cancer-2019.docx"): {1, 2, 3, 4, 5},
}
# Lines that are not a dosing statement: dose reductions, caps, cumulative limits, HDR boosts.
DROP_QUOTE = [r"reduce[sd]? (the )?(starting )?dose|dose reduces|reduced starting dose|use starting dose|reduce the \w+ dose",
              r"cumulative dose|not exceeding", r"HDR boost"]
# Candidate ids (a trailing * drops every id with that prefix), after reading the candidates.
DROP = {
    # breast
    "breast:esmo-2024-early-breast-cance:p19:ribociclib:400mg/day",  # trial description ("evaluated the addition of"), not a dosing line
    "breast:breast-treatment-pdq:p20:rt:54Gy/30", "breast:breast-treatment-pdq:p20:rt:45Gy/15",  # brachial plexus toxicity comparison
    "breast:tata-memorial-centre-evidenc:p18:rt:24Gy/2",  # spine SBRT trial result
    # lung (NSCLC)
    "lung_nsclc:ncg-guidelines-for-thoracic:p8:rt:25Gy/10", "lung_nsclc:ng122-lung-cancer-diagnosis:p37:rt:25Gy/10",  # prophylactic cranial RT (SCLC)
    "lung_nsclc:ncg-guidelines-for-thoracic:p8:rt:45-55.8Gy/25-31", "lung_nsclc:ncg-guidelines-for-thoracic:p8:rt:20-30Gy/5-10#2",  # mesothelioma
    "lung_nsclc:non-small-cell-lung-treatmen:p47:alectinib:300mg",  # the Japan dose, stated as lower than the approved dose
    "lung_nsclc:non-small-cell-lung-treatmen:p56:everolimus:10mg", "lung_nsclc:non-small-cell-lung-treatmen:p73:everolimus:10mg",  # neuroendocrine tumours
    "lung_nsclc:non-small-cell-lung-treatmen:p72:pembrolizumab:*",  # dose comparison (2 vs 10 mg/kg)
    # colorectal / rectum
    "colorectal_rectum:esmo-panasian-2023-metastati:p3:irinotecan:180mg/m2", "colorectal_rectum:esmo-panasian-2023-metastati:p6:irinotecan:180mg/m2",  # UGT1A1 threshold
    "colorectal_rectum:colorectal-cancer-0:p67:bevacizumab:7.5mg/m2",  # unit printed as mg/m2 beside 5 mg/kg; not used as a reference
    "colorectal_rectum:colorectal-cancer-0:p71:irinotecan:180mg",  # table cell, unit cut off
    "colorectal_rectum:tata-memorial-centre-evidenc:p15:mitomycin:30mg/m2",  # HIPEC trial
    "colorectal_rectum:rectal-treatment-pdq:p16:fluorouracil:450mg/m2/day", "colorectal_rectum:rectal-treatment-pdq:p16:fluorouracil:300mg/m2/day*",
    "colorectal_rectum:rectal-treatment-pdq:p16:fluorouracil:425mg/m2/day", "colorectal_rectum:rectal-treatment-pdq:p16:fluorouracil:380mg/m2/day",
    "colorectal_rectum:rectal-treatment-pdq:p16:fluorouracil:400mg/m2/day", "colorectal_rectum:rectal-treatment-pdq:p16:leucovorin:*",  # trial arm details
    "colorectal_rectum:rectal-treatment-pdq:p16:levamisole:150mg/day",  # trial arm detail
    "colorectal_rectum:rectal-treatment-pdq:p18:oxaliplatin:60mg/m2", "colorectal_rectum:rectal-treatment-pdq:p18:fluorouracil:250mg/m2",  # trial arms
    "colorectal_rectum:rectal-treatment-pdq:p28:pembrolizumab:10mg/kg", "colorectal_rectum:colon-treatment-pdq:p22:pembrolizumab:10mg/kg",  # dose comparison
    "colorectal_rectum:rectal-treatment-pdq:p27:sotorasib:240mg", "colorectal_rectum:colon-treatment-pdq:p21:sotorasib:240mg",  # dose comparison arm
    # oral cavity
    "oral_cavity:ncg-guidelines-for-head-neck:p8:fluorouracil:10000mg/m2*", "oral_cavity:ncg-guidelines-for-head-neck:p9:fluorouracil:10000mg/m2*",  # "5FU 10000 mg/m2" (CF, EXTREME):
    # likely a misprint for 1000 mg/m2 a day (D1-D4); kept, it would flag a correct 1000 mg/m2 as a tenfold slip. For clinical review (pendings).
}


# Source kind (step 2): every kept line is either a regimen / schedule line ("regimen") or a line describing what a trial gave its
# patients ("trial_summary": trial arms, "patients received", "(n = ...)", "randomly assigned"). The code reads the trial wording in the
# quote and the sentence before it (TRIAL_RX); SOURCE_KIND records the corrections made by reading every row. The checker treats a dose
# that matches only a trial summary as info, never as a pass.
TRIAL_RX = re.compile(r"\btrials?\b|\bRCT\b|\bstud(?:y|ies)\b|\brandomi[sz]ed\b|\brandomly\b|\barms?\b|\(\s*n\s*=|\bNCT\d|"
                      r"\bphase\s+(?:I{1,3}|[123])\b|\bversus\b|\bvs\b|\bcompared\b|\bpatients\s+(?:were\s+)?(?:received|treated)\b|"
                      r"\bwas given at\b|\bcontrol group\b|\bevaluated\b|\binvestigated\b|\bfollow-up\b|\benrolled\b|\baccrued\b|\bplacebo\b|"
                      r"\bparticipants\b|\bcohort\b|\bto either\b|\bwere treated with\b|\bin abstract form\b|\breceived\b", re.I)
SOURCE_KIND = {
    # regimen / schedule lines that sit next to trial wording
    "breast:breast-cancer:p30:rt:50Gy/25": "regimen", "breast:breast-cancer:p35:rt:12Gy/2": "regimen",  # ICMR recommendations
    "breast:tata-memorial-centre-evidenc:p13:rt:40-42.5Gy/15-16": "regimen",  # the standard moderate hypofractionation schedule
    "lung_nsclc:non-small-cell-lung-treatmen:p14:rt:*": "regimen",  # "Commonly used regimens include 18 Gy x 3 ..."
    "colorectal_rectum:tata-memorial-centre-evidenc:p5:*": "regimen",  # FOLFOX-4 and modified FOLFOX-6 regimen lines
    # trial descriptions with no trial word in the quote or the sentence before it
    "breast:tata-memorial-centre-evidenc:p13:rt:26Gy/5": "trial_summary", "breast:tata-memorial-centre-evidenc:p13:rt:28.5Gy/5": "trial_summary",  # FAST-Forward, FAST
    "breast:breast-treatment-pdq:p18:rt:*": "trial_summary",  # APBI trial arms
    "breast:breast-treatment-pdq:p70:tamoxifen:*": "trial_summary",  # NSABP B-24
    "lung_nsclc:non-small-cell-lung-treatmen:p55:bevacizumab:*": "trial_summary", "lung_nsclc:non-small-cell-lung-treatmen:p55:paclitaxel:*": "trial_summary",  # IMpower150
    "colorectal_rectum:tata-memorial-centre-evidenc:p26:*": "trial_summary",  # table of immunotherapy trials (KEYNOTE-177, CheckMate-142)
    "colorectal_rectum:rectal-treatment-pdq:p14:*": "trial_summary", "colorectal_rectum:rectal-treatment-pdq:p15:*": "trial_summary",  # CAO/ARO/AIO-94, Polish, NSABP R-03
    "colorectal_rectum:rectal-treatment-pdq:p18:*": "trial_summary",  # ACCORD 12/0405
}


def source_kind(c):
    """("regimen" | "trial_summary", the trial words read) for a candidate: SOURCE_KIND (by reading) first, else TRIAL_RX on the
    quote and the sentence before it."""
    words = sorted({m.group(0).lower() for m in TRIAL_RX.finditer(c.get("context") or c["quote"])})
    for k, v in SOURCE_KIND.items():
        if c["id"] == k or (k.endswith("*") and c["id"].startswith(k[:-1])):
            return v, words
    return ("trial_summary" if words else "regimen"), words


def dropped(c):
    if any(re.search(rx, c["quote"], re.I) for rx in DROP_QUOTE):
        return True
    return any(c["id"] == d or (d.endswith("*") and c["id"].startswith(d[:-1])) for d in DROP)

# ---------------------------------------------------------------- parsing (the checker's own parsers: one notion of a dose and a unit)

def _names():
    names = {d: d for d in DRUGS}
    names.update(ALIASES)
    return names


NAMES = _names()
NAME_RX = re.compile(r"(?<![A-Za-z0-9-])(" + "|".join(re.escape(n) for n in sorted(NAMES, key=len, reverse=True)) + r")(?![A-Za-z])", re.I)


def _line_bounds(text, start, end):
    """The source line(s) holding [start, end): from the line start before `start` to the line end after `end`; in prose (one long
    line) the sentence around the dose, cut at word boundaries."""
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", end)
    b = len(text) if b < 0 else b
    if b - a > 320:
        k = text.rfind(". ", a, start)
        sa = max(k + 2 if k >= 0 else a, start - 160)
        while sa > a and not text[sa - 1].isspace() and sa < start:
            sa += 1
        sb = text.find(". ", end)
        sb = b if sb < 0 or sb > b else sb + 1
        sb = min(sb, end + 160)
        while sb < b and not text[sb].isspace() and sb > end and text[sb - 1] not in ".;)":
            sb -= 1
        a, b = sa, sb
    if a == 0 and text[:1].islower():  # a text window (NCI PDQ .txt pages) can start inside a word: start at the next word
        a = min(text.find(" ") + 1 if text.find(" ") >= 0 else 0, start)
    return a, b


def _context(text, a, b):
    """The quote [a, b) with the sentence before it (at most 400 characters back): where a trial line names its trial."""
    k = text.rfind(". ", max(0, a - 400), a)
    k2 = text.rfind(". ", max(0, a - 400), k) if k > 0 else -1
    start = k2 + 2 if k2 >= 0 else (max(0, a - 400) if k >= 0 else a)
    return ws(text[start:b])


def ws(s):
    """Whitespace collapsed; a leading list bullet (PDF private-use bullet, '•', '-') is left out (the rest stays verbatim)."""
    return re.sub(r"\s+", " ", s).strip().lstrip("\uf0b7\uf0a7\uf0d8•●▪◦- ").strip()


def scan_drugs(text):
    """Drug-dose candidates of one chunk text: each dose belongs to the drug name before it (first dose within 30 characters, no
    sentence break; later doses before the next drug name joined by or / then / followed by / and / commas)."""
    out = []
    ms = list(NAME_RX.finditer(text))
    for k, m in enumerate(ms):
        seg_end = min(ms[k + 1].start() if k + 1 < len(ms) else len(text), m.end() + 200)
        seg = text[m.end():seg_end]
        pos, first = 0, True
        for d in dosecheck.parse_doses(seg):
            gap = seg[pos:d["start"]]
            if first and (len(gap) > 30 or re.search(r"[.;]\s", gap)):
                break
            if not first and (len(gap) > 70 or not re.search(r"\b(or|followed|then|f by|fb|f/b|and)\b|,|\(", gap, re.I)):
                break
            s_abs, e_abs = m.end() + d["start"], m.end() + d["end"]
            a, b = _line_bounds(text, m.start(), e_abs)
            nxt = re.search(r"[;+(]|\band\b\s+[A-Z]|\bor\b|\n|" + dosecheck.NUM + r"\s*(?:mg|g/)", seg[d["end"]:])
            sched = ws(seg[d["end"]: d["end"] + (nxt.start() if nxt else 60)])[:80].strip(" ,.()")
            reg = re.match(r"[^A-Za-z0-9]*([A-Z][A-Z0-9]{1,6}(?: with \w+)?)\s*[–\-:]", text[a:m.start()])
            out.append({"drug": NAMES[m.group(1).lower()], "as_written": m.group(1), "dose": d["dose"], "dose_max": d["dose_max"],
                        "unit": d["unit"], "schedule": sched, "quote": ws(text[a:b]), "regimen": reg.group(1) if reg else None,
                        "context": _context(text, a, b)})
            first, pos = False, d["end"]
    return out


def scan_rt(text):
    out = []
    for r in dosecheck.parse_rt(text, require_fractions=True):
        a, b = _line_bounds(text, r["start"], r["end"])
        out.append({"total_gy": r["total_gy"], "total_gy_max": r["total_gy_max"], "fractions": r["fractions"], "fractions_max": r["fractions_max"],
                    **{k: r[k] for k in ("gy_per_fraction", "gy_per_fraction_max") if r.get(k) is not None},
                    "schedule": ws(r["written"]), "quote": ws(text[a:b]), "context": _context(text, a, b)})
    return out


def _fmt(x):
    return ("%g" % x) if x is not None else ""


def candidates(chunks):
    """Every candidate for every cancer, with a stable id."""
    by_file = {}
    for c in chunks:
        by_file.setdefault(c["file"], []).append(c)
    out, seen = [], Counter()
    for cancer, files in SOURCES.items():
        for f, scope in files:
            pages = PAGES.get((cancer, f))
            for c in by_file.get(f, []):
                if scope != "all" and not re.search(scope, c["text"], re.I):
                    continue
                if pages and c["page"] not in pages:
                    continue
                base = {"cancer": cancer, "file": f, "org": c["org"], "region": c["region"], "title": c["title"], "page": c["page"]}
                stem = re.sub(r"[^a-z0-9]+", "-", Path(f).stem.lower())[:28].strip("-")
                for d in scan_drugs(c["text"]):
                    key = f"{cancer}:{stem}:p{c['page']}:{d['drug'].replace(' ', '-')}:{_fmt(d['dose'])}{('-' + _fmt(d['dose_max'])) if d['dose_max'] else ''}{d['unit']}"
                    seen[key] += 1
                    out.append({"id": key + (f"#{seen[key]}" if seen[key] > 1 else ""), "kind": "drug", **base, **d})
                    out[-1]["source_kind"], out[-1]["trial_words"] = source_kind(out[-1])
                for r in scan_rt(c["text"]):
                    key = f"{cancer}:{stem}:p{c['page']}:rt:{_fmt(r['total_gy'])}{('-' + _fmt(r['total_gy_max'])) if r['total_gy_max'] else ''}Gy/{r['fractions']}{('-' + str(r['fractions_max'])) if r['fractions_max'] else ''}"
                    seen[key] += 1
                    out.append({"id": key + (f"#{seen[key]}" if seen[key] > 1 else ""), "kind": "rt", **base, **r})
                    out[-1]["source_kind"], out[-1]["trial_words"] = source_kind(out[-1])
    return out


def unknown_words(chunks):
    """Words just before a dose that are not drug names (to extend the lexicon)."""
    cnt = Counter()
    files = {f for fs in SOURCES.values() for f, _ in fs}
    for c in chunks:
        if c["file"] not in files:
            continue
        for m in dosecheck.DOSE_RX.finditer(c["text"]):
            w = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", c["text"][max(0, m.start() - 30):m.start()])
            if w and w[-1].lower() not in NAMES:
                cnt[w[-1].lower()] += 1
    return cnt


def _n(x):
    return int(x) if isinstance(x, float) and x.is_integer() else x


def entry(c):
    c = {k: _n(v) for k, v in c.items()}
    e = {k: c[k] for k in ("id", "cancer", "kind") if c.get(k) is not None}
    if c["kind"] == "drug":
        e.update({"drug": c["drug"], "as_written": c["as_written"], "dose": c["dose"]})
        if c.get("dose_max"):
            e["dose_max"] = c["dose_max"]
        e["unit"] = c["unit"]
        for k in ("schedule", "regimen"):
            if c.get(k):
                e[k] = c[k]
    else:
        for k in ("total_gy", "total_gy_max", "fractions", "fractions_max", "gy_per_fraction", "gy_per_fraction_max", "schedule"):
            if c.get(k) is not None:
                e[k] = c[k]
    e["source_kind"] = c.get("source_kind") or "regimen"
    e.update({k: c[k] for k in ("file", "title", "org", "region", "page", "quote")})
    if "\u2014" in e["quote"]:  # no em dash in what the UI shows: the verbatim part after it, when that part still holds the dose
        tail = e["quote"].rsplit("\u2014", 1)[1].strip()
        if _fmt(e.get("dose") if e["kind"] == "drug" else e.get("total_gy")) in tail.replace(",", ""):
            e["quote"] = tail
    return e


def build(chunks):
    keep, seen = [], set()
    # one entry per dose (or schedule) per file: its first regimen line, else its first trial summary line
    for c in sorted((c for c in candidates(chunks) if not dropped(c)),
                    key=lambda c: (c["cancer"], c["file"], c["source_kind"] != "regimen", c["page"])):
        key = (c["cancer"], c["file"], c["kind"]) + ((c["drug"], c["dose"], c.get("dose_max"), c["unit"]) if c["kind"] == "drug"
                                                     else (c["total_gy"], c.get("total_gy_max"), c["fractions"], c.get("fractions_max")))
        if key not in seen:
            seen.add(key)
            keep.append(c)
    order = {f: i for fs in SOURCES.values() for i, (f, _) in enumerate(fs)}
    keep.sort(key=lambda c: (list(SOURCES).index(c["cancer"]), REGION_ORDER.get(c["region"], 9), order[c["file"]], c["page"]))
    aliases = {a: g for a, g in ALIASES.items() if a != g and any(a == e["as_written"].lower() for e in keep if e["kind"] == "drug")}
    aliases["5-fu"] = "fluorouracil"  # standard abbreviation
    return {"_note": ("Guideline dose and radiotherapy references for the guideline checks (V1 item 7.2). Built by "
                      "tumour_board/eval/build_dose_references.py from the guideline index text (every quote is a verbatim line of the file "
                      "and page cited, apart from whitespace), then curated by reading the candidates: cumulative dose limits, dose "
                      "reductions, renal adjustments, dose comparisons, some trial arm details and other cancers dropped. Regimen and "
                      "schedule lines are kept with source_kind \"regimen\"; lines describing what a trial gave its patients (trial arms, "
                      "\"patients received\", \"(n = ...)\", mostly NCI PDQ) are kept with source_kind \"trial_summary\": the check counts "
                      "a dose that matches only a trial summary as info, not a pass. Indian sources first (NCG, ICMR, TMC), then "
                      "international (ESMO), UK (NICE) and US (NCI PDQ). Coverage is limited to the doses our guideline files state. For "
                      "review by the clinical team before real use. Rebuild: python -m tumour_board.eval.build_dose_references "
                      "--candidates /tmp/c.json, read the candidates, update PAGES / DROP / SOURCE_KIND in the script, then --write."),
            "aliases": dict(sorted(aliases.items())),
            "references": [entry(c) for c in keep]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", default=str(config.DATA_ROOT / "embed_cache" / "guidelines_index.json"))
    ap.add_argument("--candidates", help="write every candidate (before DROP) to this JSON file")
    ap.add_argument("--write", action="store_true", help="write tumour_board/protocols/dose_references.json")
    ap.add_argument("--unknown", action="store_true", help="print words before doses that are not in the drug lexicon")
    a = ap.parse_args(argv)
    chunks = json.loads(Path(a.index).read_text())["chunks"]
    cands = candidates(chunks)
    print(f"{len(cands)} candidates; " + ", ".join(f"{k}: {v}" for k, v in sorted(Counter((c['cancer'], c['kind']) for c in cands).items())))
    if a.candidates:
        Path(a.candidates).write_text(json.dumps(cands, indent=1, ensure_ascii=False))
    if a.unknown:
        print(unknown_words(chunks).most_common(80))
    if a.write:
        t = build(chunks)
        OUT.write_text(json.dumps(t, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {OUT}: {len(t['references'])} references")
    ids = {c["id"] for c in cands}
    for name, keys in (("DROP", DROP), ("SOURCE_KIND", SOURCE_KIND)):
        stale = {d for d in keys if not (d in ids or (d.endswith("*") and any(i.startswith(d[:-1]) for i in ids)))}
        if stale:
            print(f"{name} ids no longer produced:", sorted(stale))
    return 0


if __name__ == "__main__":
    sys.exit(main())
