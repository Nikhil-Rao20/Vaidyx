"""Indian units and report conventions (V1 item 3.5).

Unit equivalents (lakhs/cumm = x100,000 per µL, gm% = g/dL, cumm = µL, TLC = WBC, ...) from protocols/units.json, used ONLY when
comparing numbers: the Q&A / summary number guard and post-board adjudication. The value shown to the reader is always the value as
written; nothing here rewrites a value.

Rules (conservative: a conversion may let a correctly restated number pass, never a different one):
- a number that appears as is in the other text matches (today's rule, compared as numbers so '7.20' = '7.2');
- a number with a unit matches a quoted quantity of the same family once both are in the base unit ('245000/µL' = '2.45 lakhs/cumm',
  '60 mm' = '6 cm', but '60 cm' != '6 cm'); exact conversions allow float noise only, rounded analyte conversions (creatinine
  mg/dL vs µmol/L) allow 2 % and need the analyte label next to the number;
- a number with an analyte label but no unit ('WBC 7.2') matches a quoted quantity of the same analyte expressed in one of that
  analyte's customary units ('TLC 7,200/cumm' is 7.2 x10^3/µL); a bare number with neither unit nor label only matches as is.
"""
import json
import re
from decimal import Decimal
from functools import lru_cache

from . import config, grounding

EXACT_TOL = 1e-9  # exact conversions: float noise only (11.85 g/dL is not 11.8 g/dL)
ALLOW_INEXACT = False  # rounded analyte conversions (creatinine, bilirubin, glucose) never make two numbers equal unless a caller passes tol
INEXACT_TOL = 0.02  # rounded analyte conversions (88.4, 17.1, 18.0)

_SUP = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-"}
_SUP_CLASS = "[" + "".join(_SUP) + "]"
# Indian grouping (2,45,000), western grouping (245,000) or plain digits, optional decimals; not inside another number
NUMBER = re.compile(r"(?<![\d.])(?<!\d,)(?:\d{1,3}(?:,\d{2})+,\d{3}|\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d)")
_EXP = re.compile(r"[ \t]*(?:[x×*][ \t]*)?10[ \t]*(?:(?:\^|\*\*)[ \t]*(-?\d{1,2})|(" + _SUP_CLASS + r"{1,3}))")
_DIM = re.compile(r"[ \t]*(?:[x×*]|by)[ \t]*(?=\d)", re.I)
_GAP = re.compile(r"[ \t]*")
_BARE_EXP = re.compile(r"10[ \t]*(?:(?:\^|\*\*)[ \t]*-?\d{1,2}|" + _SUP_CLASS + r"{1,3})")  # a column header 'x10^3/uL' with no number before it


@lru_cache(maxsize=1)
def table():
    return json.loads((config.PROTOCOL_DIR / "units.json").read_text())


def _rx(spelling):
    """Tolerant regex for one unit or label spelling: any case, spaces optional, 'µ' = µ/μ/u/mc, '^3' = ^3/**3/3/³."""
    out, i = [], 0
    while i < len(spelling):
        ch = spelling[i]
        if ch == "^":
            exp = re.match(r"-?\d+", spelling[i + 1:]).group(0)
            sup = "".join(k for d in exp for k, v in _SUP.items() if v == d)
            out.append(rf"(?:(?:\^|\*\*)?\s*{re.escape(exp)}|{re.escape(sup)})")
            i += 1 + len(exp)
            continue
        if ch == "x" and i == 0 and spelling[1:3] == "10":
            out.append(r"(?:[x×*]\s*)?")
        elif ch == " ":
            out.append(r"[\s.]*")
        elif ch == ".":
            out.append(r"\.?\s*")
        elif ch == "/":
            out.append(r"\s*/\s*")
        elif ch == "µ":
            out.append(r"(?:µ|μ|u|mc)")
        else:
            out.append(re.escape(ch))
        i += 1
    return "".join(out)


@lru_cache(maxsize=1)
def _units():
    """[(compiled regex, spelling, family, factor, exact)], longest spelling first; and {normalised spelling: (family, factor)}."""
    rows, index = [], {}
    for fam, f in table()["families"].items():
        for sp, factor in f["units"].items():
            rows.append((re.compile(_rx(sp) + r"(?![A-Za-zµμ])", re.I), sp, fam, float(factor), bool(f.get("exact", True))))
            index[_key(sp)] = (fam, float(factor))
    rows.sort(key=lambda r: -len(r[1]))
    return rows, index


def _key(spelling):
    return re.sub(r"[\s.]", "", spelling).lower().replace("μ", "µ")


@lru_cache(maxsize=1)
def _labels():
    """One regex over every analyte label (longest first); group name -> analyte id."""
    pairs = sorted(((lab, aid) for aid, a in table()["analytes"].items() for lab in a["labels"]), key=lambda p: -len(p[0]))
    names, parts = {}, []
    for k, (lab, aid) in enumerate(pairs):
        names[f"l{k}"] = aid
        parts.append(f"(?P<l{k}>{_rx(lab)})")
    return re.compile(r"(?<![A-Za-z])(?:" + "|".join(parts) + r")(?![A-Za-z])", re.I), names


def _label_before(text, start, floor):
    """Analyte whose label sits just before the number (same line, after the previous number, no digits in between)."""
    lo = max(floor, text.rfind("\n", 0, start) + 1, start - 60)
    rx, names = _labels()
    last = None
    for m in rx.finditer(text, lo, start):
        last = m
    if not last:
        return None
    gap = text[last.end():start]
    if len(gap) > 25 or re.search(r"\d", gap):
        return None
    return names[last.lastgroup]


def _num(s):
    return float(s.replace(",", ""))


def _unit_at(text, pos):
    g = _GAP.match(text, pos).end()
    for rx, sp, fam, factor, exact in _units()[0]:
        m = rx.match(text, g)
        if m:
            return m, sp, fam, factor, exact
    return None


def parse_quantity(text):
    """Every number in `text` with the unit written after it (if any).
    Returns [{"value", "unit", "base", "family", "exact", "label", "start", "end"}]: value as written (2.45), unit as spelled in the
    text ('lakhs/cumm'), base = value in the family's base unit (245000 per µL), family None for a number without a known unit,
    label = analyte id when an analyte label sits just before the number ('TLC 7,200' -> 'wbc'), start/end = span in the text."""
    text = text or ""
    out, pos, prev_end = [], 0, 0
    while True:
        m = NUMBER.search(text, pos)
        if not m:
            return out
        bare = _BARE_EXP.match(text, m.start())
        if bare:  # a number before it would already have taken it as its exponent or unit
            u = _unit_at(text, bare.end())
            pos = prev_end = u[0].end() if u else bare.end()
            continue
        chain, end = [m], m.end()
        while True:  # dimensions: '5.2 x 4.1 cm' -> both in cm (but 'x 10^5' is an exponent)
            d = _DIM.match(text, end)
            if not d or _EXP.match(text, end):
                break
            n = NUMBER.match(text, d.end())
            if not n:
                break
            chain.append(n)
            end = n.end()
        mult, unit_start = 1.0, end
        u = _unit_at(text, end)
        if not u and len(chain) == 1:
            e = _EXP.match(text, end)
            if e:
                exp = e.group(1) or "".join(_SUP[c] for c in e.group(2))
                mult, end = 10.0 ** int(exp), e.end()
                u = _unit_at(text, end)
        if u:
            um, sp, fam, factor, exact = u
            end = um.end()
        else:
            fam, factor, exact = None, 1.0, True
        unit = text[unit_start:end].strip()
        label = _label_before(text, m.start(), prev_end)
        for k, n in enumerate(chain):
            v = _num(n.group(0))
            last = k == len(chain) - 1
            out.append({"value": v, "unit": unit if (last or fam) else "", "base": v * mult * factor, "family": fam, "exact": exact,
                        "label": label if k == 0 else None, "start": n.start(), "end": end if last else n.end()})
        pos = prev_end = end


def _close(x, y, tol):
    return x == y or abs(x - y) <= tol * max(abs(x), abs(y))


def _convert(base, fam_from, fam_to, analyte):
    """Base value of one family into the base of another for an analyte with a listed conversion; (value, exact) or None."""
    if fam_from == fam_to:
        return base, True
    index = _units()[1]
    for c in table()["analyte_conversions"]:
        if c["analyte"] != analyte:
            continue
        (fa, ka), (fb, kb) = index[_key(c["from_unit"])], index[_key(c["to_unit"])]
        # 1 from_unit = factor to_unit  ->  1 base_fa = factor * kb / ka base_fb
        r = float(c["factor"]) * kb / ka
        if (fa, fb) == (fam_from, fam_to):
            return base * r, bool(c.get("exact"))
        if (fb, fa) == (fam_from, fam_to):
            return base / r, bool(c.get("exact"))
    return None


def _as_quantity(q):
    if isinstance(q, dict):
        return q
    qs = parse_quantity(q)
    return qs[0] if qs else None


def same_quantity(a, b, tol=None):
    """Two quantities (dicts from parse_quantity, or strings whose first quantity is used) are the same value after conversion.
    tol None: float noise only for exact conversions, 2 % for a rounded analyte conversion. Numbers without a unit compare as
    today (equal numbers only); a number with a unit never equals a bare number here."""
    a, b = _as_quantity(a), _as_quantity(b)
    if not a or not b:
        return False
    if a["family"] is None and b["family"] is None:
        return a["base"] == b["base"]
    if a["family"] is None or b["family"] is None:
        return False
    if a.get("label") and b.get("label") and a["label"] != b["label"]:
        return False
    conv = _convert(a["base"], a["family"], b["family"], a.get("label") or b.get("label"))
    if conv is None:
        return False
    v, exact = conv
    if not (exact and a["exact"] and b["exact"]) and tol is None and not ALLOW_INEXACT:
        return False  # a rounded conversion (creatinine, bilirubin, glucose) could let a different number through: never by default
    t = EXACT_TOL if exact and a["exact"] and b["exact"] else INEXACT_TOL
    if tol is not None:
        t = tol if exact else max(tol, INEXACT_TOL)
    return _close(v, b["base"], t)


def _in_units(q, analyte):
    """q expressed in each customary unit of the analyte: [(value, exact)]."""
    index = _units()[1]
    out = []
    for sp in table()["analytes"].get(analyte, {}).get("units", []):
        fam, factor = index[_key(sp)]
        conv = _convert(q["base"], q["family"], fam, analyte)
        if conv:
            out.append((conv[0] / factor, conv[1] and q["exact"]))
    return out


def _supported(q, others):
    if q["family"]:
        return any(o["family"] and same_quantity(q, o) for o in others)
    if q.get("label"):  # 'WBC 7.2' against 'TLC 7,200/cumm'
        return any(o["family"] and o.get("label") == q["label"] and _close(q["base"], v, EXACT_TOL if ex else INEXACT_TOL)
                   for o in others for v, ex in _in_units(o, q["label"]))
    return False


def unmatched_numbers(text_a, text_b):
    """Number strings of text_a (as grounding.numbers reads them) with no match in text_b, neither as the same number nor as an
    equivalent quantity. Empty list = every number of text_a is supported by text_b."""
    plain_b = {float(n) for n in grounding.numbers(text_b)}
    qa, qb = parse_quantity(text_a), parse_quantity(text_b)
    out = []
    for m in grounding.NUM.finditer(text_a or ""):
        if float(m.group(0)) in plain_b:
            continue
        q = next((q for q in qa if q["start"] <= m.start() and m.end() <= q["end"]), None)
        if q and _supported(q, qb):
            continue
        out.append(m.group(0))
    return out


def numbers_equivalent(text_a, text_b):
    """Every number in text_a is in text_b, as the same number or as an equivalent quantity."""
    return not unmatched_numbers(text_a, text_b)


def _fmt(v):
    d = Decimal(repr(float(f"{v:.10g}"))).normalize()
    return format(d, "f")


def equivalent_numbers(text_b):
    """The plain numbers of text_b plus every quantity re-spelled in the other units of its family (and, for a labelled analyte,
    in its customary units): '2.45 lakhs/cumm' -> {'2.45', '245000', '245', ...}. Unit blind (a set of strings cannot carry the
    unit): '6 cm' gives '60' (mm). The guards use unmatched_numbers / numbers_equivalent, which keep the unit."""
    out = set(grounding.numbers(text_b))
    fams = table()["families"]
    for q in parse_quantity(text_b):
        if not q["family"]:
            continue
        for factor in set(float(f) for f in fams[q["family"]]["units"].values()):
            out.add(_fmt(q["base"] / factor))
        if q.get("label"):
            out |= {_fmt(v) for v, _ in _in_units(q, q["label"])}
    return out
