"""Report status, signature and date detection from document text (deterministic, no model).

Calibrated on real reports (9,523 TCGA pathology reports, 4,999 MTSamples notes) and Indian report conventions:
most real reports carry no "Report status:" line. They say "FINAL DIAGNOSIS", "ADDENDUM", "Electronically signed by",
"*** End of report ***", "Verified by Dr ...", or "Sd/-". Policy (FHIR DiagnosticReport.status vocabulary):

  FINAL / AMENDED / CORRECTED   explicit positive evidence         -> counts as final
  PRELIMINARY / DRAFT / CANCELLED  explicit negative evidence       -> never counts as final
  UNSTATED                       no explicit status marker        -> does not pass the gate on its own; a clinician
                                                                      can attest "final, signed" (audited), see rules.py
"""
import re
from datetime import datetime

# ---- status markers (checked on the whole text; negative markers win over positive ones) ----------------------
_STATUS_LINE = re.compile(r"(?:report|record|document|result)\s+status\s*[:\-]\s*([A-Za-z ()/\-]{3,40})", re.I)
_NEG = [
    ("DRAFT", re.compile(r"\b(draft|unsigned)\s*/\s*(unsigned|draft)\b|\breport status\s*[:\-]\s*draft\b|^\s*draft\b|\bdraft report\b", re.I | re.M)),
    ("PRELIMINARY", re.compile(r"\b(preliminary|provisional|interim)\s+(report|result|diagnosis)\b|\breport status\s*[:\-]\s*(preliminary|provisional)\b|\bpreliminary\s*\(|\(\s*(preliminary|provisional)\s*\)", re.I)),
    ("CANCELLED", re.compile(r"\b(report|result)\s+(cancelled|canceled|withdrawn|entered in error)\b|\bcancelled report\b", re.I)),
    # a "final diagnosis" header whose content is still pending ("FINAL DIAGNOSIS: pending IHC", "Final diagnosis: to follow")
    # is explicit negative evidence; "FINAL DIAGNOSIS: Adenocarcinoma, HER2 pending" gives a diagnosis and stays FINAL
    ("PRELIMINARY", re.compile(r"\bfinal\s+(?:pathologic(?:al)?\s+)?(?:diagnosis|result)s?\s*[:\-]?[ \t]*\n?[ \t]*"
                               r"(?:(?:is|will|shall|be|being|the|report|diagnosis|result)\s+)*"
                               r"(?:pending|awaited|deferred|to\s+follow|will\s+follow|to\s+be\s+(?:issued|followed|given))\b", re.I)),
]
_POS = [
    ("CORRECTED", re.compile(r"\bcorrected (report|diagnosis|result)\b|\breport status\s*[:\-]\s*corrected\b", re.I)),
    ("AMENDED", re.compile(r"\b(amended|revised|modified) (report|diagnosis|result)\b|\baddend(um|a)\b|\breport status\s*[:\-]\s*(final\s*\(amended\)|amended)\b|\bsupplementary report\b", re.I)),
    ("FINAL", re.compile(r"\breport status\s*[:\-]\s*final\b|\bfinal\s*/\s*signed\b|\bfinal (pathologic(al)? )?(diagnosis|report|result)s?\b|\bfinal\b\s*$|"
                         r"\*{2,}\s*end of (final )?report|\bend of report\b|\bend of (final )?diagnosis\b", re.I | re.M)),
]
_SIG_NO = re.compile(r"signature\s+pending|\bunsigned\b|not\s+(yet\s+)?signed|awaiting\s+(signature|sign[- ]?out|verification)|pending\s+(signature|sign[- ]?out|verification)", re.I)
# State Medical Council / NMC / MCI codes, written in capitals (so 'pmc' or 'amc' in running text is not one)
_COUNCIL = r"(?-i:TNMC|APMC|TSMC|WBMC|TCMC|OCMC|UPMC|CGMC|MPMC|KMC|MMC|DMC|RMC|PMC|HMC|NMC|MCI|GMC|BMC|JMC|AMC|[A-Z]{2,4}MC)"
_COUNCIL_NAMED = r"(?-i:TNMC|APMC|TSMC|WBMC|TCMC|OCMC|UPMC|CGMC|MPMC|KMC|MMC|DMC|RMC|PMC|HMC|NMC|MCI)"  # the plan's list, for the bare form
_SIG_YES = re.compile(
    r"electronically signed|digitally signed|e-?signed|\bsigned\s*(out\s*)?(by|:|on)\b|\(signed\)|\bsd/-|\(sd\.?\)|\bsd\.\s*-|"
    r"\b(verified|authenticated|validated|approved|released|authori[sz]ed|reported|dictated|checked(?: and verified)?)\s+by\b|"
    # a registration number needs a digit: the blank form label 'Registration No. with State Code' is not a signature
    r"\bauthori[sz]ed signatory\b|\breg(n|istration)?\.?\s*no\.?\s*[:#]?\s*(?=[A-Z0-9/-]*\d)[A-Z0-9/-]{4,}|"
    # medical council registration (V1 item 3.5): 'Reg. No. KMC 45678', 'Reg No: TNMC/12345', 'KMC Reg. No. 45678', 'MCI 12345', 'NMC Reg 123456';
    # a council code right after 'UHID:', 'Sample No.', 'MRN' etc. is an identifier, not a signature
    rf"\breg(n|istration)?\.?\s*(no\.?)?\s*[:#]?\s*\(?{_COUNCIL}\)?\s*[:#/.-]?\s*\d{{3,}}|"
    rf"\b{_COUNCIL_NAMED}\s*[/(]?\s*reg(n|istration)?\.?\s*(no\.?)?\s*[:#/.-]?\s*\d{{4,}}|"
    # a bare council code + number counts only on a doctor's line (Dr., a qualification or a Reg keyword before it): hospital
    # abbreviations (KMC, GMC, MMC) also prefix IP, lab and accession numbers, which are identifiers, not signatures
    rf"(?:\bdr\.?\s|\bprof\.?\s|\b(?:MBBS|MD|MS|DNB|DM|MCh|FRCR|FRCPath|DMRD|DMRE|MRCP|FRCS|PhD)\b|\breg(?:n|istration)?\b)[^\n]{{0,80}}?"
    rf"(?<![:#])(?<![:#]\s)(?<!\bno\.\s)(?<!\bno\s)(?<!\bno\.)(?<!id\s)(?<!mrn\s)\b{_COUNCIL_NAMED}\s*[/(]?\s*(reg(n|istration)?\.?)?\s*(no\.?)?\s*[:#/.-]?\s*\d{{4,}}", re.I)
_SIGNER_LINE = re.compile(r"^.*\b(reported|signed|verified|checked|authenticated|validated|approved|authori[sz]ed|recorded|dictated|released)\s+(and verified\s+)?by\b.*$|^.*\bsd/-.*$|^\s*(dr\.?|prof\.?)\s+[A-Z][A-Za-z.\- ]{2,60}(,|\s)\s*(M\.?D\.?|MBBS|DNB|MS|MCh|DM|FRCR|FRCPath|Consultant)[^\n]{0,80}$",
                          re.I | re.M)
_DRAFT_ANYWHERE = re.compile(r"\bdraft\b", re.I)


def _snippet(text, m, pad=40):
    s, e = max(0, m.start() - pad), min(len(text), m.end() + pad)
    return " ".join(text[s:e].split())


def detect_status(text: str):
    """Returns (status, quote, notes). status in FINAL|AMENDED|CORRECTED|PRELIMINARY|DRAFT|CANCELLED|UNSTATED."""
    notes = []
    m = _STATUS_LINE.search(text)
    if m:
        v = m.group(1).upper()
        for s in ("CORRECTED", "AMENDED", "PRELIMINARY", "PROVISIONAL", "DRAFT", "CANCELLED", "CANCELED", "FINAL"):
            if s in v:
                st = {"PROVISIONAL": "PRELIMINARY", "CANCELED": "CANCELLED"}.get(s, s)
                if st == "FINAL" and "AMEND" in v:
                    st = "AMENDED"
                return st, m.group(0).strip(), notes
    for st, rx in _NEG:
        m = rx.search(text)
        if m:
            return st, _snippet(text, m), notes
    for st, rx in _POS:
        m = rx.search(text)
        if m:
            return st, _snippet(text, m), notes
    if _DRAFT_ANYWHERE.search(text):
        notes.append("the word 'draft' appears in the text; confirm this is the final version")
    return "UNSTATED", "", notes


def detect_signature(text: str):
    """Returns (signed: yes|no|unknown, signature_line_or_empty)."""
    if _SIG_NO.search(text):
        m = _SIG_NO.search(text)
        return "no", _snippet(text, m, 30)
    line = ""
    m = _SIGNER_LINE.search(text)
    if m:
        line = m.group(0).strip()
    if _SIG_YES.search(text):
        return "yes", line or _snippet(text, _SIG_YES.search(text), 30)
    return "unknown", line


# ---- dates ------------------------------------------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
# month names only (not any word): "Age 62 Years 02/09/2026" must not read "62 Years 02" as a date and swallow the real one
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![a-z])"
_DATE_RX = re.compile(
    rf"(?<!\d)(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?[\s./-]+(?P<mon>{_MON})\.?[\s,./-]+(?P<y1>\d{{4}}|\d{{2}})(?!\d)"  # 29 Sep 2026, 29-Sept-26, 29.Sep.2026
    rf"|\b(?P<mon2>{_MON})\.?\s+(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y2>\d{{4}})(?!\d)"                 # Sep 29, 2026
    r"|(?<!\d)(?P<y3>\d{4})[-/.](?P<m3>\d{1,2})[-/.](?P<d3>\d{1,2})(?!\d)"                                  # 2026-09-29
    r"|(?<!\d)(?P<d4>\d{1,2})[-/.](?P<m4>\d{1,2})[-/.](?P<y4>\d{4}|\d{2})(?!\d)", re.I)                     # 29/09/2026, 29-09-26 (India: day first)


def match_iso(m, years=(1990, 2100)) -> str:
    """ISO date of one _DATE_RX match; '' if impossible (31/02) or outside the year window. Numeric dates are day first
    (Indian convention) unless the second number cannot be a month (02/13/2026 is read month first)."""
    try:
        if m.group("d1"):
            mon = _MONTHS.get(m.group("mon")[:3].lower()); d, y = int(m.group("d1")), int(m.group("y1"))
        elif m.group("mon2"):
            mon = _MONTHS.get(m.group("mon2")[:3].lower()); d, y = int(m.group("d2")), int(m.group("y2"))
        elif m.group("y3"):
            y, mon, d = int(m.group("y3")), int(m.group("m3")), int(m.group("d3"))
        else:
            d, mon, y = int(m.group("d4")), int(m.group("m4")), int(m.group("y4"))
            if mon > 12 and d <= 12:  # clearly month-first
                d, mon = mon, d
        if not mon:
            return ""
        if y < 100:
            y += 2000 if y < 70 else 1900
        dt = datetime(y, mon, d)
    except (ValueError, TypeError):
        return ""
    return dt.date().isoformat() if years[0] <= dt.year <= years[1] else ""


def parse_date(s: str) -> str:
    """ISO date from the first recognisable date in s; '' if none. Day-first for numeric dates (Indian convention)."""
    for m in _DATE_RX.finditer((s or "").strip()):
        iso = match_iso(m)
        if iso:
            return iso
    return ""


def find_dates(text: str, limit=6):
    """Every distinct ISO date in text, in order (at most limit). No labels: see dates.document_dates for that."""
    out = []
    for m in _DATE_RX.finditer(text or ""):
        iso = match_iso(m)
        if iso and iso not in out:
            out.append(iso)
        if len(out) >= limit:
            break
    return out
