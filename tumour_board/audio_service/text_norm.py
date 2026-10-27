"""Text handling of the audio service, all pure and deterministic.

- normalise_for_speech: the clinical normaliser in front of the TTS (units, decimals, thousands, DD/MM/YYYY dates, staging strings,
  abbreviations). The spoken form is used for the audio only; the text on screen never changes.
- LEXICON: phonemes (misaki's US alphabet) for words Kokoro dropped in October 2026, drug names and Indian names.
- split_for_tts: sentence chunks small enough for Kokoro's 510-phoneme limit.
- clean_transcript: the light STT clean-up (staging tokens reshaped, "per cent" to "%", "g d l" to "g/dL"). It never adds a word.
- inverse_numbers: spoken numbers to digits for Parakeet ("eleven point eight" to "11.8").
- prompt_for: the clinical Whisper prompt (no patient data)."""
from __future__ import annotations

import datetime
import re

# ---------------------------------------------------------------------------------------------------------------- numbers

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
        "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
          "December"]
_ORDINAL_IRREGULAR = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
                      "twelve": "twelfth"}


def _under_hundred(n: int) -> str:
    if n < 20:
        return ONES[n]
    t, u = divmod(n, 10)
    return TENS[t] + ("-" + ONES[u] if u else "")


def _under_thousand(n: int) -> str:
    h, r = divmod(n, 100)
    parts = []
    if h:
        parts.append(ONES[h] + " hundred")
    if r:
        if h:
            parts.append("and")
        parts.append(_under_hundred(r))
    return " ".join(parts)


def number_to_words(n: int, indian: bool = False) -> str:
    """Cardinal words, British style ("two hundred and forty-five thousand"); indian=True uses lakh and crore."""
    if n < 0:
        return "minus " + number_to_words(-n, indian)
    if n == 0:
        return "zero"
    scales = [(10 ** 7, "crore"), (10 ** 5, "lakh"), (1000, "thousand")] if indian else \
        [(10 ** 12, "trillion"), (10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")]
    parts = []
    rest = n
    for size, name in scales:
        q, rest = divmod(rest, size)
        if q:
            parts.append(number_to_words(q, indian) + " " + name if q >= 1000 else _under_thousand(q) + " " + name)
    if rest:
        if parts and rest < 100:
            parts.append("and")
        parts.append(_under_thousand(rest))
    return " ".join(parts)


def ordinal_words(n: int) -> str:
    words = number_to_words(n)
    head, sep, last = words.rpartition(" ")
    pre, dash, tail = last.rpartition("-")
    if tail in _ORDINAL_IRREGULAR:
        tail = _ORDINAL_IRREGULAR[tail]
    elif tail.endswith("y"):
        tail = tail[:-1] + "ieth"
    else:
        tail = tail + "th"
    return head + sep + pre + dash + tail


def year_words(y: int) -> str:
    if 2000 <= y <= 2009:
        return "two thousand" + (" and " + ONES[y - 2000] if y > 2000 else "")
    if 1100 <= y <= 2099:
        hi, lo = divmod(y, 100)
        if lo == 0:
            return _under_hundred(hi) + " hundred"
        return _under_hundred(hi) + (" oh " + ONES[lo] if lo < 10 else " " + _under_hundred(lo))
    return number_to_words(y)


def decimal_words(text: str) -> str:
    """'11.8' to 'eleven point eight', '245,000' to 'two hundred and forty-five thousand', '2,45,000' in lakh."""
    whole, _, frac = text.partition(".")
    indian = bool(re.fullmatch(r"\d{1,2}(?:,\d{2})+,\d{3}", whole))
    words = number_to_words(int(whole.replace(",", "")), indian=indian)
    if frac:
        words += " point " + " ".join(ONES[int(d)] for d in frac)
    return words


# ---------------------------------------------------------------------------------------------------------- TTS normaliser

_DATE = re.compile(r"(?<![\d/.\-])(\d{1,2})([/.\-])(\d{1,2})\2((?:19|20)\d{2})(?![\d/.\-]|\.\d)")

_PRE = r"(?:yp|yc|mr|r|c|p|a|y|u)"
_TNM_TOKEN = _PRE + r"?(?:T(?:is|x|[0-4](?:[a-d]\d?)?(?:mi)?)|N(?:x|[0-3][a-c]?(?:mi)?)|M(?:x|[01][a-d]?))"
_TNM_RUN = re.compile(r"(?<![A-Za-z0-9])" + _TNM_TOKEN + r"(?:\s+" + _TNM_TOKEN + r")*(?![A-Za-z0-9])")
_TNM_GLUED = re.compile(r"(?<![A-Za-z0-9])(" + _PRE + r"?T(?:is|x|[0-4][a-d]?))(N(?:x|[0-3][a-c]?))(M(?:x|[01][a-d]?))?"
                        r"(?![A-Za-z0-9])")
_TNM_PARTS = re.compile(r"(" + _PRE + r"?)([TNM])(.*)")

# Whole-word replacements, longest first.
ABBREVIATIONS = [
    ("PET-CT", "pet C T"), ("PET/CT", "pet C T"), ("PD-L1", "P D L 1"), ("PM-JAY", "P M jay"), ("SUVmax", "S U V max"),
    ("ECOG", "E C O G"), ("HER2", "H E R 2"), ("UHID", "U H I D"), ("ICMR", "I C M R"), ("HPE", "H P E"), ("IHC", "I H C"),
    ("MRI", "M R I"), ("TPS", "T P S"), ("NCG", "N C G"), ("MDT", "M D T"), ("CT", "C T"),
]
_ABBR = [(re.compile(r"(?<![A-Za-z0-9])" + re.escape(a) + r"(?![A-Za-z0-9])"), b) for a, b in ABBREVIATIONS]
_RECEPTOR = re.compile(r"(?<![A-Za-z0-9])(ER|PR)(?![A-Za-z0-9])(?=(?:\s*(?:/|,|and)\s*(?:ER|PR|HER2))*\s*"
                       r"(?:positive|negative|equivocal|status|\+|-))")
_RECEPTOR_SIGN = re.compile(r"(?<![A-Za-z0-9])(ER|PR|HER2)\s?([+\-])(?![\w+\-])")

UNITS = {  # symbol: (singular, plural)
    "g": ("gram", "grams"), "mg": ("milligram", "milligrams"), "mcg": ("microgram", "micrograms"),
    "µg": ("microgram", "micrograms"), "μg": ("microgram", "micrograms"), "ug": ("microgram", "micrograms"),
    "ng": ("nanogram", "nanograms"), "kg": ("kilogram", "kilograms"), "mL": ("millilitre", "millilitres"),
    "ml": ("millilitre", "millilitres"), "dL": ("decilitre", "decilitres"), "dl": ("decilitre", "decilitres"),
    "L": ("litre", "litres"), "µL": ("microlitre", "microlitres"), "μL": ("microlitre", "microlitres"),
    "uL": ("microlitre", "microlitres"), "mcL": ("microlitre", "microlitres"), "cm": ("centimetre", "centimetres"),
    "mm": ("millimetre", "millimetres"), "mmol": ("millimole", "millimoles"), "U": ("unit", "units"),
    "IU": ("international unit", "international units"), "Gy": ("gray", "gray"), "cGy": ("centigray", "centigray"),
    "m2": ("square metre", "square metres"), "m²": ("square metre", "square metres"),
}
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
_NUM = r"(?<![\w.,/])\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|(?<![\w.,/])\d+(?:\.\d+)?"
_END = r"(?![A-Za-z0-9µμ²])"
_NUM_UNIT = re.compile(r"(?P<num>" + _NUM + r")\s?(?P<u1>" + _UNIT_ALT + r")(?:\s?/\s?(?P<u2>" + _UNIT_ALT + r"))?" + _END)
_NUM_PER = re.compile(r"(?P<num>" + _NUM + r")\s?/\s?(?P<u2>" + _UNIT_ALT + r")" + _END)
_BARE_RATIO = re.compile(r"(?<![A-Za-z0-9/])(?P<u1>" + _UNIT_ALT + r")/(?P<u2>" + _UNIT_ALT + r")" + _END)
_PER_UNIT = re.compile(r"(?<![A-Za-z0-9])per\s+(?P<u>" + _UNIT_ALT + r")" + _END)
_BARE_UNIT = re.compile(r"(?<![A-Za-z0-9/])(?P<u>mg|mcg|µg|μg|mL|dL|µL|μL|mcL|mmol)" + _END)
_COMMA_NUM = re.compile(r"(?<![\w.,/])\d{1,3}(?:,\d{2,3})+(?:\.\d+)?(?![\w,]|\.\d)")
_DECIMAL = re.compile(r"(?<![\w.,/])\d+\.\d+(?![\w]|\.\d)")


def _spell_tnm_token(tok: str) -> str:
    m = _TNM_PARTS.fullmatch(tok)
    pre, cat, val = m.group(1), m.group(2), m.group(3)
    pieces = list(pre) + [cat]
    if val == "is":
        pieces.append("is")
    else:
        pieces.extend(re.findall(r"mi|\d|[a-z]", val))
    return " ".join(pieces)


def spell_staging(text: str) -> str:
    """'mrT3b N1' to 'm r T 3 b, N 1'; 'cT3 N2 M0' to 'c T 3, N 2, M 0'; 'T3N2M0' to 'T 3, N 2, M 0'."""
    text = _TNM_GLUED.sub(lambda m: " ".join(g for g in m.groups() if g), text)
    return _TNM_RUN.sub(lambda m: ", ".join(_spell_tnm_token(t) for t in m.group(0).split()), text)


def _date(m: re.Match) -> str:
    day, month, year = int(m.group(1)), int(m.group(3)), int(m.group(4))
    try:
        datetime.date(year, month, day)
    except ValueError:
        return m.group(0)  # not a real date: left as written
    return f"{ordinal_words(day)} of {MONTHS[month - 1]}, {year_words(year)}"


def _unit_words(num: str | None, u1: str | None, u2: str | None) -> str:
    one = num is not None and num == "1"
    out = []
    if num is not None:
        out.append(num)
    if u1:
        out.append(UNITS[u1][0] if one else UNITS[u1][1])
    if u2:
        out.append("per " + UNITS[u2][0])
    return " ".join(out)


def normalise_for_speech(text: str) -> str:
    """The spoken form of a clinical sentence. Deterministic; used for the audio only."""
    s = text.replace("\u2013", "-").replace("\u2014", ", ")
    s = _DATE.sub(_date, s)
    s = spell_staging(s)
    s = _RECEPTOR_SIGN.sub(lambda m: m.group(1) + (" positive" if m.group(2) == "+" else " negative"), s)
    s = _RECEPTOR.sub(lambda m: " ".join(m.group(1)), s)
    s = re.sub(r"\b(E R|P R)\s*/\s*(?=E R|P R|HER2)", r"\1, ", s)
    for pat, rep in _ABBR:
        s = pat.sub(rep, s)
    s = re.sub(r"(?<![A-Za-z])Reg\.?\s*No\.?(?=\s*:?\s*\S)", "registration number", s)
    s = re.sub(r"(?<![A-Za-z])Reg\.(?=\s|$)", "registration", s)
    s = re.sub(r"(?<![A-Za-z])No\.(?=\s*:?\s*\d)", "number", s)
    s = re.sub(r"(?<![A-Za-z])Dr\.?(?=\s+[A-Z])", "Doctor", s)
    s = re.sub(r"(\d)\s?[x×]\s?(\d)", r"\1 by \2", s)
    s = re.sub(r"(\d)\+", r"\1 plus", s)
    s = _NUM_UNIT.sub(lambda m: _unit_words(m.group("num"), m.group("u1"), m.group("u2")), s)
    s = _NUM_PER.sub(lambda m: _unit_words(m.group("num"), None, m.group("u2")), s)
    s = _BARE_RATIO.sub(lambda m: _unit_words(None, m.group("u1"), m.group("u2")), s)
    s = _PER_UNIT.sub(lambda m: "per " + UNITS[m.group("u")][0], s)
    s = _BARE_UNIT.sub(lambda m: UNITS[m.group("u")][1], s)
    s = re.sub(r"\s?%", " percent", s)
    s = _COMMA_NUM.sub(lambda m: decimal_words(m.group(0)), s)
    s = _DECIMAL.sub(lambda m: decimal_words(m.group(0)), s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" ([,.;:])", r"\1", s)
    return s.strip()


# Phonemes in misaki's US alphabet (flap written as the gold lexicon writes it). Built from the espeak-ng reading of each word
# and checked by ear; the city names copy misaki's own gold entries.
LEXICON = {
    "mg": "mˈɪləɡɹˌæmz", "milligrams": "mˈɪləɡɹˌæmz", "milligram": "mˈɪləɡɹˌæm",
    "SUVmax": "ˌɛsjˌuvˌimˈæks", "Reg": "ɹˌɛʤəstɹˈAʃən", "Kavita": "kˈævɪtə",
    "decilitre": "dˈɛsəlˌiɾəɹ", "decilitres": "dˈɛsəlˌiɾəɹz", "microlitre": "mˈIkɹOlˌiɾəɹ", "microlitres": "mˈIkɹOlˌiɾəɹz",
    "millilitre": "mˈɪləlˌiɾəɹ", "millilitres": "mˈɪləlˌiɾəɹz", "centimetre": "sˈɛntəmˌiɾəɹ",
    "centimetres": "sˈɛntəmˌiɾəɹz", "millimetre": "mˈɪləmˌiɾəɹ", "millimetres": "mˈɪləmˌiɾəɹz",
    "immunohistochemistry": "ˌɪmjənOhˌɪstOkˈɛmɪstɹi",
    "capecitabine": "kˌApsˈItəbˌin", "oxaliplatin": "ɑksˈæləplˌætɪn", "trastuzumab": "tɹæstˈuzumˌæb",
    "pembrolizumab": "pˌɛmbɹOlˈɪzumˌæb", "osimertinib": "ˌOsɪmˈɜɹtɪnˌɪb", "letrozole": "lˈɛtɹəzˌOl",
    "tamoxifen": "təmˈɑksəfən", "paclitaxel": "pˌæklɪtˈæksᵊl", "docetaxel": "dˌOsətˈæksᵊl",
    "carboplatin": "kˈɑɹbOplˌætɪn", "bevacizumab": "bˌɛvəsˈɪzumˌæb", "temozolomide": "tˌɛmOzˈOləmˌId",
    "imatinib": "ɪmˈæɾɪnˌɪb",
    "Venkatesh": "vˌɛŋkətˈAʃ", "Priya": "pɹˈijə", "Thiruvananthapuram": "tˌɪɹuwˌʌnəntəpˈʊɹəm",
    "Visakhapatnam": "vɪʃˌɑkəpˈʌtnəm", "Bengaluru": "bˈɛŋɡələɹˌu", "Guwahati": "ɡˌWhˈɑɾi",
    "Bhubaneswar": "bˌʊvənˈAʃwəɹ", "Coimbatore": "kˌYmbətˈʊɹ", "Kathua": "kˈʌθuə", "Rajouri": "ɹəʤˈWɹi",
    "Poonch": "pˈunʧ",
}


def split_for_tts(text: str, max_chars: int = 300) -> list[str]:
    """Chunks at line breaks and sentence ends; a longer sentence is cut at commas, then at spaces. Each chunk has at most
    max_chars characters, which keeps Kokoro under 510 phonemes per call."""
    chunks: list[str] = []
    for para in re.split(r"\n+", text):
        for sent in re.split(r"(?<=[.!?;])\s+", para.strip()):
            sent = sent.strip()
            if not sent:
                continue
            if len(sent) <= max_chars:
                chunks.append(sent)
                continue
            cur = ""
            for piece in re.split(r"(?<=,)\s+|\s+", sent):
                while len(piece) > max_chars:
                    if cur:
                        chunks.append(cur)
                        cur = ""
                    chunks.append(piece[:max_chars])
                    piece = piece[max_chars:]
                if cur and len(cur) + 1 + len(piece) > max_chars:
                    chunks.append(cur)
                    cur = piece
                else:
                    cur = (cur + " " + piece).strip()
            if cur:
                chunks.append(cur)
    return chunks


# ---------------------------------------------------------------------------------------------------------- STT clean-up

_STT_TNM = re.compile(
    r"(?<![A-Za-z0-9])(?P<pre>y\s?p|y\s?c|m\s?r|c|p|r)?\s?t\s?(?P<t>is|x|[0-4])\s?(?P<ts>[a-d](?![a-mo-z]))?"
    r",?\s?n\s?(?P<n>x|[0-3])\s?(?P<ns>[a-c](?![a-ln-z]))?(?:\s?m\s?(?P<m>x|[01])(?![0-9]))?(?![A-Za-z0-9])", re.I)


_STT_T_ALONE = re.compile(r"(?<![A-Za-z0-9])(?P<pre>yp|yc|mr|c|p|r)t(?P<t>is|[0-4])(?P<ts>[a-d])?(?![A-Za-z0-9])", re.I)  # no "x": CTx and RTx are treatments


def _stt_tnm(m: re.Match) -> str:
    pre = re.sub(r"\s", "", m.group("pre") or "").lower()
    out = pre + "T" + m.group("t").lower() + (m.group("ts") or "").lower()
    out += " N" + m.group("n").lower() + (m.group("ns") or "").lower()
    if m.group("m"):
        out += " M" + m.group("m").lower()
    return out


_STT_SPOKEN_DATE = re.compile(r"(?<![A-Za-z0-9/])(\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?\s+(" + "|".join(MONTHS) + r")\.?,?\s+((?:19|20)\d{2})(?![0-9/])")
# month names as the engine writes them (capitalised): "Group 3 may 2026" is not a date
_STT_ECOG = re.compile(r"(?<![A-Za-z0-9])EC\s?OG\s?(\d)?(?![A-Za-z0-9])", re.I)
_STT_PMJAY = re.compile(r"(?<![A-Za-z0-9])(?:PM\s?-?\s?JAY|(?-i:PMJ))(?![A-Za-z0-9])", re.I)  # "PMJ" only in capitals; "4 pm J Kumar" stays
_STT_G_PER_DL = re.compile(r"(?<![A-Za-z])(?P<milli>milli|m)?(?:g|grams?)\s+per\s+(?:deci|d)\s?(?:litre|liter|l)(?![A-Za-z])", re.I)
_STT_HYPHEN_DATE = re.compile(r"(?<![\d/.\-])(\d{1,2})-(\d{1,2})-((?:19|20)\d{2})(?![\d/.\-])")
# no rule for glued digits ("2410-2026"): a registration number such as 0412-2026 would become a date
_STT_HER2_SCORE = re.compile(r"(?<![A-Za-z0-9])HER2\s?([0-3])\s?\+?plus(?![A-Za-z0-9])", re.I)
_STT_PDL1 = re.compile(r"(?<![A-Za-z0-9])PD\s?-?\s?L\s?1\s?(TPS)?(?![A-Za-z0-9])", re.I)


def _real_date(day: int, month: int, year: int) -> bool:
    import datetime
    try:
        datetime.date(year, month, day)
    except ValueError:
        return False
    return True


def _stt_date(m) -> str:
    day = int(m.group(1))
    month = MONTHS.index(m.group(2)) + 1
    if not _real_date(day, month, int(m.group(3))):  # "31 February 2026" stays as heard
        return m.group(0)
    return f"{day:02d}/{month:02d}/{m.group(3)}"


def _stt_numeric_date(m) -> str:
    """"4-11-2026" (the engine's separators) to 04/11/2026 when it is a real date; else as heard."""
    day, month = int(m.group(1)), int(m.group(2))
    if not _real_date(day, month, int(m.group(3))):
        return m.group(0)
    return f"{day:02d}/{month:02d}/{m.group(3)}"


def clean_transcript(text: str) -> str:
    """Reshape tokens only: staging written run together or spaced, "ECOG1" or "EC OG 1" to "ECOG 1", "PMJ" or "PMJAY" to
    "PM-JAY", "per cent" to "%", "g d l" or "grams per decilitre" to "g/dL", a spoken date ("14th of September, 2026") to the
    house format 14/09/2026. Never adds a word or a value; spelling stays as spoken and the engine's digits are kept."""
    s = _STT_TNM.sub(_stt_tnm, text)
    s = _STT_T_ALONE.sub(lambda m: m.group("pre").lower() + "T" + m.group("t").lower() + (m.group("ts") or "").lower(), s)
    s = re.sub(r"(?<![A-Za-z0-9])(ECOG)(\d)(?![0-9])", r"\1 \2", s, flags=re.I)  # "ECOG1" to "ECOG 1"
    s = _STT_ECOG.sub(lambda m: "ECOG" + (" " + m.group(1) if m.group(1) else ""), s)
    s = _STT_PMJAY.sub("PM-JAY", s)
    s = re.sub(r"(\d)\s*(?:per\s?cent)\b", r"\1%", s, flags=re.I)
    s = _STT_G_PER_DL.sub(lambda m: ("mg" if m.group("milli") else "g") + "/dL", s)
    s = re.sub(r"(?<![A-Za-z])(m?g)\s?/?\s?d\s?l(?![A-Za-z])", lambda m: m.group(1).lower() + "/dL", s, flags=re.I)
    s = _STT_SPOKEN_DATE.sub(_stt_date, s)
    s = _STT_HYPHEN_DATE.sub(_stt_numeric_date, s)
    s = _STT_HER2_SCORE.sub(lambda m: "HER2 " + m.group(1) + "+", s)
    s = _STT_PDL1.sub(lambda m: "PD-L1" + (" TPS" if m.group(1) else ""), s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def is_repetitive(text: str) -> bool:
    """True when the text holds one 3-gram repeated four times in a row (a decoding loop)."""
    words = re.findall(r"[\w'%/.]+", text.lower())
    for n in (1, 2, 3):
        for i in range(0, len(words) - 4 * n + 1):
            gram = words[i:i + n]
            if all(words[i + k * n:i + (k + 1) * n] == gram for k in range(1, 4)):
                return True
    return False


# ------------------------------------------------------------------------------------- inverse numbers (Parakeet output)

_SMALL = {w: i for i, w in enumerate(ONES)}
_TENS = {w: i * 10 for i, w in enumerate(TENS) if w}
_SCALES = {"thousand": 1000, "lakh": 10 ** 5, "lakhs": 10 ** 5, "million": 10 ** 6, "crore": 10 ** 7, "crores": 10 ** 7}
_NUMBER_WORD = "|".join(sorted(list(_SMALL) + list(_TENS) + list(_SCALES) + ["hundred", "point"], key=len, reverse=True))
_NUMBER_RUN = re.compile(r"(?<![A-Za-z])(?:" + _NUMBER_WORD + r")(?:(?:\s+|-)(?:and\s+)?(?:" + _NUMBER_WORD + r"))*"
                         r"(?![A-Za-z])", re.I)


def _fmt(n: int) -> str:
    return f"{n:,}" if n >= 10000 else str(n)


def _parse_int(words: list[str]) -> tuple[int | None, int]:
    """Parse the longest valid integer prefix. Returns (value, words used)."""
    total = current = 0
    last = None
    used = 0
    for w in words:
        if w in _SMALL:
            v = _SMALL[w]
            if last == "small" or (last == "tens" and v >= 10) or (last == "tens" and v == 0):
                break
            current += v
            last = "done" if last == "tens" else "small"  # "twenty six" is complete: no "hundred" may follow
        elif w in _TENS:
            if last in ("small", "tens", "done"):
                break
            current += _TENS[w]
            last = "tens"
        elif w == "hundred":
            if last != "small":
                break
            current *= 100
            last = "hundred"
        elif w in _SCALES:
            if last is None or last == "scale":
                break
            total += (current or 1) * _SCALES[w]
            current = 0
            last = "scale"
        else:
            break
        used += 1
    if used == 0:
        return None, 0
    return total + current, used


def _parse_run(words: list[str]) -> str:
    if not words:
        return ""
    if words == ["one"] or words[0] == "point":
        return " ".join(words[:1]) + (" " + _parse_run(words[1:]) if len(words) > 1 else "")
    if len(words) >= 2 and words[0] in ("nineteen", "twenty"):  # a year said as "twenty twenty-six"
        v, used = _parse_int(words[1:])
        if v is not None and 10 <= v <= 99 and used == len(words) - 1 and "hundred" not in words[1:]:
            return str((2000 if words[0] == "twenty" else 1900) + v)
    value, used = _parse_int(words)
    if value is None:
        return words[0] + (" " + _parse_run(words[1:]) if len(words) > 1 else "")
    out = _fmt(value)
    rest = words[used:]
    if rest and rest[0] == "point":
        digits = []
        for w in rest[1:]:
            if w in _SMALL and _SMALL[w] < 10:
                digits.append(str(_SMALL[w]))
            else:
                break
        if digits:
            out = str(value) + "." + "".join(digits)
            rest = rest[1 + len(digits):]
    return out + (" " + _parse_run(rest) if rest else "")


def inverse_numbers(text: str) -> str:
    """Spoken numbers to digits: 'eleven point eight' to '11.8', 'two hundred forty five thousand' to '245,000'.
    A lone 'one' stays a word."""
    def repl(m: re.Match) -> str:
        words = [w for w in re.split(r"[\s\-]+", m.group(0).lower()) if w and w != "and"]
        return _parse_run(words)
    return _NUMBER_RUN.sub(repl, text)


# ---------------------------------------------------------------------------------------------------------- the prompt

# Under 80 Whisper tokens with any context line (69 to 76, measured with the model's tokenizer). Vocabulary only.
CLINICAL_PROMPT = ("Tumour board. Haemoglobin 11.8 g/dL, platelets 245,000, cT3 N2 M0, mrT3b N1, HER2, PM-JAY, SUVmax. "
                   "Capecitabine, oxaliplatin, trastuzumab.")
_CONTEXT_LEAD = {
    "question": "A question for the board.",
    "decision": "Board decision, Responsible Department.",
    "note": "",
    "reason": "The reason for the change.",
}
CONTEXTS = tuple(_CONTEXT_LEAD)


def prompt_for(context: str | None) -> str:
    """The Whisper initial prompt for a context (question, decision, note, reason). Vocabulary only, never patient data."""
    lead = _CONTEXT_LEAD.get(context or "note", "")
    return (CLINICAL_PROMPT + " " + lead).strip()
