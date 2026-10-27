"""org: hospital, treating / supporting departments, users and the one permission check can() (V1 item 2.1; V2 items 2.1, 2.2).
Synthetic usernames only."""
import copy, json

import pytest

from tumour_board import config, org


def _org(**users):
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = users
    o["admins"] = ["tbadmin"]
    return o


@pytest.fixture
def people():
    """Two-department member, a radiology head, a coordinator, a root admin; saved to the temporary data root."""
    org.save(_org(
        meena={"departments": {"radiology": "member", "pathology": "member"}, "display_name": "Dr Meena Iyer"},
        ravi={"departments": {"radiology": "member"}},
        suresh={"departments": {"radiology": "head"}},
        kavya={"departments": {"pathology": "member"}},
        anil={"coordinator": True},
        priya={"departments": {"breast_surgery": "member"}},  # a treating doctor
        deepak={"admin_of": ["radiology"]},  # a department admin who is not a doctor
    ), by="test")
    return {
        "member": org.roles("ravi"),
        "two_dept": org.roles("meena"),
        "head": org.roles("suresh"),
        "path_member": org.roles("kavya"),
        "coordinator": org.roles("anil"),
        "treating": org.roles("priya"),
        "dept_admin": org.roles("deepak"),
        "root": org.roles("tbadmin"),  # a root admin: the organisation and accounts, nothing clinical (plan section 4)
        "admin": org.roles("root", vaidyx_admin=True),  # a Vaidyx admin: everything
        "vaidyx_admin": org.roles("root", vaidyx_admin=True),
        "unknown": org.roles("stranger"),
    }


# --- defaults: the plan's section 4 ---------------------------------------------------------------------------------------

def test_default_departments_follow_the_plan():
    ids = [d["id"] for d in org.DEFAULT_DEPARTMENTS]
    assert len(ids) == 29 and len(set(ids)) == 29  # the owner's settled list (18 Oct 2026): 23 treating, 6 supporting
    assert sum(1 for d in org.DEFAULT_DEPARTMENTS if d["group"] == "treating") == 23
    assert sum(1 for d in org.DEFAULT_DEPARTMENTS if d["group"] == "supporting") == 6
    assert [d["id"] for d in org.DEFAULT_DEPARTMENTS if d["group"] == "supporting"] == [
        "radiology", "pathology", "microbiology", "biochemistry", "nuclear_medicine", "clinical_pharmacology"]
    for name in ("Medical Genetics", "Paediatric Surgery", "Palliative Medicine"):
        assert any(d["name"] == name for d in org.DEFAULT_DEPARTMENTS), name
    for name in ("Medical Gastroenterology", "Dental Surgery / Oral and Maxillofacial Surgery", "Anaesthesiology"):  # removed on 18 Oct (R02-Q02)
        assert not any(d["name"] == name for d in org.DEFAULT_DEPARTMENTS), name
    assert all(d["receives_requests"] for d in org.DEFAULT_DEPARTMENTS if d["group"] == "supporting") and next(d for d in org.DEFAULT_DEPARTMENTS if d["id"] == "medical_genetics")["receives_requests"]
    assert all(d["email"] == f"{d['id']}@{org.PLACEHOLDER_DOMAIN}" for d in org.DEFAULT_DEPARTMENTS)  # placeholders until the hospital gives them
    assert not any(d["id"] in ("tumour_board", "general_medicine") for d in org.DEFAULT_DEPARTMENTS)  # the coordinator is a role; General Medicine was removed
    assert org.validate(org.DEFAULT_ORG)["departments"] == org.DEFAULT_DEPARTMENTS


def test_departments_by_group(data_root):
    assert len(org.departments("treating")) == 23 and len(org.departments("supporting")) == 6 and len(org.departments()) == 29
    assert org.department_group("radiology") == "supporting" and org.department_group("breast_surgery") == "treating"
    assert org.department_group("cardiology") == "supporting"  # unknown: the safer group
    assert org.department_email("radiology") == "radiology@hospital.example" and org.department_email("cardiology") == ""


# --- load / save / validate -------------------------------------------------------------------------------------------

def test_load_creates_default_file_and_caches(data_root):
    assert org.path() == data_root / "org.json"
    assert not org.path().exists()
    o = org.load()
    assert org.path().exists()
    raw = json.loads(org.path().read_text())
    assert raw["version"] == 3 and raw["hospital"]["level"] == "essential" and raw["hospital"]["pmjay_empanelled"] is True and raw["hospital"]["fetch_window_months"] == 12
    assert [d["id"] for d in o["departments"]] == [d["id"] for d in org.DEFAULT_DEPARTMENTS]
    assert o["users"] == {} and o["admins"] == [] and o["routes"] == {}
    assert org.load() is o


def test_load_fills_a_partly_filled_v2_file(data_root):
    (data_root / "org.json").write_text(json.dumps({"version": 3, "hospital": {"name": "Synthetic Cancer Centre"}, "users": {"a": {"departments": {"pathology": "head"}}}}))
    o = org.load()
    assert o["hospital"] == {**org.DEFAULT_HOSPITAL, "name": "Synthetic Cancer Centre", "level": "essential", "type": "", "pmjay_empanelled": True, "fetch_window_months": 12}
    assert o["hospital"]["board_heads"] == ["radiology", "medical_oncology", "surgical_oncology", "pathology", "radiation_oncology"]  # the board lists filled in (V2 item 6.1; five heads from 18 Oct)
    assert len(o["departments"]) == len(org.DEFAULT_DEPARTMENTS) and o["admins"] == []
    assert org.roles("a")["departments"] == {"pathology": "head"}
    assert not (data_root / "org_audit.jsonl").exists()  # not a migration


def test_load_sees_a_changed_file(data_root):
    org.load()
    o = _org(x={"coordinator": True})
    org.save(o, by="admin")
    assert org.roles("x")["coordinator"] is True


def test_save_writes_audit_and_keeps_unknown_keys(data_root):
    o = _org(ravi={"departments": {"radiology": "member"}})
    o["future_setting"] = {"keep": True}
    saved = org.save(o, by="admin1")
    assert saved["future_setting"] == {"keep": True}
    assert json.loads(org.path().read_text())["future_setting"] == {"keep": True}
    lines = (data_root / "org_audit.jsonl").read_text().splitlines()
    ev = json.loads(lines[0])
    assert ev["by"] == "admin1" and ev["kind"] == "org_saved" and ev["departments"] == len(org.DEFAULT_DEPARTMENTS) and ev["users"] == 1
    assert ev["ts"]
    assert [json.loads(l)["kind"] for l in lines] == ["org_saved", "account_placed", "root_admins_changed"]  # the first save placed ravi and named tbadmin
    org.save(saved, by="admin2")
    assert len((data_root / "org_audit.jsonl").read_text().splitlines()) == 4  # an unchanged save adds only org_saved
    assert [e["by"] for e in org.read_audit()] == ["admin2", "admin1", "admin1", "admin1"]


def test_save_rejects_invalid_and_writes_nothing(data_root):
    o = _org(ravi={"departments": {"cardiology": "member"}})
    with pytest.raises(ValueError):
        org.save(o, by="admin")
    assert not (data_root / "org_audit.jsonl").exists()


@pytest.mark.parametrize("mutate,msg", [
    (lambda o: o["departments"].append({"id": "Bad-Id", "name": "Bad", "group": "treating"}), "lower-case"),
    (lambda o: o["departments"].append({"id": "", "name": "Empty", "group": "treating"}), "lower-case"),
    (lambda o: o["departments"].append({"id": "pathology", "name": "Pathology Two", "group": "supporting"}), "used twice"),
    (lambda o: o["departments"].append({"id": "path2", "name": "pathology", "group": "supporting"}), "used twice"),
    (lambda o: o["departments"].append({"id": "noname", "name": "  ", "group": "treating"}), "needs a name"),
    (lambda o: o["departments"].append({"id": "x", "name": "X"}), "group"),
    (lambda o: o["departments"].append({"id": "x", "name": "X", "group": "clinical"}), "group"),
    (lambda o: o["departments"].append({"id": "x", "name": "X", "group": "treating", "aliases": "Radiology"}), "list of text"),
    (lambda o: o["departments"].append({"id": "x", "name": "X", "group": "treating", "aliases": ["Radiology"]}), "route to both"),
    (lambda o: o["departments"].append({"id": "x", "name": "X", "group": "treating", "aliases": ["radio_diagnosis"]}), "route to both"),  # V1 ids stay aliases
    (lambda o: o["departments"].append({"id": "x", "name": "X", "group": "treating", "email": "not an address"}), "email"),
    (lambda o: o["departments"].append({"id": "coordinator", "name": "Coordination", "group": "treating"}), "reserved"),
    (lambda o: o["departments"].append({"id": "x", "name": "MDT Coordinator", "group": "treating"}), "role"),
    (lambda o: o["users"].update(u={"departments": {"cardiology": "member"}}), "unknown department"),
    (lambda o: o["users"].update(u={"departments": {"pathology": "owner"}}), "member"),
    (lambda o: o["users"].update(u={"coordinator": "yes"}), "true or false"),
    (lambda o: o["users"].update(u={"disabled": "yes"}), "true or false"),
    (lambda o: o["users"].update(u={"admin_of": "radiology"}), "admin_of"),
    (lambda o: o["users"].update(u={"admin_of": ["cardiology"]}), "unknown department"),
    (lambda o: o["hospital"].update(level="tertiary"), "level"),
    (lambda o: o["hospital"].update(type="trust"), "type"),
    (lambda o: o["hospital"].update(pmjay_empanelled="yes"), "PM-JAY"),
    (lambda o: o["hospital"].update(fetch_window_months=0), "fetch window"),
    (lambda o: o["hospital"].update(fetch_window_months="a year"), "fetch window"),
    (lambda o: o.update(admins="tbadmin"), "list of usernames"),
    (lambda o: o.update(routes=["x"]), "Routes"),
    (lambda o: o.update(routes={"breast": "radiology"}), "<protocol>.<record>"),
    (lambda o: o.update(routes={"breast.cbc": "cardiology"}), "unknown department"),
    (lambda o: o.update(routes={"breast.cbc": ""}), "needs a department"),
])
def test_validate_rejects(mutate, msg):
    o = copy.deepcopy(org.DEFAULT_ORG)
    mutate(o)
    with pytest.raises(ValueError, match=msg):
        org.validate(o)


def test_validate_returns_a_cleaned_copy():
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["hospital"]["level"] = "optimal"
    o["hospital"]["type"] = "public"
    o["hospital"]["fetch_window_months"] = "24"
    o["users"] = {"ravi": {"departments": {"pathology": "head"}}, "asha": {"departments": {"Radio-diagnosis": "doctor"}, "admin_of": ["Laboratory Medicine", "biochemistry"]}}
    o["admins"] = [" a ", "a", ""]
    o["routes"] = {"breast.cbc": "Pathology", "lung_nsclc.clinical_history": "owner", "breast.previous_board": "coordinator"}
    clean = org.validate(o)
    assert clean is not o and clean["users"]["ravi"] == {"departments": {"pathology": "head"}, "admin_of": [], "coordinator": False, "disabled": False, "display_name": "",
                                                         "auditor": False, "outside_expert": False, "end_date": ""}
    assert clean["users"]["asha"]["departments"] == {"radiology": "member"} and clean["users"]["asha"]["admin_of"] == ["biochemistry"]  # V1 ids, aliases and "doctor" normalised
    assert clean["admins"] == ["a"] and clean["hospital"]["fetch_window_months"] == 24
    assert clean["routes"] == {"breast.cbc": "pathology", "lung_nsclc.clinical_history": "owner", "breast.previous_board": "coordinator"}
    assert org.validate(org.DEFAULT_ORG) == {**org.DEFAULT_ORG, "departments": org.DEFAULT_DEPARTMENTS}


# --- V1 -> V2 migration -----------------------------------------------------------------------------------------------------

V1_FILE = {
    "hospital": {"name": "Synthetic Cancer Centre", "level": "optimal", "type": "public"},
    "departments": [
        {"id": "radio_diagnosis", "name": "Radio-diagnosis", "aliases": ["Radiology", "Radiodiagnosis", "Imaging", "X-ray wing"]},
        {"id": "pathology", "name": "Pathology", "aliases": ["Histopathology", "Cytology"]},
        {"id": "molecular_pathology", "name": "Molecular Pathology", "aliases": ["Molecular"]},
        {"id": "nuclear_medicine", "name": "Nuclear Medicine", "aliases": ["Nuclear"]},
        {"id": "medical_oncology", "name": "Medical Oncology", "aliases": ["Oncology", "GI Oncology"]},
        {"id": "surgical_oncology", "name": "Surgical Oncology", "aliases": ["Surgery", "Oncosurgery"]},
        {"id": "radiation_oncology", "name": "Radiation Oncology", "aliases": ["Radiotherapy"]},
        {"id": "laboratory_medicine", "name": "Laboratory Medicine", "aliases": ["Laboratory", "Lab", "Biochemistry", "Haematology"]},
        {"id": "gastroenterology", "name": "Gastroenterology", "aliases": ["GI", "Endoscopy"]},
        {"id": "pulmonary_medicine", "name": "Pulmonary Medicine", "aliases": ["Pulmonology", "Chest Medicine", "Respiratory Medicine"]},
        {"id": "general_medicine", "name": "General Medicine", "aliases": ["Medicine"]},
        {"id": "tumour_board", "name": "Tumour Board coordination", "aliases": ["Tumour Board coordinator", "Coordinator", "MDT coordinator"]},
        {"id": "cardiology", "name": "Cardiology", "aliases": ["Cardio"]},
    ],
    "users": {"rad": {"departments": {"radio_diagnosis": "head"}, "coordinator": False, "display_name": "Dr R"},
              "lab": {"departments": {"laboratory_medicine": "member"}, "coordinator": False},
              "coord": {"departments": {"tumour_board": "member"}, "coordinator": False},
              "med": {"departments": {"general_medicine": "member", "medical_oncology": "member"}, "coordinator": False},
              "molpath": {"departments": {"molecular_pathology": "head", "pathology": "member"}, "coordinator": False}},
    "admins": ["tbadmin"],
    "extra": {"keep": 1},
}


def test_v1_hospital_added_department_colliding_with_a_v2_name_is_merged(data_root):
    """Review minor 7: a V1 department the hospital added under a name V2 now uses (e.g. "Microbiology") merges into the V2 department
    instead of breaking validation; its users land there and colliding aliases are dropped."""
    v1 = copy.deepcopy(V1_FILE)
    v1["departments"].append({"id": "micro", "name": "Microbiology", "aliases": ["Serology", "Micro lab"]})
    v1["users"]["mic"] = {"departments": {"micro": "head"}, "coordinator": False}
    (data_root / "org.json").write_text(json.dumps(v1))
    o = org.load()
    assert [d["id"] for d in o["departments"]][len(org.DEFAULT_DEPARTMENTS):] == ["cardiology"] and o["users"]["mic"]["departments"] == {"microbiology": "head"}
    ev = org.read_audit()[0]
    assert ev["kind"] == "org_migrated" and ev["departments"]["micro"] == ["microbiology"] and "Micro lab" not in json.dumps(o["departments"])


def test_v1_file_is_migrated_on_load_and_audited(data_root):
    (data_root / "org.json").write_text(json.dumps(V1_FILE))
    o = org.load()
    raw = json.loads(org.path().read_text())
    assert raw["version"] == 3 and o["version"] == 3
    assert o["hospital"] == {**org.DEFAULT_HOSPITAL, "name": "Synthetic Cancer Centre", "level": "optimal", "type": "public", "pmjay_empanelled": True, "fetch_window_months": 12}
    ids = [d["id"] for d in o["departments"]]
    assert ids[:len(org.DEFAULT_DEPARTMENTS)] == [d["id"] for d in org.DEFAULT_DEPARTMENTS] and ids[len(org.DEFAULT_DEPARTMENTS):] == ["cardiology"]
    assert org.department("cardiology")["group"] == "supporting" and org.department("cardiology")["aliases"] == ["Cardio"]
    assert "X-ray wing" in org.department("radiology")["aliases"]  # a custom V1 alias travels with its department
    assert org.department_id("Haematology") == "haematology"  # the V1 lab alias that now names a treating department is dropped
    assert o["users"]["rad"] == {"departments": {"radiology": "head"}, "admin_of": [], "coordinator": False, "disabled": False, "display_name": "Dr R",
                                 "auditor": False, "outside_expert": False, "end_date": ""}
    assert o["users"]["lab"]["departments"] == {"biochemistry": "member", "pathology": "member"}
    assert o["users"]["coord"]["coordinator"] is True and o["users"]["coord"]["departments"] == {}
    assert o["users"]["med"]["departments"] == {"medical_oncology": "member"}
    assert o["users"]["molpath"]["departments"] == {"pathology": "head"}
    assert o["admins"] == ["tbadmin"] and o["extra"] == {"keep": 1}
    ev = org.read_audit()
    assert len(ev) == 1 and ev[0]["kind"] == "org_migrated" and ev[0]["by"] == "system" and ev[0]["kept"] == ["cardiology"]
    assert ev[0]["departments"]["laboratory_medicine"] == ["biochemistry", "pathology"] and "Haematology" in ev[0]["dropped_aliases"]
    assert org.load() is o  # cached after the migration


def test_stored_v1_ids_still_resolve(data_root):
    """Documents, actions, sessions and notifications written before the migration carry V1 ids: they keep resolving."""
    assert org.department_id("radio_diagnosis") == "radiology" and org.department("radio_diagnosis")["id"] == "radiology"
    assert org.department_name("radio_diagnosis") == "Radiology" and org.department_name("laboratory_medicine") == "Biochemistry"
    assert org.department_id("molecular_pathology") == "pathology" and org.department_id("pulmonary_medicine") == "pulmonology"
    assert org.department_id("gastroenterology") == "gastrointestinal_surgery"  # Medical Gastroenterology was removed on 18 Oct: endoscopy goes to GI Surgery
    assert org.department_id("general_medicine") is None and org.department_id("Medicine") is None  # removed: the owning department's records
    assert org.department_id("tumour_board") is None and org.department_id("Tumour Board coordination") is None  # a role now
    assert org.is_coordinator_name("tumour_board") and org.is_coordinator_name("MDT Coordinator") and not org.is_coordinator_name("Radiology")
    assert org.department_name("coordinator") == "MDT Coordinator" and org.department_name("Tumour Board coordination") == "MDT Coordinator"
    assert org.department_name("owner") == "Owning department"


def test_is_v1():
    assert org.is_v1({"departments": []}) and org.is_v1({"version": 1}) and org.is_v1({"version": "x"})
    assert not org.is_v1({"version": 2}) and not org.is_v1(None)


# --- routing names ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,dept", [
    ("Radiology", "radiology"),
    ("radiology", "radiology"),
    ("Department of Radio-diagnosis", "radiology"),
    ("Dept. of Radiodiagnosis", "radiology"),
    ("radio_diagnosis", "radiology"),
    ("Pathology Department", "pathology"),
    ("Pathology", "pathology"),
    ("Molecular Pathology", "pathology"),
    ("Nuclear Medicine", "nuclear_medicine"),
    ("Medical Oncology", "medical_oncology"),
    ("GI Oncology", "medical_oncology"),
    ("Surgical Oncology", "surgical_oncology"),
    ("Radiation Oncology", "radiation_oncology"),
    ("Laboratory Medicine", "biochemistry"),
    ("Biochemistry", "biochemistry"),
    ("Microbiology", "microbiology"),
    ("Gastroenterology", "gastrointestinal_surgery"),
    ("Pulmonology", "pulmonology"),
    ("Pulmonary Medicine", "pulmonology"),
    ("Breast Surgery", "breast_surgery"),
    ("Gynaecologic Oncology", "gynaecologic_oncology"),
    ("ENT", "ent_head_neck_surgery"),
    ("Dental Surgery", None),  # the owning department's own work from 18 Oct (org.is_owner_alias)
    ("Anaesthesiology", None),
    ("Clinical Pharmacology", "clinical_pharmacology"),
    ("Medicine", None),
    ("Tumour Board coordinator", None),
    ("MDT Coordinator", None),
    ("Cardiology", None),
    ("", None),
    (None, None),
])
def test_department_id(name, dept):
    assert org.department_id(name) == dept


def test_eye_heart_and_hearing_go_to_the_owning_team():
    """night-v3 item 2.1 (research decision 4): no ophthalmology, cardiology or audiology department in the hospital set-up, so an eye
    examination, an echocardiogram or an audiogram is asked of the owning treating team."""
    for name in ("Ophthalmology", "Cardiology", "Eye", "Ophthalmologist", "Echocardiography", "2D Echo", "Audiology", "Department of Ophthalmology"):
        assert org.is_owner_alias(name), name
    assert org.department_id("Ophthalmology") is None and org.department_id("Cardiology") is None
    assert not org.is_owner_alias("Haematology") and not org.is_owner_alias("ENT / Head and Neck Surgery")  # real departments stay departments


def test_department_name_and_lookup():
    assert org.department_name("radiology") == "Radiology"
    assert org.department_name("cardiology") == "cardiology"
    assert org.department("pathology")["name"] == "Pathology" and org.department("pathology")["group"] == "supporting"
    assert org.department("cardiology") is None


def test_admin_renamed_department_still_routes(data_root):
    o = copy.deepcopy(org.load())
    i = next(i for i, d in enumerate(o["departments"]) if d["id"] == "radiology")
    o["departments"][i] = {"id": "radiology", "name": "Radiodiagnosis and Imaging", "group": "supporting", "aliases": ["Radiology", "X-ray"], "email": ""}
    org.save(o, by="admin")
    assert org.department_id("X-ray") == "radiology"
    assert org.department_name("radiology") == "Radiodiagnosis and Imaging"


# --- roles ----------------------------------------------------------------------------------------------------------------

def test_roles(people):
    root = people["root"]
    assert root["root_admin"] and not root["admin"] and not root["known"] and root["departments"] == {} and root["admin_of"] == []
    assert org.can(root, "manage_org") and org.can(root, "manage_department", "pathology") and org.can(root, "manage_department", None) and org.can(root, "view")
    assert not org.can(root, "read_case") and not org.can(root, "create_case") and not org.can(root, "waive", "radiology") and not org.can(root, "session") and not org.can(root, "inbox", "radiology")
    assert people["two_dept"] == {"user": "meena", "admin": False, "vaidyx_admin": False, "root_admin": False, "coordinator": False,
                                  "departments": {"radiology": "member", "pathology": "member"}, "admin_of": [],
                                  "treating": {}, "supporting": {"radiology": "member", "pathology": "member"}, "disabled": False, "known": True,
                                  "resident": {}, "resident_treating": {}, "auditor": False, "outside_expert": False, "end_date": "", "expired": False, "display_name": "Dr Meena Iyer"}
    assert people["head"]["departments"] == {"radiology": "head"} and people["head"]["known"]
    assert people["coordinator"]["coordinator"] and people["coordinator"]["departments"] == {} and people["coordinator"]["known"]
    assert people["vaidyx_admin"]["admin"] and people["vaidyx_admin"]["vaidyx_admin"] and not people["vaidyx_admin"]["root_admin"] and people["vaidyx_admin"]["known"]
    assert people["admin"]["admin"] and not people["admin"]["root_admin"] and people["admin"]["known"]
    assert people["unknown"] == {"user": "stranger", "admin": False, "vaidyx_admin": False, "root_admin": False, "coordinator": False, "departments": {},
                                 "admin_of": [], "treating": {}, "supporting": {}, "disabled": False, "known": False,
                                 "resident": {}, "resident_treating": {}, "auditor": False, "outside_expert": False, "end_date": "", "expired": False, "display_name": ""}
    empty = org.roles("")
    assert empty["admin"] and empty["known"]
    assert org.roles(None)["admin"]


def test_roles_treating_and_supporting_and_admin_of(data_root):
    org.save(_org(asha={"departments": {"breast_surgery": "member", "radiology": "head"}, "admin_of": ["radiology"]}), by="test")
    r = org.roles("asha")
    assert r["treating"] == {"breast_surgery": "member"} and r["supporting"] == {"radiology": "head"} and r["admin_of"] == ["radiology"]


def test_roles_ignore_hand_edited_unknowns(data_root):
    (data_root / "org.json").write_text(json.dumps({"version": 2, "users": {"z": {"departments": {"cardiology": "member", "pathology": "owner"}, "coordinator": "yes", "admin_of": ["cardiology", "pathology"]}}}))
    r = org.roles("z")
    assert r["departments"] == {} and r["coordinator"] is False and r["known"] is False and r["admin_of"] == ["pathology"]


def test_disabled_user_can_do_nothing(data_root):
    org.save(_org(ravi={"departments": {"radiology": "head"}, "coordinator": True, "disabled": True}), by="test")
    r = org.roles("ravi")
    assert r["disabled"] and not r["known"] and r["departments"] == {"radiology": "head"}
    assert not org.can(r, "view") and not org.can(r, "inbox", "radiology") and not org.can(r, "session")
    with pytest.raises(PermissionError, match="disabled"):
        org.require(r, "view")
    v = org.roles("ravi", vaidyx_admin=True)  # the flag never locks out the Vaidyx admin (review M3)
    assert not v["disabled"] and v["admin"] and v["known"] and org.can(v, "manage_org") and org.can(v, "view")
    org.save(_org(tbadmin={"disabled": True}), by="test")  # a disabled root admin loses the organisation screen
    assert org.roles("tbadmin")["disabled"] and not org.can(org.roles("tbadmin"), "manage_org")


# --- can(): table-driven ----------------------------------------------------------------------------------------------------

USERS = ("member", "head", "coordinator", "treating", "dept_admin", "root", "admin", "unknown")
# action, department, expected for (member of radiology, head of radiology, coordinator, treating doctor of breast surgery,
# department admin of radiology, root admin, Vaidyx admin, unknown). V2 plan section 4: supporting doctors receive and answer
# requests only; treating doctors create Case Files, confirm and waive; the coordinator never confirms or waives; a department
# admin has no clinical rights; the root admin edits the organisation and accounts and has no clinical action; the Vaidyx admin
# may do everything except run meetings, record the board and read the whole activity log (security review #2).
CAN = [
    ("view", None, (1, 1, 1, 1, 1, 1, 1, 1)),
    ("upload", "radiology", (1, 1, 1, 0, 0, 0, 1, 0)),
    ("upload", "pathology", (0, 0, 1, 0, 0, 0, 1, 0)),
    ("upload", None, (0, 0, 1, 0, 0, 0, 1, 0)),
    ("upload", "", (0, 0, 1, 0, 0, 0, 1, 0)),
    ("upload_to_case", None, (0, 0, 1, 1, 0, 0, 1, 0)),
    ("inbox", "radiology", (1, 1, 0, 0, 0, 0, 1, 0)),
    ("inbox", "Radiology", (1, 1, 0, 0, 0, 0, 1, 0)),
    ("inbox", "pathology", (0, 0, 0, 0, 0, 0, 1, 0)),
    ("inbox", "breast_surgery", (0, 0, 0, 1, 0, 0, 1, 0)),
    ("inbox", None, (0, 0, 0, 0, 0, 0, 1, 0)),
    ("confirm", "radiology", (1, 1, 0, 1, 0, 0, 1, 0)),
    ("confirm", "pathology", (0, 0, 0, 1, 0, 0, 1, 0)),
    ("confirm", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("dismiss_failed", "radiology", (1, 1, 0, 1, 0, 0, 1, 0)),
    ("dismiss_failed", "pathology", (0, 0, 0, 1, 0, 0, 1, 0)),
    ("dismiss_failed", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("waive", "radiology", (0, 0, 0, 1, 0, 0, 1, 0)),
    ("waive", "pathology", (0, 0, 0, 1, 0, 0, 1, 0)),
    ("waive", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("list_case", None, (0, 0, 1, 0, 0, 0, 1, 0)),
    ("match", None, (0, 0, 1, 0, 0, 0, 1, 0)),
    ("session", None, (0, 0, 1, 0, 0, 0, 0, 0)),  # the Vaidyx admin never runs meetings (security review #2)
    ("create_case", None, (0, 0, 1, 1, 0, 0, 1, 0)),
    ("delete_case", None, (0, 0, 1, 0, 0, 0, 1, 0)),
    ("board_record", None, (0, 0, 1, 0, 0, 0, 0, 0)),  # nor records the board (review #2)
    ("delete_document", "radiology", (0, 1, 1, 1, 0, 0, 1, 0)),
    ("delete_document", "pathology", (0, 0, 1, 1, 0, 0, 1, 0)),
    ("delete_document", "Radiology", (0, 1, 1, 1, 0, 0, 1, 0)),
    ("delete_document", None, (0, 0, 1, 1, 0, 0, 1, 0)),
    ("delete_document", "  ", (0, 0, 1, 1, 0, 0, 1, 0)),
    ("update_action", "radiology", (1, 1, 1, 0, 0, 0, 1, 0)),
    ("update_action", "Radiology", (1, 1, 1, 0, 0, 0, 1, 0)),
    ("update_action", "pathology", (0, 0, 1, 0, 0, 0, 1, 0)),
    ("update_action", None, (0, 0, 1, 0, 0, 0, 1, 0)),
    ("review", None, (1, 1, 1, 1, 0, 0, 1, 0)),
    ("manage_org", None, (0, 0, 0, 0, 0, 1, 1, 0)),
    ("manage_department", "radiology", (0, 0, 0, 0, 1, 1, 1, 0)),
    ("manage_department", "Radio-diagnosis", (0, 0, 0, 0, 1, 1, 1, 0)),
    ("manage_department", "pathology", (0, 0, 0, 0, 0, 1, 1, 0)),
    ("manage_department", None, (0, 0, 0, 0, 0, 1, 1, 0)),
    ("manage_department", "Cardiology", (0, 0, 0, 0, 0, 1, 1, 0)),
    ("read_case", None, (1, 1, 1, 1, 0, 0, 1, 0)),
    ("format_disk", None, (0, 0, 0, 0, 0, 0, 0, 0)),
    ("upload", "Cardiology", (0, 0, 1, 0, 0, 0, 1, 0)),
    ("upload", "Radiology", (1, 1, 1, 0, 0, 0, 1, 0)),
    ("inbox", "Cardiology", (0, 0, 0, 0, 0, 0, 1, 0)),
    ("confirm", "Cardiology", (0, 0, 0, 1, 0, 0, 1, 0)),
    ("waive", "Cardiology", (0, 0, 0, 1, 0, 0, 1, 0)),
    ("delete_document", "Cardiology", (0, 0, 1, 1, 0, 0, 1, 0)),
    ("update_action", "Cardiology", (0, 0, 1, 0, 0, 0, 1, 0)),
    ("dismiss_failed", "Cardiology", (0, 0, 0, 1, 0, 0, 1, 0)),
    # V2 item 4.2 / 4.3: requests are sent, written and closed by treating doctors; answered by the doctors of the department they went to
    ("send_request", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("create_request", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("close_request", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("answer_request", "radiology", (1, 1, 0, 0, 0, 0, 1, 0)),
    ("answer_request", "Radiology", (1, 1, 0, 0, 0, 0, 1, 0)),
    ("answer_request", "pathology", (0, 0, 0, 0, 0, 0, 1, 0)),
    ("answer_request", None, (0, 0, 1, 0, 0, 0, 1, 0)),  # no department: the MDT Coordinator's own row
    ("answer_request", "Cardiology", (0, 0, 0, 0, 0, 0, 1, 0)),
    # V2 items 5.1 / 5.2: the owning department refers and chooses the participants (access.may adds the owner rule per Case File); the
    # receiving department's doctors answer a referral
    ("refer", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("manage_participants", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("answer_referral", "radiology", (1, 1, 0, 0, 0, 0, 1, 0)),
    ("answer_referral", "breast_surgery", (0, 0, 0, 1, 0, 0, 1, 0)),
    ("answer_referral", "pathology", (0, 0, 0, 0, 0, 0, 1, 0)),
    ("answer_referral", None, (0, 0, 0, 0, 0, 0, 1, 0)),
    ("answer_referral", "Cardiology", (0, 0, 0, 0, 0, 0, 1, 0)),
    # V2 item 6.1: the owner marks the Case File ready (access.may adds the owner rule); reminders by the MDT Coordinator on the owner's behalf
    # or by the owner's doctors (access.may_remind)
    ("mark_ready", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("remind", None, (0, 0, 1, 1, 0, 0, 1, 0)),
    # 18 Oct (V3): residents propose (none of these logins is one), the owner's consultants approve, set urgency, manage the team and
    # consent; archive is the owner's or the coordinator's; the activity log is read by the auditor, the coordinator and the root admin;
    # break-glass is the Vaidyx admin's alone
    ("ask", None, (1, 1, 1, 1, 0, 0, 1, 0)),
    ("propose", None, (0, 0, 0, 0, 0, 0, 1, 0)),
    ("approve_proposal", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("set_urgency", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("manage_team", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("archive", None, (0, 0, 1, 1, 0, 0, 1, 0)),
    ("set_consent", None, (0, 0, 0, 1, 0, 0, 1, 0)),
    ("read_audit", None, (0, 0, 1, 0, 0, 1, 0, 0)),  # nor reads the whole log: one Case File inside a break-glass window only (review #2)
    ("break_glass", None, (0, 0, 0, 0, 0, 0, 1, 0)),
]
DEPT_ACTIONS = sorted(a for a, rule in org.ACTIONS.items() if rule["dept"])


def test_every_action_is_in_the_table():
    assert {a for a, _, _ in CAN} - {"format_disk"} == set(org.ACTIONS)


def test_every_department_action_has_a_none_row_and_a_no_dept_rule():
    """The no-department case is decided explicitly for every department-scoped action (review finding S2)."""
    assert {a for a, d, _ in CAN if d is None and a in DEPT_ACTIONS} == set(DEPT_ACTIONS)
    assert all("no_dept" in org.ACTIONS[a] for a in DEPT_ACTIONS)


def test_no_department_is_coordinator_or_treating_business_not_any_head(people):
    """Review finding S2 (V1), kept in V2: a document or action with no department (uploaded straight into a Case File, pre-Phase-2,
    or an empty / unresolved Responsible Department) belongs to the coordinator (and, for clinical confirmations, to the treating
    doctors). A head or member of a supporting department must not delete, update or upload it."""
    h, m, c, a, t = people["head"], people["member"], people["coordinator"], people["admin"], people["treating"]
    for action in ("delete_document", "update_action", "upload"):
        assert org.can(h, action, None) is False, action
        assert org.can(m, action, None) is False, action
        assert org.can(people["two_dept"], action, None) is False, action
        assert org.can(c, action, None) is True, action
        assert org.can(a, action, None) is True, action
        with pytest.raises(PermissionError):
            org.require(h, action, None)
    # an inbox always has a department: none named is admin only
    assert [org.can(people[u], "inbox", None) for u in ("member", "head", "coordinator", "treating", "root", "admin")] == [False, False, False, False, False, True]
    # clinical confirmations without a department: treating doctors (V2), no longer the coordinator, never the root admin
    assert [org.can(people[u], "confirm", None) for u in USERS] == [False, False, False, True, False, False, True, False]
    assert [org.can(people[u], "dismiss_failed", None) for u in USERS] == [False, False, False, True, False, False, True, False]
    assert [org.can(people[u], "waive", None) for u in USERS] == [False, False, False, True, False, False, True, False]


def test_unresolvable_department_matches_no_membership_and_hospital_wide_roles_keep_listed_rights(people):
    """"Cardiology" is not a department: a head of Radiology gets nothing for it; the coordinator and a treating doctor get exactly
    what "who" lists for the action; admins keep everything."""
    h, c, t, a = people["head"], people["coordinator"], people["treating"], people["admin"]
    for action in DEPT_ACTIONS:
        assert org.can(h, action, "Cardiology") is False, action
        assert org.can(c, action, "Cardiology") is ("coordinator" in org.ACTIONS[action]["who"]), action
        assert org.can(t, action, "Cardiology") is ("treating" in org.ACTIONS[action]["who"]), action
        assert org.can(a, action, "Cardiology") is True, action
    assert {x for x in DEPT_ACTIONS if org.can(c, x, "Cardiology")} == {"upload", "delete_document", "update_action"}
    assert {x for x in DEPT_ACTIONS if org.can(t, x, "Cardiology")} == {"confirm", "dismiss_failed", "waive", "delete_document"}


def test_raw_alias_names_resolve_like_ids(people):
    """Routes pass the raw department name ("Radiology", "Department of Radio-diagnosis", a V1 id); it resolves like the id."""
    h = people["head"]
    for name in ("radiology", "radio_diagnosis", "Radiology", "Department of Radio-diagnosis", "radiodiagnosis", " Imaging "):
        assert org.can(h, "delete_document", name) and org.can(h, "inbox", name) and org.can(h, "confirm", name), name
    assert not org.can(h, "delete_document", "Histopathology")
    assert org.can(people["path_member"], "update_action", "Histopathology")
    assert org.can(people["path_member"], "update_action", "Molecular Pathology")  # merged into Pathology


def test_supporting_departments_never_waive_or_create(people):
    """V2 plan section 4: a supporting doctor (even a head) receives and answers notifications; the treating doctor waives and creates."""
    for u in ("member", "head", "two_dept", "path_member"):
        assert not org.can(people[u], "waive", "radiology") and not org.can(people[u], "create_case") and not org.can(people[u], "upload_to_case"), u
    t = people["treating"]
    assert org.can(t, "waive", "radiology") and org.can(t, "create_case") and org.can(t, "upload_to_case") and org.can(t, "confirm", "pathology")
    assert not org.can(t, "inbox", "radiology") and not org.can(t, "session") and not org.can(t, "list_case")
    assert not org.can(people["coordinator"], "waive", "radiology") and not org.can(people["coordinator"], "confirm", "radiology")
    d = people["dept_admin"]
    assert org.can(d, "manage_department", "radiology") and not org.can(d, "manage_department", "pathology") and not org.can(d, "manage_org")
    assert not org.can(d, "inbox", "radiology") and not org.can(d, "confirm", "radiology") and not d["known"] and org.can(d, "view")


def test_department_action_without_no_dept_rule_is_admin_only(people, monkeypatch):
    """Fail closed: a future department-scoped action that forgets "no_dept" is admin only when no department is given."""
    monkeypatch.setitem(org.ACTIONS, "future_dept_action", {"who": ("member", "head", "coordinator"), "dept": True, "doc": ""})
    assert [org.can(people[u], "future_dept_action", None) for u in USERS] == [False, False, False, False, False, False, True, False]
    assert org.can(people["member"], "future_dept_action", "radiology")


@pytest.mark.parametrize("action,dept,expected", CAN)
def test_can(people, action, dept, expected):
    got = tuple(int(org.can(people[u], action, dept)) for u in USERS)
    assert got == expected, dict(zip(USERS, got))


def test_can_specific_cases(people):
    m, h, c = people["member"], people["head"], people["coordinator"]
    assert not org.can(m, "inbox", "pathology") and not org.can(m, "waive", "radiology") and not org.can(m, "list_case")
    assert org.can(h, "delete_document", "radiology") and org.can(h, "delete_document", "Radiology") and not org.can(h, "delete_document", "pathology")
    assert org.can(c, "list_case") and org.can(c, "match") and org.can(c, "create_case")
    assert not org.can(c, "inbox", "radiology") and not org.can(c, "manage_org")
    assert org.can(people["vaidyx_admin"], "manage_org") and org.can(org.roles(""), "manage_org")
    assert not org.can(people["admin"], "no_such_action")
    # two departments: both inboxes, nothing else
    t = people["two_dept"]
    assert org.can(t, "inbox", "pathology") and org.can(t, "inbox", "radiology") and not org.can(t, "inbox", "nuclear_medicine")


def test_require(people):
    org.require(people["treating"], "waive", "radiology")
    with pytest.raises(PermissionError, match="waive") as e:
        org.require(people["head"], "waive", "radiology")
    assert "Radiology" in str(e.value) and "\u2014" not in str(e.value)
    with pytest.raises(PermissionError, match="list_case"):
        org.require(people["member"], "list_case")
    with pytest.raises(PermissionError, match="no_such_action"):
        org.require(people["admin"], "no_such_action")


def test_visible_departments_for_inbox(people):
    all_ids = [d["id"] for d in org.DEFAULT_DEPARTMENTS]
    assert org.visible_departments_for_inbox(people["member"]) == ["radiology"]
    assert org.visible_departments_for_inbox(people["head"]) == ["radiology"]
    assert org.visible_departments_for_inbox(people["two_dept"]) == ["radiology", "pathology"]
    assert org.visible_departments_for_inbox(people["path_member"]) == ["pathology"]
    assert org.visible_departments_for_inbox(people["coordinator"]) == []
    assert org.visible_departments_for_inbox(people["treating"]) == ["breast_surgery"] and org.visible_departments_for_inbox(people["dept_admin"]) == []
    assert org.visible_departments_for_inbox(people["root"]) == []
    assert org.visible_departments_for_inbox(people["admin"]) == all_ids
    assert org.visible_departments_for_inbox(people["vaidyx_admin"]) == all_ids
    assert org.visible_departments_for_inbox(people["unknown"]) == []


def test_my_departments_and_admin_departments(people, data_root):
    assert [(d["id"], d["role"]) for d in org.my_departments(people["two_dept"])] == [("radiology", "member"), ("pathology", "member")]
    assert [(d["id"], d["role"]) for d in org.my_departments(people["head"])] == [("radiology", "head")]
    assert org.my_departments(people["coordinator"]) == []
    assert len(org.my_departments(people["admin"])) == len(org.DEFAULT_DEPARTMENTS) and org.my_departments(people["root"]) == []
    org.save(_org(asha={"admin_of": ["radiology"]}), by="test")
    assert [d["id"] for d in org.admin_departments(org.roles("asha"))] == ["radiology"] and org.my_departments(org.roles("asha")) == []
    assert len(org.admin_departments(org.roles("tbadmin"))) == len(org.DEFAULT_DEPARTMENTS)  # the root admin administers every department
    assert len(org.admin_departments(people["admin"])) == len(org.DEFAULT_DEPARTMENTS)


def test_save_audits_every_account_change(data_root):
    org.save(_org(ravi={"departments": {"radiology": "member"}}), by="root")
    org.save(_org(ravi={"departments": {"radiology": "head"}, "disabled": True}, asha={"coordinator": True}), by="root")
    o = copy.deepcopy(org.load()); o["admins"] = ["tbadmin", "asha"]; o["routes"] = {"breast.cbc": "pathology"}; del o["users"]["ravi"]
    org.save(o, by="root")
    kinds = [(e["kind"], e.get("username")) for e in org.read_audit()]
    assert kinds == [("routes_changed", None), ("root_admins_changed", None), ("account_unplaced", "ravi"), ("org_saved", None),
                     ("account_roles_changed", "ravi"), ("account_placed", "asha"), ("org_saved", None),
                     ("root_admins_changed", None), ("account_placed", "ravi"), ("org_saved", None)]
    ev = next(e for e in org.read_audit() if e["kind"] == "account_roles_changed")
    assert ev["roles_before"]["departments"] == {"radiology": "member"} and ev["roles"]["disabled"] is True


def test_audit_never_stores_a_password(data_root):
    org.audit("account_created", "root", username="x", password="secret-synthetic")
    ev = org.read_audit()[0]
    assert ev["username"] == "x" and "password" not in ev and "secret" not in json.dumps(ev)


def test_no_em_dashes_in_module():
    from pathlib import Path
    assert "\u2014" not in Path(org.__file__).read_text()
