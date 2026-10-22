"""Guided set-up, accounts and the organisation of the new interface (18 Oct 2026): the five steps saved at once (hospital, departments,
people, hospital system, board), the HIS test, email logins with a generated first password inside a mailto (never logged), resets by the
department admin and the root admin, residents with end dates, auditors, the V3 departments and the V2 to V3 migration of org.json.
Synthetic logins only, a fake login system and a fake HIS; the conftest temporary data root."""
import copy, json, logging, urllib.parse

import pytest

from tumour_board import accounts, his_client, org
from tumour_board.tests.test_nik_me import (ANIL, ASHA, AUDIT, DEEPAK, RAO, RAVI, ROOT, VX, Api, FakeAuth, api, auth,  # noqa: F401
                                            people)


def password_in(mailto: str) -> str:
    body = urllib.parse.parse_qs(mailto.split("?", 1)[1])["body"][0]
    return next(line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("First password: "))


def everything_stored(root) -> str:
    """Every file under the temporary data root, as text (the password must be in none of them)."""
    out = []
    for p in root.rglob("*"):
        if p.is_file():
            try:
                out.append(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return "\n".join(out)


@pytest.fixture(autouse=True)
def no_real_his_token(tmp_path, monkeypatch):
    """The HIS token file of the demo is never read here: a synthetic one in the temporary root."""
    f = tmp_path / "his_token_synthetic"
    f.write_text("synthetic-file-token\n")
    monkeypatch.setenv("TB_HIS_TOKEN_FILE", str(f))
    monkeypatch.delenv("TB_HIS_URL", raising=False)
    monkeypatch.delenv("TB_HIS_TOKEN", raising=False)


class FakeHIS:
    def __init__(self, ok=True):
        self.ok = ok

    async def ping(self):
        return {"ok": self.ok, "name": "Vaidyx Demo Hospital (synthetic)", "fhir_version": "4.0.1", "token_ok": self.ok,
                "error": "" if self.ok else "the HIS refused the token (HTTP 401)"}

    async def hospital(self):
        return {"name": "Vaidyx Demo Hospital (synthetic)"}

    def _client(self):
        class _C:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *a):
                return False
        return _C()

    async def _get_json(self, hc, res, params):
        return {"total": {"Patient": 12, "DiagnosticReport": 40}[res]}


# ---- the five steps ----------------------------------------------------------------------------------------------------------------

def test_setup_steps_are_for_the_root_admin_and_save_at_once(api, auth, monkeypatch):
    assert api.as_(RAO).get("/setup").status_code == 403
    assert api.as_(DEEPAK).post("/setup/hospital", {"name": "x"}).status_code == 403
    v = api.as_(ROOT).get("/setup").json()
    assert [s["id"] for s in v["steps"]] == ["hospital", "departments", "people", "his", "board"] and v["complete"] is False
    assert len([d for d in v["departments"] if d["group"] == "treating"]) == 23 and len([d for d in v["departments"] if d["group"] == "supporting"]) == 6

    assert api.post("/setup/hospital", {"name": ""}).status_code == 400
    r = api.post("/setup/hospital", {"name": "Vaidyx Demo Hospital (synthetic)", "level": "optimal", "type": "private", "pmjay_empanelled": True})
    assert r.status_code == 200, r.text
    h = org.hospital()
    assert h["name"] == "Vaidyx Demo Hospital (synthetic)" and h["level"] == "optimal" and h["first_setup"]["by"] == ROOT  # the old first set-up is answered too
    with pytest.raises(org.SetupDone):
        org.first_setup(ROOT, True)
    assert next(s for s in r.json()["steps"] if s["id"] == "hospital")["done"] is True

    assert api.post("/setup/departments", {"enabled": ["no_such"]}).status_code == 400
    assert api.post("/setup/departments", {"contacts": {"radiology": {"phone": "call me"}}}).status_code == 400
    enabled = [d["id"] for d in org.departments() if d["id"] != "dermatology"]
    r = api.post("/setup/departments", {"enabled": enabled, "contacts": {"radiology": {"email": "radiology@demo-hospital.example", "phone": "+91 44 2345 6789"}}})
    assert r.status_code == 200, r.text
    rad = org.department("radiology")
    assert rad["email"] == "radiology@demo-hospital.example" and rad["phone"] == "+91 44 2345 6789" and org.department_phone("radiology") == "+91 44 2345 6789"
    assert org.department("dermatology")["enabled"] is False and org.department("breast_surgery")["enabled"] is True  # people placed there: stays

    monkeypatch.setattr(his_client, "client", lambda *a, **k: FakeHIS(ok=False))
    r = api.post("/setup/his", {"url": "http://127.0.0.1:7130", "token": "synthetic-his-token"})
    assert r.status_code == 200 and r.json()["ok"] is False and "refused" in r.json()["test"]["error"]
    assert next(s for s in r.json()["steps"] if s["id"] == "his")["done"] is False  # the test must pass
    assert "synthetic-his-token" not in r.text
    monkeypatch.setattr(his_client, "client", lambda *a, **k: FakeHIS())
    t = api.post("/his/test").json()
    assert t["ok"] is True and t["hospital_name"] == "Vaidyx Demo Hospital (synthetic)" and t["patients"] == 12 and t["reports"] == 40 and t["latency_ms"] >= 0
    assert next(s for s in api.get("/setup").json()["steps"] if s["id"] == "his")["done"] is True
    assert any(e["kind"] == "his_test" for e in org.read_audit())

    assert api.post("/setup/board", {"coordinators": ["nobody-here"]}).status_code == 400
    assert api.post("/setup/board", {"meeting_defaults": {"time": "25:99"}}).status_code == 400
    r = api.post("/setup/board", {"coordinators": [ANIL], "heads": ["radiology", "medical_oncology", "surgical_oncology", "pathology", "radiation_oncology"],
                                  "meeting_defaults": {"weekday": "Thursday", "time": "14:00", "room": "Seminar hall 2", "minutes_per_case": 8}})
    assert r.status_code == 200, r.text
    h = org.hospital()
    assert h["meeting_defaults"] == {"weekday": 3, "time": "14:00", "room": "Seminar hall 2", "minutes_per_case": 8} and len(h["board_heads"]) == 5
    assert r.json()["board"]["coordinators"] == [ANIL]

    r = api.post("/setup/people", {"accounts": [{"email": "Dr.Kavya@Demo-Hospital.example", "display_name": "Dr Kavya (synthetic)", "departments": {"pathology": "head"}},
                                               {"email": "bad@", "departments": {"pathology": "member"}}]})
    assert r.status_code == 200 and len(r.json()["created"]) == 1 and len(r.json()["errors"]) == 1
    assert r.json()["created"][0]["username"] == "dr.kavya@demo-hospital.example"  # email login names are lower case
    v = api.get("/setup").json()
    assert v["complete"] is True and all(s["done"] for s in v["steps"])
    assert {e["kind"] for e in org.read_audit()} >= {"hospital_changed", "first_setup", "account_created", "first_password_set"}


# ---- accounts: generated first password inside a mailto, never logged -------------------------------------------------------------

def test_created_login_gets_a_mailto_with_a_generated_password_that_is_never_stored_or_logged(api, auth, data_root, caplog):
    caplog.set_level(logging.DEBUG)
    r = api.as_(ROOT).post("/accounts", {"email": "Dr.Meena@Demo-Hospital.example", "display_name": "Dr Meena (synthetic)",
                                         "departments": {"medical_oncology": "resident"}, "end_date": "2027-06-30"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["username"] == "dr.meena@demo-hospital.example" and m["mailto"].startswith("mailto:dr.meena@demo-hospital.example?")
    assert "subject=Your%20Vaidyx-TB%20login" in m["mailto"]
    pw = password_in(m["mailto"])
    body = urllib.parse.unquote(m["mailto"])
    assert len(pw) == 14 and "Login name: dr.meena@demo-hospital.example" in body and "/tb-nik" in body
    assert auth.users["dr.meena@demo-hospital.example"]["must_change"] is True and auth.resets[-1] == ("dr.meena@demo-hospital.example", True)
    assert pw not in json.dumps({k: v for k, v in m.items() if k != "mailto"})  # only inside the mailto
    assert pw not in everything_stored(data_root) and pw not in caplog.text
    rl = org.roles("dr.meena@demo-hospital.example")
    assert rl["resident"] == {"medical_oncology": "resident"} and rl["end_date"] == "2027-06-30" and not rl["expired"]
    assert api.post("/accounts", {"email": "vx", "coordinator": True}).status_code == 409  # never a Vaidyx admin
    assert api.post("/accounts", {"email": "nobody@demo-hospital.example"}).status_code == 400  # at least one role
    assert api.as_(DEEPAK).post("/accounts", {"email": "x@demo-hospital.example", "auditor": True}).status_code == 403
    r = api.as_(ROOT).post("/accounts", {"email": "audit2@demo-hospital.example", "auditor": True})
    assert r.status_code == 200 and org.roles("audit2@demo-hospital.example")["auditor"] is True
    assert not org.can(org.roles("audit2@demo-hospital.example"), "read_case") and org.can(org.roles("audit2@demo-hospital.example"), "read_audit")


def test_password_resets_by_the_department_admin_and_the_root_admin(api, auth, data_root, caplog):
    caplog.set_level(logging.DEBUG)
    assert api.as_(RAO).post(f"/accounts/{ASHA}/reset-password").status_code == 403  # a doctor is no admin
    assert api.as_(DEEPAK).post(f"/accounts/{RAVI}/reset-password").status_code == 403  # Radiology is not Deepak's
    r = api.as_(DEEPAK).post(f"/accounts/{ASHA}/reset-password")
    assert r.status_code == 200, r.text
    pw = password_in(r.json()["mailto"])
    assert auth.users[ASHA]["pw"] == pw and auth.users[ASHA]["must_change"] is True and r.json()["must_change_password"] is True
    assert pw not in everything_stored(data_root) and pw not in caplog.text
    assert any(e["kind"] == "password_reset" and e["username"] == ASHA and e["by"] == DEEPAK for e in org.read_audit())
    r = api.as_(ROOT).post(f"/accounts/{RAVI}/reset-password")
    assert r.status_code == 200 and password_in(r.json()["mailto"]) != pw
    assert api.as_(ROOT).post(f"/accounts/{VX}/reset-password").status_code in (404, 409)  # a Vaidyx admin is never reset here
    assert "Vaidyx admin" in accounts.RESET_NOTE


def test_department_admin_adds_a_resident_with_an_end_date(api, auth):
    api.as_(DEEPAK)
    assert api.post("/departments/radiology/people", {"email": "r1@demo-hospital.example", "role": "resident"}).status_code == 403
    r = api.post("/departments/breast_surgery/people", {"email": "Res.Two@Demo-Hospital.example", "display_name": "Dr Two (synthetic)", "role": "resident",
                                                       "end_date": "2027-03-31"})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "res.two@demo-hospital.example" and r.json()["departments"] == {"breast_surgery": "resident"} and r.json()["mailto"]
    people = api.get("/departments/breast_surgery/people").json()["people"]
    row = next(p for p in people if p["username"] == "res.two@demo-hospital.example")
    assert row["role"] == "resident" and row["end_date"] == "2027-03-31" and row["expired"] is False and row["must_change_password"] is True
    assert api.put("/departments/breast_surgery/people/res.two@demo-hospital.example", {"end_date": "2020-01-01"}).status_code == 200
    rl = org.roles("res.two@demo-hospital.example")
    assert rl["expired"] is True and rl["known"] is False and rl["departments"] == {}  # past the end date: no clinical action
    assert api.put("/departments/breast_surgery/people/res.two@demo-hospital.example", {"end_date": "31/03/2027"}).status_code == 400
    assert api.put("/departments/breast_surgery/people/res.two@demo-hospital.example", {"role": "owner"}).status_code == 400
    assert api.delete("/departments/breast_surgery/people/res.two@demo-hospital.example").status_code == 200
    assert "res.two@demo-hospital.example" not in org.load()["users"]


def test_root_admin_changes_roles_in_one_step(api, auth):
    r = api.as_(ROOT).put(f"/accounts/{RAVI}", {"auditor": True, "end_date": "2030-01-01", "departments": {"radiology": "head"}})
    assert r.status_code == 200, r.text
    assert org.roles(RAVI)["auditor"] is True and org.roles(RAVI)["departments"] == {"radiology": "head"}
    assert api.put(f"/accounts/{RAVI}", {"password": "x"}).status_code == 400  # unknown field
    assert api.put(f"/accounts/{ROOT}", {"root_admin": False}).status_code == 409  # the last root admin
    assert api.put(f"/accounts/{VX}", {"disabled": True}).status_code == 409  # never a Vaidyx admin
    assert api.as_(DEEPAK).put(f"/accounts/{RAVI}", {"auditor": False}).status_code == 403
    rows = {a["username"]: a for a in api.as_(ROOT).get("/accounts").json()["accounts"]}
    assert rows[ASHA]["end_date"] and rows[AUDIT]["auditor"] is True and rows["dr.rao@hospital.example"]["is_email"] is True


def test_login_names_old_short_names_stay_valid():
    assert accounts.clean_username("Dr.Rao@Hospital.Example") == "dr.rao@hospital.example"
    assert accounts.clean_username("ravi") == "ravi"
    with pytest.raises(accounts.AccountError):
        accounts.clean_username("not an email@")
    pw = accounts.generate_password()
    assert len(pw) == 14 and any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw) and not set(pw) & set("0OIl1")


# ---- the organisation (V3) ---------------------------------------------------------------------------------------------------------

def test_v3_departments_aliases_and_placements(data_root):
    ds = org.departments()
    assert len([d for d in ds if d["group"] == "treating"]) == 23 and len([d for d in ds if d["group"] == "supporting"]) == 6
    assert {d["id"] for d in ds if d["group"] == "supporting"} == {"radiology", "pathology", "microbiology", "biochemistry", "nuclear_medicine", "clinical_pharmacology"}
    assert org.department_id("Hematology") == "haematology" and org.department_id("Medical Gastroenterology") == "gastrointestinal_surgery"
    assert org.department_id("Endoscopy") == "gastrointestinal_surgery" and org.department_id("Dental Surgery") is None and org.is_owner_alias("Anaesthesiology")
    assert org.resolve_route(None, "Dental Surgery", owner_dept="ent_head_neck_surgery") == ("ENT / Head and Neck Surgery", "ent_head_neck_surgery", "owner")
    mg = org.department("medical_genetics")
    assert mg["group"] == "treating" and mg["receives_requests"] is True and org.receives_requests("pathology") and not org.receives_requests("dermatology")
    assert all("phone" in d for d in ds)
    assert org.hospital()["board_heads"] == ["radiology", "medical_oncology", "surgical_oncology", "pathology", "radiation_oncology"]
    assert set(org.hospital()["meeting_defaults"]) == {"weekday", "time", "room", "minutes_per_case"}
    o = copy.deepcopy(org.load())
    o["users"]["x"] = {"departments": {"breast_surgery": "pg"}, "end_date": "2027-01-01", "auditor": False}
    assert org.save(o, by="test")["users"]["x"]["departments"] == {"breast_surgery": "resident"}
    o["users"]["x"]["end_date"] = "soon"
    with pytest.raises(ValueError, match="end_date"):
        org.validate(o)
    o["users"]["x"]["end_date"] = ""
    o["users"]["x"]["auditor"] = "yes"
    with pytest.raises(ValueError, match="auditor"):
        org.validate(o)


def _v2_file() -> dict:
    """An org.json as the V2 build wrote it: the V2 departments (Medical Gastroenterology, Dental Surgery / OMFS, Anaesthesiology; no
    Medical Genetics, no Paediatric Surgery), the four V2 heads, no phones, users placed in the removed departments."""
    keep = [copy.deepcopy(d) for d in org.DEFAULT_DEPARTMENTS if d["id"] not in ("medical_genetics", "paediatric_surgery")]
    for d in keep:
        d.pop("phone", None); d.pop("receives_requests", None)
        if d["id"] == "gastrointestinal_surgery":
            d["aliases"] = ["GI Surgery", "Surgical Gastroenterology"]
    keep += [{"id": "medical_gastroenterology", "name": "Medical Gastroenterology", "group": "treating", "aliases": ["Gastroenterology", "GI", "Endoscopy", "Gastro"],
              "email": "medical_gastroenterology@hospital.example"},
             {"id": "dental_surgery", "name": "Dental Surgery / Oral and Maxillofacial Surgery", "group": "supporting", "aliases": ["Dental Surgery", "Dental", "OMFS"],
              "email": "dental_surgery@hospital.example"},
             {"id": "anaesthesiology", "name": "Anaesthesiology", "group": "supporting", "aliases": ["Anaesthesia", "PAC"], "email": "anaesthesiology@hospital.example"}]
    hosp = {k: v for k, v in org.DEFAULT_HOSPITAL.items() if k != "meeting_defaults"} | {"name": "V2 Hospital (synthetic)", "board_heads": list(org.V2_BOARD_HEADS)}
    return {"version": 2, "hospital": hosp, "departments": keep,
            "users": {"dr.gastro": {"departments": {"medical_gastroenterology": "head"}, "admin_of": ["medical_gastroenterology"], "coordinator": False, "display_name": "Dr G", "disabled": False},
                      "dr.dental": {"departments": {"dental_surgery": "member"}, "admin_of": [], "coordinator": False, "display_name": "Dr D", "disabled": False},
                      "anil": {"departments": {}, "admin_of": [], "coordinator": True, "display_name": "Anil", "disabled": False}},
            "admins": ["tbroot"], "routes": {"colorectal_rectum.endoscopy": "medical_gastroenterology", "breast.pac": "anaesthesiology"}}


def test_a_v2_file_is_migrated_to_v3_without_losing_anyone(data_root):
    org.path().write_text(json.dumps(_v2_file()))
    o = org.load()
    assert o["version"] == 3 and set(o["users"]) == {"dr.gastro", "dr.dental", "anil"} and o["admins"] == ["tbroot"]
    ids = {d["id"] for d in o["departments"]}
    assert "medical_gastroenterology" not in ids and "anaesthesiology" not in ids  # removed (nobody left in Anaesthesiology)
    assert "dental_surgery" in ids  # kept: somebody is still placed there
    assert {"medical_genetics", "paediatric_surgery"} <= ids
    assert o["users"]["dr.gastro"]["departments"] == {"gastrointestinal_surgery": "head"} and o["users"]["dr.gastro"]["admin_of"] == ["gastrointestinal_surgery"]
    assert o["users"]["dr.dental"]["departments"] == {"dental_surgery": "member"} and o["users"]["anil"]["coordinator"] is True
    assert all(u["auditor"] is False and u["outside_expert"] is False and u["end_date"] == "" for u in o["users"].values())
    assert org.department_id("Endoscopy") == "gastrointestinal_surgery" and org.department_id("Medical Gastroenterology") == "gastrointestinal_surgery"
    assert o["routes"] == {"colorectal_rectum.endoscopy": "gastrointestinal_surgery", "breast.pac": "owner"}
    assert o["hospital"]["board_heads"] == org.BOARD_HEADS and o["hospital"]["name"] == "V2 Hospital (synthetic)"
    assert o["hospital"]["meeting_defaults"] == org.DEFAULT_MEETING and all("phone" in d and "receives_requests" in d for d in o["departments"])
    ev = next(e for e in org.read_audit() if e["kind"] == "org_migrated")
    assert ev["from_version"] == 2 and ev["to_version"] == 3 and "medical_genetics" in ev["added"]
    assert json.loads(org.path().read_text())["version"] == 3  # saved
    assert org.load() is org.load()  # and not migrated again


def test_a_v1_file_still_migrates_to_the_current_version(data_root):
    v1 = {"departments": [{"id": "radio_diagnosis", "name": "Radio-diagnosis", "aliases": []}, {"id": "tumour_board", "name": "Tumour Board coordination", "aliases": []}],
          "users": {"dr.r": {"departments": {"radio_diagnosis": "head"}}, "anil": {"departments": {"tumour_board": "member"}}}, "admins": []}
    org.path().write_text(json.dumps(v1))
    o = org.load()
    assert o["version"] == 3 and o["users"]["dr.r"]["departments"] == {"radiology": "head"} and o["users"]["anil"]["coordinator"] is True
    assert org.department_id("radio_diagnosis") == "radiology"
