"""org: hospital, departments, users and the one permission check can() (plan item 2.1). Synthetic usernames only."""
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
    """Two-department member, a radiology head, a coordinator, an org admin; saved to the temporary data root."""
    org.save(_org(
        meena={"departments": {"radio_diagnosis": "member", "pathology": "member"}, "display_name": "Dr Meena Iyer"},
        ravi={"departments": {"radio_diagnosis": "member"}},
        suresh={"departments": {"radio_diagnosis": "head"}},
        kavya={"departments": {"pathology": "member"}},
        anil={"coordinator": True},
    ), by="test")
    return {
        "member": org.roles("ravi"),
        "two_dept": org.roles("meena"),
        "head": org.roles("suresh"),
        "path_member": org.roles("kavya"),
        "coordinator": org.roles("anil"),
        "admin": org.roles("tbadmin"),
        "vaidyx_admin": org.roles("root", vaidyx_admin=True),
        "unknown": org.roles("stranger"),
    }


# --- load / save / validate -------------------------------------------------------------------------------------------

def test_load_creates_default_file_and_caches(data_root):
    assert org.path() == data_root / "org.json"
    assert not org.path().exists()
    o = org.load()
    assert org.path().exists()
    assert json.loads(org.path().read_text())["hospital"]["level"] == "essential"
    assert [d["id"] for d in o["departments"]] == [d["id"] for d in org.DEFAULT_DEPARTMENTS]
    assert o["users"] == {} and o["admins"] == []
    assert org.load() is o


def test_load_fills_a_partly_filled_file(data_root):
    (data_root / "org.json").write_text(json.dumps({"hospital": {"name": "Synthetic Cancer Centre"}, "users": {"a": {"departments": {"pathology": "head"}}}}))
    o = org.load()
    assert o["hospital"] == {"name": "Synthetic Cancer Centre", "level": "essential", "type": ""}
    assert len(o["departments"]) == len(org.DEFAULT_DEPARTMENTS) and o["admins"] == []
    assert org.roles("a")["departments"] == {"pathology": "head"}


def test_load_sees_a_changed_file(data_root):
    org.load()
    o = _org(x={"coordinator": True})
    org.save(o, by="admin")
    assert org.roles("x")["coordinator"] is True


def test_save_writes_audit_and_keeps_unknown_keys(data_root):
    o = _org(ravi={"departments": {"radio_diagnosis": "member"}})
    o["future_setting"] = {"keep": True}
    saved = org.save(o, by="admin1")
    assert saved["future_setting"] == {"keep": True}
    assert json.loads(org.path().read_text())["future_setting"] == {"keep": True}
    lines = (data_root / "org_audit.jsonl").read_text().splitlines()
    ev = json.loads(lines[-1])
    assert ev["by"] == "admin1" and ev["kind"] == "org_saved" and ev["departments"] == len(org.DEFAULT_DEPARTMENTS) and ev["users"] == 1
    assert ev["ts"]
    org.save(saved, by="admin2")
    assert len((data_root / "org_audit.jsonl").read_text().splitlines()) == 2


def test_save_rejects_invalid_and_writes_nothing(data_root):
    o = _org(ravi={"departments": {"cardiology": "member"}})
    with pytest.raises(ValueError):
        org.save(o, by="admin")
    assert not (data_root / "org_audit.jsonl").exists()


def _with_depts(depts):
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["departments"] = depts
    return o


@pytest.mark.parametrize("mutate,msg", [
    (lambda o: o["departments"].append({"id": "Bad-Id", "name": "Bad"}), "lower-case"),
    (lambda o: o["departments"].append({"id": "", "name": "Empty"}), "lower-case"),
    (lambda o: o["departments"].append({"id": "pathology", "name": "Pathology Two"}), "used twice"),
    (lambda o: o["departments"].append({"id": "path2", "name": "pathology"}), "used twice"),
    (lambda o: o["departments"].append({"id": "noname", "name": "  "}), "needs a name"),
    (lambda o: o["departments"].append({"id": "x", "name": "X", "aliases": "Radiology"}), "list of text"),
    (lambda o: o["departments"].append({"id": "x", "name": "X", "aliases": ["Radiology"]}), "route to both"),
    (lambda o: o["users"].update(u={"departments": {"cardiology": "member"}}), "unknown department"),
    (lambda o: o["users"].update(u={"departments": {"pathology": "owner"}}), "member or head"),
    (lambda o: o["users"].update(u={"coordinator": "yes"}), "true or false"),
    (lambda o: o["hospital"].update(level="tertiary"), "level"),
    (lambda o: o["hospital"].update(type="trust"), "type"),
    (lambda o: o.update(admins="tbadmin"), "list of usernames"),
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
    o["users"] = {"ravi": {"departments": {"pathology": "head"}}}
    o["admins"] = [" a ", "a", ""]
    clean = org.validate(o)
    assert clean is not o and clean["users"]["ravi"] == {"departments": {"pathology": "head"}, "coordinator": False, "display_name": ""}
    assert clean["admins"] == ["a"]
    assert org.validate(org.DEFAULT_ORG) == {**org.DEFAULT_ORG, "departments": org.DEFAULT_DEPARTMENTS}


# --- routing names ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,dept", [
    ("Radiology", "radio_diagnosis"),
    ("radiology", "radio_diagnosis"),
    ("Department of Radio-diagnosis", "radio_diagnosis"),
    ("Dept. of Radiodiagnosis", "radio_diagnosis"),
    ("radio_diagnosis", "radio_diagnosis"),
    ("Pathology Department", "pathology"),
    ("Pathology", "pathology"),
    ("Molecular Pathology", "molecular_pathology"),
    ("Nuclear Medicine", "nuclear_medicine"),
    ("Medical Oncology", "medical_oncology"),
    ("GI Oncology", "medical_oncology"),
    ("Surgical Oncology", "surgical_oncology"),
    ("Radiation Oncology", "radiation_oncology"),
    ("Laboratory Medicine", "laboratory_medicine"),
    ("Gastroenterology", "gastroenterology"),
    ("Pulmonology", "pulmonary_medicine"),
    ("Medicine", "general_medicine"),
    ("Tumour Board coordinator", "tumour_board"),
    ("Cardiology", None),
    ("", None),
    (None, None),
])
def test_department_id(name, dept):
    assert org.department_id(name) == dept


def test_department_name_and_lookup():
    assert org.department_name("radio_diagnosis") == "Radio-diagnosis"
    assert org.department_name("cardiology") == "cardiology"
    assert org.department("pathology")["name"] == "Pathology"
    assert org.department("cardiology") is None


def test_admin_renamed_department_still_routes(data_root):
    o = copy.deepcopy(org.load())
    o["departments"][0] = {"id": "radio_diagnosis", "name": "Radiodiagnosis and Imaging", "aliases": ["Radiology", "X-ray"]}
    org.save(o, by="admin")
    assert org.department_id("X-ray") == "radio_diagnosis"
    assert org.department_name("radio_diagnosis") == "Radiodiagnosis and Imaging"


# --- roles ----------------------------------------------------------------------------------------------------------------

def test_roles(people):
    assert people["two_dept"] == {"user": "meena", "admin": False, "coordinator": False,
                                  "departments": {"radio_diagnosis": "member", "pathology": "member"}, "known": True}
    assert people["head"]["departments"] == {"radio_diagnosis": "head"} and people["head"]["known"]
    assert people["coordinator"]["coordinator"] and people["coordinator"]["departments"] == {} and people["coordinator"]["known"]
    assert people["vaidyx_admin"]["admin"] and people["vaidyx_admin"]["known"]
    assert people["admin"]["admin"] and people["admin"]["known"]
    assert people["unknown"] == {"user": "stranger", "admin": False, "coordinator": False, "departments": {}, "known": False}
    empty = org.roles("")
    assert empty["admin"] and empty["known"]
    assert org.roles(None)["admin"]


def test_roles_ignore_hand_edited_unknowns(data_root):
    (data_root / "org.json").write_text(json.dumps({"users": {"z": {"departments": {"cardiology": "member", "pathology": "owner"}, "coordinator": "yes"}}}))
    r = org.roles("z")
    assert r["departments"] == {} and r["coordinator"] is False and r["known"] is False


# --- can(): table-driven ----------------------------------------------------------------------------------------------------

USERS = ("member", "head", "coordinator", "admin", "unknown")
# action, department, expected for (member of radio_diagnosis, head of radio_diagnosis, coordinator, admin, unknown)
CAN = [
    ("view", None, (1, 1, 1, 1, 1)),
    ("upload", "radio_diagnosis", (1, 1, 1, 1, 0)),
    ("upload", "pathology", (0, 0, 1, 1, 0)),
    ("upload", None, (1, 1, 1, 1, 0)),
    ("upload_to_case", None, (0, 0, 1, 1, 0)),
    ("inbox", "radio_diagnosis", (1, 1, 0, 1, 0)),
    ("inbox", "Radiology", (1, 1, 0, 1, 0)),
    ("inbox", "pathology", (0, 0, 0, 1, 0)),
    ("inbox", None, (1, 1, 0, 1, 0)),
    ("confirm", "radio_diagnosis", (1, 1, 1, 1, 0)),
    ("confirm", "pathology", (0, 0, 1, 1, 0)),
    ("confirm", None, (0, 0, 1, 1, 0)),
    ("dismiss_failed", "radio_diagnosis", (1, 1, 1, 1, 0)),
    ("dismiss_failed", "pathology", (0, 0, 1, 1, 0)),
    ("dismiss_failed", None, (0, 0, 1, 1, 0)),
    ("waive", "radio_diagnosis", (0, 1, 0, 1, 0)),
    ("waive", "pathology", (0, 0, 0, 1, 0)),
    ("waive", None, (0, 0, 0, 1, 0)),
    ("list_case", None, (0, 0, 1, 1, 0)),
    ("match", None, (0, 0, 1, 1, 0)),
    ("session", None, (0, 0, 1, 1, 0)),
    ("create_case", None, (0, 0, 1, 1, 0)),
    ("delete_case", None, (0, 0, 1, 1, 0)),
    ("board_record", None, (0, 0, 1, 1, 0)),
    ("delete_document", "radio_diagnosis", (0, 1, 1, 1, 0)),
    ("delete_document", "pathology", (0, 0, 1, 1, 0)),
    ("update_action", "radio_diagnosis", (1, 1, 1, 1, 0)),
    ("update_action", "pathology", (0, 0, 1, 1, 0)),
    ("review", None, (1, 1, 1, 1, 0)),
    ("manage_org", None, (0, 0, 0, 1, 0)),
    ("format_disk", None, (0, 0, 0, 0, 0)),
    ("upload", "Cardiology", (0, 0, 1, 1, 0)),
]


def test_every_action_is_in_the_table():
    assert {a for a, _, _ in CAN} - {"format_disk"} == set(org.ACTIONS)


@pytest.mark.parametrize("action,dept,expected", CAN)
def test_can(people, action, dept, expected):
    got = tuple(int(org.can(people[u], action, dept)) for u in USERS)
    assert got == expected, dict(zip(USERS, got))


def test_can_specific_cases(people):
    m, h, c = people["member"], people["head"], people["coordinator"]
    assert not org.can(m, "inbox", "pathology") and not org.can(m, "waive", "radio_diagnosis") and not org.can(m, "list_case")
    assert org.can(h, "waive", "radio_diagnosis") and org.can(h, "waive", "Radiology") and not org.can(h, "waive", "pathology")
    assert org.can(c, "list_case") and org.can(c, "match") and org.can(c, "create_case")
    assert not org.can(c, "inbox", "radio_diagnosis") and not org.can(c, "manage_org")
    assert org.can(people["vaidyx_admin"], "manage_org") and org.can(org.roles(""), "manage_org")
    assert not org.can(people["admin"], "no_such_action")
    # two departments: both inboxes, nothing else
    t = people["two_dept"]
    assert org.can(t, "inbox", "pathology") and org.can(t, "inbox", "radio_diagnosis") and not org.can(t, "inbox", "nuclear_medicine")


def test_require(people):
    org.require(people["head"], "waive", "radio_diagnosis")
    with pytest.raises(PermissionError, match="waive") as e:
        org.require(people["member"], "waive", "radio_diagnosis")
    assert "Radio-diagnosis" in str(e.value) and "\u2014" not in str(e.value)
    with pytest.raises(PermissionError, match="list_case"):
        org.require(people["member"], "list_case")
    with pytest.raises(PermissionError, match="no_such_action"):
        org.require(people["admin"], "no_such_action")


def test_visible_departments_for_inbox(people):
    all_ids = [d["id"] for d in org.DEFAULT_DEPARTMENTS]
    assert org.visible_departments_for_inbox(people["member"]) == ["radio_diagnosis"]
    assert org.visible_departments_for_inbox(people["head"]) == ["radio_diagnosis"]
    assert org.visible_departments_for_inbox(people["two_dept"]) == ["radio_diagnosis", "pathology"]
    assert org.visible_departments_for_inbox(people["path_member"]) == ["pathology"]
    assert org.visible_departments_for_inbox(people["coordinator"]) == []
    assert org.visible_departments_for_inbox(people["admin"]) == all_ids
    assert org.visible_departments_for_inbox(people["vaidyx_admin"]) == all_ids
    assert org.visible_departments_for_inbox(people["unknown"]) == []


def test_my_departments(people):
    assert [(d["id"], d["role"]) for d in org.my_departments(people["two_dept"])] == [("radio_diagnosis", "member"), ("pathology", "member")]
    assert [(d["id"], d["role"]) for d in org.my_departments(people["head"])] == [("radio_diagnosis", "head")]
    assert org.my_departments(people["coordinator"]) == []
    assert len(org.my_departments(people["admin"])) == len(org.DEFAULT_DEPARTMENTS)


def test_no_em_dashes_in_module():
    from pathlib import Path
    assert "\u2014" not in Path(org.__file__).read_text()
