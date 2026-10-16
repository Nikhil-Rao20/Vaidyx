"""The mock hospital's internal event feed (plan item V2-1.4): HL7 v2.5-style messages, one per store event. SYNTHETIC only.

Every Store transition appends exactly one event (model.py) and stamps meta.lastUpdated on what it changed. This module
renders those events as the pipe-delimited messages an Indian HIS / LIS / RIS integration engine would pass around, and
answers the delta question a client asks on re-fetch ("what changed since my watermark?"):

    from his_mock import hl7
    text = hl7.message(store, store.events[-1])        # 'MSH|^~\\&|VXHIS|VXDEMO|...\\rPID|...\\rOBR|...'
    hl7.write_feed(store, path)                         # data/his_mock/events.hl7, one message per event
    hl7.append(store, event, path)                      # the reporting desk (1.5) after each transition
    hl7.changed_since(store, watermark)                 # reports whose meta.lastUpdated is after the watermark
    hl7.events_since(store, watermark)                  # the events behind them (and the ADT / REF / ORM ones)
    hl7.last_event_time(store)                          # the next watermark

Messages (segments separated by \\r, fields by |, components by ^, repetitions by ~; text escaped with \\F\\ \\S\\ \\T\\ \\R\\ \\E\\):
- ADT^A28 / A04 / A01 / A02 / A03: MSH, EVN, PID, PV1.
- REF^I12 / I13: MSH, RF1 (RF1-1 referral status P requested / A accepted, RF1-3 from^to department, RF1-6 referral id
  <encounter No.>-R<n>, RF1-7 effective time, RF1-10 reason), PRD|RP (from department), PRD|RT (to department), PID, PV1.
- ORM^O01: MSH, PID, PV1, ORC (ORC-1 NW placed / SC status change / CA cancelled, ORC-2 placer = order id, ORC-3 filler =
  accession No., ORC-5 = the event's order status IP / SC / CA, ORC-9 event time, ORC-12 consultant, ORC-16 cancel reason,
  ORC-17 ordering department), OBR (OBR-2 / -3 as ORC, OBR-4 test key^label, OBR-7 ordered, OBR-14 sample collected,
  OBR-24 performing department code, OBR-25 = the event's status O / S / I / X, OBR-36 scheduled for).
- ORU^R01: MSH, PID, PV1, ORC (ORC-1 RE, ORC-5 CM or CA), OBR (OBR-22 reported, OBR-25 P / F / C / X, OBR-32 the signer
  VXREG-...^Name for a signed version), one OBX per printed value of the event's version (OBX-2 ST, OBX-3 value key, OBX-5
  the printed value, OBX-11 P / F / C, OBX-14 reported, OBX-16 reporter), NTE|1|L|<signature block>|SIG for a signed
  version, NTE|n|L|<amendment note>|AMD for an amendment, NTE|n|L|<reason>|CAN for a cancellation (no OBX then).

PID carries the UHID (PID-3, assigning authority VXH, type MR), the ABHA number as a second PID-3 repetition when linked
(type NH), the PM-JAY ID as a third (type PMJAY), name SURNAME^GIVEN with "(SYNTHETIC)" kept, DOB YYYYMMDD and sex. Never an
Aadhaar number. PV1: class O / I (N for a registration), PV1-3 ward^^bed for an admission (the bed at the event's time),
PV1-7 consultant VXREG-...^Name, PV1-10 department^unit, PV1-19 OP / IP No., PV1-44 / -45 admission and discharge times.

Message times are the event's time as YYYYMMDDHHMMSS+0530; the control id is the event id. Pure stdlib.
"""
import os
from pathlib import Path

from .ids import parse_time
from .model import MARKER

SENDING_APP = "VXHIS"
FACILITY = "VXDEMO"
RECEIVING_APP = "VAIDYX_TB"
VERSION = "2.5"
SEGMENT_SEP = "\r"
MESSAGE_SEP = "\r\n\r\n"
ENCODING_CHARS = "^~\\&"
REPEATING = ("OBX", "NTE", "PRD")      # parse() always returns these as a list of field lists

ORC1 = {"O": "NW", "S": "SC", "I": "SC", "X": "CA"}
RF1_STATUS = {"requested": "P^Requested", "accepted": "A^Accepted"}
_ESCAPES = (("\\", "\\E\\"), ("|", "\\F\\"), ("^", "\\S\\"), ("&", "\\T\\"), ("~", "\\R\\"))


# -------------------------------------------------------------------- text and time helpers
def escape(text):
    """HL7 v2 escape of a text value (delimiters -> \\F\\ \\S\\ \\T\\ \\R\\ \\E\\, line breaks -> \\.br\\)."""
    if text is None:
        return ""
    s = str(text)
    for a, b in _ESCAPES:
        s = s.replace(a, b)
    return s.replace("\r\n", "\\.br\\").replace("\n", "\\.br\\").replace("\r", "\\.br\\")


def unescape(text):
    """Inverse of escape()."""
    out, i, s = [], 0, str(text or "")
    table = {"F": "|", "S": "^", "T": "&", "R": "~", "E": "\\", ".br": "\n"}
    while i < len(s):
        if s[i] == "\\":
            j = s.find("\\", i + 1)
            if j > i and s[i + 1:j] in table:
                out.append(table[s[i + 1:j]])
                i = j + 1
                continue
        out.append(s[i])
        i += 1
    return "".join(out)


def ts(value):
    """ISO date-time -> YYYYMMDDHHMMSS+0530; an ISO date -> YYYYMMDD; None -> ''."""
    if not value:
        return ""
    s = str(value).strip()
    if len(s) == 10:
        return s.replace("-", "")
    return parse_time(s).strftime("%Y%m%d%H%M%S%z")


def _comp(*parts):
    """Components joined by ^ (each escaped), trailing empties dropped."""
    vals = [escape(p) for p in parts]
    while vals and vals[-1] == "":
        vals.pop()
    return "^".join(vals)


def _seg(name, *fields):
    """A segment from already-encoded fields, trailing empties dropped."""
    vals = list(fields)
    while vals and vals[-1] in ("", None):
        vals.pop()
    return "|".join([name] + ["" if v is None else str(v) for v in vals])


# -------------------------------------------------------------------- segments
def _msh(event):
    msg_type = f"{event['kind']}^{event['trigger']}"
    return "|".join(["MSH", ENCODING_CHARS, SENDING_APP, FACILITY, RECEIVING_APP, FACILITY, ts(event["time"]), "",
                     msg_type, event["id"], "P", VERSION])


def _evn(event):
    return _seg("EVN", event["trigger"], ts(event["time"]))


def split_name(name):
    """'Venkatesh Rao (SYNTHETIC)' -> ('Rao (SYNTHETIC)', 'Venkatesh'): the last word is the surname; the marker stays."""
    plain = " ".join(str(name or "").replace(f"({MARKER})", " ").split())
    words = plain.split(" ") if plain else [""]
    family, given = words[-1], " ".join(words[:-1])
    return f"{family} ({MARKER})".strip(), given


def _pid(patient):
    reps = [_comp(patient["uhid"], "", "", "VXH", "MR")]
    abha = (patient.get("abha") or {}).get("number")
    if abha:
        reps.append(_comp(abha, "", "", "ABHA", "NH"))
    if patient.get("pmjay_id"):
        reps.append(_comp(patient["pmjay_id"], "", "", "PMJAY", "PMJAY"))
    family, given = split_name(patient["name"])
    addr = patient.get("address") or {}
    address = _comp(addr.get("line"), "", addr.get("town"), addr.get("state"), addr.get("pin"), "IND") if addr else ""
    dob = (patient.get("dob_iso") or "").replace("-", "")
    return _seg("PID", "1", "", "~".join(reps), "", _comp(family, given), "", dob, patient["sex"], "", "", address, "",
                escape(patient.get("phone")))


def _practitioner(store, pid):
    p = store.practitioner(pid) if pid else None
    return _comp(p["reg_no"], p["name"]) if p else ""


def _bed_at(encounter, t):
    """The (ward, bed) the admitted patient was in at time t (the first location before admission)."""
    hist = encounter.get("ward_history") or []
    if not hist:
        return encounter.get("ward"), encounter.get("bed")
    when = parse_time(t)
    cur = hist[0]
    for h in hist:
        if parse_time(h["from"]) <= when:
            cur = h
    return cur["ward"], cur["bed"]


def _pv1(store, encounter, event):
    if not encounter:
        return _seg("PV1", "1", "N")
    ip = encounter["kind"] == "IP"
    location = ""
    admit_time = discharge_time = ""
    if ip:
        ward, bed = _bed_at(encounter, event["time"])
        location = _comp(ward, "", bed)
        admit_time = ts((encounter.get("ward_history") or [{}])[0].get("from") or encounter.get("admitted"))
        if event["trigger"] == "A03":
            discharge_time = ts(event["time"])
    fields = [""] * 45
    fields[0] = "1"
    fields[1] = "I" if ip else "O"
    fields[2] = location
    fields[6] = _practitioner(store, encounter.get("consultant_id"))
    fields[9] = _comp(encounter["department"], encounter.get("unit"))
    fields[18] = escape(encounter["number"])
    fields[43] = admit_time
    fields[44] = discharge_time
    return _seg("PV1", *fields)


def _dept_code(store, name):
    d = store.department(name)
    return d["code"] if d else ""


def _orc(store, order, encounter, control, order_status, event, cancel_reason=""):
    fields = [""] * 17
    fields[0] = control
    fields[1] = _comp(order["id"], SENDING_APP)
    fields[2] = _comp(order["accession"], SENDING_APP) if order.get("accession") else ""
    fields[4] = order_status
    fields[8] = ts(event["time"])
    fields[11] = _practitioner(store, (encounter or {}).get("consultant_id"))
    fields[15] = cancel_reason
    fields[16] = _comp(order["ordering_department"])
    return _seg("ORC", *fields)


def _obr(store, order, event, *, reported="", interpreter="", sample=True, scheduled=True):
    fields = [""] * 36
    fields[0] = "1"
    fields[1] = _comp(order["id"], SENDING_APP)
    fields[2] = _comp(order["accession"], SENDING_APP) if order.get("accession") else ""
    fields[3] = _comp(order["test"], order["label"])
    fields[6] = ts(order["ordered_on"])
    coll = order.get("sample_collected_on")
    if sample and coll and parse_time(coll) <= parse_time(event["time"]):
        fields[13] = ts(coll)
    fields[21] = reported
    fields[23] = escape(_dept_code(store, order["performing_department"]))
    fields[24] = event["status"] or ""
    fields[31] = interpreter
    if scheduled and order.get("scheduled_for") and event["status"] != "O":
        fields[35] = ts(order["scheduled_for"])
    return _seg("OBR", *fields)


def _version(report, n):
    for v in report["versions"]:
        if v["version"] == n:
            return v
    return report["versions"][-1] if report["versions"] else None


def _referral(encounter, event, store):
    """The referral an REF event is about: the n-th I12 on the encounter is referrals[n]; an I13 names the department."""
    refs = encounter.get("referrals") or []
    if not refs:
        return None, 0
    if event["trigger"] == "I12":
        n = sum(1 for e in store.events if e["kind"] == "REF" and e["trigger"] == "I12"
                and e["refs"].get("encounter_id") == encounter["id"] and e["id"] < event["id"])
        n = min(n, len(refs) - 1)
        return refs[n], n
    text = event.get("text") or ""
    for i, r in enumerate(refs):
        if r["status"] == "accepted" and text.endswith(f"accepted by {r['to']}"):
            return r, i
    i = next((i for i, r in enumerate(refs) if r["status"] == "accepted"), 0)
    return refs[i], i


# -------------------------------------------------------------------- messages
def message(store, event):
    """One HL7 v2.5-style message for a store event (segments separated by \\r)."""
    refs = event.get("refs") or {}
    patient = store.patients.get(refs.get("patient_id"))
    if not patient:
        raise ValueError(f"event {event['id']} names no known patient")
    encounter = store.encounters.get(refs.get("encounter_id")) if refs.get("encounter_id") else None
    kind = event["kind"]
    segs = [_msh(event)]
    if kind == "ADT":
        segs += [_evn(event), _pid(patient), _pv1(store, encounter, event)]
    elif kind == "REF":
        segs += _ref_segments(store, event, patient, encounter)
    elif kind == "ORM":
        order = store.orders[refs["order_id"]]
        status = event["status"]
        reason = escape(order.get("cancel_reason")) if status == "X" else ""
        segs += [_pid(patient), _pv1(store, encounter, event),
                 _orc(store, order, encounter, ORC1.get(status, "SC"),
                      event.get("order_status") or "", event, reason),
                 _obr(store, order, event)]
    elif kind == "ORU":
        segs += _oru_segments(store, event, patient, encounter)
    else:
        raise ValueError(f"unknown event kind {kind!r}")
    return SEGMENT_SEP.join(segs)


def _ref_segments(store, event, patient, encounter):
    ref, n = _referral(encounter, event, store) if encounter else (None, 0)
    ref = ref or {}
    status = "accepted" if event["trigger"] == "I13" else "requested"
    rf1 = [""] * 10
    rf1[0] = RF1_STATUS[status]
    rf1[2] = _comp(ref.get("from"), ref.get("to"))
    rf1[5] = _comp(f"{encounter['number']}-R{n + 1}" if encounter else "", SENDING_APP)
    rf1[6] = ts(event["time"])
    rf1[9] = _comp("", ref.get("reason"))
    return [_seg("RF1", *rf1),
            _seg("PRD", "RP", _comp("", ref.get("from"))),
            _seg("PRD", "RT", _comp("", ref.get("to"))),
            _pid(patient), _pv1(store, encounter, event)]


def _oru_segments(store, event, patient, encounter):
    refs = event["refs"]
    report = store.reports[refs["report_id"]]
    order = store.orders[report["order_id"]]
    status = event["status"]
    version = _version(report, refs.get("version") or report["current_version"])
    sig = store.signatures.get(version.get("signature_id")) if version and version.get("signature_id") else None
    interpreter = _practitioner(store, sig["signer_id"]) if sig else ""
    reported = ts(version["reported_on"]) if version else ""
    reason = escape(order.get("cancel_reason")) if status == "X" else ""
    segs = [_pid(patient), _pv1(store, encounter, event),
            _orc(store, order, encounter, "CA" if status == "X" else "RE",
                 "CA" if status == "X" else ("A" if status == "P" else "CM"), event, reason),
            _obr(store, order, event, reported=reported, interpreter=interpreter)]
    nte = 0
    if status == "X":
        nte += 1
        segs.append(_seg("NTE", str(nte), "L", escape(order.get("cancel_reason") or "Cancelled"), "CAN"))
        return segs
    reporter = _practitioner(store, version["reported_by"]) if version else ""
    for i, (key, value) in enumerate((version or {}).get("values", {}).items(), start=1):
        obx = [""] * 16
        obx[0] = str(i)
        obx[1] = "ST"
        obx[2] = escape(key)
        obx[4] = escape(value)
        obx[10] = status
        obx[13] = reported
        obx[15] = reporter
        segs.append(_seg("OBX", *obx))
    if sig:
        nte += 1
        segs.append(_seg("NTE", str(nte), "L", escape(sig["block"]), "SIG"))
    if version and version.get("amendment_note"):
        nte += 1
        segs.append(_seg("NTE", str(nte), "L", escape(version["amendment_note"]), "AMD"))
    return segs


# -------------------------------------------------------------------- the feed file
def write_feed(store, path):
    """Write every store event's message to `path` (events.hl7) in event order, each followed by a blank line (\\r\\n\\r\\n).
    Atomic (temporary file, then rename). Returns the number of messages."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    msgs = [message(store, e) for e in store.events]
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write("".join(m + MESSAGE_SEP for m in msgs))
    os.replace(tmp, path)
    return len(msgs)


def append(store, event, path):
    """Append one event's message to the feed (the reporting desk calls this after each transition). Returns the message."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    msg = message(store, event)
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(msg + MESSAGE_SEP)
    return msg


def read_feed(path):
    """The messages of a feed file, in order."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    return [m.strip("\r\n") for m in text.split(MESSAGE_SEP) if m.strip("\r\n")]


def parse(msg):
    """A light parser (tests and the e2e): {"type": "ORU^R01", "control_id": ..., "segments": {name: fields}}.

    fields[n] is field n of the segment (for MSH, fields[1] is the field separator, so fields[9] is MSH-9). Fields stay
    encoded (use unescape() for text). OBX, NTE and PRD are always lists of field lists; any other segment that repeats
    becomes one too."""
    segments = {}
    for line in msg.replace("\r\n", "\r").replace("\n", "\r").split("\r"):
        if not line:
            continue
        name = line[:3]
        fields = line.split("|")
        if name == "MSH":
            fields = ["MSH", "|"] + fields[1:]
        if name in REPEATING:
            segments.setdefault(name, []).append(fields)
        elif name in segments:
            prev = segments[name]
            segments[name] = (prev if prev and isinstance(prev[0], list) else [prev]) + [fields]
        else:
            segments[name] = fields
    msh = segments.get("MSH")
    if not msh:
        raise ValueError("not an HL7 message: no MSH segment")
    return {"type": msh[9] if len(msh) > 9 else "", "control_id": msh[10] if len(msh) > 10 else "",
            "segments": segments}


# -------------------------------------------------------------------- deltas
def _after(t, cut):
    return parse_time(t) > cut


def changed_since(store, since, patient_id=None):
    """Reports whose meta.lastUpdated is strictly after `since` (ISO time), optionally of one registration; oldest change
    first. With since=None, every report."""
    reports = store.reports_for(patient_id=patient_id, since=since)
    return sorted(reports, key=lambda r: (parse_time(r["meta"]["lastUpdated"]), r["id"]))


def events_since(store, since, patient_id=None):
    """Store events strictly after `since` (ISO time), optionally of one registration, in event order."""
    cut = parse_time(since) if since else None
    out = []
    for e in store.events:
        if patient_id and e["refs"].get("patient_id") != patient_id:
            continue
        if cut and not _after(e["time"], cut):
            continue
        out.append(e)
    return out


def last_event_time(store):
    """The latest event time (ISO, +05:30): what a client keeps as its fetch watermark. None for an empty store."""
    if not store.events:
        return None
    return max(store.events, key=lambda e: parse_time(e["time"]))["time"]
