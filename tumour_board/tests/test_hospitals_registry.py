"""The hospital registry (admin consoles, 16 Nov 2026, docs/admin-console/DESIGN.md D1 to D3, D8, D11): create, ids, status, logins,
file modes, the platform audit, and how a request's hospital is worked out. Temporary folders only (conftest)."""
import json, os, stat

import pytest

from tumour_board import config, hospitals, org


def _mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def test_default_only_is_single_hospital(data_root):
    assert hospitals.list_hospitals()[0]["id"] == "default" and len(hospitals.list_hospitals()) == 1
    assert not hospitals.multi() and hospitals.ids() == ["default"]
    assert hospitals.hospital_of("anyone@x.in") == "default" and hospitals.registered("anyone@x.in") is None
    assert not config.HOSPITALS_ROOT.exists()  # nothing is written until a hospital is made
    # the default hospital's name is the one its set-up wrote
    o = org.load(); o = json.loads(json.dumps(o)); o["hospital"]["name"] = "Vaidyx Demo Hospital"; org.save(o, by="test")
    assert hospitals.get("default")["name"] == "Vaidyx Demo Hospital"


def test_hospitals_root_is_a_sibling_by_default():
    assert config.HOSPITALS_ROOT != config.BASE_ROOT
    assert config.BASE_ROOT not in config.HOSPITALS_ROOT.parents


def test_create_makes_folder_org_and_registry(data_root):
    h = hospitals.create("City Care Hospital, Pune", by="admin", city="Pune", state="Maharashtra")
    assert h["id"] == "city-care-hospital-pune" and h["status"] == "active" and h["name"] == "City Care Hospital, Pune"
    folder = config.root_for(h["id"])
    assert folder == config.HOSPITALS_ROOT / h["id"] and folder.is_dir() and _mode(folder) == 0o700
    assert _mode(config.HOSPITALS_ROOT) == 0o700 and _mode(hospitals.registry_path()) == 0o600 and _mode(hospitals.audit_path()) == 0o600
    assert not (folder / "his.json").exists()  # no hospital system until its admin sets one up
    with config.use_hospital(h["id"]):
        o = org.load()
        assert o["hospital"]["name"] == "City Care Hospital, Pune" and len(o["departments"]) == len(org.DEFAULT_ORG["departments"])
        assert o["users"] == {} and o["admins"] == []
        assert [e["kind"] for e in org.read_audit()] == ["hospital_changed", "org_saved"]
    assert org.load()["hospital"]["name"] == ""  # the default hospital is untouched
    assert hospitals.multi() and hospitals.ids() == ["default", h["id"]]
    reg = json.loads(hospitals.registry_path().read_text())
    assert reg["version"] == 1 and set(reg["hospitals"]) == {h["id"]} and reg["users"] == {}
    assert reg["hospitals"][h["id"]]["created_by"] == "admin" and reg["hospitals"][h["id"]]["created_at"]


def test_ids_are_unique_and_checked(data_root):
    a = hospitals.create("Sunrise", by="admin")
    b = hospitals.create("Sunrise", by="admin")
    assert (a["id"], b["id"]) == ("sunrise", "sunrise-2")
    assert hospitals.create("X", by="admin")["id"] == "hospital-x"  # too short a slug gets a prefix
    assert hospitals.slug("Sri Ramakrishna Instituté of Oncology") == "sri-ramakrishna-institute-of-oncology"
    assert hospitals.create("Given", by="admin", hid="given-id")["id"] == "given-id"
    for bad in ("default", "sunrise"):
        with pytest.raises(hospitals.HospitalError) as e:
            hospitals.create("Again", by="admin", hid=bad)
        assert e.value.status == 409
    for bad in ("Bad Id", "-x", "a", "../etc", "a" * 50):
        with pytest.raises(hospitals.HospitalError):
            hospitals.create("Bad", by="admin", hid=bad)
    with pytest.raises(hospitals.HospitalError):
        hospitals.create("   ", by="admin")
    for bad in ("default/../x", "../x", "A", ""):
        with pytest.raises(ValueError):
            config.root_for(bad)


def test_an_unregistered_folder_is_never_adopted(data_root):
    (config.HOSPITALS_ROOT / "left-over").mkdir(parents=True)
    with pytest.raises(hospitals.HospitalError) as e:
        hospitals.create("Left over", by="admin", hid="left-over")
    assert e.value.status == 409
    assert hospitals.create("Left over", by="admin")["id"] == "left-over-2"


def test_hospitals_root_inside_base_root_is_refused(data_root, monkeypatch):
    monkeypatch.setattr(config, "HOSPITALS_ROOT", config.BASE_ROOT / "hospitals")
    with pytest.raises(hospitals.HospitalError):
        hospitals.create("Inside", by="admin")


def test_status_update_and_audit(data_root):
    h = hospitals.create("Lotus Cancer Centre", by="admin")["id"]
    with pytest.raises(hospitals.HospitalError):
        hospitals.set_status(h, "suspended", by="admin")  # a reason is required
    with pytest.raises(hospitals.HospitalError):
        hospitals.set_status("default", "suspended", by="admin", reason="no")
    with pytest.raises(hospitals.HospitalError):
        hospitals.set_status(h, "deleted", by="admin", reason="x")
    assert hospitals.set_status(h, "suspended", by="admin", reason="Contract paused")["status"] == "suspended"
    assert hospitals.active_ids() == ["default"] and hospitals.ids() == ["default", h]
    assert hospitals.get(h)["suspended_reason"] == "Contract paused"
    assert hospitals.set_status(h, "active", by="admin")["suspended_reason"] == ""
    assert hospitals.update(h, by="admin", city="Kochi")["city"] == "Kochi"
    assert hospitals.update("default", by="admin", state="Kerala")["state"] == "Kerala"
    with pytest.raises(hospitals.HospitalError):
        hospitals.update("default", by="admin", name="Renamed")
    with pytest.raises(hospitals.HospitalError):
        hospitals.update(h, by="admin", status="suspended")
    with pytest.raises(hospitals.HospitalError):
        hospitals.update("nope", by="admin", city="x")
    assert not any(r["id"] == "default" and r.get("status") != "active" for r in hospitals.list_hospitals())
    kinds = [e["kind"] for e in hospitals.read_audit()]
    assert kinds == ["hospital_updated", "hospital_updated", "hospital_reactivated", "hospital_suspended", "hospital_created"]
    assert [e["kind"] for e in hospitals.read_audit(kind="hospital_suspended")] == ["hospital_suspended"]
    assert len(hospitals.read_audit(hospital=h)) == 4 and len(hospitals.read_audit(limit=2)) == 2


def test_logins_assign_and_unassign(data_root):
    h = hospitals.create("Lotus", by="admin")["id"]
    assert hospitals.assign("Asha@Lotus.in", h, by="admin") == h
    assert hospitals.hospital_of("asha@lotus.in") == h and hospitals.users_of(h) == ["asha@lotus.in"]
    with pytest.raises(hospitals.HospitalError):
        hospitals.assign("x@y.in", "missing", by="admin")
    assert hospitals.assign("asha@lotus.in", "default", by="admin") == "default"  # unregistered means default
    assert hospitals.registered("asha@lotus.in") is None
    hospitals.assign("asha@lotus.in", h, by="admin")
    assert hospitals.unassign("asha@lotus.in", by="admin") and not hospitals.unassign("asha@lotus.in", by="admin")
    kinds = [e["kind"] for e in hospitals.read_audit()]
    assert kinds[:4] == ["login_unassigned", "login_assigned", "login_assigned", "login_assigned"]


def test_audit_never_writes_a_secret(data_root):
    hospitals.audit("probe", "admin", hospital="x", password="Secret123", api_token="t", client_secret="s", note="kept")
    raw = hospitals.audit_path().read_text()
    assert "Secret123" not in raw and '"t"' not in raw and '"s"' not in raw and "kept" in raw


def test_resolve(data_root):
    h = hospitals.create("Lotus", by="admin")["id"]
    hospitals.assign("bina", h, by="admin")
    assert hospitals.resolve(None) == ("default", None) and hospitals.resolve("") == ("default", None)
    assert hospitals.resolve("anil") == ("default", None)
    assert hospitals.resolve("anil", requested=h) == ("default", None)  # only a Vaidyx admin may choose
    assert hospitals.resolve("bina") == (h, None)
    assert hospitals.resolve("bina", requested="default") == (h, None)
    assert hospitals.resolve("admin", vaidyx_admin=True, requested=h) == (h, None)
    assert hospitals.resolve("admin", vaidyx_admin=True, requested="nope") == ("default", None)
    assert hospitals.resolve("admin", vaidyx_admin=True) == ("default", None)
    hospitals.set_status(h, "suspended", by="admin", reason="paused")
    assert hospitals.resolve("bina") == (h, "hospital_suspended")
    assert hospitals.resolve("admin", vaidyx_admin=True, requested=h) == (h, None)  # the Vaidyx admin is exempt
    reg = json.loads(hospitals.registry_path().read_text()); reg["users"]["ghost"] = "gone"
    hospitals.registry_path().write_text(json.dumps(reg))
    assert hospitals.resolve("ghost") == ("gone", "hospital_unknown")


def test_registry_is_reread_when_the_file_changes(data_root):
    h = hospitals.create("Lotus", by="admin")["id"]
    reg = json.loads(hospitals.registry_path().read_text())
    reg["users"]["zed"] = h
    hospitals.registry_path().write_text(json.dumps(reg, indent=4))  # another size: a new signature
    assert hospitals.hospital_of("zed") == h


def test_strict_mode_raises_without_a_current_hospital(data_root, monkeypatch):
    import contextvars
    blank = contextvars.Context()  # no hospital set
    assert blank.run(config.hospital_id) == "default"  # one hospital: quietly the default
    hospitals.create("Lotus", by="admin")
    monkeypatch.delenv("TB_HOSPITAL_STRICT", raising=False)
    assert blank.run(config.hospital_id) == "default"  # several hospitals, not strict: logged once, the default
    monkeypatch.setenv("TB_HOSPITAL_STRICT", "1")
    with pytest.raises(config.HospitalContextError):
        blank.run(lambda: config.DATA_ROOT / "x")
    assert config.hospital_id() == "default"  # the test's own context has the hospital set
