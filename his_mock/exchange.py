"""The Exchange module of the demo HIMS, mounted at /his by app.py. SYNTHETIC data only.

    GET /his/exchange?patient=&type=      the HL7 v2 message viewer (last 200 messages of events.hl7, filtered by patient
                                          and message type, raw text shown), the FHIR R4 link list (metadata URL and
                                          example searches), the events log and the Integration line (whether the API
                                          token file exists; its value is never shown)
    GET /his/exchange/hl7/{control id}    one raw message as text/plain
"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from . import common, hl7, ui
from .app import Hospital, get_hospital
from .common import dt

router = APIRouter()

LAST = 200
EVENTS = 100
TYPES = ("ADT", "ORM", "ORU", "REF")


def _msh(msg):
    """(type, control id, time) of a message from its MSH segment."""
    msh = msg.split("\r", 1)[0].split("|")
    get = lambda i: msh[i] if len(msh) > i else ""   # noqa: E731
    return get(8), get(9), get(6)


def _pid(msg):
    """(identifiers, name) from the PID segment."""
    for seg in msg.split("\r"):
        if seg.startswith("PID|"):
            f = seg.split("|")
            ids_ = f[3] if len(f) > 3 else ""
            name = f[5] if len(f) > 5 else ""
            return ids_, name.replace("^", " ")
    return "", ""


def _pretty_time(t):
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", t or "")
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)} {m.group(4)}:{m.group(5)}" if m else t


def messages(files, patient="", kind="", last=LAST):
    """The last `last` messages (newest first) matching the patient text (UHID, IP / OP No. or name in PID / PV1) and
    the message kind (ADT, ORM, ORU, REF)."""
    out = []
    key = (patient or "").strip().lower()
    for msg in reversed(hl7.read_feed(files["hl7"])):
        mtype, control, when = _msh(msg)
        if kind and not mtype.upper().startswith(kind.upper()):
            continue
        if key and key not in msg.lower():
            continue
        ids_, name = _pid(msg)
        out.append({"type": mtype, "control_id": control, "time": when, "ids": ids_, "name": name, "raw": msg})
        if len(out) >= last:
            break
    return out


@router.get("/exchange", response_class=HTMLResponse)
def exchange_home(request: Request, patient: str = "", type: str = "", hospital: Hospital = Depends(get_hospital)):
    store, files = hospital.store, hospital.files
    msgs = messages(files, patient, type)
    filt = ('<div class=panel><form method=get action="/his/exchange">'
            f'<label class=lbl>Patient (UHID, IP / OP No. or name) <input type=text name=patient value="{ui.esc(patient)}" class=short></label> '
            f'<label class=lbl>Type <select name=type class=short>{ui.options([("", "All")] + [(t, t) for t in TYPES], type)}</select></label> '
            '<button type=submit>Filter</button></form></div>')
    rows = []
    for m in msgs:
        raw = ui.esc(m["raw"].replace("\r", "\n"))
        rows.append([ui.esc(_pretty_time(m["time"])), f'<span class=mono>{ui.esc(m["type"])}</span>',
                     f'<a href="/his/exchange/hl7/{ui.esc(m["control_id"])}" class=mono>{ui.esc(m["control_id"])}</a>',
                     ui.esc(m["name"]), f'<span class=mono>{ui.esc(m["ids"])}</span>',
                     f'<details><summary>raw</summary><pre class=hl7>{raw}</pre></details>'])
    total = len(hl7.read_feed(files["hl7"]))
    body = (filt + f'<div class=panel id=hl7><h2>HL7 v2 messages (last {len(msgs)} of {total} in events.hl7, newest first)</h2>'
            + ui.table(["Time", "Type", "Control id", "Patient", "PID-3 identifiers", "Message"], rows, "No message matches.")
            + '</div>')
    token_present = Path(files["token"]).exists()
    examples = [("CapabilityStatement (no token)", "/fhir/metadata"),
                ("Patient by UHID", "/fhir/Patient?identifier=VXH/26/004201"),
                ("Encounters of a patient", "/fhir/Encounter?patient=vxh-26-004201"),
                ("Reports changed since a watermark", "/fhir/DiagnosticReport?_lastUpdated=gt2026-10-01T00:00:00%2B05:30"),
                ("Documents of a patient", "/fhir/DocumentReference?patient=vxh-26-004201&status=current"),
                ("Imaging studies", "/fhir/ImagingStudy?patient=vxh-26-004201"),
                ("A patient's everything", "/fhir/Patient/vxh-26-004201/$everything")]
    rows = [[ui.esc(l), (f'<a href="{ui.esc(u)}" target=_blank class=mono>{ui.esc(u)}</a>' if u == "/fhir/metadata"
                         else f'<span class=mono>{ui.esc(u)}</span> <span class="small muted">(token)</span>')]
            for l, u in examples]
    body += ('<div class=panel id=fhir><h2>FHIR R4 API (NRCeS shapes)</h2>'
             '<p>Base URL <span class=mono>http://127.0.0.1:7130/fhir</span>; every call except metadata carries the API '
             'token as <span class=mono>Authorization: Bearer</span>. Vaidyx-TB reads this hospital through it.</p>'
             + ui.table(["Example", "URL"], rows) + '</div>')
    body += ('<div class=panel id=integration><h2>Integration</h2>'
             f'<p>API token file: <b>{"present" if token_present else "missing"}</b> (data/his_mock/token; the value is never shown). '
             f'HL7 feed: <span class=mono>{ui.esc(str(files["hl7"]))}</span>, {total} messages. '
             f'FHIR: <span class=mono>/fhir/metadata</span>. PACS viewer: <span class=mono>/api/tb/pacs/ohif/</span> (login).</p></div>')
    rows = []
    for ev in reversed(store.events[-EVENTS:]):
        refs = ", ".join(f"{k}={v}" for k, v in (ev.get("refs") or {}).items())
        rows.append([ui.esc(ev["id"]), ui.esc(dt(ev["time"])), f'<span class=mono>{ui.esc(ev["kind"])}^{ui.esc(ev["trigger"])}</span>',
                     ui.esc(ev.get("status") or ""), ui.esc(ev.get("text")), f'<span class=small>{ui.esc(refs)}</span>'])
    body += (f'<div class=panel id=events><h2>Events log (last {min(EVENTS, len(store.events))} of {len(store.events)})</h2>'
             + ui.table(["Event", "Time", "Message", "Status", "Text", "References"], rows, "No event yet.") + '</div>')
    return common.page(request, "Exchange", body, active="Exchange")


@router.get("/exchange/hl7/{control_id}")
def raw_message(control_id: str, request: Request, hospital: Hospital = Depends(get_hospital)):
    for msg in hl7.read_feed(hospital.files["hl7"]):
        if _msh(msg)[1] == control_id:
            return PlainTextResponse(msg.replace("\r", "\n"))
    return PlainTextResponse("No such message.", status_code=404)
