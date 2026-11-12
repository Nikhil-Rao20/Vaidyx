"""HL7 v2 results from a folder (his_adapters.hl7v2): parsing edge cases (delimiters, escapes, MLLP bytes, a BOM, \\n segment ends,
a PDF in an ED OBX, a PDF split over several OBX, an RP pointer), identity (UHID, visit number, never an Aadhaar), status mapping,
versions (the latest message for a filler number wins), text-only reports, open orders, path safety, and the happy path through
his_case.lookup and his_case.create. SYNTHETIC data only, temporary folders, no network."""
import asyncio
import base64
import hashlib
import os

import pytest

from tumour_board import his_case, his_client, store
from tumour_board.his_adapters import _common, hl7v2
from tumour_board.his_adapters.hl7v2 import HL7v2FolderClient
from tumour_board.tests.test_his_case import ROLES_DOC, fakes  # noqa: F401

UHID = "VXH/26/004201"
NAME = "Anitha Reddy (SYNTHETIC)"
PDF = (b"%PDF-1.4\nVaidyx Demo Hospital (SYNTHETIC)\nDepartment of Pathology\nHISTOPATHOLOGY REPORT\nPatient name : Anitha Reddy (SYNTHETIC) UHID : VXH/26/004201\n"
       b"Age / Sex : 46 Y / F OP No. : OP/26/118701\nLab No. : PATH/26/00411\nDiagnosis: Invasive carcinoma of no special type\nReport status: FINAL\n")
PDF2 = PDF.replace(b"Report status: FINAL", b"Addendum: margins re-measured\nReport status: CORRECTED")


def seg(name, fields, fs="|"):
    return fs.join([name] + [fields.get(i, "") for i in range(1, max(fields) + 1)])


def msh(ctrl, when, typ="ORU^R01", fs="|", enc="^~\\&"):
    return fs.join(["MSH", enc, "LIS", "VXDEMO", "VAIDYX_TB", "VXDEMO", when, "", typ, ctrl, "P", "2.5"])


def pid(uhid=UHID, family="Reddy (SYNTHETIC)", given="Anitha", extra="", fs="|", c="^", r="~"):
    ids = f"{uhid}{c}{c}{c}VXH{c}MR{r}99-2600-0000-0101{c}{c}{c}ABHA{c}NH{r}1234-5678-9012{c}{c}{c}UIDAI{c}AADHAAR" + extra
    return seg("PID", {1: "1", 3: ids, 5: f"{family}{c}{given}", 7: "19800118", 8: "F"}, fs)


def pv1(number="OP/26/118701", cls="O", fs="|", c="^"):
    return seg("PV1", {1: "1", 2: cls, 7: f"VXREG-10101{c}Dr Kavitha Raghunathan", 10: f"Breast Surgery{c}Unit I", 19: number}, fs)


def obr(filler="PATH/26/00411", status="F", placer="ORD-1", service="11526-1^Histopathology report^LN", reported="20260905110000+0530", dept="Pathology"):
    return seg("OBR", {1: "1", 2: f"{placer}^VXHIS", 3: f"{filler}^VXHIS", 4: service, 7: "20260903100000+0530", 22: reported, 24: dept, 25: status})


def obx(n, vtype, code, value, units="", rng="", status="F", sub=""):
    return seg("OBX", {1: str(n), 2: vtype, 3: code, 4: sub, 5: value, 6: units, 7: rng, 11: status})


def ed(n, data: bytes, sub=""):
    return obx(n, "ED", "PDF^Report", "VXHIS^AP^PDF^Base64^" + base64.b64encode(data).decode(), sub=sub)


def oru(ctrl="M1", when="20260905110000+0530", status="F", pdf=PDF, filler="PATH/26/00411", extra=(), **kw):
    lines = [msh(ctrl, when), pid(), pv1(), "ORC|RE|ORD-1^VXHIS|" + filler + "^VXHIS||CM", obr(filler, status, **kw),
             obx(1, "ST", "histologic_type^Histologic type", "Invasive carcinoma \\T\\ DCIS \\F\\ grade 2", status=status),
             obx(2, "NM", "718-7^Haemoglobin^LN", "12.1", "g/dL", "12.0-15.0", status=status)]
    if pdf:
        lines.append(ed(3, pdf))
    return "\r".join(lines + list(extra)) + "\r"


@pytest.fixture
def inbox(data_root, monkeypatch):
    monkeypatch.delenv("TB_HIS_FOLDER_ROOTS", raising=False)
    _common._CACHE.clear()
    d = data_root / "his_inbox" / "hl7"
    d.mkdir(parents=True)
    return d


def run(coro):
    return asyncio.run(coro)


# ---- parsing ------------------------------------------------------------------------------------------------------------------
def test_parse_segments_fields_escapes_and_times():
    m = hl7v2.parse_message(hl7v2.split_messages(oru().encode())[0])
    assert m["type"] == "ORU" and m["trigger"] == "R01" and m["control_id"] == "M1" and m["time"] == "2026-09-05T11:00:00+05:30"
    ids = hl7v2.identifiers(m["pid"])
    assert [(i["value"], i["type"], i["kind"]) for i in ids] == [(UHID, "MR", "uhid"), ("99-2600-0000-0101", "NH", "abha")]  # the Aadhaar is dropped
    key, p, values = hl7v2.patient_of(m)
    assert key == UHID and p["name"] == NAME and p["sex"] == "F" and p["dob"] == "1980-01-18" and p["abha"] == "99-2600-0000-0101"
    assert "1234-5678-9012" not in str(p) and "1234-5678-9012" not in values
    v = hl7v2.visit_of(m)
    assert v["number"] == "OP/26/118701" and v["kind"] == "OP" and v["department"] == "Breast Surgery" and v["unit"] == "Unit I" and v["consultant"]["name"] == "Dr Kavitha Raghunathan"
    g = m["groups"][0]
    assert g["obr"].get(3) == "PATH/26/00411" and g["obr"].get(2) == "ORD-1" and g["obr"].get(4, 2) == "Histopathology report" and g["obr"].get(25) == "F"
    o1, o2 = hl7v2.observation_of(g["obx"][0]), hl7v2.observation_of(g["obx"][1])
    assert o1["value"] == "Invasive carcinoma & DCIS | grade 2" and o1["label"] == "Histologic type" and o1["status"] == "final"
    assert o2["value"] == "12.1 g/dL" and o2["reference_range"] == "12.0-15.0" and o2["code"] == {"system": "http://loinc.org", "code": "718-7", "display": "Haemoglobin"}
    assert o2["fact"] == his_client.fact_for("718-7", "Haemoglobin")
    assert hl7v2._ed_bytes(g["obx"]) == PDF
    assert hl7v2.ts("20260905") == "2026-09-05" and hl7v2.ts("202609051100") == "2026-09-05T11:00:00+05:30" and hl7v2.ts("20261341") == "" and hl7v2.ts("") == ""
    d = hl7v2.Delims()
    assert hl7v2.unescape("a\\S\\b\\R\\c\\E\\d\\.br\\e\\X0D0A\\f \\unknown\\ x", d) == "a^b~c\\d\ne\nf \\unknown\\ x"


def test_own_delimiters_from_msh_1_and_2():
    fs, enc = "#", "*!\\&"
    text = "\r".join([msh("C1", "20260905110000", fs=fs, enc=enc), pid(fs=fs, c="*", r="!"), pv1(fs=fs, c="*"),
                      fs.join(["OBR", "1", "", "LAB/26/00007*LIS", "CBC*Complete blood count*L", "", "", "20260905100000"]) + fs * 18 + "F",
                      fs.join(["OBX", "1", "ST", "note*Note", "", "pipe | and caret ^ stay; hash \\F\\ star \\S\\ bang \\R\\"]) + fs * 6 + "F"])
    m = hl7v2.parse_message(hl7v2.split_messages(text.encode())[0])
    assert hl7v2.patient_of(m)[1]["name"] == NAME and hl7v2.patient_of(m)[1]["abha"] == "99-2600-0000-0101"
    g = m["groups"][0]
    assert g["obr"].get(3) == "LAB/26/00007" and g["obr"].get(4, 2) == "Complete blood count" and g["obr"].get(25) == "F"
    assert hl7v2.observation_of(g["obx"][0])["value"] == "pipe | and caret ^ stay; hash # star * bang !"


def test_bom_mllp_bytes_newline_ends_and_several_messages_in_one_file():
    one = oru("A1").replace("\r", "\n")
    two = oru("A2", "20260906090000+0530", filler="RAD/26/00981", service="18748-4^CECT thorax^LN", pdf=None).replace("\r", "\r\n")
    raw = b"\xef\xbb\xbf\x0b" + one.encode() + b"\x1c\r" + b"\x0b" + two.encode() + b"\x1c\r"
    msgs = [hl7v2.parse_message(x) for x in hl7v2.split_messages(raw)]
    assert [m["control_id"] for m in msgs] == ["A1", "A2"] and all(m["pid"] is not None and m["groups"] for m in msgs)
    assert hl7v2._ed_bytes(msgs[0]["groups"][0]["obx"]) == PDF and hl7v2._ed_bytes(msgs[1]["groups"][0]["obx"]) is None
    assert hl7v2.split_messages(b"not hl7 at all\n") == []


def test_pdf_split_over_several_ed_segments_and_a_wrapped_line_and_a_pointer():
    b64 = base64.b64encode(PDF).decode()
    a, b, c = b64[:40], b64[40:80], b64[80:]
    parts = [obx(3, "ED", "PDF^Report", "VXHIS^AP^PDF^Base64^" + a, sub="1"), obx(4, "ED", "PDF^Report", "VXHIS^AP^PDF^Base64^" + b, sub="2"),
             obx(5, "ED", "PDF^Report", "VXHIS^AP^PDF^Base64^" + c, sub="3"), obx(6, "RP", "IMG^Scan", "file://ris/store/scan-0042.pdf^RIS^AP^PDF")]
    m = hl7v2.parse_message(hl7v2.split_messages(oru(pdf=None, extra=parts).encode())[0])
    assert hl7v2._ed_bytes(m["groups"][0]["obx"]) == PDF and hl7v2.pointers(m["groups"][0]["obx"]) == ["file://ris/store/scan-0042.pdf"]
    separately = [obx(3, "ED", "PDF^Report", "^AP^PDF^Base64^" + base64.b64encode(PDF[:50]).decode()), obx(3, "ED", "PDF^Report", "^AP^PDF^Base64^" + base64.b64encode(PDF[50:]).decode())]
    m = hl7v2.parse_message(hl7v2.split_messages(oru(pdf=None, extra=separately).encode())[0])
    assert hl7v2._ed_bytes(m["groups"][0]["obx"]) == PDF            # pieces encoded one by one, same set id
    wrapped = oru().replace(b64[:60], b64[:30] + "\r" + b64[30:60])   # a long Base64 line broken by a relay
    m = hl7v2.parse_message(hl7v2.split_messages(wrapped.encode())[0])
    assert hl7v2._ed_bytes(m["groups"][0]["obx"]) == PDF
    bad = hl7v2.parse_message(hl7v2.split_messages(oru(pdf=None, extra=[obx(3, "ED", "PDF^Report", "^AP^PDF^Base64^@@not-base64@@")]).encode())[0])
    with pytest.raises(ValueError, match="Base64"):
        hl7v2._ed_bytes(bad["groups"][0]["obx"])


# ---- the client ---------------------------------------------------------------------------------------------------------------
def test_find_patient_encounters_reports_document_and_ping(inbox):
    (inbox / "0001.hl7").write_text(oru(), newline="")
    c = HL7v2FolderClient(str(inbox), label="City LIS (SYNTHETIC)")
    ping = run(c.ping())
    assert ping["ok"] and ping["counts"]["files"] == 1 and ping["counts"]["messages"] == 1 and ping["counts"]["patients"] == 1 and ping["counts"]["reports"] == 1
    p = run(c.find_patient(UHID))
    assert p["uhid"] == UHID and p["id"] == UHID and p["name"] == NAME and p["matched_on"] == {"kind": "uhid", "value": UHID} and p["similar"] == []
    assert run(c.find_patient("op/26/118701"))["matched_on"]["kind"] == "op_no" and run(c.find_patient("99-2600-0000-0101"))["matched_on"]["kind"] == "abha"
    assert run(c.find_patient("1234-5678-9012")) is None and run(c.find_patient("VXH/26/999999")) is None and run(c.find_patient("")) is None
    encs = run(c.encounters(UHID))
    assert [(e["kind"], e["number"], e["department"]) for e in encs] == [("OP", "OP/26/118701", "Breast Surgery")]
    (r,) = run(c.reports(UHID))
    assert r["id"] == "PATH/26/00411" and r["version"] == 1 and r["current"] is True and r["status"] == "final" and r["signature"] is None
    assert r["title"] == "Histopathology report" and r["doc_type"] == "histopathology" and r["accession"] == "PATH/26/00411" and r["order_ref"] == "ORD-1"
    assert r["encounter_number"] == "OP/26/118701" and r["encounter_kind"] == "OP" and r["issued"] == "2026-09-05T11:00:00+05:30" and r["performer_department"] == "Pathology"
    assert [o["label"] for o in r["observations"]] == ["Histologic type", "Haemoglobin"] and r["document"]["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert set(his_case._HIS_KEYS) <= set(r)                       # the shape his_case files
    d = run(c.document(r["document_ref"]))
    assert d["content"] == PDF and d["sha256"] == hashlib.sha256(PDF).hexdigest() and d["filename"].endswith(".pdf") and d["content_type"] == "application/pdf"
    assert run(c.reports(UHID, "2026-09-06T00:00:00+05:30")) == [] and len(run(c.reports(UHID, "2026-09-05"))) == 1
    with pytest.raises(his_client.HISError):
        run(c.document("hl7v2:x/y/0000000000000000"))
    with pytest.raises(his_client.HISError):
        run(c.document("DocumentReference/doc-1"))
    assert run(c.open_orders(UHID)) == [] and run(c.referrals(UHID)) == [] and run(c.imaging_study("x")) is None


@pytest.mark.parametrize("code,status", [("F", "final"), ("P", "preliminary"), ("C", "corrected"), ("X", "cancelled"), ("", "unknown"), ("Z", "unknown")])
def test_status_mapping(inbox, code, status):
    (inbox / "m.hl7").write_text(oru(status=code).replace("||F\r", "||\r") if code in ("", "Z") else oru(status=code), newline="")
    (r,) = run(HL7v2FolderClient(str(inbox)).reports(UHID))
    assert r["status"] == status and r["signature"] is None


def test_two_messages_for_one_filler_number_are_versions_and_a_resend_is_not(inbox):
    (inbox / "a.hl7").write_text(oru("M1", "20260905110000+0530", "P"), newline="")
    (inbox / "b.hl7").write_text(oru("M2", "20260907100000+0530", "C", pdf=PDF2), newline="")
    (inbox / "c.hl7").write_text(oru("M3", "20260907100500+0530", "C", pdf=PDF2), newline="")   # the same content sent again
    c = HL7v2FolderClient(str(inbox))
    reps = run(c.reports(UHID))
    assert [(r["id"], r["version"], r["status"], r["current"]) for r in reps] == [("PATH/26/00411", 1, "preliminary", False), ("PATH/26/00411", 2, "corrected", True)]
    assert run(c.document(reps[0]["document_ref"]))["content"] == PDF and run(c.document(reps[1]["document_ref"]))["content"] == PDF2
    assert run(c.ping())["counts"]["skipped"] == {"the same message sent twice": 1}
    only_new = run(c.reports(UHID, "2026-09-06"))
    assert [(r["version"], r["document_ref"]) for r in only_new] == [(2, reps[1]["document_ref"])]   # the reference of a version never changes


def test_message_without_a_pdf_is_a_text_only_report_with_no_candidates(inbox):
    note = seg("NTE", {1: "1", 2: "L", 3: "Margins re-measured", 4: "AMD"})
    (inbox / "t.hl7").write_text(oru(pdf=None, extra=[obx(3, "RP", "IMG^Scan", "file://ris/scan-1.pdf^RIS^AP^PDF"), note]), newline="")
    c = HL7v2FolderClient(str(inbox))
    (r,) = run(c.reports(UHID))
    assert r["document"]["text_only"] is True and r["observations"] == [] and "text only" in r["doc_type_basis"] and "by reference, not fetched" in r["doc_type_basis"]
    assert r["amendment_note"] == "Margins re-measured"
    d = run(c.document(r["document_ref"]))
    text = d["content"].decode()
    assert d["filename"].endswith(".txt") and d["content_type"] == "text/plain" and d["text_only"] is True
    assert "Histologic type: Invasive carcinoma & DCIS | grade 2" in text and "Haemoglobin: 12.1 g/dL   (reference range 12.0-15.0)" in text
    assert f"Patient name : {NAME}   UHID : {UHID}" in text and "Report status: FINAL" in text and "Document by reference, not fetched: file://ris/scan-1.pdf" in text
    assert run(c.ping())["counts"]["skipped"] == {"a document by reference (RP), not fetched": 1}


def test_mdm_t02_document_and_open_orders_from_orm(inbox):
    txa = seg("TXA", {1: "1", 2: "DS^Discharge summary", 4: "20260924100000+0530", 6: "20260924103000+0530", 12: "DOC/26/0042", 17: "AU"})
    (inbox / "d.hl7").write_text("\r".join([msh("D1", "20260924103000+0530", "MDM^T02"), pid(), pv1("IP/26/01871", "I"), txa, ed(1, PDF)]) + "\r", newline="")
    order = seg("OBR", {1: "1", 2: "ORD-9^VXHIS", 3: "RAD/26/01200^VXHIS", 4: "CTCAP^CECT thorax abdomen pelvis", 7: "20260925090000+0530", 25: "S", 36: "20260927090000+0530"})
    (inbox / "o.hl7").write_text("\r".join([msh("O1", "20260925090000+0530", "ORM^O01"), pid(), pv1(), "ORC|NW|ORD-9^VXHIS|RAD/26/01200^VXHIS||SC", order]) + "\r", newline="")
    done = seg("OBR", {1: "1", 2: "ORD-1^VXHIS", 3: "PATH/26/00411^VXHIS", 4: "11526-1^Histopathology report^LN", 7: "20260903100000+0530", 25: "O"})
    (inbox / "p.hl7").write_text("\r".join([msh("O2", "20260903100000+0530", "ORM^O01"), pid(), pv1(), "ORC|NW|ORD-1^VXHIS", done]) + "\r", newline="")
    (inbox / "r.hl7").write_text(oru(), newline="")
    c = HL7v2FolderClient(str(inbox))
    reps = {r["id"]: r for r in run(c.reports(UHID))}
    assert reps["DOC/26/0042"]["status"] == "final" and reps["DOC/26/0042"]["title"] == "Discharge summary" and reps["DOC/26/0042"]["encounter_kind"] == "IP"
    assert run(c.find_patient("IP/26/01871"))["matched_on"]["kind"] == "ip_no"
    (o,) = run(c.open_orders(UHID))                                 # the reported order is not open
    assert o["accession"] == "RAD/26/01200" and o["stage"] == "scheduled" and o["status"] == "active" and o["test"] == "CECT thorax abdomen pelvis"
    assert o["scheduled_for"] == "2026-09-27T09:00:00+05:30" and o["encounter_number"] == "OP/26/118701" and o["doc_type"] == "ct"
    assert [e["number"] for e in run(c.encounters(UHID))] == ["OP/26/118701", "IP/26/01871"]


def test_two_patients_under_one_visit_number_need_a_person(inbox):
    (inbox / "a.hl7").write_text(oru(), newline="")
    other = "\r".join([msh("X1", "20260905120000+0530"), pid("VXH/26/004299", "Kumar (SYNTHETIC)", "Ravi"), pv1(), obr("LAB/26/1"), ed(1, PDF)]) + "\r"
    (inbox / "b.hl7").write_text(other, newline="")
    with pytest.raises(his_client.HISError, match="more than one registration"):
        run(HL7v2FolderClient(str(inbox)).find_patient("OP/26/118701"))


# ---- path safety --------------------------------------------------------------------------------------------------------------
def test_folder_must_be_inside_an_allowed_root_and_links_and_big_files_are_skipped(inbox, data_root, tmp_path_factory, monkeypatch):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret.hl7").write_text(oru("OUT"), newline="")
    for bad in (str(outside), "relative/path", str(inbox) + "/../../x", "", str(data_root / "his_inbox" / ".." / "cases")):
        with pytest.raises(ValueError):
            _common.check_folder(bad)
        assert run(HL7v2FolderClient(bad).ping())["ok"] is False
        with pytest.raises(his_client.HISError):
            run(HL7v2FolderClient(bad).find_patient(UHID))
    (data_root / "his_inbox" / "sneaky").symlink_to(outside, target_is_directory=True)      # a folder link that leaves the root
    with pytest.raises(ValueError, match="allowed folder root"):
        _common.check_folder(str(data_root / "his_inbox" / "sneaky"))
    (inbox / "good.hl7").write_text(oru(), newline="")
    (inbox / "link.hl7").symlink_to(outside / "secret.hl7")                                  # a file link that leaves the folder
    (inbox / "big.hl7").write_bytes(b"MSH|^~\\&|" + b"x" * (_common.MAX_MESSAGE_BYTES + 1))
    (inbox / "junk.hl7").write_text("hello\n")
    (inbox / "notes.pdf").write_bytes(PDF)                                                   # not a message file: ignored
    c = HL7v2FolderClient(str(inbox))
    ping = run(c.ping())
    assert ping["ok"] and ping["counts"]["files"] == 2 and ping["counts"]["messages"] == 1
    assert ping["counts"]["skipped"] == {"a link that leaves the folder": 1, "larger than 5 MiB": 1, "no MSH segment": 1}
    assert [r["id"] for r in run(c.reports(UHID))] == ["PATH/26/00411"]
    monkeypatch.setenv("TB_HIS_FOLDER_ROOTS", str(outside))                                  # the root is configurable
    assert _common.check_folder(str(outside)) == outside.resolve()
    with pytest.raises(ValueError):
        _common.check_folder(str(inbox))
    assert run(HL7v2FolderClient(str(data_root / "his_inbox" / "missing")).ping())["ok"] is False
    assert not any(p.name.startswith(".") for p in inbox.iterdir()) and sorted(os.listdir(inbox)) == ["big.hl7", "good.hl7", "junk.hl7", "link.hl7", "notes.pdf"]  # read only


# ---- through the Case File ----------------------------------------------------------------------------------------------------
def test_lookup_and_create_a_case_file_from_the_hl7_folder(inbox, fakes, monkeypatch):
    (inbox / "a.hl7").write_text(oru("M1", "20260905110000+0530", "P"), newline="")
    (inbox / "b.hl7").write_text(oru("M2", "20260907100000+0530", "C", pdf=PDF2), newline="")
    client = HL7v2FolderClient(str(inbox), label="City LIS (SYNTHETIC)")
    monkeypatch.setattr(his_client, "client", lambda *a, **k: client)
    look = run(his_case.lookup("OP/26/118701", {"all": True}))
    assert look["found"] and look["patient"]["uhid"] == UHID and look["reports"] == 1 and look["his"] == "City LIS (SYNTHETIC)"
    assert look["encounters"][0]["number"] == "OP/26/118701" and run(his_case.lookup("VXH/26/000000"))["found"] is False

    async def go():
        out = await his_case.create(UHID, "breast", "early", "optimal", "", {"all": True}, "dr.breast", ROLES_DOC)
        await out["job"]["task"]
        return out
    out = run(go())
    case = out["case"]
    assert case["patient"]["mrn"] == UHID and case["his"]["kind"] == "hl7v2_folder" and out["job"]["his"]["added"] == 2 and out["job"]["his"]["errors"] == []
    docs = sorted(store.list_docs(case["case_id"]), key=lambda d: d["his"]["version"])
    assert [(d["his"]["id"], d["his"]["version"], d["his"]["status"], bool(d.get("superseded"))) for d in docs] == [
        ("PATH/26/00411", 1, "preliminary", True), ("PATH/26/00411", 2, "corrected", False)]
    cur = docs[1]
    assert cur["source"] == "his" and cur["ext"] == ".pdf" and cur["state"] == "ready" and cur["sha256"] == hashlib.sha256(PDF2).hexdigest()
    assert cur["classification"]["status"] == "CORRECTED" and cur["classification"]["status_source"] == "his" and cur["classification"]["signed"] != "yes"
    assert cur["his"]["signature"] is None and cur["his"]["accession"] == "PATH/26/00411" and cur["department"] == "pathology"
    assert cur["rel_path"] == "HIS/OP_26_118701/Histopathology_report_v2.pdf"
    assert all(f.get("verification") != "verified" or f.get("quote") for f in cur.get("facts", {}).values())


def test_the_demo_hospitals_own_hl7_feed_is_read(inbox):
    """The demo hospital writes an HL7 v2-style event feed (his_mock.hl7, one file, many messages): the adapter reads it as it is."""
    from his_mock import generator, scenarios
    from his_mock import hl7 as mock_hl7
    s = generator.build_store(scenarios.load())[0]
    n = mock_hl7.write_feed(s, inbox / "events.hl7")
    c = HL7v2FolderClient(str(inbox), label="Vaidyx Demo Hospital feed (SYNTHETIC)")
    ping = run(c.ping())
    assert ping["ok"] and ping["counts"]["messages"] == n and ping["counts"]["patients"] == len(s.patients) and ping["counts"]["skipped"] == {}
    p = run(c.find_patient(UHID))
    assert p["name"] == NAME and p["sex"] == "F" and p["dob"] == "1980-01-18" and p["abha"] == "99-2600-0000-0101" and p["pmjay_id"].startswith("PMJAY-")
    assert run(c.find_patient("IP/26/01871"))["uhid"] == UHID
    assert [(e["kind"], e["number"]) for e in run(c.encounters(UHID))] == [("OP", "OP/26/118701"), ("OP", "OP/26/118702"), ("IP", "IP/26/01871")]
    reps = {r["accession"]: r for r in run(c.reports(UHID)) if r["current"]}
    hpe = reps["PATH/26/00411"]
    assert hpe["status"] == "final" and hpe["doc_type"] == "histopathology" and hpe["encounter_number"] == "OP/26/118701" and hpe["reported_by"]["name"].startswith("Dr ")
    assert hpe["signature"] is None and hpe["document"]["text_only"] is True and hpe["observations"] == []      # the feed carries no PDF
    text = run(c.document(hpe["document_ref"]))["content"].decode()
    assert f"UHID : {UHID}" in text and "Report status: FINAL" in text and "Accession No. : PATH/26/00411" in text
    every = [r for pid in list(run(c._idx())["reports"]) for r in run(c.reports(pid))]
    assert {r["status"] for r in every} <= {"final", "preliminary", "corrected", "cancelled"} and any(r["version"] > 1 for r in every)
