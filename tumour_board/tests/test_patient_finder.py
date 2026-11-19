"""Find a patient by name or words on the New Case File page (docs/new-case/DESIGN.md N1 to N5, piece NC-A): the matching built for
Indian names (spelling fold, titles, initials, typing mistakes, words in any order, parts of a number), the word search with the
oncology short forms, the per-hospital index built from a FHIR hospital system (paging, visits, report text from the PDF, only what
changed on a refresh, owner-only files), GET /his/find (the lookup's gate, a guest reviewer refused, audited, Case File badges, the
hospital system down, no hospital system), two hospitals that never mix, the speed on 50,000 patients, and the Case File a hospital
doctor makes by hand (POST /cases without an id, the duplicate check on the number). The hospital system is an in-memory FHIR server
behind httpx.MockTransport; synthetic names only; no network and no model."""
import asyncio
import base64
import hashlib
import json
import os
import random
import stat
import time
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tumour_board import config, hospitals, his_client, org, patient_finder as pf, store
from tumour_board.tests.test_nik_me import ANIL, RAO, RAVI, MEHTA, VX, Api, FakeAuth, auth, people  # noqa: F401 (fixtures)

TODAY = date.today()


def day(n_days_ago: int) -> str:
    return (TODAY - timedelta(days=n_days_ago)).isoformat()


def tiny_pdf(text: str) -> bytes:
    """A one-page PDF with a text layer (Helvetica), enough for pypdf."""
    stream = f"BT /F1 11 Tf 40 760 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)


# ---- an in-memory FHIR hospital system ------------------------------------------------------------------------------------------

def _patient(pid, uhid, name, gender="female", dob="1972-03-04"):
    return {"resourceType": "Patient", "id": pid, "meta": {"lastUpdated": day(400) + "T08:00:00+05:30"},
            "identifier": [{"type": {"coding": [{"code": "MR"}]}, "system": "https://his.example/identifier/uhid", "value": uhid}],
            "name": [{"text": name}], "gender": gender, "birthDate": dob}


def _encounter(eid, pid, dept, when, number, doctor="Dr Kavitha (SYNTHETIC)"):
    return {"resourceType": "Encounter", "id": eid, "meta": {"lastUpdated": when + "T09:00:00+05:30"},
            "identifier": [{"type": {"coding": [{"code": "VN"}]}, "value": number}], "class": {"code": "AMB"},
            "serviceType": {"text": f"{dept}, Unit I"}, "serviceProvider": {"display": dept}, "subject": {"reference": f"Patient/{pid}"},
            "participant": [{"individual": {"reference": "Practitioner/x", "display": doctor}}], "period": {"start": when}}


class MockHIS:
    """Patient, Encounter, DiagnosticReport and DocumentReference with paging (_count, _offset, next links), Patient?name= (contains),
    _lastUpdated=ge, a DocumentReference read and its file. `down` makes every call fail to connect."""

    def __init__(self):
        self.res = {"Patient": {}, "Encounter": {}, "DiagnosticReport": {}, "DocumentReference": {}}
        self.files, self.calls, self.down = {}, [], False

    def add(self, r):
        self.res[r["resourceType"]][r["id"]] = r

    def report(self, did, pid, rid, version, title, when, content: bytes, ctype="text/plain", inline=True, status="current", lu=None):
        sha = hashlib.sha256(content).hexdigest()
        att = {"contentType": ctype, "title": title, "creation": when}
        if inline:
            att["data"] = base64.b64encode(content).decode()
        else:
            att["url"] = f"/documents/{did}"
            self.files[did] = content
        self.add({"resourceType": "DocumentReference", "id": did, "meta": {"versionId": str(version), "lastUpdated": lu or when + "T10:00:00+05:30"},
                  "extension": [{"url": "https://his.example/StructureDefinition/document-sha256", "valueString": sha}],
                  "masterIdentifier": {"value": f"{rid}-v{version}"}, "status": status, "description": title,
                  "subject": {"reference": f"Patient/{pid}"}, "date": when + "T10:00:00+05:30", "content": [{"attachment": att}],
                  "context": {"related": [{"reference": f"DiagnosticReport/{rid}"}]}})
        self.add({"resourceType": "DiagnosticReport", "id": rid, "meta": {"versionId": str(version), "lastUpdated": lu or when + "T10:00:00+05:30"},
                  "status": "final", "code": {"text": title}, "subject": {"reference": f"Patient/{pid}"}, "issued": when + "T10:00:00+05:30"})

    def handler(self, request: httpx.Request):
        if self.down:
            raise httpx.ConnectError("connection refused", request=request)
        u = urlsplit(str(request.url))
        q = parse_qsl(u.query)
        self.calls.append((u.path, q))
        if u.path.startswith("/documents/"):
            return httpx.Response(200, content=self.files[u.path.rsplit("/", 1)[-1]])
        parts = u.path.split("/")[2:]  # /fhir/<type>[/<id>]
        rtype = parts[0]
        if len(parts) == 2:
            r = self.res.get(rtype, {}).get(parts[1])
            return httpx.Response(200, json=r) if r else httpx.Response(404, json={"resourceType": "OperationOutcome"})
        items = list(self.res.get(rtype, {}).values())
        params = dict(q)
        if "patient" in params:
            items = [x for x in items if (x.get("subject") or {}).get("reference") == "Patient/" + params["patient"]]
        if "name" in params:
            items = [p for p in items if params["name"].lower() in p["name"][0]["text"].lower()]
        if "_lastUpdated" in params:
            cut = params["_lastUpdated"][2:]
            items = [x for x in items if his_client._parse_time(x["meta"]["lastUpdated"]) >= his_client._parse_time(cut)]
        count, off = int(params.get("_count", 50)), int(params.get("_offset", 0))
        page = items[off:off + count]
        links = [{"relation": "self", "url": str(request.url)}]
        if off + count < len(items):
            nq = [(k, v) for k, v in q if k != "_offset"] + [("_offset", str(off + count))]
            links.append({"relation": "next", "url": "http://his.test/fhir/" + rtype + "?" + "&".join(f"{k}={v}" for k, v in nq)})
        return httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "total": len(items), "link": links,
                                         "entry": [{"resource": r} for r in page]})

    def client(self):
        return his_client.FHIRClient("http://his.test", "test-token", label="Test HIS (SYNTHETIC)", transport=httpx.MockTransport(self.handler))


UHID_PRIYA = "VXH/26/004219"


def demo_his() -> MockHIS:
    h = MockHIS()
    h.add(_patient("p1", "VXH/26/004203", "Lakshmi Narayanan (SYNTHETIC)"))
    h.add(_patient("p2", UHID_PRIYA, "Priya Venkatesan (SYNTHETIC)"))
    h.add(_patient("p3", "VXH/26/004212", "Mr. Venkatesh Rao (SYNTHETIC)", gender="male", dob="1959-10-19"))
    h.add(_patient("p4", "VXH/26/004230", "Smt Laxmi Devi (SYNTHETIC)"))
    h.add(_patient("p5", "VXH/26/004231", "Kumari Kavitha Iyer (SYNTHETIC)"))
    h.add(_patient("p6", "VXH/26/004232", "Mohammed Abdul Khan (SYNTHETIC)", gender="male"))
    h.add(_encounter("e1", "p1", "Breast Surgery", day(20), "OP/26/118701"))
    h.add(_encounter("e2", "p2", "Breast Surgery", day(55), "OP/26/118702"))
    h.add(_encounter("e2b", "p2", "Medical Oncology", day(10), "OP/26/118799"))
    h.add(_encounter("e3", "p3", "Pulmonology", day(70), "OP/26/118703"))
    h.add(_encounter("e4", "p4", "Gynaecologic Oncology", day(5), "IP/26/01871"))
    h.add(_encounter("e6", "p6", "Medical Oncology", day(30), "OP/26/118706"))
    h.report("doc-r1-v1", "p2", "r1", 1, "Histopathology report (biopsy)", day(50),
             b"HISTOPATHOLOGY REPORT. Diagnosis: Invasive ductal carcinoma of the left breast, grade 2. Report status: FINAL")
    h.report("doc-r2-v1", "p2", "r2", 1, "OPD consultation note", day(12),
             tiny_pdf("Plan: neoadjuvant chemotherapy, four cycles, then surgery."), ctype="application/pdf", inline=False)
    h.report("doc-r3-v1", "p3", "r3", 1, "CECT thorax", day(65), b"CECT THORAX. Impression: right lung mass with liver metastases.")
    h.report("doc-r4-v1", "p6", "r4", 1, "PET-CT", day(28), b"PET CT whole body. No distant disease.")
    h.report("doc-r5-v1", "p1", "r5", 1, "Old discharge summary", day(900), b"Discharge summary. Radiotherapy completed. Lymphoedema clinic.")
    return h


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def finder(data_root):
    pf.reset()
    yield
    pf.reset()


def rows(idx_or_out, q=None):
    """Names (without the SYNTHETIC tag) in rank order."""
    if q is not None:
        return [idx_or_out.rows[i]["name"].replace(" (SYNTHETIC)", "") for _s, _d, i, _on, _t in idx_or_out.search(q)]
    return [r["name"].replace(" (SYNTHETIC)", "") for r in idx_or_out["results"]]


# ---- words and names ------------------------------------------------------------------------------------------------------------

def test_fold_titles_and_typo_rule():
    assert pf.fold("lakshmi") == pf.fold("laxmi") == "laksmi"
    assert pf.fold("venkatesh") == pf.fold("wenkatesh") == "venkates"
    assert pf.fold("bhaskar") == "baskar" and pf.fold("thilak") == "tilak" and pf.fold("phani") == "fani" and pf.fold("meena") == "mina"
    assert pf.fold("abdullah") == "abdula" and pf.fold("ghosh") == "gos"
    assert pf.name_words("Smt. Laxmi Devi (SYNTHETIC)") == ["laxmi", "devi"]
    assert pf.name_words("Kumari Kavitha Iyer") == ["kavitha", "iyer"] and pf.name_words("Priya Kumari") == ["priya", "kumari"]
    assert pf.name_words("Baby") == ["baby"] and pf.name_words("Dr. Mr P. Venkatesan") == ["p", "venkatesan"]
    assert [pf.typos_allowed(w) for w in ("rao", "ravi", "kavita", "lakshmi")] == [0, 1, 1, 2]


@pytest.fixture
def index(finder):
    return run(_built(demo_his()))


async def _built(h):
    await pf.build(h.client(), full=True)
    return pf._state()["index"]


def test_names_spelling_titles_typos_initials_and_any_order(index):
    assert rows(index, "lakshmi")[:2] == ["Lakshmi Narayanan", "Smt Laxmi Devi"]  # the exact word first, the folded spelling next
    assert set(rows(index, "laxmi")[:2]) == {"Lakshmi Narayanan", "Smt Laxmi Devi"}
    assert rows(index, "venkatesen")[:2] == ["Priya Venkatesan", "Mr. Venkatesh Rao"]  # one typing mistake in a long word
    assert rows(index, "venkatsan")[0] == "Priya Venkatesan"  # one letter left out (two allowed at 7+ letters)
    assert rows(index, "p venkatesan")[0] == "Priya Venkatesan"  # an initial typed
    assert rows(index, "priya v")[0] == "Priya Venkatesan"
    assert rows(index, "venkatesan priya")[0] == "Priya Venkatesan"  # words in any order
    assert rows(index, "mrs kavita iyer")[0] == "Kumari Kavitha Iyer"  # titles dropped, th folded
    assert rows(index, "abdul")[0] == "Mohammed Abdul Khan"
    assert "Mr. Venkatesh Rao" not in rows(index, "rso")  # no typing mistake allowed in a 3-letter word
    assert rows(index, "zzzz") == []
    s = {index.rows[i]["name"]: (sc, on) for sc, _d, i, on, _t in index.search("lakshmi")}
    assert s["Lakshmi Narayanan (SYNTHETIC)"][1] == "name" and s["Lakshmi Narayanan (SYNTHETIC)"][0] >= 900
    near = {index.rows[i]["name"]: sc for sc, _d, i, _on, _t in index.search("venkatesen")}
    assert 600 <= near["Priya Venkatesan (SYNTHETIC)"] < 800  # a near name ranks below a full name


def test_words_with_oncology_short_forms_prefixes_and_snippets(index):
    assert rows(index, "chemo") == ["Priya Venkatesan"]  # "chemotherapy" in the PDF's text layer
    assert rows(index, "nact")[0] == "Priya Venkatesan"  # neoadjuvant
    assert rows(index, "idc")[0] == "Priya Venkatesan"  # "invasive ductal" (both words)
    assert rows(index, "ca breast")[0] == "Priya Venkatesan"  # carcinoma ... breast
    assert rows(index, "mets") == ["Mr. Venkatesh Rao"]  # metastases
    assert rows(index, "histopath")[0] == "Priya Venkatesan"  # the start of a word of 4+ letters
    assert rows(index, "cect lung")[0] == "Mr. Venkatesh Rao"
    assert rows(index, "pet ct")[0] == "Mohammed Abdul Khan"
    assert rows(index, "chemo liver") == []  # every word must match the same patient
    assert rows(index, "radiotherapy") == []  # report text older than 24 months is not kept
    assert rows(index, "breast surgery")[:2] == ["Priya Venkatesan", "Lakshmi Narayanan"]  # the visits' department; ties by the latest visit
    sc, _d, i, on, terms = index.search("chemo")[0]
    m = index.matched(i, on, terms)
    assert on == "words" and m["on"] == "words" and "chemotherapy" in m["terms"] and 300 <= sc < 600
    assert "chemotherapy" in m["snippet"].lower() and len(m["snippet"]) <= pf.SNIPPET and m["source"].startswith("OPD consultation note")


def test_parts_of_a_number_and_the_rank_order(index):
    for q in ("4219", "004219", "26/004219"):
        top = index.search(q)[0]
        assert index.rows[top[2]]["uhid"] == UHID_PRIYA and top[3] == "identifier" and 800 <= top[0] < 900, q
    for q in (UHID_PRIYA, "vxh 26 004219", "OP/26/118702"):
        top = index.search(q)[0]
        assert index.rows[top[2]]["uhid"] == UHID_PRIYA and top[0] == 1000, q
    assert index.search("42")[:1] == []  # two digits: not a part of a number
    # exact number > full name > near name > words
    assert pf.Index([]).search("x") == []


def test_snippet_is_short_and_around_the_most_matched_words():
    text = "Patient seen in Breast Surgery. " + "Unrelated text. " * 20 + "Diagnosis: carcinoma of the left breast, grade 2. " + "More. " * 30
    s = pf.snippet_around(text, ["carcinoma", "breast"])
    assert "carcinoma" in s and "left breast" in s and len(s) <= pf.SNIPPET and s.startswith("...")
    assert pf.snippet_around("nothing here", ["chemo"]) == ""


# ---- the index ------------------------------------------------------------------------------------------------------------------

def test_index_build_pages_reads_visits_and_text_and_refreshes_only_what_changed(finder, monkeypatch):
    monkeypatch.setattr(pf, "PAGE", 2)  # several pages of every type
    h = demo_his()
    out = run(pf.build(h.client(), full=True))
    assert out["patients"] == 6 and out["full"] is True and out["texts"] == 4 and out["downloaded"] == 4  # the 900-day-old one is left out
    assert sum(1 for p, q in h.calls if p == "/fhir/Patient" and dict(q).get("_offset")) >= 2  # followed the next links
    assert [p for p, _q in h.calls if p.startswith("/documents/")] == ["/documents/doc-r2-v1"]  # only the file not in the listing
    idx = pf._state()["index"]
    priya = next(r for r in idx.rows if r["uhid"] == UHID_PRIYA)
    assert priya["last_visit"] == {"department": "Medical Oncology", "date": day(10)} and priya["age"] is not None and priya["sex"] == "F"
    d = config.DATA_ROOT / pf.INDEX_DIR
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    for f in ("index.json", "texts.json"):
        assert stat.S_IMODE(os.stat(d / f).st_mode) == 0o600
    texts = json.loads((d / "texts.json").read_text())
    assert set(texts) == {"r1@v1", "r2@v1", "r3@v1", "r4@v1"} and all(len(v["t"]) <= pf.TEXT_CHARS for v in texts.values())
    # a refresh: only the changed resources are asked for, nothing unchanged is downloaded again
    h.calls.clear()
    out = run(pf.build(h.client()))
    assert out["full"] is False and out["downloaded"] == 0
    assert all(dict(q).get("_lastUpdated", "").startswith("ge") for p, q in h.calls if p.startswith("/fhir/"))
    # a new version of one report: only that one is downloaded, the old version's text goes
    now = his_client._iso(his_client._parse_time(TODAY.isoformat()) + timedelta(days=1))
    h.res["DocumentReference"]["doc-r1-v1"]["status"] = "superseded"
    h.res["DocumentReference"]["doc-r1-v1"]["meta"]["lastUpdated"] = now
    h.report("doc-r1-v2", "p2", "r1", 2, "Histopathology report (biopsy)", day(3), b"AMENDED: invasive lobular carcinoma.", lu=now)
    out = run(pf.build(h.client()))
    assert out["downloaded"] == 1
    texts = json.loads((d / "texts.json").read_text())
    assert "r1@v2" in texts and "r1@v1" not in texts
    idx = pf._state()["index"]
    assert [idx.rows[i]["uhid"] for _s, _dd, i, _o, _t in idx.search("lobular")] == [UHID_PRIYA]
    assert idx.search("ductal") == []


def test_files_beyond_the_inline_room_are_downloaded_and_a_restart_reads_the_saved_index(finder, monkeypatch):
    monkeypatch.setattr(pf, "INLINE_BYTES", 0)
    h = demo_his()
    assert run(pf.build(h.client(), full=True))["downloaded"] == 4
    assert sum(1 for p, _q in h.calls if p.startswith("/fhir/DocumentReference/")) == 4  # each read by itself
    # a restart: the saved index answers at once, nothing is asked of the hospital system while it is fresh
    pf.reset()
    h.calls.clear()
    monkeypatch.setattr(his_client, "client", lambda *a, **k: h.client())
    run(pf._run())
    assert h.calls == [] and len(pf._state()["index"]) == 6 and pf.index_status()["patients"] == 6


def test_another_hospital_system_starts_over_and_a_system_that_cannot_list_leaves_it_empty(finder, monkeypatch):
    run(pf.build(demo_his().client(), full=True))
    assert len(pf._state()["index"]) == 6
    monkeypatch.setattr(pf, "his_signature", lambda settings=None: "another")
    run(pf.build(MockHIS().client()))
    assert len(pf._state()["index"]) == 0 and json.loads((config.DATA_ROOT / pf.INDEX_DIR / "index.json").read_text())["his"] == "another"

    class NoList(his_client.HISClient):
        kind, label = "hl7v2_folder", "Folder (SYNTHETIC)"
    out = run(pf.build(NoList()))
    assert out["patients"] == 0 and len(pf._state()["index"]) == 0


# ---- GET /his/find -----------------------------------------------------------------------------------------------------------------

@pytest.fixture
def app(auth, finder, monkeypatch):
    import routes.tumour_board_routes as R
    monkeypatch.setattr(R, "_warm", lambda: None)
    monkeypatch.setenv("TB_SCHEDULER", "0")
    h = demo_his()
    cl = h.client()
    monkeypatch.setattr(his_client, "client", lambda *a, **k: cl)
    a = FastAPI()
    who = {"user": RAO}

    @a.middleware("http")
    async def _signed_in(request, call_next):
        request.state.current_user = who["user"]
        return await call_next(request)
    a.include_router(R.setup_tumour_board_routes())
    a.state.auth_manager = auth
    with TestClient(a) as tc:
        api = Api(tc, who)
        api.his = h
        yield api


def audit_lines(kind):
    return [e for e in org.read_audit(500) if e.get("kind") == kind]


def test_find_answers_rows_with_visits_badges_and_sources(app):
    run(pf.build(app.his.client(), full=True))
    c = store.create_case("TB-2026-0007", {"name": "Priya Venkatesan (SYNTHETIC)", "mrn": "vxh-26-004219"}, "breast", created_by=RAO)
    c["department"] = "breast_surgery"; store.save_case(c)
    hidden = store.create_case("TB-2026-bharath", {"name": "Priya Venkatesan (SYNTHETIC)", "mrn": UHID_PRIYA}, "breast", created_by=RAO)  # protected: never shown
    assert hidden
    r = app.as_(RAO).get("/his/find", params={"q": "priya venkatesen"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["q"] == "priya venkatesen" and b["sources"]["his_live"] is True
    assert b["sources"]["index"]["patients"] == 6 and b["sources"]["index"]["built_at"] and b["sources"]["index"]["building"] is False
    top = b["results"][0]
    assert top["uhid"] == UHID_PRIYA and top["sex"] == "F" and top["last_visit"] == {"department": "Medical Oncology", "date": day(10)}
    assert top["matched"]["on"] == "name" and isinstance(top["score"], int)
    assert [f["case_id"] for f in top["case_files"]] == ["TB-2026-0007"]
    assert top["case_files"][0]["department"] == "Breast Surgery" and top["case_files"][0]["can_open"] is True and top["case_files"][0]["status"]
    assert "TB-2026-bharath" not in r.text
    # words, with the snippet
    w = app.as_(RAO).get("/his/find", params={"q": "chemo"}).json()["results"]
    assert w[0]["uhid"] == UHID_PRIYA and w[0]["matched"]["on"] == "words" and "chemotherapy" in w[0]["matched"]["snippet"].lower()
    assert len(w[0]["matched"]["snippet"]) <= 120
    # at most 8 rows; a one-letter query asks nothing
    for i in range(12):
        app.his.add(_patient(f"x{i}", f"VXH/26/0050{i:02d}", f"Ravi Kumar{i} (SYNTHETIC)", gender="male"))
    run(pf.build(app.his.client(), full=True))
    assert len(app.as_(RAO).get("/his/find", params={"q": "ravi"}).json()["results"]) == 8
    assert app.as_(RAO).get("/his/find", params={"q": "r"}).json()["results"] == []
    lines = audit_lines("patient_find")  # newest first
    assert [(e["by"], e["q"], e["results"]) for e in lines[:1]] == [(RAO, "r", 0)] and any(e["q"] == "priya venkatesen" and e["results"] >= 1 for e in lines)


def test_find_has_the_lookup_gate_and_refuses_a_guest_reviewer(app, monkeypatch):
    run(pf.build(app.his.client(), full=True))
    assert app.as_(RAVI).get("/his/find", params={"q": "priya"}).status_code == 403  # a supporting doctor does not start Case Files
    o = org.load(); o["users"]["guest.reviewer@example.org"] = {"departments": {"breast_surgery": "member"}, "display_name": "Guest (synthetic)", "real_data": True}
    org.save(o, by="test")
    r = app.as_("guest.reviewer@example.org").get("/his/find", params={"q": "priya"})
    assert r.status_code == 403
    assert not any(e.get("by") == "guest.reviewer@example.org" for e in audit_lines("patient_find"))
    # the handler refuses a guest too (not only the route class)
    import routes.tumour_board_routes as R
    monkeypatch.setattr(R, "_GUEST_NEVER", __import__("re").compile(r"^$"))
    monkeypatch.setenv("TB_REAL_DATA_2FA", "0")
    r = app.as_("guest.reviewer@example.org").get("/his/find", params={"q": "priya"})
    assert r.status_code == 403 and "guest reviewer" in r.text and "Priya" not in r.text
    assert app.as_(MEHTA).get("/his/find", params={"q": "priya"}).status_code == 200


def test_find_while_the_index_is_built_answers_from_the_live_search(app):
    r = app.as_(RAO).get("/his/find", params={"q": "venkatesan"})
    b = r.json()
    assert r.status_code == 200 and b["sources"]["his_live"] is True
    assert b["results"][0]["uhid"] == UHID_PRIYA and b["results"][0]["from"] in ("live", "his")
    assert any(p == "/fhir/Patient" and ("name", "venkatesan") in q for p, q in app.his.calls)
    # the live row carries its last visit too
    assert b["results"][0]["last_visit"]["department"] in ("Medical Oncology", "Breast Surgery")


def test_find_with_the_hospital_system_down_still_shows_case_files(app, monkeypatch):
    c = store.create_case("TB-2026-0011", {"name": "Lakshmi Narayanan (SYNTHETIC)", "mrn": "VXH/26/004203", "agesex": "58 Y / F"}, "breast", created_by=RAO)
    c["department"] = "breast_surgery"; store.save_case(c)
    app.his.down = True
    b = app.as_(RAO).get("/his/find", params={"q": "laxmi"}).json()
    assert b["sources"]["his_live"] is False
    assert [(r["uhid"], r["from"], r["age"], r["sex"]) for r in b["results"]] == [("VXH/26/004203", "case_file", 58, "F")]
    assert b["results"][0]["case_files"][0]["case_id"] == "TB-2026-0011"


def test_find_without_a_hospital_system_uses_the_case_files_and_their_words_only_for_readers(app, monkeypatch):
    monkeypatch.setattr(his_client, "client", lambda *a, **k: None)
    c = store.create_case("TB-2026-0012", {"name": "Kamala Bai (SYNTHETIC)", "agesex": "45 Y / F"}, "breast", created_by=RAO)
    c["department"] = "breast_surgery"; store.save_case(c)
    b = app.as_(RAO).get("/his/find", params={"q": "kamla"}).json()
    assert b["sources"] == {"his_live": False, "index": {"patients": 0, "built_at": None, "building": False}}
    assert [(r["name"], r["uhid"], r["case_files"][0]["case_id"]) for r in b["results"]] == [("Kamala Bai (SYNTHETIC)", "", "TB-2026-0012")]
    w = app.as_(RAO).get("/his/find", params={"q": "breast"}).json()["results"]
    assert w and w[0]["matched"]["on"] == "words" and "TB-2026-0012" in w[0]["matched"]["source"]
    # a consultant of another department may not open it, and it is made by hand (the patient may not be in the hospital system at
    # all): neither its name nor its cancer finds it
    assert app.as_(MEHTA).get("/his/find", params={"q": "kamala"}).json()["results"] == []
    assert app.as_(MEHTA).get("/his/find", params={"q": "breast"}).json()["results"] == []


def test_two_hospitals_never_mix(data_root, finder):
    lotus = hospitals.create("Lotus Cancer Centre (SYNTHETIC)", by="admin")["id"]
    a = demo_his()
    b = MockHIS()
    b.add(_patient("q1", "LCC/26/000001", "Zainab Fathima (SYNTHETIC)"))
    run(pf.build(a.client(), full=True))
    with config.use_hospital(lotus):
        run(pf.build(b.client(), full=True))
        assert rows(pf._state()["index"], "zainab") == ["Zainab Fathima"] and rows(pf._state()["index"], "priya") == []
        assert (config.DATA_ROOT / pf.INDEX_DIR / "index.json").exists()
        lotus_file = config.DATA_ROOT / pf.INDEX_DIR / "index.json"
    assert rows(pf._state()["index"], "zainab") == [] and rows(pf._state()["index"], "priya")[0] == "Priya Venkatesan"
    assert "Zainab" not in (config.DATA_ROOT / pf.INDEX_DIR / "index.json").read_text() and "Priya" not in lotus_file.read_text()


def test_fifty_thousand_patients_are_searched_in_under_300_ms():
    rng = random.Random(7)
    first = ["Lakshmi", "Priya", "Venkatesh", "Sunita", "Fatima", "Harbhajan", "Anitha", "Ramesh", "Kamala", "Meena", "Arjun", "Lalitha",
             "Shobha", "Prakash", "Geetha", "Abdul", "Sarita", "Kavitha", "Revathi", "Sujatha", "Bhaskar", "Thilak"]
    last = ["Narayanan", "Venkatesan", "Rao", "Devi", "Begum", "Singh", "Reddy", "Nair", "Verma", "Patil", "Mishra", "Iyer", "Kumar", "Khan"]
    syl = ["ka", "ra", "na", "shi", "ma", "la", "vi", "pa", "ta", "su", "ni", "ja", "ya", "dha", "bha", "the"]
    vocab = ("invasive ductal carcinoma breast chemotherapy neoadjuvant cycles metastasis liver lung biopsy histopathology grade nodes mass "
             "cect thorax abdomen pelvis impression findings report final radiotherapy dose lesion margin her2 positive negative").split()
    raw = {"patients": {}, "encounters": {}, "reports": {}, "docs": {}}
    texts = {}
    for i in range(50000):
        nm = rng.choice(first + ["".join(rng.choice(syl) for _ in range(3)).capitalize()]) + " " + rng.choice(last)
        raw["patients"][f"p{i}"] = {"uhid": f"VXH/26/{i:06d}", "name": nm, "sex": "F", "dob": "1970-01-01", "ids": [f"VXH/26/{i:06d}"]}
        raw["encounters"][f"e{i}"] = {"pid": f"p{i}", "department": rng.choice(["Breast Surgery", "Medical Oncology"]), "doctor": "", "date": day(i % 300), "number": f"OP/26/{i:06d}"}
    for k in range(3000):
        raw["docs"][f"d{k}"] = {"pid": f"p{rng.randrange(50000)}", "rid": f"d{k}", "version": 1, "title": "Report", "date": day(30), "status": "current"}
        texts[f"d{k}@v1"] = {"t": " ".join(rng.choice(vocab) for _ in range(500))[:4000], "d": day(30)}
    idx = pf.compile_index(raw, texts)
    for q in ("laxmi", "venkatesen", "p venkatesan", "chemo liver", "ca breast nact", "4219", "ra"):
        best = 9.0
        for _ in range(3):
            t = time.perf_counter()
            hits = idx.search(q)
            for _s, _d, i, on, terms in hits[:8]:
                idx.matched(i, on, terms)
            best = min(best, time.perf_counter() - t)
        assert hits and best < 0.3, (q, best)


# ---- a Case File made by hand by a hospital doctor (N5) ----------------------------------------------------------------------------

def test_a_doctor_makes_a_case_file_by_hand_and_the_number_is_checked(app):
    body = {"patient": {"name": "Rukmini Bai (SYNTHETIC)", "mrn": "VXH/26/009001", "ids": [{"kind": "uhid", "value": "VXH/26/009001", "from": "manual"}],
                        "age": 61, "sex": "F", "agesex": "61 Y / F", "source": "manual"},
            "protocol": "breast", "setting": "early", "board_date": ""}
    r = app.as_(RAO).post("/cases", json=body)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["case_id"] == f"TB-{TODAY.year}-0001" and c["patient"]["name"] == "Rukmini Bai (SYNTHETIC)" and c["patient"]["mrn"] == "VXH/26/009001"
    saved = store.get_case(c["case_id"])
    assert saved["department"] == "breast_surgery" and not saved.get("private") and not saved.get("his")
    assert not (store.case_dir(c["case_id"]) / config.PRIVATE_MARKER).exists()
    # the same number and cancer again (written another way): refused with the existing owner
    r = app.as_(RAO).post("/cases", json={**body, "patient": {**body["patient"], "mrn": "vxh-26-009001"}})
    assert r.status_code == 409 and r.json()["code"] == "duplicate_case_file" and r.json()["existing"]["case_id"] == c["case_id"]
    # without a number: allowed (no duplicate check possible), the next id
    r = app.as_(RAO).post("/cases", json={**body, "patient": {"name": "Rukmini Bai (SYNTHETIC)", "age": 61, "sex": "F", "agesex": "61 Y / F"}})
    assert r.status_code == 200 and r.json()["case_id"] == f"TB-{TODAY.year}-0002"
    # the finder finds the hand-made Case File by its number and name
    b = app.as_(RAO).get("/his/find", params={"q": "9001"}).json()
    assert any(f["case_id"] == c["case_id"] for row in b["results"] for f in row["case_files"])


def test_by_hand_is_refused_where_only_guests_upload(app, monkeypatch):
    """The public site (TB_UPLOAD_POLICY=private_only): a hospital doctor could never add the reports, so no Case File by hand;
    a guest reviewer's private Case File is unchanged."""
    monkeypatch.setenv("TB_UPLOAD_POLICY", "private_only")
    body = {"patient": {"name": "Rukmini Bai (SYNTHETIC)", "age": 61, "sex": "F"}, "protocol": "breast", "setting": "early", "board_date": ""}
    r = app.as_(RAO).post("/cases", json=body)
    assert r.status_code == 403 and "Making one by hand is off" in r.text
    assert not store.list_cases()


# ---- review fixes (17 Nov): the Vaidyx admin, badges, the rate limit, the event loop, the text cap, a changed hospital system ------

def test_the_vaidyx_admin_does_not_search_or_look_up_patients_and_single_user_mode_still_does(app, monkeypatch):
    run(pf.build(app.his.client(), full=True))
    for path, params in (("/his/find", {"q": "chemo"}), ("/his/lookup", {"identifier": UHID_PRIYA})):
        r = app.as_(VX).get(path, params=params)
        assert r.status_code == 403, (path, r.text)
        assert "The Vaidyx admin does not search patients; open a Case File through break-glass." in r.text
        assert "Priya" not in r.text and UHID_PRIYA not in r.text and "chemotherapy" not in r.text
    assert not any(e.get("by") == VX for e in audit_lines("patient_find") + audit_lines("his_lookup"))
    # single-user mode (no login at all: admin, no user) works as before
    monkeypatch.setenv("AUTH_ENABLED", "false")
    r = app.as_(None).get("/his/find", params={"q": "priya"})
    assert r.status_code == 200 and r.json()["results"][0]["uhid"] == UHID_PRIYA
    from tumour_board import his_case

    async def fake_lookup(identifier, window=None):  # the mock hospital system has no identifier search; the gate is what is tested
        return {"found": True, "identifier": identifier, "patient": {"uhid": identifier}}
    monkeypatch.setattr(his_case, "lookup", fake_lookup)
    r = app.as_(None).get("/his/lookup", params={"identifier": UHID_PRIYA})
    assert r.status_code == 200 and r.json()["found"] is True
    assert app.as_(VX).get("/his/lookup", params={"identifier": UHID_PRIYA}).status_code == 403


def _his_case(case_id, cancer_name, department="breast_surgery"):
    c = store.create_case(case_id, {"name": "Priya Venkatesan (SYNTHETIC)", "mrn": UHID_PRIYA}, "breast", created_by=RAO)
    c.update(department=department, cancer_name=cancer_name, his={"kind": "fhir", "label": "Test HIS (SYNTHETIC)", "uhid": UHID_PRIYA})
    store.save_case(c)
    return c


def test_a_case_file_this_doctor_may_not_open_shows_only_that_it_exists_and_its_department(app):
    run(pf.build(app.his.client(), full=True))
    _his_case("TB-2026-0007", "Phyllodes tumour left breast (SYNTHETIC)")
    hand = store.create_case("TB-2026-0008", {"name": "Rukmini Bai (SYNTHETIC)", "mrn": "VXH/26/009001"}, "breast", created_by=RAO)
    hand["department"] = "breast_surgery"; store.save_case(hand)
    from tumour_board import access
    assert access.scope(org.roles(MEHTA), store.get_case("TB-2026-0007")) is None
    r = app.as_(MEHTA).get("/his/find", params={"q": "priya"})
    assert r.status_code == 200
    top = r.json()["results"][0]
    assert top["uhid"] == UHID_PRIYA and top["case_files"] == [{"department": "Breast Surgery", "can_open": False}]
    assert "TB-2026-0007" not in r.text and "Phyllodes" not in r.text and "Breast cancer" not in r.text
    # its cancer is no word for this doctor; the owner finds it by the cancer and sees the full badge
    assert app.as_(MEHTA).get("/his/find", params={"q": "phyllodes"}).json()["results"] == []
    own = app.as_(RAO).get("/his/find", params={"q": "phyllodes"}).json()["results"]
    assert own and own[0]["case_files"][0]["case_id"] == "TB-2026-0007" and own[0]["case_files"][0]["can_open"] is True
    assert own[0]["case_files"][0]["cancer"] and own[0]["case_files"][0]["status"]
    # a Case File made by hand: found by its name or number only by a person who may open it
    for q in ("rukmini", "9001"):
        assert app.as_(MEHTA).get("/his/find", params={"q": q}).json()["results"] == [], q
        assert [f.get("case_id") for row in app.as_(RAO).get("/his/find", params={"q": q}).json()["results"] for f in row["case_files"]] == ["TB-2026-0008"], q


def test_find_is_rate_limited_per_login_and_per_hospital(app, monkeypatch):
    from tumour_board.api.common import RateLimit
    assert (pf.FIND_PER_WINDOW, pf.FIND_WINDOW) == (120, 600) and (pf.FIND_LIMIT.limit, pf.FIND_LIMIT.window) == (120, 600)
    monkeypatch.setattr(pf, "FIND_LIMIT", RateLimit(3, 600))
    codes = [app.as_(RAO).get("/his/find", params={"q": "priya"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = app.as_(RAO).get("/his/find", params={"q": "priya"})
    assert r.status_code == 429 and "Too many searches" in r.text and "Priya" not in r.text
    assert app.as_(MEHTA).get("/his/find", params={"q": "priya"}).status_code == 200  # another login has its own count
    assert len([e for e in audit_lines("patient_find") if e["by"] == RAO]) == 3  # a refused search is not a search
    lotus = hospitals.create("Lotus Cancer Centre (SYNTHETIC)", by="admin")["id"]
    with config.use_hospital(lotus):  # the same login in another hospital: another count
        pf.check_rate(RAO)


def test_the_index_files_are_read_and_written_off_the_event_loop_and_kept_in_memory(finder, monkeypatch):
    real_write, real_read, reads = pf._write, pf._read, []

    def slow_write(p, obj):  # a big hospital's index takes seconds to write
        time.sleep(0.3)
        real_write(p, obj)
    monkeypatch.setattr(pf, "_write", slow_write)
    monkeypatch.setattr(pf, "_read", lambda p, default: reads.append(p.name) or real_read(p, default))
    h = demo_his()

    async def measure():
        gaps, stop = [], asyncio.Event()

        async def tick():
            last = time.perf_counter()
            while not stop.is_set():
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                gaps.append(now - last)
                last = now
        t = asyncio.ensure_future(tick())
        await pf.build(h.client(), full=True)
        reads_after_first = list(reads)
        await pf.build(h.client())
        stop.set()
        await t
        return max(gaps), reads_after_first
    worst, first_reads = run(measure())
    assert worst < 0.2, worst  # the loop kept answering while each 0.3 s write ran
    assert sorted(first_reads) == ["index.json", "texts.json"] and sorted(reads) == ["index.json", "texts.json"]  # the refresh read nothing
    assert len(pf._state()["index"]) == 6 and pf._state()["raw"]["his"] == pf.his_signature()


def test_report_texts_are_capped_newest_first_and_the_dropped_ones_are_not_downloaded_again(finder, monkeypatch):
    assert pf.TEXTS_KEPT == 20_000
    monkeypatch.setattr(pf, "TEXTS_KEPT", 2)
    h = demo_his()
    out = run(pf.build(h.client(), full=True))
    texts = json.loads((config.DATA_ROOT / pf.INDEX_DIR / "texts.json").read_text())
    assert set(texts) == {"r2@v1", "r4@v1"} and out["texts"] == 2 and out["downloaded"] == 2  # 12 and 28 days old; 50 and 65 left out
    assert run(pf.build(h.client(), full=True))["downloaded"] == 0
    idx = pf._state()["index"]
    assert rows(idx, "chemo") == ["Priya Venkatesan"] and rows(idx, "lobular") == [] and rows(idx, "metastases") == []


def test_a_changed_hospital_system_never_answers_from_the_old_index_and_supersedes_its_build(people, finder, monkeypatch):
    signature = pf.his_signature
    run(pf.build(demo_his().client(), full=True))
    old = pf._state()["sig"]
    assert old and pf._state()["index"] is not None
    empty = MockHIS()
    monkeypatch.setattr(his_client, "client", lambda *a, **k: empty.client())

    async def main():
        st = pf._state()
        running = asyncio.get_running_loop().create_future()  # a build of the old system still running
        st.update(task=running, task_sig=old)
        monkeypatch.setattr(pf, "his_signature", lambda settings=None: "another-system")
        out = await pf.find("priya", org.roles(RAO), client=empty.client())
        return out, running, st.get("task") is not running and st.get("task_sig") == "another-system"
    out, running, replaced = run(main())
    assert [r["uhid"] for r in out["results"]] == [] and out["sources"]["index"]["patients"] == 0
    assert running.cancelled() and replaced
    # the signature covers which identifier is the UHID (and its preset), not only where the system is
    base = {"kind": "fhir_generic", "label": "HIS", "url": "https://his.example", "adapter": {"base_path": "/fhir", "identifier_systems": ["urn:a"]}}
    other = {**base, "adapter": {**base["adapter"], "identifier_systems": ["urn:b"]}}
    preset = {**base, "adapter": {**base["adapter"], "preset": "openmrs"}}
    assert len({signature(base), signature(other), signature(preset)}) == 3


def test_the_case_file_list_is_cached_per_hospital_and_read_in_a_thread(people, finder, monkeypatch):
    import threading
    calls, real = [], store.list_cases
    monkeypatch.setattr(store, "list_cases", lambda: calls.append(threading.get_ident()) or real())
    c = store.create_case("TB-2026-0011", {"name": "Lakshmi Narayanan (SYNTHETIC)", "mrn": "VXH/26/004203"}, "breast", created_by=RAO)
    c["department"] = "breast_surgery"; store.save_case(c)
    rl = org.roles(RAO)

    async def two():
        a = await pf.find("lakshmi", rl, client=None)
        b = await pf.find("lakshmi", org.roles(MEHTA), client=None)  # another login: the same cached list, its own scope
        return a, b, threading.get_ident()
    a, b, loop_thread = run(two())
    assert len(calls) == 1 and calls[0] != loop_thread
    assert a["results"][0]["case_files"][0]["case_id"] == "TB-2026-0011" and b["results"] == []
    store.create_case("TB-2026-0012", {"name": "Lakshmi Devi (SYNTHETIC)", "mrn": "VXH/26/004299"}, "breast", created_by=RAO)
    out = run(pf.find("lakshmi", rl, client=None))  # a new Case File: the folder changed, the list is read again at once
    assert len(calls) == 2 and len(out["results"]) == 2
