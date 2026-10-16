"""Patient identity: read who a record belongs to by rules, and match it to a Tumour Board Case File (V1 item 2.4).

Pure functions: no storage, no model, no network. The reader model is only a fallback the caller runs when these rules find
nothing, and its values must pass grounding.locate like everything returned here.

Reading policy (read_identity)
- Only the header is read: the first 25 non-empty lines of page 1; the first 10 lines of later pages only fill what page 1
  lacks. Reading stops at the signature block (Sd/-, Reported / Signed / Verified by, End of report), and a line naming a
  medical council (KMC, MMC, DMC, TNMC, APMC, TSMC, NMC, MCI, "Medical Council") is never read, so a doctor's council
  Reg. No. never becomes a patient ID. A patient Reg. No. is also refused when a signer or council line is within 2 lines.
- Two layouts: "Label value" on one line (several labels per line, pipes allowed), and the boxed grid of Indian lab and
  radiology reports (a row of labels, the values on the next line, paired in order by value shape: an ID is one token with
  a digit, age / sex is "61 Y / M", a date is a date; the name is the text before the next value).
- Sample ID, Lab No., Accession No. are per-sample numbers: read past, never returned. Unlabelled numbers are never IDs.
- Aadhaar is never used: mask_aadhaar() keeps the last 4 digits only (UIDAI masked form); read_identity() reports
  aadhaar_seen and never returns the number. An ABHA (14 digits) is read and normalised; an ABHA address is only noted.
- Every value carries the verbatim line (or grid value row) it was read from; a quote grounding.locate cannot find is dropped.

Matching policy (match): an exact ID with a compatible name auto-links (the caller audits it, a person can undo it); an ID
whose name, age or sex disagrees is a possible wrong ID; a name alone only ever suggests, and only when it fits exactly
one patient; name variants are suggested, never linked without an ID. A new Case File opens on its own only for an unknown
UHID / MRN / CR No. / Hospital No. with a patient name read and no existing patient whose name, age and sex fit.
"""
import re
import unicodedata
from datetime import date, datetime

from . import grounding

ID_KINDS = ("uhid", "mrn", "cr_no", "ip_no", "op_no", "reg_no", "hospital_no", "abha", "pmjay")
# kinds that identify a patient of this hospital (may open a new Case File); ip_no / op_no / pmjay / abha only link to an
# existing patient's known ids
HOSPITAL_ID_KINDS = ("uhid", "mrn", "cr_no", "hospital_no", "reg_no")
# kinds that may open a new Case File on their own: a Reg. No. (often per visit) links to a patient who has it, never opens one
OPENS_CASE_KINDS = ("uhid", "mrn", "cr_no", "hospital_no")
TITLES = ("mr", "mrs", "ms", "shri", "sri", "smt", "kumari", "km", "master", "baby", "dr", "late", "selvi", "thiru", "miss", "mx")
ID_DISPLAY = {"uhid": "UHID", "mrn": "MRN", "cr_no": "CR No.", "ip_no": "IP No.", "op_no": "OP No.", "reg_no": "Reg. No.",
              "hospital_no": "Hospital No.", "abha": "ABHA", "pmjay": "PM-JAY ID"}
# comparable ID kinds: a lab's "Hospital No." is the same number as the UHID / MRN of the Case File
_GROUP = {"uhid": "hosp", "mrn": "hosp", "hospital_no": "hosp", "reg_no": "hosp", "cr_no": "cr", "ip_no": "ipop", "op_no": "ipop",
          "abha": "abha", "pmjay": "pmjay"}
HEADER_LINES, OTHER_PAGE_LINES = 25, 10

# ---- Aadhaar -------------------------------------------------------------------------------------------------------
_AADHAAR_LABEL = re.compile(r"(?<![A-Za-z])(?:aa?dhaa?r|uid)(?![A-Za-z])", re.I)
# 4-4-4 groups, not part of a longer number (the ABHA 91-4021-7788-3105 or 91 4021 7788 3105 is never touched)
_AADHAAR_GROUPED = re.compile(r"(?<![\d-])(?<!\d )\d{4}[ -]\d{4}[ -]\d{4}(?![\d-])(?! \d{4}(?!\d))")
_AADHAAR_ANY = re.compile(r"(?<![\d-])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\d-])")


def mask_aadhaar(text: str) -> tuple:
    """Replace Aadhaar numbers with 'XXXX XXXX <last 4>'. Returns (masked_text, count).

    Masked: any 12 digits printed in 4-4-4 groups (space or hyphen) that are not part of a longer number; and any 12 digits,
    grouped or not, on a line labelled Aadhaar / Adhar / Aadhar / UID (or under such a label in a grid). No Verhoeff check:
    a number that looks like an Aadhaar is masked whether or not it is valid."""
    count = 0

    def sub(m):
        nonlocal count
        count += 1
        return "XXXX XXXX " + re.sub(r"\D", "", m.group(0))[-4:]

    out, prev = [], ""
    for line in (text or "").split("\n"):
        rx = _AADHAAR_ANY if (_AADHAAR_LABEL.search(line) or _AADHAAR_LABEL.search(prev)) else _AADHAAR_GROUPED
        out.append(rx.sub(sub, line))
        prev = line
    return "\n".join(out), count


def normalise_id(value: str) -> str:
    """Upper-case, letters and digits only: 'SYN-600744' -> 'SYN600744', 'CR/2026/04118' -> 'CR202604118'."""
    return re.sub(r"[^0-9A-Z]", "", str(value or "").upper())


# ---- age / sex / DOB -----------------------------------------------------------------------------------------------
_SEXW = r"(male|female|other|transgender|m|f|o|t)"
_YRS = r"(?:y(?:rs?|ears?)?\.?)?"
_AGESEX_RX = re.compile(r"(?<![\w/.])(\d{1,3})\s*" + _YRS + r"\s*/\s*" + _SEXW + r"(?![A-Za-z])", re.I)
_AGESEX_LONG = re.compile(r"(?<![A-Za-z])age\s*[:\-]?\s*(\d{1,3})\s*" + _YRS + r"[\s,;|]*(?:sex|gender)\s*[:\-]?\s*" + _SEXW + r"(?![A-Za-z])", re.I)
_AGE_ONLY = re.compile(r"(?<![A-Za-z])age\s*[:\-]?\s*(\d{1,3})\s*" + _YRS + r"(?![\d/])", re.I)
_SEX_ONLY = re.compile(r"(?<![A-Za-z])(?:sex|gender)\s*[:\-]?\s*" + _SEXW + r"(?![A-Za-z])", re.I)


def _sex(s):
    s = (s or "").lower()
    return "M" if s in ("m", "male") else "F" if s in ("f", "female") else "O" if s else None


def _age(s):
    a = int(s)
    return a if 0 <= a <= 120 else None


def parse_agesex(s: str) -> tuple:
    """(age, sex) from '62 Y / M', '58 yrs / Male', '58Y/M', 'Age: 62 Years Sex: M'; sex in M / F / O. (None, None) if absent."""
    s = s or ""
    m = _AGESEX_RX.search(s) or _AGESEX_LONG.search(s)
    if m:
        return _age(m.group(1)), _sex(m.group(2))
    a, x = _AGE_ONLY.search(s), _SEX_ONLY.search(s)
    return (_age(a.group(1)) if a else None), (_sex(x.group(1)) if x else None)


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DOB_RX = re.compile(r"(?P<d>\d{1,2})[-/.](?P<m>\d{1,2})[-/.](?P<y>\d{4})|(?P<d2>\d{1,2})[\s-](?P<mon>[A-Za-z]{3,9})\.?[\s,-]+(?P<y2>\d{4})"
                     r"|(?P<y3>\d{4})-(?P<m3>\d{1,2})-(?P<d3>\d{1,2})")


def _parse_dob(s) -> str:
    """ISO date of birth, day first (docstatus.parse_date only accepts report years from 1990, so births need their own)."""
    m = _DOB_RX.search(str(s or ""))
    if not m:
        return ""
    try:
        if m.group("d"):
            d, mo, y = int(m.group("d")), int(m.group("m")), int(m.group("y"))
        elif m.group("d2"):
            d, mo, y = int(m.group("d2")), _MONTHS.get(m.group("mon")[:3].lower()), int(m.group("y2"))
        else:
            d, mo, y = int(m.group("d3")), int(m.group("m3")), int(m.group("y3"))
        dt = datetime(y, mo, d)
    except (TypeError, ValueError):
        return ""
    return dt.date().isoformat() if 1900 <= dt.year <= 2100 else ""


# ---- names ----------------------------------------------------------------------------------------------------------
_VARIANT_GROUPS = (("lakshmi", "laxmi", "lakshmy", "laksmi"), ("mohammed", "mohammad", "muhammad", "muhammed", "mohd", "md", "mohamed"),
                   ("shaikh", "sheikh", "shaik", "sk", "sheik"), ("venkata", "venkat"), ("srinivas", "sreenivas", "srinivasa"),
                   ("sunita", "sunitha", "suneeta"), ("pratap", "prathap"), ("raghavendra", "raghavender"), ("devi", "devee"),
                   ("rahman", "rehman", "rahaman"), ("abdul", "abdool"), ("prasad", "prasaad"), ("gowda", "gouda"), ("iyer", "aiyar", "ayyar"))
_CANON = {v: g[0] for g in _VARIANT_GROUPS for v in g}
GENERIC = frozenset({"kumar", "kumari", "devi", "singh", "bai", "ben", "bhai", "begum", "bibi", "khan", "das", "lal", "rao", "reddy", "naidu",
                     "nair", "iyer", "sharma", "verma", "gupta", "patel", "shaikh", "sheikh", "mohammed", "mohammad", "md", "mohd", "ali"})
# gender / marital suffixes, not family names: two names that differ in them are different people (Devi / Kumari)
_MARKERS = frozenset({"kumar", "kumari", "devi", "bai", "ben", "bhai", "begum", "bibi"})
_SEXED = (("kumar", "kumari"), ("bhai", "ben"))
_TITLE_SEX = {"mr": "M", "shri": "M", "sri": "M", "master": "M", "thiru": "M",
              "mrs": "F", "ms": "F", "smt": "F", "kumari": "F", "km": "F", "selvi": "F", "miss": "F"}
_PHON = (("ph", "f"), ("v", "w"), ("dh", "d"), ("th", "t"), ("kh", "k"), ("gh", "g"), ("bh", "b"), ("sh", "s"), ("ch", "\0"),
         ("z", "j"), ("q", "k"), ("c", "k"), ("\0", "c"), ("aa", "a"), ("ee", "i"), ("oo", "u"), ("y", "i"))
_OCR = (("rn", "m"), ("vv", "w"), ("cl", "d"), ("0", "o"), ("1", "l"), ("5", "s"), ("8", "b"))
_REL_RX = re.compile(r"(?<![A-Za-z])(?:([SWDC])\s*/\s*O(?![A-Za-z])\.?|(son|wife|daughter|care)\s+of(?![A-Za-z]))", re.I)
_REL_KIND = {"s": "S/o", "w": "W/o", "d": "D/o", "c": "C/o", "son": "S/o", "wife": "W/o", "daughter": "D/o", "care": "C/o"}


def _plain(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _tokens(s):
    s = _plain(s).replace("'", "").replace("’", "")
    return [t.lower() for t in re.findall(r"[^\W_]+", s) if not t.isdigit()]


def _generic(t):
    return t in GENERIC or _CANON.get(t, t) in GENERIC


def phonetic_key(token: str) -> str:
    """Transliteration-tolerant key: variant table first, then ph=f, v=w, dh=d, th=t, kh=k, gh=g, bh=b, sh=s, z=j, q=k, c=k
    (ch kept), aa=a, ee=i, oo=u, y=i, doubled letters collapsed, a final h after a vowel dropped. Kumar and Kumari differ."""
    t = _plain(token).lower()
    t = _CANON.get(t, t)
    for a, b in _PHON:
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)
    return re.sub(r"([aeiou])h$", r"\1", t)


def _ocr_key(t):
    for a, b in _OCR:
        t = t.replace(a, b)
    return phonetic_key(t)


def _strip_titles(toks):
    toks, sex = list(toks), None
    while toks and toks[0] in TITLES:
        sex = sex or _TITLE_SEX.get(toks[0])
        toks.pop(0)
    return toks, sex


def normalise_name(name: str) -> dict:
    """Tokens for matching an Indian name as printed.

    Leading titles (Shri, Smt., Kumari, Late ...) and titles in brackets are removed and kept only as a sex hint; the
    comma form is surname first ("KUMAR, RAMESH" -> ramesh kumar: the part before the comma goes last); anything from
    S/o, W/o, D/o, C/o (or 'son of' ...) onwards is the relation, not the name. Single letters are initials."""
    raw = name or ""
    s, relation = raw, {"kind": None, "name": ""}
    m = _REL_RX.search(s)
    if m:
        relation = {"kind": _REL_KIND[(m.group(1) or m.group(2)).lower()], "name": s[m.end():].strip(" .,;:-")}
        s = s[:m.start()]
    sex = None

    def paren(mm):
        nonlocal sex
        inner = _tokens(mm.group(1))
        if inner and all(t in TITLES for t in inner):
            sex = sex or next((_TITLE_SEX[t] for t in inner if t in _TITLE_SEX), None)
            return " "
        return " " + mm.group(1) + " "
    s = re.sub(r"\(([^)]*)\)", paren, s)
    before, comma, after = s.partition(",")
    parts = [after, before] if comma and _tokens(after) else [before]
    tokens = []
    for p in parts:
        t, sx = _strip_titles(_tokens(p))
        sex = sex or sx
        tokens += t
    return {"raw": raw, "tokens": tokens, "initials": [t for t in tokens if len(t) == 1],
            "keys": [phonetic_key(t) for t in tokens if len(t) > 1], "relation": relation, "sex_hint": sex}


_LEVEL_RANK = {"exact": 0, "variant": 1, "initials": 2, "partial": 3, "incompatible": 4}


def names_compatible(a: str, b: str) -> dict:
    """How two printed names relate: {"level", "detail", "sex_conflict", "distinctive"}.

    exact        same tokens after titles and order are set aside.
    variant      every token of the shorter name has a partner in the other (same, transliteration variant, OCR
                 confusion such as rn/m, or the same letters with the spaces removed), and either a non-generic token
                 agrees or both names are fully covered (e.g. Md. Ali Khan / Mohammed Ali Khan).
    initials     as variant, but at least one token agrees only as an initial (R. Kumar / Ramesh Kumar); at least one
                 full token must agree as well.
    partial      a non-generic token agrees but another token disagrees (Ramesh Gowda / Ramesh Patil): never linked,
                 only listed for a person to look at.
    incompatible only generic tokens agree (Kumar, Devi), or the names carry different gender / marital suffixes
                 (Kumar / Kumari: sex_conflict; Devi / Kumari), or a single generic token, or only an initial.
    distinctive  a non-generic full token agrees (needed before a name alone can suggest a link)."""
    na, nb = normalise_name(a or ""), normalise_name(b or "")
    ta, tb = na["tokens"], nb["tokens"]

    def out(level, detail, sex_conflict=False, distinctive=False):
        return {"level": level, "detail": detail, "sex_conflict": sex_conflict, "distinctive": distinctive}
    if not ta or not tb:
        return out("incompatible", "a name is missing")
    sa, sb = set(ta), set(tb)
    for m, f in _SEXED:
        if (m in sa and f in sb and f not in sa and m not in sb) or (f in sa and m in sb and m not in sa and f not in sb):
            return out("incompatible", f"{m.title()} / {f.title()}: the names point to different sexes", True)
    if na["sex_hint"] and nb["sex_hint"] and na["sex_hint"] != nb["sex_hint"]:
        return out("incompatible", "the titles point to different sexes", True)
    fa, fb = [t for t in ta if len(t) > 1], [t for t in tb if len(t) > 1]
    if not fa or not fb:
        return out("incompatible", "only an initial is printed")
    if sorted(ta) == sorted(tb):
        if len(ta) == 1 and _generic(ta[0]):
            return out("incompatible", f"only the common name part '{ta[0]}'")
        return out("exact", "same name", distinctive=any(not _generic(t) for t in fa))
    for j in (fb, fb[::-1]):  # Venkata Ramana / Venkataramana, Abdul Rahman / Abdulrahman
        if len(fa) + len(j) > 2 and phonetic_key("".join(fa)) == phonetic_key("".join(j)) and not _generic("".join(fa)):
            return out("variant", "same letters, spaced differently", distinctive=True)
    A, B = (ta, tb) if (len(ta), -len(na["initials"])) <= (len(tb), -len(nb["initials"])) else (tb, ta)
    used, part = [False] * len(B), {}

    def take(i, how, pred):
        for j, t in enumerate(B):
            if not used[j] and pred(t):
                used[j], part[i] = True, (t, how)
                return
    for how, pred in (("same", lambda x, t: len(t) > 1 and t == x),
                      ("variant", lambda x, t: len(t) > 1 and phonetic_key(t) == phonetic_key(x)),
                      ("ocr", lambda x, t: len(t) >= 5 and len(x) >= 5 and _ocr_key(t) == _ocr_key(x)),
                      ("initial", lambda x, t: len(t) == 1 and t == x[0])):
        for i, x in enumerate(A):
            if len(x) > 1 and i not in part:
                take(i, how, lambda t, x=x, pred=pred: pred(x, t))
    for i, x in enumerate(A):  # initials of the shorter name: any remaining token with that first letter
        if len(x) == 1 and i not in part:
            take(i, "initial", lambda t, x=x: t[0] == x)
    full = [(A[i], t, h) for i, (t, h) in part.items() if h in ("same", "variant", "ocr")]
    distinctive = any(not _generic(x) for x, _, _ in full)
    ua = [A[i] for i in range(len(A)) if i not in part]
    ub = [t for j, t in enumerate(B) if not used[j]]
    if ua:
        if not distinctive:
            return out("incompatible", "only common name parts agree" if full else "no name part agrees")
        if any(x in _MARKERS for x in ua) and any(y in _MARKERS for y in ub):
            return out("incompatible", f"different name suffix ({', '.join(ua)} / {', '.join(ub)})", distinctive=True)
        return out("partial", f"{' '.join(ua)} does not match {' '.join(ub) or 'anything'}", distinctive=True)
    if not full:
        return out("partial", "only initials agree")
    hows = {h for _, h in part.values()}
    notes = []
    if "variant" in hows:
        notes.append("spelling variant (" + ", ".join(f"{x}/{t}" for x, t, h in full if h == "variant") + ")")
    if "ocr" in hows:
        notes.append("possible OCR misreading (" + ", ".join(f"{x}/{t}" for x, t, h in full if h == "ocr") + ")")
    if ub:
        notes.append("only in the longer name: " + " ".join(ub))
    if "initial" in hows:
        ini = [f"{A[i]}={t}" if len(A[i]) == 1 else f"{t}={A[i]}" for i, (t, h) in part.items() if h == "initial"]
        return out("initials", "initial matches (" + ", ".join(ini) + ")" + ("; " + "; ".join(notes) if notes else ""), distinctive=distinctive)
    if distinctive or (not ub and len(full) >= 2):
        return out("variant", "; ".join(notes) or "same name parts", distinctive=distinctive)
    return out("incompatible", "only common name parts agree")


# ---- header reading -------------------------------------------------------------------------------------------------
_LABEL_SPECS = (
    ("skip_id", r"sample\s*(?:id|no\.?)|lab\.?\s*(?:no\.?|id)|accession\s*(?:no\.?|number)?|specimen\s*(?:id|no\.?)|bill\s*no\.?|receipt\s*no\.?|bed\s*no\.?|barcode"),
    ("uhid", r"mrd\s*no\.?\s*/\s*uhid(?:\s*no\.?)?|op\s*/\s*ip\s*no\.?\s*/\s*uhid|uhid\s*(?:no\.?|number)?"),
    ("hospital_no", r"hosp(?:ital)?\.?\s*(?:no\.?|number|id)|(?:patient|pt\.?)\s*id"),
    ("mrn", r"mrd\s*(?:no\.?|number)|mrn\s*(?:no\.?)?|m\.?\s*r\.?\s*(?:no\.?|number)"),
    ("cr_no", r"c\.?\s*r\.?\s*(?:no\.?|number)"),
    ("ip_no", r"op\s*/\s*ip\s*no\.?|ipd?\s*(?:no\.?|number)|in-?\s*patient\s*(?:no\.?|number)|admission\s*(?:no\.?|number)"),
    ("op_no", r"opd?\s*(?:no\.?|number)|out-?\s*patient\s*(?:no\.?|number)"),
    ("reg_no", r"(?:patient\s*)?reg(?:istration|n)?\.?\s*(?:no\.?|number)"),
    ("abha_address", r"abha\s*address|phr\s*address"),
    ("abha", r"abha\s*(?:no\.?|number|id)?|health\s*id\s*(?:no\.?|number)?"),
    ("pmjay", r"pm\s*-?\s*jay\s*(?:id|no\.?|number)?|ayushman\s*(?:bharat\s*)?(?:card\s*)?(?:no\.?|id|number)"),
    ("aadhaar", r"aa?dhaa?r\s*(?:card\s*)?(?:no\.?|number)?|uid\s*(?:no\.?|number)?"),
    ("agesex", r"age\s*/\s*(?:sex|gender)|age\s*&\s*(?:sex|gender)|sex\s*/\s*age"),
    ("dob", r"d\.?\s*o\.?\s*b\.?|date\s*of\s*birth"),
    ("skip_date", r"reg(?:istration|n)?\.?\s*date|collected\s*on|collection\s*date|received\s*on|reported\s*on|report\s*date|study\s*date"
                  r"|visit\s*date|next\s*review|sampled\s*on|printed\s*on|procedure\s*date|admission\s*date|discharge\s*date"
                  r"|date\s*of\s*(?:admission|discharge|visit|procedure|surgery|report)|date"),
    ("age", r"age"),
    ("sex", r"sex|gender"),
    ("relation", r"relation(?:ship)?|father\s*/\s*guardian|father'?s?\s*/\s*husband'?s?\s*name|father'?s?\s*name|husband'?s?\s*name"
                 r"|guardian'?s?\s*name|guardian|relative'?s?\s*name|[swdc]\s*/\s*o\.?|son\s+of|wife\s+of|daughter\s+of|care\s+of"),
    ("skip_text", r"ref(?:erred)?\.?\s*by|referring\s*(?:doctor|physician|hospital)|consultant|(?:test|hospital|doctor|lab)\s*name"),
    ("name", r"patient'?s?\s*name|name\s*of\s*(?:the\s*)?patient|pt\.?\s*name|patient\s*:|name"),
)
_LABEL_RX = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(f"(?P<{k}>{rx})" for k, rx in _LABEL_SPECS) + r")(?![A-Za-z])", re.I)
_SHAPE = {"name": "text", "relation": "text", "skip_text": "text", "agesex": "agesex", "age": "age", "sex": "sex", "dob": "date",
          "skip_date": "date", "aadhaar": "aadhaar", "abha": "abha"}
_DATE_TIME = (r"(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}[\s-][A-Za-z]{3,9}\.?[\s,-]+\d{2,4}|\d{4}-\d{1,2}-\d{1,2})"
              r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp]\.?[Mm]\.?)?)?")
_SHAPE_RX = {"agesex": _AGESEX_RX, "age": re.compile(r"\d{1,3}\s*" + _YRS + r"(?![\d/])", re.I),
             "sex": re.compile(r"(?:male|female|other|m|f|o)(?![A-Za-z])", re.I), "date": re.compile(_DATE_TIME),
             "aadhaar": re.compile(r"(?:\d{4}|[Xx]{4})[ -]?(?:\d{4}|[Xx]{4})[ -]?\d{4}"), "abha": re.compile(r"\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
             "token": re.compile(r"[^\s|]+")}
_NEXT_VALUE = re.compile(r"(?<!\S)(?:[^\s|]*\d[^\s|]*|[Xx]{4})(?![^\s|])")
_REL_LABEL_KIND = {"s": "S/o", "w": "W/o", "d": "D/o", "c": "C/o", "son": "S/o", "wife": "W/o", "daughter": "D/o", "care": "C/o",
                   "husband": "W/o", "father": "father", "guardian": "C/o", "relative": "C/o"}
_STOP = re.compile(r"\bsd\s*/\s*-|\b(?:reported|signed|verified|authori[sz]ed|checked|approved)\s+(?:and\s+verified\s+)?by\b"
                   r"|electronically\s+signed|digitally\s+signed|end\s+of\s+report", re.I)
_COUNCIL = re.compile(r"(?<![A-Za-z])(?:KMC|MMC|DMC|TNMC|APMC|TSMC|NMC|MCI|[A-Z]{1,4}MC)(?![A-Za-z])|(?i:medical\s+council)")
_DOCTOR = re.compile(r"^\s*(?:[Dd][Rr]|[Pp]rof)\.?\s+[A-Z].*\b(?:MBBS|MD|MS|DNB|DM|MCh|FRCR|FRCPath|DMRD|DMRE)\b")


def _labels(line):
    return [(m.lastgroup, m.start(), m.end(), m.group(0).strip()) for m in _LABEL_RX.finditer(line)]


def _is_label_row(line, labels):
    if not labels:
        return False
    rest = list(line)
    for _, s, e, _ in labels:
        rest[s:e] = [" "] * (e - s)
    return not re.sub(r"[\s:|\-.,/()]+", "", "".join(rest))


def _clean_text(v):
    """Free text (a name, a relation name) up to the first value that has a digit; trailing punctuation removed."""
    v = (v or "").split("|")[0]
    m = _NEXT_VALUE.search(v)
    if m:
        v = v[:m.start()]
    return v.strip(" \t:-,.;")


_MASKED_AADHAAR = re.compile(r"[\s:#\-]*X{4} X{4} \d{4}(?!\d)", re.I)  # exactly the form mask_aadhaar() writes


def _id_token(v):
    """The identifier after a label: one token with a digit, at least 3 characters ('X100', 'XR-2210', 'KMH/OP/26/55120');
    a masked Aadhaar ('XXXX XXXX 1180') is never an identifier."""
    if _MASKED_AADHAAR.match(v or ""):
        return ""
    m = re.match(r"[\s:#\-]*([^\s|]+)", v or "")
    tok = m.group(1).rstrip(".,;:)") if m else ""
    return tok if len(tok) >= 3 and re.search(r"\d", tok) else ""


class _Page:
    """What one page header yields: first value of each field wins."""

    def __init__(self, pi, lines, all_lines):
        self.pi, self.lines, self.all = pi, lines, all_lines
        self.name = self.dob = self.relation = None
        self.ids, self.agesex, self.notes, self.aadhaar = [], [], [], False

    def add(self, kind, label, value, quote, line_no):
        if kind == "aadhaar":
            self.aadhaar = True
        elif kind == "name":
            v = _clean_text(value)
            m = _REL_RX.search(v)
            if m:  # 'Ramesh Kumar S/o Mohan Lal' in a grid cell
                self.add("relation", m.group(0), v[m.end():], quote, line_no)
                v = v[:m.start()].strip(" ,.;:-")
            if self.name is None and len(re.sub(r"[^A-Za-zऀ-ൿ]", "", v)) >= 2 and len(v) <= 80:
                self.name = {"value": v, "quote": quote, "page": self.pi, "label": label}
        elif kind == "relation":
            v = _clean_text(value)
            m = re.match(r"(?i)\s*(son|wife|daughter|care|husband|father|guardian|relative|s|w|d|c)", label)
            k = _REL_LABEL_KIND.get(m.group(1).lower()) if m else None
            if k and v and self.relation is None and re.search(r"[A-Za-z]{2}", v):
                self.relation = {"kind": k, "name": v, "quote": quote}
        elif kind in ("agesex", "age", "sex"):
            a, s = parse_agesex(value if kind == "agesex" else f"{label} {value}")
            if a is not None or s is not None:
                self.agesex.append((a, s, quote))
        elif kind == "dob":
            iso = _parse_dob(value)
            if iso and self.dob is None:
                self.dob = (iso, quote)
        elif kind == "abha":
            m = _SHAPE_RX["abha"].match((value or "").lstrip(" :#-"))
            if m:
                self._id("abha", label, m.group(0), quote)
            elif "@" in (value or ""):
                self.notes.append("ABHA address seen (not used for matching)")
            elif (value or "").strip():
                self.notes.append(f"{label} is not a 14-digit ABHA number: not read")
        elif kind == "abha_address":
            if "@" in (value or ""):
                self.notes.append("ABHA address seen (not used for matching)")
        elif kind in ID_KINDS:
            tok = _id_token(value)
            if not tok:
                return
            if kind == "reg_no" and (_COUNCIL.match(tok) or self._near_signer(line_no)):
                self.notes.append(f"'{label} {tok}' sits next to a doctor's signature or council: not a patient ID")
                return
            self._id(kind, label, tok, quote)

    def _id(self, kind, label, value, quote):
        if all((k, normalise_id(v)) != (kind, normalise_id(value)) for k, v, _, _ in self.ids):
            self.ids.append((kind, value, label, quote))

    def _near_signer(self, line_no):
        lo, hi = max(0, line_no - 2), min(len(self.all), line_no + 3)
        return any(_STOP.search(x) or _COUNCIL.search(x) or _DOCTOR.search(x) for i, x in enumerate(self.all[lo:hi], lo) if i != line_no)

    def read(self):
        consumed = set()
        for i, line in enumerate(self.lines):
            if i in consumed or _COUNCIL.search(line) or _DOCTOR.search(line):
                continue
            labels = _labels(line)
            if _is_label_row(line, labels):
                j = i + 1
                if j < len(self.lines) and not _COUNCIL.search(self.lines[j]):
                    vl = self.lines[j]
                    vlabels = _labels(vl)
                    if all(k == "relation" and _REL_RX.fullmatch(t) for k, _, _, t in vlabels) and not _is_label_row(vl, vlabels):
                        consumed.add(j)
                        self._grid(labels, vl, j)
                continue
            for n, (kind, s, e, text) in enumerate(labels):
                end = labels[n + 1][1] if n + 1 < len(labels) else len(line)
                cells = (line[e:] if kind in ("age", "sex") else line[e:end]).split("|")  # 'Age: 62 Years Sex: M' read together
                # the value follows the label in the same cell ('UHID SYN-1'), or sits in the next cell of a transcribed table
                # ('Name | Smt. Sunita Devi | UHID | SYN-500911 | Age / Sex | 67 Y / F')
                value = cells[0] if cells[0].strip(" :-.#") else next((c for c in cells[1:] if c.strip(" :-.#")), "")
                self.add(kind, text.rstrip(" :"), value, line, i)
            if not any(k in ("agesex", "age", "sex") for k, *_ in labels) and labels and _AGESEX_RX.search(line):
                a, s = parse_agesex(line)  # 'Patient: ... | MRN: ... | 62 Y / M'
                self.agesex.append((a, s, line))
        if not self.agesex:
            for line in self.lines:  # an unlabelled '58 yrs / Male' in the header
                if not (_COUNCIL.search(line) or _DOCTOR.search(line)) and _AGESEX_RX.search(line):
                    a, s = parse_agesex(line)
                    self.agesex.append((a, s, line))
                    break
        return self

    def _grid(self, labels, vl, j):
        """Pair a label row with the value row below it, in order, by value shape."""
        pos = 0
        for n, (kind, _, _, text) in enumerate(labels):
            while pos < len(vl) and vl[pos] in " \t|":
                pos += 1
            shape = _SHAPE.get(kind, "token")
            if shape == "text":
                nxt = labels[n + 1][0] if n + 1 < len(labels) else None
                if nxt is None:
                    value, end = vl[pos:], len(vl)
                else:
                    if _SHAPE.get(nxt, "token") == "text":
                        self.notes.append("two text columns side by side in a header grid: not read")
                        return
                    m = _NEXT_VALUE.search(vl, pos)
                    end = m.start() if m else len(vl)
                    value = vl[pos:end]
                self.add(kind, text.rstrip(" :"), value, vl, j)
                pos = end
                continue
            if shape == "token" and (_AGESEX_RX.match(vl, pos) or _SHAPE_RX["date"].match(vl, pos)):
                continue  # empty cell: the next value belongs to a later column
            m = _SHAPE_RX[shape].match(vl, pos)
            if not m or (shape == "token" and not _id_token(m.group(0)) and kind in ID_KINDS):
                continue
            self.add(kind, text.rstrip(" :"), m.group(0), vl, j)
            pos = m.end()


def _header_lines(text, limit):
    out = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if _STOP.search(s):
            break
        out.append(s)
        if len(out) >= limit:
            break
    return out


def read_identity(pages: list, filename: str = "") -> dict:
    """Identity block of a record, by rules (see the module docstring). Every value is quote-checked with grounding.locate.

    Returns {"name": {"value","quote","page","label"} | None, "ids": [{"kind","value","quote","page","label"}],
             "age", "sex", "agesex_quote", "dob" (yyyy-mm-dd), "dob_quote", "relation": {"kind","name","quote"} | None,
             "aadhaar_seen", "abha" (14 digits) | None, "hospital_header", "notes"}.
    filename is not read for identity (a file name is not a quote); it only names the record in notes."""
    pages = list(pages or [])
    masked, n_aadhaar = [], 0
    for p in pages:
        t, c = mask_aadhaar(p or "")
        masked.append(t)
        n_aadhaar += c
    res = {"name": None, "ids": [], "age": None, "sex": None, "agesex_quote": "", "dob": None, "dob_quote": "", "relation": None,
           "aadhaar_seen": n_aadhaar > 0, "abha": None, "hospital_header": "", "notes": []}
    if not masked:
        return res
    res["hospital_header"] = next((s.strip() for s in masked[0].splitlines() if s.strip()), "")

    def located(quote):
        return bool(quote) and (grounding.locate(quote, pages) is not None or grounding.locate(quote, masked) is not None)
    for pi, text in enumerate(masked):
        lines = _header_lines(text, HEADER_LINES if pi == 0 else OTHER_PAGE_LINES)
        pg = _Page(pi, lines, [s.strip() for s in text.splitlines() if s.strip()]).read()
        res["aadhaar_seen"] = res["aadhaar_seen"] or pg.aadhaar
        res["notes"] += [n for n in pg.notes if n not in res["notes"]]
        if res["name"] is None and pg.name:
            if located(pg.name["quote"]):
                res["name"] = pg.name
            else:
                res["notes"].append("patient name: quote not found in the document, dropped")
        if not res["ids"] and pg.ids:
            for kind, value, label, quote in pg.ids:
                if located(quote):
                    res["ids"].append({"kind": kind, "value": value, "quote": quote, "page": pi, "label": label})
                else:
                    res["notes"].append(f"{label}: quote not found in the document, dropped")
        if res["age"] is None and res["sex"] is None and pg.agesex:
            a, s, q = pg.agesex[0]
            if s is None or a is None:  # age and sex printed on separate lines
                other = next(((a2, s2, q2) for a2, s2, q2 in pg.agesex[1:] if (a is None and a2 is not None) or (s is None and s2 is not None)), None)
                if other and located(q + " " + other[2]):
                    a, s, q = (a if a is not None else other[0]), (s or other[1]), q + " " + other[2]
            if located(q):
                res["age"], res["sex"], res["agesex_quote"] = a, s, q
        if res["dob"] is None and pg.dob and located(pg.dob[1]):
            res["dob"], res["dob_quote"] = pg.dob
        if res["relation"] is None and pg.relation and located(pg.relation["quote"]):
            res["relation"] = pg.relation
    if res["relation"] and res["relation"]["kind"] == "father":
        res["relation"]["kind"] = {"M": "S/o", "F": "D/o"}.get(res["sex"], "C/o")
    abha = next((normalise_id(i["value"]) for i in res["ids"] if i["kind"] == "abha"), "")
    res["abha"] = abha if len(abha) == 14 and abha.isdigit() and len(set(abha)) > 1 else None
    if res["aadhaar_seen"]:
        res["notes"].append("Aadhaar number printed: masked, never used for matching")
    if res["name"] is None and filename:
        res["notes"].append(f"no patient name read from the header of {filename}")
    return res


# ---- matching -------------------------------------------------------------------------------------------------------
def _relation(rel):
    if isinstance(rel, dict):
        return {"kind": rel.get("kind"), "name": rel.get("name") or ""} if rel.get("name") else None
    if isinstance(rel, str) and rel.strip():
        n = normalise_name(rel)["relation"]
        return {"kind": n["kind"], "name": n["name"]} if n["kind"] else {"kind": None, "name": rel.strip()}
    return None


def patient_record(patient: dict) -> dict:
    """A Case File's case["patient"] in comparable form. Today's keys are name, mrn, agesex; optional keys: ids
    [{kind, value}], uhid / cr_no / ... directly, abha, age, sex, dob, relation, aliases. The MRN is stored under both
    uhid and mrn (the Case File label is 'UHID / MRN')."""
    p = patient or {}
    ids = set()
    for k in ("mrn", "uhid"):
        if p.get(k):
            ids |= {("uhid", normalise_id(p[k])), ("mrn", normalise_id(p[k]))}
    for k in ID_KINDS:
        if k not in ("mrn", "uhid", "abha") and isinstance(p.get(k), str) and normalise_id(p[k]):
            ids.add((k, normalise_id(p[k])))
    for it in p.get("ids") or []:
        if isinstance(it, dict) and it.get("kind") in ID_KINDS and normalise_id(it.get("value")):
            ids.add((it["kind"], normalise_id(it["value"])))
    abha = normalise_id(p.get("abha")) or next((v for k, v in ids if k == "abha"), "")
    if abha:
        ids.add(("abha", abha))
    age, sex = p.get("age"), p.get("sex")
    if age is None or sex is None:
        a, s = parse_agesex(p.get("agesex") or "")
        age, sex = (age if age is not None else a), (sex or s)
    return {"name": p.get("name") or "", "aliases": [a for a in (p.get("aliases") or []) if a], "ids": ids, "abha": abha or None,
            "age": int(age) if isinstance(age, (int, str)) and str(age).isdigit() else None, "sex": _sex(sex) if sex else None,
            "dob": _parse_dob(p.get("dob")) or None, "relation": _relation(p.get("relation"))}


def _age_on(dob, today):
    d = date.fromisoformat(dob)
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def _assess(name, age, sex, dob, rel, rec, today):
    """Name level (best over the Case File name and its aliases), age / sex / DOB / relation fit."""
    best = None
    for n in [rec["name"]] + rec["aliases"]:
        c = names_compatible(name or "", n)
        if best is None or _LEVEL_RANK[c["level"]] < _LEVEL_RANK[best["level"]]:
            best = c
    pa = rec["age"] if rec["age"] is not None else (_age_on(rec["dob"], today) if rec["dob"] else None)
    ia = age if age is not None else (_age_on(dob, today) if dob else None)
    rel_ok = None
    if rel and rec["relation"]:
        kinds = {rel.get("kind"), rec["relation"].get("kind")} - {None, "C/o"}
        rel_ok = len(kinds) <= 1 and names_compatible(rel["name"], rec["relation"]["name"])["level"] in ("exact", "variant", "initials")
    return {"name": best, "age_fit": (abs(ia - pa) <= 1) if ia is not None and pa is not None else None,
            "sex_fit": (sex == rec["sex"]) if sex and rec["sex"] else None,
            "dob_fit": (dob == rec["dob"]) if dob and rec["dob"] else None, "rel_ok": rel_ok,
            "single": len(normalise_name(name or "")["tokens"]) < 2 or len(normalise_name(rec["name"])["tokens"]) < 2}


def _why(a):
    w = [f"name {a['name']['level']} ({a['name']['detail']})"]
    w.append({True: "age fits", False: "age differs", None: "age not known"}[a["age_fit"]])
    w.append({True: "sex fits", False: "sex differs", None: "sex not known"}[a["sex_fit"]])
    if a["dob_fit"] is not None:
        w.append("DOB matches" if a["dob_fit"] else "DOB differs")
    if a["rel_ok"] is not None:
        w.append("relation fits" if a["rel_ok"] else "relation differs")
    return "; ".join(w)


def _cand(cid, a, id_match, listed=None):
    c = {"case_id": cid, "why": _why(a), "name_match": a["name"]["level"], "id_match": id_match, "age_fit": a["age_fit"], "sex_fit": a["sex_fit"]}
    if listed is not None:
        c["listed"] = listed
    return c


def _fmt_rel(r):
    return f"{r.get('kind') or ''} {r.get('name')}".strip()


def _fits(a):
    """Name (exact, variant, or initials with a distinctive token) + same sex + age within 1 year (or the same DOB)."""
    lv = a["name"]
    name_ok = lv["level"] in ("exact", "variant") or (lv["level"] == "initials" and lv["distinctive"])
    when_ok = a["dob_fit"] is True or (a["dob_fit"] is None and a["age_fit"] is True)
    return name_ok and not lv["sex_conflict"] and a["sex_fit"] is True and when_ok


def _known_id(patient, kind):
    """The Case File's own identifier to show beside a printed one: same kind first, then a comparable kind, then any."""
    p = patient or {}
    raw = [(k, p[k]) for k in ID_KINDS if isinstance(p.get(k), str) and p[k].strip()]
    raw += [(it["kind"], it["value"]) for it in p.get("ids") or [] if isinstance(it, dict) and it.get("kind") in ID_KINDS and it.get("value")]
    if not raw:
        return ""
    k, v = min(raw, key=lambda x: (x[0] != kind, _GROUP.get(x[0]) != _GROUP.get(kind)))
    same = k == kind or (k in ("uhid", "mrn") and kind in ("uhid", "mrn"))  # the Case File label is 'UHID / MRN'
    return f"{ID_DISPLAY[kind if same else k]} {v}"


def match(identity: dict, patients: list, today=None) -> dict:
    """Decide where a record goes. patients: [{"case_id", "patient": case["patient"], "listed": bool}].

    Returns {"decision": auto_link | suggest | needs_matching | new_case | id_conflict, "case_id", "candidates", "reason",
    "matched_on": {"kind","value"} | None}. Rules, in order:
    1. An ID equal to a Case File's ID of a comparable kind (UHID / MRN / Hospital No. / Reg. No. with each other, CR No.,
       IP / OP No., ABHA, PM-JAY ID): with a compatible name (exact, variant, initials), no sex conflict, age within
       1 year and no DOB or same-kind ID contradicting it -> auto_link (a relation mismatch is only noted). Otherwise
       -> id_conflict (possible wrong ID). IDs pointing to two Case Files -> id_conflict, never a link.
    2. No ID matched but a UHID, MRN, CR No. or Hospital No. is printed (OPENS_CASE_KINDS) -> new_case on it, only when a
       patient name was read and no Case File fits the name, sex and age (or DOB) as in rule 3; otherwise needs_matching
       (the same patient registered twice, or a different person). Only a Reg. No. / ABHA / IP / OP / PM-JAY number that
       nobody has -> needs_matching (per-visit, portable or episode numbers never open a Case File).
    3. No ID printed: name (exact or variant, or initials with a non-generic token agreeing) + same sex + age within
       1 year (or the same DOB when both are known) + compatible relation name when both are known, fitting exactly one
       Case File -> suggest (a person confirms; never automatic). Two or more -> needs_matching. A single-token name
       never suggests.
    4. Anything else -> needs_matching, listing the Case Files whose name is not incompatible.
    Aadhaar is never used. today (date or yyyy-mm-dd) only turns a DOB into an age."""
    today = date.fromisoformat(today) if isinstance(today, str) else (today or date.today())
    idt = identity or {}
    nm = idt.get("name")
    name = (nm.get("value") if isinstance(nm, dict) else nm) or ""
    age, sex, dob = idt.get("age"), idt.get("sex"), (idt.get("dob") or None)
    rel = _relation(idt.get("relation"))
    recs = [(p.get("case_id"), patient_record(p.get("patient") or {}), p.get("listed")) for p in patients or []]
    items = [(it["kind"], normalise_id(it.get("value")), it.get("value")) for it in idt.get("ids") or []
             if isinstance(it, dict) and it.get("kind") in ID_KINDS and normalise_id(it.get("value"))]
    if idt.get("abha") and ("abha", normalise_id(idt["abha"])) not in {(k, v) for k, v, _ in items}:
        items.append(("abha", normalise_id(idt["abha"]), idt["abha"]))
    assess = {cid: _assess(name, age, sex, dob, rel, rec, today) for cid, rec, _ in recs}

    def res(decision, reason, case_id=None, candidates=(), matched_on=None):
        return {"decision": decision, "case_id": case_id, "candidates": list(candidates), "reason": reason, "matched_on": matched_on}

    def name_cands(exclude=()):
        out = [(cid, a) for cid, a in assess.items() if cid not in exclude and a["name"]["level"] != "incompatible" and not a["name"]["sex_conflict"]]
        out.sort(key=lambda x: (_LEVEL_RANK[x[1]["name"]["level"]], x[1]["age_fit"] is not True, str(x[0])))
        listed = {cid: lst for cid, _, lst in recs}
        return [_cand(cid, a, False, listed.get(cid)) for cid, a in out]

    # 1. ID match
    hits = {}
    for kind, nv, printed in items:
        for cid, rec, _ in recs:
            if any(_GROUP.get(k) == _GROUP[kind] and v == nv for k, v in rec["ids"]):
                hits.setdefault(cid, (kind, printed))
    listed = {cid: lst for cid, _, lst in recs}
    raw = {p.get("case_id"): p.get("patient") or {} for p in patients or []}
    if len(hits) > 1:
        return res("id_conflict", "the IDs on this record point to more than one Case File (" + ", ".join(map(str, hits)) + "): a person must decide",
                   candidates=[_cand(cid, assess[cid], True, listed.get(cid)) for cid in hits])
    if hits:
        cid, (kind, printed) = next(iter(hits.items()))
        rec, a = next(r for c, r, _ in recs if c == cid), assess[cid]
        on, shown = {"kind": kind, "value": printed}, f"{ID_DISPLAY[kind]} {printed}"
        cand = [_cand(cid, a, True, listed.get(cid))]
        if not name:
            return res("needs_matching", f"{shown} matches {cid} but no patient name could be read: a person must confirm", candidates=cand, matched_on=on)
        problems = []
        if a["name"]["level"] not in ("exact", "variant", "initials") or a["name"]["sex_conflict"]:
            problems.append(f"name differs ({name} / {rec['name']}: {a['name']['detail']})")
        if a["sex_fit"] is False:
            problems.append("sex differs")
        if a["age_fit"] is False:
            problems.append("age differs by more than 1 year")
        if a["dob_fit"] is False:
            problems.append("DOB differs")
        for k, v, p in items:  # same kind of ID printed with a different value
            own = {rv for rk, rv in rec["ids"] if rk == k}
            if own and v not in own:
                problems.append(f"{ID_DISPLAY[k]} {p} differs from the Case File")
        if problems:
            return res("id_conflict", f"{shown} matches {cid} but " + "; ".join(problems) + ": possible wrong ID", candidates=cand, matched_on=on)
        reason = f"{shown} matches {cid}; name {a['name']['level']} ({a['name']['detail']})"
        if a["rel_ok"] is False:
            reason += f". Note: relation differs ({_fmt_rel(rel)} / {_fmt_rel(rec['relation'])})"
        return res("auto_link", reason, case_id=cid, candidates=cand, matched_on=on)
    # 2. unknown IDs
    if items:
        hosp = next(((k, p) for k, _, p in items if k in OPENS_CASE_KINDS), None)
        cands = name_cands()
        if hosp:
            shown = f"{ID_DISPLAY[hosp[0]]} {hosp[1]}"
            if not name:
                return res("needs_matching", f"{shown} is on no Case File; an identifier was read but no patient name: a person must decide",
                           candidates=cands)
            fits = [cid for cid, a in assess.items() if _fits(a)]
            if fits:
                known = ", ".join(f"{cid} ({k})" if k else str(cid) for cid, k in ((c, _known_id(raw.get(c), hosp[0])) for c in fits))
                rest = [c for c in cands if c["case_id"] not in fits]
                return res("needs_matching", f"{shown} is on no Case File, but the name, age and sex fit {known}: the same patient "
                                             "registered twice, or a different person; a person must decide",
                           candidates=[_cand(cid, assess[cid], False, listed.get(cid)) for cid in fits] + rest)
            reason = f"{shown} is on no Case File: new Case File (awaiting listing)"
            if cands:
                reason += "; same or similar name on " + ", ".join(c["case_id"] for c in cands) + " with a different ID"
            return res("new_case", reason, candidates=cands, matched_on={"kind": hosp[0], "value": hosp[1]})
        shown = ", ".join(f"{ID_DISPLAY[k]} {p}" for k, _, p in items)
        return res("needs_matching", f"{shown} is on no Case File and cannot open one on its own (a Reg. No. may be one visit, an ABHA "
                                     "is portable across hospitals, an IP / OP No. is one episode): link to a patient or start a new Case File",
                   candidates=cands)
    # 3. name + age / sex
    if not name:
        return res("needs_matching", "no ID and no patient name could be read: link to a patient or start a new Case File")
    fits = [cid for cid, a in assess.items() if _fits(a) and not a["single"] and a["rel_ok"] is not False]
    if len(fits) == 1:
        cid = fits[0]
        return res("suggest", f"no ID printed; {_why(assess[cid])}: suggested link to {cid}, a person confirms", case_id=cid,
                   candidates=[_cand(cid, assess[cid], False, listed.get(cid))])
    if len(fits) > 1:
        return res("needs_matching", "no ID printed; name, age and sex fit more than one Case File (" + ", ".join(map(str, fits)) + "): a person must decide",
                   candidates=[_cand(cid, assess[cid], False, listed.get(cid)) for cid in fits])
    # 4. anything else
    cands = name_cands()
    single = len(normalise_name(name)["tokens"]) < 2
    reason = ("no ID printed and only a single name: never matched on the name alone" if single else
              "no ID printed and name, age and sex fit no Case File exactly" if cands else "no ID printed and no Case File has a compatible name")
    return res("needs_matching", reason + ": link to a patient or start a new Case File", candidates=cands)


def describe(identity: dict) -> str:
    """One plain line for the UI and the audit, e.g. 'Sunita Devi, 67 Y / F, UHID SYN-500911 (Aadhaar seen, masked)'."""
    idt = identity or {}
    nm = idt.get("name")
    parts = [((nm.get("value") if isinstance(nm, dict) else nm) or "name not read")]
    age, sex = idt.get("age"), idt.get("sex")
    if age is not None or sex:
        parts.append(" / ".join(x for x in (f"{age} Y" if age is not None else "", sex or "") if x))
    if idt.get("dob"):
        y, m, d = idt["dob"].split("-")
        parts.append(f"DOB {d}/{m}/{y}")
    parts += [f"{ID_DISPLAY.get(i['kind'], i['kind'])} {i['value']}" for i in idt.get("ids") or []]
    return ", ".join(parts) + (" (Aadhaar seen, masked)" if idt.get("aadhaar_seen") else "")
