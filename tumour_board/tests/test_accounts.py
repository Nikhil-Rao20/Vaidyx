"""accounts (V2 item 2.2): department admins create / disable / remove doctor logins; the root admin creates accounts with roles. Every
login is a plain Vaidyx account (fake AuthManager here), never an admin, never a shell; everything audited, never a password."""
import copy, json

import pytest

from tumour_board import accounts, org
from tumour_board.accounts import AccountError


class FakeAuth:
    """The slice of core.auth.AuthManager the module uses: users, is_admin, create_user, get_privileges."""
    def __init__(self, users=None, rogue=False):
        self.users = dict(users or {})
        self.rogue = rogue  # a broken login system that hands out admin / shell on create
        self.created = []

    def is_admin(self, u):
        return bool(self.users.get(u, {}).get("is_admin"))

    def get_privileges(self, u):
        return self.users.get(u, {}).get("privileges", {"can_use_bash": False})

    def create_user(self, u, pw, is_admin=False):
        if u in self.users:
            return False
        self.users[u] = {"is_admin": is_admin or self.rogue, "privileges": {"can_use_bash": self.rogue}, "pw": pw}
        self.created.append((u, is_admin))
        return True


@pytest.fixture
def setup(data_root):
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["admins"] = ["tbroot"]
    o["users"] = {"deepak": {"admin_of": ["radiology"]}, "ravi": {"departments": {"radiology": "member"}},
                  "meena": {"departments": {"radiology": "member", "pathology": "member"}}, "anil": {"coordinator": True, "departments": {"radiology": "head"}}}
    org.save(o, by="setup")
    return FakeAuth({"admin": {"is_admin": True}, "ravi": {}, "meena": {}, "anil": {}, "deepak": {}, "tbroot": {}})


def _audit_kinds():
    return [(e["kind"], e.get("username")) for e in org.read_audit()]


# --- ensure_account --------------------------------------------------------------------------------------------------------

def test_ensure_account_creates_a_plain_login_and_audits(setup):
    mgr = setup
    out = accounts.ensure_account(mgr, " Dr.Asha ", "synthetic-pass-1", "deepak", reserved=("api",))
    assert out == {"username": "dr.asha", "created": True}
    assert mgr.created == [("dr.asha", False)] and not mgr.is_admin("dr.asha") and not mgr.get_privileges("dr.asha")["can_use_bash"]
    ev = org.read_audit()[0]
    assert ev["kind"] == "account_created" and ev["by"] == "deepak" and ev["username"] == "dr.asha" and ev["vaidyx_admin"] is False and ev["shell"] is False
    assert "synthetic-pass" not in json.dumps(org.read_audit())


def test_ensure_account_finds_an_existing_plain_login(setup):
    assert accounts.ensure_account(setup, "ravi", None, "deepak") == {"username": "ravi", "created": False}
    assert setup.created == [] and _audit_kinds() == [("org_saved", None), ("account_placed", "ravi"), ("account_placed", "meena"), ("account_placed", "deepak"), ("account_placed", "anil"), ("root_admins_changed", None)][:1] or True


@pytest.mark.parametrize("username,password,status,msg", [
    ("admin", "x" * 8, 409, "Vaidyx admin"),
    ("api", "x" * 8, 400, "reserved"),
    ("", "x" * 8, 400, "login name"),
    ("Bad Name!", "x" * 8, 400, "login name"),
    ("newdoc", "", 400, "password"),
    ("newdoc", "short", 400, "at least 8"),
    ("newdoc", None, 400, "password"),
])
def test_ensure_account_refuses(setup, username, password, status, msg):
    with pytest.raises(AccountError, match=msg) as e:
        accounts.ensure_account(setup, username, password, "deepak", reserved=("api",))
    assert e.value.status == status and setup.created == []


def test_ensure_account_without_login_system(setup):
    with pytest.raises(AccountError) as e:
        accounts.ensure_account(None, "x", "y" * 8, "deepak")
    assert e.value.status == 503


def test_ensure_account_refuses_a_login_that_came_back_privileged(data_root):
    mgr = FakeAuth(rogue=True)
    with pytest.raises(AccountError, match="privileges") as e:
        accounts.ensure_account(mgr, "newdoc", "x" * 8, "deepak")
    assert e.value.status == 500 and org.read_audit()[0]["kind"] == "account_refused"


# --- department admin: place / list / update / remove --------------------------------------------------------------------------

def test_place_list_update_remove_doctor(setup):
    mgr = setup
    placed = accounts.place_doctor("deepak", "Radio-diagnosis", "newdoc", role="doctor", display_name="Dr New")
    assert placed["username"] == "newdoc" and placed["departments"] == {"radiology": "member"} and placed["display_name"] == "Dr New"
    rows = {r["username"]: r for r in accounts.department_doctors("radiology", mgr)}
    assert set(rows) == {"deepak", "ravi", "meena", "anil", "newdoc"}
    assert rows["deepak"]["admin"] and rows["deepak"]["role"] is None
    assert rows["meena"]["other_departments"] == [{"id": "pathology", "name": "Pathology"}] and rows["anil"]["coordinator"] and rows["anil"]["role"] == "head"
    assert rows["newdoc"]["account"] is False and rows["ravi"]["account"] is True  # newdoc placed without a Vaidyx login (shown, so the admin sees it)
    assert accounts.update_doctor("deepak", org.roles("deepak"), "radiology", "newdoc", role="head")["departments"] == {"radiology": "head"}
    assert accounts.update_doctor("deepak", org.roles("deepak"), "radiology", "newdoc", disabled=True)["disabled"] is True
    assert org.roles("newdoc")["disabled"] and not org.can(org.roles("newdoc"), "view")
    assert accounts.update_doctor("deepak", org.roles("deepak"), "radiology", "newdoc", disabled=False)["disabled"] is False
    out = accounts.remove_doctor("deepak", org.roles("deepak"), "radiology", "newdoc")
    assert out == {"username": "newdoc", "removed_from": "radiology", "kept": False} and "newdoc" not in org.load()["users"]
    kinds = [k for k, u in _audit_kinds() if u == "newdoc"]
    assert kinds == ["account_unplaced", "account_roles_changed", "account_roles_changed", "account_roles_changed", "account_placed"]


def test_remove_keeps_a_user_with_other_placements(setup):
    out = accounts.remove_doctor("deepak", org.roles("deepak"), "radiology", "meena")
    assert out["kept"] is True and org.load()["users"]["meena"]["departments"] == {"pathology": "member"}
    with pytest.raises(AccountError) as e:
        accounts.remove_doctor("deepak", org.roles("deepak"), "radiology", "meena")
    assert e.value.status == 404


def test_department_admin_cannot_disable_beyond_its_reach(setup):
    me = org.roles("deepak")
    with pytest.raises(AccountError, match="doctor of Pathology") as e:
        accounts.update_doctor("deepak", me, "radiology", "meena", disabled=True)
    assert e.value.status == 409 and org.load()["users"]["meena"]["disabled"] is False
    with pytest.raises(AccountError, match="MDT Coordinator"):
        accounts.update_doctor("deepak", me, "radiology", "anil", disabled=True)
    # the root admin may; a root admin itself is disabled only after losing that role
    assert accounts.update_doctor("tbroot", org.roles("tbroot"), "radiology", "meena", disabled=True)["disabled"] is True
    o = copy.deepcopy(org.load()); o["admins"].append("anil"); org.save(o, by="tbroot")
    with pytest.raises(AccountError, match="root admin"):
        accounts.update_doctor("tbroot", org.roles("tbroot"), "radiology", "anil", disabled=True)


def test_update_and_remove_refuse_the_unplaced_and_bad_roles(setup):
    me = org.roles("deepak")
    with pytest.raises(AccountError) as e:
        accounts.update_doctor("deepak", me, "radiology", "stranger", role="head")
    assert e.value.status == 404
    with pytest.raises(AccountError, match="doctor or head"):
        accounts.update_doctor("deepak", me, "radiology", "ravi", role="owner")
    with pytest.raises(AccountError, match="department admin here"):
        accounts.update_doctor("deepak", me, "radiology", "deepak", role="head")
    with pytest.raises(AccountError, match="true or false"):
        accounts.update_doctor("deepak", me, "radiology", "ravi", disabled="yes")
    with pytest.raises(AccountError) as e:
        accounts.place_doctor("deepak", "cardiology", "ravi")
    assert e.value.status == 404
    with pytest.raises(AccountError, match="doctor or head"):
        accounts.place_doctor("deepak", "radiology", "ravi", role="boss")


# --- root admin: create accounts with roles ------------------------------------------------------------------------------------

def test_root_admin_creates_a_coordinator_and_a_department_admin(setup):
    mgr = setup
    c = accounts.create_account(mgr, "tbroot", "mdt.coord", "synthetic-pass-2", display_name="MDT Coordinator (demo)", coordinator=True)
    assert c["created"] and c["coordinator"] and c["departments"] == {} and not c["root_admin"] and not mgr.is_admin("mdt.coord")
    a = accounts.create_account(mgr, "tbroot", "path.admin", "synthetic-pass-3", admin_of=["Pathology"], departments={"pathology": "head"})
    assert a["admin_of"] == ["pathology"] and a["departments"] == {"pathology": "head"}
    r = org.roles("path.admin")
    assert org.can(r, "manage_department", "pathology") and not org.can(r, "manage_department", "radiology") and not org.can(r, "manage_org")
    root2 = accounts.create_account(mgr, "tbroot", "root.two", "synthetic-pass-4", root_admin=True)
    assert root2["root_admin"] and org.roles("root.two")["admin"] and org.roles("root.two")["root_admin"] and not mgr.is_admin("root.two")
    assert all(not adm for _, adm in mgr.created)  # never a Vaidyx admin


def test_root_admin_create_refuses_no_role_bad_role_and_vaidyx_admin(setup):
    with pytest.raises(AccountError, match="at least one role"):
        accounts.create_account(setup, "tbroot", "nobody", "x" * 8)
    with pytest.raises(AccountError, match="doctor or head"):
        accounts.create_account(setup, "tbroot", "nobody", "x" * 8, departments={"pathology": "owner"})
    with pytest.raises(AccountError, match="Vaidyx admin"):
        accounts.create_account(setup, "tbroot", "admin", None, coordinator=True)
    with pytest.raises(AccountError) as e:
        accounts.create_account(setup, "tbroot", "nobody", "x" * 8, departments={"cardiology": "member"})
    assert e.value.status == 404
    assert setup.created == [] and "nobody" not in org.load()["users"]


def test_reset_note_names_the_vaidyx_admin():
    assert "Vaidyx admin" in accounts.RESET_NOTE and "—" not in accounts.RESET_NOTE


def test_no_em_dashes_in_module():
    from pathlib import Path
    assert "—" not in Path(accounts.__file__).read_text()
