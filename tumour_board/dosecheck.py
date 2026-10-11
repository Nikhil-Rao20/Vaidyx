"""Guideline checks on the board's decision (V1 item 7.2): drug doses, radiotherapy schedules and the stage as written.

The agent checks the RECORD against reference text, it never decides. One reasoner call lists what the decision states (drugs with
doses, radiotherapy schedules, the stage as written), each with an exact span; code keeps only spans found in the decision text
(grounding.locate) and reads every number and unit from the decision text itself, never from the model. A deterministic code scan
of the decision text for every drug name in the reference table (generic names, the aliases the guideline text itself uses, the
hospital's brand names from DATA_ROOT/formulary.json when provided) runs as well, so a model miss never hides a slip.

Compared with:
  - protocols/dose_references.json: guideline dose and radiotherapy lines for the cancer, Indian first (NCG, ICMR, TMC), then
    international (ESMO), UK (NICE), US (NCI PDQ); built from the guideline text by eval/build_dose_references.py. Each line is a
    regimen / schedule line (source_kind "regimen") or a trial summary (source_kind "trial_summary": what a trial gave its patients).
    Coverage is limited to the doses our guideline files state: a drug with no reference is info only, not a pass.
  - the stage as recorded in the signed reports (passed in by the caller): like with like only (stage group with stage group, TNM
    categories with TNM categories), and only for the same stage: a known c / p / yp difference (from the TNM prefix or the words
    clinical / pathological / post-NACT) is not compared. No stage is ever computed from TNM.

Results per drug or schedule, in this order: consistent (equal to a regimen line); possible_transcription_error (dose x10 or /10, or
the same number in another unit, vs any reference: expert review); trial_dose_only (equal only to a dose in a trial summary: info, not
a pass); differs_from_reference (review; deviating from a guideline can be intentional; every dose shown carries its own citation);
no_reference (info). drug_not_identified (info): a dose in a model span with no drug name the code can read before it (never shown
under a name the text does not hold). computed_dose_not_compared: the actual dose in brackets after a per-area / per-weight dose
('175 mg/m2 (300 mg)'). Stage: stage_consistent / stage_differs (review) / stage_not_compared. Units are normalised for
comparison only (mg/m², mg /m2, mg/sqm, mg per m2 -> mg/m2; g/m2 = 1000 mg/m2; "@AUC5" = AUC 5); the dose shown is always the dose
as written. Lab units live in units.py (item 3.5); dose units are here because units.json has no dose families.
"""
import json
import math
import re
from functools import lru_cache

from . import config, grounding, llm

REF_FILE = config.PROTOCOL_DIR / "dose_references.json"
REGION_ORDER = {"India": 0, "International": 1, "UK": 2, "US": 3}

# ---------------------------------------------------------------- dose parsing

NUM = r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\d])"
_RANGE = rf"(?P<a>{NUM})(?:\s*(?:-|–|—|to)\s*(?P<b>{NUM}))?"
UNIT = (r"(?P<unit>"
        r"mg\s*(?:/|per)\s*(?:kg|kilogram)(?![a-z])"
        r"|m?g\s*(?:/|per|·)?\s*(?:m\s*(?:2|²|\^\s*2|q)(?!\d)|m\s*-\s*2|sq\.?\s*m(?![a-z])|square\s*met(?:re|er)|m(?![a-z0-9²]))"
        r"(?:\s*/\s*(?:day|d)(?![a-z])|\s*(?:day|d)\s*-\s*1)?"
        r"|mg\s*/\s*(?:day|d)(?![a-z])"
        r"|mg(?![a-z])(?!\s*/))")
DOSE_RX = re.compile(_RANGE + r"\s*" + UNIT, re.I)
AUC_RX = re.compile(r"@?\s*AUC\)?\s*(?:[=:@]|-|–|of)?\s*(?P<a>\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(?P<b>\d+(?:\.\d+)?))?", re.I)


def _num(s):
    return float(s.replace(",", "")) if s else None


def norm_unit(u):
    """Normalised dose unit: 'mg/m2', 'mg/m2/day', 'g/m2', 'mg/kg', 'mg', 'mg/day' (or 'AUC')."""
    u = re.sub(r"\s+", "", u.lower())
    if re.match(r"mg(/|per)(kg|kilogram)", u):
        return "mg/kg"
    if re.fullmatch(r"mg/(day|d)", u):
        return "mg/day"
    if u == "mg":
        return "mg"
    per_day = bool(re.search(r"(/(day|d)|(day|d)-1)$", u))
    return ("g/m2" if u.startswith("g") else "mg/m2") + ("/day" if per_day else "")


def canon(value, unit):
    """(value, unit) in the comparison unit: g/m2 -> mg/m2 x1000; '/day' is schedule (mg/m2/day = mg/m2, mg/day = mg)."""
    if value is None:
        return None, unit
    if unit.startswith("g/m2"):
        return value * 1000, "mg/m2"
    return value, {"mg/m2/day": "mg/m2", "mg/day": "mg"}.get(unit, unit)


def parse_doses(text):
    """Every dose in `text`: [{"dose", "dose_max", "unit" (normalised), "written" (as in the text), "start", "end"}], in order.
    '6 mg/m2', '60mg/m²', '1000-1250 mg/m2', '1,200 mg', '1.2 g/m2', '@AUC5', 'AUC 5-6'."""
    text = text or ""
    out = []
    for m in DOSE_RX.finditer(text):
        out.append({"dose": _num(m.group("a")), "dose_max": _num(m.group("b")), "unit": norm_unit(m.group("unit")),
                    "written": m.group(0).strip(), "start": m.start(), "end": m.end()})
    for m in AUC_RX.finditer(text):
        if any(d["start"] < m.end() and m.start() < d["end"] for d in out):
            continue
        s = m.start() + (len(m.group(0)) - len(m.group(0).lstrip("@ ")))
        out.append({"dose": _num(m.group("a")), "dose_max": _num(m.group("b")), "unit": "AUC", "written": text[s:m.end()].strip(),
                    "start": s, "end": m.end()})
    return sorted(out, key=lambda d: d["start"])


# ---------------------------------------------------------------- radiotherapy parsing

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "twelve": 12, "fifteen": 15, "sixteen": 16, "twenty": 20, "twenty-five": 25, "twenty five": 25, "twenty-eight": 28,
          "twenty eight": 28, "thirty": 30}
_W = "|".join(sorted((re.escape(w) for w in _WORDS), key=len, reverse=True))
_GY = r"(?:cGy|Gy|Gray|G\s?y)"
_FNUM = rf"(?P<f>\d+|{_W})(?:\s*(?:-|–|to)\s*(?P<g>\d+|{_W}))?"
_TOT = r"(?P<a>\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(?P<b>\d+(?:\.\d+)?))?"
RT_RX = [
    ("full", re.compile(rf"{_TOT}\s*(?P<u>{_GY})\s*(?:in|/|,|over)?\s*{_FNUM}\s*(?:once[- ]daily\s*|daily\s*)?(?:fractions?(?![a-z])|fr(?![a-z])|#)", re.I)),
    ("nxp", re.compile(rf"(?<![\d.])(?P<f>\d+)\s*[x×*]\s*(?P<p>\d+(?:\.\d+)?)\s*(?P<u>{_GY})(?![a-z])", re.I)),
    # '7 Gy x 3', '7 Gy * 2-3 Fr' (a range of fractions: NCG cervix brachytherapy, V1 item 9.2); never 'x 5 a week' (a schedule)
    ("pxn", re.compile(rf"(?<![\d.])(?P<p>\d+(?:\.\d+)?)(?:\s*(?:Gy)?\s*(?:-|–|to)\s*(?P<q>\d+(?:\.\d+)?))?\s*(?P<u>{_GY})\s*[x×*]\s*(?P<f>\d+)(?!\d)"
                       r"(?:\s*(?:-|–)\s*(?P<g>\d+)(?!\d)(?=\s*(?:fractions?(?![a-z])|fr(?![a-z])|#)))?(?!\s*(?:-|–)\s*\d)(?!\s*(?:days?|d|times|fractions?|fr|#)?\s*(?:a|per|/|each|every|in\s+a)\s*(?:week|wk))(?:\s*(?:fractions?|fr(?![a-z])|#))?", re.I)),
    ("single", re.compile(rf"{_TOT}\s*(?P<u>{_GY})\s*(?:in\s+a\s+|as\s+a\s+)?single\s+(?:fraction|#)", re.I)),
]
_TOTAL_ONLY = re.compile(rf"(?<![\d.]){_TOT}\s*(?P<u>{_GY})(?![a-z])", re.I)
_PER_FRACTION_AFTER = re.compile(r"\s*(?:per|/|each|a|every)\s*(?:fraction|fr\b|#|day|session)|\s*(?:daily|x|×)", re.I)
_PER_FRACTION_BEFORE = re.compile(r"(?:\bof|\bat|@|\bwith|[x×])\s*$", re.I)


def _fr(s):
    if s is None:
        return None
    return _WORDS[s.lower()] if s.lower() in _WORDS else int(s)


def parse_rt(text, require_fractions=False):
    """Every radiotherapy schedule in `text`: [{"total_gy", "total_gy_max", "fractions", "fractions_max", "written", "start", "end"}].
    '50 Gy/25#', '25 Gy in 5 fractions', '45-50.4 Gy in 25-28 fractions', '5 x 5 Gy', '8 Gy single fraction', '25 Gy in five
    fractions'. A total with no fractions ('boost 10 Gy') has fractions None (left out when require_fractions); a dose per fraction
    ('1.8 Gy per fraction', 'fractions of 2 Gy') is not a total."""
    text = text or ""
    out = []

    def taken(s, e):
        return any(o["start"] < e and s < o["end"] for o in out)

    for kind, rx in RT_RX:
        for m in rx.finditer(text):
            if taken(m.start(), m.end()):
                continue
            k = 0.01 if m.group("u").lower() == "cgy" else 1.0
            if kind in ("nxp", "pxn"):
                f, p = int(m.group("f")), float(m.group("p")) * k
                q = float(m.group("q")) * k if kind == "pxn" and m.group("q") else None
                g = int(m.group("g")) if kind == "pxn" and m.group("g") else None  # fractions range '2-3'
                if g is not None and not f < g <= min(2 * f, 40):  # '1-30 fractions' is not a schedule written per fraction: not read
                    continue
                tot, tmax, fr, fmax = round(f * p, 3), (round((g or f) * (q or p), 3) if (q or g) else None), f, g
            elif kind == "single":
                tot, tmax, fr, fmax = _num(m.group("a")) * k, (_num(m.group("b")) * k if m.group("b") else None), 1, None
            else:
                tot, tmax = _num(m.group("a")) * k, (_num(m.group("b")) * k if m.group("b") else None)
                fr, fmax = _fr(m.group("f")), _fr(m.group("g"))
            e = {"total_gy": tot, "total_gy_max": tmax, "fractions": fr, "fractions_max": fmax, "written": m.group(0).strip(),
                 "start": m.start(), "end": m.end()}
            if kind == "pxn" and fmax:  # '7 Gy * 2-3 Fr': the dose per fraction is fixed while the count varies (compare_rt checks it)
                e["gy_per_fraction"] = p
                if q:
                    e["gy_per_fraction_max"] = q
            out.append(e)
    if not require_fractions:
        for m in _TOTAL_ONLY.finditer(text):
            if taken(m.start(), m.end()) or _PER_FRACTION_AFTER.match(text, m.end()) or _PER_FRACTION_BEFORE.search(text[max(0, m.start() - 12):m.start()]):
                continue
            k = 0.01 if m.group("u").lower() == "cgy" else 1.0
            out.append({"total_gy": _num(m.group("a")) * k, "total_gy_max": _num(m.group("b")) * k if m.group("b") else None,
                        "fractions": None, "fractions_max": None, "written": m.group(0).strip(), "start": m.start(), "end": m.end()})
    return sorted(out, key=lambda r: r["start"])


# ---------------------------------------------------------------- stage parsing

_ARABIC = {"0": "0", "1": "I", "2": "II", "3": "III", "4": "IV"}
# 'Stage IIIA', and the FIGO forms of cervix (V1 item 9.2, review): 'FIGO IIB', 'FIGO 2018: IIB', 'FIGO (2018) stage IIIC1r'; the FIGO 2018
# r / p suffix (how nodes were assessed: radiology, pathology) is kept in what is written but never compared
_GROUP_RX = re.compile(r"\b(?:FIGO(?:\s*\(?20\d\d\)?)?\s*(?:stage\s*)?|stage\s*(?:group(?:ing)?\s*)?)[:\-]?\s*(?P<r>IV|I{1,3}|0|[1-4])(?P<l>[ABC]\d?)?"
                       r"(?:[rp](?![A-Za-z0-9]))?(?![A-Za-z0-9])", re.I)
_BARE_GROUP_RX = re.compile(r"^\s*(?P<r>IV|I{1,3})(?P<l>[ABC]\d?)?(?:[rp](?![A-Za-z0-9]))?(?![A-Za-z0-9])", re.I)
_TNM_RX = re.compile(r"(?<![A-Za-z0-9])(?P<pre>yp|yc|p|c|r|a)?\s?T(?P<t>is|[0-4X][a-d]?(?:mi)?)(?![a-z0-9])"
                     r"(?:\s*,?\s*(?:yp|yc|p|c)?\s?N(?P<n>[0-3X][a-c]?(?:mi)?)(?![a-z0-9]))?"
                     r"(?:\s*,?\s*(?:yp|yc|p|c)?\s?M(?P<m>[01X][a-d]?)(?![a-z0-9]))?")
_NM_RX = re.compile(r"(?<![A-Za-z0-9])(?P<pre>yp|yc|p|c)?\s?N(?P<n>[0-3X][a-c]?)(?![a-z0-9])\s*,?\s*(?:yp|yc|p|c)?\s?M(?P<m>[01X][a-d]?)(?![a-z0-9])")
# 'Stage 1: surgery' / 'stage 2 of the plan' is a step of the plan, not a stage group: an arabic group needs a letter ('Stage 3A'),
# the word 'group' ('stage group 2') or staging words just before it ('clinical stage 2', 'AJCC stage 3').
_STAGE_CONTEXT = re.compile(r"\b(?:clinical(?:ly)?|patholog\w*|AJCC|UICC|TNM|staged?\s+as|[cp]-?stage)\b[^.;:\n]{0,20}$", re.I)
# Words that say which stage a group is: clinical (c), pathological (p), after neoadjuvant therapy (yp)
_PREFIX_WORDS = (("yp", re.compile(r"\bpost[- ]?(?:nact|neo[- ]?adjuvant)|\bafter\s+(?:nact|neo[- ]?adjuvant)|\byp-?stage\b", re.I)),
                 ("p", re.compile(r"\bpatholog\w*|\bp-?stage\b", re.I)),
                 ("c", re.compile(r"\bclinical(?:ly)?\b|\bc-?stage\b", re.I)))


def _groups(text, bare=False, before=""):
    """Stage group matches in text (see _STAGE_CONTEXT; `before`: the text just before `text`, for the staging words); bare=True
    (a value known to be a stage) also takes 'Stage 2'."""
    for g in _GROUP_RX.finditer(text or ""):
        r = g.group("r")
        if (r.isdigit() and r != "0" and not g.group("l") and not bare and "group" not in g.group(0).lower()
                and not _STAGE_CONTEXT.search((before + text[:g.start()])[-40:])):
            continue
        yield g


def _word_prefix(text):
    """'yp' / 'p' / 'c' from the words in text ('post-NACT', 'pathological', 'clinical'), '' when none or when they disagree."""
    found = {p for p, rx in _PREFIX_WORDS if rx.search(text or "")}
    if "yp" in found and "c" not in found:
        return "yp"
    return found.pop() if len(found) == 1 else ""


def _text_prefix(text):
    """The one c / p / yp prefix a text states (its TNM prefixes and staging words), '' when none or more than one."""
    found = {(m.group("pre") or "").lower() for m in _TNM_RX.finditer(text or "") if m.group("pre") and (m.group("n") or m.group("m"))}
    w = _word_prefix(text)
    if w:
        found.add(w)
    return found.pop() if len(found) == 1 else ""


def _context_prefix(text, s, e):
    """The c / p / yp prefix stated by the staging word nearest to text[s:e] in the same sentence ('Stage IIIA (clinical)',
    'post-NACT stage IA'), '' when none."""
    a = max(max(text.rfind(ch, 0, s) for ch in ".;\n") + 1, s - 40)
    ends = [k for k in (text.find(ch, e) for ch in ".;\n") if k >= 0]
    b = min(min(ends) if ends else len(text), e + 20)
    best = None
    for p, rx in _PREFIX_WORDS:
        for m in rx.finditer(text, a, b):
            d = s - m.end() if m.end() <= s else (m.start() - e if m.start() >= e else 0)
            if best is None or d < best[0]:
                best = (d, p)
    return best[1] if best else ""


def _cat(letter, v):
    """'T' + '2a' -> 'T2a', 'is' -> 'Tis', 'x' -> 'TX'."""
    if not v:
        return None
    return letter + (v if v.lower() in ("is",) else v[0].upper() + v[1:].lower())


def parse_stage(text, bare=False, before=""):
    """Stage as written: {"group": "IIIB" | None, "roman", "letter", "prefix": "c" | "p" | "yp" | "" (as written on the TNM),
    "group_prefix" (the prefix the stage is read with: the TNM prefix, else the staging words in text), "t", "n", "m", "written",
    "start", "end"} or None. Stage group needs the word 'stage' and a roman group, a letter or staging words ('Stage 1: surgery' is a
    plan step; bare=True also takes a value that is only a group, 'IIA', or 'Stage 2'); TNM needs a prefix or at least two categories
    ('cT2', 'T2 N1', 'N0 M0'), so 'T2-weighted' is not a stage. `before`: the text just before `text` (staging words for an arabic
    group). Never derives a group from TNM."""
    text = text or ""
    res = {"group": None, "roman": None, "letter": "", "prefix": "", "group_prefix": "", "t": None, "n": None, "m": None, "written": None,
           "start": None, "end": None}
    spans = []
    g = next(_groups(text, bare, before), None) or (_BARE_GROUP_RX.search(text) if bare else None)
    if g:
        r = g.group("r").upper()
        res["roman"] = _ARABIC.get(r, r)
        res["letter"] = (g.group("l") or "").upper()
        res["group"] = res["roman"] + res["letter"]
        spans.append((g.start(), g.end()))
    for m in _TNM_RX.finditer(text):
        if not (m.group("pre") or m.group("n") or m.group("m")):
            continue
        res.update({"prefix": (m.group("pre") or "").lower(), "t": _cat("T", m.group("t")), "n": _cat("N", m.group("n")), "m": _cat("M", m.group("m"))})
        spans.append((m.start(), m.end()))
        break
    else:
        m = _NM_RX.search(text)
        if m:
            res.update({"prefix": (m.group("pre") or "").lower(), "n": _cat("N", m.group("n")), "m": _cat("M", m.group("m"))})
            spans.append((m.start(), m.end()))
    if not spans:
        return None
    res["start"], res["end"] = min(s for s, _ in spans), max(e for _, e in spans)
    res["written"] = text[res["start"]:res["end"]].strip()
    res["group_prefix"] = res["prefix"] or _word_prefix(text)
    return res


def _cat_equal(a, b):
    """'T2' vs 'T2a' compare at the precision both state; X is never compared."""
    if not a or not b or a[1:].upper().startswith("X") or b[1:].upper().startswith("X"):
        return None
    a, b = a.upper(), b.upper()
    if a[:2] != b[:2]:
        return False
    return a.startswith(b) or b.startswith(a)


def compare_stage(written, recorded):
    """(result, compared parts): like with like only; a c / p / yp prefix difference is not compared, for the stage group as for
    the TNM categories ('cT3N1M0, Stage IIIA' vs 'ypT1N0M0 Stage IA': two different stages, both correct)."""
    if not written or not recorded:
        return "stage_not_compared", []
    parts, differs = [], False
    wp, rp = written.get("group_prefix") or written["prefix"], recorded.get("group_prefix") or recorded["prefix"]
    if wp and rp and wp != rp:
        return "stage_not_compared", []
    if written["group"] and recorded["group"]:
        same = written["roman"] == recorded["roman"] and (not written["letter"] or not recorded["letter"]
                                                            or written["letter"].startswith(recorded["letter"]) or recorded["letter"].startswith(written["letter"]))
        parts.append("group")
        differs |= not same
    for c in ("t", "n", "m"):  # prefixes equal or one unknown (a known difference is returned above)
        eq = _cat_equal(written[c], recorded[c])
        if eq is None:
            continue
        parts.append(c)
        differs |= not eq
    if not parts:
        return "stage_not_compared", []
    return ("stage_differs" if differs else "stage_consistent"), parts


# ---------------------------------------------------------------- reference table and names

@lru_cache(maxsize=1)
def table():
    return json.loads(REF_FILE.read_text())


def references(cancer, kind=None):
    """Reference entries for a protocol cancer ('breast', 'lung_nsclc', 'colorectal_rectum'), Indian first; kind 'drug' / 'rt'."""
    rows = [r for r in table()["references"] if r["cancer"] == cancer and (kind is None or r["kind"] == kind)]
    return sorted(rows, key=lambda r: REGION_ORDER.get(r["region"], 9))


def formulary():
    """Hospital brand names {brand lower: generic lower} from DATA_ROOT/formulary.json ({"brand": "generic"}); absent = none."""
    f = config.DATA_ROOT / "formulary.json"
    if not f.exists():
        return {}
    try:
        raw = json.loads(f.read_text())
    except Exception:
        return {}
    aliases = table().get("aliases", {})
    out = {}
    for b, g in (raw.items() if isinstance(raw, dict) else []):
        if isinstance(b, str) and isinstance(g, str) and b.strip() and g.strip():
            g = g.strip().lower()
            out[b.strip().lower()] = aliases.get(g, g)
    return out


def drug_names(cancer=None):
    """{name as matched (lower case): generic}: generic names in the table (for this cancer; None = every cancer), the names as the
    guideline lines write them, the table's aliases for those generics, and the hospital's brand names (formulary.json)."""
    rows = [r for r in table()["references"] if r["kind"] == "drug" and (cancer is None or r["cancer"] == cancer)]
    generics = {r["drug"] for r in rows}
    out = {g: g for g in generics}
    for r in rows:
        out.setdefault(r["as_written"].lower(), r["drug"])
    for a, g in table().get("aliases", {}).items():
        if g in generics:
            out.setdefault(a.lower(), g)
    for b, g in formulary().items():
        out.setdefault(b, g)
    return out


def _name_rx(names):
    if not names:
        return None
    return re.compile(r"(?<![A-Za-z0-9-])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![A-Za-z])", re.I)


# ---------------------------------------------------------------- comparison

def _within(v, lo, hi):
    hi = lo if hi is None else hi
    return lo - 1e-6 * max(1.0, lo) <= v <= hi + 1e-6 * max(1.0, hi)


def _ref_bounds(r):
    lo, cu = canon(r["dose"], r["unit"])
    hi = canon(r.get("dose_max"), r["unit"])[0] if r.get("dose_max") else lo
    return lo, hi, cu


def _closeness(v, lo, hi):
    if v <= 0 or lo <= 0:
        return 99.0
    return 0.0 if lo <= v <= hi else min(abs(math.log(v / lo)), abs(math.log(v / hi)))


def _trial(r):
    """True for a reference line that describes a trial arm (source_kind "trial_summary"), not a regimen or schedule line."""
    return r.get("source_kind") == "trial_summary"


def _distinct(refs, key, n=3):
    """The first reference per distinct value of key(r), at most n (refs already in the order to show)."""
    out, seen = [], set()
    for r in refs:
        if key(r) not in seen:
            seen.add(key(r))
            out.append(r)
    return out[:n]


def compare_dose(drug, dose, unit, cancer, dose_max=None):
    """(result, references), in this order: (1) consistent: equal to a regimen line; (2) possible_transcription_error: x10 / /10 in
    the same unit, or the same number in another unit, against any reference (trial summaries included); (3) trial_dose_only: equal
    only to doses described in trial summaries (info, not a pass); (4) differs_from_reference: else, with the closest regimen doses
    (distinct doses, at most 3); no_reference when the drug has none. Indian sources first throughout."""
    refs = [r for r in references(cancer, "drug") if r["drug"] == drug]
    if not refs:
        return "no_reference", []
    v, cu = canon(dose, unit)
    vmax = canon(dose_max, unit)[0] if dose_max else v
    match = []
    for r in refs:
        lo, hi, rcu = _ref_bounds(r)
        if rcu == cu and _within(v, lo, hi) and _within(vmax, lo, hi):
            match.append(r)
    if any(not _trial(r) for r in match):
        return "consistent", [r for r in match if not _trial(r)]
    slip = []
    for r in refs:
        lo, hi, rcu = _ref_bounds(r)
        raw_lo, raw_hi = r["dose"], r.get("dose_max") or r["dose"]
        if rcu == cu and (_within(v * 10, lo, hi) or _within(v / 10, lo, hi)):
            slip.append(r)  # x10 / /10 in the same unit
        elif rcu != cu and (_within(dose, raw_lo, raw_hi) or _within(dose * 10, raw_lo, raw_hi) or _within(dose / 10, raw_lo, raw_hi)):
            slip.append(r)  # the same number (or x10 / /10) in another unit: '6 mg/m2' for 6 mg/kg, '6 mg' for 60 mg/m2
    if slip:
        return "possible_transcription_error", sorted(slip, key=lambda r: (REGION_ORDER.get(r["region"], 9), _trial(r)))
    if match:
        return "trial_dose_only", match
    regimen = [r for r in refs if not _trial(r)]
    pool = [r for r in regimen if _ref_bounds(r)[2] == cu] or regimen or [r for r in refs if _ref_bounds(r)[2] == cu] or refs
    pool = sorted(pool, key=lambda r: (REGION_ORDER.get(r["region"], 9), _closeness(v, *_ref_bounds(r)[:2])))
    return "differs_from_reference", _distinct(pool, lambda r: fmt_dose(r))


def compare_rt(rt, cancer):
    """(result, references) for one schedule, in the order of compare_dose: total Gy and fractions both compared (a total without
    fractions: the total only); x10 / /10 on the total Gy -> possible transcription error; a schedule equal only to trial summaries
    -> trial_dose_only (info)."""
    refs = references(cancer, "rt")
    if not refs:
        return "no_reference", []

    def fr_ok(r):
        if rt["fractions"] is None:
            return True
        return r.get("fractions") is not None and _within(rt["fractions"], r["fractions"], r.get("fractions_max")) and \
            _within(rt.get("fractions_max") or rt["fractions"], r["fractions"], r.get("fractions_max"))

    def pf_ok(r):  # a reference written per fraction with a range of fractions ('7 Gy * 2-3 Fr'): the dose per fraction must agree too
        if not r.get("gy_per_fraction") or not rt["fractions"]:
            return True
        per = rt["total_gy"] / rt["fractions"]
        per_max = (rt.get("total_gy_max") or rt["total_gy"]) / (rt.get("fractions_max") or rt["fractions"])
        return _within(per, r["gy_per_fraction"], r.get("gy_per_fraction_max")) and _within(per_max, r["gy_per_fraction"], r.get("gy_per_fraction_max"))

    t, tmax = rt["total_gy"], rt.get("total_gy_max") or rt["total_gy"]
    match = [r for r in refs if _within(t, r["total_gy"], r.get("total_gy_max")) and _within(tmax, r["total_gy"], r.get("total_gy_max")) and fr_ok(r)
             and pf_ok(r)]
    if any(not _trial(r) for r in match):
        return "consistent", [r for r in match if not _trial(r)]
    slip = [r for r in refs if fr_ok(r) and (_within(t * 10, r["total_gy"], r.get("total_gy_max")) or _within(t / 10, r["total_gy"], r.get("total_gy_max")))]
    if slip:
        return "possible_transcription_error", sorted(slip, key=lambda r: (REGION_ORDER.get(r["region"], 9), _trial(r)))
    if match:
        return "trial_dose_only", match
    regimen = [r for r in refs if not _trial(r)] or refs
    same = [r for r in regimen if fr_ok(r)] or regimen
    same = sorted(same, key=lambda r: (REGION_ORDER.get(r["region"], 9), _closeness(t, r["total_gy"], r.get("total_gy_max") or r["total_gy"])))
    return "differs_from_reference", _distinct(same, fmt_rt)


# ---------------------------------------------------------------- flag text

def _g(x):
    return ("%g" % x) if x is not None else ""


def fmt_dose(r):
    if r["unit"] == "AUC":
        return "AUC " + _g(r["dose"]) + (("-" + _g(r["dose_max"])) if r.get("dose_max") else "")
    return _g(r["dose"]) + (("-" + _g(r["dose_max"])) if r.get("dose_max") else "") + " " + r["unit"]


def fmt_rt(r):
    if r.get("gy_per_fraction") and r.get("fractions"):  # '7 Gy x 2-3 fractions (14-21 Gy)'
        n = str(r["fractions"]) + (("-" + str(r["fractions_max"])) if r.get("fractions_max") else "")
        return (_g(r["gy_per_fraction"]) + (("-" + _g(r["gy_per_fraction_max"])) if r.get("gy_per_fraction_max") else "") + f" Gy x {n} fractions ("
                + _g(r["total_gy"]) + (("-" + _g(r["total_gy_max"])) if r.get("total_gy_max") else "") + " Gy)")
    s = _g(r["total_gy"]) + (("-" + _g(r["total_gy_max"])) if r.get("total_gy_max") else "") + " Gy"
    if r.get("fractions") is not None:
        n = str(r["fractions"]) + (("-" + str(r["fractions_max"])) if r.get("fractions_max") else "")
        s += " in " + n + (" fraction" if n == "1" else " fractions")
    return s


def _cite(r, mark_trial=False):
    """'National Cancer Grid (NCG), India, p 11'; mark_trial: 'trial summary, NCI PDQ (US), p 34' for a trial summary line."""
    org = r["org"] if r["region"] in r["org"] else f"{r['org']}, {r['region']}"
    return ("trial summary, " if mark_trial and _trial(r) else "") + f"{org}, p {r['page']}"


def _ref_out(r):
    out = {k: r.get(k) for k in ("org", "region", "file", "title", "page", "quote")}
    out["source_kind"] = r.get("source_kind") or "regimen"
    if r["kind"] == "drug":
        out.update({"dose": r["dose"], "dose_max": r.get("dose_max"), "unit": r["unit"]})
    else:
        out.update({k: r.get(k) for k in ("total_gy", "total_gy_max", "fractions", "fractions_max")})
    return out


def _brief(r):
    return {"id": r["id"], **_ref_out(r), **({"regimen": r["regimen"]} if r.get("regimen") else {}),
            **({"schedule": r["schedule"]} if r.get("schedule") else {})}


def _states(shown, fmt):
    """'the guideline reference states 60 mg/m2 (NCG, India, p 11)' or, for several, 'the guideline references state 1000 mg/m2
    (NCG, India, p 22) or 650-825 mg/m2 (ICMR consensus, India, p 30)': every value carries its own citation."""
    parts = [f"{fmt(r)} ({_cite(r, mark_trial=True)})" for r in shown]
    return ("the guideline reference states " if len(parts) == 1 else "the guideline references state ") + " or ".join(parts)


def _guide_flag(check, c, sev, text, shown):
    return {"kind": "guideline", "check": check, "severity": sev, "text": text, "recorded": c["recorded"], "span": c["span"],
            "reference": _ref_out(shown[0]) if shown else None, "references": [_ref_out(r) for r in shown]}


def _dose_flag(c, refs):
    rec = c["recorded"]
    if c["result"] == "drug_not_identified":
        return _guide_flag("dose", c, "info", f"Drug not identified in the decision text: dose recorded as \"{rec}\"; no drug name the check "
                                              f"can read stands before it, so it was not compared with a guideline reference. Info only, not a pass.", [])
    name = c["drug"][:1].upper() + c["drug"][1:]
    if c["result"] == "no_reference":
        return _guide_flag("dose", c, "info", f"No guideline reference found: {name} recorded as \"{rec}\"; the dose references for this "
                                              f"cancer do not cover this drug. Info only, not a pass.", [])
    if c["result"] == "trial_dose_only":
        shown = _distinct(refs, fmt_dose, n=1)
        return _guide_flag("dose", c, "info", f"Trial dose only: {name} recorded as \"{rec}\" matches only a dose described in a trial summary "
                                              f"({_cite(shown[0])}), not a regimen line. Info only, not a pass.", shown)
    if c["result"] == "possible_transcription_error":
        shown = refs[:1]
        return _guide_flag("dose", c, "expert_review", f"Possible transcription error: {name} recorded as \"{rec}\"; {_states(shown, fmt_dose)}. "
                                                       f"Expert review: the check flags the difference, it does not decide which dose is correct.", shown)
    shown = _distinct(refs, fmt_dose)
    return _guide_flag("dose", c, "review", f"Differs from guideline reference: {name} recorded as \"{rec}\"; {_states(shown, fmt_dose)}. "
                                            f"Review: a deviation from a guideline can be intentional; the check does not decide which dose is correct.", shown)


def _rt_flag(c, refs):
    rec = c["recorded"]
    if c["result"] == "no_reference":
        return _guide_flag("rt", c, "info", f"No guideline reference found: radiotherapy recorded as \"{rec}\"; the radiotherapy references "
                                            f"for this cancer do not cover it. Info only, not a pass.", [])
    if c["result"] == "trial_dose_only":
        shown = refs[:1]
        return _guide_flag("rt", c, "info", f"Trial schedule only: radiotherapy recorded as \"{rec}\" matches only a schedule described in a "
                                            f"trial summary ({_cite(shown[0])}), not a regimen line. Info only, not a pass.", shown)
    if c["result"] == "possible_transcription_error":
        shown = refs[:1]
        return _guide_flag("rt", c, "expert_review", f"Possible transcription error: radiotherapy recorded as \"{rec}\"; {_states(shown, fmt_rt)}. "
                                                     f"Expert review: the check flags the difference, it does not decide which schedule is correct.", shown)
    shown = _distinct(refs, fmt_rt)
    return _guide_flag("rt", c, "review", f"Differs from guideline reference: radiotherapy recorded as \"{rec}\"; {_states(shown, fmt_rt)}. "
                                          f"Review: a deviation from a guideline can be intentional; the check does not decide which schedule is correct.", shown)


# ---------------------------------------------------------------- model listing + code scan

SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "drugs": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "drug": {"type": "string"}, "dose_as_written": {"type": "string"}, "frequency": {"type": "string"}, "cycles": {"type": "string"},
        "span": {"type": "string", "description": "exact text from the decision"}},
        "required": ["drug", "dose_as_written", "frequency", "cycles", "span"]}},
    "radiotherapy": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "as_written": {"type": "string"}, "span": {"type": "string", "description": "exact text from the decision"}},
        "required": ["as_written", "span"]}},
    "stage": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "as_written": {"type": "string"}, "span": {"type": "string", "description": "exact text from the decision"}},
        "required": ["as_written", "span"]}}},
    "required": ["drugs", "radiotherapy", "stage"]}

SYSTEM = ("You list what a Tumour Board decision record states: drugs with their doses, radiotherapy schedules and the stage as written. "
          "Copy each item exactly from the decision text. Do not judge, correct, convert or complete anything.")


def _messages(decision_text):
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"DECISION RECORD:\n{decision_text}\n\nList:\n"
             "- drugs: every drug written with a dose (drug name, dose as written, frequency, cycles as written; empty string if not written);\n"
             "- radiotherapy: every radiotherapy schedule written with a dose in Gy (total dose and fractions as written);\n"
             "- stage: every stage written in the record (stage group or TNM, as written).\n"
             "For every item give span: the exact text of the decision record that states it, copied character for character. "
             "If there are none, return empty lists."}]


# Words allowed between a drug name and its dose ("Inj. Doxorubicin hydrochloride at 60 mg/m2"), and between two doses of one drug
# ("8 mg/kg loading dose followed by 6 mg/kg", "f/b"). Any other word (another drug's name, even one not in the table) breaks the link.
_FILL_FIRST = {"inj", "injection", "tab", "tablet", "tabs", "cap", "capsule", "caps", "iv", "po", "sc", "im", "oral", "at", "dose", "of",
               "a", "the", "hydrochloride", "hcl", "sodium", "infusion", "bolus", "loading", "weekly", "day", "days", "d", "q", "dl",
               "biosimilar"}
_FILL_NEXT = _FILL_FIRST | {"followed", "by", "then", "or", "and", "from", "cycle", "cycles", "in", "every", "wk", "wks", "week", "weeks",
                            "onwards", "once", "twice", "daily", "od", "bd", "bid", "as", "with", "fb", "f", "maintenance", "x", "h",
                            "hours", "over", "min", "minutes", "subsequent", "doses", "thereafter", "each"}


def _only(gap, allowed):
    return all(w.lower() in allowed for w in re.findall(r"[A-Za-z]+", gap))


_FB = re.compile(r"\bf\s*/\s*by?\b", re.I)  # 'f/b': the common Indian shorthand for 'followed by'
_JOIN = re.compile(r"\b(or|then|followed|f by|fb|and)\b|,|\(", re.I)
_PER_SIZE = {"mg/m2", "mg/m2/day", "g/m2", "g/m2/day", "mg/kg", "AUC"}


def _owners(text, doses, ms, known=None):
    """For each dose in doses: the name match (from ms) it belongs to, or None. The first dose after a name: within 40 characters,
    only route / form words between, no sentence break ('Inj. Doxorubicin 60 mg/m2'); a later dose: the dose before it belongs to
    the same name and the gap joins them (or / then / followed by / f/b / a comma / a bracket) with only schedule words between
    ('8 mg/kg loading f/b 6 mg/kg'). known: owners already found (a dose with one keeps it and is not re-linked)."""
    own = []
    for i, d in enumerate(doses):
        if known and known[i] is not None:
            own.append(known[i])
            continue
        prev = [m for m in ms if m.end() <= d["start"]]
        m = prev[-1] if prev else None
        if m is not None:
            if i == 0 or doses[i - 1]["start"] < m.end():  # no dose between the name and this dose
                gap = text[m.end():d["start"]]
                if len(gap) > 40 or re.search(r"[.;]\s|\n", gap) or not _only(gap, _FILL_FIRST):
                    m = None
            else:
                gap = _FB.sub(" followed by ", text[doses[i - 1]["end"]:d["start"]])
                if own[i - 1] is not m or len(gap) > 60 or not _JOIN.search(gap) or not _only(gap, _FILL_NEXT):
                    m = None
        own.append(m)
    return own


def _computed(text, doses, own, i):
    """True for the actual dose computed from a per-area / per-weight dose, written in brackets right after it: 'Paclitaxel
    175 mg/m2 (300 mg)', 'Carboplatin AUC 5 (450 mg)'."""
    if i == 0 or own[i] is None or own[i - 1] is not own[i]:
        return False
    a, d = doses[i - 1], doses[i]
    return (a["unit"] in _PER_SIZE and d["unit"] == "mg"
            and re.fullmatch(r"\s*\(\s*(?:i\.?e\.?|=|~|approx\.?|approximately)?\s*", text[a["end"]:d["start"]], re.I) is not None
            and re.match(r"\s*(?:total|flat|approx\.?)?\s*\)", text[d["end"]:], re.I) is not None)


def _model_labels(model_drug, names):
    """(generic, the names that may stand for it in the text) for the model's drug label: the label itself (route words and
    brackets left out) plus every table name, alias and formulary brand of the same generic."""
    mk = re.sub(r"\([^)]*\)", " ", (model_drug or "").strip().lower())
    mk = re.sub(r"^(?:(?:inj|injection|tab|tablet|tabs|cap|capsule)\b\.?\s*)+", "", mk.strip())
    mk = re.sub(r"\s+", " ", mk).strip(" .,:;-")
    if not mk:
        return None, set()
    g = names.get(mk, mk)
    return g, {mk} | {n for n, x in names.items() if x == g}


def _drug_items(text, base, names, rx, model_drug=None):
    """Drug-dose items in text (offsets made absolute with `base`): each dose belongs to the last known drug name before it (see
    _owners). In a located model span (model_drug not None), a dose no known name holds belongs to the model's drug label only when
    that label (or a table alias / formulary brand of the same generic) stands before the dose in the span under the same rules;
    otherwise it is kept with drug None ("drug not identified in the decision text"), never under a name the text does not show.
    Outside model spans such a dose is left out. A bracketed actual dose after a per-area / per-weight dose is marked computed."""
    out = []
    ms = list(rx.finditer(text)) if rx else []
    doses = parse_doses(text)
    own = _owners(text, doses, ms)
    label_own, generic = [None] * len(doses), None
    if model_drug is not None:
        generic, labels = _model_labels(model_drug, names)
        lrx = _name_rx(labels)
        if lrx is not None:
            label_own = _owners(text, doses, list(lrx.finditer(text)), known=own)
    for i, d in enumerate(doses):
        if own[i] is not None:
            drug, s, o = names[own[i].group(1).lower()], own[i].start(), own
        elif label_own[i] is not None:
            drug, s, o = generic, label_own[i].start(), label_own
        elif model_drug is not None:
            drug, s, o = None, 0, None
        else:
            continue
        out.append({"drug": drug, "dose": d["dose"], "dose_max": d["dose_max"], "unit": d["unit"], "recorded": d["written"],
                    "span": text[s:d["end"]].strip(), "start": base + s, "end": base + d["end"], "dose_start": base + d["start"],
                    "computed": bool(o) and _computed(text, doses, o, i)})
    return out


def _stage_scan(text):
    out = []
    for m in list(_groups(text)) + list(_TNM_RX.finditer(text)) + list(_NM_RX.finditer(text)):
        if m.re is _TNM_RX and not (m.group("pre") or m.group("n") or m.group("m")):
            continue
        out.append((m.start(), m.end()))
    return out


async def check_decision(decision_text, cancer, recorded_stage=None, audit=None):
    """Guideline checks on a board decision. Returns {"checks": [...], "flags": [...]} (see the module docstring)."""
    text = decision_text or ""
    flags, checks = [], []
    try:
        listed = await llm.chat("reasoner", _messages(text), json_schema=SCHEMA, max_tokens=900, purpose="adjudication: guideline checks", audit=audit)
        if not isinstance(listed, dict):
            raise ValueError("no JSON object")
    except Exception as e:
        listed = {}
        flags.append({"kind": "system", "severity": "info",
                      "text": f"Guideline check: the model listing was unavailable ({str(e)[:120]}); the code scan of drug names and radiotherapy "
                              "schedules still ran"})
    names = drug_names(None)
    rx = _name_rx(names)

    def located(span):
        if not span:
            return None
        loc = grounding.locate(span, [text])
        return loc  # the model must quote the decision text itself; numbers are read from loc["matched"], never from the model

    # drugs: code scan + model items (located), one check per dose written in the decision. The code scan comes first: where both
    # tie the same dose, the name the decision text itself puts before the dose wins over the model's label.
    items = _drug_items(text, 0, names, rx)
    for it in listed.get("drugs") or []:
        loc = located(it.get("span"))
        if loc:
            items += _drug_items(loc["matched"], loc["start"], names, rx, model_drug=it.get("drug") or "")
    seen = []  # identified items first: a dose a name in the text holds is never reported as unidentified
    for it in [i for i in items if i["drug"]] + [i for i in items if not i["drug"]]:
        if it["dose"] and not any(s["dose_start"] < it["end"] and it["dose_start"] < s["end"] for s in seen):
            seen.append(it)
    for it in sorted(seen, key=lambda x: x["dose_start"]):
        if not it["drug"]:
            res, refs = "drug_not_identified", []
        elif it["computed"]:
            res, refs = "computed_dose_not_compared", []  # 'Paclitaxel 175 mg/m2 (300 mg)': the actual dose for this patient
        else:
            res, refs = compare_dose(it["drug"], it["dose"], it["unit"], cancer, it["dose_max"])
        c = {"kind": "drug", "span": it["span"], "drug": it["drug"], "dose": it["dose"], "dose_max": it["dose_max"], "unit": it["unit"],
             "recorded": it["recorded"], "result": res, "references": [_brief(r) for r in refs[:5]]}
        checks.append(c)
        if res not in ("consistent", "computed_dose_not_compared"):
            flags.append(_dose_flag(c, refs))

    # radiotherapy: model spans (located) + code scan of the whole text
    rts = []
    for it in listed.get("radiotherapy") or []:
        loc = located(it.get("span"))
        if loc:
            rts += [{**r, "start": loc["start"] + r["start"], "end": loc["start"] + r["end"]} for r in parse_rt(loc["matched"])]
    rts += parse_rt(text)
    kept = []
    for r in sorted(rts, key=lambda r: (r["start"], -(r["end"] - r["start"]))):
        if any(k["start"] < r["end"] and r["start"] < k["end"] for k in kept):
            continue
        kept.append(r)
    for r in kept:
        res, refs = compare_rt(r, cancer)
        span = text[r["start"]:r["end"]]
        c = {"kind": "rt", "span": span, "total_gy": r["total_gy"], "total_gy_max": r["total_gy_max"], "fractions": r["fractions"],
             "fractions_max": r["fractions_max"], "recorded": span, "result": res, "references": [_brief(x) for x in refs[:5]]}
        checks.append(c)
        if res != "consistent":
            flags.append(_rt_flag(c, refs))

    # stage as written vs the stage recorded in the signed reports
    spans = []
    for it in listed.get("stage") or []:
        loc = located(it.get("span"))
        if loc and parse_stage(loc["matched"], before=text[max(0, loc["start"] - 40):loc["start"]]):
            spans.append((loc["start"], loc["end"]))
    spans += _stage_scan(text)
    merged = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1] + 2:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    rec = parse_stage(recorded_stage.get("value"), bare=True) if recorded_stage and recorded_stage.get("value") else None
    if rec and not rec["group_prefix"]:
        rec["group_prefix"] = _text_prefix(recorded_stage.get("quote") or "")  # 'Pathological stage: Stage IIA (pT2 N0 M0)'
    for s, e in merged:
        w = parse_stage(text[s:e], before=text[max(0, s - 40):s])
        if not w:
            continue
        if not w["group_prefix"]:
            w["group_prefix"] = _context_prefix(text, s, e)  # 'Stage IIIA (clinical)', 'post-NACT stage IA'
        res, parts = compare_stage(w, rec)
        src = {k: recorded_stage.get(k) for k in ("value", "quote", "doc_id", "doc_title")} if recorded_stage else None
        c = {"kind": "stage", "span": text[s:e].strip(), "recorded": w["written"], "result": res, "compared": parts, "references": [],
             "source": src}
        checks.append(c)
        if res == "stage_differs":
            flags.append({"kind": "guideline", "check": "stage", "severity": "review", "recorded": w["written"], "span": c["span"], "source": src,
                          "text": f"Stage differs from the signed report: the decision records \"{w['written']}\"; the signed report records "
                                  f"\"{recorded_stage['value']}\" ({recorded_stage.get('doc_title') or recorded_stage.get('doc_id') or 'signed report'}). "
                                  "Review: the check compares the stage as written, it does not compute a stage."})
    return {"checks": checks, "flags": flags}
