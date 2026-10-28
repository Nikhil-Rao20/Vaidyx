"""The people and departments directory (night-v3 item 8.3, contract docs/night-v3/research/06_messages.md section 9.6): who is listed
(placed, not disabled or expired, and the MDT Coordinator; never the root admin, an auditor, an outside expert, a department admin
without a placement or the Vaidyx admin), which fields (never the registration number, e-mail, password or admin flags; the phone only
when the person made it visible; the photo as a link to its own route), the search (name, title, department name, prefix, case
insensitive), the department filter, the departments list with member counts, 403 not_placed, 429, and nothing written. Synthetic
people only."""
import base64, copy, hashlib

import pytest

from tumour_board import directory, messages, org, profiles
from tumour_board.api import common
from tumour_board.api import directory as api_directory
from tumour_board.tests.test_nik_meetings import As, app, tc, hospital_org  # noqa: F401

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-photo-bytes" * 4
GIF = b"GIF89a" + b"synthetic" * 3
PLACED = {"anil", "priya", "asha", "ravi", "suresh", "meena", "dev", "lata", "kiran", "mohan"}


def data_url(raw: bytes, kind: str = "png") -> str:
    return f"data:image/{kind};base64," + base64.b64encode(raw).decode()


@pytest.fixture(autouse=True)
def _fresh_limits():
    api_directory.DIRECTORY_LIMIT._hits.clear()
    api_directory.PHOTO_LIMIT._hits.clear()
    yield
    api_directory.DIRECTORY_LIMIT._hits.clear()
    api_directory.PHOTO_LIMIT._hits.clear()


@pytest.fixture
def people(app):  # noqa: F811
    """The meetings hospital plus a department admin without a placement and an auditor; profiles with titles, phones and photos."""
    o = copy.deepcopy(org.load())
    o["users"]["deepa"] = {"admin_of": ["radiology"], "display_name": "Deepa Admin"}
    o["users"]["audit1"] = {"auditor": True, "display_name": "Arun Auditor"}
    org.save(o, by="test")
    profiles.update("priya", {"title": "Breast Surgeon", "registration_no": "KMC 12345", "phone": "+91 98450 00001",
                              "phone_visible": True, "photo": data_url(PNG)}, doctor=True)
    profiles.update("asha", {"title": "Senior Resident", "registration_no": "KMC 22222", "phone": "+91 98450 00002",
                             "phone_visible": False}, doctor=True)
    profiles.update("ravi", {"title": "Interventional Radiologist", "photo": data_url(GIF, "gif")}, doctor=True)
    profiles.update("guest", {"title": "Visiting Professor", "photo": data_url(PNG)})
    return app


def by_user(rows):
    return {p["user"]: p for p in rows}


def test_who_is_listed(people):
    got = by_user(directory.people())
    assert set(got) == PLACED
    for absent in ("tbroot", "guest", "admin", "deepa", "audit1"):
        assert absent not in got
    assert all(messages.may_use(org.roles(u)) for u in got)


def test_disabled_and_expired_are_not_listed(people):
    o = copy.deepcopy(org.load())
    o["users"]["ravi"]["disabled"] = True
    o["users"]["asha"]["end_date"] = "2020-01-01"
    org.save(o, by="test")
    got = by_user(directory.people())
    assert "ravi" not in got and "asha" not in got
    assert set(got) == PLACED - {"ravi", "asha"}
    assert directory.photo("ravi") is None  # a person who left the list has no photo either
    radiology = next(d for d in directory.departments() if d["id"] == "radiology")
    assert radiology["members"] == 1


def test_fields_present_and_absent(people):
    got = by_user(directory.people())
    p = got["priya"]
    assert set(p) == {"user", "display_name", "title", "departments", "coordinator", "online", "photo", "phone"}
    assert p["display_name"] == "Dr Priya Nair" and p["title"] == "Breast Surgeon"
    assert p["departments"] == [{"id": "breast_surgery", "name": "Breast Surgery", "role": "Consultant"}]
    assert p["coordinator"] is False and p["online"] == "offline"
    assert got["suresh"]["departments"][0]["role"] == "Head"
    assert got["asha"]["departments"][0]["role"] == "Resident"
    assert got["anil"]["coordinator"] is True and got["anil"]["departments"] == []
    flat = repr(directory.people()) + repr(directory.coordinators()) + repr(directory.departments())
    for secret in ("registration_no", "KMC 12345", "KMC 22222", "email", "password", "root_admin", "admin_of", "vaidyx_admin",
                   "data:image", base64.b64encode(PNG).decode()[:20]):
        assert secret not in flat


def test_phone_only_when_visible(people):
    got = by_user(directory.people())
    assert got["priya"]["phone"] == "+91 98450 00001"
    assert got["asha"]["phone"] is None  # saved but not made visible
    assert got["ravi"]["phone"] is None  # none saved


def test_presence_comes_from_messages(people, monkeypatch):
    monkeypatch.setattr(messages, "PRESENCE", lambda u: "online" if u == "ravi" else "away" if u == "priya" else "offline")
    got = by_user(directory.people())
    assert got["ravi"]["online"] == "online" and got["priya"]["online"] == "away" and got["meena"]["online"] == "offline"


def test_photo_url_and_route(people, tc):  # noqa: F811
    got = by_user(directory.people())
    assert got["priya"]["photo"] == "/api/tb/directory/priya/photo"
    assert got["ravi"]["photo"] == "/api/tb/directory/ravi/photo"
    assert got["meena"]["photo"] is None
    r = As(tc, "meena").get("/directory/priya/photo")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "private, max-age=300" and r.headers["x-content-type-options"] == "nosniff"
    r = As(tc, "anil").get("/directory/ravi/photo")
    assert r.status_code == 200 and r.content == GIF and r.headers["content-type"] == "image/gif"
    assert As(tc, "priya").get("/directory/meena/photo").status_code == 404  # no photo
    assert As(tc, "priya").get("/directory/guest/photo").status_code == 404  # not listed, even with a photo
    assert As(tc, "priya").get("/directory/nobody/photo").status_code == 404


def test_jpg_photo_is_served_as_jpeg(people, tc):  # noqa: F811
    profiles.update("meena", {"photo": data_url(b"\xff\xd8\xff synthetic jpeg", "jpg")}, doctor=True)
    r = As(tc, "priya").get("/directory/meena/photo")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


def test_search_by_name_title_and_department(people):
    assert [p["user"] for p in directory.people("PRI")] == ["priya"]
    assert [p["user"] for p in directory.people("nair")] == ["priya"]  # any word of the name
    assert [p["user"] for p in directory.people("dr priya")] == ["priya"]
    assert [p["user"] for p in directory.people("interv")] == ["ravi"]  # title
    assert {p["user"] for p in directory.people("radiol")} == {"ravi", "suresh"}  # department name (and ravi's title)
    assert {p["user"] for p in directory.people("breast")} == {"priya", "asha"}
    assert {p["user"] for p in directory.people("oncology")} == {"dev", "lata", "kiran"}
    assert [p["user"] for p in directory.people("mdt")] == ["anil"]
    assert directory.people("iya") == []  # a prefix, not a substring
    assert directory.people("zzz") == []


def test_sorted_and_at_most_thirty(people):
    names = [p["display_name"] for p in directory.people()]
    assert names == sorted(names, key=str.casefold)
    o = copy.deepcopy(org.load())
    for i in range(40):
        o["users"][f"doc{i:02d}"] = {"departments": {"pathology": "member"}, "display_name": f"Dr Synthetic {i:02d}"}
    org.save(o, by="test")
    assert len(directory.people()) == directory.MAX_PEOPLE == 30
    assert len(directory.people("synthetic")) == 30
    path = next(d for d in directory.departments() if d["id"] == "pathology")
    assert path["members"] == 41  # the count is not cut


def test_department_filter(people):
    assert {p["user"] for p in directory.people(department="radiology")} == {"ravi", "suresh"}
    assert {p["user"] for p in directory.people("sur", department="radiology")} == {"suresh"}
    assert {p["user"] for p in directory.people(department="Breast Surgery")} == {"priya", "asha"}  # a name resolves too
    assert directory.people(department="no_such_department") == []
    assert directory.people(department="nuclear_medicine") == []


def test_departments_list_with_member_counts(people):
    got = {d["id"]: d for d in directory.departments()}
    assert set(got) == {"breast_surgery", "radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology", "microbiology"}
    assert got["breast_surgery"] == {"id": "breast_surgery", "name": "Breast Surgery", "group": "treating", "members": 2}
    assert got["radiology"]["members"] == 2 and got["radiology"]["group"] == "supporting"  # deepa administers it, unplaced: not counted
    names = [d["name"] for d in directory.departments()]
    assert names == sorted(names, key=str.casefold)
    assert [d["id"] for d in directory.departments("radio")] == ["radiology"]


def test_placed_coordinator_shows_in_both_lists(people):
    o = copy.deepcopy(org.load())
    o["users"]["meena"]["coordinator"] = True
    org.save(o, by="test")
    assert {p["user"] for p in directory.coordinators()} == {"anil", "meena"}
    meena = by_user(directory.people())["meena"]
    assert meena["coordinator"] is True and meena["departments"][0]["id"] == "pathology"


def test_route_returns_the_contract(people, tc):  # noqa: F811
    r = As(tc, "priya").get("/directory")
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"people", "departments", "coordinators", "me"} and b["me"] == "priya"
    assert {p["user"] for p in b["people"]} == PLACED
    assert [c["user"] for c in b["coordinators"]] == ["anil"]
    assert {d["id"] for d in b["departments"]} >= {"radiology", "breast_surgery"}
    b = As(tc, "anil").get("/directory", params={"q": "radiol", "department": "radiology"}).json()
    assert {p["user"] for p in b["people"]} == {"ravi", "suresh"} and [d["id"] for d in b["departments"]] == ["radiology"]
    assert [c["user"] for c in b["coordinators"]] == ["anil"]  # always there, whatever the search
    assert "KMC" not in r.text and "data:image" not in r.text and "registration" not in r.text


@pytest.mark.parametrize("who", ["tbroot", "guest", "admin"])
def test_unplaced_get_403_not_placed(people, tc, who):  # noqa: F811
    for path in ("/directory", "/directory/priya/photo"):
        r = As(tc, who).get(path)
        assert r.status_code == 403
        assert r.json()["detail"] == {"message": "Messages are for placed hospital staff.", "code": "not_placed"}


def test_expired_login_gets_403(people, tc):  # noqa: F811
    o = copy.deepcopy(org.load())
    o["users"]["asha"]["end_date"] = "2020-01-01"
    org.save(o, by="test")
    r = As(tc, "asha").get("/directory")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_placed"


def test_rate_limits(people, tc, monkeypatch):  # noqa: F811
    assert api_directory.DIRECTORY_LIMIT.limit == 60 and api_directory.DIRECTORY_LIMIT.window == 60
    assert api_directory.PHOTO_LIMIT.limit == 120 and api_directory.PHOTO_LIMIT.window == 60
    monkeypatch.setattr(api_directory, "DIRECTORY_LIMIT", common.RateLimit(2, 60))
    monkeypatch.setattr(api_directory, "PHOTO_LIMIT", common.RateLimit(2, 60))
    for _ in range(2):
        assert As(tc, "priya").get("/directory").status_code == 200
        assert As(tc, "meena").get("/directory/priya/photo").status_code == 200
    r = As(tc, "priya").get("/directory")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    r = As(tc, "meena").get("/directory/priya/photo")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    assert As(tc, "ravi").get("/directory").status_code == 200  # another person has their own allowance


def _digest(paths):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in paths}


def test_nothing_is_written(people, tc, data_root):  # noqa: F811
    files = [data_root / "org.json", data_root / "profiles.json", data_root / "org_audit.jsonl"]
    before = _digest(files)
    assert before["org.json"] and before["profiles.json"]
    tree = sorted(str(p.relative_to(data_root)) for p in data_root.rglob("*"))
    for user in ("priya", "anil", "tbroot", "guest"):
        As(tc, user).get("/directory", params={"q": "dr"})
        As(tc, user).get("/directory", params={"department": "radiology"})
        As(tc, user).get("/directory/priya/photo")
        As(tc, user).get("/directory/meena/photo")
    directory.people(); directory.departments(); directory.coordinators(); directory.photo("priya")
    assert _digest(files) == before
    assert sorted(str(p.relative_to(data_root)) for p in data_root.rglob("*")) == tree


def test_router_paths():
    paths = {getattr(r, "path", "") for r in api_directory.router.routes}
    assert paths == {"/directory", "/directory/{user}/photo"}
