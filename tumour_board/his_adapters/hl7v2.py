"""HL7 v2.x result messages from a folder (kind "hl7v2_folder"): the common interface of an Indian LIS / RIS / HIMS when
there is no API. The hospital's interface engine (or a small relay) drops message files into a folder; Vaidyx-TB only reads it.

Read: ORU^R01 (results), MDM^T02 (documents, simple form), ORM^O01 (orders). Per message: MSH (delimiters from MSH-1 / MSH-2),
PID (PID-3 identifiers with their type codes, PID-5 name, PID-7 date of birth, PID-8 sex), PV1 (class I / O, visit number
PV1-19), ORC / OBR (placer and filler numbers, OBR-4 service, OBR-7 observation time, OBR-22 report time, OBR-25 status:
F final, C corrected, P preliminary, X cancelled), OBX (type, code, value, units, range, OBX-11; an ED value carrying a
Base64 PDF is the report document: source^type^subtype^encoding^data, and a large PDF split over consecutive ED segments
of the same set id or sub-id is joined; an RP value is only a pointer: it is recorded as "document by reference, not
fetched" and never followed), NTE. A file may hold several messages (the demo hospital's events.hl7 does).

One report per OBR; the latest message for the same filler number wins and earlier ones stay as earlier versions. A message
with no PDF is a "text only" report: its OBX lines are its text (a .txt the normal ingestion reads) and it carries no
candidate values, because a value checked against a text made from itself would prove nothing. HL7 v2 carries no signature
Vaidyx-TB can verify: `signature` is None (unknown). An MLLP network listener is out of scope (docs/his-adapters/DESIGN.md).
"""
import asyncio
import base64
import binascii
import hashlib
import re
from datetime import date, datetime
from urllib.parse import quote, unquote

from .. import his_client
from ..his_client import HISClient, HISError
from . import _common as C

KIND = "hl7v2_folder"
SUFFIXES = (".hl7", ".txt", ".dat", ".msg", ".er7")
OBR_STATUS = {"F": "final", "C": "corrected", "P": "preliminary", "X": "cancelled", "A": "partial", "R": "preliminary",
              "I": "registered", "O": "registered", "S": "registered"}
OBX_STATUS = {"F": "final", "C": "corrected", "P": "preliminary", "X": "cancelled", "D": "cancelled", "R": "preliminary", "W": "cancelled"}
TXA_STATUS = {"AU": "final", "LA": "final", "PA": "preliminary", "DI": "preliminary", "DO": "preliminary", "IP": "preliminary", "IN": "preliminary"}
UHID_TYPES = {"MR", "MRN", "PI", "PT", "UHID", "CR", "CRNO", "U"}
ABHA_TYPES = {"NH", "ABHA", "HID", "PHR"}
_SEG = re.compile(r"^[A-Z][A-Z0-9]{2}$")
_TS = re.compile(r"^(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(?:\.\d+)?([+-]\d{4})?$")


class Delims:
    def __init__(self, fs="|", enc="^~\\&"):
        enc = (enc + "^~\\&"[len(enc):])[:4] if len(enc) < 4 else enc[:4]
        self.fs, self.comp, self.rep, self.esc, self.sub = fs, enc[0], enc[1], enc[2], enc[3]


def unescape(text: str, d: Delims) -> str:
    r"""HL7 escape sequences: \F\ \S\ \T\ \R\ \E\ (the message's own delimiters), \.br\ and \X0D\ as a line break."""
    s = str(text or "")
    if d.esc not in s:
        return s
    table = {"F": d.fs, "S": d.comp, "T": d.sub, "R": d.rep, "E": d.esc, ".br": "\n", "H": "", "N": ""}
    out, i = [], 0
    while i < len(s):
        if s[i] == d.esc:
            j = s.find(d.esc, i + 1)
            if j > i:
                tok = s[i + 1:j]
                if tok in table:
                    out.append(table[tok]); i = j + 1; continue
                if tok[:1] == "X" and re.fullmatch(r"(?:[0-9A-Fa-f]{2})+", tok[1:] or "-"):
                    out.append(bytes.fromhex(tok[1:]).decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")); i = j + 1; continue
        out.append(s[i]); i += 1
    return "".join(out)


class Seg:
    """One segment. get(n, c) is component c of field n (1-based, unescaped); for MSH, field 1 is the separator itself."""
    __slots__ = ("name", "fields", "d", "raw")

    def __init__(self, line: str, d: Delims):
        parts = line.split(d.fs)
        self.name, self.d, self.raw = parts[0].strip().upper()[:3], d, line
        self.fields = ["MSH", d.fs] + parts[1:] if self.name == "MSH" else parts

    def field(self, n: int) -> str:
        return self.fields[n] if 0 <= n < len(self.fields) else ""

    def reps(self, n: int) -> list:
        f = self.field(n)
        return f.split(self.d.rep) if f else []

    def get(self, n: int, c: int = 1, rep: int = 0) -> str:
        reps = self.reps(n)
        if rep >= len(reps):
            return ""
        comps = reps[rep].split(self.d.comp)
        return unescape(comps[c - 1], self.d).strip() if c <= len(comps) else ""

    def text(self, n: int) -> str:
        return unescape(self.field(n), self.d).strip()


def ts(value: str) -> str:
    """An HL7 time (YYYYMMDD[HHMM[SS]][+ZZZZ]) as ISO: a date stays a date, a time without a zone is IST; "" when unreadable."""
    m = _TS.match(str(value or "").strip())
    if not m or not m.group(2) or not m.group(3):
        return ""
    y, mo, d, hh, mi, ss, z = m.groups()
    try:
        if hh is None:
            return date(int(y), int(mo), int(d)).isoformat()
        zone = f"{z[:3]}:{z[3:]}" if z else "+05:30"
        datetime(int(y), int(mo), int(d), int(hh), int(mi or 0), int(ss or 0))        # a real time, or ValueError
        return f"{y}-{mo}-{d}T{hh}:{mi or '00'}:{ss or '00'}{zone}"
    except ValueError:
        return ""


def split_messages(data: bytes) -> list:
    """The messages of one file as lists of segment lines. Tolerates a UTF-8 BOM, MLLP framing bytes (0x0B ... 0x1C 0x0D)
    left in the file, and \r, \n or \r\n segment ends; a line that is not a segment continues the one before it."""
    text = data.decode("utf-8-sig", "replace").replace("﻿", "").replace("\x0b", "\r").replace("\x1c", "\r")
    msgs, cur = [], None
    for line in text.replace("\r\n", "\r").replace("\n", "\r").split("\r"):
        line = line.strip(" \t")
        if not line:
            continue
        if line.startswith("MSH") and len(line) > 8 and not line[3].isalnum():
            cur = [line]; msgs.append(cur)
        elif cur is not None:
            if _SEG.match(line[:3]) and len(line) > 3 and line[3] == cur[0][3]:
                cur.append(line)
            else:
                cur[-1] += line          # a wrapped line (long Base64): part of the segment before it
    return msgs


def parse_message(lines: list) -> dict:
    """One message: {"type", "trigger", "control_id", "time", "segs", "pid", "pv1", "groups"}; a group is one order or report:
    {"orc", "obr", "txa", "obx": [...], "nte": [...]}. ValueError when the first line is not a usable MSH."""
    head = lines[0]
    if not head.startswith("MSH") or len(head) < 9:
        raise ValueError("no MSH segment")
    fs = head[3]
    d = Delims(fs, head[4:].split(fs)[0])
    segs = [Seg(x, d) for x in lines]
    msh = segs[0]
    out = {"type": msh.get(9, 1).upper(), "trigger": msh.get(9, 2).upper(), "control_id": msh.get(10), "time": ts(msh.get(7)),
           "app": msh.get(3), "facility": msh.get(4), "pid": None, "pv1": None, "groups": [], "d": d}
    pending_orc, cur = None, None
    for s in segs[1:]:
        if s.name == "PID" and out["pid"] is None:
            out["pid"] = s
        elif s.name == "PV1" and out["pv1"] is None:
            out["pv1"] = s
        elif s.name == "ORC":
            pending_orc, cur = s, None
        elif s.name in ("OBR", "TXA"):
            cur = {"orc": pending_orc, "obr": s if s.name == "OBR" else None, "txa": s if s.name == "TXA" else None, "obx": [], "nte": []}
            pending_orc = None
            out["groups"].append(cur)
        elif s.name in ("OBX", "NTE"):
            if cur is None and s.name == "OBX":
                cur = {"orc": pending_orc, "obr": None, "txa": None, "obx": [], "nte": []}
                pending_orc = None
                out["groups"].append(cur)
            if cur is not None:
                cur["obx" if s.name == "OBX" else "nte"].append(s)
    if pending_orc is not None:              # an order message with ORC and no OBR
        out["groups"].append({"orc": pending_orc, "obr": None, "txa": None, "obx": [], "nte": []})
    return out


# ---------------------------------------------------------------------------------------------------- message -> dicts
def identifiers(pid: Seg) -> list:
    """PID-3 repetitions as {"value", "authority", "type", "kind"}; an Aadhaar is dropped here and never kept."""
    out = []
    for i in range(len(pid.reps(3))):
        value, auth, typ = pid.get(3, 1, i), pid.get(3, 4, i).split(pid.d.sub)[0], pid.get(3, 5, i).upper()
        if not value or C.is_aadhaar(typ, auth):
            continue
        kind = "uhid" if typ in UHID_TYPES else "pmjay" if typ == "PMJAY" or "PMJAY" in auth.upper() else ""
        if typ in ABHA_TYPES or "ABHA" in auth.upper():
            kind = "abha_address" if "@" in value else "abha"
        out.append({"value": value, "authority": auth, "type": typ, "kind": kind})
    if out and not any(x["kind"] == "uhid" for x in out):
        first = next((x for x in out if not x["kind"]), None)
        if first:
            first["kind"] = "uhid"       # an untyped first identifier is the hospital's own number
    return out


def _person(seg: Seg, n: int):
    """An XCN field as {"ref", "name"}: id^family^given (standard) or id^full name (the demo hospital)."""
    if seg is None or not seg.field(n):
        return None
    first = seg.reps(n)[0].split(seg.d.comp)[0]
    subs = [unescape(x, seg.d).strip() for x in first.split(seg.d.sub)]
    if len(subs) > 1:                     # OBR-32: id&family&given
        ident, name = subs[0], " ".join(x for x in (subs[2:3] + subs[1:2]) if x)
    else:
        ident, name = seg.get(n, 1), " ".join(x for x in (seg.get(n, 3), seg.get(n, 2)) if x)
    return {"ref": ident, "name": name or ident} if (ident or name) else None


def patient_of(msg: dict):
    """(key, patient dict, identifier values) from PID, or None when the message names no patient."""
    pid = msg["pid"]
    if pid is None:
        return None
    ids = identifiers(pid)
    pick = lambda k: next((x["value"] for x in ids if x["kind"] == k), "")
    uhid = pick("uhid")
    if not uhid:
        return None
    family, given = pid.get(5, 1), " ".join(x for x in (pid.get(5, 2), pid.get(5, 3)) if x)
    dob = ts(pid.get(7))[:10]
    p = C.patient_shape(uhid, uhid, name=" ".join(x for x in (given, family) if x), sex=pid.get(8).upper()[:1], dob=dob,
                        abha=pick("abha"), abha_address=pick("abha_address"), pmjay_id=pick("pmjay"), phone=pid.get(13), last_updated=msg["time"])
    return uhid, p, [x["value"] for x in ids]


def visit_of(msg: dict):
    pv1 = msg["pv1"]
    if pv1 is None or not pv1.get(19):
        return None
    cls = pv1.get(2).upper()
    kind = "IP" if cls == "I" else "OP" if cls in ("O", "E", "R") else ""
    ward, bed = pv1.get(3, 1), pv1.get(3, 3)
    start, end = ts(pv1.get(44)), ts(pv1.get(45))
    wards = [{"ward": ward, "bed": bed, "from": start, "to": end, "reason": ""}] if kind == "IP" and ward else []
    return C.encounter_shape(pv1.get(19), kind, start=start or msg["time"], end=end, department=pv1.get(10, 1), unit=pv1.get(10, 2),
                             consultant=_person(pv1, 7), ward_history=wards, last_updated=msg["time"])


def _ed_part(obx: Seg) -> str:
    """The Base64 text of one ED OBX (source^type^subtype^encoding^data); ValueError for another encoding."""
    comps = (obx.reps(5) or [""])[0].split(obx.d.comp)
    data = comps[4] if len(comps) >= 5 else comps[-1]
    enc = (comps[3] if len(comps) >= 4 else "").strip().upper()
    if enc and enc not in ("BASE64", "B64"):
        raise ValueError(f"an embedded document in an encoding Vaidyx-TB does not read ({enc[:12]})")
    return re.sub(r"\s+", "", unescape(data, obx.d))


def _b64(text: str) -> bytes:
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("an embedded document with unreadable Base64") from None


def _ed_bytes(obxs: list):
    """The bytes of the first embedded document of a report group, or None when it has none. A large PDF may be split over
    consecutive ED segments with the same code (OBX-3) and the same set id (OBX-1) or a sub-id (OBX-4): the parts are joined
    in order. ValueError on bad Base64."""
    start = next((i for i, x in enumerate(obxs) if x.get(2).upper() == "ED"), None)
    if start is None:
        return None
    first = obxs[start]
    parts = [_ed_part(first)]
    for x in obxs[start + 1:]:
        same = x.get(2).upper() == "ED" and x.get(3) == first.get(3) and (x.get(1) == first.get(1) or (x.get(4) and first.get(4)))
        if not same:
            break
        parts.append(_ed_part(x))
    if len(parts) == 1:
        return _b64(parts[0])
    try:
        return _b64("".join(parts))            # one Base64 text cut into pieces
    except ValueError:
        return b"".join(_b64(x) for x in parts)   # pieces encoded one by one


def pointers(obxs: list) -> list:
    """The RP values of a group: pointers to a file kept elsewhere. Recorded, never fetched."""
    return [x.get(5, 1) or x.text(5) for x in obxs if x.get(2).upper() == "RP"]


def _code(seg: Seg, n: int):
    """A CE / CWE field as (code dict or None, label, LOINC code or "")."""
    code, text, system = seg.get(n, 1), seg.get(n, 2), seg.get(n, 3)
    loinc = system.upper() in ("LN", "LOINC")
    c = {"system": his_client.LOINC if loinc else system, "code": code, "display": text} if code else None
    return c, text or code, code if loinc else ""


def observation_of(obx: Seg) -> dict:
    """A non-document OBX as the observation dict (a candidate value: checked against the report text, never a fact by itself)."""
    code, label, loinc = _code(obx, 3)
    value, units = " ".join(obx.get(5, 1, i) for i in range(len(obx.reps(5)))).strip(), obx.get(6, 1)
    return {"id": obx.get(1), "code": code, "label": label, "fact": his_client.fact_for(loinc, label), "value": f"{value} {units}".strip(),
            "status": OBX_STATUS.get(obx.get(11).upper(), obx.get(11).lower()), "units": units, "reference_range": obx.text(7),
            "abnormal": obx.get(8), "value_type": obx.get(2).upper()}


def _status(g: dict, msg: dict) -> str:
    if g["txa"] is not None:
        if msg["trigger"] == "T11" or g["txa"].get(19).upper() in ("CA", "OB"):
            return "cancelled"
        return TXA_STATUS.get(g["txa"].get(17).upper(), "unknown")
    code = g["obr"].get(25).upper() if g["obr"] is not None else ""
    if code in OBR_STATUS:
        return OBR_STATUS[code]
    marks = {x.get(11).upper() for x in g["obx"] if x.get(11)}
    if len(marks) == 1 and next(iter(marks)) in ("F", "C", "P"):
        return OBX_STATUS[next(iter(marks))]
    return "unknown"


def text_of(rep: dict, p: dict, obs: list, notes: list) -> str:
    """The text of a "text only" report: what the message says, line by line (the OBX lines as label: value)."""
    lines = ["HL7 v2 result message (text only: the message carried no PDF)", rep["title"].upper() if rep["title"] else "RESULT",
             f"Patient name : {p.get('name') or ''}   UHID : {p.get('uhid') or ''}",
             f"Age / Sex : {str(p['age']) + ' Y' if p.get('age') is not None else ''} / {p.get('sex') or ''}"]
    if rep["encounter_number"]:
        lines.append(f"{'IP' if rep['encounter_kind'] == 'IP' else 'OP'} No. : {rep['encounter_number']}")
    if rep["accession"]:
        lines.append(f"Accession No. : {rep['accession']}")
    if rep["issued"]:
        lines.append(f"Reported on : {rep['issued']}")
    lines.append("")
    for o in obs:
        if o.get("value_type") == "RP":
            lines.append(f"Document by reference, not fetched: {o['value']}"); continue
        rng = f"   (reference range {o['reference_range']})" if o.get("reference_range") else ""
        flag = f"   [{o['abnormal']}]" if o.get("abnormal") else ""
        value = o["value"].replace("\n", "\n    ")
        lines.append(f"{o['label']}: {value}{rng}{flag}")
    for n in notes:
        lines.append(n)
    lines += ["", f"Report status: {rep['status'].upper()}"]
    if (rep.get("reported_by") or {}).get("name"):
        lines.append(f"Reported by: {rep['reported_by']['name']}")
    return "\n".join(lines) + "\n"


def _group_payload(g: dict, msg: dict, p: dict, rep: dict):
    """(bytes, text_only) of one report group: the ED document, else the text made of its OBX and NTE lines."""
    data = _ed_bytes(g["obx"])
    if data is not None:
        return data, False
    obs = [observation_of(x) for x in g["obx"]]
    notes = [x.text(3) for x in g["nte"] if x.text(3)]
    return text_of(rep, p, obs, notes).encode("utf-8"), True


def report_of(g: dict, msg: dict, key: str, p: dict, visit) -> dict:
    """One report dict from an OBR (or TXA) group. Raises ValueError (plain reason) when the group cannot be a report."""
    obr, txa, orc = g["obr"], g["txa"], g["orc"]
    if txa is not None:
        rid, placer = txa.get(12, 1) or txa.get(15, 1) or msg["control_id"], txa.get(14, 1)
        code, title, loinc = None, txa.get(2, 2) or txa.get(2, 1) or "Document", ""
        effective, issued, author, dept = ts(txa.get(4)), ts(txa.get(6)) or ts(txa.get(4)) or msg["time"], _person(txa, 9), ""
    else:
        rid = (obr.get(3, 1) if obr is not None else "") or (orc.get(3, 1) if orc is not None else "") \
            or (obr.get(2, 1) if obr is not None else "") or (orc.get(2, 1) if orc is not None else "") or msg["control_id"]
        placer = (obr.get(2, 1) if obr is not None else "") or (orc.get(2, 1) if orc is not None else "")
        if obr is not None:
            code, title, loinc = _code(obr, 4)
            effective, issued = ts(obr.get(7)), ts(obr.get(22)) or ts(obr.get(7)) or msg["time"]
            author, dept = _person(obr, 32), obr.get(24)
        else:
            code, title, loinc, effective, issued, author, dept = None, "Result", "", "", msg["time"], None, ""
    if not rid:
        raise ValueError("no filler, placer or control number")
    digest = hashlib.sha256("\r".join(s.raw for s in ([x for x in (orc, obr, txa) if x is not None] + g["obx"] + g["nte"])).encode()).hexdigest()[:16]
    doc_type, basis = his_client.doc_type_for(loinc, [], title, "")
    rep = C.report_shape(rid, 1, f"hl7v2:{quote(key, safe='')}/{quote(rid, safe='')}/{digest}", title=title, status=_status(g, msg),
                         issued=issued, effective=effective, code=code, doc_type=doc_type, doc_type_basis=basis,
                         encounter_number=(visit or {}).get("number") or "", encounter_kind=(visit or {}).get("kind") or "",
                         accession=(obr.get(3, 1) if obr is not None else "") or (orc.get(3, 1) if orc is not None else ""),
                         order_ref=placer or None, performer_department=dept, reported_by=author,
                         amendment_note=" ".join(x.text(3) for x in g["nte"] if x.get(4).upper() == "AMD"),
                         last_updated=msg["time"] or C.stamp(issued))
    data, text_only = _group_payload(g, msg, p, rep)
    rep["document"].update(sha256=hashlib.sha256(data).hexdigest(), size=len(data), content_type=C.sniff(data)[1], text_only=text_only)
    if text_only:
        rep["doc_type_basis"] = (basis + "; " if basis else "") + "text only (the HL7 message carried no PDF)"
    else:                                  # candidates only beside a real document: its text is what they are checked against
        rep["observations"] = [observation_of(x) for x in g["obx"] if x.get(2).upper() not in ("ED", "RP")]
    if pointers(g["obx"]):
        rep["doc_type_basis"] = (rep["doc_type_basis"] + "; " if rep["doc_type_basis"] else "") + "document by reference, not fetched"
        rep["_pointers"] = len(pointers(g["obx"]))
    rep["_digest"] = digest
    return rep


def order_of(g: dict, msg: dict, visit) -> dict:
    """An ORM^O01 group as the order dict of his_client.order_dict."""
    orc, obr = g["orc"], g["obr"]
    f = lambda seg, n, c=1: seg.get(n, c) if seg is not None else ""
    placer, filler = f(obr, 2) or f(orc, 2), f(obr, 3) or f(orc, 3)
    code, title, loinc = _code(obr, 4) if obr is not None else (None, "", "")
    cancelled = f(orc, 1).upper() in ("CA", "OC", "DC", "CR") or f(orc, 5).upper() == "CA" or f(obr, 25).upper() == "X"
    collected, scheduled = ts(f(obr, 14)), ts(f(obr, 36))
    stage = "cancelled" if cancelled else "sample_collected" if collected or f(obr, 25).upper() == "I" \
        else "scheduled" if scheduled or f(obr, 25).upper() == "S" else "ordered"
    doc_type, _ = his_client.doc_type_for(loinc, [], title, "")
    return {"id": placer or filler, "ref": "", "accession": filler, "test": title, "code": code, "doc_type": doc_type,
            "status": "revoked" if cancelled else "active", "stage": stage, "scheduled_for": scheduled,
            "authored_on": ts(f(obr, 7)) or ts(f(orc, 9)) or msg["time"],
            "specimen": {"ref": "", "collected": collected, "received": "", "barcode": "", "block_no": ""} if collected else None,
            "performer_department": f(obr, 24), "requester_department": f(orc, 17),
            "encounter_ref": "", "encounter_number": (visit or {}).get("number") or "", "encounter_kind": (visit or {}).get("kind") or "",
            "note": f(orc, 16) if cancelled else "", "last_updated": msg["time"]}


# ---------------------------------------------------------------------------------------------------- the folder
def load(folder) -> dict:
    """The parsed folder: patients, visits, reports (numbered versions), orders, where each document lives, and counts."""
    files, skipped = C.list_files(folder, SUFFIXES)

    def build():
        idx = {"patients": {}, "ids": {}, "visits": {}, "reports": {}, "orders": {}, "docs": {}, "skipped": dict(skipped),
               "files": len(files), "messages": 0}
        raw_reports, seen = {}, set()
        msgs = []
        for path, _, _ in files:
            try:
                parts = split_messages(path.read_bytes())
            except OSError:
                C._skip(idx["skipped"], "unreadable file"); continue
            if not parts:
                C._skip(idx["skipped"], "no MSH segment"); continue
            for n, lines in enumerate(parts):
                try:
                    m = parse_message(lines)
                except (ValueError, IndexError):
                    C._skip(idx["skipped"], "not a readable HL7 message"); continue
                m["file"], m["pos"] = path, n
                msgs.append(m)
        idx["messages"] = len(msgs)
        msgs.sort(key=lambda m: (m["time"] or "", m["file"].name, m["pos"]))
        for m in msgs:
            got = patient_of(m)
            if got is None:
                C._skip(idx["skipped"], "no patient identifier (PID-3)"); continue
            key, p, values = got
            idx["patients"][key] = p                       # the latest message's demographics
            for v in values:
                idx["ids"].setdefault(v.lower(), {})[key] = "id"
            visit = visit_of(m)
            if visit:
                idx["ids"].setdefault(visit["number"].lower(), {})[key] = "ip_no" if visit["kind"] == "IP" else "op_no"
                old = idx["visits"].setdefault(key, {}).get(visit["number"])
                if old:                                     # the first message opens the visit, later ones add its end
                    visit["start"] = min(x for x in (old["start"], visit["start"]) if x) if (old["start"] or visit["start"]) else ""
                    visit["end"] = visit["end"] or old["end"]
                    visit["ward_history"] = visit["ward_history"] or old["ward_history"]
                idx["visits"][key][visit["number"]] = visit
            if m["type"] == "ORM":
                for g in m["groups"]:
                    o = order_of(g, m, visit)
                    if o["id"]:
                        idx["orders"].setdefault(key, {})[o["id"]] = o
                continue
            if m["type"] not in ("ORU", "MDM"):
                continue                                    # ADT and the rest: identity and visits only
            for gi, g in enumerate(m["groups"]):
                if m["type"] == "MDM" and g["txa"] is None:
                    continue
                try:
                    rep = report_of(g, m, key, p, visit)
                except ValueError as e:
                    C._skip(idx["skipped"], str(e)); continue
                if (key, rep["_digest"]) in seen:
                    C._skip(idx["skipped"], "the same message sent twice"); continue
                seen.add((key, rep["_digest"]))
                rep.pop("_digest")
                if rep.pop("_pointers", 0):
                    C._skip(idx["skipped"], "a document by reference (RP), not fetched")
                raw_reports.setdefault(key, []).append(rep)
                idx["docs"][rep["document_ref"]] = (m["file"], m["pos"], gi, key)
        for key, reps in raw_reports.items():
            idx["reports"][key] = C.number_versions(reps)
        return idx
    return C.cached(KIND, folder, tuple((p.name, s, t) for p, s, t in files), build)


class HL7v2FolderClient(HISClient):
    """HL7 v2.x result messages read from a folder (see the module docstring)."""
    carries_signature = False  # no verifiable signature on this transport: the report text decides (his_overlay)
    kind = KIND

    def __init__(self, folder, label: str = ""):
        self.folder = str(folder or "")
        self.label = label or "HL7 v2 results folder"

    def __repr__(self):
        return f"HL7v2FolderClient({self.folder!r})"

    def _load(self) -> dict:
        return load(C.runtime_folder(self.folder))

    async def _idx(self) -> dict:
        return await asyncio.to_thread(self._load)

    async def ping(self) -> dict:
        out = {"ok": False, "name": self.label, "fhir_version": "", "token_ok": None, "error": ""}
        try:
            idx = await self._idx()
            out["counts"] = {"files": idx["files"], "messages": idx["messages"], "patients": len(idx["patients"]),
                             "reports": sum(len(v) for v in idx["reports"].values()), "skipped": idx["skipped"]}
            out["ok"] = True
        except HISError as e:
            out["error"] = str(e)
        return out

    async def find_patient(self, identifier: str) -> dict | None:
        value = str(identifier or "").strip()
        if not value:
            return None
        idx = await self._idx()
        hits = idx["ids"].get(value.lower()) or {}
        key = C.one_match(hits, value)
        if key is None:
            return None
        p = dict(idx["patients"][key])
        how = hits[key]
        if how == "id":
            how = next((k for k in ("uhid", "abha", "abha_address") if (p.get(k) or "").lower() == value.lower()), "pmjay" if (p.get("pmjay_id") or "").lower() == value.lower() else "uhid")
        return {**p, "matched_on": {"kind": how, "value": value}, "similar": []}

    async def encounters(self, patient_id: str) -> list:
        idx = await self._idx()
        return sorted((dict(v) for v in (idx["visits"].get(patient_id) or {}).values()), key=lambda e: (e["start"] or "9999", e["number"]))

    async def reports(self, patient_id: str, since: str | None = None) -> list:
        idx = await self._idx()
        return [dict(r, document=dict(r["document"])) for r in idx["reports"].get(patient_id) or [] if C.after(r["last_updated"], since)]

    async def open_orders(self, patient_id: str) -> list:
        """Orders (ORM^O01) with no result message yet, the latest message per placer number; [] when the folder has no orders."""
        idx = await self._idx()
        reported = {x for r in idx["reports"].get(patient_id) or [] for x in (r["order_ref"], r["accession"], r["id"]) if x}
        out = [dict(o) for o in (idx["orders"].get(patient_id) or {}).values() if o["id"] not in reported and (not o["accession"] or o["accession"] not in reported)]
        return sorted(out, key=lambda o: (o["authored_on"], o["id"]))

    async def document(self, ref: str) -> dict:
        """The report's file: the PDF of the ED OBX, or the text of a "text only" message; checked against the sha256 taken when
        the folder was read."""
        m = re.match(r"^hl7v2:([^/]+)/([^/]+)/([0-9a-f]{16})$", str(ref or ""))
        if not m:
            raise HISError(f"not an HL7 v2 report reference: {str(ref)[:80]}")
        idx = await self._idx()
        where = idx["docs"].get(ref)
        rep = next((r for r in idx["reports"].get(unquote(m.group(1))) or [] if r["document_ref"] == ref), None)
        if not where or rep is None:
            raise HISError("the HL7 v2 folder no longer holds that report message")
        path, pos, gi, key = where

        def read():
            try:
                msg = parse_message(split_messages(path.read_bytes())[pos])
                return _group_payload(msg["groups"][gi], msg, idx["patients"][key], rep)
            except (OSError, ValueError, IndexError):
                raise HISError("the HL7 v2 message file of that report changed or cannot be read") from None
        data, text_only = await asyncio.to_thread(read)
        his_client._check_sha(data, rep["document"]["sha256"], "", f"report {rep['id']}")
        return C.document_shape(ref, data, rep["title"] or rep["id"], f"{rep['title'] or 'report'}_{rep['id']}_v{rep['version']}",
                                creation=rep["issued"], doc_status=rep["status"], text_only=text_only)
